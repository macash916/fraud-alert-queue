# Decisions made overnight for Amrit's review

On 16 Nov 2026 (00:45) Amrit chose **option A**: Claude continues overnight using the recommended option wherever a design question comes up, records every such choice here, and commits each finished section locally (no push). Amrit approves or reverses each item in the morning; anything reversed gets reworked.

**Status (16 Nov 2026, morning): O1 to O28 approved by Amrit.**

Each entry gives the question, the option chosen, the alternatives, and why.

| # | Section | Question | Chosen (recommended) | Alternatives | Why |
|---|---|---|---|---|---|
| O1 | 7c Final model | Which settings become the production model? | XGBoost run 10 settings (best validation PR-AUC 0.983), retrained on all training months | Any of the other 19 settings (all PR-AUC 0.957 to 0.983) | Selection rule agreed earlier: best PR-AUC on validation |
| O2 | 7c Final model | How is the model versioned? | MLflow model registry `fraud-xgboost`, alias `champion` (version 1) | Plain run artefact only | Registry and aliases are how model risk tracks which version is live |
| O3 | 7c Final model | Where do scores live? | New PostgreSQL schema `scoring.model_scores`, separate from dbt's `analytics` | A dbt model; CSV files | Python writes scores; dbt owns `analytics`. Keeps ownership clear |
| O4 | 7c Final model | Keep logistic regression? | Yes, as the comparison baseline only, scored on test months | Drop it | The Definition of done compares rules, logistic regression and XGBoost |
| O5 | 8 Decisioning | Where do the cost assumptions live? | `config/decision_params.yaml`, one named, commented value per assumption | Constants in Python; dbt vars | Editable without touching code, as the brief requires |
| O6 | 8 Decisioning | Assumption values | Analyst $32/hour, 5 min per review ($2.67), capacity 21 a day; step-up $0.50, budget 2 a day; false decline $20; loss rate 100%; block delay 1 hour | Any; all are tested in the sensitivity analysis | Plausible starting points; the tornado chart shows which matter |
| O7 | 8 Decisioning | What does analyst review do to the payment? | Holds it until worked: fraud stopped, genuine released | Review after the payment goes through (fraud lost, card blocked) | Matches a held-payment queue; stated as a caveat |
| O8 | 8 Decisioning | How are step-up responses simulated? | Fixed random draw per payment (seed 42), same draws for every policy | Expected values (fractions) | Keeps card blocks clean and policies comparable |
| O9 | 8 Decisioning | How are daily volumes set? | Thresholds from the validation months, applied unchanged to the test months | Tuned on test months | No test-month tuning, so test volumes can differ from target (they do: real-world behaviour) |
| O10 | 8 Decisioning | Which policies are compared? | No controls, rules, model like-for-like (same routes and budgets), model four routes (cheapest action per payment) | Four routes only | Separates the gain from better ranking from the gain from more routes |
| O11 | 8 Decisioning | Which policy feeds the alert queue? | Model, four routes (`scoring.decisions`) | Like-for-like | Lever C was agreed; the queue shows all four routes. The business case recommends starting like-for-like and piloting four routes |
| O12 | 8 Decisioning | How are money figures framed? | Annualised from 194 days, also per card; heavy caveats on simulated data | Scaled up to a real bank's card book | Scaling a simulated book would overclaim |
| O13 | 9 Explainability | How are SHAP values computed? | `shap.TreeExplainer` on the champion model, checked to match XGBoost's built-in TreeSHAP exactly | XGBoost `pred_contribs` only; KernelSHAP | Exact for tree models, fast, and verified |
| O14 | 9 Explainability | How is the one-hot category explained? | Its 14 columns' contributions are summed into one "merchant category" reason | One reason per one-hot column | One business concept, one reason |
| O15 | 9 Explainability | What becomes a reason? | The 3 features pushing the score up most, worded with the payment's own values and the direction it's unusual in ("unusually small", "after a quiet spell") | Fixed generic labels | Readable by a customer or auditor; avoids "reasons" that sound like non-reasons |
| O16 | 9 Explainability | What does the alerts table contain? | `app.alerts`: every test-month payment routed to analyst review, step-up or decline (5,245), with score, expected loss, route, 3 reasons and a JSON audit trail of all contributions. No fraud labels. Card shown as an 8-character token prefix; the simulator's "fraud_" merchant prefix is stripped | Analyst-review alerts only; labels included | Analysts must judge on evidence; PCI-safe; the prefix would mislead in a demo |
| O17 | 9 Explainability | Q4: drop the two weak features? | **Keep all 14, no retrain.** Mean absolute SHAP share: usual time of day 4.8%, small payments 2.4%, so neither adds "nothing". Flag for Amrit: new merchant (0.1%) and new category (0.0%) contribute almost nothing | Drop and retrain (new model version, rerun of sections 7c to 9) | Your rule was to drop only if SHAP confirms no contribution; it doesn't. New merchant is in the original brief |
| O18 | 10 Fairness | Where do age and gender live? | Restricted dbt model in its own schema (`analytics_restricted.fairness_attributes`): transaction ID, age band, gender only | Read straight from the raw table in Python | Documented, tested, minimal; the personal-data test on `analytics` still passes |
| O19 | 10 Fairness | Age bands | Under 18, 18-24, 25-34, 35-44, 45-54, 55-64, 65+ (age on the payment date). "Under 18" added after finding 13 cards aged 13 to 17 | Fold under-18s into 18-24 | Hiding a data-quality problem would be worse than showing it |
| O20 | 10 Fairness | When is a group flagged? | 95% Wilson interval: interruption lower bound above 1.25x overall, or detection upper bound below 0.8x overall | Raw rate differences; the four-fifths rule | Material and statistically clear; avoids over-reading small groups |
| O21 | 10 Fairness | Act on the female/male interruption gap now? | **No model change** (scope freeze). Documented as a watch item with root-cause evidence and a recommended challenger (customer-specific category norm) | Retrain now with a new feature | The gap is below the flag threshold; changing the model overnight would invalidate sections 7c to 9 |
| O22 | 11 App | What may the app read? | Only the `app` schema (alerts and the decision log). Card shown by 8-character token prefix; no customer names | Join to the features or raw tables for richer context | Data minimisation: the analyst sees what the decision needs, nothing more |
| O23 | 11 App | Two analysts on one alert | A decision is written only if the alert is still open; the second analyst is told it has already been worked | Row locks or a "claimed by" field | Simplest guard that cannot double-count; claiming can come later |
| O24 | 11 App | Audit trail | Append-only `app.alert_decision_log`: who, when, decision, note, and the score, route and model version they saw | Rely on the latest state in `app.alerts` only | An auditor asks "what did the analyst see when they decided?"; current state can't answer that |
| O25 | 11 App | Source of MI figures | Analysts' recorded decisions only, not the dataset's fraud labels. No decisions are seeded, so MI starts empty | Pre-fill MI with simulated analyst decisions | That is how live MI works; simulating analysts would be the "replay" feature, which is out of scope |
| O26 | 11 App | Queue layout | Full-width queue ranked by expected loss on top, case panel below (reasons, decision buttons, SHAP breakdown, other alerts on the card). Selection resets to the top alert after each decision | Side-by-side list and detail | Side by side clipped the table at laptop width; the reset stops an analyst acting on a different alert from the one they read |
| O27 | 11 App | Analyst identity | A name field in the sidebar, required before deciding. No login | Authentication | Login is out of scope for a portfolio build; the model card will list it as a production gap |
| O28 | 11 App | Docker | Separate slim image with only the app's 4 packages; `.dockerignore` admits only `app/*.py`, its requirements and the Streamlit config; runs as a non-root user; port bound to 127.0.0.1 | One image with the full modelling stack | Smaller image; data and `.env` can never be copied into it |

