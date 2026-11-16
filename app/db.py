"""Database access for the analyst app.

The app reads and writes only the app schema (app.alerts and app.alert_decision_log).
It never touches the raw table or any personal data: cards are shown by an 8-character
token prefix, and customers are never named.
"""

import os

import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()  # local runs read .env; in Docker the variables come from docker-compose.yml


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or {})
        return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


def open_queue(route: str, limit: int = 200) -> pd.DataFrame:
    """Open alerts for one route, highest expected loss first (probability x amount)."""
    return query("""
        SELECT trans_num, trans_ts, card_ref, merchant, category, amount_usd::float AS amount_usd,
               fraud_probability, expected_loss_usd::float AS expected_loss_usd,
               reason_1, reason_2, reason_3, reason_detail, model_version
        FROM app.alerts
        WHERE status = 'open' AND route = %(route)s
        ORDER BY expected_loss_usd DESC, trans_ts
        LIMIT %(limit)s
    """, {"route": route, "limit": limit})


def queue_summary() -> pd.DataFrame:
    return query("""
        SELECT route, count(*) FILTER (WHERE status = 'open') AS open_alerts,
               coalesce(sum(expected_loss_usd) FILTER (WHERE status = 'open'), 0)::float AS open_expected_loss
        FROM app.alerts GROUP BY route
    """)


def card_alerts(card_ref: str) -> pd.DataFrame:
    return query("""
        SELECT trans_ts, merchant, category, amount_usd::float AS amount_usd, fraud_probability, route,
               status, analyst_decision
        FROM app.alerts WHERE card_ref = %(card_ref)s ORDER BY trans_ts
    """, {"card_ref": card_ref})


def record_decision(trans_num: str, decision: str, note: str, analyst: str) -> bool:
    """Close an alert and write the decision to the audit log, in one transaction.

    Only an alert that is still open can be decided, so two analysts can't work the same alert.
    Returns False if someone else got there first.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE app.alerts
            SET status = 'closed', analyst_decision = %(decision)s, analyst_note = %(note)s,
                decided_by = %(analyst)s, decided_at = now()
            WHERE trans_num = %(trans_num)s AND status = 'open'
            RETURNING model_version, fraud_probability, route
        """, {"trans_num": trans_num, "decision": decision, "note": note or None, "analyst": analyst})
        row = cur.fetchone()
        if row is None:
            return False
        cur.execute("""
            INSERT INTO app.alert_decision_log
                (trans_num, analyst_decision, analyst_note, decided_by, model_version, fraud_probability, route)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (trans_num, decision, note or None, analyst, *row))
        return True


def worked_alerts() -> pd.DataFrame:
    """Every closed alert, for the MI page."""
    return query("""
        SELECT trans_num, route, amount_usd::float AS amount_usd, fraud_probability, analyst_decision,
               decided_by, decided_at
        FROM app.alerts WHERE status = 'closed'
    """)


def recent_decisions(limit: int = 50) -> pd.DataFrame:
    return query("""
        SELECT l.decided_at, l.decided_by, a.card_ref, a.merchant, a.amount_usd::float AS amount_usd,
               l.route, l.analyst_decision, l.analyst_note
        FROM app.alert_decision_log l JOIN app.alerts a USING (trans_num)
        ORDER BY l.decision_id DESC LIMIT %(limit)s
    """, {"limit": limit})
