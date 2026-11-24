---
name: copilot-eval
description: Run the v2 co-pilot evaluation the same way every time (unit checks, policy retrieval recall at 5, injection suite, and the model-based backtest once built) and report results against the previous run. Use when Amrit types /copilot-eval, or after any change to the co-pilot, its prompts, the policy library or the guardrails.
---

# Co-pilot evaluation

Every run uses the same commands and the same report shape, so results can be compared over time and quoted in the README and model card. Run from the repo root.

## Spending rule (hard)
Free checks run without asking. **Any step that calls a paid API (Claude) needs Amrit's explicit yes in this conversation first**, stating the expected number of calls and cost. The total API budget for v2 is £10 (decision V14). CI never calls an API; it uses recorded responses.

## Checks, in order

| # | Check | Command | Needs |
|---|---|---|---|
| 1 | Unit tests: draft shape, grounding, citations, data fencing, templates, blocked reasons, tools, library | `.venv/bin/python -m pytest tests/copilot -q` | nothing |
| 2 | Injection suite (offline layer: every attack fenced and flagged, controls not flagged) | included in check 1 (`test_injection_text_is_fenced_and_flagged`) | nothing |
| 3 | Policy retrieval, recall at 5 | `.venv/bin/python -m src.copilot.eval_retrieval` | PostgreSQL up; Ollama serving `nomic-embed-text` at 127.0.0.1:11434 |
| 4 | Model drafts on the 30-case benchmark: agreement with Amrit by stratum, Evidence label validation (V23), grounding failures, refusals, seconds per draft | harness not built yet | local model first; Claude only with a yes |
| 5 | Consistency: the same case three times | harness not built yet | as check 4 |
| 6 | Injection suite with a model (draft must not follow the attack) | harness not built yet | as check 4 |
| 7 | Cost per case (reported in docs, never shown in the app) | harness not built yet | Claude runs only |

If Ollama is not running, start it (do not install anything new):
`cd ~/.local/ollama-v0.40.13 && OLLAMA_HOST=127.0.0.1:11434 ./ollama serve` in the background, then retry check 3.

For checks not yet built, report "not built yet". Never invent or estimate a result.

## Report
1. A table: check | result | previous run | change. Previous results come from `v2_prep/eval_history.md`.
2. Anything that got worse, with the likely cause.
3. Append this run to `v2_prep/eval_history.md`: date, commit (`git rev-parse --short HEAD`), model and library versions, and the results table.
4. Keep the retrieval caveat: the glossary was written after seeing the first misses, so recall is optimistic until tested on new questions.
