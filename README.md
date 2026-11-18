# AI Travel Planner Agent

This project is the initial implementation of the Phase 1 foundation for the AI Travel Planner Agent described in `PRD.md`.

## Phase 1 goals
- create the project structure
- define the trip request schema
- build parsing and validation helpers
- create a working CLI prototype
- prepare the foundation for tool integration and itinerary generation

## Project layout
- `app/`: core application code
- `agents/`: agent and planner logic
- `tests/`: validation tests

## Quick start
```bash
python -m app.cli "Plan a 4-day trip to Goa with a budget of INR 25000 for 2 people. I like beaches and food. Start on 2026-12-10."
```

## Demo flow
```bash
python main.py "Plan a 4-day trip to Goa with a budget of INR 25000 for 2 people. I like beaches and food. Start on 2026-12-10 and keep it balanced."
```
This generates a validated itinerary, stores the trip in local JSON, and saves the user preferences for future reuse.

## Local web planner
```bash
python local_app.py
```
Open `http://127.0.0.1:8000` to plan a trip with the structured form and view its saved itinerary.
Saved trip result pages also provide a PDF download. PDFs use ReportLab and locally cached Wikimedia/optional stock images, with generated placeholders when no suitable licensed image is available.

## Public hosting (Render)
1. Push this project to a GitHub repository. Do not commit your `.env` file or API keys.
2. In Render, create a **New Web Service** and connect the repository.
3. Set the build command to `pip install -r requirements.txt` and the start command to `python local_app.py`.
4. Add the environment variable `HOST` with value `0.0.0.0`. Render supplies `PORT` automatically.
5. If you want AI-generated planning, add `OPENAI_API_KEY` in Render's environment settings. Keep it secret; the app can also use its local fallback without it.
6. Deploy and open the `onrender.com` URL Render provides.

The public app currently has no sign-in, so anyone with its URL can submit trips. On Render's free service, local files are not durable across restarts or redeploys; saved trips and preferences may be lost. Configure persistent storage and set `TRAVEL_DATA_DIR` to its mount path if those records need to survive. Avoid storing sensitive personal information.

## Notes
This v1 implementation is intentionally lightweight: it uses local fallback data and approximate travel estimates, but it demonstrates the core agent behaviors: parsing, tool use, planning, verification, and persistence.
