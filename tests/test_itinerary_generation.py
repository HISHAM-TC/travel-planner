import unittest

from app.models import TripRequest
from agents.itinerary_generator import generate_placeholder_itinerary


class ItineraryGenerationTests(unittest.TestCase):
    def test_itinerary_respects_pace_limit(self):
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
        self.assertIn(result["status"], {"draft_ready", "finalized"})
        self.assertEqual(len(result["itinerary"]["days_plan"]), 4)

        for day in result["itinerary"]["days_plan"]:
            self.assertLessEqual(len(day["stops"]), 4)
            known_day_cost = sum(
                stop["cost_estimate"]
                for stop in day["stops"]
                if isinstance(stop.get("cost_estimate"), (int, float))
            )
            self.assertEqual(day["estimated_day_cost"], known_day_cost)

        self.assertLessEqual(result["itinerary"]["total_estimated_cost"], trip.budget)

    def test_itinerary_handles_missing_follows_up(self):
        trip = TripRequest(days=3, budget=1000, currency="INR")
        result = generate_placeholder_itinerary(trip)
        self.assertEqual(result["status"], "needs_follow_up")


if __name__ == "__main__":
    unittest.main()
