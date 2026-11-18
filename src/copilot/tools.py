"""The co-pilot's read-only tools: what it may look at, and nothing else.

Plain English: three lookups an analyst would do: the alert and its reasons, the card's last 72 hours,
and the card's earlier alerts. Each returns numbered facts ("fact:amount", "fact:recent_3") so every
sentence in a draft can point to the exact fact behind it. They run on a read-only connection and
return only tokens and payment features: no names, addresses, dates of birth or card numbers.

Earlier alerts show their outcome only if they are more than 7 days old (decision V3 = b); newer ones
say "Under investigation". In benchmark mode the outcome is the simulator's label, standing in for the
result of the bank's investigation; in the app it is the analyst's recorded decision.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .guardrails import as_data

ROOT = Path(__file__).resolve().parents[2]
OUTCOME_AFTER_DAYS = 7
# Columns that must never reach the model (the staging layer already drops them; this is a second lock).
FORBIDDEN = {"first", "last", "street", "city", "zip", "dob", "gender", "cc_num", "job", "lat", "long"}

Query = Callable[[str, dict], pd.DataFrame]


def read_only_query(sql: str, params: dict) -> pd.DataFrame:
    """Run a query inside a read-only transaction, so a tool can never change the database."""
    sys.path.insert(0, str(ROOT / "app"))
    import db

    with db.connect() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


@dataclass
class ToolResult:
    facts: dict[str, str] = field(default_factory=dict)   # fact id -> plain-English fact
    flags: list[str] = field(default_factory=list)         # warnings for the analyst (e.g. suspicious text)


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _guard(df: pd.DataFrame) -> pd.DataFrame:
    leaked = FORBIDDEN & {c.lower() for c in df.columns}
    if leaked:
        raise PermissionError(f"tool query returned personal fields: {sorted(leaked)}")
    return df


def get_alert(trans_num: str, q: Query = read_only_query) -> ToolResult:
    df = _guard(q("""
        SELECT a.trans_num, a.trans_ts, a.card_ref, a.merchant, a.category, a.amount_usd::float AS amount,
               a.fraud_probability AS p, a.expected_loss_usd::float AS expected_loss, a.route,
               a.reason_1, a.reason_2, a.reason_3, a.model_version
        FROM app.alerts a WHERE a.trans_num = %(t)s
    """, {"t": trans_num}))
    if df.empty:
        return ToolResult(flags=["alert not found"])
    a = df.iloc[0]
    merchant = as_data(a.merchant, "merchant")
    res = ToolResult(flags=[f"merchant name: {f}" for f in merchant.flags])
    res.facts = {
        "fact:amount": f"Payment amount {_money(a.amount)}",
        "fact:merchant": f"Merchant {merchant.text}, category {a.category}",
        "fact:time": f"Made on {pd.Timestamp(a.trans_ts):%d %b %Y} at {pd.Timestamp(a.trans_ts):%H:%M}",
        "fact:score": f"Model fraud probability {a.p * 100:.1f}% (model version {a.model_version})",
        "fact:expected_loss": f"Expected loss {_money(a.expected_loss)}",
        "fact:route": f"Route {a.route}",
        "fact:reason_1": a.reason_1,
        "fact:reason_2": a.reason_2,
        "fact:reason_3": a.reason_3,
    }
    return res


def card_last_72h(card_token: str, before, q: Query = read_only_query) -> ToolResult:
    df = _guard(q("""
        SELECT trans_ts, merchant, category, amt::float AS amount
        FROM analytics.fct_transaction_features
        WHERE card_token = %(c)s AND trans_ts < %(ts)s AND trans_ts >= %(ts)s - interval '72 hours'
        ORDER BY trans_ts
    """, {"c": card_token, "ts": before}))
    res = ToolResult()
    res.facts["fact:recent_count"] = f"{len(df)} payments in the 72 hours before this one"
    if not df.empty:
        res.facts["fact:recent_total"] = f"{_money(df.amount.sum())} spent in the 72 hours before this one"
    for i, r in enumerate(df.itertuples(), start=1):
        m = as_data(str(r.merchant).removeprefix("fraud_"), "merchant")
        res.flags += [f"recent merchant {i}: {f}" for f in m.flags]
        res.facts[f"fact:recent_{i}"] = f"{pd.Timestamp(r.trans_ts):%d %b %H:%M} {m.text} {r.category} {_money(r.amount)}"
    return res


def earlier_alerts(card_token: str, before, mode: str = "app", q: Query = read_only_query) -> ToolResult:
    """mode 'app' uses analysts' recorded decisions; 'benchmark' uses the label as the investigation result."""
    df = _guard(q("""
        SELECT a.trans_ts, a.merchant, a.amount_usd::float AS amount, a.route, a.fraud_probability AS p,
               a.analyst_decision, f.is_fraud
        FROM app.alerts a JOIN analytics.fct_transaction_features f USING (trans_num)
        WHERE f.card_token = %(c)s AND a.trans_ts < %(ts)s ORDER BY a.trans_ts
    """, {"c": card_token, "ts": before}))
    res = ToolResult()
    res.facts["fact:earlier_count"] = f"{len(df)} earlier alerts on this card"
    cutoff = pd.Timestamp(before) - pd.Timedelta(days=OUTCOME_AFTER_DAYS)
    for i, r in enumerate(df.itertuples(), start=1):
        if pd.Timestamp(r.trans_ts) >= cutoff:
            outcome = "Under investigation"
        elif mode == "benchmark":
            outcome = "Confirmed fraud" if r.is_fraud == 1 else "Not fraud"
        else:
            outcome = {"confirmed_fraud": "Confirmed fraud", "not_fraud": "Not fraud"}.get(r.analyst_decision, "Not worked")
        m = as_data(str(r.merchant), "merchant")
        res.facts[f"fact:earlier_{i}"] = (f"{pd.Timestamp(r.trans_ts):%d %b %Y} {m.text} {_money(r.amount)}, "
                                         f"route {r.route}, score {r.p * 100:.1f}%, outcome: {outcome}")
    return res
