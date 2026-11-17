from __future__ import annotations

import copy
import logging
from typing import Any

from models.trip import TripRequest
from agent.planner import PACE_LIMITS

logger = logging.getLogger(__name__)


def verify_itinerary(trip: TripRequest, itinerary: dict[str, Any]) -> dict[str, Any]:
    """Check day coverage, budget arithmetic, pace, schedule order, and travel gaps."""
    issues: list[dict[str, str]] = []
    warnings: list[str] = []
    plans = itinerary.get("days_plan")
    if not isinstance(plans, list) or not plans:
        return _result([{"type": "empty_plan", "message": "No day plans were generated."}], warnings, 0, trip.budget or 0)
    if trip.days is not None and len(plans) != trip.days:
        issues.append({"type": "day_count", "message": f"Expected {trip.days} day plans, received {len(plans)}."})

    budget = float(trip.budget or 0)
    pace_limit = PACE_LIMITS.get((trip.pace or "balanced").lower(), 4)
    computed_total = 0.0
    unpriced = 0
    for day_number, day in enumerate(plans, start=1):
        stops = day.get("stops", [])
        if len(stops) > pace_limit:
            issues.append({"type": "pace_limit", "message": f"Day {day_number} has {len(stops)} stops; limit is {pace_limit}."})
        previous_minutes = None
        previous_stop = None
        for stop in stops:
            minutes = _to_minutes(stop.get("time"))
            if previous_minutes is not None and minutes <= previous_minutes:
                issues.append({"type": "schedule_order", "message": f"Day {day_number} stops are not in strictly increasing time order."})
                break
            if previous_stop is not None:
                travel = _travel_minutes(previous_stop, stop)
                if travel is not None and minutes - previous_minutes < travel:
                    issues.append({"type": "travel_gap", "message": f"Day {day_number} has insufficient time for estimated travel between stops."})
                    break
            previous_minutes = minutes
            previous_stop = stop
            cost = stop.get("cost_estimate")
            if cost is None:
                unpriced += 1
            elif isinstance(cost, (int, float)) and cost >= 0:
                computed_total += cost
            else:
                issues.append({"type": "invalid_cost", "message": f"Day {day_number} contains an invalid cost estimate."})
        day_total = round(sum(
            stop["cost_estimate"] for stop in stops
            if isinstance(stop.get("cost_estimate"), (int, float)) and stop["cost_estimate"] >= 0
        ), 2)
        if round(float(day.get("estimated_day_cost", 0)), 2) != day_total:
            issues.append({"type": "day_cost_mismatch", "message": f"Day {day_number} total does not match its priced stops."})

    computed_total = round(computed_total, 2)
    if round(float(itinerary.get("total_estimated_cost", 0)), 2) != computed_total:
        issues.append({"type": "trip_cost_mismatch", "message": "Trip total does not match the priced stops."})
    if budget and computed_total > budget:
        issues.append({"type": "budget_overrun", "message": f"Known estimated costs {computed_total} exceed budget {budget}."})
    if unpriced:
        warnings.append(f"{unpriced} itinerary stop(s) have no sourced price; budget compliance is incomplete.")
    return _result(issues, warnings, computed_total, budget)


def revise_itinerary_if_needed(
    trip: TripRequest,
    itinerary: dict[str, Any],
    max_loops: int = 3,
) -> dict[str, Any]:
    """Revise only objective constraint failures, with no more than three loops."""
    if not 0 <= max_loops <= 3:
        raise ValueError("max_loops must be between 0 and 3.")
    current = copy.deepcopy(itinerary)
    history = []
    verification = verify_itinerary(trip, current)

    for loop_index in range(1, max_loops + 1):
        if verification["valid"]:
            break
        changes = _apply_revisions(trip, current, verification["issues"])
        history.append({"loop": loop_index, "issues": verification["issues"], "changes": changes})
        logger.info("Revision loop %s: %s", loop_index, changes or "no safe automatic revision available")
        verification = verify_itinerary(trip, current)
        if not changes:
            break

    status = "finalized" if verification["valid"] else "needs_review"
    return {"status": status, "itinerary": current, "verification": verification, "revisions": history}


def finalize_itinerary(trip: TripRequest, itinerary: dict[str, Any]) -> dict[str, Any]:
    return revise_itinerary_if_needed(trip, itinerary, max_loops=3)


def _apply_revisions(trip: TripRequest, itinerary: dict[str, Any], issues: list[dict]) -> list[str]:
    changes = []
    pace_limit = PACE_LIMITS.get((trip.pace or "balanced").lower(), 4)
    issue_types = {issue["type"] for issue in issues}

    for day in itinerary.get("days_plan", []):
        stops = day.get("stops", [])
        if "pace_limit" in issue_types and len(stops) > pace_limit:
            day["stops"] = stops[:pace_limit]
            changes.append(f"Trimmed day {day.get('day')} to the {pace_limit}-stop pace limit.")
        if "travel_gap" in issue_types and len(day.get("stops", [])) > 1:
            day["stops"].pop()
            changes.append(f"Removed the last stop from day {day.get('day')} due to insufficient travel time.")
        if "schedule_order" in issue_types and len(day.get("stops", [])) > 1:
            day["stops"] = sorted(day["stops"], key=lambda stop: _to_minutes(stop.get("time")))
            changes.append(f"Sorted day {day.get('day')} stops by their scheduled time.")
        day["estimated_day_cost"] = round(sum(
            stop["cost_estimate"] for stop in day.get("stops", [])
            if isinstance(stop.get("cost_estimate"), (int, float))
        ), 2)

    if "budget_overrun" in issue_types:
        candidates = sorted(
            (
                (day, stop) for day in itinerary.get("days_plan", [])
                for stop in day.get("stops", [])
                if isinstance(stop.get("cost_estimate"), (int, float)) and stop["cost_estimate"] > 0
            ),
            key=lambda item: item[1]["cost_estimate"],
            reverse=True,
        )
        total = sum(day["estimated_day_cost"] for day in itinerary.get("days_plan", []))
        while total > (trip.budget or 0) and candidates:
            day, stop = candidates.pop(0)
            day["stops"].remove(stop)
            total -= stop["cost_estimate"]
            day["estimated_day_cost"] = round(sum(
                item["cost_estimate"] for item in day["stops"]
                if isinstance(item.get("cost_estimate"), (int, float))
            ), 2)
            changes.append(f"Removed an over-budget priced stop from day {day.get('day')}.")

    itinerary["total_estimated_cost"] = round(sum(day.get("estimated_day_cost", 0) for day in itinerary.get("days_plan", [])), 2)
    itinerary["remaining_budget"] = round((trip.budget or 0) - itinerary["total_estimated_cost"], 2)
    return changes


def _travel_minutes(origin: dict, destination: dict) -> int | None:
    estimate = destination.get("travel_from_previous")
    return int(estimate) if isinstance(estimate, (int, float)) else None


def _to_minutes(time_value: str | None) -> int:
    try:
        hour, minute = (time_value or "").split(":", 1)
        if not (0 <= int(hour) < 24 and 0 <= int(minute) < 60):
            return -1
        return int(hour) * 60 + int(minute)
    except ValueError:
        return -1


def _result(issues: list[dict[str, str]], warnings: list[str], total: float, budget: float) -> dict[str, Any]:
    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "summary": "All verifiable itinerary checks passed." if not issues else "Issues found; the plan needs revision or review.",
        "known_estimated_cost": total,
        "budget": budget,
        "budget_status": "over_budget" if total > budget else "incomplete" if warnings else "within_known_costs",
    }
