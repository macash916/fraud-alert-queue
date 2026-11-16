"""Headline results: rules, logistic regression and XGBoost on the test months, at the same workload.

Each approach sends the same number of payments to analyst review as the rules did (A2 and B2,
about 21 a day); everything else is approved. That makes the comparison fair: same analyst
budget, different choice of which payments to review.

For each: precision (hit rate), recall, PR-AUC, share of fraud value caught, and total cost
(fraud losses + analyst time) with confirm then block, using config/decision_params.yaml.

Writes docs/results_table.md (used in the README).
Run from the repo root:  .venv/bin/python src/results_table.py
"""

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score

from decisioning import PARAMS_FILE, REPO_ROOT, days_in, simulate
from load_data import connect


def load() -> pd.DataFrame:
    sql = """
        SELECT s.trans_num, s.trans_ts, s.card_token, s.amt::float AS amt, s.is_fraud, r.rules_route,
               x.fraud_probability AS p_xgb, l.fraud_probability AS p_lr
        FROM analytics.stg_transactions s
        JOIN analytics.fct_rules_baseline r USING (trans_num)
        JOIN scoring.model_scores x ON x.trans_num = s.trans_num AND x.model_name = 'xgboost' AND x.period = 'test'
        JOIN scoring.model_scores l ON l.trans_num = s.trans_num AND l.model_name = 'logistic_regression'
                                    AND l.period = 'test'
        WHERE s.source_file = 'fraudTest.csv'
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    df["trans_ts"] = pd.to_datetime(df["trans_ts"])
    return df.sort_values("trans_ts").reset_index(drop=True)


def evaluate(df: pd.DataFrame, reviewed: np.ndarray, score: np.ndarray | None, P: dict) -> dict:
    y, amt = df["is_fraud"].to_numpy(), df["amt"].to_numpy()
    routes = np.where(reviewed, "analyst_review", "approve")
    money = simulate(df, routes, P)
    return {
        "Analyst alerts a day": reviewed.sum() / days_in(df),
        "Precision (hit rate)": 100 * y[reviewed].mean(),
        "Recall (frauds caught)": 100 * y[reviewed].sum() / y.sum(),
        "PR-AUC": average_precision_score(y, score) if score is not None else np.nan,
        "Fraud value caught": 100 * (amt * y)[reviewed].sum() / (amt * y).sum(),
        "Fraud value protected incl. card blocks": money["fraud_value_protected_pct"],
        "Total cost": money["total_cost_usd"],
    }


def main() -> None:
    P = yaml.safe_load(PARAMS_FILE.read_text())
    df = load()
    rules = (df["rules_route"] == "analyst_review").to_numpy()   # A2 and B2: the rules' analyst alerts
    k = int(rules.sum())

    def top_k(p: np.ndarray) -> np.ndarray:
        chosen = np.zeros(len(p), dtype=bool)
        chosen[np.argsort(-p)[:k]] = True
        return chosen

    rows = {
        "Rules (A2, B2)": evaluate(df, rules, None, P),
        "Logistic regression": evaluate(df, top_k(df["p_lr"].to_numpy()), df["p_lr"].to_numpy(), P),
        "XGBoost (champion)": evaluate(df, top_k(df["p_xgb"].to_numpy()), df["p_xgb"].to_numpy(), P),
    }
    table = pd.DataFrame(rows).T
    print(table.round(3).to_string())

    fmt = {"Analyst alerts a day": "{:.1f}", "Precision (hit rate)": "{:.1f}%", "Recall (frauds caught)": "{:.1f}%",
           "PR-AUC": "{:.3f}", "Fraud value caught": "{:.1f}%",
           "Fraud value protected incl. card blocks": "{:.1f}%", "Total cost": "${:,.0f}"}
    lines = ["| Approach | " + " | ".join(fmt) + " |", "|---|" + "---|" * len(fmt)]
    for name, r in table.iterrows():
        cells = ["n/a" if pd.isna(r[c]) else f.format(r[c]) for c, f in fmt.items()]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    note = (f"Test months (21 Jun to 31 Dec 2020, {len(df):,} payments, {int(df['is_fraud'].sum()):,} frauds), "
            f"each approach reviewing the same {k:,} payments ({k / days_in(df):.1f} a day). Total cost = fraud "
            "losses + analyst time, with a confirmed fraud blocking the card after one hour. Simulated data; "
            "US dollars. Produced by `src/results_table.py`.\n\n"
            "Rules cost more here than in `business_case.md` ($86.8k) because this comparison uses analyst "
            "review only; the business case also counts the rules' D1 step-up route. Logistic regression "
            "catches more fraud value per alert than the rules but costs more overall: its alerts reach fewer "
            "of the compromised cards (208 of 218, against 216 for the rules and 218 for XGBoost), so fewer "
            "cards are blocked before the next fraud.")
    out = REPO_ROOT / "docs" / "results_table.md"
    out.write_text("# Results: rules against models at the same analyst workload\n\n" + "\n".join(lines)
                   + f"\n\n{note}\n")
    print(f"\nWrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
