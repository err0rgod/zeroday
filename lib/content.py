import os
import json
from datetime import datetime
from typing import List, Dict, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
OUTPUT_DIR = os.path.join(DATA_DIR, "output")

# Simple in-memory cache with 10-minute TTL
_blob_cache = {
    "dates": None,
    "issues": {},
    "last_checked": 0
}

import time
CACHE_TTL = 600 # 10 minutes

def _get_blob_service():
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str: return None, None
    try:
        from azure.storage.blob import BlobServiceClient
        service = BlobServiceClient.from_connection_string(conn_str)
        container = os.getenv("AZURE_CONTAINER_NAME", "news")
        return service, container
    except Exception:
        return None, None

def get_issue_dates() -> List[str]:
    """Returns a sorted list of all available issue dates (YYYY-MM-DD), newest first."""
    service, container = _get_blob_service()
    
    if service:
        current_time = time.time()
        # If cache is valid, return it
        if _blob_cache["dates"] is not None and (current_time - _blob_cache["last_checked"] < CACHE_TTL):
            return _blob_cache["dates"]
            
        try:
            container_client = service.get_container_client(container)
            dates = []
            for blob in container_client.list_blobs(name_starts_with="issue_"):
                # Extract date from "issue_2026-03-24.json"
                try:
                    date_str = blob.name.replace("issue_", "").replace(".json", "")
                    datetime.strptime(date_str, "%Y-%m-%d")
                    dates.append(date_str)
                except ValueError:
                    pass
            dates.sort(reverse=True)
            _blob_cache["dates"] = dates
            _blob_cache["last_checked"] = time.time()
            return dates
        except Exception as e:
            print(f"Error listing blobs: {e}")
            pass # Fall back to local
    
    if not os.path.exists(OUTPUT_DIR):
        return []
    
    dates = []
    for d in os.listdir(OUTPUT_DIR):
        path = os.path.join(OUTPUT_DIR, d)
        if os.path.isdir(path):
            try:
                datetime.strptime(d, "%Y-%m-%d")
                dates.append(d)
            except ValueError:
                pass # not a date folder
                
    dates.sort(reverse=True)
    return dates

def get_issue_data(date_str: str) -> Optional[Dict]:
    """Reads and returns the JSON data for a specific issue date."""
    if date_str in _blob_cache["issues"]:
        return _blob_cache["issues"][date_str]

    service, container = _get_blob_service()
    if service:
        try:
            container_client = service.get_container_client(container)
            blob_client = container_client.get_blob_client(f"issue_{date_str}.json")
            data = json.loads(blob_client.download_blob().readall())
            _blob_cache["issues"][date_str] = data
            return data
        except Exception as e:
            print(f"Error downloading blob for {date_str}: {e}")
            pass # Fall back to local
            
    json_path = os.path.join(OUTPUT_DIR, date_str, "newsletter_prepared_data.json")
    if not os.path.exists(json_path):
        return None
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _blob_cache["issues"][date_str] = data
            return data
    except Exception as e:
        print(f"Error reading {json_path}: {e}")
        return None

def get_latest_issue() -> Optional[Dict]:
    """Returns the latest issue data, if any."""
    dates = get_issue_dates()
    if not dates:
        return None
    return get_issue_data(dates[0])

def get_all_articles() -> List[Dict]:
    """Returns a flat list of all articles across all issues (useful for search)."""
    dates = get_issue_dates()
    all_articles = []
    
    for d in dates:
        issue = get_issue_data(d)
        if issue and "top_stories" in issue:
            for story in issue["top_stories"]:
                story["issue_date"] = issue.get("date", d)
                all_articles.append(story)
                
    return all_articles

def search_articles(query: str) -> List[Dict]:
    """Simple text search on article titles and summaries."""
    if not query:
        return []
        
    query = query.lower()
    results = []
    for article in get_all_articles():
        title = article.get("title", "").lower()
        summary = article.get("short_summary", "").lower()
        
        if query in title or query in summary:
            results.append(article)
            
    return results
