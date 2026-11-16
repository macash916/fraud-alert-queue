"""MI calculations, kept apart from the page so they can be unit tested."""

import pandas as pd


def summarise(df: pd.DataFrame) -> dict:
    """Headline MI for a set of worked alerts (one row per closed alert)."""
    worked = len(df)
    fraud = int((df["analyst_decision"] == "confirmed_fraud").sum())
    genuine = worked - fraud
    return {
        "Alerts worked": worked,
        "Confirmed fraud": fraud,
        "Not fraud": genuine,
        "Hit rate": fraud / worked if worked else None,
        "False positive rate": genuine / worked if worked else None,
        "Value saved": float(df.loc[df["analyst_decision"] == "confirmed_fraud", "amount_usd"].sum()),
    }


def pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"
