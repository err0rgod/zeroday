import json
import os
import logging
from summarizer import summarize_article, generate_two_level_summary
from categorizer import categorize_article
from utils import is_duplicate_title, rank_article

# Setup pipeline logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def generate_newsletter(json_data: dict, output_file: str = None):
    """
    Generates a human-readable text newsletter from the structured JSON data.
    """
    if not output_file:
        from datetime import datetime
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
        output_file = os.path.join(DATA_DIR, "output", datetime.today().strftime("%Y-%m-%d"), "newsletter.txt")
        
    # Ensure output directory exists before writing
    out_dir = os.path.dirname(output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("Cybersecurity Weekly Brief\n")
        f.write("=" * 50 + "\n\n")
        
        f.write("Top 5 Security Stories\n")
        f.write("-" * 50 + "\n\n")
        
        # Write top stories
        for i, story in enumerate(json_data.get("top_stories", []), 1):
            f.write(f"{i}. {story['title']}\n\n")
            f.write(f"{story['short_summary']}\n\n")
            f.write(f"{story['deep_summary']}\n")
            f.write("\n" + "-" * 30 + "\n\n")
            
        # Optional: Add CVE section
        cves = json_data.get("cves", [])
        if cves:
            f.write("Important Vulnerabilities (CVEs)\n")
            f.write("-" * 50 + "\n\n")
            for cve in cves:
                f.write(f"- {cve['title']}: {cve['summary']}\n")
                if cve.get('cve_ids'):
                    ids_str = ', '.join(cve['cve_ids'])
                    f.write(f"  Vulnerabilities: {ids_str}\n")

    logger.info(f"Generated human readable newsletter text at {output_file}")


def process_scraped_json(file_path: str, output_path: str = None):
    """
    Reads JSON from v2.py, applies filtering, deduplication, ranking, and AI summarization rules.
    Outputs the final segregated structure into output/newsletter.json.
    """
    if not os.path.exists(file_path):
        logger.error(f"File {file_path} not found.")
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if not output_path:
        from datetime import datetime
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
        output_path = os.path.join(DATA_DIR, "output", datetime.today().strftime("%Y-%m-%d"), "newsletter.json")
        
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    
    seen_urls = set()
    seen_titles = []
    
    processed_news = []
    processed_cves = []
    
    # --- PROCESS NEWS ---
    logger.info("Processing News Articles...")
    for item in data.get("news", []):
        if len(processed_news) >= 15:
            logger.info("Reached maximum of 15 processed articles. Skipping the rest.")
            break
            
        title = item.get("title", "")
        content = item.get("content", "")
        url = item.get("link", "")
        
        # Filter 1: Length check
        if len(content) < 200:
            logger.info(f"Skipping '{title[:30]}...': content too short ({len(content)} chars)")
            continue
            
        # Filter 2: Exact URL Duplicate (just in case scraper misses it)
        if url and url in seen_urls:
            logger.info(f"Skipping '{title[:30]}...': duplicate URL")
            continue
            
        # Filter 3: AI Deduplication (Fuzzy title match)
        is_dup = False
        for seen_t in seen_titles:
            if is_duplicate_title(title, seen_t, threshold=0.8):
                logger.info(f"Skipping '{title[:30]}...': fuzzy duplicate of '{seen_t[:30]}...'")
                is_dup = True
                break
        if is_dup:
            continue
            
        # Item passed filters!
        seen_urls.add(url)
        seen_titles.append(title)
        
        # Compute keyword ranking
        score = rank_article(content)
        
        logger.info(f"Processing article: {title}")
        logger.info(f" -> Compressed length: ~{min(len(content), 2000)} (raw: {len(content)})")
        logger.info(f" -> Ranking score: {score}")
        
        try:
            category = categorize_article(title, content[:1500]) # Quick category from snippet
            logger.info(f" -> Category detected: {category}")
            
            # Segregation rule: If CVE category, process differently later, or store separately
            if category == "CVE":
                logger.info(" -> Routing to CVE list instead of main stories.")
                summary = summarize_article(title, content)

                # Extract real CVE IDs (e.g. CVE-2026-21262) from content
                import re as _re
                extracted_ids = list(dict.fromkeys(
                    _re.findall(r'CVE-\d{4}-\d{4,7}', content, _re.IGNORECASE)
                ))
                logger.info(f" -> Extracted CVE IDs: {extracted_ids}")

                processed_cves.append({
                    "title": title,
                    "summary": summary,
                    "cve_ids": [c.upper() for c in extracted_ids],  # list of real IDs
                    "score": score
                })
                continue
                
            # If standard news, generate two-level summary
            summaries = generate_two_level_summary(title, content)
            
            processed_news.append({
                "title": title,
                "category": category,
                "short_summary": summaries["short_summary"],
                "deep_summary": summaries["deep_summary"],
                "score": score,
                "source": "RSS Scraping",
                "url": url
            })
            logger.info(" -> Successfully processed and added to candidate stories.")
            
        except Exception as e:
            logger.error(f"Error AI processing article '{title}': {e}")


    # --- PROCESS CVES ---
    # Scraper explicit CVEs
    logger.info("Processing Explicit API CVEs...")
    for cve in data.get("cves", []):
        cve_id = cve.get("cve_id", "")
        desc = cve.get("description", "")
        if cve_id and desc:
            logger.info(f"Processing CVE: {cve_id}")
            title = f"Vulnerability {cve_id}"
            try:
                summary = summarize_article(title, desc)
                processed_cves.append({
                    "title": title,
                    "summary": summary,
                    "cve_ids": [cve_id]
                })
            except Exception as e:
                logger.error(f"Error processing CVE {cve_id}: {e}")

    # --- RANK & SELECT TOP STORIES ---
    # Sort news descending by score
    processed_news.sort(key=lambda x: x["score"], reverse=True)
    top_5_stories = processed_news[:5]
    
    logger.info(f"Selected {len(top_5_stories)} Top stories for the final newsletter.")

    # --- BUILD FINAL JSON ---
    from datetime import datetime
    final_output = {
        "date": datetime.today().strftime("%Y-%m-%d"),
        "top_stories": top_5_stories,
        "cves": processed_cves
    }

    # Save to disk
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(final_output, out, indent=4)
        
    logger.info(f"Structured JSON saved to {output_path}")
    
    # Also generate text version
    text_out_path = output_path.replace(".json", ".txt")
    generate_newsletter(final_output, text_out_path)

    return final_output
