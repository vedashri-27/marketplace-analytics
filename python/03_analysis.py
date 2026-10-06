"""
Build the charts and the dashboard_data.json that the dashboard reads.

Also does the bits that are easier in Python than SQL: the two-proportion
z-test for the checkout_v2 experiment, and a composite "health index" I made up
to get a single number for how the marketplace is doing (weights are in
docs/DECISIONS.md -- they're a judgement call, not gospel).

    python python/03_analysis.py
-> charts/*.png and dashboard/dashboard_data.json
"""
from __future__ import annotations
import json
import math
import os
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from _sqlutil import run_all, DB_PATH, ROOT

CHARTS = os.path.join(ROOT, "charts")
DASH = os.path.join(ROOT, "dashboard")
os.makedirs(CHARTS, exist_ok=True)
os.makedirs(DASH, exist_ok=True)

# ---- palette / style -----------------------------------------------------
INK = "#1E293B"; MUTED = "#64748B"; GRID = "#E2E8F0"
PRIMARY = "#4F46E5"; TEAL = "#0EA5A4"; AMBER = "#F59E0B"; RED = "#EF4444"; GREEN = "#16A34A"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "font.size": 11,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})


def _despine(ax, left=True):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    if not left:
        ax.spines["left"].set_visible(False)


def _save(fig, name):
    path = os.path.join(CHARTS, name)
    fig.savefig(path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [chart] {name}")


def recs(df):
    return json.loads(df.to_json(orient="records"))


# ---- experiment statistics ------------------------------------------------
def norm_cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def two_proportion_ztest(x1, n1, x2, n2):
    """control=(x1,n1), treatment=(x2,n2). Returns dict with lift, z, p, 95% CI."""
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se_pool
    p_value = 2 * (1 - norm_cdf(abs(z)))
    se_diff = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    diff = p2 - p1
    ci = (diff - 1.96 * se_diff, diff + 1.96 * se_diff)
    return dict(control_rate=p1, treatment_rate=p2, abs_lift_pp=diff * 100,
                rel_lift_pct=diff / p1 * 100, z=z, p_value=p_value,
                ci_low_pp=ci[0] * 100, ci_high_pp=ci[1] * 100,
                significant=bool(p_value < 0.05))


# --------------------------------------------------------------------------
def main():
    con = sqlite3.connect(DB_PATH)
    res = run_all(con)

    monthly = res["01_marketplace_health::Q1"]
    region = res["01_marketplace_health::Q2"]
    channels = res["02_growth_marketing::Q1"]
    ltv = res["02_growth_marketing::Q2"]
    cohort = res["02_growth_marketing::Q3"]
    funnel = res["03_product_funnel_experiment::Q1"]
    device = res["03_product_funnel_experiment::Q2"]
    experiment = res["03_product_funnel_experiment::Q3"]
    suppliers = res["04_supply_economics::Q1"]
    cities = res["04_supply_economics::Q2"]
    pricing_cat = res["05_pricing::Q1"]
    leadtime = res["05_pricing::Q2"]
    demand = res["05_pricing::Q3"]

    # extra headline metrics not covered by a single .sql query
    q = lambda s: pd.read_sql(s, con)
    repeat = q("""
        SELECT ROUND(100.0*SUM(CASE WHEN n>1 THEN 1 ELSE 0 END)/COUNT(*),1) repeat_rate_pct
        FROM (SELECT customer_id, COUNT(*) n FROM fact_bookings
              WHERE status<>'cancelled' AND customer_id>0 GROUP BY customer_id)""").iloc[0, 0]
    overall_conv = q("SELECT ROUND(100.0*AVG(converted),2) c FROM fact_sessions").iloc[0, 0]
    tot = q("""SELECT SUM(gbv_usd) gmv, SUM(net_revenue_usd) net, COUNT(*) bk,
               ROUND(AVG(gbv_usd),1) aov, ROUND(100.0*SUM(net_revenue_usd)/SUM(gbv_usd),1) take
               FROM fact_bookings WHERE status<>'cancelled'""").iloc[0]
    paid = channels[channels["spend_usd"] > 0]
    blended_roas = round(paid["net_revenue_usd"].sum() / paid["spend_usd"].sum(), 2)
    paid_spend = float(paid["spend_usd"].sum())

    # device-level checkout counts — the scenario simulator needs absolute numbers
    device_checkout = q("""
        SELECT device,
               SUM(stage_checkout) AS checkout_started,
               SUM(converted)      AS booked,
               ROUND(100.0*SUM(converted)/NULLIF(SUM(stage_checkout),0),2) AS checkout_to_book_pct
        FROM fact_sessions GROUP BY device ORDER BY checkout_started DESC""")

    # top-10 supplier GMV share (concentration input for the health index)
    top10_share = q("""
        WITH s AS (SELECT supplier_id, SUM(gbv_usd) g FROM fact_bookings
                   WHERE status<>'cancelled' GROUP BY supplier_id)
        SELECT 1.0*(SELECT SUM(g) FROM (SELECT g FROM s ORDER BY g DESC LIMIT 10))
               / (SELECT SUM(g) FROM s) AS share""").iloc[0, 0]

    # ---- Marketplace Health Index (0-100) ----
    # A single north-star I blended from five drivers. Each driver is mapped to
    # 0-1 against a sensible band, then weighted. Weights/bands are a judgement
    # call (documented in docs/DECISIONS.md) so the number is transparent.
    recent3 = monthly["gmv_usd"].tail(3).sum()
    prev3 = monthly["gmv_usd"].iloc[-6:-3].sum()
    growth_ratio = recent3 / prev3 if prev3 else 1.0

    def unit(x, lo, hi):
        return float(min(1.0, max(0.0, (x - lo) / (hi - lo))))

    comp = {
        "Growth":         unit(growth_ratio, 0.90, 1.40),
        "Conversion":     unit(overall_conv,  3.0, 7.0),
        "Retention":      unit(repeat,       10.0, 35.0),
        "Marketing ROAS": unit(blended_roas,  0.8, 2.0),
        "Supply spread":  unit(1.0 - top10_share, 0.45, 0.85),
    }
    weights = {"Growth": .30, "Conversion": .20, "Retention": .15,
               "Marketing ROAS": .20, "Supply spread": .15}
    health_index = round(100 * sum(comp[k] * weights[k] for k in comp), 1)
    health_components = [{"name": k, "score": round(comp[k] * 100, 1),
                         "weight": int(weights[k] * 100)} for k in comp]

    # experiment significance
    c_row = experiment[experiment["variant"] == "control"].iloc[0]
    t_row = experiment[experiment["variant"] == "treatment"].iloc[0]
    exp_stats = two_proportion_ztest(int(c_row["bookings"]), int(c_row["sessions"]),
                                     int(t_row["bookings"]), int(t_row["sessions"]))

    # =====================================================================
    # CHARTS
    # =====================================================================
    usd_m = FuncFormatter(lambda v, _: f"${v/1e6:.1f}M" if v >= 1e6 else f"${v/1e3:.0f}K")

    # 1 — monthly GMV + MoM growth
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.bar(monthly["year_month"], monthly["gmv_usd"], color=TEAL, alpha=0.85, label="GMV")
    ax.set_ylabel("GMV (USD)"); ax.yaxis.set_major_formatter(usd_m)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels(monthly["year_month"], rotation=45, ha="right", fontsize=8)
    ax2 = ax.twinx()
    ax2.plot(range(len(monthly)), monthly["gmv_mom_growth_pct"], color=PRIMARY,
             marker="o", ms=4, lw=2, label="MoM growth %")
    ax2.axhline(0, color=MUTED, lw=0.8, ls="--")
    ax2.set_ylabel("MoM growth %"); ax2.grid(False)
    _despine(ax); _despine(ax2)
    ax.set_title("Monthly GMV and month-over-month growth")
    _save(fig, "01_monthly_gmv.png")

    # 2 — conversion funnel
    fig, ax = plt.subplots(figsize=(9, 4.4))
    f = funnel.copy()
    colors = [PRIMARY, "#6366F1", TEAL, AMBER, GREEN]
    ax.barh(f["stage"], f["users"], color=colors)
    ax.invert_yaxis(); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/1e3:.0f}K"))
    for i, r in f.iterrows():
        ax.text(r["users"], i, f"  {r['users']:,.0f}  ({r['pct_of_sessions']:.0f}%)",
                va="center", fontsize=9, color=INK)
    _despine(ax)
    ax.set_title("Conversion funnel — biggest leak is View → Cart")
    _save(fig, "02_funnel.png")

    # 3 — channel ROAS
    fig, ax = plt.subplots(figsize=(9, 4.4))
    pc = paid.sort_values("roas_on_net_rev")
    cmap = {"Scale": GREEN, "Optimise": AMBER, "Cut / fix": RED}
    bar_colors = [cmap.get(r, MUTED) for r in pc["recommendation"]]
    ax.barh(pc["channel"], pc["roas_on_net_rev"], color=bar_colors)
    ax.axvline(1.0, color=INK, lw=1, ls="--")
    ax.text(1.02, -0.4, "break-even (ROAS=1)", fontsize=8, color=INK)
    for i, (_, r) in enumerate(pc.iterrows()):
        ax.text(r["roas_on_net_rev"], i,
                f"  {r['roas_on_net_rev']:.2f}×  (CAC ${r['cac_usd']:.0f})",
                va="center", fontsize=9)
    _despine(ax)
    ax.set_xlabel("ROAS on net revenue")
    ax.set_title("Paid channel efficiency — cut Display, scale Affiliates & Social")
    _save(fig, "03_channel_roas.png")

    # 4 — cohort retention heatmap
    piv = cohort.pivot_table(index="cohort_month", columns="months_since_signup",
                             values="retention_pct", aggfunc="first")
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    im = ax.imshow(piv.values, aspect="auto", cmap="BuPu")
    ax.set_xticks(range(piv.shape[1])); ax.set_xticklabels(piv.columns)
    ax.set_yticks(range(piv.shape[0])); ax.set_yticklabels(piv.index, fontsize=8)
    ax.set_xlabel("Months since signup"); ax.set_ylabel("Signup cohort")
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=7,
                        color="white" if v > np.nanmax(piv.values) * 0.6 else INK)
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="Repeat-purchase rate %")
    ax.set_title("Signup-cohort repeat-purchase retention")
    _save(fig, "04_cohort_retention.png")

    # 5 — lead-time pricing & volume
    fig, ax = plt.subplots(figsize=(9, 4.4))
    xpos = range(len(leadtime))
    ax.bar(xpos, leadtime["bookings"], color="#CBD5E1", label="Bookings")
    ax.set_ylabel("Bookings"); _despine(ax)
    ax.set_xticks(list(xpos))
    ax.set_xticklabels(leadtime["lead_time_bucket"], rotation=20, ha="right", fontsize=9)
    ax2 = ax.twinx()
    ax2.plot(list(xpos), leadtime["avg_price_multiplier"],
             color=PRIMARY, marker="o", lw=2)
    ax2.set_ylabel("Avg price multiplier"); ax2.grid(False); _despine(ax2)
    ax.set_title("Last-minute premium: multiplier rises as travel date nears")
    _save(fig, "05_leadtime_pricing.png")

    # 6 — experiment
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    arms = ["control", "treatment"]
    rates = [exp_stats["control_rate"] * 100, exp_stats["treatment_rate"] * 100]
    # 95% CI per arm for error bars
    errs = []
    for v, n in [(c_row["bookings"], c_row["sessions"]), (t_row["bookings"], t_row["sessions"])]:
        p = v / n; errs.append(1.96 * math.sqrt(p * (1 - p) / n) * 100)
    ax.bar(arms, rates, color=[MUTED, GREEN], yerr=errs, capsize=8, width=0.55)
    for i, r in enumerate(rates):
        ax.text(i, r + errs[i] + 0.1, f"{r:.2f}%", ha="center", fontweight="bold")
    _despine(ax); ax.set_ylabel("Session → booking conversion %")
    sig = "significant" if exp_stats["significant"] else "not significant"
    p_disp = "<1e-10" if exp_stats["p_value"] == 0 else f"{exp_stats['p_value']:.1e}"
    ax.set_title(f"checkout_v2 A/B: +{exp_stats['rel_lift_pct']:.1f}% lift "
                 f"(p={p_disp}, {sig})")
    _save(fig, "06_experiment.png")

    # 7 — supplier Pareto
    fig, ax = plt.subplots(figsize=(10, 4.4))
    s = suppliers.copy()
    ax.bar(range(len(s)), s["gmv_usd"], color=TEAL, alpha=0.85)
    ax.set_ylabel("Supplier GMV (USD)"); ax.yaxis.set_major_formatter(usd_m)
    ax.set_xlabel("Suppliers ranked by GMV (top 25)")
    ax2 = ax.twinx()
    ax2.plot(range(len(s)), s["running_gmv_share_pct"], color=PRIMARY, marker="o", ms=3, lw=2)
    ax2.axhline(80, color=RED, ls="--", lw=1); ax2.set_ylabel("Cumulative GMV share %")
    ax2.grid(False); _despine(ax); _despine(ax2)
    ax.set_title("Supplier concentration (Pareto)")
    _save(fig, "07_supplier_pareto.png")

    # 8 — pricing uplift by category
    fig, ax = plt.subplots(figsize=(9, 4.4))
    pcat = pricing_cat.sort_values("pricing_uplift_usd")
    ax.barh(pcat["category"], pcat["pricing_uplift_usd"], color=PRIMARY, alpha=0.85)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e3:.0f}K"))
    for i, (_, r) in enumerate(pcat.iterrows()):
        ax.text(r["pricing_uplift_usd"], i, f"  +{r['uplift_pct']:.1f}%", va="center", fontsize=9)
    _despine(ax)
    ax.set_title("Incremental GMV captured by dynamic pricing, by category")
    _save(fig, "08_pricing_uplift.png")

    # =====================================================================
    # DASHBOARD JSON
    # =====================================================================
    dashboard = dict(
        meta=dict(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            as_of_date="2026-10-05",
            window="2025-04 to 2026-09 (18 months)",
            currency="USD",
        ),
        headline=dict(
            gmv_usd=float(tot["gmv"]), net_revenue_usd=float(tot["net"]),
            bookings=int(tot["bk"]), aov_usd=float(tot["aov"]),
            take_rate_pct=float(tot["take"]), conversion_pct=float(overall_conv),
            repeat_rate_pct=float(repeat), paid_blended_roas=blended_roas,
            paid_spend_usd=paid_spend,
            latest_mom_growth_pct=float(monthly["gmv_mom_growth_pct"].iloc[-1]),
            health_index=health_index,
            recent_quarter_growth_pct=round((growth_ratio - 1) * 100, 1),
        ),
        health_components=health_components,
        monthly=recs(monthly), region=recs(region), channels=recs(channels),
        ltv=recs(ltv), funnel=recs(funnel), device=recs(device),
        device_checkout=recs(device_checkout),
        cohort=dict(cohorts=list(piv.index), months=[int(c) for c in piv.columns],
                    matrix=[[None if pd.isna(v) else float(v) for v in row] for row in piv.values]),
        experiment=dict(
            control=dict(sessions=int(c_row["sessions"]), bookings=int(c_row["bookings"])),
            treatment=dict(sessions=int(t_row["sessions"]), bookings=int(t_row["bookings"])),
            **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in exp_stats.items()},
        ),
        leadtime=recs(leadtime), pricing_by_category=recs(pricing_cat),
        demand_utilisation=recs(demand),
        suppliers_top=recs(suppliers), cities=recs(cities),
    )
    out = os.path.join(DASH, "dashboard_data.json")
    with open(out, "w") as f:
        json.dump(dashboard, f, indent=2)
    con.close()

    print("\nExperiment readout")
    print("-" * 40)
    for k, v in exp_stats.items():
        print(f"  {k:<16} {v}")
    print(f"\ndashboard_data.json written -> {out}")
    print(f"headline: GMV ${tot['gmv']/1e6:.2f}M | net ${tot['net']/1e6:.2f}M | "
          f"take {tot['take']}% | conv {overall_conv}% | repeat {repeat}% | "
          f"blended paid ROAS {blended_roas}x | health index {health_index}/100")


if __name__ == "__main__":
    main()
