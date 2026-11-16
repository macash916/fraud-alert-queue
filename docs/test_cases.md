# Test cases

Each test states what is checked, how, what should happen and what did happen. Tests are added as each part of the build lands. Automated tests live in `tests/` and run in GitHub Actions; the checks below were run by hand against the full dataset.

## Data load

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-01 | Every source row is loaded | Count rows in each CSV with pandas; count `raw_transactions` by `source_file` | Train 1,296,675 and test 555,719 in both | ✅ Pass, 15 Nov 2026 |
| TC-02 | No duplicate transactions | `trans_num` is the primary key, so the load fails on a duplicate | Load completes | ✅ Pass |
| TC-03 | Test period starts after training ends | Compare latest train timestamp with earliest test timestamp | Train ends first | ✅ Pass (train ends 21 Jun 2020, test starts 21 Jun 2020, later in the day) |
| TC-04 | ZIP codes keep leading zeros | Count ZIPs not 5 characters long | 0 | ✅ Pass |

## Feature model

The features were first built as a SQL view and are now the dbt model `analytics.fct_transaction_features`. TC-05 to TC-08 were rerun against the dbt model with the same results.

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-05 | One feature row per transaction | Count `fct_transaction_features` against `raw_transactions` (automated: `assert_row_counts_reconcile`) | 1,852,394 in both | ✅ Pass |
| TC-06 | Features never see the current or later transactions | Count rows with no history (`amt_vs_avg`, `secs_since_last` NULL) | Exactly one per card: 999 | ✅ Pass (automated: `assert_first_transaction_has_no_history`) |
| TC-07 | SQL features match an independent calculation | `src/spot_check_features.py` recalculates all 14 features in pandas for 5 cards (3 with the most fraud, 2 busiest with none) and compares every transaction | 0 mismatches | ✅ Pass: 164,234 values, 0 mismatches (14 features; 105,579 values when there were 9) |
| TC-08 | TC-07 can actually fail | Plant a leak in the pandas version (count the current transaction in its own 24h window) and rerun | Mismatches reported, exit code 1 | ✅ Pass: 23,462 mismatches flagged |
| TC-18 | Lever B features stay in valid ranges | dbt test `assert_new_features_in_range`: shares 0–1, ratios positive, small-payment count ≤ all payments, first payment has no history | No violations | ✅ Pass |

## Data protection and dbt build

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-09 | No card number or personal field exists in any dbt model | dbt test `assert_no_personal_data_downstream` scans every column in the `analytics` schema | No matching columns | ✅ Pass |
| TC-10 | TC-09 can actually fail | Plant a table with a `cc_num` column in `analytics`, run the test, then remove it | Test fails | ✅ Pass: failed on the planted column |
| TC-11 | Tokenisation keeps cards distinct | dbt test `assert_one_token_per_card`: distinct tokens against distinct card numbers | 999 = 999 | ✅ Pass |
| TC-12 | Tokens can be reproduced independently | Spot check recomputes each token in Python (HMAC-SHA256) and finds the card in the dbt model | All 5 cards found | ✅ Pass |
| TC-13 | Velocity features are internally consistent | dbt test `assert_velocity_windows_consistent`: 1h count ≤ 24h count ≤ prior history, spend ≥ 0 | No violations | ✅ Pass |
| TC-14 | Full dbt build | `dbt build`: 2 models and 26 data tests | All pass | ✅ Pass: 28 of 28 |

## Rules baseline

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-15 | Every payment gets exactly one valid route | dbt tests: `rules_route` not null and one of analyst_review, step_up, approve; `trans_num` unique | All pass | ✅ Pass |
| TC-16 | Routing follows the agreed priority (analyst wins over step-up) | dbt test `assert_rules_routing_priority` compares each route with its rule flags | No violations | ✅ Pass |
| TC-17 | Rules weren't tuned on the test months | Thresholds chosen from training-month profiling only; train and test results compared | Similar performance in both periods | ✅ Pass: 82.0% of fraud value caught in train, 82.1% in test |

## Model validation: leakage checks

XGBoost scored ROC-AUC 0.9997 and PR-AUC 0.983 on the validation months (Jan to 21 Jun 2020). By project rule that is treated as a possible leak until proven otherwise. `src/leakage_checks.py` runs four checks with the best XGBoost settings; results are logged in the MLflow experiment `leakage-checks`.

| ID | What is checked | How | Expected if leak-free | Result |
|---|---|---|---|---|
| TC-19 | The pipeline doesn't leak the label into features | Shuffle the fraud labels in the fit months, retrain, score validation | ROC-AUC about 0.5 | ✅ Pass: 0.459 |
| TC-20 | The high score comes from the data, not from history windows | Train on amount, category and hour only (current payment, no history, no windows) | Near-perfect if the simulator makes fraud easy to separate | ✅ Explained: ROC-AUC 0.9975, PR-AUC 0.851. History features lift PR-AUC to 0.983 |
| TC-21 | The result doesn't rest on the 91 fraud-only cards | Score validation without those cards | Little change | ✅ Pass: PR-AUC 0.981 against 0.983 |
| TC-22 | No single feature dominates suspiciously | XGBoost share of total gain | Importance spread across plausible features | ✅ Pass: top is spend vs daily norm (31%), then hour (16%), grocery in-store (12%); card history count only 2% |

## Final evaluation (test months, used once)

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-23 | The model holds up on months it has never seen | Retrain on all training months, score 21 Jun to 31 Dec 2020 once (`src/final_model.py`) | Performance close to validation | ✅ Pass: PR-AUC 0.974 (validation 0.983); 99.75% of fraud value caught at the rules' volume against 80.6% for the rules |
| TC-24 | Probabilities stay calibrated when the fraud rate shifts | Mean predicted fraud rate against actual on the test months | Close | ✅ Pass: 0.380% predicted, 0.386% actual |
| TC-25 | Scores are stored for every scored payment | Row count of `scoring.model_scores` | 371,825 validation + 2 × 555,719 test = 1,483,263 | ✅ Pass |

