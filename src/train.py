"""Train and compare the fraud models on the validation months.

Design (agreed decisions are in docs/decision_log.md, E12 to E16):
  - Fit on calendar 2019; compare on 1 Jan to 21 Jun 2020 (the rest of the training file).
    The test months (21 Jun to Dec 2020) are NOT read here at all.
  - No class reweighting: models learn the true fraud rate, so probabilities stay honest.
  - Category is one-hot encoded for both models.
  - Logistic regression: missing history filled with neutral values plus a has_history flag;
    skewed features log-transformed and scaled. XGBoost: missing values handled natively.
  - Small hyperparameter search (about 20 XGBoost settings, 6 logistic regression strengths).
  - Every run is logged to MLflow. Selection by PR-AUC; business metrics reported alongside.

Run from the repo root:  .venv/bin/python src/train.py
"""

import itertools
import os
import random
import time

import mlflow
import mlflow.sklearn
import mlflow.xgboost
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from load_data import connect  # also loads .env

EXPERIMENT = "fraud-model-selection"
FIT_END = "2020-01-01"          # fit on payments before this date (calendar 2019)
SEED = 42

NUMERIC_FEATURES = [
    "amt", "hour_of_day",
    "txn_count_1h", "txn_count_24h", "amt_sum_24h",
    "prior_txn_count", "amt_vs_avg", "distance_km", "is_new_merchant", "secs_since_last",
    "amt_vs_category_avg", "is_new_category", "hour_band_share",
    "small_txn_count_24h", "spend_24h_vs_daily_avg",
]

# Logistic regression only: values used when a card has no history yet.
# Ratios get 1.0 ("same as usual"); hour_band_share gets 1/6 (all six 4-hour bands equally likely).
# secs_since_last gets the median of the fit months (filled in at run time).
NEUTRAL_FILL = {
    "amt_vs_avg": 1.0,
    "amt_vs_category_avg": 1.0,
    "spend_24h_vs_daily_avg": 1.0,
    "hour_band_share": 1 / 6,
}

# Logistic regression only: heavily right-skewed features are log-transformed so a few
# very large values don't dominate a linear model.
LOG_FEATURES = [
    "amt", "txn_count_1h", "txn_count_24h", "amt_sum_24h", "prior_txn_count", "amt_vs_avg",
    "distance_km", "secs_since_last", "amt_vs_category_avg", "small_txn_count_24h",
    "spend_24h_vs_daily_avg",
]

XGB_GRID = {
    "n_estimators": [200, 400, 800],
    "max_depth": [3, 4, 6, 8],
    "learning_rate": [0.05, 0.1, 0.2],
    "subsample": [0.8, 1.0],
    "colsample_bytree": [0.8, 1.0],
    "min_child_weight": [1, 5],
}
XGB_TRIALS = 20
LR_STRENGTHS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]  # C: smaller = stronger regularisation


# ---------------------------------------------------------------- data

