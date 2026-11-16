"""Reason codes: every alert's three reasons must be true, readable and point the right way."""

import pandas as pd

from explain import reason_text, times


def payment(**values) -> pd.Series:
    base = {"category": "grocery_pos", "trans_ts": pd.Timestamp("2020-07-01 22:20")}
    return pd.Series({**base, **values})


def test_ratios_are_written_for_people():
    assert times(0.04) == "0.04x"
    assert times(3.46) == "3.5x"
    assert times(59.4) == "59x"


def test_amount_reasons_say_which_way_the_payment_is_unusual():
    assert reason_text("amt", payment(amt=4.5)).startswith("Small payment of $4.50")
    assert reason_text("amt", payment(amt=5920.5)) == "Large payment of $5,920.50"
    assert reason_text("amt", payment(amt=120)) == "Payment amount of $120.00"


def test_ratio_reasons_flip_wording_below_one():
    assert reason_text("amt_vs_category_avg", payment(amt_vs_category_avg=75)) == \
        "Amount is 75x a typical grocery (in store) payment"
    assert reason_text("amt_vs_category_avg", payment(amt_vs_category_avg=0.2)).startswith("Unusually small")
    assert reason_text("spend_24h_vs_daily_avg", payment(spend_24h_vs_daily_avg=0.5)).startswith("Unusually quiet")


def test_missing_history_is_explained_not_shown_as_a_number():
    assert reason_text("amt_vs_avg", payment(amt_vs_avg=float("nan"))).startswith("First payment on this card")
    assert reason_text("secs_since_last", payment(secs_since_last=float("nan"))) == "First payment on this card"
    assert reason_text("hour_band_share", payment(hour_band_share=float("nan"))).startswith("No history")


def test_card_history_wording_matches_the_count():
    # Bug found in testing: 2,521 earlier payments was described as "Limited card history".
    assert reason_text("prior_txn_count", payment(prior_txn_count=6)) == "Limited card history: 6 earlier payment(s)"
    long_history = reason_text("prior_txn_count", payment(prior_txn_count=2521))
    assert "Limited" not in long_history and "2,521" in long_history


def test_time_of_day_wording_matches_the_share():
    assert reason_text("hour_band_share", payment(hour_band_share=0.05)).startswith("Customer rarely pays")
    assert "rarely" not in reason_text("hour_band_share", payment(hour_band_share=0.6))


def test_gap_since_last_payment():
    assert reason_text("secs_since_last", payment(secs_since_last=600)) == "Only 10 minutes since the previous payment"
    assert reason_text("secs_since_last", payment(secs_since_last=7200)).startswith("First payment in 2 hours")
