"""The co-pilot's draft: a fixed structure, checked before an analyst ever sees it.

Plain English: whatever model writes the draft, it must come back in exactly this shape. Every piece of
evidence names its sources, the suggested action is one of a short list, and there is no field that
could hold a decision. A draft that doesn't fit the shape is rejected, not repaired.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .messages import ALLOWED, TEMPLATES, NO_MESSAGE

# The only actions the co-pilot may suggest. "insufficient_evidence" is always allowed: saying so beats guessing.
ACTIONS = {
    "confirm_fraud_block_card": "Confirm fraud and block the card",
    "keep_declined_block_card": "Keep the card blocked and confirm fraud",
    "reinstate_contact_customer": "Reinstate the card and contact the customer",
    "release_payment": "Release the payment (not fraud)",
    "ask_customer_in_app": "Ask the customer to confirm in the app before deciding",
    "call_customer": "Call the customer before deciding",
    "escalate": "Escalate to a senior analyst",
    "insufficient_evidence": "Insufficient evidence: gather more before deciding",
}
CONFIDENCE = ("low", "medium", "high")

# A source is either a fact from the database tools ("fact:...") or a policy passage ("policy:...").
FACT, POLICY = "fact:", "policy:"


@dataclass
class Evidence:
    text: str
    sources: list[str]


@dataclass
class Draft:
    summary: str
    evidence_for: list[Evidence]
    evidence_against: list[Evidence]
    suggested_action: str
    confidence: str
    message_template: str  # an approved template id (see messages.py), never free text
    audit_note: str
    policy_sources: list[str] = field(default_factory=list)  # passages behind the suggested action

    def all_text(self) -> str:
        """Every sentence the co-pilot wrote, for the grounding check. The customer message isn't here:
        it is filled from the alert itself, so it can't contain an invented figure."""
        parts = [self.summary, self.audit_note]
        parts += [e.text for e in self.evidence_for + self.evidence_against]
        return "\n".join(parts)

    def all_sources(self) -> list[str]:
        return [s for e in self.evidence_for + self.evidence_against for s in e.sources] + self.policy_sources


class DraftShapeError(ValueError):
    """The model's output didn't fit the fixed structure."""


def _evidence(items, name: str) -> list[Evidence]:
    if not isinstance(items, list):
        raise DraftShapeError(f"{name} must be a list")
    out = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise DraftShapeError(f"{name}[{i}] needs a text")
        sources = item.get("sources")
        if not isinstance(sources, list) or not sources or not all(isinstance(s, str) for s in sources):
            raise DraftShapeError(f"{name}[{i}] must name at least one source")
        out.append(Evidence(item["text"].strip(), sources))
    return out


def parse_draft(data: dict) -> Draft:
    """Turn the model's JSON into a Draft, or raise DraftShapeError saying exactly what's wrong."""
    if not isinstance(data, dict):
        raise DraftShapeError("the draft must be a JSON object")
    allowed = {"summary", "evidence_for", "evidence_against", "suggested_action", "confidence",
               "message_template", "audit_note", "policy_sources"}
    extra = set(data) - allowed
    if extra:  # e.g. a model trying to add "decision" or "close_alert"
        raise DraftShapeError(f"unexpected fields: {sorted(extra)}")
    for key in ("summary", "audit_note"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise DraftShapeError(f"{key} is missing")
    if data.get("suggested_action") not in ACTIONS:
        raise DraftShapeError(f"suggested_action must be one of {sorted(ACTIONS)}")
    template = data.get("message_template")
    if template != NO_MESSAGE and template not in TEMPLATES:
        raise DraftShapeError(f"message_template must be one of {sorted(TEMPLATES) + [NO_MESSAGE]}")
    if template not in ALLOWED[data["suggested_action"]]:
        raise DraftShapeError(f"message_template {template!r} doesn't fit the action {data['suggested_action']!r}")
    if data.get("confidence") not in CONFIDENCE:
        raise DraftShapeError(f"confidence must be one of {CONFIDENCE}")
    policy = data.get("policy_sources", [])
    if not isinstance(policy, list) or not all(isinstance(s, str) for s in policy):
        raise DraftShapeError("policy_sources must be a list of passage ids")
    return Draft(
        summary=data["summary"].strip(),
        evidence_for=_evidence(data.get("evidence_for"), "evidence_for"),
        evidence_against=_evidence(data.get("evidence_against", []), "evidence_against"),
        suggested_action=data["suggested_action"],
        confidence=data["confidence"],
        message_template=template,
        audit_note=data["audit_note"].strip(),
        policy_sources=policy,
    )
