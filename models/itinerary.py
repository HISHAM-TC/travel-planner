from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class ItineraryStop(TypedDict):
    time: str
    name: str
    category: str
    cost_estimate: float | None
    cost_status: str
    notes: str
    latitude: NotRequired[float]
    longitude: NotRequired[float]


class DayPlan(TypedDict):
    day: int
    date: str | None
    weather: str
    temperature_range: str | None
    stops: list[ItineraryStop]
    estimated_day_cost: float


class Itinerary(TypedDict):
    destination: str
    start_date: str | None
    days: int
    currency: str
    budget: float
    pace: str
    interests: list[str]
    planning_preferences: NotRequired[dict[str, Any]]
    budget_summary: dict
    days_plan: list[DayPlan]
    total_estimated_cost: float
    remaining_budget: float
