{#- Plainfold calendar macros. Both read the plainfold_business_days seed (2026-01-01 to 2028-12-31).
    calendar: 'USD' (Federal Reserve), 'EUR' (TARGET2/T2), 'GBP' (England and Wales), 'JPY', 'NZD' (Wellington),
    or an exchange MIC: 'XNYS', 'XLON', 'XTSE', 'XETR', 'XPAR', 'XTKS', 'XHKG', 'XASX', 'XSWX'.
    Dates outside 2026-2028 return null. calendar must be a string literal. Seed columns are prefixed pf_ so they do
    not shadow the caller's columns inside the subqueries. -#}

{% macro is_business_day(date_expr, calendar) -%}
  (select bd.pf_is_business_day = 1 from {{ ref('plainfold_business_days') }} bd
   where bd.pf_calendar = '{{ calendar }}' and bd.pf_date = cast({{ date_expr }} as date))
{%- endmacro %}

{#- Business days d with start <= d < end. When end < start: minus the business days d with end <= d < start. -#}
{% macro business_days_between(start_expr, end_expr, calendar) -%}
  ((select bd.pf_business_day_number - bd.pf_is_business_day from {{ ref('plainfold_business_days') }} bd
    where bd.pf_calendar = '{{ calendar }}' and bd.pf_date = cast({{ end_expr }} as date))
   - (select bd.pf_business_day_number - bd.pf_is_business_day from {{ ref('plainfold_business_days') }} bd
    where bd.pf_calendar = '{{ calendar }}' and bd.pf_date = cast({{ start_expr }} as date)))
{%- endmacro %}