## Decisioning

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-26 | Probabilities are calibrated by score band | Mean predicted against actual fraud rate in 9 score bands, validation and test (`figures/calibration.png`) | Close to the diagonal | ✅ Pass: close throughout; slightly cautious in the 0.1 to 0.7 bands |
| TC-27 | Daily volumes are set without seeing the test months | Thresholds computed on validation, applied to test (`src/decisioning.py`) | Test volumes near, not exactly at, targets | ✅ Pass: analyst volumes on test differ from target, as expected out of sample |
| TC-28 | Every test payment gets exactly one valid route | `scoring.decisions` primary key on `trans_num`, CHECK on route | 555,719 rows, all valid | ✅ Pass |
| TC-29 | The business case holds under each assumption | Sensitivity: each assumption moved down and up | Saving stays positive | ✅ Pass: lowest $85k a year (loss rate 50%), base $155k |

## Explainability and alerts

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-30 | SHAP values are exact for the model | Compare `shap.TreeExplainer` with XGBoost's own TreeSHAP on a test model | Identical | ✅ Pass |
| TC-31 | Every alert has three plain-English reasons | Count alerts with an empty reason | 0 | ✅ Pass: 0 of 5,245 |
| TC-32 | Refreshing scores never overwrites an analyst's decision | Record a decision on one alert, rerun `src/explain.py`, check it, then remove it | Decision unchanged | ✅ Pass: still closed / confirmed_fraud |
| TC-33 | Reasons say which way a payment is unusual | Review all reason patterns; reword ratios below 1, small amounts and long gaps | No reason reads as a non-reason | ✅ Pass after rewording (126 low ratios, 483 small amounts, 586 long gaps) |

## Fairness

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-34 | Protected characteristics never reach the analytical layer | dbt test `assert_no_personal_data_downstream` after adding the restricted model | Pass | ✅ Pass |
| TC-35 | Age bands cover every payment | dbt accepted-values test on `age_band` | Pass | ✅ Pass after adding "Under 18" (13 cards aged 13 to 17 found) |
| TC-36 | No customer group is materially worse off under the model | `src/fairness.py`: interruptions and detection by age band and gender with 95% intervals | No flags | ✅ Pass: no flags; one watch item (female/male interruption gap, 1.09x overall) |

## Analyst app and MI

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-37 | Queue ranks open alerts by expected loss within each route | Open each route tab; compare with `ORDER BY expected_loss_usd DESC` in SQL | Same order | ✅ Pass |
| TC-38 | Every alert shows three plain-English reasons and its route | Select alerts on each route | Three reasons, route description shown | ✅ Pass |
| TC-39 | Confirm fraud writes back | Enter a name, add a note, click Confirm fraud | `app.alerts` closed with decision, note, name, time; one row in `app.alert_decision_log` with the score and model version seen; alert leaves the queue | ✅ Pass |
| TC-40 | Not fraud writes back on a selected row | Select row 3 on another route, click Not fraud | Same as TC-39 for that alert; selection returns to the top alert | ✅ Pass (selection reset added after the first run showed the next alert inheriting the selection) |
| TC-41 | An alert can't be worked twice | Call the decision function again on a closed alert | Rejected; no second log row | ✅ Pass |
| TC-42 | Decisions need an analyst name | Leave the name empty | Buttons disabled, prompt shown | ✅ Pass |
| TC-43 | MI figures match the recorded decisions | Two test decisions (1 fraud $5,920.50, 1 genuine) | Worked 2, hit rate 50%, value saved $5,921, false positive rate 50% | ✅ Pass. Test decisions then removed so MI starts clean |
| TC-44 | `docker compose up` starts the app with the database | `docker compose up -d --build app` | `fraud_app` healthy on 127.0.0.1:8501, queue loads | ✅ Pass |
| TC-45 | No data or secrets in the app image | List `/srv` inside the container | Only the app's Python files, its requirements and the Streamlit config | ✅ Pass |

## Monitoring

| ID | What is checked | How | Expected | Result |
|---|---|---|---|---|
| TC-46 | Monthly drift report runs end to end | `src/drift.py` over the test months | 189 checks written to `monitoring.drift_monthly`, heatmap and MLflow run produced | ✅ Pass |
| TC-47 | Model score is stable after go-live | Score PSI each month against the training months | Green every month | ✅ Pass: 0.005 to 0.036 |
| TC-48 | Seasonal change is told apart from real change | December's red features compared with December 2019 | Seasonal features go green against last year | ✅ Pass: five December reds all 0.000 to 0.003 against Dec 2019 |
| TC-49 | Monitor catches a feature that drifts by design | "Length of card history" PSI | Flagged | ✅ Flagged red every month, also against the same month last year; raised as a feature-design finding |

## Findings from testing

- **91 of the 999 cards contain nothing but fraud.** They average 10 transactions over 1.7 days, and they are exactly the 91 cards that appear in only one of the two files. That's 904 transactions, about 9% of all fraud. These cards have no genuine history, so "amount vs average" is measured against earlier fraud, and a model could learn "new card means fraud". Real fraud on newly compromised or newly opened cards does exist, so this is plausible, but it needs watching in SHAP and goes in the decision log.
- **Distance from home doesn't separate fraud from genuine spend** (average 76.3 km against 76.1 km). The simulator places merchants randomly near the customer. The feature stays because it matters in real card fraud, but it should rank low.
