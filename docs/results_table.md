# Results: rules against models at the same analyst workload

| Approach | Analyst alerts a day | Precision (hit rate) | Recall (frauds caught) | PR-AUC | Fraud value caught | Fraud value protected incl. card blocks | Total cost |
|---|---|---|---|---|---|---|---|
| Rules (A2, B2) | 20.9 | 24.8% | 47.0% | n/a | 80.6% | 92.5% | $94,596 |
| Logistic regression | 20.9 | 36.7% | 69.4% | 0.574 | 85.9% | 87.9% | $144,706 |
| XGBoost (champion) | 20.9 | 52.1% | 98.6% | 0.974 | 99.8% | 99.9% | $7,027 |

Test months (21 Jun to 31 Dec 2020, 555,719 payments, 2,145 frauds), each approach reviewing the same 4,058 payments (20.9 a day). Total cost = fraud losses + analyst time, with a confirmed fraud blocking the card after one hour. Simulated data; US dollars. Produced by `src/results_table.py`.

Rules cost more here than in `business_case.md` ($86.8k) because this comparison uses analyst review only; the business case also counts the rules' D1 step-up route. Logistic regression catches more fraud value per alert than the rules but costs more overall: its alerts reach fewer of the compromised cards (208 of 218, against 216 for the rules and 218 for XGBoost), so fewer cards are blocked before the next fraud.
