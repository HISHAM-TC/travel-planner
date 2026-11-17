from __future__ import annotations

import re
from datetime import datetime

from app.config import (
    DEFAULT_CURRENCY,
    DEFAULT_GROUP_SIZE,
    DEFAULT_PACE,
    INTEREST_KEYWORDS,
    SUPPORTED_CURRENCIES,
)
from app.models import TripRequest


def parse_trip_request(request_text: str, preferences: dict | None = None) -> TripRequest:
    """Extract trip fields from a natural-language request and optional defaults."""
    clean_text = (request_text or "").strip()
    preferences = preferences or {}
    if not clean_text:
        return TripRequest(
            request=clean_text or None,
            currency=preferences.get("currency", DEFAULT_CURRENCY),
            interests=preferences.get("interests", []),
            group_size=preferences.get("group_size", DEFAULT_GROUP_SIZE),
            pace=preferences.get("pace", DEFAULT_PACE),
        )

    destination = _extract_destination(clean_text)
    start_date = _extract_start_date(clean_text)
    days = _extract_days(clean_text)
    budget, currency = _extract_budget(clean_text)
    interests = _extract_interests(clean_text)
    group_size = _extract_group_size(clean_text)
    pace = _extract_pace(clean_text)

    return TripRequest(
        request=clean_text,
        destination=destination,
        start_date=start_date,
        days=days,
        budget=budget,
        currency=currency or preferences.get("currency") or DEFAULT_CURRENCY,
        interests=interests or preferences.get("interests", []),
        group_size=group_size or preferences.get("group_size", DEFAULT_GROUP_SIZE),
        pace=pace or preferences.get("pace", DEFAULT_PACE),
        notes=clean_text,
    )


def _extract_destination(text: str) -> str | None:
    pattern = r"\b(?:to|in|visit)\s+([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2})"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        words = match.group(1).split()
        stop_words = {"a", "an", "the", "on", "with", "for", "and", "from", "starting", "budget"}
        while words and words[-1].lower() in stop_words:
            words.pop()
        if words and words[0].lower() not in {"a", "an", "the"}:
            return " ".join(words)
    return None


def _extract_start_date(text: str) -> str | None:
    patterns = [
        r"(?:start(?:ing)?\s+(?:on|date)\s+|on\s+)(\d{4}-\d{2}-\d{2})",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1)
            try:
                datetime.strptime(value, "%Y-%m-%d")
                return value
            except ValueError:
                continue
    return None


def _extract_days(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:-|\s+)?(?:day|days|night|nights)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _extract_budget(text: str) -> tuple[float | None, str | None]:
    currency_pattern = r"INR|USD|EUR|GBP|AED|AUD"
    number_pattern = r"\d+(?:,\d{3})*(?:\.\d+)?"
    currency_match = re.search(rf"\b({currency_pattern})\b", text, re.IGNORECASE)
    currency = currency_match.group(1).upper() if currency_match else None

    patterns = [
        rf"(?:budget|cost|spend)(?:\s+(?:of|is|to|up\s+to))?\s*:?\s*(?:{currency_pattern}\s*)?({number_pattern})",
        rf"\b(?:{currency_pattern})\s+({number_pattern})",
        rf"\b({number_pattern})\s*(?:{currency_pattern})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1).replace(",", ""))
            return value, currency or DEFAULT_CURRENCY
    return None, currency or DEFAULT_CURRENCY


def _extract_interests(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for interest_name, keywords in INTEREST_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            found.append(interest_name)
    return found


def _extract_group_size(text: str) -> int | None:
    match = re.search(r"for\s+(\d+)\s*(?:people|persons|travellers|travelers)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _extract_pace(text: str) -> str | None:
    lowered = text.lower()
    if "relaxed" in lowered:
        return "relaxed"
    if "packed" in lowered:
        return "packed"
    if "balanced" in lowered:
        return "balanced"
    return None
