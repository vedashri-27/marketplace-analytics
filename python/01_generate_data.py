"""
Generate a synthetic online-experiences marketplace to practise analytics on.

Builds cities, suppliers, experiences, customers, web sessions (the funnel),
bookings, daily marketing spend and a daily price/inventory snapshot, then
writes data/*.csv and loads a SQLite warehouse at data/marketplace.db.

Seeded (see SEED) so every run is identical.

    python python/01_generate_data.py
"""
from __future__ import annotations

import os
import sqlite3
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
SEED = 42
rng = np.random.default_rng(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "marketplace.db")
os.makedirs(DATA_DIR, exist_ok=True)

START_DATE = pd.Timestamp("2025-04-01")
END_DATE = pd.Timestamp("2026-09-30")          # data runs through end of Sep 2026
TODAY = pd.Timestamp("2026-10-05")             # "as of" date for the analysis
EXPERIMENT_START = pd.Timestamp("2026-06-01")  # checkout_v2 A/B test launch
N_DAYS = (END_DATE - START_DATE).days + 1

N_CUSTOMERS = 45_000
N_SUPPLIERS = 150
N_EXPERIENCES = 420
TARGET_IDENTIFIED_SESSIONS = 220_000            # sessions tied to a known customer
TARGET_ANON_SESSIONS = 150_000                  # anonymous / logged-out sessions


def dprint(msg: str) -> None:
    print(f"  [gen] {msg}", flush=True)


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------
# city, country, region, currency, fx (local units per 1 USD), tier, popularity weight
CITY_DATA = [
    ("New York",      "USA",         "North America", "USD", 1.00,  1, 1.00),
    ("Las Vegas",     "USA",         "North America", "USD", 1.00,  1, 0.85),
    ("Orlando",       "USA",         "North America", "USD", 1.00,  2, 0.70),
    ("London",        "UK",          "Europe",        "GBP", 0.79,  1, 0.95),
    ("Paris",         "France",      "Europe",        "EUR", 0.92,  1, 0.92),
    ("Rome",          "Italy",       "Europe",        "EUR", 0.92,  1, 0.78),
    ("Barcelona",     "Spain",       "Europe",        "EUR", 0.92,  2, 0.74),
    ("Amsterdam",     "Netherlands", "Europe",        "EUR", 0.92,  2, 0.60),
    ("Dubai",         "UAE",         "Middle East",   "AED", 3.67,  1, 0.80),
    ("Singapore",     "Singapore",   "APAC",          "SGD", 1.35,  2, 0.55),
    ("Tokyo",         "Japan",       "APAC",          "JPY", 149.0, 1, 0.72),
    ("Sydney",        "Australia",   "APAC",          "AUD", 1.52,  2, 0.50),
    ("Cancun",        "Mexico",      "LATAM",         "MXN", 17.8,  2, 0.52),
    ("Istanbul",      "Turkey",      "Europe",        "TRY", 34.0,  2, 0.48),
    ("Bangkok",       "Thailand",    "APAC",          "THB", 36.0,  2, 0.46),
]

CATEGORIES = [
    "Attraction Tickets", "Guided Tours", "Day Trips & Excursions",
    "Food & Drink", "Shows & Concerts", "Water Activities", "Museums & Exhibits",
]

# channel, acquisition weight, is_paid, conversion multiplier, CPC (USD), CTR
CHANNELS = [
    ("Organic Search", 0.26, False, 1.10, 0.00, 0.00),
    ("Direct",         0.14, False, 1.30, 0.00, 0.00),
    ("Paid Search",    0.22, True,  1.00, 2.60, 0.040),  # borderline ROAS -> optimise
    ("Paid Social",    0.16, True,  0.72, 1.10, 0.012),  # healthy ROAS  -> scale
    ("Display",        0.08, True,  0.52, 2.20, 0.004),  # ROAS < 1      -> cut / fix
    ("Affiliates",     0.08, True,  0.95, 1.40, 0.030),  # best ROAS     -> scale
    ("Email",          0.06, False, 1.42, 0.00, 0.00),
]
CH_NAMES = [c[0] for c in CHANNELS]
CH_ACQ_W = np.array([c[1] for c in CHANNELS]); CH_ACQ_W /= CH_ACQ_W.sum()
CH_IS_PAID = {c[0]: c[2] for c in CHANNELS}
CH_CONV = {c[0]: c[3] for c in CHANNELS}
CH_CPC = {c[0]: c[4] for c in CHANNELS}
CH_CTR = {c[0]: c[5] for c in CHANNELS}

