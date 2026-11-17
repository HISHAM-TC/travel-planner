import unittest

from app.parser import parse_trip_request
from app.validator import validate_trip_request


class ParserValidationTests(unittest.TestCase):
    def test_parse_valid_trip_request(self):
        request = (
            "Plan a 4-day trip to Goa with a budget of INR 25000 for 2 people. "
            "I like beaches and food. Start on 2026-12-10 and keep it balanced."
        )
        trip = parse_trip_request(request)

        self.assertEqual(trip.destination, "Goa")
        self.assertEqual(trip.days, 4)
        self.assertEqual(trip.budget, 25000.0)
        self.assertEqual(trip.currency, "INR")
        self.assertIn("beaches", trip.interests)
        self.assertIn("food", trip.interests)
        self.assertEqual(trip.pace, "balanced")
        self.assertEqual(trip.group_size, 2)

        validation = validate_trip_request(trip)
        self.assertTrue(validation["valid"])

    def test_missing_destination_requires_follow_up(self):
        trip = parse_trip_request("Plan a 3-day trip with a budget of USD 1500")
        validation = validate_trip_request(trip)

        self.assertFalse(validation["valid"])
        self.assertIn("destination", validation["missing_fields"])
        self.assertTrue(validation["requires_follow_up"])


if __name__ == "__main__":
    unittest.main()
