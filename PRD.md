# Product Requirements Document: AI Travel Planner Agent

**Project type:** Trainee project (LLM / AI agent)
**Difficulty:** Medium
**Status:** Draft v1
**Date:** 2026-11-16

---

## 1. Overview

### 1.1 Summary
The AI Travel Planner Agent takes a natural-language trip request (destination, dates, budget, interests) and produces a complete day-by-day itinerary with a cost breakdown. Unlike a plain chatbot, it plans multiple steps, calls external tools (weather, search, maps), checks its own output against constraints, and revises when needed.

### 1.2 Problem Statement
Planning a trip means juggling many sources: weather, attraction lists, travel times, and budget. People spend hours on this and still end up with plans that are over budget, badly routed, or ignore the weather.

### 1.3 Goals
- Generate a realistic, budget-aware itinerary from a single natural-language request.
- Demonstrate core agent concepts: tool use, planning, self-verification, and memory.
- Be simple enough to finish in about 4 weeks, with clear stretch goals.

### 1.4 Non-Goals (v1)
- Booking flights, hotels, or tickets.
- Real-time price tracking.
- Multi-user accounts or authentication.
- Mobile app.

---

## 2. Target Users

| Persona | Description | Need |
|---|---|---|
| Casual traveler | Plans 1-2 trips a year, has a rough budget | Quick, sensible itinerary without hours of research |
| Student / budget traveler | Tight budget, flexible schedule | Plans that stay within budget |
| Evaluator / reviewer | Trainer assessing the project | Clear demonstration of agent behavior |

---

## 3. User Stories

1. As a traveler, I can describe my trip in plain language and get a day-by-day plan.
2. As a traveler, I want the plan to respect my budget and show a cost breakdown.
3. As a traveler, I want the plan to adapt to the weather forecast.
4. As a traveler, I want the agent to ask me for missing details instead of guessing.
5. As a traveler, I can ask for changes ("make day 2 more relaxed") without starting over.
6. As a traveler, I can save a trip and my preferences for later.

---

## 4. Functional Requirements

### 4.1 Input Parsing
- **FR-1:** Accept free-text requests and extract structured fields: destination, start date, number of days, budget, currency, interests, group size, pace (relaxed / balanced / packed).
- **FR-2:** If required fields (destination, number of days, budget) are missing, ask a follow-up question before planning.
- **FR-3:** Validate extracted data (e.g., days > 0, budget > 0, date not in the past).

### 4.2 Tool Use
- **FR-4:** Fetch the weather forecast for the destination and dates (e.g., Open-Meteo API).
- **FR-5:** Search the web for attractions, restaurants, and events matching the user's interests.
- **FR-6:** Get distances and travel times between places (maps/places API or an approximation).
- **FR-7:** Calculate and track costs (stay, food, transport, activities) with a budget calculator tool.
- **FR-8:** The LLM decides which tools to call and in what order (function calling).

### 4.3 Planning
- **FR-9:** Group nearby places into the same day to minimize travel time.
- **FR-10:** Adjust activities to the forecast (outdoor on clear days, indoor on rainy days).
- **FR-11:** Respect the pace setting (max activities per day: relaxed 2-3, balanced 3-4, packed 5+).
- **FR-12:** Include meal suggestions and rest time.

### 4.4 Self-Verification
- **FR-13:** After drafting, run a check step that verifies:
  - Total estimated cost is within budget.
  - No day exceeds the pace limit.
  - Travel time between consecutive stops is realistic.
- **FR-14:** If any check fails, the agent revises the plan (max 3 revision loops) and notes what changed.

### 4.5 Output
- **FR-15:** Present a day-by-day itinerary with time slots, place names, short descriptions, and estimated costs.
- **FR-16:** Include a budget summary table (category totals and remaining budget).
- **FR-17:** Include a weather summary per day.

### 4.6 Conversation and Editing
- **FR-18:** Support follow-up edits in the same session (swap activity, change pace, adjust budget) without regenerating everything.

### 4.7 Memory and Persistence
- **FR-19:** Save finished trips (JSON) and reload them.
- **FR-20:** Store user preferences (interests, pace, usual budget range) and reuse them as defaults.

### 4.8 Stretch Features (post-v1)
- Export itinerary to PDF.
- Export to Google Calendar (.ics).
- Compare two destinations side by side.
- Multi-city trips.

---

