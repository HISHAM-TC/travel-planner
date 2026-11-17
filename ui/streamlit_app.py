from __future__ import annotations

import streamlit as st

from app.ui import (
    apply_follow_up_edit,
    build_chat_session,
    list_saved_trips,
    load_saved_trip_session,
)

st.set_page_config(page_title="AI Travel Planner", page_icon="✈️", layout="wide")
st.title("AI Travel Planner")
st.caption("Create a sourced itinerary with clear budget and data limitations.")

if "planner_session" not in st.session_state:
    st.session_state.planner_session = None

with st.sidebar:
    st.subheader("Saved trips")
    saved_trips = list_saved_trips()
    options = {
        f"{trip.get('destination') or 'Unknown'} · {trip.get('days') or '?'} days · {str(trip.get('id'))[:8]}": str(trip.get("id"))
        for trip in reversed(saved_trips)
    }
    if options:
        selected_label = st.selectbox("Load a trip", list(options))
        if st.button("Load selected trip"):
            st.session_state.planner_session = load_saved_trip_session(options[selected_label])
    else:
        st.caption("No saved trips yet.")

with st.form("trip_form"):
    request_text = st.text_area(
        "Describe your trip",
        placeholder="4 days in Goa, 25000 INR, beaches and food",
        height=120,
    )
    submitted = st.form_submit_button("Plan my trip")

if submitted:
    if not request_text.strip():
        st.error("Enter a trip request first.")
    else:
        with st.spinner("Checking details and gathering available travel data..."):
            st.session_state.planner_session = build_chat_session(request_text)

session = st.session_state.planner_session
if session:
    result = session["itinerary_output"]
    if result["status"] == "needs_follow_up":
        st.info(result["validation"]["follow_up_question"])
    else:
        itinerary = result["itinerary"]
        st.success(f"Plan status: {result['status']}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Destination", itinerary["destination"])
        col2.metric("Days", itinerary["days"])
        col3.metric("Budget", f"{itinerary['currency']} {itinerary['budget']:,.2f}")

        st.subheader("Verification")
        st.write(result["verification"]["summary"])
        st.write(f"Budget status: **{result['verification']['budget_status']}**")
        if result["verification"]["warnings"]:
            for warning in result["verification"]["warnings"] + itinerary.get("data_warnings", []):
                st.warning(warning)
        if result["verification"]["issues"]:
            st.error(result["verification"]["issues"])

        st.subheader("Budget summary")
        st.dataframe(
            [
                {"Item": name.replace("_", " ").title(), "Amount": value, "Currency": itinerary["currency"]}
                for name, value in itinerary["budget_summary"]["category_allocations"].items()
            ],
            hide_index=True,
        )
        st.caption(itinerary["budget_summary"]["allocation_note"])
        st.write(
            f"Known priced items: {itinerary['total_estimated_cost']:,.2f} {itinerary['currency']} · "
            f"Unpriced stops: {itinerary['budget_summary']['unpriced_items']} · "
            f"Budget remaining after known costs: {itinerary['remaining_budget']:,.2f} {itinerary['currency']}"
        )

        st.subheader("Day-by-day itinerary")
        for day in itinerary["days_plan"]:
            with st.expander(f"Day {day['day']} · {day['date'] or 'date not specified'}"):
                st.write(f"Weather: {day['weather']}")
                if day.get("temperature_range"):
                    st.write(f"Temperature: {day['temperature_range']}")
                if day.get("notes"):
                    st.info(day["notes"])
                for stop in day["stops"]:
                    cost = (
                        f"{stop['cost_estimate']:,.2f} {itinerary['currency']}"
                        if stop["cost_estimate"] is not None
                        else "price unavailable"
                    )
                    st.markdown(f"- **{stop['time']} — {stop['name']}** ({stop['category']}) · {cost}")
                    st.caption(stop["notes"])
                st.write(f"Known day costs: {day['estimated_day_cost']:,.2f} {itinerary['currency']}")

        st.subheader("Edit this trip")
        with st.form("edit_form"):
            edit_text = st.text_input(
                "Follow-up edit",
                placeholder="Make day 2 more relaxed, reduce budget to 20000 INR, remove a stop, or replace A with B",
            )
            edit_submitted = st.form_submit_button("Apply edit")
        if edit_submitted:
            try:
                st.session_state.planner_session = apply_follow_up_edit(session, edit_text)
                st.rerun()
            except (ValueError, KeyError) as exc:
                st.error(str(exc))

st.caption("External results and travel-time estimates may be incomplete; check provider warnings and verify details before travel.")