DEVICES = ["Mobile", "Desktop", "Tablet"]
DEVICE_W = np.array([0.62, 0.33, 0.05])

CUSTOMER_COUNTRIES = [
    "USA", "UK", "Germany", "France", "India", "Canada", "Australia",
    "Spain", "Italy", "Brazil", "UAE", "Singapore", "Japan", "Netherlands",
]


def rand_dates(n: int, start: pd.Timestamp, end: pd.Timestamp, bias=None) -> np.ndarray:
    """n random dates in [start, end]. bias in (0,1): <1 skews later, >1 earlier."""
    span = (end - start).days
    u = rng.random(n)
    if bias is not None:
        u = u ** bias
    offs = np.floor(u * span).astype("int64")
    return (start.to_datetime64() + offs.astype("timedelta64[D]"))


def seasonality_factor(dates: np.ndarray) -> np.ndarray:
    """Travel demand multiplier: summer peak, Dec bump, weekend lift."""
    ts = pd.to_datetime(dates)
    month = ts.month.to_numpy()
    dow = ts.dayofweek.to_numpy()
    # summer peak centred on July, mild December bump
    seasonal = 1.0 + 0.30 * np.cos((month - 7) / 12 * 2 * np.pi)
    seasonal += np.where(month == 12, 0.12, 0.0)
    weekend = np.where(dow >= 5, 1.18, 1.0)
    return seasonal * weekend


# --------------------------------------------------------------------------
# 1. Dimensions
# --------------------------------------------------------------------------
def build_dim_city() -> pd.DataFrame:
    rows = []
    for i, (city, country, region, cur, fx, tier, w) in enumerate(CITY_DATA, start=1):
        launch = START_DATE - pd.Timedelta(days=int(rng.integers(120, 1200)))
        rows.append(dict(city_id=i, city=city, country=country, region=region,
                         currency=cur, fx_local_per_usd=fx, city_tier=tier,
                         popularity_weight=w, launch_date=launch.date().isoformat()))
    return pd.DataFrame(rows)


def build_dim_supplier(dim_city: pd.DataFrame) -> pd.DataFrame:
    city_ids = dim_city["city_id"].to_numpy()
    city_w = dim_city["popularity_weight"].to_numpy(); city_w = city_w / city_w.sum()
    rows = []
    for sid in range(1, N_SUPPLIERS + 1):
        cid = int(rng.choice(city_ids, p=city_w))
        tier = int(rng.choice([1, 2, 3], p=[0.2, 0.45, 0.35]))
        # take rate: bigger suppliers negotiate a lower commission
        base_comm = {1: 0.18, 2: 0.22, 3: 0.27}[tier]
        comm = round(float(np.clip(base_comm + rng.normal(0, 0.02), 0.12, 0.33)), 3)
        onboarded = START_DATE - pd.Timedelta(days=int(rng.integers(0, 900)))
        rows.append(dict(supplier_id=sid, supplier_name=f"Supplier {sid:03d}",
                         city_id=cid, supplier_tier=tier, commission_rate=comm,
                         onboarded_date=onboarded.date().isoformat()))
    return pd.DataFrame(rows)


