import requests
import feedparser
import time
import random
import json
import logging
from newspaper import Article




logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

NEWS_FEEDS = [
    "https://feeds.feedburner.com/TheHackersNews",
    "https://www.bleepingcomputer.com/feed/",
    "https://krebsonsecurity.com/feed/",
    # "https://www.darkreading.com/rss.xml",
    "https://blog.cloudflare.com/rss/",
    "https://googleprojectzero.blogspot.com/feeds/posts/default?alt=rss"
]

NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/114.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/113.0 Safari/537.36"
]


def random_delay():
    time.sleep(random.uniform(1, 3))


def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS)}


def extract_article(url):
    try:
        random_delay()

        article = Article(url)
        article.download()
        article.parse()

        return article.text

    except Exception as e:
        logging.warning(f"Failed to parse article: {url}")
        return ""


def scrape_news(max_items=5):

    news_data = []
    seen_links = set()

    for feed_url in NEWS_FEEDS:

        logging.info(f"Reading RSS: {feed_url}")

        feed = feedparser.parse(feed_url)

        count = 0

        for entry in feed.entries:

            if count >= max_items:
                break

            link = entry.link

            if link in seen_links:
                continue

            seen_links.add(link)

            title = entry.title
            date = entry.get("published", "")
            summary = entry.get("summary", "")

            logging.info(f"Scraping article: {title}")

            content = extract_article(link)
            if not content:
                continue

            news_data.append({
                "id":link,
                "title": title,
                "link": link,
                "date": date,
                "summary": summary,
                "content": content
            })

            count += 1

    return news_data


def scrape_cves(max_items=10):

    logging.info("Fetching latest CVEs")

    params = {
        "resultsPerPage": max_items,
        "sortBy": "published",
        "sortOrder": "desc"
    }

    for attempt in range(3):
        try:
            response = requests.get(NVD_API, headers=get_headers(), params=params, timeout=20)
            response.raise_for_status()
            data = response.json()

            cves = []
            for vuln in data.get("vulnerabilities", []):
                cve = vuln["cve"]
                cve_id = cve["id"]
                
                descriptions = cve.get("descriptions", [])
                description = ""
                for d in descriptions:
                    if d["lang"] == "en":
                        description = d["value"]
                        break

                severity = "Unknown"
                metrics = cve.get("metrics", {})
                if "cvssMetricV31" in metrics:
                    cvss = metrics["cvssMetricV31"][0]["cvssData"]
                    severity = f'{cvss["baseScore"]} ({cvss["baseSeverity"]})'

                cves.append({
                    "cve_id": cve_id,
                    "description": description,
                    "severity": severity,
                    "published_date": cve.get("published", "")
                })

            return cves
            
        except requests.exceptions.HTTPError as http_err:
            logging.warning(f"CVE scraping HTTP error on attempt {attempt + 1}: {http_err}")
            time.sleep(5)
        except Exception as e:
            logging.warning(f"CVE scraping general error on attempt {attempt + 1}: {e}")
            time.sleep(5)
            
    logging.error("All CVE scraping attempts failed after 3 retries.")
    return []


def main():

    logging.info("Starting Cyber News Scraper")

    news = scrape_news()
    cves = scrape_cves()

    output = {
        "news": news,
        "cves": cves
    }

    import os
    from datetime import datetime

    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
    output_dir = os.path.join(DATA_DIR, "output", datetime.today().strftime("%Y-%m-%d"))
    os.makedirs(output_dir, exist_ok=True)

    raw_output_file = os.path.join(output_dir, "scraped_data.json")
    with open(raw_output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    logging.info(f"Raw data saved to {raw_output_file}")
    
    # Run the AI pipeline over the scraped data
    try:
        from pipeline import process_scraped_json
        logging.info("Starting AI Processing Pipeline...")
        processed_file = os.path.join(output_dir, "newsletter_prepared_data.json")
        process_scraped_json(raw_output_file, processed_file)
        logging.info(f"AI Pipeline completed successfully. Output saved to {processed_file}.")
        
        # Trigger email automation
        try:
            import sys
            if PROJECT_ROOT not in sys.path:
                sys.path.insert(0, PROJECT_ROOT)
            
            from automation.send_newsletter import send_newsletters
            logging.info("Dispatching email newsletters...")
            send_newsletters()
            logging.info("Email dispatch process completed.")
        except Exception as e:
            logging.error(f"Failed to launch email automation: {e}")
            
    except ImportError as e:
        logging.error(f"Failed to load AI pipeline modules: {e}")
        logging.error("Ensure 'pipeline.py', 'summarizer.py', and 'categorizer.py' exist and are imported correctly.")
    except Exception as e:
        logging.error(f"Error during AI pipeline processing: {e}")

if __name__ == "__main__":
    main()