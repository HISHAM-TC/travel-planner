from __future__ import annotations

import re
from typing import Any

from agent.loop import plan_trip
from agent.verifier import finalize_itinerary
from app.models import TripRequest, trip_request_from_dict
from app.storage import (
    load_preferences,
    load_trip,
    load_trips,
    save_preferences,
    save_trip,
    update_trip,
)


def build_chat_session(
    request_text: str,
    structured_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan a request, reuse preferences, and persist only a completed plan."""
    preferences = load_preferences()
    result = plan_trip(request_text, preferences, structured_request)
    parsed = result["parsed_request"]
    trip = trip_request_from_dict(parsed)
    saved_trip = None

    if result["status"] == "finalized":
        updated_preferences = _preferences_after_trip(preferences, trip)
        save_preferences(updated_preferences)
        saved_trip = save_trip(
            {
                "request": request_text,
                **trip.to_dict(),
                "itinerary": result,
            }
        )
        preferences = updated_preferences

    return {
        "request": request_text,
        "parsed_request": parsed,
        "preferences": preferences,
        "saved_trip": saved_trip,
        "itinerary_output": result,
    }


def load_saved_trip_session(trip_id: str) -> dict[str, Any]:
    """Reload a previously saved trip for display or follow-up editing."""
    saved = load_trip(trip_id)
    result = saved.get("itinerary")
    if not isinstance(result, dict):
        raise ValueError(f"Saved trip {trip_id} has no valid itinerary.")
    parsed_request = trip_request_from_dict(
        {
            **saved,
            "notes": saved.get("notes", saved.get("request", "")),
        }
    ).to_dict()
    return {
        "request": saved.get("request", ""),
        "parsed_request": parsed_request,
        "preferences": load_preferences(),
        "saved_trip": saved,
        "itinerary_output": result,
    }


def list_saved_trips() -> list[dict[str, Any]]:
    return load_trips()


def apply_follow_up_edit(session_data: dict[str, Any], follow_up_text: str) -> dict[str, Any]:
    """Apply supported edits to the existing plan instead of regenerating it."""
    text = follow_up_text.strip()
    if not text:
        raise ValueError("Enter an edit request.")

    updated = dict(session_data)
    trip = trip_request_from_dict(session_data["parsed_request"])
    result = session_data["itinerary_output"]
    itinerary = _copy_itinerary(result.get("itinerary"))
    if not itinerary:
        raise ValueError("There is no completed itinerary to edit.")

    budget_trip = _request_with_updates(trip, text)
    day_number = _target_day(text)
    replacement = re.search(r"\breplace\s+(.+?)\s+with\s+(.+?)(?:\s+on\s+day\s+\d+)?$", text, re.IGNORECASE)
    removal = re.search(r"\bremove\s+(.+?)(?:\s+from\s+day\s+\d+)?$", text, re.IGNORECASE)

    if replacement:
        old_name, new_name = replacement.group(1).strip(), replacement.group(2).strip()
        stop = _find_stop(itinerary, old_name, day_number)
        if stop is None:
            raise ValueError(f"Could not find '{old_name}' in the requested itinerary.")
        stop.update(
            {
                "name": new_name,
                "category": "user-requested",
                "cost_estimate": None,
                "cost_status": "unknown",
                "notes": "Replacement name supplied by the user; place details and price are unverified.",
            }
        )
    elif removal:
        target = removal.group(1).strip()
        if not _remove_stop(itinerary, target, day_number):
            raise ValueError(f"Could not find '{target}' in the requested itinerary.")
    elif "relax" in text.lower() or budget_trip.pace != trip.pace or budget_trip.budget != trip.budget:
        if day_number and ("relax" in text.lower() or budget_trip.pace != trip.pace):
            day = _find_day(itinerary, day_number)
            if day is None:
                raise ValueError(f"Day {day_number} does not exist in this itinerary.")
            day["stops"] = day["stops"][:2]
        elif budget_trip.pace != trip.pace:
            maximum = {"relaxed": 3, "balanced": 4, "packed": 5}.get(budget_trip.pace or "balanced", 4)
            for day in itinerary["days_plan"]:
                day["stops"] = day["stops"][:maximum]
    else:
        raise ValueError("Supported edits: change the budget or pace, relax a day, remove a stop, or replace a named stop.")

    trip = budget_trip
    _recalculate_totals(itinerary, trip)
    finalized = finalize_itinerary(trip, itinerary)
    updated_result = {
        **result,
        "status": finalized["status"],
        "parsed_request": trip.to_dict(),
        "itinerary": finalized["itinerary"],
        "verification": finalized["verification"],
        "revisions": finalized["revisions"],
    }
    updated["follow_up"] = text
    updated["parsed_request"] = trip.to_dict()
    updated["itinerary_output"] = updated_result
    saved = session_data.get("saved_trip")
    if saved and saved.get("id"):
        updated["saved_trip"] = update_trip(
            str(saved["id"]),
            {
                "budget": trip.budget,
                "currency": trip.currency,
                "pace": trip.pace,
                "itinerary": updated_result,
            },
        )
    return updated


def render_console_response(session_data: dict[str, Any]) -> str:
    result = session_data.get("itinerary_output", {})
    itinerary = result.get("itinerary") or {}
    if result.get("status") == "needs_follow_up":
        return result.get("validation", {}).get("follow_up_question") or "Please provide the missing trip details."
    return (
        f"Trip plan for {itinerary.get('destination', 'Unknown')}: "
        f"{itinerary.get('days', 0)} days. "
        f"Estimated priced items: {itinerary.get('total_estimated_cost', 0)} "
        f"{itinerary.get('currency', '')}. "
        f"Status: {result.get('status', 'unknown')}."
    )


def _preferences_after_trip(preferences: dict, trip: TripRequest) -> dict:
    updated = dict(preferences)
    if trip.interests:
        updated["interests"] = trip.interests
    if trip.pace:
        updated["pace"] = trip.pace
    if trip.currency:
        updated["currency"] = trip.currency
    if trip.budget:
        updated["preferred_budget"] = trip.budget
    if trip.group_size:
        updated["group_size"] = trip.group_size
    return updated


def _request_with_updates(trip: TripRequest, text: str) -> TripRequest:
    from app.parser import parse_trip_request

    parsed = parse_trip_request(text)
    values = trip.to_dict()
    explicit_currency = re.search(r"\b(?:INR|USD|EUR|GBP|AED|AUD)\b", text, re.IGNORECASE)
    target_day = _target_day(text)
    fields = ("budget", "interests", "destination", "days", "start_date", "group_size")
    for field in fields:
        value = getattr(parsed, field)
        if value is not None and (field not in {"interests"} or value):
            values[field] = value
    if explicit_currency:
        values["currency"] = parsed.currency
    if not (target_day and ("relax" in text.lower() or "pace" in text.lower())):
        explicit_pace = re.search(r"\b(relaxed|balanced|packed)\b", text, re.IGNORECASE)
        if explicit_pace:
            values["pace"] = parsed.pace
    return trip_request_from_dict(values)


def _copy_itinerary(itinerary: Any) -> dict[str, Any] | None:
    if not isinstance(itinerary, dict):
        return None
    import copy

    return copy.deepcopy(itinerary)


def _target_day(text: str) -> int | None:
    match = re.search(r"\bday\s+(\d+)\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _find_day(itinerary: dict, day_number: int) -> dict | None:
    return next((day for day in itinerary.get("days_plan", []) if day.get("day") == day_number), None)


def _find_stop(itinerary: dict, name: str, day_number: int | None) -> dict | None:
    days = [_find_day(itinerary, day_number)] if day_number else itinerary.get("days_plan", [])
    for day in days:
        if day:
            for stop in day.get("stops", []):
                if name.lower() in stop.get("name", "").lower():
                    return stop
    return None


def _remove_stop(itinerary: dict, name: str, day_number: int | None) -> bool:
    days = [_find_day(itinerary, day_number)] if day_number else itinerary.get("days_plan", [])
    removed = False
    for day in days:
        if day:
            original = day.get("stops", [])
            remaining = [stop for stop in original if name.lower() not in stop.get("name", "").lower()]
            removed = removed or len(remaining) != len(original)
            day["stops"] = remaining
    return removed


def _recalculate_totals(itinerary: dict, trip: TripRequest) -> None:
    for day in itinerary.get("days_plan", []):
        day["estimated_day_cost"] = round(
            sum(stop["cost_estimate"] for stop in day.get("stops", []) if isinstance(stop.get("cost_estimate"), (int, float))),
            2,
        )
    known = round(sum(day["estimated_day_cost"] for day in itinerary.get("days_plan", [])), 2)
    itinerary["budget"] = trip.budget
    itinerary["currency"] = trip.currency
    itinerary["pace"] = trip.pace
    itinerary["total_estimated_cost"] = known
    itinerary["remaining_budget"] = round((trip.budget or 0) - known, 2)
    budget_summary = itinerary.get("budget_summary", {})
    budget_summary["budget_total"] = trip.budget
    budget_summary["known_cost_total"] = known
    budget_summary["remaining_after_known_costs"] = round((trip.budget or 0) - known, 2)
