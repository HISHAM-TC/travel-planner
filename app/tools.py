"""Compatibility exports for the original app package."""

from tools.budget import calculate_trip_budget as _calculate_budget
from tools.maps import estimate_travel_time
from tools.places import search_places
from tools.weather import get_weather_forecast


def calculate_trip_budget(trip_request):
    """Legacy adapter for callers that pass a TripRequest object."""
    return _calculate_budget(
        trip_request.budget or 0,
        trip_request.days or 0,
        trip_request.currency or "INR",
        budget_split=trip_request.budget_split,
    )


def discover_places(destination, interests, limit=3):
    """Legacy adapter returning only the place list."""
    return search_places(destination or "", interests, limit)["places"]


def gather_tool_context(trip_request):
    """Legacy adapter returning normalized tool data for the planner."""
    weather = (
        get_weather_forecast(trip_request.destination or "", trip_request.start_date, trip_request.days or 0)
        if trip_request.start_date and trip_request.days
        else {"status": "unavailable", "source": "Open-Meteo", "days": [], "warning": "A start date is needed for weather lookup."}
    )
    places = search_places(
        trip_request.destination or "",
        trip_request.interests or [],
        areas=trip_request.areas,
        diet=trip_request.diet,
        food_styles=trip_request.food_styles,
    )
    budget = calculate_trip_budget(trip_request)
    return {"weather": weather, "places": places, "budget_summary": budget}
