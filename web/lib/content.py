import os
import json
from datetime import datetime
from typing import List, Dict, Optional

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "content_gen", "output")

def get_issue_dates() -> List[str]:
    """Returns a sorted list of all available issue dates (YYYY-MM-DD), newest first."""
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
    json_path = os.path.join(OUTPUT_DIR, date_str, "newsletter_prepared_data.json")
    if not os.path.exists(json_path):
        return None
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
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
