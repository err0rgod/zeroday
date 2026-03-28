import os
import json
from typing import Optional
from dotenv import load_dotenv

# Load .env from project root
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path, override=True)

BLOB_NAME = "subscribers.json"
BACKUP_BLOB_NAME = "subscribers_backup.json"


def _get_blob_client():
    """Return a BlobClient for the subscribers.json blob."""
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("AZURE_CONTAINER_NAME", "news")
    if not conn_str:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set.")
    from azure.storage.blob import BlobServiceClient
    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container_client = blob_service.get_container_client(container_name)
    if not container_client.exists():
        container_client.create_container()
    return container_client.get_blob_client(BLOB_NAME)


def _get_backup_blob_client():
    """Return a BlobClient for the subscribers_backup.json blob."""
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("AZURE_CONTAINER_NAME", "news")
    if not conn_str:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set.")
    from azure.storage.blob import BlobServiceClient
    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container_client = blob_service.get_container_client(container_name)
    if not container_client.exists():
        container_client.create_container()
    return container_client.get_blob_client(BACKUP_BLOB_NAME)


def load_subscribers() -> list:
    """
    Download and parse subscribers.json from Azure Blob Storage.
    Returns [] if the blob does not exist or on any error.
    """
    try:
        blob_client = _get_blob_client()
        raw = blob_client.download_blob().readall().decode("utf-8-sig")
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception as e:
        err = str(e)
        if "BlobNotFound" in err or "The specified blob does not exist" in err:
            return []
        print(f"[BLOB] load_subscribers error: {e}")
    return []


def save_subscribers(data: list) -> bool:
    """Upload the full subscribers list to Azure Blob Storage."""
    try:
        blob_client = _get_blob_client()
        payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8-sig")
        blob_client.upload_blob(payload, overwrite=True)
        print(f"[BLOB] Saved {len(data)} subscribers to blob.")
        return True
    except Exception as e:
        print(f"[BLOB] save_subscribers error: {e}")
        return False


def _append_to_backup(email: str):
    """
    Append an email to the backup list if not already present.
    Never removes any entries.
    """
    try:
        blob_client = _get_backup_blob_client()
        data = []
        try:
            raw = blob_client.download_blob().readall().decode("utf-8-sig")
            data = json.loads(raw)
        except Exception:
            pass  # Likely blob doesn't exist yet

        if not isinstance(data, list):
            data = []

        email_lower = email.lower()
        if email_lower not in [e.lower() for e in data if isinstance(e, str)]:
            data.append(email_lower)
            payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8-sig")
            blob_client.upload_blob(payload, overwrite=True)
            print(f"[BLOB] Added {email} to backup archive.")
    except Exception as e:
        print(f"[BLOB] _append_to_backup error: {e}")


def get_subscriber(email: str) -> Optional[dict]:
    """Return a single subscriber dict by email, or None."""
    subscribers = load_subscribers()
    for sub in subscribers:
        if sub.get("email", "").lower() == email.lower():
            return sub
    return None


def get_subscriber_by_token(token_type: str, token_value: str) -> Optional[dict]:
    """
    Find a subscriber by a token field.
    token_type: 'verification_token' or 'unsubscribe_token'
    """
    subscribers = load_subscribers()
    for sub in subscribers:
        if sub.get(token_type) == token_value:
            return sub
    return None


def add_subscriber(email: str, verification_token: str, unsubscribe_token: str,
                   created_at: str, verification_token_created_at: str) -> bool:
    """
    Append a new subscriber entry to blob storage.
    Returns False if the email already exists.
    """
    subscribers = load_subscribers()
    if any(s.get("email", "").lower() == email.lower() for s in subscribers):
        return False
    subscribers.append({
        "email": email,
        "verified_email": False,
        "is_active": True,
        "verification_token": verification_token,
        "verification_token_created_at": verification_token_created_at,
        "unsubscribe_token": unsubscribe_token,
        "created_at": created_at,
    })
    # Also save to append-only backup
    _append_to_backup(email)
    return save_subscribers(subscribers)


def update_subscriber(email: str, **kwargs) -> bool:
    """
    Update fields on an existing subscriber by email.
    Returns False if the subscriber is not found.
    """
    subscribers = load_subscribers()
    found = False
    for sub in subscribers:
        if sub.get("email", "").lower() == email.lower():
            sub.update(kwargs)
            found = True
            break
    if not found:
        return False
    # Ensure they are in the append-only archive
    _append_to_backup(email)
    return save_subscribers(subscribers)


def remove_subscriber(email: str) -> bool:
    """Remove a subscriber by email and re-save."""
    subscribers = load_subscribers()
    new_list = [s for s in subscribers if s.get("email", "").lower() != email.lower()]
    if len(new_list) == len(subscribers):
        return False  # not found
    return save_subscribers(new_list)


def get_active_verified_emails() -> list:
    """Return a list of email strings for active, verified subscribers."""
    subscribers = load_subscribers()
    return [
        s["email"]
        for s in subscribers
        if s.get("verified_email") and s.get("is_active", True)
    ]


def count_active_verified() -> int:
    """Return the count of active, verified subscribers."""
    return len(get_active_verified_emails())


def get_recent_subscribers(limit: int = 10) -> list:
    """Return the most recently created subscribers (newest first)."""
    subscribers = load_subscribers()
    try:
        sorted_subs = sorted(subscribers, key=lambda s: s.get("created_at", ""), reverse=True)
    except Exception:
        sorted_subs = subscribers
    return sorted_subs[:limit]