def build_dim_experience(dim_city: pd.DataFrame, dim_supplier: pd.DataFrame) -> pd.DataFrame:
    sup_by_city = dim_supplier.groupby("city_id")["supplier_id"].apply(list).to_dict()
    city_ids = dim_city["city_id"].to_numpy()
    city_w = dim_city["popularity_weight"].to_numpy(); city_w = city_w / city_w.sum()
    # price bands by category (USD, per person)
    price_band = {
        "Attraction Tickets": (25, 70), "Guided Tours": (40, 140),
        "Day Trips & Excursions": (70, 260), "Food & Drink": (45, 160),
        "Shows & Concerts": (60, 320), "Water Activities": (50, 220),
        "Museums & Exhibits": (18, 55),
    }
    rows = []
    for eid in range(1, N_EXPERIENCES + 1):
        cid = int(rng.choice(city_ids, p=city_w))
        suppliers = sup_by_city.get(cid)
        if not suppliers:
            cid = int(dim_supplier.sample(1, random_state=int(eid))["city_id"].iloc[0])
            suppliers = sup_by_city[cid]
        sup = int(rng.choice(suppliers))
        cat = CATEGORIES[int(rng.integers(0, len(CATEGORIES)))]
        lo, hi = price_band[cat]
        base_price = round(float(rng.uniform(lo, hi)), 2)
        pop = round(float(rng.gamma(1.6, 1.0)), 3)   # experience-level popularity (long tail)
        listed = START_DATE - pd.Timedelta(days=int(rng.integers(0, 700)))
        rows.append(dict(experience_id=eid, experience_name=f"{cat.split(' ')[0]} Experience {eid:03d}",
                         city_id=cid, supplier_id=sup, category=cat,
                         base_price_usd=base_price, duration_hours=round(float(rng.uniform(1, 9)), 1),
                         max_group_size=int(rng.choice([6, 8, 10, 15, 20, 30])),
                         popularity=pop, listed_date=listed.date().isoformat()))
    return pd.DataFrame(rows)


def build_dim_customer() -> pd.DataFrame:
    # bias<1 skews signups toward more recent dates -> growing acquisition over time
    signup = rand_dates(N_CUSTOMERS, START_DATE, END_DATE - pd.Timedelta(days=5), bias=0.82)
    channel = rng.choice(CH_NAMES, size=N_CUSTOMERS, p=CH_ACQ_W)
    country = rng.choice(CUSTOMER_COUNTRIES, size=N_CUSTOMERS)
    device = rng.choice(DEVICES, size=N_CUSTOMERS, p=DEVICE_W)
    # heavy-tailed engagement propensity -> drives repeat sessions / retention
    propensity = rng.gamma(0.9, 1.0, size=N_CUSTOMERS) + 0.15
    return pd.DataFrame(dict(
        customer_id=np.arange(1, N_CUSTOMERS + 1),
        signup_date=pd.to_datetime(signup),
        acquisition_channel=channel, country=country, signup_device=device,
        propensity=propensity,
    ))


