"""Alert queue: open alerts ranked by expected loss, each with three plain-English reasons."""

import json

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


def money(x: float) -> str:
    return f"${x:,.2f}"


st.title("Alert queue")
if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"))

summary = db.queue_summary().set_index("route")
cols = st.columns(4)
for col, (route, (label, _)) in zip(cols, ROUTES.items()):
    n = int(summary.loc[route, "open_alerts"]) if route in summary.index else 0
    col.metric(f"Open: {label.lower()}", f"{n:,}")
cols[3].metric("Expected loss in open alerts", f"${summary['open_expected_loss'].sum():,.0f}",
               help="Sum of fraud probability x amount over every open alert.")

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

st.subheader("Open alerts by expected loss")
st.caption(f"Highest first; showing the top {len(queue)}. Select a row to work it.")
picked = st.dataframe(
    table, hide_index=True, height=320, on_select="rerun", selection_mode="single-row", key=f"table_{route}_{st.session_state.get('decisions_made', 0)}",
    column_config={
        "Rank": st.column_config.NumberColumn(width="small"),
        "Time": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
        "Amount": st.column_config.NumberColumn(format="$%.2f"),
        "Fraud probability": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "Expected loss": st.column_config.NumberColumn(format="$%.2f",
                                                       help="Fraud probability x amount: what the bank "
                                                            "stands to lose if this alert is fraud and missed."),
        "Main reason": st.column_config.TextColumn(width="large"),
    },
)
rows = picked.selection.rows
alert = queue.iloc[rows[0] if rows else 0]

st.divider()
left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader(f"Card {alert['card_ref']}: {money(alert['amount_usd'])}")
    st.write(f"**{alert['merchant']}**, {alert['category'].replace('_', ' ')} · "
             f"{pd.Timestamp(alert['trans_ts']):%d %b %Y, %H:%M}")
    a, b = st.columns(2)
    a.metric("Fraud probability", f"{alert['fraud_probability']:.1%}")
    b.metric("Expected loss", money(alert["expected_loss_usd"]))

    st.markdown("**Why this alert**")
    for i in (1, 2, 3):
        st.markdown(f"{i}. {alert[f'reason_{i}']}")

    analyst = st.session_state.get("analyst", "").strip()
    note = st.text_area("Note (optional)", key=f"note_{alert['trans_num']}", height=80,
                        placeholder="e.g. Customer confirmed card lost on Friday")
    confirm, genuine = st.columns(2)
    clicked = None
    if confirm.button("Confirm fraud", type="primary", use_container_width=True, disabled=not analyst):
        clicked = "confirmed_fraud"
    if genuine.button("Not fraud", use_container_width=True, disabled=not analyst):
        clicked = "not_fraud"
    if not analyst:
        st.caption("Enter your name in the sidebar to record decisions.")

with right:
    st.markdown("**Score breakdown (for audit)**")
    detail = alert["reason_detail"]
    detail = json.loads(detail) if isinstance(detail, str) else detail
    breakdown = pd.DataFrame({"Feature": [FEATURE_LABELS.get(k, k) for k in detail],
                              "Effect on score": list(detail.values())})
    breakdown = breakdown.sort_values("Effect on score", key=abs, ascending=False).head(8)
    st.dataframe(breakdown, hide_index=True, use_container_width=True, column_config={
        "Effect on score": st.column_config.NumberColumn(format="%+.2f")})
    st.caption("The eight largest SHAP contributions, in log-odds: positive pushes towards fraud, negative "
               f"towards genuine. Model version {alert['model_version']}.")

    history = db.card_alerts(alert["card_ref"])
    st.markdown(f"**All alerts on this card ({len(history)})**")
    outcome = history["analyst_decision"].map({"confirmed_fraud": "Confirmed fraud", "not_fraud": "Not fraud"})
    history = pd.DataFrame({"Time": history["trans_ts"], "Amount": history["amount_usd"],
                            "Outcome": outcome.fillna("Open"), "Probability": history["fraud_probability"],
                            "Merchant": history["merchant"]})
    st.dataframe(history, hide_index=True, use_container_width=True, height=200, column_config={
        "Time": st.column_config.DatetimeColumn(format="D MMM, HH:mm"),
        "Amount": st.column_config.NumberColumn(format="$%.2f"),
        "Probability": st.column_config.NumberColumn(format="percent")})

if clicked:
    if db.record_decision(alert["trans_num"], clicked, note, analyst):
        outcome = "confirmed fraud" if clicked == "confirmed_fraud" else "not fraud"
        st.session_state["flash"] = f"Recorded: {outcome} on card {alert['card_ref']}, {money(alert['amount_usd'])}."
    else:
        st.session_state["flash"] = "Someone else has already worked this alert."
    # A new table key clears the selection, so the case panel goes back to the top alert
    # rather than silently showing whichever alert has moved into the selected row.
    st.session_state["decisions_made"] = st.session_state.get("decisions_made", 0) + 1
    st.rerun()

with st.expander("Recently worked"):
    recent = db.recent_decisions()
    if recent.empty:
        st.write("No decisions recorded yet.")
    else:
        st.dataframe(recent, hide_index=True)
