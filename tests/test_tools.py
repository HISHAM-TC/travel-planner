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

    @patch("tools.places.time.sleep")
    @patch("tools.places.request_json")
    def test_place_search_uses_areas_interests_food_style_and_diet(self, request_json, _sleep):
        destination = [
            {
                "boundingbox": ["14.7", "15.8", "73.6", "74.4"],
                "display_name": "Goa, India",
            }
        ]
        beach = [
            {
                "display_name": "Miramar Beach, Panjim, Goa",
                "name": "Miramar Beach",
                "lat": "15.49",
                "lon": "73.83",
                "category": "natural",
                "type": "beach",
                "osm_type": "way",
                "osm_id": 1,
                "extratags": {"surface": "sand"},
            }
        ]
        seafood = [
            {
                "display_name": "Seafood Restaurant, Panjim, Goa",
                "name": "Seafood Restaurant",
                "lat": "15.50",
                "lon": "73.84",
                "category": "amenity",
                "type": "restaurant",
                "osm_type": "node",
                "osm_id": 2,
                "extratags": {"cuisine": "seafood"},
            }
        ]
        request_json.side_effect = [(destination, None), (beach, None), (seafood, None)]

        result = search_places(
            "Goa",
            ["beaches", "food"],
            areas=["Panjim"],
            diet="Vegetarian",
            food_styles=["Seafood"],
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual([place["name"] for place in result["places"]], ["Miramar Beach", "Seafood Restaurant"])
        self.assertEqual(result["places"][0]["matched_preference"], "beaches")
        self.assertEqual(result["places"][1]["dietary_status"], "unverified")
        search_urls = [call.args[0] for call in request_json.call_args_list[1:]]
        self.assertIn("beach+Panjim", search_urls[0])
        self.assertIn("seafood+restaurant+Panjim", search_urls[1])
        self.assertTrue(all("bounded=1" in url and "viewbox=" in url for url in search_urls))

    def test_tool_context_returns_weather_and_places(self):
        trip = TripRequest(destination="Goa", days=3, budget=15000, currency="INR", interests=["beaches", "food"], start_date="2026-12-10")
        context = gather_tool_context(trip)

        self.assertIn("weather", context)
        self.assertIn("places", context)
        self.assertIn("budget_summary", context)
        self.assertTrue(bool(context["weather"]))

    def test_travel_time_estimation(self):
        origin, destination = (15.2993, 74.1240), (15.4909, 73.8278)
        estimate = estimate_travel_time(origin, destination)
        self.assertIn("distance_km", estimate)
        self.assertIn("estimated_minutes", estimate)
        self.assertGreater(estimate["estimated_minutes"], 0)
        walking = estimate_travel_time(origin, destination, ["Mostly on foot"])
        scooter = estimate_travel_time(origin, destination, ["Rented scooter"])
        self.assertGreater(walking["estimated_minutes"], scooter["estimated_minutes"])
        self.assertEqual(walking["mode_assumption"], "walking")


if __name__ == "__main__":
    unittest.main()
