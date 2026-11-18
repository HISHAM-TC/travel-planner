from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.ui import build_chat_session, render_console_response

app = FastAPI(title="AI Travel Planner Agent")


class TripRequest(BaseModel):
    request: str


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/plan")
def plan(body: TripRequest):
    session = build_chat_session(body.request.strip())
    output = session["itinerary_output"]

    if output["status"] == "needs_follow_up":
        return {
            "status": "needs_follow_up",
            "message": render_console_response(session),
        }
    return output
