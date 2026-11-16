"""Fairness audit: confidence intervals and the flag rule."""

import numpy as np
import pandas as pd
import pytest

from fairness import group_rates, wilson


def test_wilson_interval_known_values():
    low, high = wilson(np.array([5, 0]), np.array([10, 10]))
    assert low[0] == pytest.approx(0.2366, abs=1e-4) and high[0] == pytest.approx(0.7634, abs=1e-4)
    assert low[1] == pytest.approx(0.0, abs=1e-9) and high[1] == pytest.approx(0.2775, abs=1e-4)


def test_groups_are_flagged_for_more_interruptions_or_less_protection():
    rows = []
    # Group A: 30% of genuine customers interrupted; all fraud caught.
    rows += [("A", 0, "step_up")] * 300 + [("A", 0, "approve")] * 700 + [("A", 1, "decline")] * 50
    # Group B: 1% interrupted, but only 5 of 50 frauds caught.
    rows += [("B", 0, "step_up")] * 10 + [("B", 0, "approve")] * 990
    rows += [("B", 1, "decline")] * 5 + [("B", 1, "approve")] * 45
    df = pd.DataFrame(rows, columns=["group_col", "is_fraud", "route"]).assign(amt=100.0)
    flags = group_rates(df, "route", "group_col").set_index("group")["flag"]
    assert flags["All customers"] == ""
    assert flags["A"] == "more interruptions"
    assert flags["B"] == "less protection"
