# Model card: card fraud alert model (`fraud-xgboost`, version 2)

**Status:** draft for review, not independently validated. Structured on the five principles of the PRA's supervisory statement SS1/23 (model risk management). Built on **simulated data** (Sparkov): it shows the method and the controls, not the performance of a live model.

## Summary

| Item | Detail |
|---|---|
| Model | XGBoost gradient-boosted trees, registered in MLflow as `fraud-xgboost`, version 2, alias `champion`. Version 2 is the same settings and data as version 1, retrained with a fixed row order so a rebuild reproduces it exactly (decision D50) |
| Purpose | Estimate the probability that a card payment is fraud, so each payment can be routed to its cheapest safe treatment and analysts can work the highest expected loss first |
| Decisions it drives | Approve, in-app step-up, analyst review, or decline and block (`src/decisioning.py`); alert ranking; three reasons per alert |
| Users | Fraud analysts (queue), operations team leader (MI), model owner (monitoring) |
| Not for | Credit decisions, customer profiling, marketing, anything other than fraud screening of card payments; populations unlike the training data without revalidation |
| Owner (role) | Fraud analytics |
| Proposed risk tier | **High**: it can decline payments and block cards automatically, which directly affects customers (Consumer Duty, UK GDPR Article 22), and errors carry fraud losses |

## Principle 1: Model identification and risk classification

- **Inventory entry:** name, version, owner, purpose and tier as above; artefacts and run history in MLflow (`final-evaluation` experiment and the model registry).
- **Materiality:** high customer impact (automated declines) and high financial impact (fraud losses). Complexity: medium (tree ensemble, explained per decision with SHAP).
- **Dependencies:** the dbt feature model (`fct_transaction_features`), the cost assumptions (`config/decision_params.yaml`) and the routing logic. A change to any of them is a model change.

## Principle 2: Governance

| Role | Responsibility here |
|---|---|
| Head of fraud strategy | Accountable for the business use and the go-live decision |
| Model owner (fraud analytics) | Development, documentation, monitoring, retraining proposals |
| Model risk management (second line) | Independent validation, approval of material changes |
| Compliance and DPO | Fairness audit sign-off, Article 22 route, data minimisation |
| Internal audit (third line) | Periodic review of the control and the decision trail |

Every design decision, its alternatives and who made it is in `decision_log.md`. RACI in `stakeholders.md`.

## Principle 3: Development, implementation and use

### Data
- Kaggle "Credit Card Transactions Fraud Detection" (simulated with Sparkov): 1,852,394 payments on 999 cards, 1 Jan 2019 to 31 Dec 2020, about 0.5% fraud overall.
- **US data, UK controls:** the model is designed for a UK card issuer, so it is governed under UK rules (SS1/23, Consumer Duty, UK GDPR). The simulated customers are US residents and amounts are in US dollars; no public UK dataset of this kind exists. Before any UK use the model would be revalidated on the issuer's own sterling data (Principle 4).
- **Split by time, never at random:**
  - Model selection: fit on calendar 2019, compare on 1 Jan to 21 Jun 2020.
  - The chosen settings were then retrained on all training months (to 21 Jun 2020).
  - Test months (21 Jun to 31 Dec 2020: 555,719 payments, 2,145 frauds) were used **once**, for the final evaluation.
- **Controls:** card numbers are tokenised (HMAC-SHA256) in the dbt staging layer; names, address, date of birth, gender and job never reach the features. Age and gender exist only in a restricted table for the fairness audit. See `data_dictionary.md`.

### Inputs (16)
Payment amount, hour of day, merchant category (one-hot), and 13 behavioural features built in SQL from the card's earlier payments only: payments in the last hour and 24 hours, spend in the last 24 hours, length of card history, amount against the card's average, distance from home, new merchant, time since the last payment, amount against the category norm, first use of the category, how usual this time of day is for the card, small payments in the last 24 hours, and 24-hour spend against usual daily spend. Definitions are in the data dictionary; every value was checked against an independent pandas calculation (TC-07) and against hand-worked answers on a test fixture (TC-50).

