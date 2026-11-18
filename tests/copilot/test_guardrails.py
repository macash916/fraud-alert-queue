"""Guardrails: unsupported numbers block a draft, fake citations are caught, injected text is fenced."""

import pytest
from copilot.draft import ACTIONS, DraftShapeError, parse_draft
from copilot.guardrails import as_data, check_citations, check_numbers, figures
from copilot.injection_suite import ATTACKS

FACTS = {
    "fact:amount": "Payment amount $2,965.05",
    "fact:time": "Made on 04 Dec 2020 at 03:28",
    "fact:score": "Model fraud probability 42.0% (model version 2)",
    "fact:reason_2": "Spend in the last 24 hours is 65x this customer's usual daily spend",
    "fact:reason_3": "$1,305 already spent on this card in the previous 24 hours",
    "fact:recent_count": "2 payments on this card in the 72 hours before this one",
}
PASSAGES = {"PSRs 2017 reg 74(1)": "no later than 13 months after the debit date",
            "PSRs 2017 reg 71(2)": "stop the use of a payment instrument on reasonable grounds"}


def draft(**over):
    base = {
        "summary": "$2,965.05 online at 03:28; spend in the last 24 hours is 65x usual.",
        "evidence_for": [{"text": "Spend in the last 24 hours is 65x usual daily spend", "sources": ["fact:reason_2"]}],
        "evidence_against": [{"text": "Model probability is 42%, below even odds", "sources": ["fact:score"]}],
        "suggested_action": "confirm_fraud_block_card",
        "confidence": "medium",
        "customer_message": "We've paused your card after a payment of $2,965.05 that didn't look like you.",
        "audit_note": "Checked reasons and last 72 hours; suggested block under PSRs reg 71(2).",
        "policy_sources": ["policy:PSRs 2017 reg 71(2)"],
    }
    base.update(over)
    return parse_draft(base)


def test_figures_reads_money_percent_time_multiples_and_counts():
    kinds = {(f.kind, f.value) for f in figures("$1,305 then $2,965.05 at 03:28, 42%, 6.1x, within 13 months")}
    assert {("money", 1305.0), ("money", 2965.05), ("time", 208), ("percent", 42.0),
            ("multiple", 6.1), ("count", 13.0)} <= kinds


def test_grounded_draft_passes():
    result = check_numbers(draft(), FACTS, PASSAGES)
    assert result.ok, result.unsupported


def test_one_invented_number_blocks_the_draft():
    bad = draft(summary="$2,965.05 at 03:28, the customer's 9th large payment this week, 80x usual.")
    result = check_numbers(bad, FACTS, PASSAGES)
    assert not result.ok
    assert "80x" in result.unsupported


def test_policy_figures_count_only_when_the_passage_is_cited():
    note = "Customer can report within 13 months."
    assert not check_numbers(draft(audit_note=note), FACTS, PASSAGES).ok
    cited = draft(audit_note=note, policy_sources=["policy:PSRs 2017 reg 74(1)"])
    assert check_numbers(cited, FACTS, PASSAGES).ok


def test_rounded_amounts_and_percentages_are_accepted():
    ok = draft(summary="About $2,965 at 03:28; score 42.0%.")
    assert check_numbers(ok, FACTS, PASSAGES).ok


def test_citations_must_exist():
    library = set(PASSAGES)
    assert check_citations(draft(), FACTS, library) == []
    fake = draft(policy_sources=["policy:PSRs 2017 reg 999"],
                 evidence_for=[{"text": "Card was reported stolen", "sources": ["fact:stolen_report"]}])
    problems = check_citations(fake, FACTS, library)
    assert any("reg 999" in p for p in problems) and any("stolen_report" in p for p in problems)


@pytest.mark.parametrize("field, value", [
    ("suggested_action", "close_alert"),
    ("confidence", "certain"),
    ("evidence_for", [{"text": "Large payment", "sources": []}]),
])
def test_shape_errors_are_rejected(field, value):
    with pytest.raises(DraftShapeError):
        draft(**{field: value})


def test_a_draft_cannot_carry_a_decision():
    with pytest.raises(DraftShapeError, match="unexpected fields"):
        draft(decision="not_fraud")


def test_insufficient_evidence_is_always_an_option():
    assert "insufficient_evidence" in ACTIONS


@pytest.mark.parametrize("attack", ATTACKS, ids=[a.id for a in ATTACKS])
def test_injection_text_is_fenced_and_flagged(attack):
    clean = as_data(attack.text, attack.field)
    assert clean.text.startswith(f'<data field="{attack.field}">') and clean.text.endswith("</data>")
    inner = clean.text[len(f'<data field="{attack.field}">'):-len("</data>")]
    assert "<" not in inner and ">" not in inner          # the fence can't be closed from inside
    assert "​" not in inner and "‮" not in inner  # hidden characters are gone
    assert len(inner) <= 200
    assert bool(clean.flags) == attack.should_flag, clean.flags
