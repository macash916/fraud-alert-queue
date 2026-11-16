"""Ongoing monitoring: is the model still working on the payments it now sees?

Four checks, month by month over the test months (the period after go-live):
  1. Input drift:  Population Stability Index (PSI) for each feature and for the merchant-category mix,
                   against the training months the champion model learned from.
  2. Score drift:  PSI of the model's fraud probability against its scores on the training months.
  3. Outcomes:     share of fraud value the routes stopped, alerts per day by route, analyst hit rate,
                   genuine customers interrupted, against the whole test period as the baseline.
     Any amber or red feature is also compared with the same month a year earlier, to tell
     seasonal change (December shopping) from a lasting change in the customer base.
  4. Fairness:     the watch item from the fairness audit: each gender's interruption rate against
                   the overall rate that month.

Red / amber / green (RAG) rules:
  PSI          green below 0.10, amber 0.10 to 0.25, red above 0.25 (the usual industry convention)
  Fraud value  amber if the month is more than 2 points below the test baseline, red if more than 5
  Fairness     amber if a group's rate is 1.10x the overall rate or more, red if the lower 95% bound is
               above 1.25x (the flag rule used in the fairness audit)

Outputs: monitoring.drift_monthly in PostgreSQL, docs/figures/drift_psi.png, MLflow experiment 'monitoring'.
In live use this runs monthly and a red goes to the model owner (see docs/monitoring.md).

Run from the repo root:  .venv/bin/python src/drift.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from decisioning import FIGURES, INK, INK_2, SURFACE  # noqa: E402
from fairness import wilson  # noqa: E402
from load_data import connect  # noqa: E402
from train import NUMERIC_FEATURES, load_training_file, xgb_matrix  # noqa: E402

MODEL_URI = "models:/fraud-xgboost@champion"
PSI_AMBER, PSI_RED = 0.10, 0.25
VALUE_AMBER_PTS, VALUE_RED_PTS = 2.0, 5.0
FAIR_AMBER, FAIR_RED = 1.10, 1.25
BINS = 10
STATUS_COLOURS = {"amber": "#fab219", "red": "#d03b3b"}  # status palette; green cells stay unfilled

# Plain names for the chart and the report.
FEATURE_LABELS = {
    "amt": "Payment amount", "hour_of_day": "Time of day", "txn_count_1h": "Payments in last hour",
    "txn_count_24h": "Payments in last 24h", "amt_sum_24h": "Spend in last 24h",
    "prior_txn_count": "Length of card history", "amt_vs_avg": "Amount vs card average",
    "distance_km": "Distance from home", "is_new_merchant": "New merchant",
    "secs_since_last": "Time since last payment", "amt_vs_category_avg": "Amount vs category norm",
    "is_new_category": "First use of category", "hour_band_share": "Usual time of day for card",
    "small_txn_count_24h": "Small payments in last 24h", "spend_24h_vs_daily_avg": "24h spend vs usual daily",
    "category": "Merchant category mix", "fraud_probability": "Model score",
}


# ---------------------------------------------------------------- PSI

def psi_from_shares(expected: np.ndarray, actual: np.ndarray, floor: float = 1e-4) -> float:
    """PSI = sum over bins of (actual - expected) x ln(actual / expected).

    A small floor stops an empty bin from producing an infinite value.
    """
    e = np.clip(expected, floor, None)
    a = np.clip(actual, floor, None)
    return float(np.sum((a - e) * np.log(a / e)))


def numeric_psi(reference: pd.Series, current: pd.Series, bins: int = BINS) -> float:
    """PSI for a numeric feature: bins are the reference deciles; missing values get their own bin.

    Features with few distinct values (yes/no flags, counts) end up with fewer bins, because
    repeated decile edges are merged.
    """
    ref = reference.to_numpy(dtype=float)
    cur = current.to_numpy(dtype=float)
    edges = np.unique(np.nanquantile(ref, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    if len(edges) < 3:  # a constant feature: compare "value" against "missing" only
        edges = np.array([-np.inf, np.inf])

    def shares(x: np.ndarray) -> np.ndarray:
        missing = np.isnan(x)
        counts = np.histogram(x[~missing], bins=edges)[0]
        return np.append(counts, missing.sum()) / len(x)

    return psi_from_shares(shares(ref), shares(cur))


def categorical_psi(reference: pd.Series, current: pd.Series) -> float:
    levels = sorted(set(reference.unique()) | set(current.unique()))
    e = reference.value_counts(normalize=True).reindex(levels, fill_value=0).to_numpy()
    a = current.value_counts(normalize=True).reindex(levels, fill_value=0).to_numpy()
    return psi_from_shares(e, a)


def psi_status(value: float) -> str:
    return "red" if value > PSI_RED else "amber" if value >= PSI_AMBER else "green"


# ---------------------------------------------------------------- data

def month_label(ts: pd.Series) -> pd.Series:
    """Calendar months; June is only 21-30 June in the test period, so it says so."""
    label = ts.dt.strftime("%b %Y")
    return label.where(label != "Jun 2020", "Jun 2020 (21-30)")


def load_outcomes() -> pd.DataFrame:
    """Test-month payments with the model's route, the label and gender (aggregated below, never output)."""
    sql = """
        SELECT s.trans_num, s.trans_ts, s.amt::float AS amt, s.is_fraud, d.route, a.gender
        FROM analytics.stg_transactions s
        JOIN scoring.decisions d USING (trans_num)
        JOIN analytics_restricted.fairness_attributes a USING (trans_num)
        WHERE s.source_file = 'fraudTest.csv'
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    df["trans_ts"] = pd.to_datetime(df["trans_ts"])
    return df


# ---------------------------------------------------------------- the four checks

def input_and_score_drift(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for month, part in test.groupby("month", sort=False):
        for feature in NUMERIC_FEATURES + ["fraud_probability"]:
            value = numeric_psi(train[feature], part[feature])
            kind = "score" if feature == "fraud_probability" else "input"
            rows.append({"month": month, "check": kind, "metric": feature, "value": value,
                         "status": psi_status(value)})
        value = categorical_psi(train["category"], part["category"])
        rows.append({"month": month, "check": "input", "metric": "category", "value": value,
                     "status": psi_status(value)})
    return pd.DataFrame(rows)


def seasonal_checks(train: pd.DataFrame, test: pd.DataFrame, drift: pd.DataFrame) -> pd.DataFrame:
    """For every amber or red feature, compare with the same calendar month a year earlier.

    If the month looks like its own month last year (PSI below 0.10), the drift is seasonal,
    not a change in the customer base, and the status says so.
    """
    rows = []
    flagged = drift[drift["status"].isin(["amber", "red"]) & (drift["check"] == "input")]
    for r in flagged.itertuples():
        month_number = test.loc[test["month"] == r.month, "trans_ts"].dt.month.iloc[0]
        last_year = train[train["trans_ts"].dt.month == month_number]
        if r.metric == "category":
            value = categorical_psi(last_year["category"], test.loc[test["month"] == r.month, "category"])
        else:
            value = numeric_psi(last_year[r.metric], test.loc[test["month"] == r.month, r.metric])
        rows.append({"month": r.month, "check": "seasonal", "metric": r.metric, "value": value,
                     "baseline": r.value, "status": "green" if value < PSI_AMBER else psi_status(value)})
    return pd.DataFrame(rows)


def outcome_checks(df: pd.DataFrame) -> pd.DataFrame:
    def summary(part: pd.DataFrame) -> dict:
        fraud = part[part["is_fraud"] == 1]
        genuine = part[part["is_fraud"] == 0]
        stopped = fraud["route"] != "approve"
        analyst = part[part["route"] == "analyst_review"]
        days = part["trans_ts"].dt.normalize().nunique()
        return {
            "fraud_value_stopped_pct": 100 * fraud.loc[stopped, "amt"].sum() / fraud["amt"].sum(),
            "analyst_alerts_per_day": len(analyst) / days,
            "step_ups_per_day": (part["route"] == "step_up").sum() / days,
            "declines_per_day": (part["route"] == "decline").sum() / days,
            "analyst_hit_rate_pct": 100 * analyst["is_fraud"].mean() if len(analyst) else np.nan,
            "genuine_interrupted_per_10k": 1e4 * (genuine["route"] != "approve").mean(),
        }

    baseline = summary(df)
    rows = []
    for month, part in df.groupby("month", sort=False):
        for metric, value in summary(part).items():
            status = "info"
            if metric == "fraud_value_stopped_pct":
                gap = baseline[metric] - value
                status = "red" if gap > VALUE_RED_PTS else "amber" if gap > VALUE_AMBER_PTS else "green"
            rows.append({"month": month, "check": "outcome", "metric": metric, "value": value,
                         "baseline": baseline[metric], "status": status})
    return pd.DataFrame(rows)


def fairness_checks(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    genuine = df[df["is_fraud"] == 0].assign(interrupted=lambda d: d["route"] != "approve")
    for month, part in genuine.groupby("month", sort=False):
        overall = part["interrupted"].mean()
        for gender, g in part.groupby("gender"):
            rate = g["interrupted"].mean()
            low, _ = wilson(np.array([g["interrupted"].sum()]), np.array([len(g)]))
            ratio = rate / overall
            status = "red" if low[0] > FAIR_RED * overall else "amber" if ratio >= FAIR_AMBER else "green"
            rows.append({"month": month, "check": "fairness", "metric": f"interruption_ratio_{gender}",
                         "value": ratio, "baseline": 1.0, "status": status})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- outputs

def plot_heatmap(drift: pd.DataFrame, months: list[str]) -> None:
    order = ["fraud_probability", "category"] + NUMERIC_FEATURES
    grid = drift.pivot(index="metric", columns="month", values="value").reindex(index=order, columns=months)
    fig, ax = plt.subplots(figsize=(10, 7.5), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for i, metric in enumerate(order):
        for j, month in enumerate(months):
            value = grid.loc[metric, month]
            status = psi_status(value)
            if status in STATUS_COLOURS:
                ax.add_patch(plt.Rectangle((j - 0.48, i - 0.45), 0.96, 0.9, color=STATUS_COLOURS[status]))
            marker = {"amber": " ▲", "red": " ●"}.get(status, "")
            colour = "#0b0b0b" if status == "amber" else "white" if status == "red" else INK_2
            ax.text(j, i, f"{value:.2f}{marker}", ha="center", va="center", fontsize=9, color=colour)
    ax.set_xlim(-0.5, len(months) - 0.5)
    ax.set_ylim(len(order) - 0.5, -0.5)
    ax.set_xticks(range(len(months)), [m.replace(" 2020", "") for m in months], color=INK_2)
    ax.set_yticks(range(len(order)), [FEATURE_LABELS[m] for m in order], color=INK_2)
    ax.axhline(0.5, color=INK_2, linewidth=0.8)
    ax.tick_params(length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_title("Drift against the training months, PSI by month (2020)", loc="left", color=INK, fontsize=12,
                 pad=12)
    fig.text(0.01, 0.01, "Unfilled: stable (below 0.10)    ▲ Amber: watch (0.10 to 0.25)    "
             "● Red: act (above 0.25)", color=INK_2, fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIGURES / "drift_psi.png", dpi=160)
    plt.close(fig)


DDL = """
CREATE SCHEMA IF NOT EXISTS monitoring;
DROP TABLE IF EXISTS monitoring.drift_monthly;
CREATE TABLE monitoring.drift_monthly (
    month       TEXT NOT NULL,
    check_type  TEXT NOT NULL CHECK (check_type IN ('input', 'score', 'seasonal', 'outcome', 'fairness')),
    metric      TEXT NOT NULL,
    value       DOUBLE PRECISION,
    baseline    DOUBLE PRECISION,
    status      TEXT NOT NULL CHECK (status IN ('green', 'amber', 'red', 'info')),
    model_version TEXT NOT NULL,
    run_at      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (month, check_type, metric)
);
"""


def write_table(results: pd.DataFrame, version: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(DDL)
        cur.executemany(
            "INSERT INTO monitoring.drift_monthly (month, check_type, metric, value, baseline, status, model_version)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [(r.month, r.check, r.metric, None if pd.isna(r.value) else float(r.value),
              None if pd.isna(r.baseline) else float(r.baseline), r.status, version)
             for r in results.itertuples()])


def main() -> None:
    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    model = mlflow.xgboost.load_model(MODEL_URI)
    version = mlflow.MlflowClient().get_model_version_by_alias("fraud-xgboost", "champion").version
    features = model.get_booster().feature_names
    categories = [c.removeprefix("cat_") for c in features if c.startswith("cat_")]

    print("Loading training and test months ...")
    train = load_training_file("fraudTrain.csv")
    test = load_training_file("fraudTest.csv")
    # Score baseline: the champion's scores on the months it was trained on (the development sample).
    train["fraud_probability"] = model.predict_proba(xgb_matrix(train, categories)[features])[:, 1]
    test["fraud_probability"] = model.predict_proba(xgb_matrix(test, categories)[features])[:, 1]
    test["month"] = month_label(test["trans_ts"])
    months = list(dict.fromkeys(test.sort_values("trans_ts")["month"]))

    outcomes = load_outcomes()
    outcomes["month"] = month_label(outcomes["trans_ts"])

    drift = input_and_score_drift(train, test)
    results = pd.concat([drift, seasonal_checks(train, test, drift), outcome_checks(outcomes),
                         fairness_checks(outcomes)], ignore_index=True)
    if "baseline" not in results:
        results["baseline"] = np.nan

    pd.set_option("display.width", 160)
    psi = results[results["check"].isin(["input", "score"])]
    print("\nPSI by month (rows: feature or score):")
    print(psi.pivot(index="metric", columns="month", values="value")[months].round(3).to_string())
    seasonal = results[results["check"] == "seasonal"]
    print("\nFlagged features against the same month last year (baseline = PSI against all training months):")
    seasonal = seasonal.assign(order=seasonal["month"].map(months.index)).sort_values(["order", "metric"])
    print(seasonal[["month", "metric", "baseline", "value", "status"]].round(3).to_string(index=False))
    for check in ("outcome", "fairness"):
        print(f"\n{check.title()} checks:")
        part = results[results["check"] == check]
        print(part.pivot(index="metric", columns="month", values="value")[months].round(2).to_string())
        flagged = part[part["status"].isin(["amber", "red"])]
        if len(flagged):
            print(flagged[["month", "metric", "value", "status"]].round(3).to_string(index=False))
    counts = results["status"].value_counts().to_dict()
    print(f"\nStatus counts: {counts}")

    plot_heatmap(psi, months)
    write_table(results, version)
    print("Wrote monitoring.drift_monthly and docs/figures/drift_psi.png")

    mlflow.set_experiment("monitoring")
    with mlflow.start_run(run_name="drift-test-months"):
        mlflow.log_params({"model_version": version, "reference": "training months", "bins": BINS,
                           "psi_amber": PSI_AMBER, "psi_red": PSI_RED})
        for status in ("green", "amber", "red"):
            mlflow.log_metric(f"{status}_checks", counts.get(status, 0))
        mlflow.log_text(results.round(5).to_csv(index=False), "drift_monthly.csv")
        mlflow.log_artifact(str(FIGURES / "drift_psi.png"), "figures")


if __name__ == "__main__":
    main()
