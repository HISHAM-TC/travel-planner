from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class TripRequest:
    request: str | None = None
    destination: str | None = None
    areas: list[str] | None = None
    origin: str | None = None
    arrival_mode: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    days: int | None = None
    flexible_dates: bool | None = None
    budget: float | None = None
    currency: str | None = None
    budget_mode: str | None = None
    budget_split: dict[str, float] | None = None
    interests: list[str] | None = None
    group_size: int | None = None
    travelers: dict[str, int] | None = None
    group_type: str | None = None
    pace: str | None = None
    stay_type: str | None = None
    local_transport: list[str] | None = None
    diet: str | None = None
    food_styles: list[str] | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return this request as a JSON-compatible dictionary."""
        return asdict(self)


def trip_request_from_dict(data: dict[str, Any]) -> TripRequest:
    """Build a trip request from persisted JSON fields."""
    allowed = TripRequest.__dataclass_fields__.keys()
    return TripRequest(**{key: value for key, value in data.items() if key in allowed})
