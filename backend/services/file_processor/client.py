from google import genai
from config import GEMINI_API_KEY

MODEL_NAME = "gemini-2.5-flash"


def get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)
