import os
import json
import time
import boto3
from botocore.config import Config
from datetime import datetime
from typing import List, Dict, Optional

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "zeroday-news-issues")

# Module-level S3 client - reused across Lambda invocations (container reuse)
_s3_client = None

def _get_s3_client():
    """Return the S3 client (cached for Lambda container reuse)."""
    global _s3_client
    if _s3_client is None:
        max_connections = max(10, int(os.getenv("S3_MAX_POOL_CONNECTIONS", "16")))
        _s3_client = boto3.client(
            "s3",
            region_name=os.getenv("AWS_REGION", "ap-south-2"),
            config=Config(max_pool_connections=max_connections),
        )
    return _s3_client

# Simple in-memory cache with 60-second TTL
_s3_cache = {
    "dates": None,
    "issues": {},
    "last_checked": 0
}

CACHE_TTL = 60  # Refresh every minute

def get_issue_dates() -> List[str]:
    """Returns a sorted list of all available issue dates (YYYY-MM-DD), newest first."""
    s3 = _get_s3_client()

    current_time = time.time()
    # If cache is valid, return it
    if _s3_cache["dates"] is not None and (current_time - _s3_cache["last_checked"] < CACHE_TTL):
        return _s3_cache["dates"]

    try:
        dates = []
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix="issue_")
        if "Contents" in response:
            for obj in response["Contents"]:
                key = obj["Key"]
                try:
                    date_str = key.replace("issue_", "").replace(".json", "")
                    datetime.strptime(date_str, "%Y-%m-%d")
                    dates.append(date_str)
                except ValueError:
                    pass

        # Handle pagination if more than 1000 objects
        while response.get("IsTruncated"):
            response = s3.list_objects_v2(
                Bucket=S3_BUCKET_NAME,
                Prefix="issue_",
                ContinuationToken=response.get("NextContinuationToken")
            )
            if "Contents" in response:
                for obj in response["Contents"]:
                    key = obj["Key"]
                    try:
                        date_str = key.replace("issue_", "").replace(".json", "")
                        datetime.strptime(date_str, "%Y-%m-%d")
                        dates.append(date_str)
                    except ValueError:
                        pass

        dates.sort(reverse=True)
        _s3_cache["dates"] = dates
        _s3_cache["last_checked"] = time.time()
        return dates
    except Exception as e:
        print(f"[CONTENT] Error listing S3 objects: {e}")
        return []

def get_issue_data(date_str: str) -> Optional[Dict]:
    """Reads and returns the JSON data for a specific issue date from S3."""
    if date_str in _s3_cache["issues"]:
        return _s3_cache["issues"][date_str]

    s3 = _get_s3_client()
    try:
        file_key = f"issue_{date_str}.json"
        response = s3.get_object(Bucket=S3_BUCKET_NAME, Key=file_key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        _s3_cache["issues"][date_str] = data
        return data
    except Exception as e:
        print(f"[CONTENT] Error downloading from S3 for {date_str}: {e}")
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

def delete_issue(date_str: str) -> bool:
    """Deletes an issue by date from AWS S3."""
    s3 = _get_s3_client()
    try:
        file_key = f"issue_{date_str}.json"
        s3.delete_object(Bucket=S3_BUCKET_NAME, Key=file_key)

        # Invalidate cache
        if date_str in _s3_cache["issues"]:
            del _s3_cache["issues"][date_str]
        _s3_cache["dates"] = None
        _s3_cache["last_checked"] = 0

        return True
    except Exception as e:
        print(f"[CONTENT] Error deleting S3 object {date_str}: {e}")
        return False
