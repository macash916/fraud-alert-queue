"""Analyst app: the alert queue and the MI page.

Run locally from the repo root:  .venv/bin/streamlit run app/streamlit_app.py
In Docker it starts with:        docker compose up
"""

import streamlit as st

import db

st.set_page_config(page_title="Fraud alert queue", page_icon="🛡️", layout="wide")

pages = st.navigation([
    st.Page("queue_page.py", title="Alert queue", icon="📥", default=True),
    st.Page("mi_page.py", title="Management information", icon="📊"),
])

with st.sidebar:
    st.text_input("Your name", key="analyst", placeholder="e.g. A. Sharma",
                  help="Recorded against every decision you make, for the audit trail.")
    st.caption("Simulated data (Sparkov), test months 21 Jun to 31 Dec 2020. "
               "Amounts in US dollars because the dataset is US-simulated.")

# On a clean machine the alerts only exist once the pipeline has run; say so rather than crash.
ready = db.query("SELECT to_regclass('app.alerts') IS NOT NULL AND to_regclass('app.alert_decision_log') "
                 "IS NOT NULL AS ready")["ready"][0]
if not ready:
    st.title("Fraud alert queue")
    st.warning("No alerts yet. Load the data and run the pipeline first (see 'How to run' in the README); "
               "the queue fills once src/explain.py has written the alerts.")
    st.stop()

pages.run()
