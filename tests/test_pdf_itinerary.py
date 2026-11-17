from __future__ import annotations

import base64
import io
import re
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import images
from pdf_itinerary import _trip_facts, build_itinerary_pdf, safe_filename


class PdfItineraryTests(unittest.TestCase):
    def test_trip_glance_includes_all_selected_planner_options(self):
        trip = {
            "destination": "Goa",
            "areas": ["North Goa"],
            "budget_mode": "per_person",
            "flexible_dates": True,
            "food_styles": ["Seafood", "Cafes"],
            "local_transport": ["Rented scooter"],
            "stay_type": "Resort",
            "diet": "Vegetarian",
            "arrival_mode": "Train",
            "origin": "Mumbai",
        }
        itinerary = {
            "days": 4,
            "pace": "balanced",
            "planning_preferences": {"group_type": "Couple"},
        }

        facts = dict(_trip_facts(trip, itinerary, ["beaches", "food"], {}))

        self.assertEqual(facts["Areas"], "North Goa")
        self.assertEqual(facts["Budget basis"], "Per person")
        self.assertEqual(facts["Date flexibility"], "Flexible by up to 2 days")
        self.assertEqual(facts["Food styles"], "Seafood, Cafes")
        self.assertEqual(facts["Stay"], "Resort")
        self.assertEqual(facts["Local transport"], "Rented scooter")
        self.assertEqual(facts["Diet"], "Vegetarian")
        self.assertEqual(facts["Arrival"], "Train")
        self.assertEqual(facts["Travelling from"], "Mumbai")

    def test_trip_glance_reads_selected_options_from_nested_itinerary(self):
        planning = {
            "areas": ["Panjim"],
            "budget_mode": "total",
            "flexible_dates": False,
            "food_styles": ["Local cuisine"],
        }
        facts = dict(_trip_facts({}, {"days": 2}, [], planning))

        self.assertEqual(facts["Areas"], "Panjim")
        self.assertEqual(facts["Budget basis"], "Total for the trip")
        self.assertEqual(facts["Date flexibility"], "Fixed dates")
        self.assertEqual(facts["Food styles"], "Local cuisine")

    def test_pdf_contains_cover_budget_one_page_per_day_and_credits(self):
        placeholder = images._placeholder("Goa")
        trip = {
            "id": "test-trip",
            "destination": "Goa",
            "start_date": "2026-12-10",
            "days": 2,
            "budget": 25000,
            "currency": "INR",
            "group_size": 2,
            "travelers": {"adults": 2, "children": 0},
            "group_type": "Couple",
            "interests": ["beaches", "food"],
            "pace": "balanced",
            "stay_type": "Budget hotel",
            "local_transport": ["Rented scooter"],
            "diet": "Vegetarian",
            "budget_split": {"stay": 8750, "food": 6250, "transport": 5000, "activities": 3750, "misc": 1250},
            "notes": "Early start",
            "itinerary": {
                "status": "finalized",
                "itinerary": {
                    "destination": "Goa",
                    "days": 2,
                    "currency": "INR",
                    "budget": 25000,
                    "planning_preferences": {"group_type": "Couple"},
                    "budget_summary": {},
                    "data_warnings": ["Weather data was unavailable."],
                    "days_plan": [
                        {
                            "day": 1,
                            "date": "2026-12-10",
                            "weather": "Clear sky",
                            "temperature_range": "24°C to 30°C",
                            "stops": [
                                {
                                    "name": "Anjuna Beach",
                                    "time": "09:00",
                                    "notes": "Verify opening hours.",
                                    "cost_estimate": None,
                                }
                            ],
                            "estimated_day_cost": 0,
                        },
                        {
                            "day": 2,
                            "date": "2026-12-11",
                            "weather": "Unavailable",
                            "stops": [],
                            "estimated_day_cost": 0,
                        },
                    ],
                },
                "tool_data": {},
            },
        }

        with patch("pdf_itinerary.images.get_relevant_image", return_value=placeholder):
            pdf_data = build_itinerary_pdf(trip)

        self.assertTrue(pdf_data.startswith(b"%PDF-"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", pdf_data)), 6)

    def test_empty_legacy_trip_still_gets_pdf_and_interest_images(self):
        placeholder = images._placeholder("beaches")
        trip = {
            "id": "empty-trip",
            "destination": "Kerala",
            "days": 2,
            "budget": 12000,
            "itinerary": {},
            "interests": ["beaches", "food"],
        }
        with patch("pdf_itinerary.images.get_relevant_image", return_value=placeholder) as lookup:
            pdf_data = build_itinerary_pdf(trip)
        self.assertTrue(pdf_data.startswith(b"%PDF-"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", pdf_data)), 6)
        self.assertEqual(
            {call.args[0] for call in lookup.call_args_list},
            {"Kerala", "beaches", "food"},
        )

    def test_offline_image_lookup_uses_valid_cached_placeholder(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            with (
                patch.object(images, "CACHE_DIR", Path(cache_dir)),
                patch(
                    "images._request_json",
                    side_effect=urllib.error.URLError("offline"),
                ) as request_json,
            ):
                first = images.get_relevant_image("NoSuchPlace", "NoSuchDestination")
                second = images.get_relevant_image("NoSuchPlace", "NoSuchDestination")

            self.assertEqual(first["source"], "Generated placeholder")
            self.assertEqual(first["image_base64"], second["image_base64"])
            self.assertEqual(request_json.call_count, 2)
            image_data = base64.b64decode(first["image_base64"])
            with Image.open(io.BytesIO(image_data)) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertLessEqual(image.width, 1200)

    def test_pdf_build_completes_when_every_image_source_is_offline(self):
        trip = {
            "destination": "Goa",
            "days": 1,
            "interests": ["beaches", "food"],
            "itinerary": {"itinerary": {"days_plan": [{"day": 1, "stops": []}]}},
        }
        with (
            tempfile.TemporaryDirectory() as cache_dir,
            patch.object(images, "CACHE_DIR", Path(cache_dir)),
            patch("images._request_json", side_effect=urllib.error.URLError("offline")),
        ):
            pdf_data = build_itinerary_pdf(trip)

        self.assertTrue(pdf_data.startswith(b"%PDF-"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", pdf_data)), 5)

    def test_download_filename_is_a_safe_slug(self):
        self.assertEqual(safe_filename("Panjim & Goa!"), "panjim-goa")


if __name__ == "__main__":
    unittest.main()
