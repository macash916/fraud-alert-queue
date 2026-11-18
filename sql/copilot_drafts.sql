-- Co-pilot drafts (v2, decision V10). Every draft an analyst asked for, with everything needed to audit it.
-- There is deliberately no column that can hold a decision: decisions stay in app.alerts and
-- app.alert_decision_log, written only by the analyst's own button.

CREATE TABLE IF NOT EXISTS app.copilot_drafts (
    draft_id          bigserial PRIMARY KEY,
    trans_num         text        NOT NULL REFERENCES app.alerts (trans_num),
    requested_by      text        NOT NULL,                 -- the analyst who asked
    requested_at      timestamptz NOT NULL DEFAULT now(),
    model             text        NOT NULL,                 -- e.g. claude-haiku-5-5 or qwen3:4b (local)
    prompt_version    text        NOT NULL,
    library_version   text        NOT NULL,                 -- policy library build the draft cited
    draft             jsonb,                                -- the structured draft; null if blocked before parsing
    status            text        NOT NULL CHECK (status IN ('shown', 'blocked_grounding', 'blocked_citation',
                                                             'blocked_shape', 'error')),
    blocked_reason    text,                                 -- what the guardrail found, in plain English
    input_flags       text[]      NOT NULL DEFAULT '{}',    -- e.g. merchant name reads like an instruction
    feedback          text CHECK (feedback IN ('accepted', 'edited', 'rejected')),
    feedback_reason   text,                                 -- wrong facts / wrong policy / disagree
    edited_text       text,                                 -- the analyst's version, if edited
    input_tokens      integer,
    output_tokens     integer,
    cost_usd          numeric(10, 6),
    latency_ms        integer
);

CREATE INDEX IF NOT EXISTS copilot_drafts_trans_idx ON app.copilot_drafts (trans_num, requested_at DESC);
