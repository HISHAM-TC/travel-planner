from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from tools.base import request_json

logger = logging.getLogger(__name__)


def search_places(
    destination: str,
    interests: list[str] | None = None,
    limit: int = 8,
    areas: list[str] | None = None,
    diet: str | None = None,
    food_styles: list[str] | None = None,
) -> dict[str, Any]:
    """Search OpenStreetMap results; never create replacement place names."""
    if not destination.strip() or limit <= 0:
        return {"status": "unavailable", "source": "OpenStreetMap Nominatim", "places": [], "warning": "A destination and positive result limit are required."}

    places = []
    warnings = []
    dietary_terms = {
        "vegetarian": ["vegetarian restaurant"],
        "vegan": ["vegan restaurant"],
        "pescatarian": ["seafood restaurant"],
    }
    search_terms = dietary_terms.get((diet or "").lower(), [])
    search_areas = areas or [""]
    per_area_limit = max(1, min(20, (limit + len(search_areas) - 1) // len(search_areas)))
    seen = set()

    for area in search_areas:
        query = " ".join(part for part in (area, destination, *search_terms) if part)
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": query, "format": "jsonv2", "limit": per_area_limit, "addressdetails": 1}
        )
        results, error = request_json(url, user_agent="TravelPlannerAgent/1.0 (trip-planning prototype)")
        if not isinstance(results, list):
            warnings.append(error or "The place search provider returned an invalid response.")
            continue

        for result in results:
            name = result.get("display_name")
            try:
                latitude = float(result["lat"])
                longitude = float(result["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            place_key = (name, latitude, longitude)
            if place_key in seen:
                continue
            seen.add(place_key)
            places.append(
                {
                    "name": name,
                    "category": result.get("type") or "place",
                    "latitude": latitude,
                    "longitude": longitude,
                    "source": "OpenStreetMap Nominatim",
                    "cost_estimate": None,
                    "cost_status": "unknown",
                }
            )
            if len(places) >= limit:
                break
        if len(places) >= limit:
            break

    status = "ok" if places else "unavailable"
    warning = None if places else (warnings[0] if warnings else "No matching places were returned by OpenStreetMap Nominatim.")
    logger.info("Tool call place_search: %s verified results for %s", len(places), destination)
    return {"status": status, "source": "OpenStreetMap Nominatim", "places": places, "warning": warning}
