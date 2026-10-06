# Decisions & notes

A running note of the choices I made and why, plus stuff I'm not fully happy
with. Mostly for my own memory.

## Why synthetic data
I wanted a marketplace with a funnel, supply side, multiple currencies and an
experiment, and I couldn't find one open that had all of it together. So I
generated it (`python/01_generate_data.py`). It's seeded so runs are repeatable.
Downside: the relationships are ones I put in, so "findings" are really
"did my analysis recover what I planted". That's fine for showing method, but
I'm not pretending it's a market study.

## Data model
Star schema — fact_bookings and fact_sessions as the two fact grains, with
dim_city / dim_experience / dim_supplier / dim_customer around them. Bookings are
derived from converted sessions so the funnel actually ties out to bookings
(early version had them independent and the funnel numbers didn't reconcile,
which bugged me).

## SQLite + dbt-duckdb
Shipped a SQLite db so the SQL just runs with no setup. For the dbt layer I used
duckdb reading the CSVs, so `dbt build` works locally without a cloud warehouse.
Wrote the SQL to be mostly portable; the one thing that isn't is date bucketing
(`strftime` vs `date_trunc`), which I noted inline.

## Attribution = last-touch
Simplest thing that's still useful, and it's what a lot of dashboards actually
use. It over-credits bottom-funnel channels (Direct, Email) and under-credits
awareness ones. Multi-touch is the honest upgrade; didn't want to fake a
touch-path model I couldn't defend, so I left it last-touch and flagged it.

## The health index
This is the most "made up" part. I wanted one number, so I blended five drivers,
each mapped to 0–1 against a band I picked, then weighted:

| Driver | Weight | Band (0 → 100) |
|---|--:|---|
| Growth (last 3mo GMV vs prior 3mo) | 30% | 0.90x → 1.40x |
| Conversion % | 20% | 3% → 7% |
| Repeat rate | 15% | 10% → 35% |
| Blended paid ROAS | 20% | 0.8 → 2.0 |
| Supply spread (1 − top-10 GMV share) | 15% | 0.45 → 0.85 |

The weights are a judgement call. I leaned growth and marketing heaviest because
for an early marketplace that's what I'd obsess over. I'd want a team to argue
about these before anyone put it on a wall — a single score can hide a bad
component (here, marketing ROAS is weak but growth masks it). Code is in
`03_analysis.py` if the bands need changing.

## A/B significance by hand
Used a two-proportion z-test and computed the p-value with `math.erf` so there's
no SciPy dependency. The z is large enough that the p-value underflows to 0 in
float, so I display it as "<1e-10" rather than a fake 0.

## Weekly report: z-scores not thresholds
First version flagged "down >8% WoW", which fired constantly because of
seasonality. Switched to scoring each metric against the trailing 8 weeks and
only flagging |z| ≥ 2. Much quieter, and it won't cry wolf on a normal seasonal
dip.

## TODO / not done
- Multi-touch attribution.
- A real price-elasticity model instead of the rule-based multipliers in the
  generator.
- The dashboard charts need internet (Chart.js from a CDN). Everything else
  works offline; I let the charts degrade to a message rather than break the page.
- Haven't written unit tests for the generator — the dbt tests cover the output
  shape, but the generator itself is untested.
