-- Routing rule agreed with the fraud lead: the stronger treatment wins.
-- Fails if any payment is routed differently from its rule flags.
select trans_num, rules_route, rule_a2_unusual_amount, rule_b2_night_high_value, rule_d1_new_merchant_high_value
from {{ ref('fct_rules_baseline') }}
where (rules_route = 'analyst_review' and not (rule_a2_unusual_amount or rule_b2_night_high_value))
   or (rules_route = 'step_up' and (rule_a2_unusual_amount or rule_b2_night_high_value or not rule_d1_new_merchant_high_value))
   or (rules_route = 'approve' and (rule_a2_unusual_amount or rule_b2_night_high_value or rule_d1_new_merchant_high_value))
