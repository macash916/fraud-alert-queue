# User acceptance test (UAT) script

**Purpose:** confirm the alert queue and MI do what the fraud team needs, in their terms, before go-live.

**How to run:** `docker compose up`, open http://localhost:8501, follow each scenario and record the actual result. Scenarios are written for a fraud analyst or team leader, not a developer.

**Status:**
- **Dry run by the build team: 16 Nov 2026.** All scenarios pass after one fix (UAT-10, below).
- **Business UAT: all ten scenarios passed (17 to 18 Nov 2026), after fixes TC-71 to TC-74. Signed off 18 Nov 2026.** The tester and sign-off columns were left for a business tester (Amrit, as the person with fraud-operations experience), so the build team did not sign its own work.
- The dry-run decisions were removed afterwards, so the queue starts clean.
- The dry run used model version 1. Version 2 (same settings, fixed row order) replaced it later on 16 Nov, so scores and expected losses in the queue differ slightly from those recorded below; the business tester should record what they see.
- **Business UAT run order** (so each scenario leaves the queue ready for the next, and the audit trail and MI include every decision): UAT-01, 08, 09, 02, 03, 04, 05, 10, 06, 07.

**Values to expect with model version 2** (rechecked against the database on 18 Nov 2026 for the re-run of UAT-03, 05, 10, 06 and 07. By then five decisions were already in the queue from the business tester's earlier runs: d1e0ba14, 4b7a7a55, a1cd9e67 (UAT-04), 8adcbe46 (analyst A, UAT-10 first run) and 47a138af (analyst B, the click that exposed TC-73). Earlier versions of this table are superseded):

| Scenario | Expected |
|---|---|
| UAT-03 | Top alert 699c0828, $6,025.40 (expected loss $2,106.80, 35.0%): "Spend in the last 24 hours is 42x this customer's usual daily spend"; "Made at 22:16, a time of day linked to fraud"; "Large payment of $6,025.40"; 10 alerts on the card |
| UAT-05 | Top decline is 3dcbed45, $1,320.92 at Daugherty, Pouros and Beahan (score 100.0%); Not fraud |
| UAT-10 | Both tabs on 699c0828, $6,025.40. A confirms; B's Not fraud is refused with a warning beside the buttons that stays until dismissed (TC-73) |
| UAT-06 | Seven decisions, newest first: 699c0828 (A), 3dcbed45 not fraud, then 47a138af (B), 8adcbe46 (A), a1cd9e67, 4b7a7a55, d1e0ba14; nothing new for B |
| UAT-07 | 7 worked, hit rate 86%, value saved $27,836, false positive rate 14%; clearing the Analysts filter shows a message, not an error |

| ID | Story | Scenario | Steps | Expected result | Dry run (build team) | Business tester | Pass / fail | Date |
|---|---|---|---|---|---|---|---|---|
| UAT-01 | US-15 | A newcomer understands the system | Open the app. Read the Overview without help. | Can say in their own words what the system does, the four outcomes and where to go next | Overview shows the problem, the four-step flow, the four outcomes with live counts, links and a glossary | Amrit Sharma | Pass | 17 Nov 2026 |
| UAT-02 | US-01 | Riskiest alerts come first | Alert queue, route "Analyst review". Compare the top five with their expected loss. | Ordered by expected loss, highest first | Top five (d1e0ba14 $2,367, 8adcbe46 $1,775, a1cd9e67 $1,604, 699c0828 $1,449, 0e2e3e0f $1,209) match the database's own ordering exactly | Amrit Sharma | Pass | 17 Nov 2026 |
| UAT-03 | US-02, US-04 | Understand why a payment was flagged | Open the top alert. Read step 3. | Three plain-English reasons with the payment's own values; the card's other alerts; a chart of what moved the score | "Large payment of $5,920.50", "Spend in the last 24 hours is 59x this customer's usual daily spend", "Amount is 75x a typical shopping (in store) payment"; 12 alerts on the card; 8-factor chart | Amrit Sharma | Pass on re-run. First run failed: the script still listed values for two alerts the tester had already closed (script error, corrected) | 18 Nov 2026 |
| UAT-04 | US-03 | Confirm fraud on a chosen alert, with a note | Enter a name. Tick rank 3. Type a note. Click Confirm fraud. | That alert (not another) closes with the decision, note, name and time; the queue moves on | Card 699c0828, $6,025.40 recorded with the note, the 24% score shown and model version 1; it left the queue | Amrit Sharma | Pass (a1cd9e67, $4,622.47, with note) | 17 Nov 2026 |
| UAT-05 | US-06, US-03 | Reinstate a genuine customer after an automatic decline | Route "Decline and block". Read the route explanation. Click Not fraud on the top alert. | Explanation says the card was blocked automatically and can be reinstated; the alert closes as Not fraud | Card 4b7a7a55, $2,761.28 recorded as Not fraud | Amrit Sharma | Pass on re-run (3dcbed45, $1,320.92, Not fraud). First run failed for the same script error as UAT-03 | 18 Nov 2026 |
| UAT-06 | US-13 | Every decision leaves an audit trail | Open "Recently worked". | Who, when, card, amount, route, decision and note for each decision | All three dry-run decisions listed; the database log also holds the score and model version | Amrit Sharma | Pass (7 decisions; nothing recorded for analyst B after the fix) | 18 Nov 2026 |
| UAT-07 | US-07 | MI reflects the work done | Open Management information. | Alerts worked, hit rate, value saved and false positive rate match the decisions made | 3 worked, hit rate 67%, value saved $11,946 ($5,920.50 + $6,025.40), false positive rate 33% | Amrit Sharma | Pass (7 worked, hit rate 86%, value saved $27,836, false positive rate 14%; empty filter shows a message) | 18 Nov 2026 |
| UAT-08 | US-03 | No anonymous decisions | Open the queue without entering a name. Click Not fraud. | Nothing is recorded; a warning beside the buttons asks for a name and stays until dismissed; the same alert is still shown | Both buttons disabled; prompt shown (behaviour before TC-74) | Amrit Sharma | Pass (17 Nov against the old disabled buttons; re-tested after fix TC-74: warning shown, nothing recorded) | 18 Nov 2026 |
| UAT-09 | US-05 | Each route explains what has happened to the payment | Switch between the three routes. | A one-line explanation for each: held for an analyst, declined and blocked, or customer asked to confirm in the app | All three explanations shown | Amrit Sharma | Pass | 17 Nov 2026 |
| UAT-10 | US-03, US-13 | Two analysts can't act on the same alert | Two browser tabs, two names, both viewing the top alert. Analyst A confirms it. Analyst B then clicks Not fraud on their (now out-of-date) screen. | B's click is refused with a message; no decision is recorded on any other alert | **First run: fail.** B's click was recorded against the next alert in the queue ($6,852.36), a payment B had never seen. **Fixed** (decisions are now bound to the alert on screen; selection is tracked by transaction ID). **Re-run: pass.** B was told "Not recorded: card d1e0ba14, $5,920.50 had already been worked by someone else", and only A's decision exists | Amrit Sharma | Pass on re-run after fix TC-73. Earlier runs: the refusal was a fading toast and B then recorded a decision on 47a138af (defect TC-73); one run where the name was not applied (TC-74); one where tab B lost its connection (browser, not app) | 18 Nov 2026 |

## Defect found in UAT

| Defect | Severity | Cause | Fix | Retest |
|---|---|---|---|---|
| A decision could be recorded against a different alert from the one the analyst was looking at, if another analyst worked the queue in between | **High**: a likely fraud could be cleared under an analyst's name without them seeing it | Each click reloads the queue before acting, and the buttons acted on whichever alert was then at the top or in the ticked row position | Buttons carry the transaction ID of the alert drawn on screen; the ticked row is resolved by transaction ID from the table the analyst actually saw; a closed alert is refused | UAT-10 re-run: pass |
| Business UAT: entering a name seemed to do nothing (TC-71) | **Low**: the name was saved, but an analyst could think they were locked out | The decision buttons it unlocks sit further down the queue page, out of sight | The sidebar confirms "Working as [name]", or prompts for a name when empty | Confirmed by business tester (UAT-04, UAT-08 pass, 17 Nov 2026) |
| Business UAT: the MI page crashed when every analyst was removed from the filter (TC-72) | **Medium**: a team leader loses the MI page until they reload | The page assumed at least one analyst was selected | A message asks for at least one analyst; "What is waiting" still shows | Confirmed by business tester (UAT-07 pass, 18 Nov 2026) |
| Business UAT: a refused decision was easy to miss (TC-73) | **Medium**: the analyst thinks their click did nothing and may act on an alert they did not mean to; in UAT, B's next click recorded confirmed fraud on 47a138af, $1,653.99 | The refusal was a toast that faded in a few seconds, shown away from the buttons, while the case above silently moved to the next alert | A warning next to the decision buttons stays until dismissed and says the case has moved on | Confirmed by business tester (UAT-10 pass, 18 Nov 2026) |
| Business UAT: a click on a greyed-out decision button was silently lost (TC-74) | **Low**: no wrong decision possible, but the analyst thinks the app is broken and clicks again | Buttons were disabled until a name was applied; a name typed without Enter was only applied by the next click, which was then thrown away | Buttons always clickable; without a name nothing is recorded and a warning beside the buttons asks for one | Confirmed by business tester (UAT-08 re-test pass, 18 Nov 2026) |

## Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Business tester (fraud operations) | Amrit Sharma | Approved | 18 Nov 2026 |
| Product owner | Amrit Sharma | Approved | 18 Nov 2026 |

Portfolio project: the same person acted as business tester and product owner. In a bank these would be separate people, so that the person accepting the system is not the person who specified it.
