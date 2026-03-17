import time
import logging
from functools import wraps
from difflib import SequenceMatcher

# Setup basic logging for utilities
logger = logging.getLogger(__name__)

def compress_content(content: str) -> str:
    """
    Compresses long article content to save AI tokens.
    If content > 4000 characters, keeps the first 1500 and last 500 characters,
    removing the middle section.
    """
    if not content:
        return ""
        
    if len(content) <= 4000:
        return content
        
    # Keep first 1500 and last 500
    compressed = content[:1500] + "\n\n... [CONTENT COMPRESSED] ...\n\n" + content[-500:]
    return compressed

def rate_limit_and_retry(max_retries=3, base_delay=2.0):
    """
    Decorator to enforce a minimum delay between API calls and retry on failures 
    with exponential backoff.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries <= max_retries:
                try:
                    # Enforce minimum delay before every attempt
                    time.sleep(base_delay)
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries > max_retries:
                        logger.error(f"[{func.__name__}] Failed after {max_retries} retries: {e}")
                        raise e
                        
                    # Exponential backoff
                    sleep_time = base_delay * (2 ** (retries - 1))
                    logger.warning(f"[{func.__name__}] Error occurred: {e}. Retrying in {sleep_time}s... ({retries}/{max_retries})")
                    time.sleep(sleep_time)
            return None
        return wrapper
    return decorator

def is_duplicate_title(title1: str, title2: str, threshold: float = 0.8) -> bool:
    """
    Returns True if two titles have a similarity ratio > threshold (default 80%).
    """
    if not title1 or not title2:
        return False
        
    similarity = SequenceMatcher(None, title1.lower(), title2.lower()).ratio()
    return similarity > threshold

def rank_article(content: str) -> int:
    """
    Scores an article based on the frequency of high-priority cybersecurity keywords.
    """
    if not content:
        return 0
        
    content_lower = content.lower()
    
    # High priority keywords requested
    keywords = [
        "zero-day",
        "critical vulnerability",
        "data breach",
        "ransomware",
        "nation state",
        "mass exploitation",
        "supply chain attack"
    ]
    
    score = 0
    for kw in keywords:
        # Add 1 point for every occurrence of a high priority keyword
        score += content_lower.count(kw)
        
    return score
