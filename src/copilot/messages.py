"""Customer messages come only from approved templates; the co-pilot picks one, it never writes one.

Plain English: in a bank, what goes to a customer is worded in advance and approved by compliance.
So the co-pilot doesn't write the customer message. It chooses which approved template fits its
suggested action, and the system fills in the payment's amount, merchant and date straight from the
alert. No figure in a customer message can be invented, and no fraudster text can reach a customer
unchecked: if the merchant name was flagged as suspicious, the message says "the merchant" instead.

The wording below is a draft for Amrit's approval (decision V21) and is versioned, so every logged
draft records which wording it used. Messages never contain links or ask for security details,
which is standard anti-phishing practice.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TEMPLATE_VERSION = "2026-11-19 draft (awaiting approval)"

NO_MESSAGE = "none"  # escalations and "insufficient evidence": nothing goes to the customer yet

TEMPLATES = {
    "card_blocked_fraud": (
        "We've blocked your card because we don't think you made a payment of {amount} to {merchant} "
        "on {date}. If the money has left your account, we'll refund it. We'll send you a new card. "
        "If you did make this payment, please call us on the number on the back of your card."
    ),
    "card_reinstated": (
        "Your card is working again. We paused it while we checked a payment of {amount} to {merchant} "
        "on {date}. Thank you for your patience, and sorry for the inconvenience."
    ),
    "payment_released": (
        "We've checked your payment of {amount} to {merchant} on {date} and it has now gone through. "
        "You don't need to do anything."
    ),
    "confirm_in_app": (
        "Please check a payment of {amount} to {merchant} on {date}. Open your banking app to tell us "
        "whether you made it. We will never ask for your PIN or passcode."
    ),
    "call_request": (
        "We need to check a payment of {amount} to {merchant} on {date}. Please call us on the number on "
        "the back of your card. We will never ask for your full PIN or online banking password."
    ),
}

# Which templates fit which suggested action. A mismatch (e.g. "release payment" with "card blocked")
# blocks the draft.
ALLOWED = {
    "confirm_fraud_block_card": {"card_blocked_fraud"},
    "keep_declined_block_card": {"card_blocked_fraud"},
    "reinstate_contact_customer": {"card_reinstated"},
    "release_payment": {"payment_released"},
    "ask_customer_in_app": {"confirm_in_app"},
    "call_customer": {"call_request"},
    "escalate": {NO_MESSAGE},
    "insufficient_evidence": {NO_MESSAGE},
}


@dataclass(frozen=True)
class AlertForMessage:
    """The only values a template may use, taken from the alert row, never from the model."""
    amount: float
    trans_ts: pd.Timestamp
    merchant: str           # as stored in app.alerts
    merchant_flagged: bool  # True if the cleaning step flagged the name


def render(template_id: str, alert: AlertForMessage) -> str:
    """The exact text the customer would receive, or "" when no message is due."""
    if template_id == NO_MESSAGE:
        return ""
    merchant = "the merchant" if alert.merchant_flagged else alert.merchant.strip()[:60]
    return TEMPLATES[template_id].format(
        amount=f"${alert.amount:,.2f}",
        merchant=merchant,
        date=f"{pd.Timestamp(alert.trans_ts):%-d %b %Y}",
    )
