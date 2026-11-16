"""Management information: what the team has worked and what it achieved.

Every figure comes from analysts' recorded decisions in app.alerts, not from the dataset's
fraud labels. That is how a live MI pack works: the bank only knows what its analysts confirmed.
"""

import altair as alt
import pandas as pd
import streamlit as st

import db
from metrics import pct, summarise

ROUTE_LABELS = {"analyst_review": "Analyst review", "decline": "Decline and block", "step_up": "In-app step-up"}
DECISION_LABELS = {"confirmed_fraud": "Confirmed fraud", "not_fraud": "Not fraud"}
ORANGE, BLUE = "#eb6834", "#2a78d6"  # project palette: fraud orange, genuine blue


st.title("Management information")

worked = db.worked_alerts()
open_q = db.queue_summary()

with st.expander("How these figures are defined"):
    st.markdown("""
- **Alerts worked:** alerts an analyst has closed with a decision.
- **Hit rate:** share of worked alerts confirmed as fraud.
- **False positive rate:** share of worked alerts that turned out genuine. Each one is a genuine customer
  who was interrupted, which matters under Consumer Duty. Also shown as a ratio (genuine alerts per fraud).
- **Value saved:** total amount of payments confirmed as fraud and stopped.
- All figures come from analysts' recorded decisions, not from the dataset's fraud labels.
""")

if worked.empty:
    st.info("No alerts have been worked yet. Figures appear here as analysts record decisions in the queue.")
else:
    analysts = sorted(worked["decided_by"].dropna().unique())
    chosen = st.multiselect("Analysts", analysts, default=analysts)
    worked = worked[worked["decided_by"].isin(chosen)]
    s = summarise(worked)

    c = st.columns(4)
    c[0].metric("Alerts worked", f"{s['Alerts worked']:,}")
    c[1].metric("Hit rate", pct(s["Hit rate"]))
    c[2].metric("Value saved", f"${s['Value saved']:,.0f}")
    ratio = f"{s['Not fraud'] / s['Confirmed fraud']:.1f} : 1" if s["Confirmed fraud"] else "n/a"
    c[3].metric("False positive rate", pct(s["False positive rate"]),
                help=f"Genuine alerts per confirmed fraud: {ratio}")

    st.subheader("Alerts worked per day")
    daily = (worked.assign(day=pd.to_datetime(worked["decided_at"]).dt.normalize(),
                           decision=worked["analyst_decision"].map(DECISION_LABELS))
             .groupby(["day", "decision"]).size().rename("alerts").reset_index())
    chart = (alt.Chart(daily).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=28)
             .encode(x=alt.X("yearmonthdate(day):O", title=None, axis=alt.Axis(format="%d %b", labelAngle=0)),
                     y=alt.Y("alerts:Q", title="Alerts worked", stack=True,
                             axis=alt.Axis(tickMinStep=1, format="d", gridOpacity=0.3)),
                     color=alt.Color("decision:N", title=None,
                                     scale=alt.Scale(domain=list(DECISION_LABELS.values()), range=[ORANGE, BLUE]),
                                     legend=alt.Legend(orient="top")),
                     tooltip=[alt.Tooltip("day:T", format="%d %b %Y", title="Day"), "decision:N", "alerts:Q"])
             .properties(height=260))
    st.altair_chart(chart, use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("By route")
        by_route = pd.DataFrame([{"Route": ROUTE_LABELS[r], **summarise(g)} for r, g in worked.groupby("route")])
        st.dataframe(by_route[["Route", "Alerts worked", "Hit rate", "False positive rate", "Value saved"]],
                     hide_index=True, column_config={
            "Hit rate": st.column_config.NumberColumn(format="percent"),
            "False positive rate": st.column_config.NumberColumn(format="percent"),
            "Value saved": st.column_config.NumberColumn(format="dollar")})
    with right:
        st.subheader("By model score")
        bands = pd.cut(worked["fraud_probability"], [0, 0.5, 0.9, 1.0001],
                       labels=["Under 50%", "50% to 90%", "90% and over"], right=False)
        by_band = pd.DataFrame([{"Fraud probability": b, **summarise(g)}
                                for b, g in worked.groupby(bands, observed=True)])
        st.dataframe(by_band[["Fraud probability", "Alerts worked", "Hit rate"]], hide_index=True,
                     column_config={"Hit rate": st.column_config.NumberColumn(format="percent")})
        st.caption("A model-risk check: hit rates should rise with the score. If they stop doing so, "
                   "the model needs reviewing.")

st.subheader("Open queue")
open_q = open_q.assign(Route=open_q["route"].map(ROUTE_LABELS))
st.dataframe(open_q[["Route", "open_alerts", "open_expected_loss"]], hide_index=True, column_config={
    "open_alerts": st.column_config.NumberColumn("Open alerts", format="%d"),
    "open_expected_loss": st.column_config.NumberColumn("Expected loss in open alerts", format="dollar")})
