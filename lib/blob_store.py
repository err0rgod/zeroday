import os
import uuid
import boto3
from boto3.dynamodb.conditions import Key, Attr
from typing import Optional, List

TABLE_NAME = os.getenv("DYNAMODB_TABLE") or os.getenv("DYNAMODB_TABLE_NAME", "zeroday-subscribers")

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

def get_recent_subscribers(limit: int = 10) -> list:
    """Return the most recently created subscribers (newest first)."""
    table = _get_table()
    try:
        response = table.scan()
        all_items = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
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
