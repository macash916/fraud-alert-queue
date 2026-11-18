# Decision log

Every material design decision, the options considered, the reason, and who made it. Kept for model risk (PRA SS1/23 principle 2), audit and anyone picking the project up later.

**Who decided:** "Amrit" means Amrit Sharma decided directly. "Proposed by Claude, approved by Amrit" means the option was proposed by Claude (AI assistant used to build the project) and approved by Amrit, either one by one or as a reviewed batch, as noted in each section.

## 1. Scope, approach and early design (15 and 16 Nov 2026)

| # | Date | Decision | Alternatives considered | Why | Decided by |
|---|---|---|---|---|---|
| E1 | 15 Nov | PostgreSQL 16 in Docker as the system of record | Local PostgreSQL install on the Mac | Same database on any machine; `docker compose up` on a clean machine | Amrit |
| E2 | 15 Nov | Scope additions 1 to 9 for London bank BA/DA roles; real-time API, replay, backtesting, point-of-compromise analysis and SLA timers out of scope | A broader build | Depth on what UK banks assess (cost, fairness, model risk, BA artefacts) over breadth | Amrit |
| E3 | 15 Nov | Three-way routing with in-app step-up (customer confirms in the banking app), replacing "call the bank to release the charge"; genuine confirm 95%, fraudster pass 10%; separate analyst and step-up budgets | Analyst review or approve only | Amrit's design from card-fraud operations; links to UK Strong Customer Authentication; step-ups cost customer friction, so they get their own budget | Amrit |
| E4 | 15 Nov | Rules baseline: A2 (amount at least 10x card average) and B2 (22:00 to 04:00 and at least $500) to analyst review; D1 (new merchant and at least $500) to step-up; analyst wins; rules in dbt; designed on training months only | Other rule sets; rules in Python | An honest, analyst-style "today" to beat, built like a bank rules engine | Amrit |
| E5 | 15 Nov | Models compared with the rules at the same alert volume; money shown in US dollars | Compare at a default 0.5 threshold; convert to GBP | Same workload is the only fair comparison; the data is US-simulated | Amrit |
| E6 | 15 Nov | dbt layer with the essentials only: staging (tokenised, minimised) and features as tables, with tests and lineage | Views; a larger dbt project | Tables run window functions once; essentials keep it reviewable | Amrit |
| E7 | 15 Nov | Card tokens by keyed HMAC-SHA256, key in `.env` | Plain SHA-256 hash | Card numbers are short enough that an unkeyed hash can be brute-forced | Proposed by Claude, approved by Amrit |
| E8 | 15 Nov | Modelling levers A to D: confirm then block (1-hour delay); five extra features; four routes; expected-loss ranking | Transaction-level outcome only; fixed-rule routing | Evidence from the rules baseline: 67% of missed fraud came after the card was already alerted, and 92% of missed fraud dollars were $100 to $499 | Amrit |
| E9 | 15 Nov | Feature definitions: category norm across all cards; small payment under $20; 4-hour time-of-day bands | Customer-specific category norm; other cut-offs | Simple and leak-free; the customer-specific norm is now the recommended fairness challenger | Amrit |
| E10 | 15 Nov | Project moved out of the iCloud-synced Desktop to `~/Projects` | Keep it there | iCloud offloading stalled every Python and dbt start-up | Amrit |
| E11 | 16 Nov | Scope frozen; thin end-to-end slice, then deepen; README tells a two-minute story | Keep adding levers | Finish properly rather than wide | Amrit |
| E12 | 16 Nov | Validation: fit on 2019, compare on 1 Jan to 21 Jun 2020, retrain the chosen settings on all training months, use the test months once | Random split; repeated test use | Time split mirrors live use; one look at the test months keeps it honest | Amrit |
| E13 | 16 Nov | No reweighting of the fraud class; a weighted challenger only if calibration or ranking turned out poor | Class weights from the start | Honest probabilities are needed for expected loss; not needed in the end | Amrit |
| E14 | 16 Nov | Missing history: XGBoost native handling; logistic regression gets neutral fills plus a has-history flag | Fill zeros everywhere | Every payment stays scoreable without inventing history | Amrit |
| E15 | 16 Nov | Keep all 14 features for the first run; drop the two weak ones only if SHAP confirms they add nothing | Drop them up front | Let the evidence decide (see O17) | Amrit |
| E16 | 16 Nov | One-hot merchant category; a small logged search (20 XGBoost and 6 logistic regression settings); choose by validation PR-AUC and report business metrics | Large automated search | Every run is visible and explainable to model risk | Amrit |
| E17 | 16 Nov | MLflow upgraded from 2.17.2 to 2.22.1 (database migrated) | Pin protobuf below 6 | 2.17.2 conflicted with dbt's protobuf requirement | Amrit |
| E18 | 16 Nov | MLflow on host port 5001 | Port 5000 | macOS uses 5000 for AirPlay | Proposed by Claude, approved by Amrit |
| E19 | 16 Nov | One push at the very end, no versions; a detailed report after every section | Push as you go | Amrit's working preference | Amrit |
| E20 | 16 Nov | Tableau dashboards parked until further notice | Build them now | Not the priority; Streamlit covers the queue and MI | Amrit |

