"""Cost-based routing and the confirm-then-block simulation."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from decisioning import action_costs, four_route, review_cost, simulate, volume_threshold

PARAMS = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "decision_params.yaml").read_text())


def payments(rows: list[tuple]) -> pd.DataFrame:
    """rows: (fraud probability, amount); all on one day."""
    df = pd.DataFrame(rows, columns=["p", "amt"])
    df["expected_loss"] = df["p"] * df["amt"]
    df["trans_ts"] = pd.Timestamp("2020-07-01 12:00")
    return df


def test_review_cost_is_analyst_time():
    assert review_cost(PARAMS) == pytest.approx(32 * 5 / 60)   # $32 an hour, 5 minutes a review


@pytest.mark.parametrize("p, amount, cheapest", [
    (0.001, 10, "approve"),           # almost certainly genuine: any intervention costs more than the risk
    (0.05, 200, "step_up"),           # uncertain, mid value: a 50c in-app check is cheapest
    (0.6, 50, "analyst_review"),      # likely fraud, low value: one review beats a step-up a fraudster may pass
    (0.99, 1000, "decline"),          # near-certain fraud: decline and block
])
def test_each_payment_gets_its_cheapest_action(p, amount, cheapest):
    costs = action_costs(payments([(p, amount)]), PARAMS)
    assert costs.idxmin(axis=1).iloc[0] == cheapest


def test_volume_threshold():
    values = np.array([5, 4, 3, 2, 1])
    assert volume_threshold(values, days=1, per_day=2) == 4
    assert volume_threshold(values, days=1, per_day=0) == np.inf
    assert volume_threshold(values, days=1, per_day=10) == 1


def test_analyst_capacity_is_respected():
    params = {**PARAMS, "analyst": {**PARAMS["analyst"], "alerts_per_day": 2}}
    # Validation day: three payments want an analyst (expected loss 40, 30, 20); capacity is 2.
    valid = payments([(0.5, 80), (0.5, 60), (0.5, 40)])
    test = payments([(0.5, 70), (0.5, 50)])           # expected loss 35 (above the cut) and 25 (below)
    assert list(four_route(test, valid, params)) == ["analyst_review", "step_up"]


def card_timeline(block_delay_hours: float) -> dict:
    t0 = pd.Timestamp("2020-07-01 12:00")
    df = pd.DataFrame({
        "card_token": ["x", "x", "x", "y"],
        "trans_ts": [t0, t0 + pd.Timedelta("30min"), t0 + pd.Timedelta("2h"), t0],
        "amt": [100.0, 200.0, 300.0, 50.0],
        "is_fraud": [1, 1, 1, 0],
    })
    routes = np.array(["analyst_review", "approve", "approve", "approve"])
    params = {**PARAMS, "fraud": {**PARAMS["fraud"], "block_delay_hours": block_delay_hours}}
    return simulate(df, routes, params)


def test_confirm_then_block_stops_later_fraud_after_the_delay():
    result = card_timeline(block_delay_hours=1)
    assert result["fraud_loss_usd"] == 200              # 30 minutes later: card not yet blocked
    assert result["fraud_prevented_by_block_usd"] == 300  # 2 hours later: card already blocked


def test_instant_block_prevents_all_follow_on_fraud():
    result = card_timeline(block_delay_hours=0)
    assert result["fraud_loss_usd"] == 0
    assert result["fraud_prevented_by_block_usd"] == 500
