# Requirements traceability matrix

Each requirement traced from the user story that needs it, to the tests that check it, to the evidence. Test IDs: TC = `test_cases.md`, UAT = `uat_script.md`. Stories and requirements: `user_stories.md`.

## Functional requirements

| Requirement | Story | Tests | Evidence |
|---|---|---|---|
| FR-01 Score every payment, using only prior information | US-01 | TC-05 to TC-08, TC-19 to TC-25, TC-50, TC-53 | `dbt/models/marts/fct_transaction_features.sql`; `src/final_model.py`; MLflow `final-evaluation`; `results_table.md` |
| FR-02 Rank open alerts by expected loss | US-01 | TC-37, UAT-02 | `app/db.py` (`open_queue`); `app/queue_page.py` |
| FR-03 Three strongest reasons per alert, from SHAP | US-02 | TC-30, TC-31, UAT-03 | `src/explain.py`; `app.alerts` (`reason_1` to `reason_3`, `reason_detail`) |
| FR-04 Reason wording states direction and handles missing history | US-02 | TC-33, TC-54 | `tests/test_reasons.py`; finding in `test_cases.md` |
| FR-05 Confirm fraud or clear, with a note, written back | US-03 | TC-39, TC-40, TC-42, UAT-04, UAT-05, UAT-08 | `app/db.py` (`record_decision`); `app.alerts` |
| FR-06 Close only open alerts; append every decision to an audit log | US-03, US-13 | TC-41, TC-65, UAT-06, UAT-10 | `app.alert_decision_log`; `app/queue_page.py` (`decide`); defect record in `uat_script.md` |
| FR-07 Show the card's other alerts | US-04 | TC-38, UAT-03 | `app/db.py` (`card_alerts`) |
| FR-08 Route each payment to its cheapest expected action | US-05, US-06 | TC-28, TC-55, UAT-05, UAT-09 | `src/decisioning.py` (`action_costs`, `four_route`); `scoring.decisions`; `process_to_be.png` |
| FR-09 Respect analyst capacity | US-06 | TC-27, TC-55 | `src/decisioning.py` (`four_route`); `config/decision_params.yaml` |
| FR-10 MI: alerts worked, hit rate, value saved, false positive rate | US-07 | TC-43, TC-59, UAT-07 | `app/mi_page.py`; `app/metrics.py` |
| FR-11 Rules, logistic regression and XGBoost compared at the same workload | US-08 | TC-23 | `results_table.md` (`src/results_table.py`); MLflow `final-evaluation` |
| FR-12 Editable cost assumptions, sensitivity, annual business case | US-08 | TC-26, TC-29, TC-56 | `config/decision_params.yaml`; `business_case.md`; `figures/sensitivity_tornado.png`; `figures/capacity_curve.png`; `figures/calibration.png` |
| FR-13 Monthly drift, outcome and fairness monitoring with RAG thresholds | US-09 | TC-46 to TC-49, TC-58 | `src/drift.py`; `monitoring.drift_monthly`; `monitoring.md`; `figures/drift_psi.png` |
| FR-14 Every run logged; chosen model registered | US-10 | TC-25 | MLflow experiments and the `fraud-xgboost@champion` registry entry; `model_card.md` |
| FR-15 Fairness audit by age band and gender | US-11 | TC-35, TC-36, TC-57 | `src/fairness.py`; `fairness_audit.md`; `figures/fairness_interruptions.png` |

## Non-functional requirements

| Requirement | Story | Tests | Evidence |
|---|---|---|---|
| NFR-01 Card numbers only in the raw table; HMAC token downstream | US-12 | TC-09 to TC-12, TC-51 | `dbt/models/staging/stg_transactions.sql`; dbt test `assert_no_personal_data_downstream` |
| NFR-02 No personal fields as features; age and gender restricted | US-11, US-12 | TC-09, TC-10, TC-34 | `dbt/models/restricted/fairness_attributes.sql`; `data_dictionary.md` |
| NFR-03 No data leakage | US-10 | TC-03, TC-06, TC-08, TC-17, TC-19 to TC-22, TC-27, TC-53 | `src/leakage_checks.py`; `tests/test_sql_features.py`; MLflow `leakage-checks` |
| NFR-04 Reproducible: fixed seed, every run logged, model versioned | US-10 | TC-25, TC-66 | MLflow; `config/decision_params.yaml` (`random_seed`); clean-machine rerun (S16) |
| NFR-05 `docker compose up` starts everything on a clean machine | US-14 | TC-44, TC-66 | `docker-compose.yml`; `app/Dockerfile`; clean-machine test (S16) |
| NFR-06 Automated tests and lint in CI | US-14 | TC-60, TC-61 | `.github/workflows/ci.yml`; `tests/` |
| NFR-07 Secrets only in `.env`, never committed | US-12 | TC-45, TC-67 | `.gitignore`; `.env.example`; `.dockerignore`; pre-push secrets scan (S17) |
| NFR-08 Explanations exact and truthful | US-02 | TC-30, TC-54 | `src/explain.py`; `tests/test_reasons.py` |
| NFR-09 A newcomer can follow the app; British English | US-15 | TC-62, TC-63, UAT-01 | `app/overview_page.py`; `docs/` |

## Coverage check

Every story US-01 to US-15 maps to at least one requirement, and every requirement to at least one test. TC-66 (clean-machine rerun) and TC-67 (pre-push secrets scan) are completed in S16 and S17.
