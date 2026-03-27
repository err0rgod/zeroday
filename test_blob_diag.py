"""Quick diagnostic: test Azure Blob Storage read/write from the project."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
container = os.getenv("AZURE_CONTAINER_NAME", "news")

print(f"Connection string set: {bool(conn_str)}")
print(f"Container name: {container}")

if not conn_str:
    print("ERROR: AZURE_STORAGE_CONNECTION_STRING is not set.")
    sys.exit(1)

from lib.blob_store import load_subscribers, add_subscriber, remove_subscriber, get_subscriber_by_token

print("\n--- Testing load_subscribers ---")
subs = load_subscribers()
print(f"Loaded {len(subs)} subscribers from blob.")

print("\n--- Testing add_subscriber ---")
TEST_EMAIL = "_test_diag_@zeroday.test"
result = add_subscriber(
    email=TEST_EMAIL,
    verification_token="diagtoken123",
    verification_token_created_at="2099-01-01T00:00:00",
    unsubscribe_token="diagunsubtoken123",
    created_at="2099-01-01T00:00:00",
)
print(f"add_subscriber result: {result}")

print("\n--- Testing get_subscriber_by_token ---")
found = get_subscriber_by_token("verification_token", "diagtoken123")
print(f"Found by token: {found}")

print("\n--- Cleaning up test entry ---")
removed = remove_subscriber(TEST_EMAIL)
print(f"remove_subscriber result: {removed}")

print("\nDiagnosis complete.")
