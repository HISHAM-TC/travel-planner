from __future__ import annotations

import json
import html
import logging
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.ui import build_chat_session, load_saved_trip_session
import images
from pdf_itinerary import build_itinerary_pdf, safe_filename
from storage.json_store import load_trip

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEFAULT_REQUEST = "Plan a 4-day trip to Goa with a budget of INR 25000 for 2 people. I like beaches and food. Start on 2026-12-10 and keep it balanced."
PLANNER_TEMPLATE = Path(__file__).resolve().parent / "templates" / "planner.html"
RESULT_TEMPLATE = Path(__file__).resolve().parent / "templates" / "result.html"
logger = logging.getLogger(__name__)


def render_form(request_value: str = DEFAULT_REQUEST) -> str:
    escaped = html.escape(request_value)
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>AI Travel Planner</title>
      <style>
        body {{ font-family: Arial, sans-serif; max-width: 960px; margin: 40px auto; padding: 20px; }}
        textarea {{ width: 100%; min-height: 120px; font-size: 16px; }}
        button {{ background: #2563eb; color: white; border: none; padding: 10px 18px; font-size: 16px; border-radius: 6px; cursor: pointer; }}
        pre {{ background: #f3f4f6; padding: 16px; border-radius: 8px; white-space: pre-wrap; }}
      </style>
    </head>
    <body>
      <h1>AI Travel Planner</h1>
      <form method="post">
        <label for="request">Trip request</label><br />
        <textarea name="request" id="request">{escaped}</textarea><br /><br />
        <button type="submit">Plan my trip</button>
      </form>
    </body>
    </html>
    """


def render_result(request_text: str, session: dict) -> str:
    _attach_result_images(session)
    saved_trip = session.get("saved_trip") or {}
    trip_id = saved_trip.get("id")
    pdf_url = "/trips/" + urllib.parse.quote(str(trip_id), safe="") + "/pdf" if trip_id else "#"
    safe_json = json.dumps(session, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = RESULT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("__TRIP_JSON__", safe_json).replace("__PDF_URL__", html.escape(pdf_url, quote=True))


def _attach_result_images(session: dict) -> None:
    """Attach the PDF image-service assets to the result page without persisting them."""
    output = session.get("itinerary_output") or {}
    itinerary = output.get("itinerary") or {}
    days = itinerary.get("days_plan") or []
    saved_trip = session.get("saved_trip") or {}
    destination = str(
        itinerary.get("destination")
        or session.get("parsed_request", {}).get("destination")
        or saved_trip.get("destination")
        or ""
    )
    if not destination:
        return

    requests = {destination.casefold(): (destination, destination)}
    for day in days:
        for stop in day.get("stops", []) if isinstance(day, dict) else []:
            if isinstance(stop, dict) and stop.get("name"):
                name = str(stop["name"])
                requests.setdefault(name.casefold(), (name, destination))

    with ThreadPoolExecutor(max_workers=min(8, len(requests))) as executor:
        futures = {
            executor.submit(images.get_relevant_image, place, place_destination): key
            for key, (place, place_destination) in requests.items()
        }
        assets = {}
        for future in as_completed(futures):
            key = futures[future]
            try:
                assets[key] = future.result()
            except Exception:
                logger.exception("Could not prepare result-page image for %s", requests[key][0])

    hero_asset = assets.get(destination.casefold())
    if hero_asset:
        session["hero_image_url"] = "data:image/jpeg;base64," + hero_asset["image_base64"]
        session["hero_image_credit"] = _image_credit(hero_asset)

    for day in days:
        for stop in day.get("stops", []) if isinstance(day, dict) else []:
            if not isinstance(stop, dict) or not stop.get("name"):
                continue
            asset = assets.get(str(stop["name"]).casefold())
            if asset:
                stop["image_url"] = "data:image/jpeg;base64," + asset["image_base64"]
                stop["image_credit"] = _image_credit(asset)
                stop["wiki_title"] = asset.get("title", str(stop["name"]))


def _image_credit(asset: dict[str, str]) -> str:
    details = [
        asset.get("title"),
        asset.get("author"),
        asset.get("license"),
        asset.get("source"),
    ]
    return " — ".join(value for value in details if value)


class PlannerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlsplit(self.path)
        if parsed_url.path == "/":
            page = PLANNER_TEMPLATE.read_text(encoding="utf-8")
            self._send_response(200, page, "text/html; charset=utf-8")
        elif parsed_url.path == "/result":
            query = urllib.parse.parse_qs(parsed_url.query)
            trip_id = query.get("trip_id", [""])[0]
            try:
                session = load_saved_trip_session(trip_id)
                self._send_response(
                    200,
                    render_result(session.get("request", ""), session),
                    "text/html; charset=utf-8",
                )
            except KeyError as exc:
                self._send_response(
                    404,
                    f"<html><body><h1>Saved trip not found</h1><p>{html.escape(str(exc))}</p><p><a href='/'>Back to planner</a></p></body></html>",
                    "text/html; charset=utf-8",
                )
        elif re.fullmatch(r"/trips/[^/]+/pdf", parsed_url.path):
            trip_id = urllib.parse.unquote(parsed_url.path[len("/trips/") : -len("/pdf")])
            self._send_trip_pdf(trip_id)
        else:
            self._send_response(404, "Not found", "text/plain; charset=utf-8")

    def _send_trip_pdf(self, trip_id: str):
        try:
            trip = load_trip(trip_id)
        except KeyError:
            self._send_response(404, "Saved trip not found.", "text/plain; charset=utf-8")
            return

        try:
            pdf_data = build_itinerary_pdf(trip)
        except Exception:
            logger.exception("Could not build itinerary PDF for saved trip %s", trip_id)
            self._send_response(500, "Could not prepare this itinerary PDF.", "text/plain; charset=utf-8")
            return

        destination = safe_filename(str(trip.get("destination") or "trip"))
        start_date = safe_filename(str(trip.get("start_date") or "undated"))
        filename = f"{destination}-{start_date}-itinerary.pdf"
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(pdf_data)))
        self.end_headers()
        self.wfile.write(pdf_data)

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/plan":
            self._plan_structured_request()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length).decode("utf-8", errors="ignore")
        form_data = urllib.parse.parse_qs(raw)
        request_text = form_data.get("request", [DEFAULT_REQUEST])[0].strip()

        try:
            session = build_chat_session(request_text)
            page = render_result(request_text, session)
            status = 200
        except (ValueError, OSError) as exc:
            page = f"<html><body><h1>Could not plan trip</h1><p>{html.escape(str(exc))}</p></body></html>"
            status = 500
        self._send_response(status, page, "text/html; charset=utf-8")

    def _plan_structured_request(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 1_000_000:
                self._send_json(413, {"error": "Request body is too large."})
                return
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("The planner request must be a JSON object.")
            request_text = payload.get("request", "")
            if not isinstance(request_text, str):
                raise ValueError("The request field must be a string.")
            session = build_chat_session(request_text, payload)
            result = session["itinerary_output"]
            if result["status"] != "finalized" or not session.get("saved_trip"):
                message = (
                    result.get("validation", {}).get("follow_up_question")
                )
                if not message:
                    itinerary = result.get("itinerary") or {}
                    warnings = itinerary.get("data_warnings") or []
                    issues = (result.get("verification") or {}).get("issues") or []
                    details = warnings[:3] + [
                        issue.get("message", "")
                        for issue in issues[:3]
                        if issue.get("message")
                    ]
                    message = "The planner could not complete this trip request."
                    if details:
                        message += " " + " ".join(details)
                self._send_json(422, {"error": message, "result": result})
                return
            trip_id = session["saved_trip"]["id"]
            self._send_json(
                200,
                {
                    "saved_trip_id": trip_id,
                    "redirect_url": "/result?trip_id="
                    + urllib.parse.quote(str(trip_id), safe=""),
                },
            )
        except (ValueError, OSError, TypeError) as exc:
            self._send_json(400, {"error": str(exc)})

    def _send_json(self, status: int, data: dict):
        self._send_response(
            status,
            json.dumps(data, ensure_ascii=False),
            "application/json; charset=utf-8",
        )

    def _send_response(self, status: int, body: str, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), PlannerHandler)
    display_host = "127.0.0.1" if HOST == "0.0.0.0" else HOST
    print(f"Travel planner running at http://{display_host}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local app...")
    finally:
        server.server_close()
