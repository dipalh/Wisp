from google import genai
from config import GEMINI_API_KEY

MODEL_NAME = "gemini-2.5-flash"
EMBED_MODEL = "models/text-embedding-004"


def get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)
