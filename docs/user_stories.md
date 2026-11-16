# User stories and requirements

Stories follow "As a / I want / so that", with acceptance criteria in Given / When / Then form and a MoSCoW priority (Must, Should, Could, Won't this time). Each story links to the requirements it creates; `traceability_matrix.md` links every requirement to its tests and evidence.

## Stories

### US-01 Work the riskiest alerts first (Must)
**As a** fraud analyst **I want** open alerts ranked by expected loss **so that** my limited time goes where the most money is at risk.
- Given open alerts on a route, when I open the queue, then they are ordered by fraud probability x amount, highest first.
- Given a $5,000 payment at 40% and a $50 payment at 90%, when both are open, then the $5,000 payment ranks higher.

Requirements: FR-01, FR-02

### US-02 See why a payment was flagged (Must)
**As a** fraud analyst **I want** three plain-English reasons on every alert **so that** I can judge it quickly and explain it to the customer.
- Given any alert, when I open it, then I see three reasons that use the payment's own values (for example "Amount is 75x a typical in-store shopping payment").
- Given a reason based on a ratio below 1 or on a card with no history, when it is shown, then the wording says which way the payment is unusual or that there is no history, never a misleading number.

Requirements: FR-03, FR-04, NFR-08

### US-03 Record my decision (Must)
**As a** fraud analyst **I want** to confirm fraud or clear a payment, with a note **so that** the outcome is recorded and the alert leaves the queue.
- Given an open alert and my name entered, when I click Confirm fraud or Not fraud, then the alert closes with my decision, note, name and time.
- Given an alert another analyst has just closed, when I try to decide it, then my decision is refused and I am told it was already worked.
- Given no name entered, when I look at the decision buttons, then they are disabled.

Requirements: FR-05, FR-06

### US-04 See the card's other alerts (Should)
**As a** fraud analyst **I want** every alert on the same card in one view **so that** I can spot a pattern and know whether the card has already been confirmed as compromised.
- Given an alert, when I open it, then all alerts on that card are listed with time, amount, probability and outcome.

Requirements: FR-07

### US-05 Confirm a payment in my banking app (Must)
**As a** customer **I want** to confirm an unusual payment in my banking app instead of phoning the bank **so that** a genuine payment goes through with little effort.
- Given a medium-risk payment, when it is scored, then it is routed to in-app step-up, not to an analyst or a decline.
- Given a step-up the customer doesn't answer, when the decision is simulated, then the payment goes to an analyst.

Requirements: FR-08

### US-06 Decline near-certain fraud at once (Should)
**As the** head of fraud strategy **I want** near-certain fraud declined and the card blocked straight away **so that** follow-on fraud is stopped without waiting for an analyst.
- Given a payment where declining is the cheapest action, when it is scored, then it is routed to decline and block, and an analyst reviews it afterwards so a genuine customer can be reinstated.

Requirements: FR-08, FR-09

### US-07 See what the team achieved (Must)
**As a** fraud operations team leader **I want** MI on alerts worked, hit rate, value saved and false positive rate **so that** I can manage throughput and quality.
- Given recorded decisions, when I open the MI page, then I see those four figures, alerts worked per day, and a breakdown by route and by score band.
- Given no decisions yet, when I open the MI page, then it says so instead of showing zeros as results.

Requirements: FR-10

### US-08 Decide on the business case (Must)
**As the** head of fraud strategy **I want** the model compared with the rules in money, with the assumptions editable and stress-tested **so that** I can make and defend the decision.
- Given the cost assumptions file, when the decisioning script runs, then it reports total cost for each policy and the annual saving against the rules.
- Given each assumption moved down and up, when the sensitivity analysis runs, then the saving is shown for every case.

Requirements: FR-11, FR-12

### US-09 Know when the model is going wrong (Must)
**As the** model owner **I want** monthly drift and outcome checks with red, amber and green status **so that** I find problems before losses or complaints do.
- Given a month of new payments, when monitoring runs, then each feature, the score, the outcomes and the fairness watch item get a status.
- Given a red feature, when monitoring runs, then it is compared with the same month a year earlier to tell seasonality from real change.

Requirements: FR-13

### US-10 Validate the model independently (Must)
**As** model risk management **I want** a model card, a decision log and test evidence **so that** I can validate the model under SS1/23.
- Given the repository, when I review it, then I find the model's purpose, data, features, performance, limitations and monitoring in one model card, and every design decision with its alternatives in the decision log.
- Given the leakage checks, when I read the test cases, then each has a result and evidence.

Requirements: FR-14, NFR-03, NFR-04

### US-11 Check the model is fair (Must)
**As the** compliance and Consumer Duty lead **I want** interruption and detection rates by age band and gender **so that** I can show no group is treated worse.
- Given the test months, when the fairness audit runs, then it reports both measures with 95% intervals for each group and flags any material, statistically clear difference.

Requirements: FR-15, NFR-02

### US-12 Keep card numbers and personal data out of the model (Must)
**As the** data protection officer and information security **I want** card numbers tokenised and personal fields dropped before any modelling **so that** the system meets PCI DSS and UK GDPR.
- Given the staging layer, when it is built, then no card number, name, address, date of birth or gender exists in any analytical table, and a dbt test proves it.
- Given the fairness audit's need for age and gender, when it runs, then it reads them from a separate restricted table that no model or app reads.

Requirements: NFR-01, NFR-02, NFR-07

### US-13 Reconstruct any decision later (Must)
**As** internal audit **I want** every analyst decision logged with the score, route and model version the analyst saw **so that** any decision can be reconstructed.
- Given a recorded decision, when I query the decision log table, then I see who decided, when, what, their note, the score, the route and the model version.

Requirements: FR-06

### US-14 Run and change it safely (Should)
**As** IT and the data platform team **I want** one command to start the services and automated tests on every change **so that** the system is supportable.
- Given a clean machine with Docker, when I run `docker compose up`, then PostgreSQL, MLflow and the app start.
- Given a push to the main branch, when CI runs, then lint, tests (including the SQL feature tests) and the app image build all run.

Requirements: NFR-05, NFR-06

### US-15 Understand the app without training (Could)
**As a** newcomer (a manager, a BA or a reviewer) **I want** an overview of what the system does and how a payment flows **so that** I can follow the queue and MI without a walkthrough.
- Given the app, when I open it, then the first page explains the flow, the four outcomes and where to go next in plain English.

Requirements: NFR-09

### Won't have this time
Real-time scoring API; replaying analyst decisions; monthly backtesting; point-of-compromise analysis; SLA timers; user login (the analyst types their name); Tableau dashboards (parked).

## Requirements

### Functional

| ID | Requirement |
|---|---|
| FR-01 | Score every payment with a fraud probability, using only information available before the payment |
| FR-02 | Rank open alerts by expected loss (probability x amount) within each route |
| FR-03 | Give every alert its three strongest reasons, from SHAP, worded with the payment's own values |
| FR-04 | Word each reason so it states which way the payment is unusual, and handle missing history explicitly |
| FR-05 | Let an analyst confirm fraud or clear a payment, with an optional note, writing back to PostgreSQL |
| FR-06 | Close an alert only if it is still open, and append every decision to an audit log with the score, route and model version shown |
| FR-07 | Show all alerts on the same card alongside the selected alert |
| FR-08 | Route every payment to its cheapest expected action: approve, in-app step-up, analyst review, or decline and block |
| FR-09 | Respect analyst capacity: when more payments want an analyst than capacity allows, the lowest expected-loss ones take their next-cheapest action |
| FR-10 | Provide MI: alerts worked, hit rate, value saved, false positive rate, by day, route and score band, and the open queue |
| FR-11 | Compare rules, logistic regression and XGBoost on the test months at the same analyst workload: precision, recall, PR-AUC, cost |
| FR-12 | Hold the cost assumptions as named, editable parameters and run a sensitivity analysis with an annual business case |
| FR-13 | Monitor input drift, score drift, outcomes and the fairness watch item monthly with red, amber and green thresholds |
| FR-14 | Log every training run, its parameters and metrics in MLflow and register the chosen model |
| FR-15 | Audit genuine-customer interruptions and fraud detection by age band and gender, with confidence intervals and flags |

### Non-functional

| ID | Requirement |
|---|---|
| NFR-01 | PCI DSS: card numbers only in the raw table; every later layer uses a keyed HMAC-SHA256 token |
| NFR-02 | Data minimisation: personal fields are never features; age and gender are used only in a restricted table for the fairness audit |
| NFR-03 | No data leakage: split by time; features look only backwards; results that look too good are investigated |
| NFR-04 | Reproducibility: fixed random seed, every run logged, model versioned in a registry |
| NFR-05 | Portability: `docker compose up` starts PostgreSQL, MLflow and the app on a clean machine |
| NFR-06 | Quality: automated tests (unit and SQL) and lint run in CI on every push |
| NFR-07 | Secrets (database passwords, the token key) only in `.env`, which is never committed |
| NFR-08 | Explanations are exact for the model (SHAP values match the model's own) and truthful in wording |
| NFR-09 | Usability: someone new can follow the app without training; British English throughout |
