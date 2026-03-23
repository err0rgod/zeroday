import os
from openai import OpenAI
from dotenv import load_dotenv
from utils import rate_limit_and_retry

# Load environment variables from the root directory's .env
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path, override=True)

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
    
    api_key = os.getenv("CEREBRAS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("CEREBRAS_API_KEY is not set in the environment or .env file.")
        
    client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)
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
        model="llama3.1-8b",
        temperature=0.1,
        max_tokens=15
    )
    raw_category = response.choices[0].message.content.strip()
    
    for valid_category in categories:
        if valid_category.lower() in raw_category.lower():
            return valid_category
            
    return "General Security"

