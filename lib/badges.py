import hashlib
import html
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, Iterator, Tuple

import tiktoken

from lib.blob_store import get_or_create_subscriber_badge_counter
from lib.content import get_issue_data, get_issue_dates


BADGE_LABELS = {
    "tokens": "tokens used",
    "subscribers": "subscribers",
    "posts": "posts written",
}

BADGE_COLORS = {
    "black": "#000000",
    "blue": "#007ec6",
    "brightgreen": "#4c1",
    "green": "#4c1",
    "grey": "#555555",
    "gray": "#555555",
    "lightgrey": "#9f9f9f",
    "lightgray": "#9f9f9f",
    "orange": "#fe7d37",
    "purple": "#9f4bff",
    "red": "#e05d44",
    "yellow": "#dfb317",
    "yellowgreen": "#a4a61d",
}

STORY_TEXT_FIELDS = ("title", "category", "short_summary", "deep_summary")
CONTENT_CACHE_TTL = int(os.getenv("BADGE_CONTENT_CACHE_TTL", "900"))
S3_READ_WORKERS = max(1, int(os.getenv("BADGE_S3_READ_WORKERS", "16")))

_content_cache = {"expires_at": 0.0, "metrics": None}
_content_cache_lock = threading.Lock()
_encoding = None


def _get_encoding():
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def _iter_strings(value) -> Iterator[str]:
    if isinstance(value, str):
        value = value.strip()
        if value:
            yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def _roast_paragraphs(value) -> list:
    paragraphs = []
    for text in _iter_strings(value):
        paragraphs.extend(part.strip() for part in re.split(r"[\r\n]+", text) if part.strip())
    return paragraphs


def _issue_text_and_post_count(issue: dict) -> Tuple[Iterable[str], int]:
    texts = []
    stories = issue.get("top_stories") or []
    cves = issue.get("cves") or []

    for story in stories:
        if not isinstance(story, dict):
            continue
        for field in STORY_TEXT_FIELDS:
            texts.extend(_iter_strings(story.get(field)))

    for cve in cves:
        if not isinstance(cve, dict):
            continue
        for field in ("title", "summary"):
            texts.extend(_iter_strings(cve.get(field)))
        cve_identifiers = cve.get("cve_ids") or cve.get("cve_id")
        texts.extend(_iter_strings(cve_identifiers))

    roasts = _roast_paragraphs(issue.get("roast_summary"))
    texts.extend(roasts)
    post_count = len(stories) + len(cves) + len(roasts)
    return texts, post_count


def calculate_published_metrics(issues: Iterable[dict]) -> Dict[str, int]:
    encoding = _get_encoding()
    token_count = 0
    post_count = 0

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        texts, issue_posts = _issue_text_and_post_count(issue)
        token_count += sum(len(encoding.encode(text)) for text in texts)
        post_count += issue_posts

    return {"tokens": token_count, "posts": post_count}


def get_published_metrics() -> Dict[str, int]:
    now = time.monotonic()
    cached = _content_cache["metrics"]
    if cached is not None and now < _content_cache["expires_at"]:
        return cached.copy()

    with _content_cache_lock:
        now = time.monotonic()
        cached = _content_cache["metrics"]
        if cached is not None and now < _content_cache["expires_at"]:
            return cached.copy()

        dates = get_issue_dates()
        issues = []
        if dates:
            # Prime the shared boto3 client before reading the remaining objects concurrently.
            issues.append(get_issue_data(dates[0]))
            with ThreadPoolExecutor(max_workers=min(S3_READ_WORKERS, len(dates))) as executor:
                issues.extend(executor.map(get_issue_data, dates[1:]))

        for date_str, issue in zip(dates, issues):
            if issue is None:
                raise RuntimeError(f"Unable to read issue {date_str} from S3")

        metrics = calculate_published_metrics(issues)
        _content_cache["metrics"] = metrics
        _content_cache["expires_at"] = now + CONTENT_CACHE_TTL
        return metrics.copy()


def get_badge_value(metric: str) -> int:
    if metric == "subscribers":
        counter = get_or_create_subscriber_badge_counter()
        return int(counter["value"])
    if metric in ("tokens", "posts"):
        return get_published_metrics()[metric]
    raise KeyError(metric)


def normalize_badge_text(value: str, default: str, max_length: int = 32) -> str:
    if not value:
        return default
    cleaned = "".join(char for char in value.strip() if unicodedata.category(char)[0] != "C")
    return cleaned[:max_length] or default


def normalize_badge_color(value: str, default: str) -> str:
    if not value:
        return default
    normalized = value.strip().lower()
    if normalized in BADGE_COLORS:
        return BADGE_COLORS[normalized]
    match = re.fullmatch(r"#?([0-9a-f]{3}|[0-9a-f]{6})", normalized)
    if match:
        return f"#{match.group(1)}"
    return default


def _text_width(value: str) -> int:
    units = sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in value)
    return max(40, units * 7 + 14)


def render_badge_svg(label: str, value: str, left_color: str, right_color: str) -> str:
    label = normalize_badge_text(label, "badge")
    value = normalize_badge_text(value, "unavailable")
    left_color = normalize_badge_color(left_color, BADGE_COLORS["black"])
    right_color = normalize_badge_color(right_color, BADGE_COLORS["green"])

    left_width = _text_width(label)
    right_width = _text_width(value)
    total_width = left_width + right_width
    escaped_label = html.escape(label, quote=True)
    escaped_value = html.escape(value, quote=True)
    escaped_accessible = html.escape(f"{label}: {value}", quote=True)
    left_x = left_width / 2
    right_x = left_width + right_width / 2

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" '
        f'role="img" aria-label="{escaped_accessible}">'
        f'<title>{escaped_accessible}</title>'
        '<clipPath id="badge-clip"><rect width="100%" height="20" rx="3"/></clipPath>'
        '<g clip-path="url(#badge-clip)">'
        f'<rect width="{left_width}" height="20" fill="{left_color}"/>'
        f'<rect x="{left_width}" width="{right_width}" height="20" fill="{right_color}"/>'
        '</g>'
        '<g fill="#fff" text-anchor="middle" '
        'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{left_x:g}" y="15" fill="#010101" fill-opacity=".3">{escaped_label}</text>'
        f'<text x="{left_x:g}" y="14">{escaped_label}</text>'
        f'<text x="{right_x:g}" y="15" fill="#010101" fill-opacity=".3">{escaped_value}</text>'
        f'<text x="{right_x:g}" y="14">{escaped_value}</text>'
        '</g></svg>'
    )


def badge_etag(svg: str) -> str:
    return hashlib.sha256(svg.encode("utf-8")).hexdigest()
