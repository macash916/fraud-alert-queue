"""Spot-check the dbt feature model against an independent pandas calculation.

For five cards (three with fraud, two without), this recalculates every feature in
pandas from raw_transactions and compares it with analytics.fct_transaction_features,
row by row. Two separate implementations agreeing is strong evidence both are right.

It also recomputes each card's token in Python (HMAC-SHA256 with the key from .env) to
find the card in the feature model, which independently checks the tokenisation in dbt.

Run from the repo root:  .venv/bin/python src/spot_check_features.py
"""

import hashlib
import hmac
import os

import numpy as np
import pandas as pd

from load_data import connect  # also loads .env

FEATURES_TABLE = "analytics.fct_transaction_features"

# Picks the same five cards every run: the three cards with the most fraud,
# and the two busiest cards with no fraud at all.
PICK_CARDS_SQL = """
(SELECT cc_num FROM raw_transactions GROUP BY cc_num
 ORDER BY sum(is_fraud) DESC, cc_num LIMIT 3)
UNION ALL
(SELECT cc_num FROM raw_transactions GROUP BY cc_num
 HAVING sum(is_fraud) = 0 ORDER BY count(*) DESC, cc_num LIMIT 2);
"""

# Columns to compare, with how close counts as "the same" (SQL rounds some values).
TOLERANCE = {
    "txn_count_1h": 0,
    "txn_count_24h": 0,
    "amt_sum_24h": 0.005,
    "prior_txn_count": 0,
    "amt_vs_avg": 0.0005,
    "distance_km": 0.05,
    "is_new_merchant": 0,
    "secs_since_last": 0,
    "hour_of_day": 0,
}


def query(conn, sql: str, params=None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def card_token(cc_num: str) -> str:
    """Same keyed hash as dbt's stg_transactions, computed independently in Python."""
    key = os.environ["CARD_TOKEN_KEY"].encode()
    return hmac.new(key, cc_num.encode(), hashlib.sha256).hexdigest()


def pandas_features(raw: pd.DataFrame) -> pd.DataFrame:
    """Recalculate the features for one card using pandas and numpy only."""
    df = raw.sort_values(["trans_ts", "trans_num"]).reset_index(drop=True)
    ts = df["trans_ts"].to_numpy()
    amt = df["amt"].astype(float).to_numpy()

    # Velocity: transactions strictly before this timestamp, within the last 1h / 24h.
    # searchsorted finds positions in the sorted timestamps, so right - left = count in the window.
    before_now = np.searchsorted(ts, ts, side="left")
    start_1h = np.searchsorted(ts, ts - np.timedelta64(1, "h"), side="left")
    start_24h = np.searchsorted(ts, ts - np.timedelta64(24, "h"), side="left")
    running_total = np.concatenate([[0.0], np.cumsum(amt)])
    df["txn_count_1h"] = before_now - start_1h
    df["txn_count_24h"] = before_now - start_24h
    df["amt_sum_24h"] = running_total[before_now] - running_total[start_24h]

    # Customer history: average of all earlier amounts.
    df["prior_txn_count"] = np.arange(len(df))
    prior_avg = pd.Series(amt).expanding().mean().shift(1)
    df["amt_vs_avg"] = amt / prior_avg

    # Distance from home (haversine).
    lat1, lon1 = np.radians(df["cust_lat"]), np.radians(df["cust_long"])
    lat2, lon2 = np.radians(df["merch_lat"]), np.radians(df["merch_long"])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    df["distance_km"] = 2 * 6371 * np.arcsin(np.sqrt(a))

    # New merchant: first time this card appears at this merchant.
    df["is_new_merchant"] = (df.groupby("merchant").cumcount() == 0).astype(int)

    # Time since the previous transaction.
    df["secs_since_last"] = df["trans_ts"].diff().dt.total_seconds()
    df["hour_of_day"] = df["trans_ts"].dt.hour
    return df


def compare(card: str, sql_df: pd.DataFrame, py_df: pd.DataFrame) -> dict:
    merged = sql_df.merge(py_df, on="trans_num", suffixes=("_sql", "_py"))
    assert len(merged) == len(sql_df) == len(py_df), "row counts differ"

    mismatches = {}
    for col, tol in TOLERANCE.items():
        a = pd.to_numeric(merged[f"{col}_sql"], errors="coerce").astype(float)
        b = pd.to_numeric(merged[f"{col}_py"], errors="coerce").astype(float)
        same = np.isclose(a, b, atol=tol, rtol=0, equal_nan=True)
        if not same.all():
            mismatches[col] = int((~same).sum())

    return {
        "card": "**** " + card[-4:],
        "transactions": len(merged),
        "fraud": int(merged["is_fraud"].sum()),
        "values_checked": len(merged) * len(TOLERANCE),
        "mismatches": sum(mismatches.values()),
        "detail": mismatches or "",
    }


def main() -> None:
    with connect() as conn:
        cards = query(conn, PICK_CARDS_SQL)["cc_num"].tolist()
        results = []
        for card in cards:
            raw = query(conn, "SELECT * FROM raw_transactions WHERE cc_num = %s", (card,))
            sql_df = query(conn, f"SELECT * FROM {FEATURES_TABLE} WHERE card_token = %s",
                           (card_token(card),))
            if sql_df.empty:
                raise SystemExit(f"Card **** {card[-4:]}: token not found in {FEATURES_TABLE}")
            py_df = pandas_features(raw)[["trans_num", *TOLERANCE]]
            results.append(compare(card, sql_df, py_df))

    summary = pd.DataFrame(results)
    print(summary.to_string(index=False))
    total = summary["mismatches"].sum()
    print(f"\n{summary['values_checked'].sum():,} values checked, {total} mismatches")
    if total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
