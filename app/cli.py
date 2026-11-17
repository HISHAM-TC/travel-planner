from __future__ import annotations

import argparse
import json

from app.ui import build_chat_session
from app.ui import render_console_response


def run_cli(request_text: str | None = None) -> int:
    text = request_text or input("Describe your trip: ").strip()
    session = build_chat_session(text)
    if session["itinerary_output"]["status"] == "needs_follow_up":
        print(render_console_response(session))
        return 1

    print(json.dumps(session["itinerary_output"], indent=2, ensure_ascii=False))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Travel Planner Agent CLI")
    parser.add_argument("request", nargs="?", help="Natural language trip description")
    args = parser.parse_args()
    raise SystemExit(run_cli(args.request))


if __name__ == "__main__":
    main()
