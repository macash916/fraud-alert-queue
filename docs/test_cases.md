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
| TC-07 | SQL features match an independent calculation | `src/spot_check_features.py` recalculates all 9 features in pandas for 5 cards (3 with the most fraud, 2 busiest with none) and compares every transaction | 0 mismatches | ✅ Pass: 105,579 values, 0 mismatches |
| TC-08 | TC-07 can actually fail | Plant a leak in the pandas version (count the current transaction in its own 24h window) and rerun | Mismatches reported, exit code 1 | ✅ Pass: 23,462 mismatches flagged |

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

## Findings from testing

- **91 of the 999 cards contain nothing but fraud.** They average 10 transactions over 1.7 days, and they are exactly the 91 cards that appear in only one of the two files. That's 904 transactions, about 9% of all fraud. These cards have no genuine history, so "amount vs average" is measured against earlier fraud, and a model could learn "new card means fraud". Real fraud on newly compromised or newly opened cards does exist, so this is plausible, but it needs watching in SHAP and goes in the decision log.
- **Distance from home doesn't separate fraud from genuine spend** (average 76.3 km against 76.1 km). The simulator places merchants randomly near the customer. The feature stays because it matters in real card fraud, but it should rank low.
