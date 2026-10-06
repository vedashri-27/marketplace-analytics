# dbt layer

Turns the raw CSV extracts into clean, tested tables. It runs locally on
dbt-duckdb (reading the CSVs directly, no load step) and is written so the same
models would run on Snowflake with just a profile change.

## Layout

```
models/
  staging/   one view per source, typed and renamed, no logic
             stg_bookings, stg_sessions, stg_experiences, stg_suppliers,
             stg_cities, stg_customers, stg_marketing_spend, stg_daily_pricing
  marts/     the tables people actually query
    core/      dim_experience, fct_bookings, fct_sessions
    marketing/ mart_channel_performance   (CAC / ROAS / recommendation)
    product/   mart_conversion_funnel, mart_experiment_checkout_v2
    supply/    mart_supplier_economics    (Pareto / concentration)
```

sources -> staging -> marts is the usual split: staging soaks up source changes,
marts hold the business logic.

## Run it

```bash
cd dbt
export DATA_DIR=$(cd ../data && pwd)   # points sources at the CSVs
dbt build --profiles-dir .
```

That builds 8 views + 7 tables and runs 37 data tests (unique, not_null,
accepted_values, relationships). Last time I ran it: PASS=52, 0 failures.

The tests are the point as much as the models: PK uniqueness, referential
integrity (fct_bookings.experience_id has to exist in dim_experience), and enum
checks on status / experiment_group. There's one small macro,
`macros/safe_divide.sql`, for null-safe rates.
