"""Analyst app: overview, alert queue and MI page.

Run locally from the repo root:  .venv/bin/streamlit run app/streamlit_app.py
In Docker it starts with:        docker compose up
"""

import streamlit as st

import db

st.set_page_config(page_title="Fraud alert queue", layout="wide")

pages = st.navigation([
    st.Page("overview_page.py", title="Overview", default=True),
    st.Page("queue_page.py", title="Alert queue"),
    st.Page("mi_page.py", title="Management information"),
])

with st.sidebar:
    st.text_input("Your name", key="analyst", placeholder="e.g. John Doe",
                  help="Recorded against every decision you make, for the audit trail.")
    # Visible feedback: the decision buttons it unlocks are further down the queue page, out of sight.
    if st.session_state.get("analyst", "").strip():
        st.success(f"Working as **{st.session_state['analyst'].strip()}**. "
                   "Your decisions are recorded under this name.")
    else:
        st.info("Type your name and press Enter before recording decisions.")
    st.caption("Start with the Overview, then work alerts in the Alert queue. "
               "Management information shows the results.")
    st.caption("Simulated data (Sparkov), test months 21 Jun to 31 Dec 2020. Amounts in US dollars.")

# On a clean machine the alerts only exist once the pipeline has run; say so rather than crash.
ready = db.query("SELECT to_regclass('app.alerts') IS NOT NULL AND to_regclass('app.alert_decision_log') "
                 "IS NOT NULL AS ready")["ready"][0]
if not ready:
    st.title("Fraud alert queue")
    st.warning("No alerts yet. Load the data and run the pipeline first (see 'How to run' in the README); "
               "the queue fills once src/explain.py has written the alerts.")
    st.stop()

pages.run()
