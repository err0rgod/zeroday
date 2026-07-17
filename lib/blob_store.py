import os
import uuid
import boto3
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr
from typing import Optional, List

TABLE_NAME = os.getenv("DYNAMODB_TABLE") or os.getenv("DYNAMODB_TABLE_NAME", "zeroday-subscribers")
SUBSCRIBER_BADGE_INITIAL_VALUE = int(os.getenv("SUBSCRIBER_BADGE_INITIAL_VALUE", "62"))

# Module-level resource - reused across Lambda invocations (container reuse)
_dynamodb = None
_table = None

def _get_table():
    """Return the DynamoDB table resource (cached for Lambda container reuse)."""
    global _dynamodb, _table
    if _table is None:
        _dynamodb = boto3.resource("dynamodb")
        _table = _dynamodb.Table(TABLE_NAME)
    return _table

def _make_key(email: str) -> dict:
    """Build the composite key for a subscriber item."""
    return {"PK": f"EMAIL#{email.lower()}", "SK": "PROFILE"}


def _subscriber_badge_key() -> dict:
    return {"PK": "METRIC#SUBSCRIBERS", "SK": "COUNT"}

def _extract_email(item: dict) -> str:
    """Extract the raw email address from a PK field."""
    pk = item.get("PK", "")
    return pk.replace("EMAIL#", "") if pk.startswith("EMAIL#") else pk

def get_subscriber(email: str) -> Optional[dict]:
    """Return a single subscriber dict by email, or None."""
    table = _get_table()
    try:
        response = table.get_item(Key=_make_key(email))
        item = response.get("Item")
        if item:
            item["email"] = _extract_email(item)
        return item
    except Exception as e:
        print(f"[DYNAMODB] Error getting subscriber {email}: {e}")
        return None

