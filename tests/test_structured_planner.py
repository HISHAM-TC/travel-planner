from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import patch

from agent.loop import plan_trip


class StructuredPlannerTests(unittest.TestCase):
    @patch("agent.loop.parse_trip_request", side_effect=AssertionError("parser should not be called"))
    @patch("agent.loop._gather_tool_data")
    def test_structured_destination_skips_text_parser_and_uses_budget_split(
        self, gather_tool_data, _parse_trip_request
    ):
        start_date = (date.today() + timedelta(days=30)).isoformat()
        gather_tool_data.return_value = (
            {
                "weather": {
                    "status": "ok",
                    "days": [
                        {"date": start_date, "summary": "Clear sky"},
                        {"date": (date.today() + timedelta(days=31)).isoformat(), "summary": "Clear sky"},
                    ],
                },
                "places": {"status": "ok", "places": []},
                "budget": {
                    "category_allocations": {},
                    "known_cost_total": 0,
                    "remaining_after_known_costs": 25000,
                },
                "travel_estimates": [],
            },
            None,
        )
        request = {
            "request": "Plan a 2-day trip to Goa.",
            "destination": "Goa",
            "start_date": start_date,
            "days": 2,
            "budget": 25000,
            "currency": "INR",
            "interests": ["beaches", "food"],
            "group_size": 2,
            "pace": "balanced",
            "budget_split": {
                "stay": 10000,
                "food": 7000,
                "transport": 4000,
                "activities": 3000,
                "misc": 1000,
            },
            "areas": ["Panjim"],
            "travelers": {"adults": 2, "children": 0},
            "diet": "Vegetarian",
        }

        result = plan_trip("Plan a trip to Goa with a budget", structured_request=request)

        self.assertEqual(result["parsed_request"]["destination"], "Goa")
        self.assertEqual(result["parsed_request"]["request"], request["request"])
        self.assertEqual(
            result["itinerary"]["budget_summary"]["category_allocations"],
            request["budget_split"],
        )
        self.assertEqual(result["itinerary"]["planning_preferences"]["areas"], ["Panjim"])
        self.assertEqual(result["itinerary"]["planning_preferences"]["diet"], "Vegetarian")
        gather_tool_data.assert_called_once()


if __name__ == "__main__":
    unittest.main()
