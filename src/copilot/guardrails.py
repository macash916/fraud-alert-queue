"""Guardrails that run on every draft before an analyst sees it.

Plain English, three checks:
1. Numbers: every amount, percentage, time and "Nx" in the draft must match a value the database tools
   returned or a figure in a cited policy passage. One unsupported number blocks the whole draft.
2. Citations: every source the draft names must exist (a fact the tools returned, or a passage in the
   library), and every piece of evidence must name at least one.
3. Untrusted text: merchant names and notes can be written by fraudsters. They are cleaned and fenced as
   data before the model sees them, and anything that looks like an instruction is flagged to the analyst.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .draft import FACT, POLICY, Draft

# ---------- 1. Numeric grounding ----------

_MONEY = re.compile(r"[$£]\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_MULT = re.compile(r"\b(\d+(?:\.\d+)?)\s?x\b", re.IGNORECASE)
_COUNT = re.compile(r"\b(\d+(?:\.\d+)?)\s+(hours?|days?|months?|payments?|alerts?|minutes?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Figure:
    kind: str     # money | percent | time | multiple | count
    value: float
    text: str     # as written, for the analyst-facing message


def figures(text: str) -> list[Figure]:
    """Every checkable number in a piece of text."""
    out: list[Figure] = []
    for m in _MONEY.finditer(text):
        out.append(Figure("money", float(m.group(1).replace(",", "")), m.group(0)))
    for m in _PCT.finditer(text):
        out.append(Figure("percent", float(m.group(1)), m.group(0)))
    for m in _TIME.finditer(text):
        out.append(Figure("time", int(m.group(1)) * 60 + int(m.group(2)), m.group(0)))
    for m in _MULT.finditer(text):
        out.append(Figure("multiple", float(m.group(1)), m.group(0)))
    for m in _COUNT.finditer(text):
        out.append(Figure("count", float(m.group(1)), m.group(0)))
    return out


def _matches(f: Figure, allowed: list[Figure]) -> bool:
    for a in allowed:
        if a.kind != f.kind:
            continue
        if f.kind == "money" and abs(a.value - f.value) <= 0.01:
            return True
        if f.kind == "money" and a.value >= 100 and abs(round(a.value) - f.value) <= 0.5:
            return True  # "$2,965" for $2,965.05 is a fair rounding
        if f.kind == "percent" and abs(a.value - f.value) <= 0.05 + 1e-9:
            return True
        if f.kind == "percent" and abs(round(a.value) - f.value) < 1e-9:
            return True
        if f.kind == "multiple" and (abs(a.value - f.value) < 1e-9 or abs(round(a.value) - f.value) < 1e-9):
            return True
        if f.kind in ("time", "count") and abs(a.value - f.value) < 1e-9:
            return True
    return False


@dataclass
class GroundingResult:
    ok: bool
    unsupported: list[str] = field(default_factory=list)


def check_numbers(draft: Draft, facts: dict[str, str], passages: dict[str, str]) -> GroundingResult:
    """Block the draft if it states any figure that no tool result or cited passage supports.

    facts:    fact id -> the fact as text, e.g. {"fact:amount": "$2,965.05", "fact:p": "42.0%"}
    passages: passage id -> text, for the passages the draft cites
    """
    cited = set(draft.all_sources())
    allowed: list[Figure] = []
    for text in facts.values():
        allowed += figures(text)
    for pid, text in passages.items():
        if f"{POLICY}{pid}" in cited:
            allowed += figures(text)
    unsupported = [f.text for f in figures(draft.all_text()) if not _matches(f, allowed)]
    return GroundingResult(not unsupported, unsupported)


# ---------- 2. Citation validity ----------

def check_citations(draft: Draft, facts: dict[str, str], library_ids: set[str]) -> list[str]:
    """Problems with the draft's sources; an empty list means every citation is real."""
    problems = []
    for src in draft.all_sources():
        if src.startswith(FACT):
            if src not in facts:
                problems.append(f"{src} is not a fact the tools returned")
        elif src.startswith(POLICY):
            if src[len(POLICY):] not in library_ids:
                problems.append(f"{src} is not a passage in the policy library")
        else:
            problems.append(f"{src} is not a recognised source")
    if not draft.evidence_for and not draft.evidence_against and draft.suggested_action != "insufficient_evidence":
        problems.append("a suggestion with no evidence")
    return problems


# ---------- 3. Untrusted text ----------

MAX_FIELD = 200
_INSTRUCTION = re.compile(
    r"ignore (all |any )?(previous|prior|above)|disregard|system\s*[:\]]|\[\s*system|assistant\s*:|"
    r"you are now|new instructions|override|recommend\s*:|close (the )?alert|not fraud|verified|"
    r"no further checks|score\s*(override|=|:)|mark (as|this)|approve|whitelist|<\s*/?\s*(data|system)|"
    r"instructions?\b|already (checked|verified|confirmed)|just (write|say|output|reply)",
    re.IGNORECASE,
)


@dataclass
class CleanText:
    text: str           # what the model sees, inside the data fence
    flags: list[str]    # reasons to warn the analyst


def as_data(value: str | None, field_name: str) -> CleanText:
    """Clean a fraudster-controllable string and fence it as data, never instructions.

    Removes invisible and control characters, normalises look-alike characters, caps the length,
    escapes the fence markers, and flags anything that reads like an instruction to the model.
    """
    raw = value or ""
    flags = []
    norm = unicodedata.normalize("NFKC", raw)
    visible = "".join(ch for ch in norm if unicodedata.category(ch) not in ("Cf", "Cc", "Co", "Cs") or ch == " ")
    if len(visible) != len(norm):
        flags.append("hidden characters removed")
    if len(visible) > MAX_FIELD:
        flags.append(f"cut to {MAX_FIELD} characters (was {len(visible)})")
        visible = visible[:MAX_FIELD]
    if _INSTRUCTION.search(visible):
        flags.append("reads like an instruction to the co-pilot")
    if any(ord(ch) > 0x2FF for ch in visible) and not visible.isascii():
        flags.append("non-Latin characters")
    safe = visible.replace("<", "‹").replace(">", "›")
    return CleanText(f'<data field="{field_name}">{safe}</data>', flags)
