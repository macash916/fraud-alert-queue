# Business case: model-led alert queue against the current rules

**Status:** draft for review. All figures come from `src/decisioning.py` on the test months (21 Jun to 31 Dec 2020, 194 days, 555,719 payments, 2,145 frauds) and the assumptions in `config/decision_params.yaml`.

**Read this first:** the data is simulated (Sparkov) and covers 999 cards. The fraud rate (about 0.4% of payments) is several times higher than a real UK card book, and the simulator makes fraud unusually easy to separate (see `test_cases.md`, TC-19 to TC-22). The dollar figures show **how the decision is made and which assumptions matter**, not what a bank would save. Money is in US dollars because the dataset is US-simulated.

## The decision

Should the fraud team replace its rules with the model-led queue, and if so, with which routing policy?

## Options compared (test months; confirm then block applied to every option)

| | No controls | Rules (today) | Model, like-for-like | **Model, four routes** |
|---|---|---|---|---|
| Fraud $ stopped by the route itself | 0% | 82.1% | 99.9% | 99.8% |
| Fraud $ protected, including card blocks | 0% | 93.2% | 99.9% | 99.9% |
| Fraud losses | $1,133,325 | $77,535 | $715 | $960 |
| Analyst alerts worked per day | 0 | 17.6 | 9.6 | **3.2** |
| Analyst hit rate | n/a | 10% | 16% | 10% |
| Customer step-ups per day (genuine) | 0 | 1.7 (1.7) | 2.0 (1.9) | 14.0 (13.8) |
| Genuine cards declined per day | 0 | 0 | 0 | 0.1 |
| **Total cost over the test months** | $1,133,325 | $86,804 | $5,889 | **$4,393** |
| **Total cost, annualised** | $2.13m | $163k | $11k | **$8k** |

Total cost = fraud losses + analyst time + step-up cost + false-decline cost.

"Like-for-like" keeps the rules' three routes and daily budgets but ranks payments by expected loss. "Four routes" gives each payment its cheapest expected action (approve, in-app step-up, analyst review, or decline and block), with analyst reviews capped at capacity.

## What the numbers say

1. **The model's gain over the rules is about $155k a year on this book** (annualised from 194 days), roughly **$155 per card per year**. The rules already protect 93% of fraud value once confirm then block is counted; the model closes most of the remaining 7%.
2. **Most of the gain comes from better ranking, not from the extra routes.** Like-for-like already cuts cost from $86.8k to $5.9k. Four routes saves a further $1.5k, mainly by needing a third as many analyst reviews.
3. **The four-route policy trades analyst time for customer friction:** 3 analyst reviews a day instead of 10, but about 14 genuine customers a day asked to confirm a payment in their app (0.5% of the day's payments), against 2.
4. **Analyst capacity stops being the constraint.** The model protects about 98% of fraud value with roughly 2 analyst alerts a day (`figures/capacity_curve.png`). The rules need about 18 a day to reach 93%.

## How much the answer depends on the assumptions

`figures/sensitivity_tornado.png` moves each assumption down and up. Base saving: **$155k a year**.

| Assumption (low / high) | Saving at low | Saving at high |
|---|---|---|
| Loss rate on missed fraud (50% / 100%) | $85k | $155k |
| Block delay (15 min / 4 hours) | $141k | $206k |
| Minutes per review (2.5 / 7.5) | $148k | $163k |
| Analyst hourly cost ($16 / $48) | $148k | $163k |
| Fraudster pass rate on step-up (5% / 20%) | $156k | $157k |
| Step-up cost ($0.25 / $0.75) | $156k | $155k |
| False-decline cost ($10 / $30) | $155k | $155k |
| Genuine confirm rate (90% / 99%) | $155k | $155k |
| Analyst capacity (10 / 32 a day) | $155k | $155k |

- **The case is positive under every assumption tested.** The lowest value is $85k, when the bank recovers half of each missed fraud.
- **The two assumptions that matter are how much of a missed fraud the bank actually loses, and how fast a confirmed fraud blocks the card.** A slower block helps the model's case, because the rules rely more on blocks to catch follow-on fraud.
- The step-up assumptions barely move the answer in this data, because the model is rarely unsure. On a real book, with a less separable model, they would matter more, and they are the first thing to measure in a pilot.

## Calibration

`figures/calibration.png`: predicted probabilities track actual fraud rates on both the validation and test months, which is what expected-loss ranking relies on. In the middle bands the model is slightly cautious (payments scored around 0.6 turn out to be fraud about 69% of the time), so it understates rather than overstates risk there.

## Recommendation

Move from rules to the model-led queue, starting with the **like-for-like** policy: the same routes and budgets the team knows, with better ranking, which delivers most of the gain. Pilot the **four-route** policy (decline and block for near-certain fraud, in-app step-up for the uncertain middle) once step-up confirm and pass rates have been measured on real customers, and track the genuine step-up rate as a Consumer Duty indicator.

## Caveats

- Simulated data with an unrealistically high and separable fraud rate: treat the dollar figures as illustrative.
- Annualising a June to December window assumes the second half of the year is typical; it includes December, the busiest month.
- An analyst review is assumed to hold the payment until it is worked (fraud stopped, genuine released). Payments after a card block on genuine customers are assumed to move to a replacement card at no extra cost.
- Step-up outcomes use a fixed random seed so that every policy faces the same customer responses.