# --------------------------------------------------------------------------
# 2. Sessions (the funnel grain) + bookings derived from conversions
# --------------------------------------------------------------------------
def build_sessions(dim_city, dim_experience, dim_customer):
    exp_ids = dim_experience["experience_id"].to_numpy()
    exp_city = dim_experience.set_index("experience_id")["city_id"].to_dict()
    exp_pop = dim_experience["popularity"].to_numpy()
    city_of_exp = dim_experience["city_id"].to_numpy()
    city_pop_map = dim_city.set_index("city_id")["popularity_weight"].to_dict()
    # experience sampling weight = experience popularity * its city popularity
    exp_weight = exp_pop * np.array([city_pop_map[c] for c in city_of_exp])
    exp_weight = exp_weight / exp_weight.sum()

    # ---- identified sessions: distribute across customers by propensity ----
    prop = dim_customer["propensity"].to_numpy()
    exp_sessions = prop / prop.sum() * TARGET_IDENTIFIED_SESSIONS
    n_sessions_per_cust = rng.poisson(exp_sessions).astype("int64")
    n_sessions_per_cust = np.clip(n_sessions_per_cust, 0, 60)
    total_ident = int(n_sessions_per_cust.sum())

    cust_idx = np.repeat(np.arange(N_CUSTOMERS), n_sessions_per_cust)
    cust_ids = dim_customer["customer_id"].to_numpy()[cust_idx]
    signups = dim_customer["signup_date"].to_numpy()[cust_idx]
    acq = dim_customer["acquisition_channel"].to_numpy()[cust_idx]

    # session date = signup + Beta-biased offset within remaining window
    end64 = END_DATE.to_datetime64()
    span_days = ((end64 - signups) / np.timedelta64(1, "D")).astype("int64")
    span_days = np.clip(span_days, 0, None)
    # flatter offset (not strongly front-loaded) keeps late weeks well-populated
    offs = np.floor(rng.beta(1.0, 1.5, size=total_ident) * (span_days + 1)).astype("int64")
    sess_date_ident = signups + offs.astype("timedelta64[D]")

    # rank each customer's sessions chronologically to flag "returning"
    order = np.lexsort((sess_date_ident, cust_ids))
    ranks = np.empty(total_ident, dtype="int64")
    tmp = cust_ids[order]
    seq = np.zeros(total_ident, dtype="int64")
    # cumulative count within customer
    is_new_cust = np.concatenate(([True], tmp[1:] != tmp[:-1]))
    grp_start = np.where(is_new_cust)[0]
    counter = np.arange(total_ident) - np.repeat(grp_start, np.diff(np.append(grp_start, total_ident)))
    seq[order] = counter
    is_returning_ident = seq > 0

    # channel for identified sessions: first session uses acquisition channel,
    # later sessions skew to owned/direct channels (retention behaviour)
    retn_channel_w = np.array([0.30, 0.26, 0.12, 0.06, 0.02, 0.04, 0.20])  # organic,direct,psearch,psocial,display,aff,email
    retn_channel_w /= retn_channel_w.sum()
    ch_ident = np.where(
        is_returning_ident,
        rng.choice(CH_NAMES, size=total_ident, p=retn_channel_w),
        acq,
    )
    dev_ident = dim_customer["signup_device"].to_numpy()[cust_idx]

    # ---- anonymous sessions ----
    n_anon = TARGET_ANON_SESSIONS
    sess_date_anon = rand_dates(n_anon, START_DATE, END_DATE, bias=0.9)
    anon_channel_w = CH_ACQ_W.copy()
    ch_anon = rng.choice(CH_NAMES, size=n_anon, p=anon_channel_w)
    dev_anon = rng.choice(DEVICES, size=n_anon, p=DEVICE_W)

    # ---- combine ----
    sess_date = np.concatenate([sess_date_ident, sess_date_anon])
    customer_id = np.concatenate([cust_ids, np.zeros(n_anon, dtype="int64")])  # 0 == anonymous
    is_returning = np.concatenate([is_returning_ident, np.zeros(n_anon, dtype=bool)])
    channel = np.concatenate([ch_ident, ch_anon])
    device = np.concatenate([dev_ident, dev_anon])
    n = sess_date.shape[0]

    landing_exp = rng.choice(exp_ids, size=n, p=exp_weight)
    city_id = np.array([exp_city[e] for e in landing_exp])

    # experiment assignment (checkout_v2) for sessions on/after launch
    post = pd.to_datetime(sess_date) >= EXPERIMENT_START
    grp = np.where(post, rng.choice(["control", "treatment"], size=n), "pre_experiment")

    # ---- funnel ----
    season = seasonality_factor(sess_date)
    conv_mult = np.array([CH_CONV[c] for c in channel])
    returning_mult = np.where(is_returning, 1.5, 1.0)

    p_view = np.clip(0.80 * (0.9 + 0.1 * season), 0, 0.98)
    stage_view = rng.random(n) < p_view

    p_cart = np.where(stage_view, 0.36, 0.0)
    stage_cart = rng.random(n) < p_cart

    p_checkout = np.where(stage_cart, 0.56, 0.0)
    stage_checkout = rng.random(n) < p_checkout

    # final book probability picks up all the business levers
    treat_mult = np.where((grp == "treatment"), 1.18, 1.0)
    # device effect concentrated at checkout->book: mobile checkout has friction
    device_mult = np.select(
        [device == "Mobile", device == "Desktop", device == "Tablet"],
        [0.85, 1.12, 1.00], default=1.0,
    )
    p_book = np.where(
        stage_checkout,
        np.clip(0.22 * conv_mult * returning_mult * device_mult
                * (0.85 + 0.25 * season) * treat_mult, 0, 0.95),
        0.0,
    )
    converted = rng.random(n) < p_book

    sessions = pd.DataFrame(dict(
        session_id=np.arange(1, n + 1),
        session_date=pd.to_datetime(sess_date),
        customer_id=customer_id,
        is_returning=is_returning,
        channel=channel,
        device=device,
        city_id=city_id,
        landing_experience_id=landing_exp,
        experiment_group=grp,
        stage_view=stage_view,
        stage_cart=stage_cart,
        stage_checkout=stage_checkout,
        converted=converted,
    ))
    # shuffle so session_id isn't correlated with customer ordering
    sessions = sessions.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    sessions["session_id"] = np.arange(1, n + 1)
    return sessions


