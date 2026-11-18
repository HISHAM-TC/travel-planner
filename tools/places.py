from __future__ import annotations

import logging
import math
import re
import threading
import time
import urllib.parse
from typing import Any

from tools.base import request_json

logger = logging.getLogger(__name__)
_NOMINATIM_LOCK = threading.Lock()
_LAST_NOMINATIM_REQUEST = 0.0
_NOMINATIM_MIN_INTERVAL = 1.0
_MAX_SEARCHES = 12

_FOOD_TYPES = {
    ("amenity", "bar"),
    ("amenity", "cafe"),
    ("amenity", "fast_food"),
    ("amenity", "food_court"),
    ("amenity", "pub"),
    ("amenity", "restaurant"),
    ("tourism", "restaurant"),
}
_INTEREST_SEARCHES = {
    "beaches": [("beach", {("natural", "beach"), ("leisure", "beach")})],
    "culture": [
        ("museum", {("tourism", "museum"), ("amenity", "museum")}),
        ("historic site", {("historic", "monument"), ("historic", "archaeological_site")}),
    ],
    "adventure": [
        ("water sports", {("sport", "surfing"), ("leisure", "water_park")}),
        ("viewpoint", {("tourism", "viewpoint")}),
    ],
    "nature": [
        ("park", {("leisure", "park"), ("leisure", "nature_reserve")}),
        ("viewpoint", {("tourism", "viewpoint")}),
    ],
    "nightlife": [
        ("nightclub", {("amenity", "nightclub")}),
        ("bar", {("amenity", "bar"), ("amenity", "pub")}),
    ],
    "shopping": [
        ("market", {("shop", "mall"), ("shop", "department_store"), ("amenity", "marketplace")}),
    ],
    "wellness": [("spa", {("leisure", "spa"), ("amenity", "spa")})],
    "sightseeing": [
        ("tourist attraction", {("tourism", "attraction"), ("tourism", "viewpoint")}),
    ],
    "photography": [("viewpoint", {("tourism", "viewpoint")})],
}
_INTEREST_ALIASES = {
    "beach": "beaches",
    "culture & heritage": "culture",
    "shopping & markets": "shopping",
    "relaxation": "wellness",
}
_FOOD_STYLE_SEARCHES = {
    "local cuisine": "restaurant",
    "street food": "street food",
    "seafood": "seafood restaurant",
    "cafes": "cafe",
    "cafe": "cafe",
    "fine dining": "fine dining restaurant",
}


