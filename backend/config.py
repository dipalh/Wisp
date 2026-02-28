import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Path to Google Cloud service account JSON key.
# Used by google-cloud-vision (and any other Cloud SDK client) automatically.
GOOGLE_CLOUD_VISION_API_KEY = os.getenv("GOOGLE_CLOUD_VISION_API_KEY")


def get_gemini_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY")


def get_google_cloud_vision_api_key() -> str | None:
    return os.getenv("GOOGLE_CLOUD_VISION_API_KEY")
