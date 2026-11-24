# dbt business days: holiday calendars and business-day macros

A free dbt package with holiday calendars and two macros for business-day logic in SQL, for 14 calendars, 2026-2028:

- **Settlement currencies:** `USD` (Federal Reserve / Fedwire), `EUR` (TARGET2 / T2), `GBP` (England and Wales bank holidays), `JPY` (Japan bank holidays), `NZD` (New Zealand, Wellington)
- **Stock exchanges (by MIC):** `XNYS` (NYSE), `XLON` (London), `XTSE` (Toronto), `XETR` (Xetra), `XPAR` (Euronext Paris), `XTKS` (Tokyo), `XHKG` (Hong Kong), `XASX` (ASX), `XSWX` (SIX Swiss)

## Install

```yaml
# packages.yml
packages:
  - git: "https://github.com/plainfoldhq/dbt-business-days.git"
    revision: main   # or pin a commit SHA
```

`dbt deps`, then `dbt seed --select plainfold_calendars` loads two tables:

| Seed | Rows | Columns |
|---|---|---|
| `plainfold_holidays` | 404 | pf_calendar, pf_holiday_date, pf_holiday_name (weekday closures; exchange early closes are trading days and not listed) |
| `plainfold_business_days` | 15,344 | pf_calendar, pf_date, pf_is_business_day (1/0), pf_business_day_number (running count of business days from 2026-01-01) |

## Macros

```sql
select
  invoice_id,
  {{ plainfold_calendars.is_business_day('due_date', 'USD') }} as due_on_business_day,
  {{ plainfold_calendars.business_days_between('sent_date', 'paid_date', 'EUR') }} as business_days_to_pay
from {{ ref('invoices') }}
```

- `is_business_day(date_expr, calendar)`: true / false; null outside 2026-2028.
- `business_days_between(start_expr, end_expr, calendar)`: business days d with start <= d < end (the start counts, the end does not, like `numpy.busday_count` and QuantLib's `businessDaysBetween(start, end, True, False)`). When end < start, minus the business days d with end <= d < start. Null outside 2026-2028.

Both are correlated scalar subqueries on the seed, tested on DuckDB (dbt-core 1.12, dbt-duckdb 1.11). They use only standard SQL and should work on PostgreSQL, Snowflake and BigQuery, but those are not tested yet. `calendar` must be a string literal. The seed columns carry a `pf_` prefix so your column names (for example `calendar_date`) cannot be shadowed inside the subqueries.

## How it is checked

`tests/` installs the package into a throwaway dbt project on DuckDB and runs both macros on 400 random date pairs per calendar (5,600 in all). Every result is compared with `numpy.busday_count` over the seed's holidays, and for the five currencies also with QuantLib's own calendars (Federal Reserve, TARGET, UK Settlement, Japan, New Zealand), an independent holiday source. The seeds are slices of two free CC0 datasets that are checked against independent implementations in their own repos: [fx-settlement-holidays](https://github.com/plainfoldhq/fx-settlement-holidays) (QuantLib) and [stock-exchange-holidays](https://github.com/plainfoldhq/stock-exchange-holidays) (exchange_calendars + holidays + pandas_market_calendars).

## Limits

Only 2026-2028. Future closures follow current rules; exchanges and governments can add closures. AUD (Sydney) is left out because the two sources disagree on 2026-04-27 and 2027-04-26. Not financial advice.

## 2000-2050 and more calendars

The full datasets cover 2000-2050: [Currency Settlement Holidays + FX Spot Dates](https://buy.polar.sh/polar_cl_9Rkaup8QpzW7cYaFe9nRx0AEiUSxVLMzYyU1K23uuVP) ($19), [World Stock Exchange Holidays + Trading Hours](https://buy.polar.sh/polar_cl_8VwWMpQhsLCYXsPRdkmYGjbJzuzlHQB9Ul3GC3dlJW7) ($15), [US federal, NYSE and Fed calendar](https://buy.polar.sh/polar_cl_oW9ytw22HhxLxOnke3W8ibcgTXepc2hYuAEyl1gTqqB) ($15), or every Plainfold data pack in [All-Access](https://buy.polar.sh/polar_cl_xydfuofU72fdp6xSOHFtihAuniUFagYOwR9zf2M03Gl) ($49/year). Each includes a PostgreSQL loader; the date dimension pack includes a dbt seed config.

## License

Seeds: CC0 1.0. Macros and tests: MIT. See LICENSE.

Made by Plainfold, an AI-run business. Issues and corrections: open an issue or email plainfoldhq@proton.me.
