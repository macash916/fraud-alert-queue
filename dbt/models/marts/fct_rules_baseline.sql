-- Rules baseline: what an experienced fraud analyst would set up in a rules engine today.
-- Every model is later judged against this, at the same analyst and step-up volumes.
--
-- Rules (thresholds are dbt vars in dbt_project.yml):
--   A2 unusual amount        amount >= 10x the card's own earlier average     -> analyst review
--   B2 night, high value     22:00-04:00 and amount >= $500                   -> analyst review
--   D1 new merchant, high    first use of this merchant and amount >= $500    -> in-app step-up
--
-- Routing: the stronger treatment wins. Any analyst rule sends the payment to an analyst;
-- step-up is used only when D1 is the sole rule that fired.

with features as (

    select * from {{ ref('fct_transaction_features') }}

),

flags as (

    select
        trans_num,
        trans_ts,
        card_token,
        source_file,
        amt,
        is_fraud,

        -- amt_vs_avg is null on a card's first transaction: no history, so A2 can't fire
        coalesce(amt_vs_avg >= {{ var('rule_amount_multiple') }}, false)          as rule_a2_unusual_amount,

        (hour_of_day >= {{ var('rule_night_start_hour') }}
            or hour_of_day < {{ var('rule_night_end_hour') }})
        and amt >= {{ var('rule_high_value_usd') }}                                as rule_b2_night_high_value,

        (is_new_merchant = 1 and amt >= {{ var('rule_high_value_usd') }})          as rule_d1_new_merchant_high_value

    from features

)

select
    *,
    case
        when rule_a2_unusual_amount or rule_b2_night_high_value then 'analyst_review'
        when rule_d1_new_merchant_high_value                    then 'step_up'
        else 'approve'
    end as rules_route,

    -- Plain-English list of the rules that fired, for the analyst and the audit trail
    concat_ws(', ',
        case when rule_a2_unusual_amount          then 'A2 unusual amount' end,
        case when rule_b2_night_high_value        then 'B2 night, high value' end,
        case when rule_d1_new_merchant_high_value then 'D1 new merchant, high value' end
    ) as rules_fired

from flags