def build_bookings(sessions, dim_city, dim_experience, dim_supplier):
    conv = sessions[sessions["converted"]].copy().reset_index(drop=True)
    n = len(conv)
    exp = dim_experience.set_index("experience_id")
    sup = dim_supplier.set_index("supplier_id")
    city = dim_city.set_index("city_id")

    eid = conv["landing_experience_id"].to_numpy()
    base_price = exp.loc[eid, "base_price_usd"].to_numpy()
    supplier_id = exp.loc[eid, "supplier_id"].to_numpy()
    city_id = conv["city_id"].to_numpy()
    cur = city.loc[city_id, "currency"].to_numpy()
    fx = city.loc[city_id, "fx_local_per_usd"].to_numpy()
    comm = sup.loc[supplier_id, "commission_rate"].to_numpy()

    booking_date = conv["session_date"].to_numpy()  # book same day as session
    lead_days = np.clip(rng.gamma(2.0, 9.0, size=n).astype("int64"), 0, 160)
    travel_date = booking_date + lead_days.astype("timedelta64[D]")

    # dynamic pricing multiplier: last-minute premium + weekend travel + demand noise
    tdow = pd.to_datetime(travel_date).dayofweek.to_numpy()
    lastminute = np.where(lead_days <= 2, 1.12, np.where(lead_days <= 7, 1.05, 1.0))
    weekend_travel = np.where(tdow >= 5, 1.06, 1.0)
    demand_noise = np.clip(rng.normal(1.0, 0.07, size=n), 0.82, 1.3)
    price_mult = np.round(lastminute * weekend_travel * demand_noise, 3)
    effective_price = np.round(base_price * price_mult, 2)

    guests = rng.choice([1, 2, 3, 4, 5, 6], size=n, p=[0.18, 0.40, 0.14, 0.16, 0.06, 0.06])

    # promo discounts: ~22% of bookings get a discount
    has_disc = rng.random(n) < 0.22
    disc_rate = np.where(has_disc, rng.choice([0.05, 0.10, 0.15], size=n, p=[0.5, 0.35, 0.15]), 0.0)
    gross_pre = effective_price * guests
    discount_usd = np.round(gross_pre * disc_rate, 2)
    gbv_usd = np.round(gross_pre - discount_usd, 2)
    gbv_local = np.round(gbv_usd * fx, 2)
    net_revenue_usd = np.round(gbv_usd * comm, 2)       # platform commission (take)
    supplier_payout_usd = np.round(gbv_usd - net_revenue_usd, 2)

    # status: cancelled ~9%; else completed if travel in past, confirmed otherwise
    cancelled = rng.random(n) < 0.09
    travelled = pd.to_datetime(travel_date) < TODAY
    status = np.where(cancelled, "cancelled", np.where(travelled, "completed", "confirmed"))

    # ratings only for completed bookings, skewed high
    rating = np.where(status == "completed",
                      rng.choice([3, 4, 5], size=n, p=[0.12, 0.33, 0.55]).astype("float64"),
                      np.nan)

    bookings = pd.DataFrame(dict(
        booking_id=np.arange(1, n + 1),
        session_id=conv["session_id"].to_numpy(),
        customer_id=conv["customer_id"].to_numpy(),
        experience_id=eid,
        supplier_id=supplier_id,
        city_id=city_id,
        booking_date=pd.to_datetime(booking_date),
        travel_date=pd.to_datetime(travel_date),
        lead_days=lead_days,
        num_guests=guests,
        currency=cur,
        fx_local_per_usd=fx,
        base_price_usd=np.round(base_price, 2),
        price_multiplier=price_mult,
        effective_price_usd=effective_price,
        discount_usd=discount_usd,
        gbv_usd=gbv_usd,
        gbv_local=gbv_local,
        commission_rate=comm,
        net_revenue_usd=net_revenue_usd,
        supplier_payout_usd=supplier_payout_usd,
        channel=conv["channel"].to_numpy(),
        device=conv["device"].to_numpy(),
        experiment_group=conv["experiment_group"].to_numpy(),
        status=status,
        rating=rating,
    ))
    return bookings


