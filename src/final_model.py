"""Retrain the chosen models on all training months and evaluate ONCE on the test months.

  - Settings come from model selection on the validation months (src/train.py):
      XGBoost: run xgboost-10 (best PR-AUC, 0.983). Logistic regression: C = 0.01 (best PR-AUC, 0.682).
  - Both are retrained on the whole training file (1 Jan 2019 to 21 Jun 2020).
  - The test months (21 Jun to 31 Dec 2020) are scored once and compared with the rules at the
    rules' own analyst volume over the same months.
  - XGBoost is registered in MLflow as 'fraud-xgboost' with the alias 'champion'.
  - Scores are written to PostgreSQL table scoring.model_scores for the decisioning step and the app:
      period 'validation': the 2019-fit XGBoost on Jan to 21 Jun 2020 (out-of-sample, for calibration checks)
      period 'test':       the final models on the test months

Run from the repo root:  .venv/bin/python src/final_model.py
"""

import io
import os

import mlflow
import mlflow.sklearn
import mlflow.xgboost
import numpy as np
import pandas as pd
from mlflow import MlflowClient
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from load_data import connect
from train import FIT_END, SEED, load_training_file, lr_matrix, score_metrics, warn_if_too_good, xgb_matrix

XGB_SETTINGS = {"n_estimators": 800, "max_depth": 4, "learning_rate": 0.05,
                "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 1}
LR_C = 0.01
REGISTERED_MODEL = "fraud-xgboost"

SCORES_DDL = """
CREATE SCHEMA IF NOT EXISTS scoring;
DROP TABLE IF EXISTS scoring.model_scores;
CREATE TABLE scoring.model_scores (
    trans_num      TEXT    NOT NULL,
    model_name     TEXT    NOT NULL,   -- 'xgboost' or 'logistic_regression'
    model_version  TEXT    NOT NULL,   -- MLflow registered version, or 'fit-2019' for validation scores
    period         TEXT    NOT NULL,   -- 'validation' or 'test'
    fraud_probability DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (trans_num, model_name, period)
);
"""


def new_xgb() -> XGBClassifier:
    return XGBClassifier(**XGB_SETTINGS, tree_method="hist", random_state=SEED, n_jobs=-1)


def new_lr() -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("logreg", LogisticRegression(C=LR_C, max_iter=2000))])


def write_scores(frames: list[pd.DataFrame]) -> None:
    """Bulk-write scores with COPY (fast), replacing the table each run."""
    scores = pd.concat(frames, ignore_index=True)
    buffer = io.StringIO()
    scores.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(SCORES_DDL)
        with cur.copy("COPY scoring.model_scores (trans_num, model_name, model_version, period, "
                      "fraud_probability) FROM STDIN WITH (FORMAT csv)") as copy:
            copy.write(buffer.read())
        conn.commit()
    print(f"Wrote {len(scores):,} scores to scoring.model_scores")


