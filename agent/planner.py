from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from models.trip import TripRequest


PACE_LIMITS = {"relaxed": 3, "balanced": 4, "packed": 5}


def build_itinerary(trip: TripRequest, tool_data: dict[str, Any]) -> dict[str, Any]:
    """Build day plans only from sourced places and tool results."""
    days = trip.days or 0
    places = interleave_places(tool_data.get("places", {}).get("places", []))
    weather_data = tool_data.get("weather", {})
    weather_days = {item["date"]: item for item in weather_data.get("days", []) if item.get("date")}
    route_times = tool_data.get("travel_estimates", [])
    pace_limit = PACE_LIMITS.get((trip.pace or "balanced").lower(), 4)
    date_values = _trip_dates(trip.start_date, days)
    places_by_day = distribute_places(places, days, pace_limit)
    plans = []

    for day_index in range(days):
        day_date = date_values[day_index]
        weather = weather_days.get(day_date, {})
        day_places = places_by_day[day_index]
        day_stops = []
        time_minutes = 9 * 60
        previous_place = None

        for place in day_places:
            travel_from_previous = None
            if previous_place:
                travel_from_previous = _travel_minutes(previous_place, place, route_times)
                time_minutes += travel_from_previous if travel_from_previous is not None else 30
            duration_minutes = _visit_duration(place)
            details = place.get("details") or {}
            stop = {
                "time": _format_time(time_minutes),
                "end_time": _format_time(time_minutes + duration_minutes),
                "duration_minutes": duration_minutes,
                "name": place["name"],
                "category": place.get("category") or "place",
                "cost_estimate": place.get("cost_estimate"),
                "cost_status": place.get("cost_status", "unknown"),
                "description": place.get("description")
                or f"Place result from {place.get('source', 'an external place source')}. Verify current details before visiting.",
                "details": details,
                "matched_preference": place.get("matched_preference"),
                "area": place.get("area"),
                "dietary_status": place.get("dietary_status"),
                "notes": "Prices and current opening hours are not guaranteed; confirm before visiting.",
                "latitude": place["latitude"],
                "longitude": place["longitude"],
            }
            if previous_place and travel_from_previous is not None:
                stop["travel_from_previous"] = travel_from_previous
            elif previous_place:
                stop["transfer_buffer_minutes"] = 30
            day_stops.append(stop)
            previous_place = place
            time_minutes += duration_minutes

        plans.append(
            {
                "day": day_index + 1,
                "date": day_date,
                "weather": weather.get("summary", "Unavailable"),
                "temperature_range": weather.get("temperature_range"),
                "weather_status": weather_data.get("status", "unavailable"),
                "stops": day_stops,
                "estimated_day_cost": _known_total(day_stops),
                "notes": None if day_stops else "No verified place results were available for this day.",
            }
        )

    known_cost_total = round(sum(item["estimated_day_cost"] for item in plans), 2)
    budget_summary = tool_data["budget"]
    budget_summary["known_cost_total"] = known_cost_total
    budget_summary["remaining_after_known_costs"] = round((trip.budget or 0) - known_cost_total, 2)
    budget_summary["unpriced_items"] = sum(
        stop["cost_estimate"] is None for plan in plans for stop in plan["stops"]
    )

    return {
        "destination": trip.destination or "",
        "start_date": trip.start_date,
        "days": days,
        "currency": trip.currency or "INR",
        "budget": trip.budget or 0,
        "pace": trip.pace or "balanced",
        "interests": trip.interests or [],
        "planning_preferences": {
            "areas": trip.areas or [],
            "origin": trip.origin,
            "arrival_mode": trip.arrival_mode,
            "end_date": trip.end_date,
            "flexible_dates": trip.flexible_dates,
            "travelers": trip.travelers,
            "group_type": trip.group_type,
            "budget_mode": trip.budget_mode,
            "stay_type": trip.stay_type,
            "local_transport": trip.local_transport or [],
            "diet": trip.diet,
            "food_styles": trip.food_styles or [],
        },
        "budget_summary": budget_summary,
        "data_warnings": _data_warnings(tool_data),
        "unmatched_preferences": tool_data.get("places", {}).get("unmatched_preferences", []),
        "days_plan": plans,
        "total_estimated_cost": known_cost_total,
        "remaining_budget": round((trip.budget or 0) - known_cost_total, 2),
    }


def _trip_dates(start_date: str | None, days: int) -> list[str | None]:
    if not start_date:
        return [None] * days
    first = date.fromisoformat(start_date)
    return [(first + timedelta(days=index)).isoformat() for index in range(days)]


def _travel_minutes(origin: dict, destination: dict, estimates: list[dict]) -> int | None:
    for estimate in estimates:
        if estimate.get("origin") == origin.get("name") and estimate.get("destination") == destination.get("name"):
            return int(estimate["estimated_minutes"])
    return None


def interleave_places(places: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for place in places:
        preference = str(place.get("matched_preference") or "other")
        buckets.setdefault(preference, []).append(place)

    ordered = []
    while buckets:
        for preference in list(buckets):
            ordered.append(buckets[preference].pop(0))
            if not buckets[preference]:
                del buckets[preference]
    return ordered


def distribute_places(places: list[dict], days: int, pace_limit: int) -> list[list[dict]]:
    if days <= 0:
        return []
    selected = places[: days * pace_limit]
    daily = []
    offset = 0
    base_count, extra_days = divmod(len(selected), days)
    for day_index in range(days):
        count = base_count + (1 if day_index < extra_days else 0)
        daily.append(selected[offset : offset + count])
        offset += count
    return daily


def _visit_duration(place: dict) -> int:
    category = str(place.get("category") or "").casefold()
    if category in {"beach", "park", "nature reserve", "water park"}:
        return 120
    if category in {"restaurant", "cafe", "fast food", "food court"}:
        return 60
    return 90


def _format_time(minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    return f"{hour % 24:02d}:{minute:02d}"


def _known_total(stops: list[dict]) -> float:
    return round(sum(stop["cost_estimate"] for stop in stops if isinstance(stop.get("cost_estimate"), (int, float))), 2)


def _data_warnings(tool_data: dict[str, Any]) -> list[str]:
    warnings = []
    for key in ("weather", "places"):
        result = tool_data.get(key, {})
        if result.get("status") != "ok":
            warnings.append(result.get("warning") or f"{key.title()} data is unavailable.")
        if key == "places" and result.get("unmatched_preferences"):
            warnings.append(
                "No mapped places matched: " + ", ".join(result["unmatched_preferences"]) + "."
            )
    if any(place.get("cost_estimate") is None for place in tool_data.get("places", {}).get("places", [])):
        warnings.append("Prices were not supplied by the place source; unpriced items are not treated as free.")
    if tool_data.get("travel_estimates"):
        warnings.append("Between-stop travel times are straight-line approximations, not routed road or transit times.")
    return warnings
