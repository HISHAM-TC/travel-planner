from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CATEGORY_SHARES = {
    "stay": 0.35,
    "food": 0.25,
    "transport": 0.20,
    "activities": 0.15,
    "misc": 0.05,
}


def calculate_trip_budget(
    budget: float,
    days: int,
    currency: str,
    known_costs: list[float] | None = None,
    budget_split: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Return planning allocations separately from known, sourced expenses."""
    if budget <= 0:
        raise ValueError("Budget must be greater than zero.")
    if days <= 0:
        raise ValueError("Trip duration must be greater than zero.")

    category_allocations = (
        {key: round(budget_split.get(key, 0), 2) for key in CATEGORY_SHARES}
        if budget_split is not None
        else {key: round(budget * share, 2) for key, share in CATEGORY_SHARES.items()}
    )
    known_total = round(sum(value for value in (known_costs or []) if value >= 0), 2)
    logger.info("Tool call budget_calculator: budget=%s %s days=%s", budget, currency, days)
    return {
        "currency": currency,
        "budget_total": round(budget, 2),
        "daily_budget_ceiling": round(budget / days, 2),
        "category_allocations": category_allocations,
        "allocation_note": "Planning allocations, not quoted or confirmed prices.",
        "known_cost_total": known_total,
        "unpriced_items": None,
        "remaining_after_known_costs": round(budget - known_total, 2),
        "remaining_note": "Excludes activities or services whose prices are unavailable.",
    }
