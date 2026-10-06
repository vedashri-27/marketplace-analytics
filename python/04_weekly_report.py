"""
Generate a weekly business review from the warehouse as Markdown.

Instead of flagging "down >8% WoW" with a fixed threshold, it scores each
metric against the last 8 weeks with a z-score and only flags genuine outliers
(|z| >= 2). That way seasonal wobble doesn't trip false alarms. Meant to be run
on a schedule (cron / Airflow) and posted to Slack.

    python python/04_weekly_report.py              # latest complete week
    python python/04_weekly_report.py 2026-09-27   # a specific week-ending Sunday
"""
from __future__ import annotations
import os
import sqlite3
import sys
import pandas as pd

from _sqlutil import DB_PATH, ROOT

REPORTS = os.path.join(ROOT, "reports")
os.makedirs(REPORTS, exist_ok=True)

TRAILING_WEEKS = 8      # window for the anomaly baseline
Z_FLAG = 2.0            # |z| above this gets flagged


def week_ending(dates: pd.Series) -> pd.Series:
    """Sunday that ends the week each date falls in."""
    return dates + pd.to_timedelta((6 - dates.dt.weekday) % 7, unit="D")


def arrow(delta):
    if delta is None:
        return "n/a"
    if delta > 0.5:
        return f"up {delta:+.1f}%"
    if delta < -0.5:
        return f"down {delta:+.1f}%"
    return f"flat {delta:+.1f}%"


def pct_change(cur, prev):
    if prev in (0, None) or pd.isna(prev):
        return None
    return (cur - prev) / prev * 100


def main():
    con = sqlite3.connect(DB_PATH)
    bk = pd.read_sql("SELECT booking_date, gbv_usd, net_revenue_usd, num_guests, "
                     "status, channel, city_id FROM fact_bookings",
                     con, parse_dates=["booking_date"])
    sess = pd.read_sql("SELECT session_date, converted FROM fact_sessions",
                       con, parse_dates=["session_date"])
    cities = pd.read_sql("SELECT city_id, city FROM dim_city", con)
    con.close()

    bk = bk.merge(cities, on="city_id", how="left")
    realised = bk[bk["status"] != "cancelled"].copy()
    realised["week"] = week_ending(realised["booking_date"])
    sess["week"] = week_ending(sess["session_date"])

    # weekly metric series
    wk = realised.groupby("week").agg(
        gmv=("gbv_usd", "sum"),
        net_rev=("net_revenue_usd", "sum"),
        bookings=("gbv_usd", "size"),
        guests=("num_guests", "sum"),
    )
    wk["aov"] = wk["gmv"] / wk["bookings"]
    sess_wk = sess.groupby("week").agg(sessions=("converted", "size"),
                                       conv=("converted", "mean"))
    sess_wk["conv"] *= 100
    wk = wk.join(sess_wk)

    data_max = realised["booking_date"].max()
    complete = [w for w in wk.index if w <= data_max]
    target = pd.Timestamp(sys.argv[1]) if len(sys.argv) > 1 else complete[-1]
    prev = target - pd.Timedelta(days=7)
    start = target - pd.Timedelta(days=6)

    metrics = [("GMV (USD)", "gmv", "${:,.0f}"),
               ("Net revenue (USD)", "net_rev", "${:,.0f}"),
               ("Bookings", "bookings", "{:,.0f}"),
               ("AOV (USD)", "aov", "${:,.1f}"),
               ("Sessions", "sessions", "{:,.0f}"),
               ("Conversion %", "conv", "{:.2f}%")]

    # anomaly scores vs the trailing window
    hist = wk.loc[wk.index < target].tail(TRAILING_WEEKS)
    rows, flags = [], []
    for label, col, fmt in metrics:
        cur = wk.at[target, col] if target in wk.index else float("nan")
        pv = wk.at[prev, col] if prev in wk.index else None
        mean = hist[col].mean()
        std = hist[col].std()
        z = (cur - mean) / std if std and std > 0 else 0.0
        rows.append((label, fmt.format(cur), fmt.format(pv) if pv is not None else "n/a",
                     arrow(pct_change(cur, pv)), f"{z:+.1f}"))
        if abs(z) >= Z_FLAG:
            direction = "above" if z > 0 else "below"
            flags.append(f"**{label}** is {abs(z):.1f} sigma {direction} its 8-week "
                         f"average ({fmt.format(cur)} vs ~{fmt.format(mean)}).")

    # movers
    cur_rows = realised[(realised["booking_date"] >= start) & (realised["booking_date"] <= target)]
    prv_rows = realised[(realised["booking_date"] >= prev - pd.Timedelta(days=6)) &
                        (realised["booking_date"] <= prev)]

    def movers(dim):
        c = cur_rows.groupby(dim)["gbv_usd"].sum().sort_values(ascending=False).head(3)
        p = prv_rows.groupby(dim)["gbv_usd"].sum()
        return [(k, v, pct_change(v, p.get(k, 0))) for k, v in c.items()]

    cancel_pct = 100 * (bk[(bk["booking_date"] >= start) &
                           (bk["booking_date"] <= target)]["status"].eq("cancelled").mean())

    # render
    L = [f"# Weekly business review — week ending {target.date()}",
         f"_{start.date()} to {target.date()}, vs the prior week and the trailing "
         f"{TRAILING_WEEKS} weeks. Auto-generated._\n",
         "## Metrics\n",
         "| Metric | This week | Last week | WoW | z vs 8-wk |",
         "|---|--:|--:|:--|--:|"]
    L += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows]

    L.append("\n## Flags")
    if flags:
        L += [f"- {f}" for f in flags]
    else:
        L.append("- Nothing outside 2 sigma this week.")
    if cancel_pct > 11:
        L.append(f"- Cancellation rate {cancel_pct:.1f}% (above the 11% watch line).")

    L.append("\n## Top cities this week (GMV)\n| City | GMV | WoW |\n|---|--:|:--|")
    L += [f"| {k} | ${v:,.0f} | {arrow(d)} |" for k, v, d in movers("city")]
    L.append("\n## Top channels this week (GMV)\n| Channel | GMV | WoW |\n|---|--:|:--|")
    L += [f"| {k} | ${v:,.0f} | {arrow(d)} |" for k, v, d in movers("channel")]

    md = "\n".join(L) + "\n"
    out = os.path.join(REPORTS, f"WBR_{target.date()}.md")
    with open(out, "w") as f:
        f.write(md)
    print(md)
    print(f"[saved] {out}")


if __name__ == "__main__":
    main()
