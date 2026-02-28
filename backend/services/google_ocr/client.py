import google.generativeai as genai
from config import GEMINI_API_KEY

# Configure once at import time
genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.0-flash"


def get_model() -> genai.GenerativeModel:
    return genai.GenerativeModel(MODEL_NAME)
