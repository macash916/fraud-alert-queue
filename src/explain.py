"""Reason codes: the top 3 plain-English reasons behind every alert, and the alerts table.

  1. Loads the champion model from the MLflow registry (models:/fraud-xgboost@champion).
  2. SHAP (TreeExplainer) splits each alert's score into the contribution of each feature.
     The 14 one-hot category columns are added together into one 'category' contribution.
  3. The 3 features that pushed the score up most become the reasons, written with the
     payment's own values ("Spend in the last 24 hours is 12x this customer's usual daily spend").
  4. Alerts (test-month payments routed to analyst review, step-up or decline) are written to
     app.alerts. Re-running refreshes scores and reasons but never touches analyst decisions.
  5. Global importance (mean absolute SHAP) on a sample of all test payments, to decide
     whether the two weak features earn their place: docs/figures/shap_importance.png.

No fraud labels are written to app.alerts: analysts must judge alerts on the evidence.

Run from the repo root:  .venv/bin/python src/explain.py
"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import mlflow.xgboost  # noqa: E402
import pandas as pd  # noqa: E402
import shap  # noqa: E402

from decisioning import BLUE, FIGURES, style, SURFACE  # noqa: E402
from load_data import connect  # noqa: E402
from train import load_training_file, xgb_matrix  # noqa: E402

MODEL_URI = "models:/fraud-xgboost@champion"
GLOBAL_SAMPLE = 50_000

CATEGORY_LABELS = {
    "entertainment": "entertainment", "food_dining": "food and dining", "gas_transport": "fuel and transport",
    "grocery_net": "grocery (online)", "grocery_pos": "grocery (in store)", "health_fitness": "health and fitness",
    "home": "home", "kids_pets": "kids and pets", "misc_net": "miscellaneous (online)",
    "misc_pos": "miscellaneous (in store)", "personal_care": "personal care",
    "shopping_net": "shopping (online)", "shopping_pos": "shopping (in store)", "travel": "travel",
}

FEATURE_NAMES = {  # short labels for charts and the audit trail
    "spend_24h_vs_daily_avg": "Spend today vs usual daily spend", "amt_vs_category_avg": "Amount vs category norm",
    "amt_vs_avg": "Amount vs customer's average", "amt": "Amount", "amt_sum_24h": "Spend in previous 24h",
    "hour_of_day": "Time of day", "category": "Merchant category", "is_new_merchant": "New merchant",
    "is_new_category": "New category for customer", "txn_count_1h": "Payments in previous hour",
    "txn_count_24h": "Payments in previous 24h", "secs_since_last": "Time since previous payment",
    "prior_txn_count": "Card history length", "distance_km": "Distance from home",
    "hour_band_share": "Usual time of day for customer", "small_txn_count_24h": "Small payments in previous 24h",
}


def times(v: float) -> str:
    """A ratio written for people: 0.04x, 3.5x, 59x."""
    return f"{v:.2f}x" if v < 0.1 else f"{v:.1f}x" if v < 10 else f"{v:.0f}x"


def reason_text(feature: str, row: pd.Series) -> str:
    """One plain-English reason, using this payment's own values.

    A feature can push the score up in either direction (a very large OR a very small amount),
    so each template says which way the payment is unusual.
    """
    v = row.get(feature)
    category = CATEGORY_LABELS.get(row["category"], row["category"])
    if feature == "spend_24h_vs_daily_avg":
        if pd.isna(v):
            return "No spending history to compare today's spend with"
        return (f"Spend in the last 24 hours is {times(v)} this customer's usual daily spend" if v >= 1
                else f"Unusually quiet day for this customer ({times(v)} their usual daily spend)")
    if feature == "amt_vs_category_avg":
        return (f"Amount is {times(v)} a typical {category} payment" if v >= 1
                else f"Unusually small for a {category} payment ({times(v)} typical)")
    if feature == "amt_vs_avg":
        if pd.isna(v):
            return "First payment on this card, so no average to compare with"
        return (f"Amount is {times(v)} this customer's average payment" if v >= 1
                else f"Unusually small for this customer ({times(v)} their average payment)")
    if feature == "amt":
        if v < 20:
            return f"Small payment of ${v:,.2f}, a size often used to test a stolen card"
        return f"Large payment of ${v:,.2f}" if v >= 500 else f"Payment amount of ${v:,.2f}"
    if feature == "amt_sum_24h":
        return f"${v:,.0f} already spent on this card in the previous 24 hours"
    if feature == "hour_of_day":
        return f"Made at {row['trans_ts']:%H:%M}, a time of day linked to fraud"
    if feature == "category":
        return f"Merchant category ({category}) is often targeted by fraud"
    if feature == "is_new_merchant":
        return "First payment at this merchant" if v == 1 else "Payment at a merchant this card has used before"
    if feature == "is_new_category":
        return (f"First {category} payment by this customer" if v == 1
                else f"Customer has paid in this category ({category}) before")
    if feature == "txn_count_1h":
        return f"{v:.0f} other payment(s) on this card in the previous hour"
    if feature == "txn_count_24h":
        return f"{v:.0f} other payment(s) on this card in the previous 24 hours"
    if feature == "secs_since_last":
        if pd.isna(v):
            return "First payment on this card"
        return (f"Only {v / 60:.0f} minutes since the previous payment" if v < 3600
                else f"First payment in {v / 3600:.0f} hours, after a quiet spell on the card")
    if feature == "prior_txn_count":
        # Only a short history is unusual in itself; a long one is stated as a plain fact.
        return (f"Limited card history: {v:.0f} earlier payment(s)" if v < 50
                else f"Card history of {v:,.0f} earlier payments, a pattern the model links to fraud here")
    if feature == "distance_km":
        return f"Merchant is {v:.0f} km from the customer's home"
    if feature == "hour_band_share":
        if pd.isna(v):
            return "No history of this customer's usual payment times"
        return (f"Customer rarely pays at this time of day ({100 * v:.0f}% of past payments)" if v < 0.2
                else f"{100 * v:.0f}% of this customer's past payments were at this time of day")
    if feature == "small_txn_count_24h":
        return f"{v:.0f} small payment(s) under $20 in the previous 24 hours"
    return FEATURE_NAMES.get(feature, feature)


def grouped_shap(model, x: pd.DataFrame) -> pd.DataFrame:
    """SHAP values per feature, with the one-hot category columns summed into 'category'."""
    values = shap.TreeExplainer(model).shap_values(x)
    frame = pd.DataFrame(values, columns=x.columns, index=x.index)
    cat_cols = [c for c in frame.columns if c.startswith("cat_")]
    frame["category"] = frame[cat_cols].sum(axis=1)
    return frame.drop(columns=cat_cols)


def load_alerts() -> pd.DataFrame:
    sql = """
        SELECT d.trans_num, d.route, d.fraud_probability, d.expected_loss_usd::float AS expected_loss_usd,
               s.merchant, s.card_token
        FROM scoring.decisions d
        JOIN analytics.stg_transactions s USING (trans_num)
        WHERE d.route <> 'approve'
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


