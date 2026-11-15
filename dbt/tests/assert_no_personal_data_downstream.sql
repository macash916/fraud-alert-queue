-- PCI DSS / GDPR control: no card number or personal field may exist in any dbt model.
-- Returns a row for every offending column; dbt fails the test if any row comes back.
select table_name, column_name
from information_schema.columns
where table_schema = '{{ target.schema }}'
  and column_name in (
      'cc_num', 'first_name', 'last_name', 'street', 'city', 'zip',
      'dob', 'gender', 'job', 'cust_lat', 'cust_long'
  )