## 5. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Performance | Full itinerary in under 60 seconds for a 5-day trip |
| Reliability | Graceful fallback if a tool/API fails (use cached or LLM-only suggestion and flag it) |
| Accuracy | Clearly label estimates; never present invented prices as exact |
| Cost | Stay within a low LLM/API budget (cap tokens, cache repeat lookups) |
| Security | API keys in environment variables, never committed to the repo |
| Usability | Clean, readable output; clear error messages |
| Maintainability | Modular code: separate tools, agent loop, and UI |

---

## 6. System Design

### 6.1 Agent Loop
```
User request
   -> Parse + validate (LLM, structured JSON)
   -> Missing info? -> Ask user
   -> Plan: decide tools to call (LLM function calling)
   -> Execute tools (weather, search, maps, budget)
   -> Draft itinerary
   -> Verify (budget, pace, travel time)
   -> Fail? -> Revise (max 3 loops)
   -> Final itinerary + budget summary
   -> Save trip / handle edits
```

### 6.2 Components
- **Agent core:** the loop above, with conversation state.
- **Tools:** weather, search, maps, budget calculator (each a function with a JSON schema).
- **Verifier:** rule-based checks plus an LLM review of the plan.
- **Storage:** local JSON files (or SQLite) for trips and preferences.
- **UI:** Streamlit or Gradio chat interface.

### 6.3 Suggested Tech Stack
- **Language:** Python 3.10+
- **LLM:** any API with tool/function calling
- **UI:** Streamlit or Gradio
- **APIs:** Open-Meteo (weather), a search API, a maps/places API
- **Storage:** JSON or SQLite
- **Framework:** plain function calling first; LangGraph optional later

### 6.4 Example Data Schema (trip)
```json
{
  "destination": "Goa",
  "start_date": "2026-12-10",
  "days": 4,
  "budget": 25000,
  "currency": "INR",
  "interests": ["beaches", "food"],
  "pace": "balanced",
  "itinerary": [
    {
      "day": 1,
      "weather": "Sunny, 30C",
      "stops": [
        {"time": "09:00", "name": "Example Beach", "cost": 0, "notes": "..."}
      ],
      "day_cost": 2500
    }
  ],
  "total_cost": 23800
}
```

---

## 7. Milestones

| Week | Deliverable |
|---|---|
| 1 | Prompt design and structured output. LLM-only itinerary generation, input parsing, basic CLI |
| 2 | Tool integration: weather and search via function calling |
| 3 | Budget calculator, verification step, self-revision loop |
| 4 | UI, saved trips and preferences, testing, demo, documentation |

---

## 8. Success Metrics

- **Constraint adherence:** at least 90% of generated itineraries are within budget after verification.
- **Completeness:** every itinerary includes all days, costs, and weather notes.
- **Tool use:** the agent calls the right tools for each request (tracked in logs).
- **Latency:** 5-day itinerary in under 60 seconds.
- **Test set:** 10 sample requests (varied destinations and budgets) all produce valid output.
- **User feedback:** at least 3 testers rate the plan "usable" or better.

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LLM hallucinates places or prices | Wrong plans | Ground suggestions in search results; label estimates; verify names via places API |
| API rate limits or downtime | Agent fails | Retries, caching, fallback behavior |
| Scope creep | Missed deadline | Lock v1 scope; stretch goals only after week 4 |
| Cost of LLM calls | Budget overrun | Token caps, caching, smaller model for parsing |
| Ambiguous user input | Poor plans | Follow-up questions and validation |

---

## 10. Testing Plan

- **Unit tests:** parsing, budget calculator, tool wrappers (with mocked APIs).
- **Integration tests:** full agent run on 10 sample prompts.
- **Edge cases:** very low budget, 1-day trip, missing fields, unknown destination, API failure.
- **Manual review:** read each sample itinerary for realism.

---

## 11. Open Questions

1. Which LLM API and model will be used?
2. Which search and maps APIs fit the free-tier limits?
3. Should v1 support multiple currencies or just one?
4. UI choice: Streamlit or Gradio?
5. Is a live demo required for evaluation?

---

## 12. Appendix: Sample Prompts for Testing

1. "4 days in Goa, 25,000 INR, beaches and food, December."
2. "Weekend in Jaipur, relaxed pace, love history, budget 12,000."
3. "7 days in Kerala for 2 people, 60,000 INR, backwaters and hiking."
4. "1 day in Mumbai on a very tight budget of 1,500."
5. "Plan a trip." (should trigger follow-up questions)
