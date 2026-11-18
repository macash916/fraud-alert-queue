"""Alert queue: open alerts ranked by expected loss, worked in four steps (route, alert, why, decide)."""

import json

import altair as alt
import pandas as pd
import streamlit as st

import db

ROUTES = {
    "analyst_review": ("Analyst review",
                       "Payment held for you. Check the reasons and the card's other alerts, contact the customer "
                       "if needed, then decide."),
    "decline": ("Decline and block",
                "Payment declined and card blocked automatically, because the model is near-certain. "
                "Review to confirm the fraud, or reinstate a genuine customer quickly."),
    "step_up": ("In-app step-up",
                "Customer asked to confirm the payment in their banking app. Work these when the customer "
                "doesn't respond or disputes the payment."),
}

# Plain names for the audit view of the score breakdown.
FEATURE_LABELS = {
    "amt": "Payment amount", "category": "Merchant category", "hour_of_day": "Time of day",
    "amt_vs_avg": "Amount vs this card's average", "amt_vs_category_avg": "Amount vs category norm",
    "amt_sum_24h": "Spend in last 24 hours", "spend_24h_vs_daily_avg": "24-hour spend vs usual daily spend",
    "txn_count_1h": "Payments in last hour", "txn_count_24h": "Payments in last 24 hours",
    "secs_since_last": "Time since last payment", "distance_km": "Distance from home",
    "is_new_merchant": "New merchant for this card", "is_new_category": "First use of this category",
    "hour_band_share": "How usual this time of day is for the card",
    "small_txn_count_24h": "Small payments in last 24 hours", "prior_txn_count": "Length of card history",
}


ORANGE, BLUE = "#eb6834", "#2a78d6"  # project palette: towards fraud, towards genuine


def money(x: float) -> str:
    return f"${x:,.2f}"


st.title("Alert queue")
st.caption("Work the riskiest alerts first: choose a route, pick an alert, read why it was flagged, then decide.")
if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"))

summary = db.queue_summary().set_index("route")
cols = st.columns(4)
for col, (route, (label, _)) in zip(cols, ROUTES.items()):
    n = int(summary.loc[route, "open_alerts"]) if route in summary.index else 0
    col.metric(f"Open: {label.lower()}", f"{n:,}")
cols[3].metric("Expected loss in open alerts", f"${summary['open_expected_loss'].sum():,.0f}",
               help="Sum of fraud probability x amount over every open alert.")

st.subheader("Step 1 · Choose a route")
route = st.segmented_control("Route", options=list(ROUTES), default="analyst_review",
                             format_func=lambda r: ROUTES[r][0], label_visibility="collapsed") or "analyst_review"
st.caption(ROUTES[route][1])

queue = db.open_queue(route)
if queue.empty:
    st.success("Nothing open on this route.")
    st.stop()

table = pd.DataFrame({
    "Rank": range(1, len(queue) + 1),
    "Time": queue["trans_ts"],
    "Card": queue["card_ref"],
    "Merchant": queue["merchant"],
    "Amount": queue["amount_usd"],
    "Fraud probability": queue["fraud_probability"],
    "Expected loss": queue["expected_loss_usd"],
    "Main reason": queue["reason_1"],
})

st.subheader("Step 2 · Pick an alert")
st.caption(f"Ranked by expected loss (fraud probability x amount), highest first; showing the top {len(queue)}. "
           "Tick a row to open it; otherwise the top alert is shown.")
picked = st.dataframe(
    table, hide_index=True, height=320, on_select="rerun", selection_mode="single-row",
    key=f"table_{route}_{st.session_state.get('decisions_made', 0)}",
    column_config={
        "Rank": st.column_config.NumberColumn(width="small"),
        "Time": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
        "Amount": st.column_config.NumberColumn(format="dollar"),
        "Fraud probability": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "Expected loss": st.column_config.NumberColumn(format="dollar",
                                                       help="Fraud probability x amount: what the bank "
                                                            "stands to lose if this alert is fraud and missed."),
        "Main reason": st.column_config.TextColumn(width="large"),
    },
)
# The row the analyst ticked refers to the table as it was drawn on their screen, which can differ from
# the queue just re-read if someone else has worked an alert since. So the IDs shown last time are kept,
# and the chosen alert is identified by its transaction ID, never by its row position.
shown_key = f"shown_ids_{route}"
rows = picked.selection.rows
chosen = None
if rows and shown_key in st.session_state and rows[0] < len(st.session_state[shown_key]):
    chosen = st.session_state[shown_key][rows[0]]
st.session_state[shown_key] = list(queue["trans_num"])

if chosen is not None and chosen in set(queue["trans_num"]):
    alert = queue.set_index("trans_num", drop=False).loc[chosen]
else:
    if chosen is not None:
        st.warning("The alert you selected has just been worked by someone else. Showing the top alert instead.")
    alert = queue.iloc[0]

st.subheader(f"Step 3 · Understand why: card {alert['card_ref']}, {money(alert['amount_usd'])}")
st.write(f"**{alert['merchant']}**, {alert['category'].replace('_', ' ')} · "
         f"{pd.Timestamp(alert['trans_ts']):%d %b %Y, %H:%M} · Route: **{ROUTES[route][0]}**")
left, right = st.columns([1, 1], gap="large")

