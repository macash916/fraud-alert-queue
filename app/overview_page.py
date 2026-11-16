"""Overview: what this system does, in plain English, for anyone opening it for the first time."""

import streamlit as st

import db

st.title("Card fraud alert queue")
st.markdown(
    "A bank sees more suspicious card payments than its fraud analysts can check. This system scores "
    "every payment for fraud risk, decides what should happen to it, and explains each decision in plain "
    "English, so it can stand up to a customer, an auditor and the regulator."
)
st.info("Demonstration on simulated card data (the Sparkov dataset), not real customers. "
        "Amounts are in US dollars because the dataset is US-simulated.")

st.subheader("How a payment flows through the system")
steps = [
    ("1. Score", "A machine-learning model estimates how likely each payment is to be fraud, using only "
                 "what was known before it: the card's usual spending, recent activity, merchant and time."),
    ("2. Route", "Each payment gets the cheapest safe treatment, weighing the likely fraud loss against the "
                 "cost of interrupting a genuine customer and of an analyst's time."),
    ("3. Explain", "Every alert carries the three factors that pushed its score up most, written in plain "
                   "English, for example: \"Amount is 75x a typical in-store shopping payment\"."),
    ("4. Decide and learn", "An analyst confirms fraud or clears the payment. Every decision is logged for "
                            "audit, feeds the management information, and is used to monitor the model."),
]
for column, (title, text) in zip(st.columns(4), steps):
    with column.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(text)

st.subheader("The four outcomes")
counts = db.queue_summary().set_index("route")["open_alerts"]
outcomes = [
    ("Approve", None, "Payment goes through. The customer notices nothing. Most payments end here."),
    ("In-app step-up", "step_up", "The customer is asked to confirm the payment in their banking app. "
                                  "Genuine customers tap 'yes' and carry on; no response sends it to an analyst."),
    ("Analyst review", "analyst_review", "The payment is held and a fraud analyst checks it. Used for the "
                                         "riskiest payments where a person's judgement is worth the cost."),
    ("Decline and block", "decline", "The model is near-certain it is fraud: the payment is declined and "
                                     "the card blocked straight away. An analyst reviews it afterwards."),
]
for title, route, text in outcomes:
    left, right = st.columns([1, 3])
    left.markdown(f"**{title}**")
    if route:
        left.caption(f"{int(counts.get(route, 0)):,} open alerts")
    right.write(text)

st.subheader("Where to go next")
a, b = st.columns(2)
with a.container(border=True):
    st.page_link("queue_page.py", label="**Alert queue**: for analysts")
    st.caption("Work alerts in order of expected loss: read why each was flagged, then confirm fraud or "
               "clear it. Enter your name in the sidebar first.")
with b.container(border=True):
    st.page_link("mi_page.py", label="**Management information**: for team leaders and managers")
    st.caption("Alerts worked, hit rate, value saved, false positive rate, and whether the model still "
               "ranks well. Figures fill in as analysts record decisions.")

with st.expander("Terms used in this app"):
    st.markdown("""
- **Fraud probability:** the model's estimate that a payment is fraud. 0.40 means about 4 in 10 payments
  like this one turn out to be fraud.
- **Expected loss:** fraud probability x amount. A $5,000 payment at 40% risks more ($2,000) than a $50
  payment at 90% ($45), so it is worked first.
- **Reasons:** the three factors that pushed this payment's score up the most (from SHAP, a standard method
  for explaining a model's individual decisions).
- **Hit rate:** the share of alerts an analyst works that turn out to be fraud.
- **False positive:** a genuine payment that was flagged. Each one is a real customer interrupted.
""")