def load_training_file(source_file: str = "fraudTrain.csv") -> pd.DataFrame:
    """Features, label and the rules' route for every payment in one source file.

    train.py only ever reads the training file; final_model.py reads the test file once.
    """
    assert source_file in ("fraudTrain.csv", "fraudTest.csv")
    sql = f"""
        SELECT f.trans_num, f.trans_ts, f.card_token, f.category,
               {', '.join('f.' + c for c in NUMERIC_FEATURES)},
               f.is_fraud, r.rules_route
        FROM analytics.fct_transaction_features f
        JOIN analytics.fct_rules_baseline r USING (trans_num)
        WHERE f.source_file = '{source_file}'
        -- Fixed row order, so a rebuilt database gives an identical model and results (TC-68).
        ORDER BY f.trans_ts, f.trans_num
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    for col in NUMERIC_FEATURES:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    df["trans_ts"] = pd.to_datetime(df["trans_ts"])
    return df


def one_hot(df: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    """One yes/no column per category, using the category list from the fit months."""
    return pd.DataFrame({f"cat_{c}": (df["category"] == c).astype(float) for c in categories},
                        index=df.index)


def xgb_matrix(df: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    """XGBoost input: numeric features as they are (missing stays missing) plus one-hot category."""
    return pd.concat([df[NUMERIC_FEATURES], one_hot(df, categories)], axis=1)


def lr_matrix(df: pd.DataFrame, categories: list[str], secs_fill: float) -> pd.DataFrame:
    """Logistic regression input: neutral fills, has_history flag, log transforms, one-hot."""
    x = df[NUMERIC_FEATURES].copy()
    x["has_history"] = (df["prior_txn_count"] > 0).astype(float)
    x = x.fillna({**NEUTRAL_FILL, "secs_since_last": secs_fill})
    for col in LOG_FEATURES:
        x[col] = np.log1p(x[col].clip(lower=0))
    return pd.concat([x, one_hot(df, categories)], axis=1)


# ---------------------------------------------------------------- metrics

def score_metrics(y: np.ndarray, p: np.ndarray, amt: np.ndarray, k: int) -> dict:
    """Ranking, calibration and business metrics for one set of scores.

    k = number of payments the rules sent to analysts over the same months, so the model is
    judged at exactly the same analyst workload as the rules.
    """
    top_k = np.argsort(-p)[:k]
    fraud_value = (amt * y).sum()
    return {
        "pr_auc": average_precision_score(y, p),
        "roc_auc": roc_auc_score(y, p),
        "brier": brier_score_loss(y, p),
        "mean_predicted_pct": 100 * p.mean(),
        "actual_fraud_pct": 100 * y.mean(),
        "hit_rate_at_rules_volume_pct": 100 * y[top_k].mean(),
        "recall_at_rules_volume_pct": 100 * y[top_k].sum() / y.sum(),
        "value_caught_at_rules_volume_pct": 100 * (amt[top_k] * y[top_k]).sum() / fraud_value,
    }


def warn_if_too_good(name: str, metrics: dict) -> None:
    """Project rule: results near perfect are treated as a bug until proven otherwise."""
    if metrics["roc_auc"] > 0.995 or metrics["pr_auc"] > 0.97:
        print(f"  !! {name}: ROC-AUC {metrics['roc_auc']:.4f}, PR-AUC {metrics['pr_auc']:.4f} "
              f"looks too good - investigate for leakage before trusting it")


# ---------------------------------------------------------------- main

def main() -> None:
    started = time.time()
    df = load_training_file()
    fit = df[df["trans_ts"] < FIT_END].reset_index(drop=True)
    valid = df[df["trans_ts"] >= FIT_END].reset_index(drop=True)
    categories = sorted(fit["category"].unique())
    secs_fill = float(fit["secs_since_last"].median())

    y_fit, y_valid = fit["is_fraud"].to_numpy(), valid["is_fraud"].to_numpy()
    amt_valid = valid["amt"].to_numpy()
    rules_alerts = valid["rules_route"].eq("analyst_review").to_numpy()
    k = int(rules_alerts.sum())
    valid_days = (valid["trans_ts"].max().normalize() - valid["trans_ts"].min().normalize()).days + 1

    print(f"Fit months:   {fit['trans_ts'].min():%d %b %Y} to {fit['trans_ts'].max():%d %b %Y}  "
          f"{len(fit):,} payments, {y_fit.sum():,} fraud")
    print(f"Validation:   {valid['trans_ts'].min():%d %b %Y} to {valid['trans_ts'].max():%d %b %Y}  "
          f"{len(valid):,} payments, {y_valid.sum():,} fraud")
    print(f"Rules volume: {k:,} analyst alerts ({k / valid_days:.1f} a day) - models are compared at this volume\n")

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment(EXPERIMENT)
    common_params = {"fit_window": f"2019-01-01 to {FIT_END} (exclusive)",
                     "validation_window": f"{FIT_END} to 2020-06-21",
                     "class_weighting": "none", "category_encoding": "one-hot"}
    results = []

    # 1. Rules baseline on the same months, so every comparison has its reference point
    with mlflow.start_run(run_name="rules-baseline"):
        hit = 100 * y_valid[rules_alerts].mean()
        value = 100 * (amt_valid * y_valid)[rules_alerts].sum() / (amt_valid * y_valid).sum()
        mlflow.set_tags({"model_family": "rules"})
        mlflow.log_params({**common_params, "rules": "A2, B2 to analyst review"})
        mlflow.log_metrics({"hit_rate_at_rules_volume_pct": hit,
                            "recall_at_rules_volume_pct": 100 * y_valid[rules_alerts].sum() / y_valid.sum(),
                            "value_caught_at_rules_volume_pct": value,
                            "alerts_per_day": k / valid_days})
        results.append({"run": "rules-baseline", "family": "rules",
                        "hit_rate_at_rules_volume_pct": hit, "value_caught_at_rules_volume_pct": value})

    # 2. Logistic regression across six regularisation strengths
    x_fit_lr, x_valid_lr = lr_matrix(fit, categories, secs_fill), lr_matrix(valid, categories, secs_fill)
    best = {}
    for c in LR_STRENGTHS:
        name = f"logreg-C{c:g}"
        model = Pipeline([("scale", StandardScaler()),
                          ("logreg", LogisticRegression(C=c, max_iter=2000))])
        t0 = time.time()
        model.fit(x_fit_lr, y_fit)
        p = model.predict_proba(x_valid_lr)[:, 1]
        m = score_metrics(y_valid, p, amt_valid, k)
        with mlflow.start_run(run_name=name) as run:
            mlflow.set_tags({"model_family": "logistic_regression"})
            mlflow.log_params({**common_params, "C": c, "features": len(x_fit_lr.columns),
                               "missing_history": "neutral fill + has_history flag",
                               "transforms": "log1p on skewed features, standard scaling"})
            mlflow.log_metrics({**m, "fit_seconds": time.time() - t0})
            mlflow.log_dict({"features": list(x_fit_lr.columns)}, "features.json")
        results.append({"run": name, "family": "logistic_regression", "run_id": run.info.run_id, **m})
        if m["pr_auc"] > best.get("logistic_regression", (None, -1))[1]:
            best["logistic_regression"] = (run.info.run_id, m["pr_auc"], model, x_valid_lr.iloc[:5])
        print(f"{name:<22} PR-AUC {m['pr_auc']:.4f}  ROC-AUC {m['roc_auc']:.4f}  "
              f"value caught {m['value_caught_at_rules_volume_pct']:.1f}%  ({time.time() - t0:.0f}s)")
        warn_if_too_good(name, m)

    # 3. XGBoost across a fixed random sample of settings (same sample every run)
    x_fit_xgb, x_valid_xgb = xgb_matrix(fit, categories), xgb_matrix(valid, categories)
    all_settings = [dict(zip(XGB_GRID, values)) for values in itertools.product(*XGB_GRID.values())]
    for i, settings in enumerate(random.Random(SEED).sample(all_settings, XGB_TRIALS), start=1):
        name = f"xgboost-{i:02d}"
        model = XGBClassifier(**settings, tree_method="hist", eval_metric="aucpr",
                              random_state=SEED, n_jobs=-1)
        t0 = time.time()
        model.fit(x_fit_xgb, y_fit)
        p = model.predict_proba(x_valid_xgb)[:, 1]
        m = score_metrics(y_valid, p, amt_valid, k)
        with mlflow.start_run(run_name=name) as run:
            mlflow.set_tags({"model_family": "xgboost"})
            mlflow.log_params({**common_params, **settings, "features": len(x_fit_xgb.columns),
                               "missing_history": "native missing-value handling"})
            mlflow.log_metrics({**m, "fit_seconds": time.time() - t0})
            mlflow.log_dict({"features": list(x_fit_xgb.columns)}, "features.json")
        results.append({"run": name, "family": "xgboost", "run_id": run.info.run_id, **m})
        if m["pr_auc"] > best.get("xgboost", (None, -1))[1]:
            best["xgboost"] = (run.info.run_id, m["pr_auc"], model, x_valid_xgb.iloc[:5])
        print(f"{name:<22} PR-AUC {m['pr_auc']:.4f}  ROC-AUC {m['roc_auc']:.4f}  "
              f"value caught {m['value_caught_at_rules_volume_pct']:.1f}%  ({time.time() - t0:.0f}s)  {settings}")
        warn_if_too_good(name, m)

    # 4. Save the best model of each family into its own run, and tag it
    for family, (run_id, _, model, example) in best.items():
        with mlflow.start_run(run_id=run_id):
            mlflow.set_tag("best_in_family", "true")
            if family == "xgboost":
                mlflow.xgboost.log_model(model, "model", input_example=example)
            else:
                mlflow.sklearn.log_model(model, "model", input_example=example)

    summary = pd.DataFrame(results)
    cols = ["run", "pr_auc", "roc_auc", "brier", "mean_predicted_pct", "actual_fraud_pct",
            "hit_rate_at_rules_volume_pct", "value_caught_at_rules_volume_pct"]
    print("\nBest of each family, plus the rules (validation months):")
    best_runs = [r for r in summary.sort_values("pr_auc", ascending=False).groupby("family").head(1)["run"]]
    print(summary[summary["run"].isin(best_runs + ["rules-baseline"])][cols].round(4).to_string(index=False))
    print(f"\nDone in {(time.time() - started) / 60:.1f} minutes. Runs are in MLflow experiment '{EXPERIMENT}'.")


if __name__ == "__main__":
    main()
