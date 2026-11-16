"""Turn fraud scores into actions, and actions into money.

What this script does, in order:
  1. Calibration check: does a score of 0.3 really mean a 30% chance of fraud?
     (validation months from the 2019-fit model, and test months from the champion model)
  2. Three policies, compared on the test months:
       Rules            the rules baseline's routes (analyst review / step-up / approve)
       Model, like-for-like   same three routes and same daily budgets as the rules, but
                              payments ranked by expected loss (probability x amount)
       Model, four routes     each payment gets its cheapest expected action (approve, in-app
                              step-up, analyst review, or decline and block), within analyst capacity
     Daily volume thresholds are set on the VALIDATION months and then applied to the test months.
  3. Confirm then block (lever A) for every policy: once fraud is stopped on a card, the card is
     blocked (after the block delay for analyst alerts, immediately for declines and failed
     step-ups) and later fraud on that card counts as prevented.
  4. Capacity curve: fraud $ protected against analyst alerts per day.
  5. Sensitivity analysis: each assumption moved down and up; effect on the annual saving.
  6. Writes the four-route decisions to scoring.decisions (read by the alert queue), charts to
     docs/figures/, and everything to the MLflow experiment 'decisioning'.

Assumptions live in config/decision_params.yaml.
Run from the repo root:  .venv/bin/python src/decisioning.py
"""

import copy
import io
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from load_data import REPO_ROOT, connect  # noqa: E402

PARAMS_FILE = REPO_ROOT / "config" / "decision_params.yaml"
FIGURES = REPO_ROOT / "docs" / "figures"
ROUTES = ["approve", "step_up", "analyst_review", "decline"]

# Reference palette (dataviz skill): fixed order, never cycled
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


# ---------------------------------------------------------------- data

