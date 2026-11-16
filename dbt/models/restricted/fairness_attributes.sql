{{ config(schema='restricted', materialized='table') }}

-- Restricted: protected characteristics for the fairness audit ONLY (FCA Consumer Duty, Equality Act).
-- Never joined into model features or the analyst app. Holds age band and gender per transaction,
-- not date of birth or names, so even this table carries the minimum needed.

select
    trans_num,
    case
        when age < 18 then 'Under 18'   -- simulator artefact (13 cards); kept visible, not hidden in 18-24
        when age < 25 then '18-24'
        when age < 35 then '25-34'
        when age < 45 then '35-44'
        when age < 55 then '45-54'
        when age < 65 then '55-64'
        else '65+'
    end as age_band,
    gender
from (
    select
        trans_num,
        gender,
        date_part('year', age(trans_ts::date, dob)) as age   -- age on the day of the payment
    from {{ source('raw', 'raw_transactions') }}
) aged