## Remaining build, S12 to S17 (approved by Amrit, 16 Nov 2026)

Proposed by Claude, approved by Amrit as one blanket go-ahead with the changes noted. These move into `decision_log.md` in S14.

| # | Section | Decision | Status |
|---|---|---|---|
| D1 | S12 Monitoring | Monthly checks: input drift (PSI on 14 features and the category mix), score drift, outcomes, the fairness watch item | Approved |
| D2 | S12 Monitoring | Reference: training months; calendar-month windows, part-June labelled | Approved |
| D3 | S12 Monitoring | RAG: PSI below 0.10 / 0.10-0.25 / above 0.25; fraud value amber at 2 and red at 5 points below baseline; fairness amber at 1.10x, red on the audit's 1.25x rule | Approved |
| D4 | S12 Monitoring | A test injects synthetic drift and must turn red | Approved |
| D5 | S12 Monitoring | Outputs: `monitoring.drift_monthly`, heatmap, MLflow `monitoring`, `docs/monitoring.md`; no app page | Approved |
| D6 | S12 Monitoring | Retraining policy documented, not automated | Approved |
| D7 | S12 Monitoring | Label delay documented, not simulated | Approved |
| D8 | S13 Tests | Unit tests (no database) for wording, intervals, cost and routing logic, confirm then block, fairness flags, MI sums, PSI | Approved |
| D9 | S13 Tests | Hand-made synthetic fixture with hand-calculated expected SQL feature values | Approved |
| D10 | S13 CI | GitHub Actions: lint, unit tests, dbt build and fixture tests on PostgreSQL 16, app Docker build; dummy secrets for the fixture only | Approved |
| D11 | S13 CI | ruff, default rules, 120-character lines | Approved |
| D12 | S13 CI | Every CI step run locally first | Approved |
| D13 | S13 CI | `requirements-dev.txt` for pytest and ruff | Approved |
| D14 | S14 BA pack | Process maps as Mermaid, exported to PNG with Playwright | Approved |
| D15 | S14 BA pack | Generic UK issuer as-is process; Amrit reviews accuracy | Approved |
| D16 | S14 BA pack | To-be process: four routes, expected-loss ranking, confirm then block, audit log, MI, monitoring | Approved |
| D17 | S14 BA pack | One-page problem statement | Approved |
| D18 | S14 BA pack | Stakeholder register, RACI, power/interest grid (generic roles) | Approved |
| D19 | S14 BA pack | Jira import CSV | **Dropped by Amrit** |
| D20 | S14 BA pack | Requirements inside `user_stories.md` | Approved |
| D21 | S14 BA pack | Traceability by file path | Approved |
| D22 | S14 BA pack | UAT dry run by the build team; business sign-off left for Amrit | Approved |
| D23 | S14 BA pack | Model card on SS1/23's five principles plus regulatory mapping | Approved |
| D24 | S14 BA pack | One consolidated `decision_log.md` | Approved |
| D25 | S14 BA pack | dbt lineage screenshot and data dictionary | Approved |
| D26 | S14 BA pack | British English, plain-English pass, one data caveat per document | Approved |
| D27 | S15 README | Two-minute story order | Approved |
| D28 | S15 README | Capacity curve as the README chart | Approved |
| D29 | S15 README | Scripted demo GIF | Approved |
| D30 | S15 App | Theme proposal | **Replaced by Amrit:** keep the app basic and minimal, structured as a guided flow that hiring managers, banking professionals and BAs can follow |
| D31 | S15 App | Replace deprecated `use_container_width` | Approved |
| D32 | S15 README | One-command pipeline script | **Dropped by Amrit** |
| D33 | S15 README | MIT licence for code; dataset not redistributed | Approved |
| D34 | S15 README | Author section with LinkedIn | **Set aside:** needs Amrit's LinkedIn URL |
| D35 | S15 README | CI badge and MLflow screenshot | **Dropped by Amrit** |
| D36 | S16 Clean machine | Fresh clone, separate Compose project and ports, full rerun, tear down only the test stack | Approved |
| D37 | S16 Clean machine | Reproducibility check against committed metrics | Approved |
| D38 | S17 Pre-push | Whole-history audit including a secrets scan | Approved |
| D39 | S17 Pre-push | Keep the commit email (already public on the first commit) | Default, to confirm at the pre-push report |
| D40 | S17 Pre-push | Keep the Claude co-author lines | Default, to confirm at the pre-push report |
| D41 | S17 Pre-push | Keep `CLAUDE.md` public | Default, to confirm at the pre-push report |
| D42 | S17 Pre-push | Fix the remote URL's trailing slash | Approved |
| D43 | S17 Push | Amrit pastes repo description and topics | Approved |
| D44 | S17 Push | Amrit runs `git push` himself after the pre-push report | Approved |
| D45 | S17 Push | One follow-up fix push allowed if CI fails only on GitHub | Approved |
| D46 | Parked | Tableau `rpt_*` tables | **Parked until further notice** |
| D47 | Housekeeping | Old Desktop copy deleted by Amrit, or on his explicit word | Approved |
| D48 | Housekeeping | Update `CLAUDE.md` layout and definition of done at the end | Approved |
| D49 | Housekeeping | Detailed report per section, then continue | Approved |