def load_period(period: str) -> pd.DataFrame:
    """Payments with the champion-family XGBoost score, label, amount, card and rules route."""
    sql = """
        SELECT f.trans_num, f.trans_ts, f.card_token, f.amt::float AS amt, f.is_fraud,
               r.rules_route, s.fraud_probability AS p
        FROM analytics.fct_transaction_features f
        JOIN analytics.fct_rules_baseline r USING (trans_num)
        JOIN scoring.model_scores s USING (trans_num)
        WHERE s.model_name = 'xgboost' AND s.period = %s
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (period,))
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    df["trans_ts"] = pd.to_datetime(df["trans_ts"])
    df["expected_loss"] = df["p"] * df["amt"]
    return df.sort_values("trans_ts").reset_index(drop=True)


def days_in(df: pd.DataFrame) -> int:
    return df["trans_ts"].dt.normalize().nunique()


# ---------------------------------------------------------------- policies

def review_cost(P: dict) -> float:
    return P["analyst"]["hourly_cost_usd"] * P["analyst"]["minutes_per_review"] / 60


def action_costs(df: pd.DataFrame, P: dict) -> pd.DataFrame:
    """Expected cost of each action for each payment, given its fraud probability p.

    approve        the fraud loss if it is fraud
    step_up        challenge cost + loss if a fraudster passes + analyst review if a genuine
                   customer doesn't respond
    analyst_review one review (the payment is held; fraud is stopped, genuine is released)
    decline        the false-decline cost if it is genuine (fraud is fully stopped)
    """
    p, amt = df["p"].to_numpy(), df["amt"].to_numpy()
    loss = P["fraud"]["loss_rate"]
    su = P["step_up"]
    return pd.DataFrame({
        "approve": p * amt * loss,
        "step_up": su["cost_per_challenge_usd"] + p * su["fraud_pass_rate"] * amt * loss
                   + (1 - p) * (1 - su["genuine_confirm_rate"]) * review_cost(P),
        "analyst_review": np.full(len(df), review_cost(P)),
        "decline": (1 - p) * P["decline"]["false_decline_cost_usd"],
    })


def volume_threshold(values: np.ndarray, days: int, per_day: float) -> float:
    """The value above which, on average, `per_day` payments a day fall (set on validation)."""
    n = int(round(per_day * days))
    if n <= 0:
        return np.inf
    ranked = np.sort(values)[::-1]
    return ranked[min(n, len(ranked)) - 1]


def like_for_like(test: pd.DataFrame, valid: pd.DataFrame, P: dict,
                  analyst_per_day: float | None = None, step_up_per_day: float | None = None) -> np.ndarray:
    """Same three routes and budgets as the rules; payments ranked by expected loss."""
    a = P["analyst"]["alerts_per_day"] if analyst_per_day is None else analyst_per_day
    s = P["step_up"]["alerts_per_day"] if step_up_per_day is None else step_up_per_day
    t_analyst = volume_threshold(valid["expected_loss"].to_numpy(), days_in(valid), a)
    t_step_up = volume_threshold(valid["expected_loss"].to_numpy(), days_in(valid), a + s)
    el = test["expected_loss"].to_numpy()
    return np.where(el >= t_analyst, "analyst_review", np.where(el >= t_step_up, "step_up", "approve"))


def four_route(test: pd.DataFrame, valid: pd.DataFrame, P: dict) -> np.ndarray:
    """Cheapest expected action per payment, with analyst reviews capped at capacity.

    If more payments want an analyst than capacity allows, the ones with the lowest expected
    loss take their next-cheapest action instead. The cut-off is set on the validation months.
    """
    def cheapest(df):
        costs = action_costs(df, P)
        return costs, costs.idxmin(axis=1).to_numpy()

    v_costs, v_choice = cheapest(valid)
    wants_analyst_valid = valid["expected_loss"].to_numpy()[v_choice == "analyst_review"]
    t_capacity = volume_threshold(wants_analyst_valid, days_in(valid), P["analyst"]["alerts_per_day"])

    costs, choice = cheapest(test)
    over_capacity = (choice == "analyst_review") & (test["expected_loss"].to_numpy() < t_capacity)
    next_best = costs.drop(columns="analyst_review").idxmin(axis=1).to_numpy()
    return np.where(over_capacity, next_best, choice)


# ---------------------------------------------------------------- outcomes

def simulate(df: pd.DataFrame, routes: np.ndarray, P: dict) -> dict:
    """Money and workload for one policy, including confirm then block (lever A)."""
    rng = np.random.default_rng(P["reporting"]["random_seed"])
    draw = rng.random(len(df))                # same draws for every policy, so they're comparable
    fraud = df["is_fraud"].to_numpy() == 1
    amt, ts = df["amt"].to_numpy(), df["trans_ts"]
    su = P["step_up"]

    genuine_confirms = draw < su["genuine_confirm_rate"]
    fraud_passes = draw < su["fraud_pass_rate"]
    is_ = {r: routes == r for r in ROUTES}

    # When does each stopped fraud block its card?
    delay = pd.to_timedelta(P["fraud"]["block_delay_hours"], unit="h")
    block_at = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    block_at[fraud & is_["analyst_review"]] = ts[fraud & is_["analyst_review"]] + delay
    immediate = fraud & (is_["decline"] | (is_["step_up"] & ~fraud_passes))
    block_at[immediate] = ts[immediate]
    card_blocked_at = block_at.groupby(df["card_token"]).transform("min")
    stopped_by_block = fraud & (ts > card_blocked_at).to_numpy()

    live = ~stopped_by_block                  # payments still handled by their route
    lost = live & fraud & (is_["approve"] | (is_["step_up"] & fraud_passes))
    reviews = live & (is_["analyst_review"] | (is_["step_up"] & ~fraud & ~genuine_confirms))
    step_ups = live & is_["step_up"]
    false_declines = live & is_["decline"] & ~fraud

    days = days_in(df)
    loss = P["fraud"]["loss_rate"]
    cost = {
        "fraud_loss_usd": (amt * lost).sum() * loss,
        "analyst_cost_usd": reviews.sum() * review_cost(P),
        "step_up_cost_usd": step_ups.sum() * su["cost_per_challenge_usd"],
        "false_decline_cost_usd": false_declines.sum() * P["decline"]["false_decline_cost_usd"],
    }
    fraud_value = (amt * fraud).sum()
    stopped_by_route = fraud & (is_["analyst_review"] | is_["decline"] | (is_["step_up"] & ~fraud_passes))
    return {
        **cost,
        "total_cost_usd": sum(cost.values()),
        "fraud_value_protected_pct": 100 * (1 - (amt * lost).sum() / fraud_value),
        "fraud_value_caught_by_route_pct": 100 * (amt * stopped_by_route).sum() / fraud_value,
        "fraud_prevented_by_block_usd": (amt * stopped_by_block).sum(),
        "analyst_reviews_per_day": reviews.sum() / days,
        "analyst_hours_per_day": reviews.sum() * P["analyst"]["minutes_per_review"] / 60 / days,
        "step_ups_per_day": step_ups.sum() / days,
        "genuine_step_ups_per_day": (step_ups & ~fraud).sum() / days,
        "declines_per_day": (live & is_["decline"]).sum() / days,
        "genuine_declines_per_day": false_declines.sum() / days,
        "analyst_hit_rate_pct": 100 * (live & is_["analyst_review"] & fraud).sum()
                                / max((live & is_["analyst_review"]).sum(), 1),
    }


def annual(usd: float, days: int) -> float:
    return usd * 365 / days


# ---------------------------------------------------------------- reports

def calibration_table(df: pd.DataFrame) -> pd.DataFrame:
    edges = [0, 0.001, 0.01, 0.05, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
    bins = pd.cut(df["p"], edges, include_lowest=True)
    t = df.groupby(bins, observed=True).agg(payments=("p", "size"), mean_predicted=("p", "mean"),
                                            actual_rate=("is_fraud", "mean"))
    return t.reset_index().rename(columns={"p": "score_band"})


def style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=12)
    ax.set_xlabel(xlabel, color=INK_2)
    ax.set_ylabel(ylabel, color=INK_2)
    ax.tick_params(colors=INK_2)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def plot_calibration(valid_tab: pd.DataFrame, test_tab: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(7, 5), facecolor=SURFACE)
    ax.plot([0, 1], [0, 1], color=INK_2, linewidth=1, linestyle="--", label="Perfect calibration")
    for tab, colour, name in ((valid_tab, AQUA, "Validation months"), (test_tab, BLUE, "Test months")):
        ax.plot(tab["mean_predicted"], tab["actual_rate"], marker="o", markersize=8,
                linewidth=2, color=colour, label=name)
    style(ax, "Predicted fraud probability against actual fraud rate",
          "Mean predicted probability (score band)", "Actual fraud rate")
    ax.legend(frameon=False, labelcolor=INK_2)
    path = FIGURES / "calibration.png"
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_capacity(curve: pd.DataFrame, rules_point: dict) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 5), facecolor=SURFACE)
    ax.plot(curve["alerts_per_day"], curve["fraud_value_protected_pct"], color=BLUE, linewidth=2,
            marker="o", markersize=8, label="Model (ranked by expected loss)")
    ax.scatter([rules_point["analyst_reviews_per_day"]], [rules_point["fraud_value_protected_pct"]],
               s=90, color=ORANGE, zorder=3, label="Rules")
    ax.annotate(f"Rules: {rules_point['fraud_value_protected_pct']:.1f}%",
                (rules_point["analyst_reviews_per_day"], rules_point["fraud_value_protected_pct"]),
                textcoords="offset points", xytext=(10, -16), color=INK_2)
    style(ax, "Fraud \\$ protected against analyst workload (test months)",
          "Analyst alerts worked per day", "Fraud \\$ protected, with confirm then block (%)")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, labelcolor=INK_2, loc="lower right")
    path = FIGURES / "capacity_curve.png"
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_tornado(sens: pd.DataFrame, base: float) -> Path:
    sens = sens.sort_values("swing")
    fig, ax = plt.subplots(figsize=(8, 0.55 * len(sens) + 1.5), facecolor=SURFACE)
    y = np.arange(len(sens))
    ax.barh(y, sens["low_saving"] - base, left=base, color=AQUA, height=0.6, label="Assumption lower")
    ax.barh(y, sens["high_saving"] - base, left=base, color=BLUE, height=0.6, label="Assumption higher")
    ax.axvline(base, color=INK_2, linewidth=1)
    ax.set_yticks(y, sens["label"])
    style(ax, "Annual saving vs rules: sensitivity to each assumption",
          "Annual saving against the rules (US$)", "")
    ax.legend(frameon=False, labelcolor=INK_2, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"\\${v / 1e3:.0f}k"))
    path = FIGURES / "sensitivity_tornado.png"
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


SENSITIVITY = [  # (label, path in params, low, high)
    ("Analyst hourly cost (\\$16 / \\$48)", ("analyst", "hourly_cost_usd"), 16, 48),
    ("Minutes per review (2.5 / 7.5)", ("analyst", "minutes_per_review"), 2.5, 7.5),
    ("Analyst capacity per day (10 / 32)", ("analyst", "alerts_per_day"), 10, 32),
    ("Step-up cost (\\$0.25 / \\$0.75)", ("step_up", "cost_per_challenge_usd"), 0.25, 0.75),
    ("Genuine confirm rate (90% / 99%)", ("step_up", "genuine_confirm_rate"), 0.90, 0.99),
    ("Fraudster pass rate (5% / 20%)", ("step_up", "fraud_pass_rate"), 0.05, 0.20),
    ("False-decline cost (\\$10 / \\$30)", ("decline", "false_decline_cost_usd"), 10, 30),
    ("Loss rate on missed fraud (50% / 100%)", ("fraud", "loss_rate"), 0.5, 1.0),
    ("Block delay (15 min / 4 hours)", ("fraud", "block_delay_hours"), 0.25, 4),
]


def annual_saving(test, valid, P) -> float:
    rules = simulate(test, test["rules_route"].to_numpy(), P)
    model = simulate(test, four_route(test, valid, P), P)
    return annual(rules["total_cost_usd"] - model["total_cost_usd"], days_in(test))


def write_decisions(test: pd.DataFrame, routes: np.ndarray, P: dict) -> None:
    out = pd.DataFrame({"trans_num": test["trans_num"], "route": routes,
                        "fraud_probability": test["p"], "expected_loss_usd": test["expected_loss"].round(2)})
    buffer = io.StringIO()
    out.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS scoring.decisions;
            CREATE TABLE scoring.decisions (
                trans_num         TEXT PRIMARY KEY,
                route             TEXT NOT NULL CHECK (route IN ('approve','step_up','analyst_review','decline')),
                fraud_probability DOUBLE PRECISION NOT NULL,
                expected_loss_usd NUMERIC(12,2) NOT NULL
            );""")
        with cur.copy("COPY scoring.decisions FROM STDIN WITH (FORMAT csv)") as copy_:
            copy_.write(buffer.read())
        conn.commit()


