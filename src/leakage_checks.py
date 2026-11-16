"""Leakage diagnostics for a result that looks too good.

Project rule: near-perfect scores are treated as a bug until proven otherwise. These checks
use the same fit months (2019) and validation months (Jan to 21 Jun 2020) as train.py, and
the settings of the best XGBoost run, and log everything to the MLflow experiment
'leakage-checks'.

  1. Current-payment-only model: amount, category and hour only. No history, no windows,
     so no possible time leakage. If this alone scores near-perfectly, the separability
     comes from how the simulator generates fraud, not from our features.
  2. Shuffled labels: fraud labels in the fit months are scrambled. A leak-free pipeline
     must then score about 0.5 ROC-AUC (no better than random).
  3. Feature importance: no single feature should dominate suspiciously.
  4. Without fraud-only cards: score the validation months excluding the 91 cards that
     contain nothing but fraud, to show the result doesn't rest on them.

Run from the repo root:  .venv/bin/python src/leakage_checks.py
"""

import os

import mlflow
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from xgboost import XGBClassifier

from load_data import connect
from train import FIT_END, SEED, load_training_file, xgb_matrix

# Settings of the best XGBoost run on the validation months (xgboost-10)
BEST_SETTINGS = {"n_estimators": 800, "max_depth": 4, "learning_rate": 0.05,
                 "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 1}


def fit_and_score(x_fit, y_fit, x_valid, y_valid) -> tuple[XGBClassifier, dict]:
    model = XGBClassifier(**BEST_SETTINGS, tree_method="hist", random_state=SEED, n_jobs=-1)
    model.fit(x_fit, y_fit)
    p = model.predict_proba(x_valid)[:, 1]
    return model, {"pr_auc": average_precision_score(y_valid, p), "roc_auc": roc_auc_score(y_valid, p)}


def fraud_only_cards() -> set[str]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT card_token FROM analytics.fct_transaction_features
                       GROUP BY card_token HAVING min(is_fraud) = 1""")
        return {row[0] for row in cur.fetchall()}


def main() -> None:
    df = load_training_file()
    with connect() as conn, conn.cursor() as cur:   # card token, for check 4
        cur.execute("SELECT trans_num, card_token FROM analytics.fct_transaction_features "
                    "WHERE source_file = 'fraudTrain.csv'")
        df = df.merge(pd.DataFrame(cur.fetchall(), columns=["trans_num", "card_token"]), on="trans_num")
    fit = df[df["trans_ts"] < FIT_END].reset_index(drop=True)
    valid = df[df["trans_ts"] >= FIT_END].reset_index(drop=True)
    categories = sorted(fit["category"].unique())
    y_fit, y_valid = fit["is_fraud"].to_numpy(), valid["is_fraud"].to_numpy()
    x_fit, x_valid = xgb_matrix(fit, categories), xgb_matrix(valid, categories)

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment("leakage-checks")
    results = []

    # Reference: the full model, as in train.py
    full_model, m = fit_and_score(x_fit, y_fit, x_valid, y_valid)
    results.append(("0. Full model (14 features + category)", m))

    # 1. Current-payment-only model
    current_cols = ["amt", "hour_of_day"] + [c for c in x_fit.columns if c.startswith("cat_")]
    _, m = fit_and_score(x_fit[current_cols], y_fit, x_valid[current_cols], y_valid)
    results.append(("1. Amount + category + hour only (no history)", m))

    # 2. Shuffled labels in the fit months
    y_shuffled = np.random.default_rng(SEED).permutation(y_fit)
    _, m = fit_and_score(x_fit, y_shuffled, x_valid, y_valid)
    results.append(("2. Fit labels shuffled (must be ~0.5 ROC-AUC)", m))

    # 4. Without fraud-only cards in the validation months
    keep = ~valid["card_token"].isin(fraud_only_cards()).to_numpy()
    p = full_model.predict_proba(x_valid[keep])[:, 1]
    m = {"pr_auc": average_precision_score(y_valid[keep], p), "roc_auc": roc_auc_score(y_valid[keep], p)}
    results.append((f"4. Full model, fraud-only cards removed ({(~keep).sum():,} payments out)", m))

    for name, m in results:
        with mlflow.start_run(run_name=name[:60]):
            mlflow.log_params({"check": name, **BEST_SETTINGS})
            mlflow.log_metrics(m)
        print(f"{name:<62} PR-AUC {m['pr_auc']:.4f}   ROC-AUC {m['roc_auc']:.4f}")

    # 3. Feature importance (share of total gain) for the full model
    gain = pd.Series(full_model.get_booster().get_score(importance_type="total_gain"))
    share = (100 * gain / gain.sum()).sort_values(ascending=False)
    print("\n3. Feature importance, share of total gain (full model):")
    print(share.round(1).head(12).to_string())
    with mlflow.start_run(run_name="3. Feature importance"):
        mlflow.log_dict(share.round(3).to_dict(), "feature_importance_gain_pct.json")


if __name__ == "__main__":
    main()
