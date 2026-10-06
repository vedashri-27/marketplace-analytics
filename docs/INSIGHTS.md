# What the data says

Notes on what I found in the generated marketplace. Every number comes from a
query in `sql/` or from `python/03_analysis.py`, and most of it is on the
dashboard. The data is synthetic, so treat this as a demonstration of the
analysis, not real market facts.

## Overall

GMV grows from about $94k/month at the start to a summer-2026 peak, ~$5.2M over
the 18 months, with ~$1.2M in commission. Take rate sits around 23% and doesn't
drift. Demand is seasonal (summer peak, December bump), so week-on-week and
month-on-month numbers have to be read against that, not on their own.

I rolled the main drivers into a single **Marketplace Health Index** (0–100) to
have one number to track. It currently lands at **67**. Growth and supply spread
score well; the thing dragging it down is marketing efficiency (blended ROAS of
1.18x), which lines up with the Display problem below. The weights are my own
call — see `DECISIONS.md`.

## Growth & marketing

| Channel | ROAS (net rev) | CAC | Call |
|---|--:|--:|---|
| Affiliates | 2.00x | $32 | Scale |
| Paid Social | 1.79x | $37 | Scale |
| Paid Search | 1.10x | $60 | Optimise |
| Display | 0.58x | $94 | Cut / fix |

Display spends more than the net revenue it brings in (it's losing ~$17k). The
obvious move is to pull most of that budget and push it into Affiliates and Paid
Social. The "Shift paid budget" slider on the Scenario Simulator tab lets you
play with exactly that.

Affiliates is the best channel on two counts: cheapest to acquire *and* the best
90-day value per customer, so it's not just cheap traffic.

Retention is low but normal for travel (people don't book trips often):
roughly 5–7% of a cohort books again in month one, decaying after that. One nice
detail — newer signup cohorts retain a bit better than older ones, which hints
onboarding has improved over time.

## Product

The largest single leak in the funnel is **view → add-to-cart** (only ~36% of
people who view an experience add it). But the more actionable finding is by
device: **mobile converts at checkout about 25% worse than desktop** (roughly
30% vs 40% checkout-to-book), and mobile is ~62% of traffic. That gap on that
much volume is worth more than any top-of-funnel tweak. The "Fix mobile
checkout" slider sizes it: closing half the gap is on the order of ~1,800 extra
bookings across the period.

The **checkout_v2 A/B test** backs up spending on this. Treatment beat control
7.07% vs 6.06% — a +16.6% relative lift, p < 1e-10, 95% CI roughly +0.75 to
+1.26pp. Big enough sample that the interval is tight. I'd ship it and fold the
learnings into the mobile work.

## Supply & operations

Supplier concentration is the thing I'd watch: ~60 of 134 active suppliers make
up 80% of GMV, and the top 25 alone are about half. Losing a few head suppliers
would hurt, so they're worth a retention / SLA focus.

On operations, most cities cancel at 8–9%; Amsterdam and Bangkok run hotter
(~10–11%) and are worth a supply-quality look. Ratings are uniformly good.

Geographically, Europe + North America tier-1/2 cities are ~69% of GMV. APAC and
LATAM are under-penetrated relative to how many experiences are listed there,
which is where I'd look for expansion.

## Pricing

Dynamic pricing adds ~$161k of GMV over flat base prices (+3.3%), strongest on
day trips. The last-minute premium holds up: 0–2 day lead time carries a ~1.14x
multiplier vs ~1.02x at 8–30 days. And there's headroom — even in the top demand
band, slot utilisation is only ~45%, so on high-demand dates the lever is more
demand (marketing) than price.

## If I were prioritising

1. Rebuild mobile checkout (biggest conversion upside, and checkout_v2 says the
   direction works).
2. Reallocate paid budget away from Display this week.
3. Put a retention programme around the head suppliers.
4. Look at APAC/LATAM, where supply is ahead of demand.
