import unittest

from app.storage import load_preferences, load_trips
from app.ui import build_chat_session


class IntegrationFlowTests(unittest.TestCase):
    def test_full_demo_flow(self):
        request = (
            "Plan a 4-day trip to Goa with a budget of INR 25000 for 2 people. "
            "I like beaches and food. Start on 2026-12-10 and keep it balanced."
        )

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
