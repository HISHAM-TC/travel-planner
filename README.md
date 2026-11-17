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

## Notes
This v1 implementation is intentionally lightweight: it uses local fallback data and approximate travel estimates, but it demonstrates the core agent behaviors: parsing, tool use, planning, verification, and persistence.
