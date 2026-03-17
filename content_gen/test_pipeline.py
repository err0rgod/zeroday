import json
import os
import sys
from pipeline import process_scraped_json

def test_production_pipeline():
    """Test the upgraded production pipeline against real scraped data."""
    print("--- Running Pipeline with Real Scraped Data ---")
    
    from datetime import datetime
    import os
    
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
    output_dir = os.path.join(DATA_DIR, "output", datetime.today().strftime("%Y-%m-%d"))
    os.makedirs(output_dir, exist_ok=True)
    
    # Check if real scraped data exists from v2.py
    real_scraper_file = os.path.join(output_dir, "scraped_data.json")
    if not os.path.exists(real_scraper_file):
        print(f"Error: Could not find '{real_scraper_file}'.")
        print("Please run 'python v2.py' first to generate real scraped data!")
        sys.exit(1)
        
    print(f"Loading real data from {real_scraper_file}...")
    
    # Process it via new pipeline logic into output dir
    test_json_out = os.path.join(output_dir, "test_newsletter.json")
    newsletter_json = process_scraped_json(real_scraper_file, test_json_out)
    
    if not newsletter_json:
        print("Pipeline failed or returned empty data.")
        sys.exit(1)
        
    print("\n--- FINAL JSON OUTPUT GENERATED SUCCESSFULLY ---")
    print("Top stories found:", len(newsletter_json.get("top_stories", [])))
    print("CVEs found:", len(newsletter_json.get("cves", [])))
    
    # Text generation should also implicitly run and be stored in output/test_newsletter.txt
    test_txt_out = test_json_out.replace(".json", ".txt")
    print(f"\n--- READING GENERATED TEXT NEWSLETTER ({test_txt_out}) PREVIEW ---")
    if os.path.exists(test_txt_out):
        with open(test_txt_out, "r", encoding="utf-8") as f:
            content = f.read()
            # Print just the first 1000 chars as a rough preview
            print(content[:1000] + "\n\n... (preview truncated) ...")

if __name__ == "__main__":
    test_production_pipeline()

