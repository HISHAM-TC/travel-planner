import unittest
from unittest.mock import patch

from app.models import TripRequest
from agent.planner import distribute_places
from agents.itinerary_generator import generate_placeholder_itinerary


class ItineraryGenerationTests(unittest.TestCase):
    def _tool_data(self, places):
        return {
            "weather": {"status": "ok", "days": []},
            "places": {"status": "ok" if places else "unavailable", "places": places, "warning": None if places else "Place provider unavailable."},
            "budget": {
                "category_allocations": {},
                "known_cost_total": 0,
                "remaining_after_known_costs": 25000,
            },
            "travel_estimates": [],
        }

    def test_search_results_are_spread_across_long_trips(self):
        days = distribute_places([{"id": index} for index in range(20)], 7, 4)

        self.assertEqual([len(day) for day in days], [3, 3, 3, 3, 3, 3, 2])
        self.assertEqual(sum(map(len, days)), 20)

    @patch("agent.loop._gather_tool_data")
    def test_itinerary_respects_pace_limit(self, gather_tool_data):
        places = []
        for index in range(16):
            is_beach = index % 2 == 0
            places.append(
                {
                    "name": f"Place {index + 1}",
                    "category": "Beach" if is_beach else "Restaurant",
                    "latitude": 15.4 + index / 1000,
                    "longitude": 73.8 + index / 1000,
                    "matched_preference": "beaches" if is_beach else "Food: local cuisine",
                    "description": "Mapped place matching a requested interest.",
                    "details": {"opening_hours": "09:00-18:00"},
                    "cost_estimate": None,
                    "cost_status": "unknown",
                }
            )
        gather_tool_data.return_value = (self._tool_data(places), None)
        trip = TripRequest(
            destination="Goa",
            start_date="2026-12-10",
            days=4,
            budget=25000,
            currency="INR",
            interests=["beaches", "food"],
            group_size=2,
            pace="balanced",
        )

        result = generate_placeholder_itinerary(trip)
        self.assertEqual(result["status"], "finalized")
        self.assertEqual(len(result["itinerary"]["days_plan"]), 4)

        for day in result["itinerary"]["days_plan"]:
            self.assertEqual(len(day["stops"]), 4)
            self.assertEqual(
                {stop["matched_preference"] for stop in day["stops"]},
                {"beaches", "Food: local cuisine"},
            )
            for stop in day["stops"]:
                self.assertIn("Mapped place", stop["description"])
                self.assertEqual(stop["details"]["opening_hours"], "09:00-18:00")
                self.assertGreater(stop["duration_minutes"], 0)
                self.assertLess(stop["time"], stop["end_time"])
            known_day_cost = sum(
                stop["cost_estimate"]
                for stop in day["stops"]
                if isinstance(stop.get("cost_estimate"), (int, float))
            )
            self.assertEqual(day["estimated_day_cost"], known_day_cost)

        self.assertLessEqual(result["itinerary"]["total_estimated_cost"], trip.budget)

    @patch("agent.loop._gather_tool_data")
    def test_days_without_verified_places_are_not_finalized(self, gather_tool_data):
        gather_tool_data.return_value = (self._tool_data([]), None)
        trip = TripRequest(
            destination="Goa",
            start_date="2026-12-10",
            days=2,
            budget=25000,
            currency="INR",
            interests=["beaches"],
            group_size=2,
        )

        result = generate_placeholder_itinerary(trip)

        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(all(not day["stops"] for day in result["itinerary"]["days_plan"]))
        self.assertIn("empty_day", [issue["type"] for issue in result["verification"]["issues"]])
        self.assertIn("Place provider unavailable.", result["itinerary"]["data_warnings"])

    @patch("agent.loop._gather_tool_data")
    def test_unmatched_selected_interest_requires_review(self, gather_tool_data):
        places = [
            {
                "name": f"Beach {day}",
                "category": "Beach",
                "latitude": 15.4 + day / 100,
                "longitude": 73.8 + day / 100,
                "matched_preference": "beaches",
                "description": "OpenStreetMap beach result.",
                "details": {},
                "cost_estimate": None,
                "cost_status": "unknown",
            }
            for day in range(1, 3)
        ]
        tool_data = self._tool_data(places)
        tool_data["places"]["status"] = "partial"
        tool_data["places"]["unmatched_preferences"] = ["Food"]
        tool_data["places"]["warning"] = "No food results were found."
        gather_tool_data.return_value = (tool_data, None)
        trip = TripRequest(
            destination="Goa",
            start_date="2026-12-10",
            days=2,
            budget=25000,
            currency="INR",
            interests=["beaches", "food"],
            group_size=2,
        )

        result = generate_placeholder_itinerary(trip)

        self.assertEqual(result["status"], "needs_review")
        self.assertIn(
            "unmatched_preferences",
            [issue["type"] for issue in result["verification"]["issues"]],
        )

    def test_itinerary_handles_missing_follows_up(self):
        trip = TripRequest(days=3, budget=1000, currency="INR")
        result = generate_placeholder_itinerary(trip)
        self.assertEqual(result["status"], "needs_follow_up")


if __name__ == "__main__":
    unittest.main()
