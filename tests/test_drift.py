"""Drift monitoring: PSI behaves as expected and the alarm fires on real drift."""

import numpy as np
import pandas as pd

from drift import categorical_psi, month_label, numeric_psi, psi_status

rng = np.random.default_rng(42)
AMOUNTS = pd.Series(rng.lognormal(mean=4, sigma=1, size=20_000))


def test_no_drift_scores_near_zero():
    same_population = pd.Series(rng.lognormal(mean=4, sigma=1, size=20_000))
    assert numeric_psi(AMOUNTS, same_population) < 0.01
    assert psi_status(numeric_psi(AMOUNTS, same_population)) == "green"


def test_synthetic_drift_raises_the_alarm():
    # Amounts are spread widely, so a 20% rise is within normal variation, a 50% rise is worth
    # watching, and doubling must turn red. (Measured PSI: 0.03, 0.16 and 0.45.)
    assert psi_status(numeric_psi(AMOUNTS, AMOUNTS * 1.2)) == "green"
    assert psi_status(numeric_psi(AMOUNTS, AMOUNTS * 1.5)) == "amber"
    assert psi_status(numeric_psi(AMOUNTS, AMOUNTS * 2.0)) == "red"


def test_category_mix_shift_is_detected():
    before = pd.Series(["grocery"] * 500 + ["travel"] * 500)
    after = pd.Series(["grocery"] * 200 + ["travel"] * 800)
    assert psi_status(categorical_psi(before, after)) == "red"
    assert categorical_psi(before, before) == 0


def test_missing_values_count_as_their_own_band():
    with_gaps = AMOUNTS.copy()
    with_gaps[: len(with_gaps) // 2] = np.nan     # half the payments suddenly have no value
    assert psi_status(numeric_psi(AMOUNTS, with_gaps)) == "red"


def test_thresholds():
    assert [psi_status(v) for v in (0.05, 0.10, 0.25, 0.26)] == ["green", "amber", "amber", "red"]


def test_part_month_is_labelled():
    labels = month_label(pd.Series(pd.to_datetime(["2020-06-25", "2020-07-03"])))
    assert list(labels) == ["Jun 2020 (21-30)", "Jul 2020"]
