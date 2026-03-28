import os
import json
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
container = os.getenv("AZURE_CONTAINER_NAME", "news")

if not conn_str:
    print("No connection string!")
    exit(1)

client = BlobServiceClient.from_connection_string(conn_str)
blob = client.get_container_client(container).get_blob_client("subscribers.json")

try:
    content = blob.download_blob().readall().decode("utf-8-sig")
    data = json.loads(content)
    print(f"Total entries in blob: {len(data)}")
    for sub in data:
        print(f"EMAIL: {sub.get('email')}")
        print(f"VERIFIED: {sub.get('verified_email')}")
        print(f"ACTIVE: {sub.get('is_active')}")
        print("-" * 20)
except Exception as e:
    print(f"Error: {e}")
