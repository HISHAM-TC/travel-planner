from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

SUPPORTED_CURRENCIES = {"INR", "USD", "EUR", "GBP", "AED", "AUD"}
DEFAULT_PACE = os.getenv("DEFAULT_PACE", "balanced")
DEFAULT_GROUP_SIZE = int(os.getenv("DEFAULT_GROUP_SIZE", "1"))
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "INR")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "6"))
API_RETRIES = int(os.getenv("API_RETRIES", "2"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

INTEREST_KEYWORDS = {
    "beaches": {"beach", "beaches", "shore", "sunset"},
    "food": {"food", "cuisine", "restaurants", "street food", "dining"},
    "culture": {"culture", "heritage", "museum", "palace", "temple", "history"},
    "adventure": {"hiking", "trek", "adventure", "wildlife", "rafting"},
    "nature": {"nature", "garden", "lake", "national park", "mountains"},
    "nightlife": {"nightlife", "clubs", "bars", "party"},
    "shopping": {"shopping", "market", "mall"},
    "relaxation": {"spa", "relax", "wellness", "quiet"},
    "sightseeing": {"sightseeing", "landmarks", "tourist attractions", "explore"},
}
