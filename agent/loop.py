from __future__ import annotations

import json
import logging
from typing import Any

from app.config import API_TIMEOUT_SECONDS, MODEL_NAME, OPENAI_API_KEY
from app.parser import parse_trip_request
from app.validator import validate_trip_request
from agent.planner import PACE_LIMITS, build_itinerary, distribute_places, interleave_places
from agent.verifier import finalize_itinerary
from models.trip import TripRequest, trip_request_from_dict
from tools.budget import calculate_trip_budget
from tools.maps import estimate_travel_time
from tools.places import search_places
from tools.schemas import TOOL_SCHEMAS
from tools.weather import get_weather_forecast

logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 6


def plan_trip(
    request_text: str,
    preferences: dict | None = None,
    structured_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse, gather tool context, plan, verify, and return a structured result."""
    if structured_request and any(key in TripRequest.__dataclass_fields__ for key in structured_request):
        trip = trip_request_from_dict(structured_request)
    else:
        trip = parse_trip_request(request_text, preferences)
    validation = validate_trip_request(trip)
    if not validation["valid"]:
        return {
            "status": "needs_follow_up",
            "validation": validation,
            "parsed_request": trip.to_dict(),
            "itinerary": None,
            "verification": None,
            "revisions": [],
        }

    tool_data, agent_warning = _gather_tool_data(trip)
    _apply_budget_split(trip, tool_data)
    itinerary = build_itinerary(trip, tool_data)
    finalized = finalize_itinerary(trip, itinerary)
    if agent_warning:
        finalized["itinerary"]["data_warnings"].append(agent_warning)
    return {
        "status": finalized["status"],
        "validation": validation,
        "parsed_request": trip.to_dict(),
        "tool_data": tool_data,
        "itinerary": finalized["itinerary"],
        "verification": finalized["verification"],
        "revisions": finalized["revisions"],
    }


def _gather_tool_data(trip: TripRequest) -> tuple[dict[str, Any], str | None]:
    if OPENAI_API_KEY:
        try:
            return _gather_with_openai(trip), None
        except _openai_error_types() as exc:
            logger.exception("OpenAI tool-calling request failed; using direct tool orchestration.")
            warning = f"LLM tool calling was unavailable; tools were called directly instead ({exc})."
            return _gather_directly(trip), warning
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.exception("Invalid LLM tool-call response; using direct tool orchestration.")
            warning = f"LLM tool response was invalid; tools were called directly instead ({exc})."
            return _gather_directly(trip), warning

    logger.info("OPENAI_API_KEY is unset; using direct tool orchestration.")
    return _gather_directly(trip), "LLM tool calling was not enabled because OPENAI_API_KEY is unset."


def _gather_with_openai(trip: TripRequest) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS, max_retries=1)
    messages = [
        {
            "role": "system",
            "content": (
                "You are the tool-selection component of a travel planner. Use the supplied tools to get "
                "weather, places, and budget data. Use estimate_travel_time only with coordinates returned "
                "by place search. Use the complete structured trip request to respect areas, travelers, "
                "arrival, accommodation, transport, dietary, and food-style preferences. Only search for "
                "vegetarian food when the diet is Vegetarian. Do not invent data. Call each needed tool at most once."
            ),
        },
        {"role": "user", "content": json.dumps(trip.to_dict(), ensure_ascii=False)},
    ]
    results: dict[str, Any] = {"travel_estimates": []}
    called: set[str] = set()

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        messages.append(message.model_dump(exclude_none=True))
        if not tool_calls:
            break

        for tool_call in tool_calls:
            name = tool_call.function.name
            if name in called and name != "estimate_travel_time":
                output = {"status": "error", "error": "This tool was already called for this request."}
            else:
                arguments = _structured_tool_arguments(
                    name, json.loads(tool_call.function.arguments), trip
                )
                output = _execute_tool(name, arguments)
                called.add(name)
                _collect_result(results, name, output)
            logger.info("Tool call via OpenAI function calling: %s", name)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(output, ensure_ascii=False),
                }
            )

    _ensure_required_tool_results(trip, results)
    _add_route_estimates(results, trip)
    return results


def _gather_directly(trip: TripRequest) -> dict[str, Any]:
    """Fallback orchestration when no OpenAI key is configured."""
    results = {
        "weather": get_weather_forecast(trip.destination or "", trip.start_date or "", trip.days or 0),
        "places": search_places(
            trip.destination or "",
            trip.interests or [],
            limit=_place_search_limit(trip),
            areas=trip.areas,
            diet=trip.diet,
            food_styles=trip.food_styles,
        ),
        "budget": calculate_trip_budget(
            trip.budget or 0,
            trip.days or 0,
            trip.currency or "INR",
            budget_split=trip.budget_split,
        ),
        "travel_estimates": [],
    }
    logger.info("Tool call direct: weather")
    logger.info("Tool call direct: search_places")
    logger.info("Tool call direct: calculate_trip_budget")
    _add_route_estimates(results, trip)
    return results


def _execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "get_weather_forecast":
        return get_weather_forecast(**arguments)
    if name == "search_places":
        return search_places(**arguments)
    if name == "calculate_trip_budget":
        return calculate_trip_budget(**arguments)
    if name == "estimate_travel_time":
        origin = tuple(arguments["origin"])
        destination = tuple(arguments["destination"])
        return estimate_travel_time(
            origin, destination, transport_modes=arguments.get("transport_modes")
        )
    raise ValueError(f"Unknown tool requested by model: {name}")


def _structured_tool_arguments(name: str, arguments: dict[str, Any], trip: TripRequest) -> dict[str, Any]:
    if name == "get_weather_forecast":
        return {
            **arguments,
            "destination": trip.destination or "",
            "start_date": trip.start_date or "",
            "days": trip.days or 0,
        }
    if name == "search_places":
        return {
            **arguments,
            "destination": trip.destination or "",
            "interests": trip.interests or [],
            "areas": trip.areas or [],
            "diet": trip.diet,
            "food_styles": trip.food_styles or [],
            "limit": _place_search_limit(trip),
        }
    if name == "calculate_trip_budget":
        return {
            **arguments,
            "budget": trip.budget or 0,
            "days": trip.days or 0,
            "currency": trip.currency or "INR",
            "budget_split": trip.budget_split,
        }
    if name == "estimate_travel_time":
        return {**arguments, "transport_modes": trip.local_transport or []}
    return arguments


def _apply_budget_split(trip: TripRequest, tool_data: dict[str, Any]) -> None:
    if trip.budget_split is None:
        return
    category_allocations = {
        key: round(trip.budget_split.get(key, 0), 2)
        for key in ("stay", "food", "transport", "activities", "misc")
    }
    tool_data["budget"]["category_allocations"] = category_allocations


def _collect_result(results: dict[str, Any], name: str, output: dict[str, Any]) -> None:
    target = {
        "get_weather_forecast": "weather",
        "search_places": "places",
        "calculate_trip_budget": "budget",
    }.get(name)
    if target:
        results[target] = output
    elif name == "estimate_travel_time":
        results["travel_estimates"].append(output)


def _ensure_required_tool_results(trip: TripRequest, results: dict[str, Any]) -> None:
    if "weather" not in results:
        logger.info("Tool call fallback: weather was not selected by LLM; invoking it directly.")
        results["weather"] = get_weather_forecast(trip.destination or "", trip.start_date or "", trip.days or 0)
    if "places" not in results:
        logger.info("Tool call fallback: place search was not selected by LLM; invoking it directly.")
        results["places"] = search_places(
            trip.destination or "",
            trip.interests or [],
            limit=_place_search_limit(trip),
            areas=trip.areas,
            diet=trip.diet,
            food_styles=trip.food_styles,
        )
    if "budget" not in results:
        logger.info("Tool call fallback: budget calculator was not selected by LLM; invoking it directly.")
        results["budget"] = calculate_trip_budget(
            trip.budget or 0,
            trip.days or 0,
            trip.currency or "INR",
            budget_split=trip.budget_split,
        )


def _add_route_estimates(results: dict[str, Any], trip: TripRequest) -> None:
    places = interleave_places(results.get("places", {}).get("places", []))
    estimates = results.setdefault("travel_estimates", [])
    existing = {(item.get("origin"), item.get("destination")) for item in estimates}
    pace_limit = PACE_LIMITS.get((trip.pace or "balanced").lower(), 4)
    for day_places in distribute_places(places, trip.days or 0, pace_limit):
        for first, second in zip(day_places, day_places[1:]):
            pair = (first.get("name"), second.get("name"))
            if pair in existing:
                continue
            estimate = estimate_travel_time(
                (first["latitude"], first["longitude"]),
                (second["latitude"], second["longitude"]),
                transport_modes=trip.local_transport,
            )
            estimates.append({"origin": pair[0], "destination": pair[1], **estimate})
            existing.add(pair)


def _place_search_limit(trip: TripRequest) -> int:
    pace_limit = PACE_LIMITS.get((trip.pace or "balanced").lower(), 4)
    return min(20, max(1, (trip.days or 1) * pace_limit))


def _openai_error_types():
    from openai import OpenAIError

    return OpenAIError


def generate_placeholder_itinerary(trip_request: TripRequest) -> dict[str, Any]:
    """Compatibility entry point for callers using the original generator."""
    result = plan_trip(
        trip_request.notes or _request_summary(trip_request),
        _trip_preferences(trip_request),
        trip_request.to_dict(),
    )
    if result["parsed_request"] != trip_request.to_dict():
        result["parsed_request"] = trip_request.to_dict()
    return {
        "status": result["status"],
        "validation": result["validation"],
        "verification": result["verification"],
        "revisions": result["revisions"],
        "itinerary": result["itinerary"],
    }


def _request_summary(trip: TripRequest) -> str:
    parts = []
    if trip.days:
        parts.append(f"{trip.days} days")
    if trip.destination:
        parts.append(f"in {trip.destination}")
    if trip.budget:
        parts.append(f"budget {trip.budget} {trip.currency or 'INR'}")
    if trip.interests:
        parts.append("interests " + " ".join(trip.interests))
    return ", ".join(parts)


def _trip_preferences(trip: TripRequest) -> dict[str, Any]:
    return {
        "interests": trip.interests or [],
        "pace": trip.pace,
        "currency": trip.currency,
        "group_size": trip.group_size,
    }
