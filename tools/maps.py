from __future__ import annotations

import math
from typing import Any


def estimate_travel_time(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict[str, Any]:
    """Estimate travel from coordinates using straight-line distance, clearly labeled."""
    lat1, lon1 = origin
    lat2, lon2 = destination
    if not all(math.isfinite(value) for value in (lat1, lon1, lat2, lon2)):
        raise ValueError("Coordinates must be finite numbers.")
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError("Coordinates are outside valid latitude/longitude ranges.")

    radius_km = 6371.0
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(delta_lon / 2) ** 2
    )
    distance_km = 2 * radius_km * math.asin(math.sqrt(haversine))
    return {
        "status": "estimated",
        "distance_km": round(distance_km, 1),
        "estimated_minutes": round(distance_km / 25 * 60),
        "method": "straight_line_distance_at_25_km_per_hour",
        "warning": "Approximation only; not a routed road or transit estimate.",
    }
