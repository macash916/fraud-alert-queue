"""Fairness audit (FCA Consumer Duty, Equality Act): does the queue treat customer groups fairly?

For the test months, by age band and by gender, for the rules and for the model's four-route policy:
  - Genuine customers interrupted: the share of GENUINE payments that were stepped up, declined or
    held for an analyst (per 10,000 genuine payments). This is the customer-harm side.
  - Fraud detected: the share of fraud payments and fraud value caught by the route.
    This is the protection side: is any group left less protected?
Every rate has a 95% Wilson confidence interval, so small groups are not over-read.

A group is flagged only when the difference is both material and statistically clear:
  - interruptions: the group's lower 95% bound is above 1.25x the overall rate
  - protection:    the group's upper 95% bound is below 0.8x the overall detection rate

Age and gender come from the restricted dbt model analytics_restricted.fairness_attributes.
They are never model features. This script outputs aggregates only.

Run from the repo root:  .venv/bin/python src/fairness.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from decisioning import BLUE, FIGURES, INK_2, ORANGE, SURFACE, style  # noqa: E402
from load_data import connect  # noqa: E402

AGE_ORDER = ["Under 18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
HIGHER_FLAG, LOWER_FLAG = 1.25, 0.8


def wilson(successes: np.ndarray, n: np.ndarray, z: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
    """95% Wilson score interval for a proportion (well behaved for small counts and rare events)."""
    n = np.maximum(n, 1)
    p = successes / n
    centre = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    return centre - half, centre + half


def load() -> pd.DataFrame:
    sql = """
        SELECT s.trans_num, s.is_fraud, s.amt::float AS amt, r.rules_route, d.route AS model_route,
               a.age_band, a.gender
        FROM analytics.stg_transactions s
        JOIN analytics.fct_rules_baseline r USING (trans_num)
        JOIN scoring.decisions d USING (trans_num)
        JOIN analytics_restricted.fairness_attributes a USING (trans_num)
        WHERE s.source_file = 'fraudTest.csv'
        -- Fixed row order, so a rebuilt database gives an identical model and results (TC-68).
        ORDER BY s.trans_ts, s.trans_num
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


def group_rates(df: pd.DataFrame, policy_col: str, by: str) -> pd.DataFrame:
    d = df.assign(interrupted=df[policy_col] != "approve", genuine=df["is_fraud"] == 0)
    rows = []
    groups = [("All customers", d)] + [(g, part) for g, part in d.groupby(by)]
    for name, part in groups:
        gen, fr = part[part["genuine"]], part[~part["genuine"]]
        rows.append({
            "group": name, "genuine_payments": len(gen), "genuine_interrupted": int(gen["interrupted"].sum()),
            "genuine_step_ups": int((gen[policy_col] == "step_up").sum()),
            "genuine_declines": int((gen[policy_col] == "decline").sum()),
            "genuine_analyst_holds": int((gen[policy_col] == "analyst_review").sum()),
            "fraud_payments": len(fr), "fraud_detected": int(fr["interrupted"].sum()),
            "fraud_value_detected_pct": 100 * (fr["amt"] * fr["interrupted"]).sum() / max(fr["amt"].sum(), 1e-9),
        })
    t = pd.DataFrame(rows)
    t["interrupted_per_10k"] = 1e4 * t["genuine_interrupted"] / t["genuine_payments"]
    lo, hi = wilson(t["genuine_interrupted"].to_numpy(), t["genuine_payments"].to_numpy())
    t["interrupted_per_10k_low"], t["interrupted_per_10k_high"] = 1e4 * lo, 1e4 * hi
    t["detection_pct"] = 100 * t["fraud_detected"] / t["fraud_payments"].clip(lower=1)
    lo, hi = wilson(t["fraud_detected"].to_numpy(), t["fraud_payments"].to_numpy())
    t["detection_pct_low"], t["detection_pct_high"] = 100 * lo, 100 * hi

    overall = t.iloc[0]
    t["interruption_ratio"] = t["interrupted_per_10k"] / overall["interrupted_per_10k"]
    t["detection_ratio"] = t["detection_pct"] / overall["detection_pct"]
    t["flag"] = np.where(t["interrupted_per_10k_low"] > HIGHER_FLAG * overall["interrupted_per_10k"],
                         "more interruptions", "")
    t["flag"] = np.where(t["detection_pct_high"] < LOWER_FLAG * overall["detection_pct"],
                         (t["flag"] + "; less protection").str.strip("; "), t["flag"])
    t.loc[0, "flag"] = ""
    return t


def plot(tables: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 6.5), facecolor=SURFACE)
    order = ["All customers"] + AGE_ORDER + ["F", "M"]
    y = {g: i for i, g in enumerate(reversed(order))}
    for (policy, colour, offset) in (("Rules", ORANGE, 0.15), ("Model, four routes", BLUE, -0.15)):
        t = pd.concat([tables[(policy, "age_band")], tables[(policy, "gender")].iloc[1:]])
        t = t[t["group"].isin(order)]
        ys = [y[g] + offset for g in t["group"]]
        ax.hlines(ys, t["interrupted_per_10k_low"], t["interrupted_per_10k_high"], color=colour, linewidth=2)
        ax.scatter(t["interrupted_per_10k"], ys, color=colour, s=60, zorder=3, label=policy)
    ax.set_yticks(list(y.values()), [{"F": "Female", "M": "Male"}.get(g, g) for g in y])
    style(ax, "Genuine customers interrupted, per 10,000 genuine payments (95% interval)",
          "Interruptions per 10,000 genuine payments (step-up, decline or analyst hold)", "")
    ax.legend(frameon=False, labelcolor=INK_2, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURES / "fairness_interruptions.png", dpi=160)
    plt.close(fig)


def main() -> None:
    df = load()
    tables = {}
    for policy, col in (("Rules", "rules_route"), ("Model, four routes", "model_route")):
        for by in ("age_band", "gender"):
            t = group_rates(df, col, by)
            if by == "age_band":
                t = pd.concat([t.iloc[:1], t.iloc[1:].set_index("group").reindex(AGE_ORDER).reset_index()])
            tables[(policy, by)] = t.reset_index(drop=True)

    show = ["group", "genuine_payments", "genuine_interrupted", "interrupted_per_10k", "interrupted_per_10k_low",
            "interrupted_per_10k_high", "interruption_ratio", "fraud_payments", "detection_pct",
            "fraud_value_detected_pct", "flag"]
    for (policy, by), t in tables.items():
        print(f"\n{policy} by {by}:")
        print(t[show].round(1).to_string(index=False))

    plot(tables)
    print("\nChart: docs/figures/fairness_interruptions.png")

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment("fairness")
    with mlflow.start_run(run_name="fairness-audit-test-months"):
        mlflow.log_params({"higher_flag_ratio": HIGHER_FLAG, "lower_flag_ratio": LOWER_FLAG,
                           "interval": "95% Wilson", "period": "test months"})
        for (policy, by), t in tables.items():
            mlflow.log_text(t.round(4).to_csv(index=False), f"{policy.replace(', ', '_').replace(' ', '_')}_{by}.csv")
            mlflow.log_metric(f"{policy.replace(', ', '_').replace(' ', '_')}.{by}.flags", int((t["flag"] != "").sum()))
        mlflow.log_artifact(str(FIGURES / "fairness_interruptions.png"), "figures")


if __name__ == "__main__":
    main()
