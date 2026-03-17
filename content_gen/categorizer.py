import os
from groq import Groq
from dotenv import load_dotenv
from utils import rate_limit_and_retry

# Load environment variables from the root directory's .env
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path)

@rate_limit_and_retry(max_retries=3, base_delay=2.0)
def categorize_article(title: str, summary: str) -> str:
    """
    Categorizes a cybersecurity article based on its title and summary.
    Always returns exactly one of the predefined category names.
    """
    categories = [
        "CVE",
        "Malware",
        "Ransomware",
        "Data Breach",
        "Zero-Day",
        "Security Tools",
        "General Security"
    ]
    
    client = Groq()
    prompt = f"""
    Categorize the following cybersecurity article based on its title and summary.
    You must choose EXACTLY ONE category from the list below:
    {', '.join(categories)}
    
    Article Title: {title}
    Article Summary: {summary}
    
    Return ONLY the category name. Do not output anything else.
    """
    
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a strict categorization system. Output exactly one category name."},
            {"role": "user", "content": prompt}
        ],
        model="llama-3.3-70b-versatile",
        temperature=0.1,
        max_tokens=15
    )
    raw_category = response.choices[0].message.content.strip()
    
    for valid_category in categories:
        if valid_category.lower() in raw_category.lower():
            return valid_category
            
    return "General Security"

