from __future__ import annotations

import math
from typing import Any


def estimate_travel_time(
    origin: tuple[float, float],
    destination: tuple[float, float],
    transport_modes: list[str] | None = None,
) -> dict[str, Any]:
    """Estimate transfer time using distance and the selected mode's assumed speed."""
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
    selected_modes = {mode.casefold() for mode in (transport_modes or [])}
    if "mostly on foot" in selected_modes:
        speed_km_per_hour = 4
        mode_assumption = "walking"
    elif "public bus" in selected_modes:
        speed_km_per_hour = 20
        mode_assumption = "public_bus"
    elif "rented scooter" in selected_modes:
        speed_km_per_hour = 25
        mode_assumption = "scooter"
    elif selected_modes.intersection({"taxi / cab", "own car"}):
        speed_km_per_hour = 30
        mode_assumption = "car"
    else:
        speed_km_per_hour = 25
        mode_assumption = "default"
    return {
        "status": "estimated",
        "distance_km": round(distance_km, 1),
        "estimated_minutes": round(distance_km / speed_km_per_hour * 60),
        "mode_assumption": mode_assumption,
        "method": f"straight_line_distance_at_{speed_km_per_hour}_km_per_hour",
        "warning": "Approximation only; not a routed road or transit estimate.",
    }
