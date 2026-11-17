import unittest
from unittest.mock import patch

from app.models import TripRequest
from app.tools import calculate_trip_budget, gather_tool_context, estimate_travel_time
from tools.budget import calculate_trip_budget as calculate_budget_allocation
from tools.places import search_places


class ToolIntegrationTests(unittest.TestCase):
    def test_trip_budget_calculation(self):
        trip = TripRequest(destination="Goa", days=4, budget=25000, currency="INR", interests=["beaches", "food"])
        budget = calculate_trip_budget(trip)

        self.assertEqual(budget["currency"], "INR")
        self.assertEqual(budget["budget_total"], trip.budget)
        self.assertGreaterEqual(budget["known_cost_total"], 0)
        self.assertGreaterEqual(budget["remaining_after_known_costs"], 0)

    def test_structured_budget_split_replaces_default_shares(self):
        split = {"stay": 10000, "food": 7000, "transport": 4000, "activities": 3000, "misc": 1000}
        summary = calculate_budget_allocation(25000, 4, "INR", budget_split=split)

        self.assertEqual(summary["category_allocations"], split)

    @patch(
        "tools.places.request_json",
        return_value=(
            [{"display_name": "Panjim, Goa", "lat": "15.49", "lon": "73.83", "type": "city"}],
            None,
        ),
    )
    def test_place_search_uses_selected_area_and_diet(self, request_json):
        result = search_places("Goa", ["food"], areas=["Panjim"], diet="Vegetarian")

        self.assertEqual(result["status"], "ok")
        query = request_json.call_args.args[0]
        self.assertIn("Panjim", query)
        self.assertIn("Goa", query)
        self.assertIn("vegetarian", query)

    def test_tool_context_returns_weather_and_places(self):
        trip = TripRequest(destination="Goa", days=3, budget=15000, currency="INR", interests=["beaches", "food"], start_date="2026-12-10")
        context = gather_tool_context(trip)

        self.assertIn("weather", context)
        self.assertIn("places", context)
        self.assertIn("budget_summary", context)
        self.assertTrue(bool(context["weather"]))

    def test_travel_time_estimation(self):
        estimate = estimate_travel_time((15.2993, 74.1240), (15.4909, 73.8278))
        self.assertIn("distance_km", estimate)
        self.assertIn("estimated_minutes", estimate)
        self.assertGreater(estimate["estimated_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