def get_subscriber_by_token(token_type: str, token_value: str) -> Optional[dict]:
    """
    Find a subscriber by a token field (verification_token or unsubscribe_token).
    Uses scan with filter - acceptable for small subscriber counts.
    For production scale, add GSIs on token fields.
    """
    table = _get_table()
    try:
        response = table.scan(
            FilterExpression=Attr(token_type).eq(token_value)
        )
        items = response.get("Items", [])

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(
                FilterExpression=Attr(token_type).eq(token_value),
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            items.extend(response.get("Items", []))

        if items:
            items[0]["email"] = _extract_email(items[0])
            return items[0]
        return None
    except Exception as e:
        print(f"[DYNAMODB] Error getting subscriber by token {token_type}: {e}")
        return None

def add_subscriber(email: str, verification_token: str, unsubscribe_token: str,
                   created_at: str, verification_token_created_at: str) -> bool:
    """
    Create a new subscriber entry in DynamoDB.
    Returns False if the email already exists.
    """
    email_lower = email.lower()
    if get_subscriber(email_lower):
        return False

    table = _get_table()
    try:
        table.put_item(
            Item={
                "PK": f"EMAIL#{email_lower}",
                "SK": "PROFILE",
                "user_id": str(uuid.uuid4()),
                "verified_email": False,
                "is_active": True,
                "verification_token": verification_token,
                "verification_token_created_at": verification_token_created_at,
                "unsubscribe_token": unsubscribe_token,
                "created_at": created_at,
            },
            ConditionExpression="attribute_not_exists(PK)"
        )
        return True
    except Exception as e:
        print(f"[DYNAMODB] Error adding subscriber {email_lower}: {e}")
        return False

def update_subscriber(email: str, **kwargs) -> bool:
    """
    Update fields on an existing subscriber by email.
    Returns False if the subscriber is not found.
    """
    email_lower = email.lower()
    if not get_subscriber(email_lower):
        return False

    table = _get_table()

    update_expr = "SET "
    expr_attr_values = {}
    expr_attr_names = {}

    for key, value in kwargs.items():
        # Use expression attribute names to avoid DynamoDB reserved words
        expr_attr_names[f"#{key}"] = key
        expr_attr_values[f":{key}"] = value

    update_expr += ", ".join([f"#{k} = :{k}" for k in kwargs.keys()])

    try:
        table.update_item(
            Key=_make_key(email_lower),
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
        return True
    except Exception as e:
        print(f"[DYNAMODB] Error updating subscriber {email_lower}: {e}")
        return False

def remove_subscriber(email: str) -> bool:
    """Remove a subscriber by email."""
    email_lower = email.lower()
    if not get_subscriber(email_lower):
        return False

    table = _get_table()
    try:
        table.delete_item(Key=_make_key(email_lower))
        return True
    except Exception as e:
        print(f"[DYNAMODB] Error removing subscriber {email_lower}: {e}")
        return False

def get_active_verified_emails() -> list:
    """Return a list of email strings for active, verified subscribers."""
    table = _get_table()
    try:
        response = table.scan(
            FilterExpression=Attr("verified_email").eq(True) & Attr("is_active").eq(True)
        )
        emails = [_extract_email(item) for item in response.get("Items", [])]

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(
                FilterExpression=Attr("verified_email").eq(True) & Attr("is_active").eq(True),
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            emails.extend([_extract_email(item) for item in response.get("Items", [])])

        return emails
    except Exception as e:
        print(f"[DYNAMODB] Error getting active verified emails: {e}")
        return []

def count_active_verified() -> int:
    """Return the count of active, verified subscribers."""
    return len(get_active_verified_emails())


def get_or_create_subscriber_badge_counter() -> dict:
    """Return the cumulative public subscriber counter, creating it at 62 if needed."""
    table = _get_table()
    initialized_at = datetime.now(timezone.utc).isoformat()
    try:
        table.put_item(
            Item={
                **_subscriber_badge_key(),
                "value": SUBSCRIBER_BADGE_INITIAL_VALUE,
                "initialized_at": initialized_at,
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        pass

    response = table.get_item(Key=_subscriber_badge_key(), ConsistentRead=True)
    item = response.get("Item")
    if not item:
        raise RuntimeError("Subscriber badge counter is unavailable")
    return item


def _parse_utc_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def mark_subscriber_verified(email: str) -> bool:
    """
    Verify a subscriber and increment the public counter exactly once when eligible.

    Returns True when this call increments the badge counter.
    """
    email_lower = email.lower()
    subscriber = get_subscriber(email_lower)
    if not subscriber:
        raise ValueError("Subscriber not found")

    counter = get_or_create_subscriber_badge_counter()
    created_at = _parse_utc_timestamp(subscriber.get("created_at", ""))
    initialized_at = _parse_utc_timestamp(counter.get("initialized_at", ""))
    should_increment = (
        not subscriber.get("verified_email", False)
        and not subscriber.get("badge_counted", False)
        and created_at is not None
        and initialized_at is not None
        and created_at >= initialized_at
    )

    table = _get_table()
    if not should_increment:
        table.update_item(
            Key=_make_key(email_lower),
            UpdateExpression=(
                "SET verified_email = :verified, is_active = :active, "
                "badge_counted = :counted"
            ),
            ExpressionAttributeValues={
                ":verified": True,
                ":active": True,
                ":counted": True,
            },
        )
        return False

    client = table.meta.client
    try:
        client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": TABLE_NAME,
                        "Key": {
                            "PK": {"S": f"EMAIL#{email_lower}"},
                            "SK": {"S": "PROFILE"},
                        },
                        "UpdateExpression": (
                            "SET verified_email = :verified, is_active = :active, "
                            "badge_counted = :counted"
                        ),
                        "ConditionExpression": (
                            "(attribute_not_exists(verified_email) OR verified_email = :unverified) "
                            "AND (attribute_not_exists(badge_counted) OR badge_counted = :uncounted)"
                        ),
                        "ExpressionAttributeValues": {
                            ":verified": {"BOOL": True},
                            ":unverified": {"BOOL": False},
                            ":active": {"BOOL": True},
                            ":counted": {"BOOL": True},
                            ":uncounted": {"BOOL": False},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": TABLE_NAME,
                        "Key": {
                            "PK": {"S": _subscriber_badge_key()["PK"]},
                            "SK": {"S": _subscriber_badge_key()["SK"]},
                        },
                        "UpdateExpression": "ADD #value :one",
                        "ExpressionAttributeNames": {"#value": "value"},
                        "ExpressionAttributeValues": {":one": {"N": "1"}},
                        "ConditionExpression": "attribute_exists(PK)",
                    }
                },
            ]
        )
        return True
    except client.exceptions.TransactionCanceledException:
        current = get_subscriber(email_lower)
        if current and current.get("verified_email") and current.get("badge_counted"):
            return False
        raise

def get_recent_subscribers(limit: int = 10) -> list:
    """Return the most recently created subscribers (newest first)."""
    table = _get_table()
    try:
        profile_filter = Attr("SK").eq("PROFILE")
        response = table.scan(FilterExpression=profile_filter)
        all_items = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(
                FilterExpression=profile_filter,
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            all_items.extend(response.get("Items", []))

        # Inject email field from PK for downstream consumers
        for item in all_items:
            item["email"] = _extract_email(item)

        try:
            sorted_subs = sorted(all_items, key=lambda s: s.get("created_at", ""), reverse=True)
        except Exception:
            sorted_subs = all_items

        return sorted_subs[:limit]
    except Exception as e:
        print(f"[DYNAMODB] Error getting recent subscribers: {e}")
        return []