def search_places(
    destination: str,
    interests: list[str] | None = None,
    limit: int = 8,
    areas: list[str] | None = None,
    diet: str | None = None,
    food_styles: list[str] | None = None,
) -> dict[str, Any]:
    """Find named OpenStreetMap places inside the requested destination."""
    if not destination.strip() or limit <= 0:
        return _unavailable("A destination and positive result limit are required.")

    specs = _search_specs(interests or [], food_styles or [], diet)
    if not specs:
        specs = [{"label": "sightseeing", "query": "tourist attraction", "types": {("tourism", "attraction")}, "food": False}]

    boundary, error = _destination_boundary(destination)
    if boundary is None:
        return _unavailable(error or f"Could not locate {destination} in OpenStreetMap.")

    area_targets = _area_targets(areas)
    search_count = len(specs) * len(area_targets)
    allowed_searches = min(search_count, _MAX_SEARCHES)
    per_search_limit = max(1, math.ceil(min(20, limit) / max(1, allowed_searches)))
    places: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    warnings: list[str] = []
    searched_preferences: set[str] = set()
    found_preferences: set[str] = set()
    searches_run = 0

    for spec in specs:
        for area_label, area_query, area_fragments in area_targets:
            if searches_run >= _MAX_SEARCHES:
                warnings.append("Search limit reached; some selected areas or preferences could not be searched.")
                break

            searched_preferences.add(spec["label"])
            params = {
                "q": " ".join(part for part in (spec["query"], area_query) if part),
                "format": "jsonv2",
                "limit": per_search_limit,
                "addressdetails": 1,
                "extratags": 1,
                "viewbox": boundary["viewbox"],
                "bounded": 1,
            }
            results, request_error = _nominatim_search(params)
            searches_run += 1
            if not isinstance(results, list):
                warnings.append(f"{spec['label']}: place search failed ({request_error or 'invalid provider response'}).")
                continue

            matches = 0
            for result in results:
                if not isinstance(result, dict) or not _matches_types(result, spec["types"]):
                    continue
                address = str(result.get("display_name") or "")
                if area_fragments and not any(fragment.casefold() in address.casefold() for fragment in area_fragments):
                    continue
                place = _place_record(result, spec, area_label, diet)
                if place is None:
                    continue
                key = (
                    result.get("osm_type"),
                    result.get("osm_id"),
                    place["latitude"],
                    place["longitude"],
                )
                if key in seen:
                    continue
                seen.add(key)
                places.append(place)
                matches += 1
                found_preferences.add(spec["label"])

            if not matches:
                warnings.append(f"{spec['label']}{f' in {area_label}' if area_label else ''}: no matching mapped places were found.")

    all_preferences = {spec["label"] for spec in specs}
    included_places = places[: min(20, limit)]
    included_preferences = {place["matched_preference"] for place in included_places}
    excluded_preferences = found_preferences - included_preferences
    if excluded_preferences:
        warnings.append(
            "The result limit excluded all places for: " + ", ".join(sorted(excluded_preferences)) + "."
        )
    places = included_places
    unmatched = sorted(all_preferences - included_preferences)
    if unmatched:
        logger.info("Place search returned no matches for: %s", ", ".join(unmatched))

    status = "ok" if places and not warnings else "partial" if places else "unavailable"
    warning = "; ".join(dict.fromkeys(warnings)) or None
    logger.info("Place search returned %s verified results for %s", len(places), destination)
    return {
        "status": status,
        "source": "OpenStreetMap Nominatim",
        "places": places,
        "searched_preferences": sorted(searched_preferences),
        "unmatched_preferences": unmatched,
        "warning": warning,
    }


def _search_specs(
    interests: list[str],
    food_styles: list[str],
    diet: str | None,
) -> list[dict[str, Any]]:
    specs = []
    for raw_interest in interests:
        interest = raw_interest.strip().casefold()
        interest = _INTEREST_ALIASES.get(interest, interest)
        if interest == "food":
            continue
        for query, place_types in _INTEREST_SEARCHES.get(
            interest,
            [("tourist attraction", {("tourism", "attraction")})],
        ):
            specs.append(
                {"label": raw_interest, "query": query, "types": place_types, "food": False}
            )

    normalized_food_styles = []
    for style in food_styles:
        style_key = style.strip().casefold()
        query = _FOOD_STYLE_SEARCHES.get(style_key, style.strip())
        if query and all(existing_query != query for _, existing_query in normalized_food_styles):
            normalized_food_styles.append((style.strip(), query))

    food_selected = any(item.strip().casefold() == "food" for item in interests)
    if food_selected or normalized_food_styles:
        if normalized_food_styles:
            for label, query in normalized_food_styles:
                specs.append(
                    {
                        "label": f"Food: {label}",
                        "query": query,
                        "types": _FOOD_TYPES,
                        "food": True,
                    }
                )
        else:
            diet_query = {
                "vegetarian": "vegetarian restaurant",
                "vegan": "vegan restaurant",
                "pescatarian": "seafood restaurant",
            }.get((diet or "").casefold(), "restaurant")
            specs.append(
                {"label": "Food", "query": diet_query, "types": _FOOD_TYPES, "food": True}
            )

    if not specs and interests:
        specs.append(
            {
                "label": interests[0],
                "query": "tourist attraction",
                "types": {("tourism", "attraction")},
                "food": False,
            }
        )
    return specs


def _destination_boundary(destination: str) -> tuple[dict[str, str] | None, str | None]:
    params = {
        "q": destination,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
    }
    results, error = _nominatim_search(params)
    if not isinstance(results, list) or not results:
        return None, error or f"No mapped boundary was found for {destination}."
    try:
        south, north, west, east = (float(value) for value in results[0]["boundingbox"])
    except (KeyError, TypeError, ValueError):
        return None, "OpenStreetMap did not provide a usable destination boundary."
    if not all(math.isfinite(value) for value in (south, north, west, east)) or south >= north or west >= east:
        return None, "OpenStreetMap returned an invalid destination boundary."
    return {"viewbox": f"{west},{north},{east},{south}"}, None


