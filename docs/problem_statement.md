# Problem statement

## The problem

A card fraud operations team gets more alerts than its analysts can work. Today the alerts come from fixed rules ("amount at least 10x the card's average", "night-time and over $500"), and analysts work them roughly in the order the rules produced them. Three things go wrong:

1. **Analysts spend most of their time on genuine customers.** Three in four rules alerts turn out to be genuine (hit rate 24.8% on the test months).
2. **Fraud that doesn't trip a rule goes straight through.** The rules' alerts catch 80.6% of fraud value; most of the rest is mid-sized payments ($100 to $499, mainly in-store grocery) that no rule describes.
3. **Every decision has to be explained** to the customer who was interrupted, to internal audit and to the regulator. A score with no reason attached can't be.

**The business question:** which alerts should an analyst see first, and can each one be explained to a customer, an auditor and the regulator?

## Current state, in numbers

From the test months (21 Jun to 31 Dec 2020) of the simulated dataset: 555,719 payments on 999 cards, 2,145 of them fraud (0.39%).

| Measure | Rules today |
|---|---|
| Analyst alerts a day | 20.9 |
| Hit rate (alerts that are fraud) | 24.8% |
| Fraud value caught by the alerts | 80.6% |
| Fraud value protected, counting card blocks after a confirmed fraud | 93.2% |
| Genuine customers interrupted per 10,000 genuine payments | 61.1 |
| Alerts with a written reason | Rule name only (for example "A2 unusual amount") |

The data is simulated (Sparkov) and small: about 2,900 payments a day. A real UK issuer sees millions, so analyst capacity is the binding constraint there. To keep the question honest at this scale, the analyst budget is set to what the rules use today (21 alerts a day): the model must do better **with the same workload**, and the capacity curve then shows how much workload it really needs.

## Objectives and how success is measured

| # | Objective | Measure | Target |
|---|---|---|---|
| O1 | Stop more fraud | Fraud value protected (including card blocks) | Above the rules' 93.2% |
| O2 | No extra analyst workload | Analyst alerts a day | At or below 21 |
| O3 | Less time wasted on genuine customers | Analyst hit rate | Above the rules' 24.8% |
| O4 | Fewer genuine customers interrupted (Consumer Duty) | Interruptions per 10,000 genuine payments | At or below the rules' 61.1 |
| O5 | Every decision explainable | Alerts with three plain-English reasons | 100% |
| O6 | Fair to every customer group | Fairness audit flags by age band and gender | None |
| O7 | A decision the business can make | Annual cost against the rules, with sensitivity | Positive in every scenario tested |

Results against these objectives are in the README, `business_case.md`, `fairness_audit.md` and the traceability matrix.

## Scope

**In scope:** a rules baseline; logistic regression and XGBoost models; cost-based routing to four treatments (approve, in-app step-up, analyst review, decline and block); expected-loss ranking; confirm then block; three plain-English reasons per alert; an analyst queue that records decisions; MI; probability calibration, capacity curve and sensitivity analysis; a fairness audit; drift monitoring; PCI tokenisation and data minimisation; a model card and decision log on PRA SS1/23 principles; BA documentation.

**Out of scope** (agreed 15 Nov 2026): a real-time scoring API, replaying analyst decisions, monthly backtesting, point-of-compromise analysis, SLA timers, user login. Tableau dashboards are parked.

## Assumptions

All editable in `config/decision_params.yaml` and tested in the sensitivity analysis.

| Assumption | Value |
|---|---|
| Analyst cost and time | $32 an hour, 5 minutes a review ($2.67 a review) |
| Analyst capacity | 21 alerts a day |
| In-app step-up | $0.50 a challenge; 95% of genuine customers confirm; 10% of fraudsters get through |
| Wrongly declining a genuine customer | $20 |
| Loss on a missed fraud | 100% of the payment |
| Time from confirmed fraud to card block | 1 hour |

## Constraints

| Constraint | What it means here |
|---|---|
| PCI DSS | Card numbers stay in the raw table; every later layer uses a keyed hash (token) |
| UK GDPR (data minimisation; Article 22) | Names, address, date of birth and gender never reach the model; a person can review any automated decline |
| FCA Consumer Duty | Interrupting genuine customers is a harm and is measured, as is fairness between groups |
| Equality Act 2010 | No indirect discrimination by age or sex; audited, not assumed |
| PRA SS1/23 | Model card, decision log, validation evidence, monitoring with thresholds and an owner |
| Strong Customer Authentication (UK) | In-app step-up is the bank's existing authentication, used as a treatment |
| No data leakage | Train on earlier months, test on later ones; features use only what was known before each payment |
