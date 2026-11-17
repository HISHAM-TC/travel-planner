import unittest

from app.models import TripRequest
from app.verifier import revise_itinerary_if_needed, verify_itinerary


class VerifierTests(unittest.TestCase):
    def test_verify_itinerary_detects_budget_overrun(self):
        trip = TripRequest(destination="Goa", days=3, budget=5000, currency="INR", pace="balanced")
        itinerary = {
            "days_plan": [
                {"estimated_day_cost": 2500, "stops": [{"time": "09:00", "cost_estimate": 1200}, {"time": "12:00", "cost_estimate": 1300}]},
                {"estimated_day_cost": 2500, "stops": [{"time": "09:00", "cost_estimate": 1100}, {"time": "12:00", "cost_estimate": 1400}]},
                {"estimated_day_cost": 2500, "stops": [{"time": "09:00", "cost_estimate": 900}, {"time": "12:00", "cost_estimate": 1600}]},
            ],
            "total_estimated_cost": 7500,
        }
        result = verify_itinerary(trip, itinerary)
        self.assertFalse(result["valid"])
        self.assertIn("budget_overrun", [issue["type"] for issue in result["issues"]])

    def test_revision_loop_reduces_over_budget_itinerary(self):
        trip = TripRequest(destination="Goa", days=2, budget=4000, currency="INR", pace="relaxed")
        itinerary = {
            "days_plan": [
                {"estimated_day_cost": 3000, "stops": [{"time": "09:00", "cost_estimate": 1200}, {"time": "11:00", "cost_estimate": 1300}, {"time": "14:00", "cost_estimate": 500}, {"time": "18:00", "cost_estimate": 600}]},
                {"estimated_day_cost": 2000, "stops": [{"time": "09:00", "cost_estimate": 900}, {"time": "12:00", "cost_estimate": 1100}]},
            ],
            "total_estimated_cost": 5000,
        }
        result = revise_itinerary_if_needed(trip, itinerary)
        self.assertIn(result["status"], {"finalized", "needs_review"})
        self.assertIsInstance(result["verification"]["issues"], list)


if __name__ == "__main__":
    unittest.main()
