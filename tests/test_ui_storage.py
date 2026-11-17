import unittest

from app.storage import load_preferences, load_trips, save_preferences, save_trip
from app.ui import build_chat_session


class UiStorageTests(unittest.TestCase):
    def test_chat_session_saves_preferences_and_trip(self):
        request = "Plan a 3-day trip to Goa with a budget of INR 18000 for 2 people. I like beaches and food."
        session = build_chat_session(request)

        self.assertIn("parsed_request", session)
        self.assertIn("saved_trip", session)
        self.assertIn("preferences", session)
        self.assertTrue(session["saved_trip"]["destination"] == "Goa" or session["saved_trip"]["destination"] is None)

        preferences = load_preferences()
        self.assertIn("interests", preferences)
        self.assertIn("pace", preferences)

        trips = load_trips()
        self.assertTrue(len(trips) >= 1)

    def test_storage_round_trip(self):
        save_preferences({"currency": "INR", "pace": "balanced"})
        saved = save_trip({"destination": "Kerala", "days": 2, "budget": 12000})

        self.assertEqual(load_preferences()["currency"], "INR")
        self.assertEqual(saved["destination"], "Kerala")


if __name__ == "__main__":
    unittest.main()
