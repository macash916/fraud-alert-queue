---
name: section-report
description: Close a finished section of the fraud-alert-queue build with Amrit's standard report (summary, business reason, method, evidence, findings, decisions, risks, interview lines, commit status). Use when Amrit types /section-report, or when a section of work is complete and needs reporting before anything is committed.
---

# Section report

Amrit reads every report to understand the work, defend it in BA/DA interviews and decide what happens next. Write it so it can be read once, in a few minutes, and acted on. Follow the house style in CLAUDE.md: British English, plain English, real numbers only, no marketing words. Use the humaniser skill's rules for the prose.

## Before writing
1. Re-run what proves the section works (tests, the script, the query, the app check). Never report a number you did not see in this session's output. If something could not be checked, say so in the report.
2. Run `git status --short` and `git log --oneline -3` so the commit status is accurate.
3. Re-read the decision log rows written during the section.

## The report (in this order, these headings)

**1. Summary.** Two or three sentences: what is now true that wasn't before. No preamble.

**2. Business reason.** Why this section matters to a fraud team, a customer, an auditor or the regulator. One short paragraph.

**3. What was built, and how.** A table: component | what it does in plain English | why this way (the alternative not taken). File links as markdown links.

**4. Evidence.** The numbers and checks, with how they were produced (command or file). Tests passed / failed, metrics, before-and-after. Include anything that failed and was fixed.

**5. Findings.** What the work revealed, especially surprises, bugs caught and assumptions that turned out wrong. Honest beats impressive.

**6. Decisions.** Two lists:
- *Made* (already logged as V-decisions): one line each with the V number.
- *Needed from Amrit*: each as a question with my recommendation first and the realistic alternative. Only real decisions; small instructions need no log row.

**7. Risks and limitations.** A short table: risk | level | mitigation or status. Say plainly where the result rests on simulated data or placeholders.

**8. Interview lines.** Three or four sentences in Amrit's voice, first person, that a hiring manager at a London bank would find specific and credible. Each must be backed by evidence in section 4.

**9. Commit status and next step.** What is committed, what is not, what is pushed (Amrit does every push). End by asking whether to commit. Never commit or push without Amrit's go-ahead, and never add co-author lines in this repo.

Keep it under about 800 words unless the section is unusually large. No closing summary after section 9.