## 2. Overnight build, sections 7c to 11 (proposed by Claude overnight, approved by Amrit on 16 Nov 2026)

| # | Section | Question | Chosen | Alternatives | Why |
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

## 3. Remaining build, S12 to S17 (proposed by Claude, approved by Amrit as one batch on 16 Nov 2026, with his changes)

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
| D19 | S14 BA pack | Jira import CSV | **Dropped by Amrit** (briefly reconsidered on 16 Nov, see D51) |
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
| D34 | S15 README | Author section with LinkedIn | Approved; link supplied by Amrit |
| D35 | S15 README | CI badge and MLflow screenshot | **Dropped by Amrit** |
| D36 | S16 Clean machine | Fresh clone, separate Compose project and ports, full rerun, tear down only the test stack | Approved |
| D37 | S16 Clean machine | Reproducibility check against committed metrics | Approved |
| D38 | S17 Pre-push | Whole-history audit including a secrets scan | Approved |
| D39 | S17 Pre-push | Keep the commit email (already public on the first commit) | Default, to confirm at the pre-push report |
| D40 | S17 Pre-push | Claude co-author lines removed from commit messages; AI assistance stays disclosed in the README and this log | Amrit |
| D41 | S17 Pre-push | `CLAUDE.md` (the AI assistant's project brief) kept local only: removed from the repository and its history | Amrit |
| D42 | S17 Pre-push | Fix the remote URL's trailing slash | Approved |
| D43 | S17 Push | Amrit pastes repo description and topics | Approved |
| D44 | S17 Push | Amrit runs `git push` himself after the pre-push report | Approved |
| D45 | S17 Push | One follow-up fix push allowed if CI fails only on GitHub | Approved |
| D46 | Parked | Tableau `rpt_*` tables | **Parked until further notice** |
| D47 | Housekeeping | Old Desktop copy deleted by Amrit, or on Amrit's explicit word | **Done on Amrit's word (16 Nov 2026):** moved to the Bin (iCloud blocked a direct delete); Amrit empties the Bin |
| D48 | Housekeeping | Update the local project brief's layout and definition of done at the end | Approved |
| D49 | Housekeeping | Detailed report per section, then continue | Approved |
| D50 | Pre-push | Fix the training row order found by the clean-machine rerun (B-03); retrain and register the champion as version 2; refresh the published figures | Amrit |
| D51 | Pre-push | Jira backlog reconsidered and dropped again: the user stories, traceability matrix and UAT script already cover the agile artefacts, and a solo two-day build has no sprint history to show | Amrit |
| D52 | Pre-push | Keep US dollars and UK controls, and say why in the README and model card (the rules follow the bank, not the currency) | Amrit |
| D53 | Business review | As-is process map corrected from Amrit's operations review: rules both decline ("authorisation prohibited") and approve-and-alert; a text asks the customer to confirm; the queue runs in arrival order with a suspicious-merchant watchlist; customers phone the card fraud team directly, including when approve-and-alert payments are still held; a confirmed fraud blocks and reissues the card at once, and refunds and disputes go to the claims team | Amrit |
| D54 | Business UAT | Two defects Amrit found during UAT fixed before sign-off: no visible feedback after entering a name (TC-71) and an MI crash when the analyst filter is emptied (TC-72); the test name placeholder now reads "e.g. John Doe" | Amrit |
| D55 | Business UAT | Two more defects found in Amrit's UAT fixed before sign-off. TC-73: a refused decision (alert already worked by another analyst) is now a warning beside the decision buttons that stays until dismissed, not a toast that faded while the screen moved to another alert. TC-74: the decision buttons are always clickable, and without a name nothing is recorded and a warning asks for one; a disabled button had silently swallowed clicks. The UAT script's expected values were re-derived from the live queue after the tester chose to keep the earlier test decisions. All ten scenarios passed; signed off 18 Nov 2026, with a note that tester and product owner are the same person in this portfolio project | Amrit |

## 4. Decisions made while building S12 to S14 (proposed by Claude under the batch approval; for Amrit's review)

| # | Section | Decision | Alternatives | Why |
|---|---|---|---|---|
| S1 | S12 Monitoring | Score-drift baseline: the champion's scores on its own training months | The first test month | The development sample is the usual SS1/23 reference; it makes the alarm slightly early, the safe direction |
| S2 | S12 Monitoring | Any amber or red feature is also compared with the same calendar month a year earlier | Investigate by hand | The first run showed December reds; one comparison proved them seasonal |
| S3 | S12 Monitoring | "Length of card history" (red every month by construction) raised as a feature-design finding with a capped-feature challenger; no model change | Retrain now | Score and outcomes are stable; scope is frozen |
| S4 | S13 Tests | Fix the card-history and time-of-day reason wording (78 alerts said "Limited card history" for long histories) and regenerate the alerts | Leave as is | A misleading reason is a Consumer Duty and audit problem; no analyst decisions existed to protect |
| S5 | S13 Tests | Drift alarm test: +20% green, +50% amber, doubling red | Expect red at +50% | Measured PSI is 0.03, 0.16 and 0.45; the first expectation was wrong, not the monitor |
| S6 | S13 Tests | MI calculations moved to `app/metrics.py` | Test through the page | Testable without starting the app |
| S7 | App | Overview landing page; queue as four numbered steps; score breakdown as a towards-fraud / towards-genuine bar chart; plain light theme | Keep the analyst-only layout | Amrit's instruction (replacing D30): basic, structured, followable by hiring managers, banking professionals and BAs |
| S8 | S14 | Results for rules, logistic regression and XGBoost at the same workload, including total cost with card blocks (`src/results_table.py`) | Cost only for the XGBoost policies | The definition of done asks for cost at the chosen threshold for all three |
| S9 | S14 | Data dictionary and lineage generated from dbt's manifest; every column documented in the dbt YAML | Hand-written dictionary; dbt docs screenshot | Can't drift from the models |
| S10 | S14 | Process maps as Mermaid swimlanes with pain (P) and gain (G) markers explained in `process_maps.md` | Draw.io by hand | Versioned source; renders on GitHub |

## 5. v2: governed AI co-pilot (from 18 Nov 2026)

v2 adds a co-pilot that investigates an alert and drafts a cited case summary; the ML model still decides the risk and the analyst decides the outcome. Decisions marked "Proposed" were made by Claude on recommended defaults and wait for Amrit's approval at the next input session.

| # | Area | Decision | Alternatives | Why | Status |
|---|---|---|---|---|---|
| V1 | Benchmark | 30 alerts, blind: outcomes hidden, answer key in a separate folder, the four UAT cards left out, one alert per card, seed 2026 | Show the tester the outcomes; pick cases by hand | A blind expert benchmark is the only honest test of the co-pilot against an experienced analyst's judgement | Proposed |
| V2 | Benchmark | Stratified 15 fraud and 15 genuine across the three routes and weighted to hard cases (low-score fraud, high-score genuine, false declines); results reported per stratum | A random sample (would be about 95% genuine step-ups) | Tests judgement where it matters; the README will say it is not a sample of the live fraud rate | Proposed |
| V3 | Benchmark | Whether to show the outcome of earlier alerts on the card | (a) hidden, as now; (b) shown if older than 7 days | (b) is more realistic: a bank knows the outcome of earlier investigations. The same rule applies to the tester and the co-pilot | **Approved by Amrit, 18 Nov 2026: option (b)** |
| V4 | Housekeeping | v2 working material in a local, gitignored `v2_prep/` folder until reviewed | Straight into `docs/` | Interview answers and the benchmark answer key are not published before Amrit has reviewed them | Proposed |
| V5 | Policy library | Analyst procedures written from Amrit's session A interview answers and credited to Amrit in this log | Amrit writes them from scratch | Fits the 6-hour input budget; still Amrit's knowledge | Proposed |
| V6 | Policy library | Sources S1 to S11 in the v2 source list; downloaded only after Amrit's yes | Different or fewer sources | All public and official; cover card fraud law, conduct, data protection and model risk | **Approved by Amrit, 18 Nov 2026: download** |
| V7 | Retrieval | Keyword plus embedding search, with embeddings from a small local model, stored in a PostgreSQL table, similarity computed in Python | pgvector extension; a hosted vector database | The library is small (a few thousand passages). No change to the Docker images, and the text never leaves the machine for indexing | Proposed |
| V8 | LLM | Claude as the main model; a small local open-weight model as the second; same prompts and tools behind one provider interface | One vendor only | Answers the FCA's single-vendor concern; needs about 10 GB of free disk | Proposed (disk space needed) |
| V9 | Licensing | Check whether retrieved passages from FCA, PRA and ICO material can be republished in the public repo; if unclear, publish code and citations only and keep the passages local | Publish everything | Avoids a copyright problem in a public portfolio | Proposed |
| V10 | App | Co-pilot runs on demand per alert and caches its draft in a new `app.copilot_drafts` table; it can never write a decision | Pre-generate drafts for all 5,129 alerts | Lower cost, and every draft is tied to a moment an analyst asked for it | Proposed |
| V11 | CI | Tests use recorded LLM responses; CI never needs an API key | Live calls in CI | Keeps CI free, repeatable and secret-free | Proposed |
| V12 | Governance | SS1/23 used as best practice, saying plainly that it formally applies to banks with internal-model approval for capital | Claim it applies directly | Accurate, and an easy point to win in interviews | Proposed |
| V13 | Governance | Article 22 answers checked against the Data (Use and Access) Act 2025 reforms before the co-pilot cites them | Cite the original Article 22 only | The law changed in 2025; a wrong citation would undermine the whole grounding story | Proposed |
| V14 | Budget | API spend capped at £10 (about $12), set by Amrit as a hard spend limit in the console. Build and debug on the local open-weight model (free); all scored runs on Claude Haiku 5.5; one batched Claude Opus 5.5 pass over the 30 benchmark alerts only if the remaining budget covers it. Cost per case measured on the first 5 runs before scaling | Opus or Sonnet for the scored runs (about $30 to $100) | Amrit's budget; the three-model comparison (free, cheapest, strongest) is a stronger result than one model | Proposed (Amrit set the £10 cap, 18 Nov) |
| V15 | App | One-screen redesign of the analyst app, as in the mock-up (`v2_prep/mockup/fraud_queue_mockup.html`): three panes (queue, case, decide), co-pilot draft with source chips beside the decision buttons, every v1 detail kept under "Show the evidence", Team view and Audit trail as tabs, a three-step guided tour, light and dark themes | Keep the v1 four-step page and add a co-pilot panel | Three of the four business UAT defects (TC-71, TC-73, TC-74) came from things happening out of the analyst's sight | **Approved by Amrit, 18 Nov 2026** |
| V16 | App | Claim on open: an alert opened by one analyst shows as taken to others and cannot be decided by them; a decision can be undone for 10 seconds before it is final in the audit trail | Keep refusing the second decision after the fact (TC-73 fix only) | Prevents the clash instead of warning about it; undo replaces "are you sure?" pop-ups | **Approved by Amrit, 18 Nov 2026** (with V15) |
| V17 | Policy library | FCA and PRA guidance (Consumer Duty, FG22/5, FG21/1, SS1/23, the FCA AI good and poor practice paper) held as the project's own short summaries, each with the exact paragraph reference and a link to the official page, not the regulators' wording. The terms of use of both sites forbid storing their content in a retrieval system without written permission | (b) ask the FCA and the Bank of England for permission; (c) leave them out | Keeps the library lawful and still lets the co-pilot cite paragraph by paragraph; the citation names the summary as the project's, never as a quotation | Proposed (Amrit to choose a, b or c) |
| V18 | Retrieval | A fixed banking-to-legal glossary of nine general terms (card, bank, block, unblock, customer, report, SCA, £35, automated decision) expands each query before search. Recall at 5 on the 17 checkable policy questions rose from 12 (71%) to 14 (82%) | Tune search weights; a larger embedding model | Every miss in the first run was the law using different words from an analyst. The score is reported as optimistic, because the glossary was written after seeing the misses; it is re-tested on new questions before the README quotes it | Proposed |
| V19 | LLM | Local model is qwen3:4b (2.5 GB), with nomic-embed-text for search, run through Ollama on the Mac. One draft took about 20 seconds | A 7 to 8 billion parameter model, as first planned | The machine has 8 GB of memory; a larger model would leave too little for PostgreSQL, MLflow and the app. The weaker local model makes the comparison with Claude a fair test of the exit plan, not a showcase | Proposed |
| V20 | Licensing | Downloaded source text and the built passage file are gitignored; only the code, the source list and citations are published. Legislation and ICO text are under the Open Government Licence and can be published later with attribution, once Amrit has reviewed them | Commit the passages now | Nothing third-party goes public before a human has checked it, matching V9 | Proposed |