ALERTS_DDL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.alerts (
    trans_num          TEXT PRIMARY KEY,
    trans_ts           TIMESTAMP NOT NULL,
    card_ref           TEXT NOT NULL,          -- first 8 characters of the card token (pseudonymous)
    merchant           TEXT NOT NULL,
    category           TEXT NOT NULL,
    amount_usd         NUMERIC(12,2) NOT NULL,
    fraud_probability  DOUBLE PRECISION NOT NULL,
    expected_loss_usd  NUMERIC(12,2) NOT NULL,
    route              TEXT NOT NULL CHECK (route IN ('step_up', 'analyst_review', 'decline')),
    reason_1           TEXT NOT NULL,
    reason_2           TEXT NOT NULL,
    reason_3           TEXT NOT NULL,
    reason_detail      JSONB NOT NULL,         -- features and SHAP contributions, for audit
    model_version      TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    analyst_decision   TEXT CHECK (analyst_decision IN ('confirmed_fraud', 'not_fraud')),
    analyst_note       TEXT,
    decided_by         TEXT,
    decided_at         TIMESTAMP,
    created_at         TIMESTAMP NOT NULL DEFAULT now()
);

-- Append-only audit trail: one row per analyst decision, never updated or deleted.
-- app.alerts holds the current state; this table holds the history an auditor asks for.
CREATE TABLE IF NOT EXISTS app.alert_decision_log (
    decision_id        BIGSERIAL PRIMARY KEY,
    trans_num          TEXT NOT NULL REFERENCES app.alerts (trans_num),
    analyst_decision   TEXT NOT NULL CHECK (analyst_decision IN ('confirmed_fraud', 'not_fraud')),
    analyst_note       TEXT,
    decided_by         TEXT NOT NULL,
    decided_at         TIMESTAMP NOT NULL DEFAULT now(),
    model_version      TEXT NOT NULL,
    fraud_probability  DOUBLE PRECISION NOT NULL,   -- the score the analyst saw
    route              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS alerts_open_queue ON app.alerts (status, route, expected_loss_usd DESC);
"""

UPSERT = """
INSERT INTO app.alerts (trans_num, trans_ts, card_ref, merchant, category, amount_usd, fraud_probability,
                        expected_loss_usd, route, reason_1, reason_2, reason_3, reason_detail, model_version)
VALUES (%(trans_num)s, %(trans_ts)s, %(card_ref)s, %(merchant)s, %(category)s, %(amount_usd)s,
        %(fraud_probability)s, %(expected_loss_usd)s, %(route)s, %(reason_1)s, %(reason_2)s, %(reason_3)s,
        %(reason_detail)s, %(model_version)s)
ON CONFLICT (trans_num) DO UPDATE SET
    fraud_probability = EXCLUDED.fraud_probability, expected_loss_usd = EXCLUDED.expected_loss_usd,
    route = EXCLUDED.route, reason_1 = EXCLUDED.reason_1, reason_2 = EXCLUDED.reason_2,
    reason_3 = EXCLUDED.reason_3, reason_detail = EXCLUDED.reason_detail, model_version = EXCLUDED.model_version
"""


def plot_importance(importance: pd.Series) -> None:
    importance = importance.sort_values()
    fig, ax = plt.subplots(figsize=(8, 6), facecolor=SURFACE)
    ax.barh([FEATURE_NAMES.get(f, f) for f in importance.index], importance.values, color=BLUE, height=0.6)
    style(ax, "What drives the model: mean absolute SHAP, test months", "Mean |SHAP| (log-odds)", "")
    fig.tight_layout()
    fig.savefig(FIGURES / "shap_importance.png", dpi=160)
    plt.close(fig)


def main() -> None:
    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    model = mlflow.xgboost.load_model(MODEL_URI)
    version = mlflow.MlflowClient().get_model_version_by_alias("fraud-xgboost", "champion").version
    features = model.get_booster().feature_names
    categories = [c.removeprefix("cat_") for c in features if c.startswith("cat_")]

    test = load_training_file("fraudTest.csv").set_index("trans_num")
    x_all = xgb_matrix(test, categories)[features]

    # Global importance on a random sample of all test payments
    sample = x_all.sample(GLOBAL_SAMPLE, random_state=42)
    importance = grouped_shap(model, sample).abs().mean().sort_values(ascending=False)
    plot_importance(importance)
    print("Mean |SHAP| on 50,000 random test payments:")
    print((importance / importance.sum() * 100).round(1).rename("share_pct").to_string(), "\n")

    # Reasons for every alert
    alerts = load_alerts().set_index("trans_num")
    contrib = grouped_shap(model, x_all.loc[alerts.index])
    rows = []
    for trans_num, c in contrib.iterrows():
        top = c.sort_values(ascending=False).head(3)
        payment = test.loc[trans_num]
        a = alerts.loc[trans_num]
        reasons = [reason_text(f, payment) for f in top.index]
        rows.append({
            "trans_num": trans_num, "trans_ts": payment["trans_ts"].to_pydatetime(),
            "card_ref": a["card_token"][:8], "merchant": a["merchant"].removeprefix("fraud_"),
            "category": payment["category"], "amount_usd": round(float(payment["amt"]), 2),
            "fraud_probability": float(a["fraud_probability"]), "expected_loss_usd": float(a["expected_loss_usd"]),
            "route": a["route"], "reason_1": reasons[0], "reason_2": reasons[1], "reason_3": reasons[2],
            "reason_detail": json.dumps({f: round(float(v), 4) for f, v in c.sort_values(ascending=False).items()}),
            "model_version": str(version),
        })

    with connect() as conn, conn.cursor() as cur:
        cur.execute(ALERTS_DDL)
        cur.executemany(UPSERT, rows)
        conn.commit()
        cur.execute("SELECT route, count(*) FROM app.alerts GROUP BY route ORDER BY 2 DESC")
        print("app.alerts by route:", dict(cur.fetchall()))

    print("\nThree example alerts (highest expected loss in the analyst queue):")
    examples = sorted((r for r in rows if r["route"] == "analyst_review"),
                      key=lambda r: -r["expected_loss_usd"])[:3]
    for r in examples:
        print(f"  ${r['amount_usd']:,.2f} at {r['merchant']} ({r['category']}), p={r['fraud_probability']:.2f}")
        for i in (1, 2, 3):
            print(f"     {i}. {r[f'reason_{i}']}")

    mlflow.set_experiment("explainability")
    with mlflow.start_run(run_name=f"reason-codes-champion-v{version}"):
        mlflow.log_params({"model_uri": MODEL_URI, "model_version": version, "global_sample": GLOBAL_SAMPLE,
                           "alerts_explained": len(rows)})
        mlflow.log_dict((importance / importance.sum() * 100).round(3).to_dict(), "shap_importance_share_pct.json")
        mlflow.log_artifact(str(FIGURES / "shap_importance.png"), "figures")


if __name__ == "__main__":
    main()
