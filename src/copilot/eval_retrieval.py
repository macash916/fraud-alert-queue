"""Retrieval test: does the policy library find the right passage for each policy question?

Plain English: for every question in Amrit's policy set that the open-licence sources can answer, the
right provision has to appear in the top five search results ("recall at 5"). The expected provisions
were checked against the official text on 18 Nov 2026.

FCA and PRA questions (P15 to P20, P24 to P29) are left out until decision V17 settles how that guidance
is held; P30 waits for the analyst procedures from session A.

Run from the repo root:  .venv/bin/python -m src.copilot.eval_retrieval
"""

from __future__ import annotations

import sys
from pathlib import Path

from .policy_library import from_database

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "v2_prep" / "retrieval_eval.md"

# (id, question, accepted passages: any passage whose id starts with one of these counts as a hit)
QUESTIONS = [
    ("P01", "How quickly must the bank refund an unauthorised card payment once the customer reports it?", ["PSRs 2017 reg 76(2)"]),
    ("P02", "When can the bank delay refunding an unauthorised card payment?", ["PSRs 2017 reg 76(3)"]),
    ("P03", "What is the most a customer can be made to pay for a lost or stolen card?", ["PSRs 2017 reg 77(1)"]),
    ("P04", "When does the £35 limit not protect the customer?", ["PSRs 2017 reg 77(3)"]),
    ("P05", "Is the customer liable if the bank didn't apply Strong Customer Authentication?", ["PSRs 2017 reg 77(4)"]),
    ("P06", "Who has to prove that a payment was authorised?", ["PSRs 2017 reg 75(1)"]),
    ("P07", "Is the use of the card itself proof that the customer was grossly negligent?", ["PSRs 2017 reg 75(3)"]),
    ("P08", "When may the bank block a card?", ["PSRs 2017 reg 71(2)"]),
    ("P09", "Must the bank tell the customer it has blocked their card, and when?", ["PSRs 2017 reg 71(3)", "PSRs 2017 reg 71(4)"]),
    ("P10", "When must the bank unblock the card?", ["PSRs 2017 reg 71(6)"]),
    ("P11", "What must the customer do to keep their card and security details safe?", ["PSRs 2017 reg 72(1)", "PSRs 2017 reg 72(3)"]),
    ("P12", "How long does a customer have to report an unauthorised payment?", ["PSRs 2017 reg 74(1)"]),
    ("P13", "What counts as Strong Customer Authentication?", ["PSRs 2017 reg 100", "SCA RTS Art 4", "SCA RTS Art 9"]),
    ("P14", "When can a payment be exempt from SCA because the bank judges it low risk?", ["SCA RTS Art 18"]),
    ("P21", "Can a bank decline a payment by a purely automated decision? What safeguards apply?", ["UK GDPR Art 22A", "UK GDPR Art 22B", "UK GDPR Art 22C", "ICO ADM"]),
    ("P22", "What should a bank tell a customer about an automated decision?", ["UK GDPR Art 22C", "ICO ADM: safeguards", "ICO AI: individual rights"]),
    ("P23", "What does data minimisation mean for what goes into a model or an AI tool?", ["UK GDPR Art 5(1)", "ICO AI: data minimisation"]),
]


def run(k: int = 5, use_glossary: bool = True) -> tuple[int, list[str]]:
    lib = from_database()
    hits, lines = 0, []
    for qid, q, gold in QUESTIONS:
        results = lib.search(q, k=k, use_glossary=use_glossary)
        ids = [p.id for p, _ in results]
        rank = next((i + 1 for i, pid in enumerate(ids) if any(pid.startswith(g) for g in gold)), None)
        hits += rank is not None
        lines.append(f"| {qid} | {q} | {', '.join(gold)} | {rank or 'miss'} | {ids[0]} |")
    return hits, lines


if __name__ == "__main__":
    base_hits, _ = run(use_glossary=False)
    hits, lines = run()
    n = len(QUESTIONS)
    report = [
        "# Retrieval test: policy questions (recall at 5)",
        "",
        f"**{hits} of {n} questions ({hits / n:.0%})** have the right provision in the top five results. "
        "Search is hybrid: half keyword (BM25), half meaning (nomic-embed-text, run locally). "
        f"Library: {len(from_database().passages)} passages from open-licence sources (legislation.gov.uk and the ICO).",
        "",
        f"Without the banking-to-legal glossary (V18) the same search finds {base_hits} of {n} ({base_hits / n:.0%}). "
        "The glossary is a fixed list of nine general terms (card, bank, block, unblock, customer, report, SCA, £35, "
        "automated decision), added after the first run showed every miss was a vocabulary gap. Because it was added "
        "after seeing these results, the score below is optimistic until it is re-run on new questions.",
        "",
        "| Q | Question | Accepted provisions | Rank of first hit | Top result |",
        "|---|---|---|---|---|",
        *lines,
        "",
        "Not tested yet: P15 to P20 and P24 to P29 (FCA and PRA guidance, waiting for decision V17) and P30 "
        "(analyst procedures, from session A).",
    ]
    OUT.write_text("\n".join(report) + "\n")
    print("\n".join(report))
    sys.exit(0)
