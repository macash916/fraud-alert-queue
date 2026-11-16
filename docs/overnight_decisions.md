# Decisions made overnight for Amrit's review

On 16 Nov 2026 (00:45) Amrit chose **option A**: Claude continues overnight using the recommended option wherever a design question comes up, records every such choice here, and commits each finished section locally (no push). Amrit approves or reverses each item in the morning; anything reversed gets reworked.

Each entry gives the question, the option chosen, the alternatives, and why.

| # | Section | Question | Chosen (recommended) | Alternatives | Why |
|---|---|---|---|---|---|
| O1 | 7c Final model | Which settings become the production model? | XGBoost run 10 settings (best validation PR-AUC 0.983), retrained on all training months | Any of the other 19 settings (all PR-AUC 0.957 to 0.983) | Selection rule agreed earlier: best PR-AUC on validation |
| O2 | 7c Final model | How is the model versioned? | MLflow model registry `fraud-xgboost`, alias `champion` (version 1) | Plain run artefact only | Registry and aliases are how model risk tracks which version is live |
| O3 | 7c Final model | Where do scores live? | New PostgreSQL schema `scoring.model_scores`, separate from dbt's `analytics` | A dbt model; CSV files | Python writes scores; dbt owns `analytics`. Keeps ownership clear |
| O4 | 7c Final model | Keep logistic regression? | Yes, as the comparison baseline only, scored on test months | Drop it | The Definition of done compares rules, logistic regression and XGBoost |
