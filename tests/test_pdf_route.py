from __future__ import annotations

import threading
import unittest
import json
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from local_app import PlannerHandler, _attach_result_images, render_result


class PdfRouteTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PlannerHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_pdf_route_returns_attachment_and_sanitized_filename(self):
        trip = {"destination": "Panjim & Goa!", "start_date": "2026-12-10"}
        with (
            patch("local_app.load_trip", return_value=trip),
            patch("local_app.build_itinerary_pdf", return_value=b"%PDF-1.4 test"),
        ):
            with urllib.request.urlopen(f"{self.base_url}/trips/trip-1/pdf") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Content-Type"], "application/pdf")
                self.assertEqual(
                    response.headers["Content-Disposition"],
                    'attachment; filename="panjim-goa-2026-12-10-itinerary.pdf"',
                )
                self.assertTrue(response.read().startswith(b"%PDF-"))

    def test_pdf_route_returns_404_for_missing_trip(self):
        with patch("local_app.load_trip", side_effect=KeyError("not found")):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(f"{self.base_url}/trips/missing/pdf")
        self.assertEqual(error.exception.code, 404)

    def test_incomplete_plan_returns_place_search_details_to_the_form(self):
        session = {
            "saved_trip": None,
            "itinerary_output": {
                "status": "needs_review",
                "itinerary": {"data_warnings": ["No beach results were found in Goa."]},
                "verification": {
                    "issues": [{"type": "empty_day", "message": "Day 1 has no verified places."}]
                },
            },
        }
        request = urllib.request.Request(
            f"{self.base_url}/plan",
            data=json.dumps({"request": "Goa", "destination": "Goa"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with patch("local_app.build_chat_session", return_value=session):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)

        payload = json.loads(error.exception.read().decode())
        self.assertEqual(error.exception.code, 422)
        self.assertIn("No beach results were found in Goa.", payload["error"])
        self.assertIn("Day 1 has no verified places.", payload["error"])

    def test_result_page_adds_download_link_without_removing_existing_links(self):
        page = render_result(
            "A saved request",
            {"saved_trip": {"id": "trip-1"}, "itinerary_output": {}},
        )
        self.assertIn('href="/trips/trip-1/pdf" download', page)
        self.assertIn('id="back" href="/">&larr; Back to planner</a>', page)
        self.assertIn("Preparing PDF...", page)
        self.assertIn('<pre id="raw"', page)
        self.assertIn('id="trip-data"', page)

    def test_result_page_safely_injects_trip_json(self):
        request = "</script><script>alert('x')</script>"
        session = {
            "request": request,
            "parsed_request": {"destination": "Goa"},
            "saved_trip": {"id": "trip-1"},
            "itinerary_output": {},
        }

        page = render_result(request, session)
        payload = page.split('id="trip-data">', 1)[1].split("</script>", 1)[0]

        self.assertNotIn("</script><script>alert", page)
        self.assertEqual(json.loads(payload)["request"], request)

    def test_result_page_attaches_shared_image_service_assets(self):
        session = {
            "parsed_request": {"destination": "Goa"},
            "saved_trip": {"destination": "Goa"},
            "itinerary_output": {
                "itinerary": {
                    "destination": "Goa",
                    "days_plan": [{"stops": [{"name": "Candolim Beach"}]}],
                }
            },
        }
        asset = {
            "image_base64": "an-image",
            "title": "Candolim Beach",
            "author": "Local source",
            "license": "Test license",
            "source": "Test source",
        }
        with patch("local_app.images.get_relevant_image", return_value=asset) as image_lookup:
            _attach_result_images(session)

        self.assertEqual(image_lookup.call_count, 2)
        self.assertTrue(session["hero_image_url"].startswith("data:image/jpeg;base64,"))
        stop = session["itinerary_output"]["itinerary"]["days_plan"][0]["stops"][0]
        self.assertEqual(stop["image_url"], session["hero_image_url"])
        self.assertIn("Test license", stop["image_credit"])
        self.assertEqual(stop["wiki_title"], "Candolim Beach")


if __name__ == "__main__":
    unittest.main()
