# Decisions made overnight for Amrit's review

On 16 Nov 2026 (00:45) Amrit chose **option A**: Claude continues overnight using the recommended option wherever a design question comes up, records every such choice here, and commits each finished section locally (no push). Amrit approves or reverses each item in the morning; anything reversed gets reworked.

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