# --------------------------------------------------------------------------
# 3. Marketing spend (paid sessions == clicks)  &  daily pricing/inventory
# --------------------------------------------------------------------------
def build_marketing_spend(sessions):
    paid = sessions[sessions["channel"].map(CH_IS_PAID)].copy()
    paid["d"] = paid["session_date"].dt.date
    grp = (paid.groupby(["d", "channel", "city_id"]).size()
           .reset_index(name="clicks"))
    cpc = grp["channel"].map(CH_CPC).to_numpy()
    ctr = grp["channel"].map(CH_CTR).to_numpy()
    noise = np.clip(rng.normal(1.0, 0.12, size=len(grp)), 0.7, 1.4)
    grp["spend_usd"] = np.round(grp["clicks"].to_numpy() * cpc * noise, 2)
    grp["impressions"] = np.ceil(grp["clicks"].to_numpy() / np.where(ctr > 0, ctr, 0.02)).astype("int64")
    grp = grp.rename(columns={"d": "spend_date"})
    grp["spend_date"] = pd.to_datetime(grp["spend_date"])
    return grp[["spend_date", "channel", "city_id", "impressions", "clicks", "spend_usd"]]


def build_daily_pricing(dim_experience, bookings):
    """Daily dynamic-price + inventory snapshot for the top ~60 experiences."""
    top = (bookings.groupby("experience_id").size().sort_values(ascending=False)
           .head(60).index.to_numpy())
    exp = dim_experience.set_index("experience_id")
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    rows = []
    for eid in top:
        base = float(exp.loc[eid, "base_price_usd"])
        cap = int(rng.choice([20, 30, 40, 60, 80]))  # daily slot capacity
        season = seasonality_factor(dates.to_numpy())
        demand_index = np.clip(season * rng.normal(1.0, 0.08, size=len(dates)), 0.6, 1.6)
        dyn = np.round(base * (0.9 + 0.35 * (demand_index - 0.8)), 2)
        slots_booked = np.clip((cap * (demand_index - 0.5) * rng.uniform(0.3, 0.7, len(dates))).astype("int64"), 0, cap)
        rows.append(pd.DataFrame(dict(
            experience_id=eid, price_date=dates,
            base_price_usd=round(base, 2), dynamic_price_usd=dyn,
            demand_index=np.round(demand_index, 3),
            slots_available=cap, slots_booked=slots_booked,
        )))
    return pd.concat(rows, ignore_index=True)


