"""MI page calculations."""

import pandas as pd

from metrics import pct, summarise


def test_headline_mi():
    worked = pd.DataFrame({"analyst_decision": ["confirmed_fraud", "not_fraud", "not_fraud", "not_fraud"],
                           "amount_usd": [5920.50, 100.0, 50.0, 25.0]})
    s = summarise(worked)
    assert s["Alerts worked"] == 4
    assert s["Hit rate"] == 0.25
    assert s["False positive rate"] == 0.75
    assert s["Value saved"] == 5920.50          # only confirmed fraud counts as saved
    assert pct(s["Hit rate"]) == "25%"


def test_no_decisions_yet():
    s = summarise(pd.DataFrame({"analyst_decision": [], "amount_usd": []}))
    assert s["Alerts worked"] == 0 and s["Hit rate"] is None
    assert pct(s["Hit rate"]) == "n/a"
