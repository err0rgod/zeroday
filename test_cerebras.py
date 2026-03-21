import os
from openai import OpenAI

# We will need the user to provide a CEREBRAS_API_KEY in the environment or .env
api_key = os.getenv("CEREBRAS_API_KEY", "dummy")
client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)

try:
    print(client.models.list())
except Exception as e:
    print("Error:", e)
