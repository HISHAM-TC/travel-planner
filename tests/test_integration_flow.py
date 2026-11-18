import unittest
from datetime import date, timedelta
from unittest.mock import patch

from app.storage import load_preferences, load_trips
from app.ui import build_chat_session


class IntegrationFlowTests(unittest.TestCase):
    def test_incomplete_itinerary_is_not_saved_as_finished(self):
        start_date = (date.today() + timedelta(days=30)).isoformat()
        tool_data = (
            {
                "weather": {"status": "unavailable", "days": [], "warning": "Forecast unavailable."},
                "places": {
                    "status": "unavailable",
                    "places": [],
                    "warning": "No matching places were found.",
                },
                "budget": {
                    "category_allocations": {},
                    "known_cost_total": 0,
                    "remaining_after_known_costs": 10000,
                },
                "travel_estimates": [],
            },
            None,
        )
        request = {
            "destination": "Goa",
            "start_date": start_date,
            "days": 2,
            "budget": 10000,
            "currency": "INR",
            "interests": ["beaches"],
            "group_size": 1,
        }

        with patch("agent.loop._gather_tool_data", return_value=tool_data):
            session = build_chat_session("Plan a two-day Goa trip", request)

        self.assertEqual(session["itinerary_output"]["status"], "needs_review")
        self.assertIsNone(session["saved_trip"])

    def test_full_demo_flow(self):
        request = (
            "Plan a 4-day trip to Goa with a budget of INR 25000 for 2 people. "
            "I like beaches and food. Start on 2026-12-10 and keep it balanced."
        )

        place_results = [
            {
                "name": f"Goa place {day}",
                "category": "Attraction",
                "latitude": 15.4 + day / 100,
                "longitude": 73.8 + day / 100,
                "matched_preference": "beaches",
                "description": "OpenStreetMap attraction matching the requested interest.",
                "details": {},
                "cost_estimate": None,
                "cost_status": "unknown",
            }
            for day in range(1, 5)
        ]
        tool_data = (
            {
                "weather": {"status": "unavailable", "days": [], "warning": "Forecast unavailable for test."},
                "places": {"status": "ok", "places": place_results, "warning": None},
                "budget": {
                    "category_allocations": {},
                    "known_cost_total": 0,
                    "remaining_after_known_costs": 25000,
                },
                "travel_estimates": [],
            },
            None,
        )
        with patch("agent.loop._gather_tool_data", return_value=tool_data):
            session = build_chat_session(request)
        itinerary = session["itinerary_output"]["itinerary"]

        self.assertEqual(itinerary["destination"], "Goa")
        self.assertEqual(itinerary["days"], 4)
        self.assertTrue(itinerary["total_estimated_cost"] <= 25000)
        self.assertTrue(itinerary["remaining_budget"] >= 0)

        preferences = load_preferences()
        self.assertIn("interests", preferences)
        self.assertEqual(preferences["pace"], "balanced")

        trips = load_trips()
        self.assertTrue(len(trips) >= 1)
        self.assertEqual(trips[-1]["destination"], "Goa")


if __name__ == "__main__":
    unittest.main()
