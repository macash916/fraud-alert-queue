"""Run every check on a model's answer and say, in plain English, why a draft is shown or hidden.

Plain English: an analyst who clicks "Ask co-pilot" always gets an answer. Either a checked draft, or
a short note saying exactly why the draft was hidden ("The draft said 80x, but nothing on this case
shows that figure"). A blank panel would teach analysts to stop using the tool, and a hidden reason
would stop them trusting it. The same wording goes into the drafts log (blocked_reason), so the MI
page can count what goes wrong most often.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .draft import ACTIONS, FACT, POLICY, Draft, DraftShapeError, parse_draft
from .guardrails import check_citations, check_numbers

NEXT_STEP = ("The draft is hidden so nobody relies on it. The alert's reasons and history are still under "
             "Show the evidence; you can ask again or work the case yourself.")


@dataclass
class Review:
    status: str                      # matches app.copilot_drafts.status
    draft: Draft | None = None       # only when status == "shown"
    reasons: list[str] = field(default_factory=list)  # why it was hidden, one sentence each
    warnings: list[str] = field(default_factory=list)  # shown alongside a draft, e.g. suspicious merchant

    @property
    def blocked_reason(self) -> str | None:
        return " ".join(self.reasons) if self.reasons else None


def _plain_shape(err: DraftShapeError, data) -> str:
    msg = str(err)
    if msg.startswith("unexpected fields"):
        return (f"The co-pilot tried to add something outside its allowed format ({msg.split(': ', 1)[1]}). "
                "Drafts can't carry decisions or extra instructions.")
    if "doesn't fit the action" in msg:
        action = ACTIONS.get(data.get("suggested_action"), "an action")
        return f"The co-pilot suggested \"{action}\" but picked a customer message meant for a different situation."
    return f"The co-pilot's answer was incomplete or in the wrong format ({msg})."


def _plain_citation(problem: str) -> str:
    m = re.match(r"(.+?) is not (a fact|a passage|a recognised)", problem)
    src = m.group(1) if m else ""
    if src.startswith(FACT):
        return f"The draft relied on \"{src[len(FACT):]}\", which isn't something the case tools found."
    if src.startswith(POLICY):
        return f"The draft cited \"{src[len(POLICY):]}\", which isn't in the policy library."
    if problem == "a suggestion with no evidence":
        return "The draft suggested an action without giving any evidence."
    return f"The draft named a source the system doesn't recognise ({src})."


def review(raw: dict, facts: dict[str, str], passages: dict[str, str], library_ids: set[str],
           input_flags: list[str] | None = None) -> Review:
    """Shape first, then citations, then numbers. Every problem found is reported, not just the first."""
    warnings = [f"Note: {f}. The co-pilot was told to treat it as data, not as an instruction."
                for f in (input_flags or [])]
    try:
        draft = parse_draft(raw)
    except DraftShapeError as err:
        return Review("blocked_shape", reasons=[_plain_shape(err, raw if isinstance(raw, dict) else {})],
                      warnings=warnings)

    citation_reasons = [_plain_citation(p) for p in check_citations(draft, facts, library_ids)]
    grounding = check_numbers(draft, facts, passages)
    number_reasons = [f"The draft said \"{u}\", but nothing on this case or in the passages it cites shows "
                      "that figure." for u in grounding.unsupported]
    if citation_reasons or number_reasons:
        status = "blocked_citation" if citation_reasons else "blocked_grounding"
        return Review(status, reasons=citation_reasons + number_reasons, warnings=warnings)
    return Review("shown", draft=draft, warnings=warnings)