def _area_targets(areas: list[str] | None) -> list[tuple[str, str, list[str]]]:
    targets = []
    for area in areas or []:
        fragments = [part.strip() for part in re.split(r"[&,]", area) if part.strip()]
        if not fragments:
            continue
        for fragment in fragments:
            targets.append((area.strip(), fragment, fragments))
    return targets or [("", "", [])]


def _nominatim_search(params: dict[str, Any]) -> tuple[Any | None, str | None]:
    global _LAST_NOMINATIM_REQUEST

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    with _NOMINATIM_LOCK:
        elapsed = time.monotonic() - _LAST_NOMINATIM_REQUEST
        if elapsed < _NOMINATIM_MIN_INTERVAL:
            time.sleep(_NOMINATIM_MIN_INTERVAL - elapsed)
        _LAST_NOMINATIM_REQUEST = time.monotonic()
        return request_json(url, user_agent="TravelPlannerAgent/1.0 (trip-planning prototype)")


def _matches_types(result: dict[str, Any], allowed_types: set[tuple[str, str]]) -> bool:
    category = str(result.get("category") or "")
    place_type = str(result.get("type") or "")
    return (category, place_type) in allowed_types


def _place_record(
    result: dict[str, Any],
    spec: dict[str, Any],
    area: str,
    diet: str | None,
) -> dict[str, Any] | None:
    try:
        latitude = float(result["lat"])
        longitude = float(result["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None

    tags = result.get("extratags") if isinstance(result.get("extratags"), dict) else {}
    address = str(result.get("display_name") or "")
    name = str(result.get("name") or address.split(",", 1)[0]).strip()
    if not name or not address:
        return None
    place_type = str(result.get("type") or "place").replace("_", " ")
    facts = [
        f"OpenStreetMap classifies this as a {place_type}; it was selected for your {spec['label']} search."
    ]
    if area:
        facts.append(f"Located in your selected area: {area}.")
    if tags.get("cuisine"):
        facts.append(f"Cuisine listed: {tags['cuisine']}.")
    elif spec["food"]:
        facts.append("Cuisine is not listed; check the menu with the venue.")
    if tags.get("opening_hours"):
        facts.append(f"Listed opening hours: {tags['opening_hours']}.")
    else:
        facts.append("Opening hours are not listed; confirm before visiting.")
    if spec["food"] and (diet or "").casefold() in {"vegetarian", "vegan", "pescatarian"}:
        diet_tag = f"diet:{diet.casefold()}"
        diet_status = "confirmed" if tags.get(diet_tag) == "yes" else "unverified"
        facts.append(
            f"Your {diet} preference is {diet_status} in OpenStreetMap; contact the venue to confirm."
        )
    else:
        diet_status = None

    details = {
        "address": address,
        "opening_hours": tags.get("opening_hours"),
        "cuisine": tags.get("cuisine"),
        "website": tags.get("website") or tags.get("contact:website"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "wheelchair": tags.get("wheelchair"),
    }
    return {
        "name": name,
        "category": place_type.title(),
        "latitude": latitude,
        "longitude": longitude,
        "source": "OpenStreetMap Nominatim",
        "osm_type": result.get("osm_type"),
        "osm_id": result.get("osm_id"),
        "matched_preference": spec["label"],
        "area": area or None,
        "description": " ".join(facts),
        "details": {key: value for key, value in details.items() if value},
        "dietary_status": diet_status,
        "cost_estimate": None,
        "cost_status": "unknown",
    }


def _unavailable(message: str) -> dict[str, Any]:
    logger.warning("Place search unavailable: %s", message)
    return {
        "status": "unavailable",
        "source": "OpenStreetMap Nominatim",
        "places": [],
        "searched_preferences": [],
        "unmatched_preferences": [],
        "warning": message,
    }
