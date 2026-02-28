from google import genai
from config import get_gemini_api_key

MODEL_NAME = "gemini-2.5-flash"
EMBED_MODEL = "models/gemini-embedding-001"


def get_client() -> genai.Client:
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in your .env file")
    return genai.Client(api_key=api_key)
