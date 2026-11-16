# Test fixture

`raw_transactions.csv` is **invented** for testing: 4 made-up cards, 12 payments, fake names, card
numbers starting 999 (not a real card range). It is not taken from the Kaggle dataset, which is never
committed.

`expected_features.csv` holds the value each SQL feature should produce, **worked out by hand** from
the feature definitions in `dbt/models/marts/fct_transaction_features.sql`. The payments were chosen
to sit on the edges where leakage and off-by-one bugs hide:

| Payment | Edge case it tests |
|---|---|
| fx-a1 and fx-b1 | Two cards pay in the same category at the same second: neither counts towards the other's category norm |
| fx-b2 and fx-b3 | One card, two payments at the same second: velocity windows leave both out of each other; history counts follow a fixed tie-break |
| fx-b2 | A payment exactly one hour after the previous one is inside the 1-hour window |
| fx-b4 | 23:59:59 after a payment is inside the 24-hour window; 24:59:59 is not |
| fx-a3 | Amount exactly 10x the card average fires rule A2 (the threshold is inclusive) |
| fx-a5 | Night, high value, new merchant and 10x average all at once: analyst review wins; 111.2 km from home |
| fx-c1 | Night, high value and new merchant: analyst review beats step-up |
| fx-d1 | New merchant, high value, daytime, first payment on the card: in-app step-up only |
| fx-a1, fx-b1, fx-c1, fx-d1 | A card's first payment: every history feature is empty, not zero |
| fx-c2, fx-d1 | Age on a birthday: 65 on the day (65+) and 25 on the day (25-34) |
| fx-b1 to fx-b4 | A 17-year-old card holder lands in the "Under 18" band |
| fx-a5 and fx-c1 | One fraud in each source file, so per-period reports never divide by zero |