### Method
- XGBoost, 800 trees, depth 4, learning rate 0.05, subsample 0.8, column sample 0.8. Chosen as the best of 20 logged settings by validation PR-AUC; logistic regression (6 settings) is kept as the comparison.
- **No reweighting of the rare fraud class**, so probabilities stay honest for expected-loss ranking. A weighted challenger was to be tried only if calibration or ranking was poor; it wasn't needed (TC-24, TC-26).
- Missing history (a card's first payment) is left missing; XGBoost handles it natively.

### Performance (test months, used once)

| Measure | XGBoost | Logistic regression | Rules |
|---|---|---|---|
| PR-AUC | 0.974 (validation 0.983) | 0.574 | n/a |
| ROC-AUC | 0.9995 | 0.958 | n/a |
| Brier score | 0.0004 | 0.0023 | n/a |
| Mean predicted against actual fraud rate | 0.381% against 0.386% | 0.374% against 0.386% | n/a |
| At the rules' workload (20.9 alerts a day): precision | 52.1% | 36.7% | 24.8% |
| Recall | 98.6% | 69.4% | 47.0% |
| Fraud value caught | 99.8% | 85.9% | 80.6% |
| Total cost (fraud losses + analyst time, with card blocks) | $7,027 | $144,706 | $94,596 |

Sources: MLflow `final-evaluation`; `results_table.md`. The four-route policy and its business case (about $156k a year saved against the rules, positive in every sensitivity case) are in `business_case.md`.

### Why the results are believed, despite looking very good
Results this strong are treated as a possible bug until explained (TC-19 to TC-22):
- Shuffled labels give ROC-AUC 0.42: the pipeline carries no hidden label.
- A model on amount, category and hour alone (no history at all) reaches ROC-AUC 0.9975: **the simulator makes fraud easy to separate.** This is the main reason the numbers would not carry over to a real book.
- Removing the 91 cards that hold nothing but fraud barely changes the result (PR-AUC 0.981 against 0.983).
- No single feature dominates suspiciously.

### Explainability
- SHAP (TreeExplainer) splits every score into feature contributions; checked to match XGBoost's own values exactly (TC-30).
- Each alert shows its three strongest reasons in plain English with the payment's own values. Wording is tested in both directions; testing found and fixed a misleading card-history reason (TC-54).
- Largest contributors overall (mean absolute SHAP share): amount 15.7%, amount against category norm 15.5%, merchant category 11.2%, spend in last 24 hours 11.0%, hour of day 10.0%.

### Fairness (Consumer Duty, Equality Act)
No age band or gender group is flagged (`fairness_audit.md`).
- The model interrupts fewer genuine customers than the rules overall (54.7 against 61.1 per 10,000), and closes a protection gap the rules had (women's fraud detected 42% under the rules against 55% for men; 97% against 99% under the model).
- **Watch item:** genuine women are interrupted more than genuine men (60.9 against 47.3 per 10,000), below the flag threshold. The likely cause is the population-wide category norm feature; a customer-specific version is the recommended challenger.

### Implementation and use
Batch scoring of a historical period; results in PostgreSQL (`scoring.*`, `app.alerts`); a Streamlit queue records analyst decisions with an audit log of the score, route and model version shown. Real-time scoring is out of scope.

## Principle 4: Independent validation

**Status: not independently validated.** The developer's own evidence is in `test_cases.md` (TC-01 to TC-70), including leakage checks, a planted-leak test, calibration, a single use of the test months, and CI that rebuilds the SQL on a hand-checked fixture. A second-line validator should, as a minimum:

1. Rerun the pipeline from raw data and reproduce the test metrics (fixed seed).
2. Challenge the feature definitions for leakage (window boundaries, same-second payments).
3. Review whether simulated-data performance says anything about the target portfolio; agree a pilot design with real data.
4. Challenge the cost assumptions and the routing thresholds.
5. Review the fairness method and the watch item.
6. Confirm the monitoring thresholds and runbook are workable.

## Principle 5: Risk mitigants

| Risk | Mitigant |
|---|---|
| Wrong automated decline | Analyst reviews every decline afterwards and can reinstate the customer; decline only where the expected cost says it's cheapest |
| Analyst overload | Analyst review is capped at capacity; overflow takes its next-cheapest action |
| Model degrades or data changes | Monthly drift, outcome and fairness monitoring with red/amber/green thresholds, an owner and a runbook (`monitoring.md`) |
| Model failure or withdrawal | The rules baseline stays built in dbt and can take over routing |
| Misleading explanations | Reason wording tests; SHAP matches the model exactly |
| Personal data misuse | Tokenisation, data minimisation, restricted fairness schema, dbt tests that fail if personal data appears downstream |
| Untraceable decisions | Append-only decision log with score, route and model version; MLflow run history; decision log of design choices |

## Regulatory mapping

| Requirement | Where it's addressed |
|---|---|
| PRA SS1/23 | This card, `decision_log.md`, `test_cases.md`, `monitoring.md` |
| FCA Consumer Duty | Interruptions measured per 10,000 genuine payments; fairness audit; reasons for every alert; in-app step-up instead of a phone call |
| Equality Act 2010 | Fairness audit by age band and gender, with confidence intervals |
| UK GDPR: data minimisation | Personal fields dropped in staging; restricted schema |
| UK GDPR Article 22 | Declines are reviewed by an analyst, who can overturn them |
| PCI DSS | Card numbers only in the raw table; HMAC token downstream; key in `.env` |

## Known limitations

1. **Simulated, highly separable data.** Real fraud is harder to separate; expect much lower precision and recall on a real book.
2. **Small book:** 999 cards, about 2,900 payments a day.
3. **"Length of card history" drifts by construction:** a running count that only grows. A capped or banded version is recommended (`monitoring.md`).
4. **Population-wide category norm** is the likely driver of the gender interruption gap.
5. **Labels are complete and immediate here.** Live fraud labels arrive 30 to 90 days late.
6. **Step-up confirm and pass rates are assumptions**, not measurements; they are the first thing to measure in a pilot.
7. **No login:** analysts type their name. Production would need authentication and role-based access.
8. **Batch, not real time.**

## Approvals (to be completed)

| Role | Decision | Date |
|---|---|---|
| Model owner | Pending | |
| Model risk management | Pending (validation not started) | |
| Compliance and DPO | Pending | |
| Head of fraud strategy | Pending | |