def build_dim_date() -> pd.DataFrame:
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    return pd.DataFrame(dict(
        date_day=dates,
        year=dates.year, quarter=dates.quarter, month=dates.month,
        month_name=dates.strftime("%b"),
        day_of_week=dates.dayofweek,
        day_name=dates.strftime("%a"),
        is_weekend=(dates.dayofweek >= 5),
        year_month=dates.strftime("%Y-%m"),
    ))


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    dprint("building dimensions ...")
    dim_city = build_dim_city()
    dim_supplier = build_dim_supplier(dim_city)
    dim_experience = build_dim_experience(dim_city, dim_supplier)
    dim_customer = build_dim_customer()
    dim_date = build_dim_date()

    dprint("building sessions (funnel grain) ...")
    sessions = build_sessions(dim_city, dim_experience, dim_customer)
    dprint(f"  -> {len(sessions):,} sessions")

    dprint("deriving bookings from conversions ...")
    bookings = build_bookings(sessions, dim_city, dim_experience, dim_supplier)
    # link booking_id back onto sessions
    sess_to_booking = dict(zip(bookings["session_id"], bookings["booking_id"]))
    sessions["booking_id"] = sessions["session_id"].map(sess_to_booking).fillna(0).astype("int64")
    dprint(f"  -> {len(bookings):,} bookings "
           f"(session->booking conv = {len(bookings)/len(sessions)*100:.2f}%)")

    dprint("building marketing spend ...")
    marketing = build_marketing_spend(sessions)

    dprint("building daily pricing / inventory ...")
    pricing = build_daily_pricing(dim_experience, bookings)

    # drop helper columns not meant for the warehouse
    dim_customer_out = dim_customer.drop(columns=["propensity"])
    dim_experience_out = dim_experience  # keep popularity: it's a legit attribute

    tables = {
        "dim_city": dim_city,
        "dim_supplier": dim_supplier,
        "dim_experience": dim_experience_out,
        "dim_customer": dim_customer_out,
        "dim_date": dim_date,
        "fact_sessions": sessions,
        "fact_bookings": bookings,
        "fact_marketing_spend": marketing,
        "fact_daily_pricing": pricing,
    }

    # ---- write CSVs ----
    dprint("writing CSVs ...")
    for name, df in tables.items():
        out = df.copy()
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                out[col] = out[col].dt.strftime("%Y-%m-%d")
        out.to_csv(os.path.join(DATA_DIR, f"{name}.csv"), index=False)

    # ---- load SQLite warehouse ----
    dprint("loading SQLite warehouse ...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    for name, df in tables.items():
        out = df.copy()
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                out[col] = out[col].dt.strftime("%Y-%m-%d")
            if pd.api.types.is_bool_dtype(out[col]):
                out[col] = out[col].astype("int64")
        out.to_sql(name, con, if_exists="replace", index=False)

    idx = [
        "CREATE INDEX idx_book_city ON fact_bookings(city_id);",
        "CREATE INDEX idx_book_exp ON fact_bookings(experience_id);",
        "CREATE INDEX idx_book_sup ON fact_bookings(supplier_id);",
        "CREATE INDEX idx_book_cust ON fact_bookings(customer_id);",
        "CREATE INDEX idx_book_date ON fact_bookings(booking_date);",
        "CREATE INDEX idx_book_channel ON fact_bookings(channel);",
        "CREATE INDEX idx_sess_date ON fact_sessions(session_date);",
        "CREATE INDEX idx_sess_channel ON fact_sessions(channel);",
        "CREATE INDEX idx_sess_cust ON fact_sessions(customer_id);",
        "CREATE INDEX idx_mkt_date ON fact_marketing_spend(spend_date);",
        "CREATE INDEX idx_price_exp ON fact_daily_pricing(experience_id);",
    ]
    for stmt in idx:
        con.execute(stmt)
    con.commit()
    con.close()

    dprint("done.")
    print("\nRow counts")
    print("-" * 32)
    for name, df in tables.items():
        print(f"  {name:<24} {len(df):>9,}")
    print(f"\nSQLite warehouse: {DB_PATH}")


if __name__ == "__main__":
    main()
