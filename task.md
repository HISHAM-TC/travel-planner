# AI Travel Planner Agent — Execution Plan

## 1. Project Goal
Build a working v1 travel-planning agent that accepts a natural-language trip request, gathers relevant travel data from tools, generates a day-by-day itinerary within budget, verifies the result, and presents it through a simple UI with saved trip preferences.

This plan follows the requirements in PRD.md and is structured to finish in approximately 4 weeks.

---

## 2. Delivery Outcome
By the end of the project, the app should:
- parse a free-text trip request into structured fields
- ask follow-up questions when required inputs are missing
- fetch weather, attraction, and travel information using external tools
- generate a multi-day itinerary with estimated costs and weather summaries
- validate budget, pace, and travel logic before presenting the final result
- support at least basic saved trips and user preferences
- run from a simple local interface (Streamlit/Gradio or CLI prototype)

---

## 3. Execution Plan

### Phase 1 — Project Setup and Requirements Foundation

#### Step 1: Set up the project skeleton
- Create the repository structure: app/, agents/, tools/, models/, storage/, tests/
- Initialize Python environment and dependencies
- Define .env handling for API keys
- Create a README and project config

#### Step 2: Define data contracts
- Finalize input schema for trip requests
- Define output schema for itinerary, cost breakdown, and weather data
- Decide how user preferences and saved trips will be stored
- Confirm validation rules for days, budget, dates, and pace

#### Step 3: Build the first prompt and structured-output contract
- Write a prompt template for request parsing
- Force structured JSON output for destination, budget, dates, interests, etc.
- Add basic validation logic for malformed input
- Test with 5–10 sample prompts

#### Step 4: Create a minimal working CLI flow
- Accept manual input from terminal
- Display parsed request info
- Show a placeholder “generated itinerary” response
- Ensure the flow can later be replaced by the UI without changing core logic

Deliverable: A working request parser and CLI shell with no external tool calls yet.

---

### Phase 2 — Tool Integration

#### Step 5: Implement weather tool
- Integrate Open-Meteo or another weather API
- Build a function wrapper that accepts destination and date range
- Validate missing weather data and provide fallback behavior

#### Step 6: Implement search and attraction tool
- Add a web-search or travel data source for attractions, restaurants, and events
- Filter results based on user interests and destination
- Normalize results into a simple internal format

#### Step 7: Implement distance/travel-time tool
- Add a simple maps or travel-time approximation layer
- Estimate travel duration between nearby stops
- Use this to build day clustering logic later

#### Step 8: Implement budget calculator tool
- Define categories: stay, food, transport, activities, local travel
- Create a cost estimator based on trip length, destination, and pace
- Return category totals and remaining budget

#### Step 9: Connect tools to the LLM via function calling
- Add tool definitions in the agent loop
- Allow the LLM to decide which tool should be called and when
- Log each tool call and output in a structured trace

Deliverable: The agent can gather weather, attraction, travel, and budget information for a trip request.

---

### Phase 3 — Planning and Itinerary Generation

#### Step 10: Build a planner prompt
- Generate a day-by-day itinerary with time slots and venue suggestions
- Enforce pace rules: relaxed, balanced, packed
- Include meal/rest suggestions and nearby clustering
- Use weather to prefer outdoor or indoor activities

#### Step 11: Cluster stops by day
- Group locations in geographic proximity to reduce travel time
- Avoid unrealistic back-and-forth movement
- Automatically spread activities across the trip based on destination and day count

#### Step 12: Draft the first itinerary
- Create an itinerary JSON structure with costs and weather notes
- Include route estimates and budget summaries
- Label all values as estimates, not exact prices

Deliverable: A first-pass itinerary is generated for a valid trip request.

---

### Phase 4 — Verification and Self-Revision Loop

#### Step 13: Create a verifier module
- Check total cost <= budget
- Check daily activity count against pace limits
- Check travel times between consecutive stops
- Ensure all required fields are present

#### Step 14: Add revision loop
- If verification fails, call an LLM review step to revise the itinerary
- Limit revision attempts to 3 loops
- Save the reason for each revision in the trace

#### Step 15: Generate final plan output
- Produce final itinerary with a budget summary table
- Include weather summary for each day
- Return the final plan in a clear, readable format for the UI

Deliverable: The agent self-checks its output and produces a corrected final itinerary when needed.

---

### Phase 5 — UI, Storage, and Conversation Flow

#### Step 16: Build the interface
- Use Streamlit or Gradio for a simple chat-style UI
- Add text box for trip requests and follow-up edits
- Show itinerary output in a readable card/table format

#### Step 17: Add persistence for trips
- Save completed itineraries to local JSON or SQLite
- Allow user to reload a previous trip from storage
- Keep trip metadata: destination, dates, budget, created_at

#### Step 18: Add preference memory
- Store user interests, pace, preferred currency, and usual budget range
- Reuse those as default values for future trips
- Make preferences editable in the UI if needed

#### Step 19: Support in-session edits
- Allow follow-up requests like “make day 2 more relaxed” or “reduce budget”
- Only modify the relevant portion of the trip rather than regenerating everything from scratch

Deliverable: The app supports a reusable planning experience with saved trips and user preferences.

---

### Phase 6 — Quality, Testing, and Demo Readiness

#### Step 20: Write unit tests
- Test request parsing and validation
- Test budget calculations
- Test tool wrappers with mocked responses
- Test verifier logic for budget and pace violations

#### Step 21: Write integration tests
- Run a complete trip request flow end-to-end
- Verify the final itinerary respects the requested constraints
- Simulate missing input, tool failures, and revision triggers

#### Step 22: Demo polish
- Improve output formatting and readability
- Add helpful fallback messaging when APIs fail
- Test with 10 sample trip scenarios

#### Step 23: Final validation
- Confirm latency target: <60 seconds for a 5-day itinerary
- Check 90%+ rule compliance for tested examples
- Prepare demo presentation and user instructions

Deliverable: Project is ready for evaluation and presentation.

---

## 4. Recommended Order of Execution
1. Setup project and schema
2. Parse and validate input
3. Build weather/search/budget tools
4. Connect tools to the agent
5. Generate itinerary draft
6. Add verifier and self-revision loop
7. Build UI and persistence
8. Run tests and demo validation

---

## 5. Risk Control Plan
- Keep v1 scope tight; avoid stretch features until the core flow works
- Use cached or fallback values when APIs fail
- Label all cost estimates clearly as approximations
- Limit LLM token usage and tool calls during early builds
- Validate with sample prompts before polishing UI

---

## 6. Definition of Done
The project is complete when:
- a valid trip prompt can be converted into a structured request
- the agent can gather required tool data and generate a multi-day itinerary
- the itinerary is checked against budget and pace constraints
- revisions happen automatically when checks fail
- the final result is displayed in a usable interface
- trips and preferences can be stored and reloaded
- tests cover the main behaviors and the demo works reliably

---

## 7. Suggested Sprint Breakdown

### Week 1
- environment setup
- prompt design
- structured parsing and validation
- CLI prototype

### Week 2
- weather + search + maps tools
- first itinerary generation
- tool integration and logging

### Week 3
- budget calculator
- revision loop and self-verification
- output formatting and budget summary

### Week 4
- UI polish
- saved trips and preferences
- testing, bug fixing, and demo prep

---

## 8. Immediate Next Action
Start by creating the project structure and building the request parser + validation logic before integrating any external APIs. This gives the team a clean foundation and makes the later tool and planner work easier to test.
