from __future__ import annotations

from datetime import date, datetime

from app.config import SUPPORTED_CURRENCIES
from app.models import TripRequest


def validate_trip_request(trip_request: TripRequest) -> dict:
    """Return missing fields, validation errors, and a user-facing follow-up question."""
    missing_fields: list[str] = []
    errors: list[str] = []

    if not trip_request.destination:
        missing_fields.append("destination")
    if trip_request.days is None:
        missing_fields.append("days")
    elif trip_request.days <= 0:
        errors.append("days must be greater than zero")
    if trip_request.budget is None:
        missing_fields.append("budget")
    elif trip_request.budget <= 0:
        errors.append("budget must be greater than zero")
    if trip_request.currency and trip_request.currency.upper() not in SUPPORTED_CURRENCIES:
        errors.append(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}")
    if trip_request.group_size is not None and trip_request.group_size <= 0:
        errors.append("group_size must be greater than zero")
    if trip_request.pace and trip_request.pace.lower() not in {"relaxed", "balanced", "packed"}:
        errors.append("pace must be relaxed, balanced, or packed")

    if trip_request.start_date:
        try:
            parsed = datetime.strptime(trip_request.start_date, "%Y-%m-%d").date()
            if parsed < date.today():
                errors.append("start_date cannot be in the past")
        except ValueError:
            errors.append("start_date must use YYYY-MM-DD format")

    valid = not missing_fields and not errors
    follow_up_question = None
    if missing_fields:
        questions = {
            "destination": "Where would you like to travel?",
            "days": "How many days will the trip last?",
            "budget": "What is your total trip budget and currency?",
        }
        follow_up_question = " ".join(questions[field] for field in missing_fields)
    elif errors:
        follow_up_question = "Please correct these trip details: " + "; ".join(errors)

    return {
        "valid": valid,
        "missing_fields": missing_fields,
        "errors": errors,
        "requires_follow_up": bool(missing_fields or errors),
        "follow_up_question": follow_up_question,
        "message": (
            "All required travel fields are present and valid."
            if valid
            else "Missing or invalid travel details require follow-up before planning."
        ),
    }