def main() -> None:
    P = yaml.safe_load(PARAMS_FILE.read_text())
    FIGURES.mkdir(parents=True, exist_ok=True)
    valid, test = load_period("validation"), load_period("test")
    test_days = days_in(test)
    print(f"Validation: {len(valid):,} payments over {days_in(valid)} days.  "
          f"Test: {len(test):,} payments over {test_days} days.\n")

    # 1. Calibration
    valid_cal, test_cal = calibration_table(valid), calibration_table(test)
    print("Calibration on the test months (champion model):")
    print(test_cal.round(4).to_string(index=False), "\n")

    # 2-3. Policies, with confirm then block
    policies = {
        "No controls (approve all)": np.full(len(test), "approve"),
        "Rules": test["rules_route"].to_numpy(),
        "Model, like-for-like": like_for_like(test, valid, P),
        "Model, four routes": four_route(test, valid, P),
    }
    results = {name: simulate(test, routes, P) for name, routes in policies.items()}
    table = pd.DataFrame(results).T
    table["annual_total_cost_usd"] = table["total_cost_usd"].apply(lambda v: annual(v, test_days))
    show = ["fraud_value_caught_by_route_pct", "fraud_value_protected_pct", "fraud_loss_usd",
            "analyst_reviews_per_day", "analyst_hit_rate_pct", "step_ups_per_day", "genuine_step_ups_per_day",
            "declines_per_day", "genuine_declines_per_day", "total_cost_usd", "annual_total_cost_usd"]
    print("Policies on the test months (confirm then block applied to all):")
    print(table[show].round(2).to_string(), "\n")

    # 4. Capacity curve (analyst route only, ranked by expected loss)
    curve_rows = []
    for per_day in [1, 2, 3, 5, 8, 10, 15, 21, 30, 40, 60]:
        routes = like_for_like(test, valid, P, analyst_per_day=per_day, step_up_per_day=0)
        r = simulate(test, routes, P)
        curve_rows.append({"alerts_per_day": r["analyst_reviews_per_day"], "target_per_day": per_day,
                           "fraud_value_protected_pct": r["fraud_value_protected_pct"],
                           "fraud_value_caught_by_route_pct": r["fraud_value_caught_by_route_pct"],
                           "analyst_hit_rate_pct": r["analyst_hit_rate_pct"]})
    curve = pd.DataFrame(curve_rows)
    print("Capacity curve (model, analyst route only):")
    print(curve.round(1).to_string(index=False), "\n")

    # 5. Sensitivity
    base = annual_saving(test, valid, P)
    sens_rows = []
    for label, (section, key), low, high in SENSITIVITY:
        savings = []
        for value in (low, high):
            P2 = copy.deepcopy(P)
            P2[section][key] = value
            savings.append(annual_saving(test, valid, P2))
        sens_rows.append({"label": label, "low_saving": savings[0], "high_saving": savings[1],
                          "swing": abs(savings[1] - savings[0])})
    sens = pd.DataFrame(sens_rows)
    print(f"Base annual saving of 'Model, four routes' against the rules: ${base:,.0f}")
    print(sens.sort_values("swing", ascending=False).round(0).to_string(index=False), "\n")

    # 6. Outputs
    figures = [plot_calibration(valid_cal, test_cal), plot_capacity(curve, results["Rules"]), plot_tornado(sens, base)]
    write_decisions(test, policies["Model, four routes"], P)
    print("Wrote scoring.decisions (Model, four routes) and charts:", ", ".join(f.name for f in figures))

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment("decisioning")
    with mlflow.start_run(run_name="policy-comparison-test-months"):
        mlflow.log_params({f"{s}.{k}": v for s, d in P.items() for k, v in d.items()})
        for name, r in results.items():
            slug = name.lower().replace(" ", "_").replace(",", "").replace("(", "").replace(")", "")
            mlflow.log_metrics({f"{slug}.{k}": float(v) for k, v in r.items()})
        mlflow.log_metric("annual_saving_vs_rules_usd", base)
        for f in figures:
            mlflow.log_artifact(str(f), "figures")
        mlflow.log_text(table.round(4).to_csv(), "policy_comparison.csv")
        mlflow.log_text(curve.round(4).to_csv(index=False), "capacity_curve.csv")
        mlflow.log_text(sens.round(2).to_csv(index=False), "sensitivity.csv")
        mlflow.log_text(test_cal.round(6).to_csv(index=False), "calibration_test.csv")
        mlflow.log_text(valid_cal.round(6).to_csv(index=False), "calibration_validation.csv")


if __name__ == "__main__":
    main()
