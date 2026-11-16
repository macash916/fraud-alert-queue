# Stakeholders

Generic roles at a UK card issuer. No real people or organisations are named.

## Register

| Stakeholder | What they need from this change | Main concern | How they are engaged |
|---|---|---|---|
| Fraud analysts | A shorter, better-ordered queue; reasons they can act on and repeat to a customer | Being asked to trust a score they can't question | User stories, UAT, reasons shown on every alert |
| Fraud operations team leader | Staffing that matches demand; MI on hit rate and throughput | December peaks; quality of decisions | MI page, capacity curve, monitoring runbook |
| Head of fraud strategy (sponsor) | Lower fraud losses without more headcount | Business case holding up under scrutiny | Business case, sensitivity analysis |
| Fraud analytics (model owner) | A model that stays accurate and is documented | Drift, retraining, explaining the model | Model card, monitoring, decision log |
| Model risk management (second line) | Evidence for independent validation under SS1/23 | Leakage, over-fitting, undocumented choices | Model card, test cases, leakage checks, decision log |
| Compliance and Consumer Duty lead | Fair outcomes; interruptions justified | Groups treated worse; unexplained declines | Fairness audit, interruption measures, reasons |
| Data protection officer | Lawful, minimal use of personal data | Protected characteristics used as features; automated decisions | Tokenisation, restricted fairness schema, Article 22 review route |
| Information security (PCI) | Card numbers protected | Card numbers spreading beyond the system of record | Tokenisation in staging, dbt tests, secrets in `.env` |
| Customer complaints | Fewer complaints about blocked payments; explanations to give | Genuine customers declined or blocked | Reasons per alert, reinstatement through analyst review |
| Internal audit (third line) | A trail from each decision back to the data and model | Decisions that can't be reconstructed | Decision log table, model version on every alert |
| IT and data platform | Something they can run and support | Unsupported tools, manual steps | Docker Compose, CI, dbt |
| Customers | Payments that work; fraud stopped; a quick fix if wrongly blocked | Being interrupted or blocked for no clear reason | In-app step-up instead of a phone call; Consumer Duty measures |
| FCA and PRA (external) | Fair outcomes; sound model risk management | Consumer harm; unmanaged model risk | Evidence pack: model card, fairness audit, monitoring |

## RACI for the main activities

R = responsible, A = accountable, C = consulted, I = informed.

| Activity | Analysts | Ops team leader | Head of fraud strategy | Model owner | Model risk | Compliance | DPO | Internal audit |
|---|---|---|---|---|---|---|---|---|
| Define requirements and cost assumptions | C | C | A | R | I | C | I | I |
| Build and document the model | I | I | I | A, R | C | C | C | I |
| Independent validation | I | I | I | C | A, R | C | I | I |
| Fairness audit | I | I | I | R | C | A | C | I |
| Approve go-live | I | C | A | R | C | C | C | I |
| Work alerts and record decisions | R | A | I | I | I | I | I | I |
| Monthly monitoring and MI | I | R | I | A, R | C | C | I | I |
| Retrain or roll back | I | C | A | R | C | C | I | I |
| Periodic review of the control | I | I | I | C | C | C | I | A, R |

## Power and interest

| | Lower interest | Higher interest |
|---|---|---|
| **Higher power** | Keep satisfied: internal audit, IT and data platform, FCA and PRA | Manage closely: head of fraud strategy, model risk management, compliance, DPO |
| **Lower power** | Monitor: customer complaints | Keep informed: fraud analysts, ops team leader, model owner, customers |

The analysts sit in "keep informed" on formal power, but their trust decides whether the queue gets used as designed. They are involved through UAT and the reasons shown on every alert.