with left:
    a, b = st.columns(2)
    a.metric("Fraud probability", f"{alert['fraud_probability']:.1%}")
    b.metric("Expected loss", money(alert["expected_loss_usd"]),
             help="Fraud probability x amount: what the bank stands to lose if this is fraud and missed.")
    st.markdown("**Why this payment was flagged**")
    for i in (1, 2, 3):
        st.markdown(f"{i}. {alert[f'reason_{i}']}")

    history = db.card_alerts(alert["card_ref"])
    st.markdown(f"**All alerts on this card ({len(history)})**")
    outcome = history["analyst_decision"].map({"confirmed_fraud": "Confirmed fraud", "not_fraud": "Not fraud"})
    history = pd.DataFrame({"Time": history["trans_ts"], "Amount": history["amount_usd"],
                            "Outcome": outcome.fillna("Open"), "Probability": history["fraud_probability"],
                            "Merchant": history["merchant"]})
    st.dataframe(history, hide_index=True, width="stretch", height=180, column_config={
        "Time": st.column_config.DatetimeColumn(format="D MMM, HH:mm"),
        "Amount": st.column_config.NumberColumn(format="dollar"),
        "Probability": st.column_config.NumberColumn(format="percent")})

with right:
    st.markdown("**What moved the score** (for audit)")
    detail = alert["reason_detail"]
    detail = json.loads(detail) if isinstance(detail, str) else detail
    breakdown = pd.DataFrame({"Factor": [FEATURE_LABELS.get(k, k) for k in detail],
                              "Effect": list(detail.values())})
    breakdown = breakdown.reindex(breakdown["Effect"].abs().sort_values(ascending=False).index).head(8)
    breakdown["Direction"] = breakdown["Effect"].map(lambda v: "Towards fraud" if v > 0 else "Towards genuine")
    chart = (alt.Chart(breakdown).mark_bar(cornerRadiusEnd=4, size=16)
             .encode(x=alt.X("Effect:Q", title="Effect on the score (log-odds)", axis=alt.Axis(gridOpacity=0.3)),
                     y=alt.Y("Factor:N", sort=list(breakdown["Factor"]), title=None,
                             axis=alt.Axis(labelLimit=280, labelOverlap=False, labelFontSize=12)),
                     color=alt.Color("Direction:N", title=None, legend=alt.Legend(orient="top"),
                                     scale=alt.Scale(domain=["Towards fraud", "Towards genuine"],
                                                     range=[ORANGE, BLUE])),
                     tooltip=["Factor", alt.Tooltip("Effect:Q", format="+.2f"), "Direction"])
             .properties(height=300))
    st.altair_chart(chart, width="stretch")
    st.caption("The eight factors that moved this payment's score most, from SHAP. Bars to the right push "
               f"towards fraud, to the left towards genuine. Model version {alert['model_version']}.")

st.subheader("Step 4 · Decide")
# A refused decision must not be missed, so it stays here, where the analyst clicked, until they
# dismiss it (a toast fades after a few seconds, and the case above has already moved on).
if "refused" in st.session_state:
    st.warning(st.session_state["refused"], icon="⚠️")
    if st.button("Dismiss", key="dismiss_refused"):
        del st.session_state["refused"]
        st.rerun()
analyst = st.session_state.get("analyst", "").strip()
st.text_area("Note (optional)", key=f"note_{alert['trans_num']}", height=80,
             placeholder="e.g. Customer confirmed card lost on Friday")


def decide(trans_num: str, decision: str, label: str) -> None:
    """Record a decision on the alert that was on screen when the button was drawn.

    The transaction ID travels with the button, so a click can never land on a different alert,
    even if the queue changed in the meantime. If no name has been entered, or someone else has
    already worked this alert, nothing is recorded and a warning stays beside the buttons.
    """
    who = st.session_state.get("analyst", "").strip()
    if not who:
        # The buttons stay clickable so a click is never silently lost; without a name nothing is saved.
        st.session_state["refused"] = (
            "**Not recorded.** No name has been entered, so your decision was not saved. Type your name in "
            "the sidebar, press Enter, then click again.")
        return
    note = st.session_state.get(f"note_{trans_num}", "")
    if db.record_decision(trans_num, decision, note, who):
        outcome = "confirmed fraud" if decision == "confirmed_fraud" else "not fraud"
        st.session_state["flash"] = f"Recorded: {outcome} on {label}."
        st.session_state.pop("refused", None)  # an earlier warning no longer applies
    else:
        st.session_state["refused"] = (
            f"**Not recorded.** {label} had already been worked by someone else, so your decision was not "
            "saved. The case above has been refreshed and now shows the next alert: check it before deciding.")
    # A new table key clears the selection, so the case panel goes back to the top alert.
    st.session_state["decisions_made"] = st.session_state.get("decisions_made", 0) + 1


label = f"card {alert['card_ref']}, {money(alert['amount_usd'])}"
confirm, genuine, _ = st.columns([1, 1, 2])
confirm.button("Confirm fraud", type="primary", width="stretch",
               on_click=decide, args=(alert["trans_num"], "confirmed_fraud", label))
genuine.button("Not fraud", width="stretch",
               on_click=decide, args=(alert["trans_num"], "not_fraud", label))
st.caption("Enter your name in the sidebar (and press Enter) to record decisions." if not analyst else
           "Your name, the time, the score you saw and the model version are logged with the decision for audit.")

with st.expander("Recently worked"):
    recent = db.recent_decisions()
    if recent.empty:
        st.write("No decisions recorded yet.")
    else:
        recent = recent.rename(columns={
            "decided_at": "When", "decided_by": "Analyst", "card_ref": "Card", "merchant": "Merchant",
            "amount_usd": "Amount", "route": "Route", "analyst_decision": "Decision", "analyst_note": "Note"})
        recent["Route"] = recent["Route"].map(lambda r: ROUTES[r][0])
        recent["Decision"] = recent["Decision"].map({"confirmed_fraud": "Confirmed fraud", "not_fraud": "Not fraud"})
        st.dataframe(recent, hide_index=True, width="stretch", column_config={
            "When": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
            "Amount": st.column_config.NumberColumn(format="dollar")})