def main() -> None:
    train = load_training_file("fraudTrain.csv")
    test = load_training_file("fraudTest.csv")
    categories = sorted(train["category"].unique())
    secs_fill = float(train["secs_since_last"].median())
    y_train, y_test = train["is_fraud"].to_numpy(), test["is_fraud"].to_numpy()
    amt_test = test["amt"].to_numpy()

    rules_alerts = test["rules_route"].eq("analyst_review").to_numpy()
    k = int(rules_alerts.sum())
    test_days = (test["trans_ts"].max().normalize() - test["trans_ts"].min().normalize()).days + 1
    print(f"Train: {len(train):,} payments ({y_train.sum():,} fraud).  "
          f"Test: {len(test):,} payments ({y_test.sum():,} fraud), {test_days} days.")
    print(f"Rules' analyst volume on the test months: {k:,} alerts ({k / test_days:.1f} a day)\n")

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment("final-evaluation")
    params = {"train_window": "2019-01-01 to 2020-06-21", "test_window": "2020-06-21 to 2020-12-31",
              "class_weighting": "none", "category_encoding": "one-hot"}
    rows = []

    # Rules on the test months
    rules_value = 100 * (amt_test * y_test)[rules_alerts].sum() / (amt_test * y_test).sum()
    rules_hit = 100 * y_test[rules_alerts].mean()
    with mlflow.start_run(run_name="rules-baseline-test"):
        mlflow.log_params({**params, "rules": "A2, B2 to analyst review"})
        mlflow.log_metrics({"hit_rate_at_rules_volume_pct": rules_hit,
                            "value_caught_at_rules_volume_pct": rules_value, "alerts_per_day": k / test_days})
    rows.append({"model": "Rules", "hit_rate_at_rules_volume_pct": rules_hit,
                 "value_caught_at_rules_volume_pct": rules_value})

    # Logistic regression, retrained on all training months
    lr = new_lr().fit(lr_matrix(train, categories, secs_fill), y_train)
    p_lr = lr.predict_proba(lr_matrix(test, categories, secs_fill))[:, 1]
    m_lr = score_metrics(y_test, p_lr, amt_test, k)
    with mlflow.start_run(run_name="logistic-regression-test"):
        mlflow.log_params({**params, "C": LR_C})
        mlflow.log_metrics(m_lr)
        mlflow.sklearn.log_model(lr, "model")
    rows.append({"model": "Logistic regression", **m_lr})

    # XGBoost, retrained on all training months, registered as champion
    x_train, x_test = xgb_matrix(train, categories), xgb_matrix(test, categories)
    xgb = new_xgb().fit(x_train, y_train)
    p_xgb = xgb.predict_proba(x_test)[:, 1]
    m_xgb = score_metrics(y_test, p_xgb, amt_test, k)
    warn_if_too_good("XGBoost on test months", m_xgb)
    with mlflow.start_run(run_name="xgboost-test") as run:
        mlflow.log_params({**params, **XGB_SETTINGS})
        mlflow.log_metrics(m_xgb)
        mlflow.log_dict({"features": list(x_train.columns), "categories": categories}, "features.json")
        info = mlflow.xgboost.log_model(xgb, "model", input_example=x_test.head(5).astype(float),
                                        registered_model_name=REGISTERED_MODEL)
    version = str(info.registered_model_version)
    MlflowClient().set_registered_model_alias(REGISTERED_MODEL, "champion", version)
    rows.append({"model": "XGBoost", **m_xgb})
    print(f"\nRegistered {REGISTERED_MODEL} version {version} as 'champion' (run {run.info.run_id})")

    # Out-of-sample validation scores from the 2019-fit XGBoost, for the calibration check
    fit = train[train["trans_ts"] < FIT_END]
    valid = train[train["trans_ts"] >= FIT_END]
    xgb_2019 = new_xgb().fit(xgb_matrix(fit, categories), fit["is_fraud"].to_numpy())
    p_valid = xgb_2019.predict_proba(xgb_matrix(valid, categories))[:, 1]

    write_scores([
        pd.DataFrame({"trans_num": valid["trans_num"], "model_name": "xgboost",
                      "model_version": "fit-2019", "period": "validation", "p": p_valid}),
        pd.DataFrame({"trans_num": test["trans_num"], "model_name": "xgboost",
                      "model_version": version, "period": "test", "p": p_xgb}),
        pd.DataFrame({"trans_num": test["trans_num"], "model_name": "logistic_regression",
                      "model_version": "final", "period": "test", "p": p_lr}),
    ])

    cols = ["model", "pr_auc", "roc_auc", "brier", "mean_predicted_pct", "actual_fraud_pct",
            "hit_rate_at_rules_volume_pct", "recall_at_rules_volume_pct", "value_caught_at_rules_volume_pct"]
    print(f"\nTest months (21 Jun to 31 Dec 2020), compared at the rules' volume of {k / test_days:.1f} alerts a day:")
    print(pd.DataFrame(rows).reindex(columns=cols).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
