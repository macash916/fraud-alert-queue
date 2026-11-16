# User acceptance test (UAT) script

**Purpose:** confirm the alert queue and MI do what the fraud team needs, in their terms, before go-live.

**How to run:** `docker compose up`, open http://localhost:8501, follow each scenario and record the actual result. Scenarios are written for a fraud analyst or team leader, not a developer.

**Status:**
- **Dry run by the build team: 16 Nov 2026.** All scenarios pass after one fix (UAT-10, below).
- **Business sign-off: pending.** The tester and sign-off columns are deliberately left for a business tester (Amrit, as the person with fraud-operations experience); the build team does not sign its own work.
- The dry-run decisions were removed afterwards, so the queue starts clean.
- The dry run used model version 1. Version 2 (same settings, fixed row order) replaced it later on 16 Nov, so scores and expected losses in the queue differ slightly from those recorded below; the business tester should record what they see.

| ID | Story | Scenario | Steps | Expected result | Dry run (build team) | Business tester | Pass / fail | Date |
|---|---|---|---|---|---|---|---|---|
| UAT-01 | US-15 | A newcomer understands the system | Open the app. Read the Overview without help. | Can say in their own words what the system does, the four outcomes and where to go next | Overview shows the problem, the four-step flow, the four outcomes with live counts, links and a glossary | | | |
| UAT-02 | US-01 | Riskiest alerts come first | Alert queue, route "Analyst review". Compare the top five with their expected loss. | Ordered by expected loss, highest first | Top five (d1e0ba14 $2,367, 8adcbe46 $1,775, a1cd9e67 $1,604, 699c0828 $1,449, 0e2e3e0f $1,209) match the database's own ordering exactly | | | |
| UAT-03 | US-02, US-04 | Understand why a payment was flagged | Open the top alert. Read step 3. | Three plain-English reasons with the payment's own values; the card's other alerts; a chart of what moved the score | "Large payment of $5,920.50", "Spend in the last 24 hours is 59x this customer's usual daily spend", "Amount is 75x a typical shopping (in store) payment"; 12 alerts on the card; 8-factor chart | | | |
| UAT-04 | US-03 | Confirm fraud on a chosen alert, with a note | Enter a name. Tick rank 3. Type a note. Click Confirm fraud. | That alert (not another) closes with the decision, note, name and time; the queue moves on | Card 699c0828, $6,025.40 recorded with the note, the 24% score shown and model version 1; it left the queue | | | |
| UAT-05 | US-06, US-03 | Reinstate a genuine customer after an automatic decline | Route "Decline and block". Read the route explanation. Click Not fraud on the top alert. | Explanation says the card was blocked automatically and can be reinstated; the alert closes as Not fraud | Card 4b7a7a55, $2,761.28 recorded as Not fraud | | | |
| UAT-06 | US-13 | Every decision leaves an audit trail | Open "Recently worked". | Who, when, card, amount, route, decision and note for each decision | All three dry-run decisions listed; the database log also holds the score and model version | | | |
| UAT-07 | US-07 | MI reflects the work done | Open Management information. | Alerts worked, hit rate, value saved and false positive rate match the decisions made | 3 worked, hit rate 67%, value saved $11,946 ($5,920.50 + $6,025.40), false positive rate 33% | | | |
| UAT-08 | US-03 | No anonymous decisions | Open the queue without entering a name. | Decision buttons disabled, with a prompt | Both buttons disabled; prompt shown | | | |
| UAT-09 | US-05 | Each route explains what has happened to the payment | Switch between the three routes. | A one-line explanation for each: held for an analyst, declined and blocked, or customer asked to confirm in the app | All three explanations shown | | | |
| UAT-10 | US-03, US-13 | Two analysts can't act on the same alert | Two browser tabs, two names, both viewing the top alert. Analyst A confirms it. Analyst B then clicks Not fraud on their (now out-of-date) screen. | B's click is refused with a message; no decision is recorded on any other alert | **First run: fail.** B's click was recorded against the next alert in the queue ($6,852.36), a payment B had never seen. **Fixed** (decisions are now bound to the alert on screen; selection is tracked by transaction ID). **Re-run: pass.** B was told "Not recorded: card d1e0ba14, $5,920.50 had already been worked by someone else", and only A's decision exists | | | |

## Defect found in UAT

| Defect | Severity | Cause | Fix | Retest |
|---|---|---|---|---|
| A decision could be recorded against a different alert from the one the analyst was looking at, if another analyst worked the queue in between | **High**: a likely fraud could be cleared under an analyst's name without them seeing it | Each click reloads the queue before acting, and the buttons acted on whichever alert was then at the top or in the ticked row position | Buttons carry the transaction ID of the alert drawn on screen; the ticked row is resolved by transaction ID from the table the analyst actually saw; a closed alert is refused | UAT-10 re-run: pass |

## Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Business tester (fraud operations) | | | |
| Product owner | | | |
