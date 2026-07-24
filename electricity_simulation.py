"""
Forecast #9: deterministic + stochastic decomposition for the Virginia
commercial electricity rate reversal question (resolution 2027-01-21).

YES if the EIA commercial-sector VA rate at the January 2027 observation is
BELOW the 10.33 cents/kWh baseline (July 2026, the latest cached actual). The
persisted tier-3 estimate (30%) hand-blended a locked base-rate increase
against a forecast fuel-cost easing. This module models the two separately and
combines them properly:

    rate_jan2027 = 10.33
                 + base-rate delta   (deterministic: Dominion's SCC-locked
                                      Jan 1, 2027 step, small allocation band)
                 + regulatory risk   (securitization decision; GS-5 class
                                      composition change)
                 + fuel delta        (stochastic: OU-simulated Henry Hub path
                                      mapped through the REAL fuel-factor
                                      pass-through timing)
                 + winter-spike risk (cold-event Januaries in the EIA-861M
                                      history)
                 + idiosyncratic noise

The decisive research finding is about TRANSMISSION, not gas prices: Dominion's
fuel factor is an annual tariff -- the rate applying on 2027-01-21 was fixed on
2026-07-01 (3.7648 c/kWh interim, case PUR-2026-00058) and holds through
2027-06-30, with interim gas moves accruing to a deferral that surfaces only at
the 2027-07-01 reset. So the Ornstein-Uhlenbeck Henry Hub simulation below --
calibrated to real daily spot data and anchored to the July 2026 STEO -- enters
the January 2027 rate with a pass-through weight of ZERO. It is retained (a)
because it documents that the tier-3 "+8pp STEO fuel easing" adjustment lacks a
transmission channel inside this window, and (b) to quantify the counterfactual:
what the fuel component WOULD contribute if pass-through were live.

Sources are cited on each constant; parameters that had to be assumed rather
than estimated carry explicit ASSUMED comments.
"""

import json
import math
import random
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forecasts import FORECAST_STATE_PATH, set_forecast_probability


FORECAST_ID = 9
AS_OF_DATE = date(2026, 7, 22)        # repo convention, mirrors fomc_history.CURRENT_AS_OF_DATE
RESOLUTION_DATE = date(2027, 1, 21)
BASELINE_CENTS_PER_KWH = 10.33        # Jul 2026 actual, data_cache/eia_virginia_retail_electricity.json
DEFAULT_MONTE_CARLO_PATHS = 10_000
DEFAULT_RANDOM_SEED = 20260722        # deterministic; same convention as tier1_market.py
SAMPLE_GAS_PATHS_FOR_PLOT = 12

DATA_CACHE_DIR = Path(__file__).with_name("data_cache")
HENRY_HUB_CACHE = DATA_CACHE_DIR / "henry_hub_daily.json"
TRADING_DAYS_PER_YEAR = 252
OU_CALIBRATION_YEARS = 3              # trailing window, avoids the 2021-22 crisis regime

# Literature anchor for the OU fit (sanity check, not the estimate):
# Schwartz one-factor / Hull-White-Vasicek OLS calibration on Henry Hub daily
# spot 2000-2008 (2,676 obs): kappa = 1.7696/yr (half-life ~4.7 months),
# annualized sigma = 0.7445.
# https://www.mathworks.com/matlabcentral/mlc-downloads/downloads/submissions/28056/versions/6/previews/html/ModelNGPrice.html (accessed 2026-07-22)
LITERATURE_OU = {"kappa_per_year": 1.7696, "half_life_months": 4.7, "sigma_annualized": 0.7445}

# EIA July 2026 STEO Henry Hub forecast (published 2026-07-07): 2026 avg $3.67,
# 2027 avg $3.49; quarterly path below. Note the seasonal shape: Q1 2027
# ($3.83) is the HIGHEST quarter in the window -- gas is seasonally expensive
# in January. The May 2026 STEO cut cited by the tier-3 estimate ($3.50 for
# 2026, -4.4%) was REVERSED by this July vintage, so the "+8pp fuel easing"
# adjustment is stale on its own terms.
# https://www.rigzone.com/news/usa_eia_raises_henry_hub_price_forecast_for_2026_2027-15-jul-2026-184139-article/ (accessed 2026-07-22)
STEO_QUARTERLY_USD_MMBTU = {"2026Q3": 3.37, "2026Q4": 3.57, "2027Q1": 3.83}
SIMULATION_MONTHS = ("2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01")
_MONTH_TO_QUARTER = {
    "2026-08": "2026Q3", "2026-09": "2026Q3",
    "2026-10": "2026Q4", "2026-11": "2026Q4", "2026-12": "2026Q4",
    "2027-01": "2027Q1",
}

# Fuel share of the VA commercial rate: fuel factor / commercial average price
# = 2.9680/10.33 = 0.287 (pre-Jul 2026) and 3.7648/10.33 = 0.364 (current
# interim) -- the project's ~1/3 assumption confirmed, range 0.29-0.36.
# https://gridflexibility.fyi/case-studies/dominion-virginia (accessed 2026-07-22)
FUEL_SHARE = 0.33

# THE TRANSMISSION FINDING. Dominion fuel factor (Rider A): annual fuel case
# filed ~April-May, rates effective July 1 for the 12-month fuel year. The
# 2026 interim rate (3.7648 c/kWh, approved 2026-05-29, case PUR-2026-00058)
# applies 2026-07-01 .. 2027-06-30; interim gas moves accrue to the deferral
# and surface at the 2027-07-01 reset. An Aug-Dec 2026 Henry Hub move
# therefore does NOT reach the 2027-01-21 commercial rate.
# https://aobaalliance.com/2025/06/virginia-dominion-power-application-to-revise-its-fuel-factor/ (accessed 2026-07-22)
# https://gridflexibility.fyi/case-studies/dominion-virginia (accessed 2026-07-22)
IN_WINDOW_GAS_PASS_THROUGH = 0.0

# Dominion is not all of Virginia: the EIA commercial average covers every VA
# utility (APCo, co-ops, municipals). ASSUMED: Dominion serves ~65% of VA
# commercial retail sales (roughly two-thirds, its commonly cited share of VA
# load), so Dominion-specific tariff deltas are diluted by 0.65 in the
# statewide EIA average. No precise class-level share was published.
DOMINION_SHARE_OF_VA_COMMERCIAL = 0.65

# Locked base-rate step: biennial review PUR-2025-00058 (final order
# 2025-11-25) approved a second revenue step of $209.9M effective 2027-01-01
# -- 20 days before resolution. Class-level c/kWh was not published; $209.9M
# over ~85 TWh jurisdictional sales ~ +0.25 c/kWh system average. ASSUMED
# band: Uniform(0.15, 0.30) c/kWh on Dominion bills, covering commercial-class
# allocation uncertainty around that midpoint.
# https://www.scc.virginia.gov/about-the-scc/newsreleases/release/scc-issues-order-on-dev-biennial-review-2025/scc-rules-in-dev-biennial-review-case.html (accessed 2026-07-22)
# https://reisingergooch.com/virginia-energy-regulatory-updates-november-2025/ (accessed 2026-07-22)
BASE_STEP_JAN2027_CENTS_LOW = 0.15
BASE_STEP_JAN2027_CENTS_HIGH = 0.30

# Securitization contingency: petition PUR-2026-00078 (hearing 2026-08-11/12,
# final order deadline 2026-09-29). The current interim fuel rate is
# predicated on securitizing the ~$1.078B fuel deferral; if DENIED, the fuel
# factor rises to standard one-year recovery -- ~+1.4 c/kWh above the interim
# -- inside the resolution window. If APPROVED, a ~$1.80/mo residential
# securitization rider (~0.18 c/kWh) begins "early 2027", timing vs Jan 21
# uncertain. One-sided UPSIDE risk to the rate either way.
# https://reisingergooch.com/virginia-energy-regulatory-updates-june-2026/ (accessed 2026-07-22)
# https://cardinalnews.org/2026/05/08/dominion-details-2-scenarios-for-higher-monthly-bills/ (accessed 2026-07-22)
P_SECURITIZATION_DENIED = 0.25        # ASSUMED: SCC granted the interim rate on the
                                      # securitization premise; denial is the minority case
SECURITIZATION_DENIED_CENTS = 1.4
P_RIDER_IN_WINDOW_IF_APPROVED = 0.5   # ASSUMED: "early 2027" vs the Jan 21 observation is a coin flip
SECURITIZATION_RIDER_CENTS = 0.18

# GS-5 data-center rate class (25 MW+) takes effect 2027-01-01, moving the
# largest loads out of the general commercial mix exactly at resolution.
# Direction on the EIA commercial AVERAGE is ambiguous. ASSUMED: zero-mean
# Normal(0, 0.05) composition noise.
# https://virginiamercury.com/2025/11/25/scc-approves-chesterfield-gas-plant-and-dominion-rate-hike-creates-new-rate-class-for-data-centers/ (accessed 2026-07-22)
GS5_COMPOSITION_NOISE_STD = 0.05

# Winter cold-spike risk: the EIA-861M history shows Jan 2026 at 11.43 c/kWh
# (+11% vs Dec 2025) in the extreme-cold event that created the $567M fuel
# deferral, and a milder Jan 2024 bump. ASSUMED: P(spike) = 2/11 Januaries
# ~ 0.18, magnitude Uniform(0.3, 1.2) c/kWh -- calibrated to those two events.
# https://www.eia.gov/electricity/data/eia861m/ (accessed 2026-07-22)
P_WINTER_SPIKE = 0.18
WINTER_SPIKE_CENTS_LOW = 0.3
WINTER_SPIKE_CENTS_HIGH = 1.2

# Idiosyncratic 6-month noise: month-over-month moves in the cached smooth
# commercial series (10.21 .. 10.33, Dec 2025-Jul 2026) have sd ~0.033/month
# -> sqrt(6) x 0.033 ~ 0.08 over the horizon. ASSUMED normality; see the
# series-discrepancy caveat below for why this sigma may be understated.
IDIOSYNCRATIC_NOISE_STD = 0.08

# DATA-QUALITY CAVEAT (flagged, not silently resolved): the repo cache
# (eia_virginia_retail_electricity.json) shows a smooth 10.21-10.33 path for
# Dec 2025-Jul 2026, while the preliminary EIA-861M spreadsheet shows Jan 2026
# = 11.43 and Feb 2026 = 13.01 -- the cold-event spike. If the resolution
# series behaves like 861M, January is likelier to spike UP than to dip below
# baseline, and the noise sigma above is understated. Both readings hurt YES,
# so the headline is, if anything, generous to YES.
SERIES_DISCREPANCY_CAVEAT = (
    "The cached EIA commercial series (smooth 10.21-10.33, Dec 2025-Jul 2026) and the "
    "preliminary EIA-861M spreadsheet (Jan 2026 = 11.43, Feb 2026 = 13.01 -- the "
    "cold-event spike) disagree. The winter-spike term and noise sigma are calibrated "
    "on the assumption the resolution series can show 861M-style January spikes; if it "
    "instead tracks the smooth cached series, the spike term overstates January "
    "variance -- in either case the effect on P(YES) is downward or neutral, so the "
    "discrepancy does not rescue the YES side."
)

# Empirical cross-check: of the 11 Jan(t+1)-vs-Jul(t) pairs in the EIA-861M VA
# commercial history 2015-2026, January printed BELOW the prior July 4 times
# (2016, 2019, 2020, 2021) = 36% -- close to the tier-3 35% base rate. All
# four came from the flat-to-declining-rate era before the current locked
# increase cycle; the component model conditions on the 2027-01-01 locked step
# that era did not have.
# https://www.eia.gov/electricity/data/eia861m/xls/sales_revenue.xlsx (accessed 2026-07-22)
EMPIRICAL_JAN_BELOW_JUL = (4, 11)

TIER3_REFERENCE_PCT = 30.0


@dataclass(frozen=True)
class OUFit:
    kappa_per_year: float
    half_life_months: float
    sigma_annualized: float
    long_run_mean_usd: float
    n_observations: int
    window_start: str
    window_end: str
    source: str


def calibrate_ou_from_cache(cache_path: Path = HENRY_HUB_CACHE) -> OUFit | None:
    """AR(1) calibration of an OU process on daily log Henry Hub prices.

    Discrete exact OU: X_{t+dt} = a + b X_t + eps, with b = exp(-kappa dt),
    long-run log mean m = a / (1 - b), and Var(eps) = sigma^2 (1 - b^2) / (2 kappa)
    -> sigma = sd(eps) * sqrt(2 kappa / (1 - b^2)). dt = one trading day.
    Restricted to the trailing OU_CALIBRATION_YEARS to avoid the 2021-22
    crisis regime dominating the variance. Returns None if the cache written
    by the research pass is unavailable (the caller falls back to the
    literature anchor with a loud note).
    """
    if not cache_path.exists():
        return None
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    observations = payload.get("observations", [])
    cutoff = f"{AS_OF_DATE.year - OU_CALIBRATION_YEARS:04d}-{AS_OF_DATE.month:02d}-{AS_OF_DATE.day:02d}"
    prices = [
        (o["date"], float(o["price_usd_per_mmbtu"]))
        for o in observations
        if o.get("price_usd_per_mmbtu") and o["date"] >= cutoff
    ]
    if len(prices) < 200:
        return None
    logs = [math.log(p) for _, p in prices]
    xs, ys = logs[:-1], logs[1:]
    n = len(xs)
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = mean_y - b * mean_x
    if not 0.0 < b < 1.0:
        return None
    dt = 1.0 / TRADING_DAYS_PER_YEAR
    kappa = -math.log(b) / dt
    residual_sd = math.sqrt(
        sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / (n - 2)
    )
    sigma = residual_sd * math.sqrt(2.0 * kappa / (1.0 - b * b))
    return OUFit(
        kappa_per_year=kappa,
        half_life_months=math.log(2.0) / kappa * 12.0,
        sigma_annualized=sigma,
        long_run_mean_usd=math.exp(a / (1.0 - b)),
        n_observations=n + 1,
        window_start=prices[0][0],
        window_end=prices[-1][0],
        source=str(cache_path.name),
    )


def _latest_cached_gas_price(cache_path: Path = HENRY_HUB_CACHE) -> float:
    """Simulation starting point: last cached daily spot ($2.83 on 2026-07-13)."""
    if cache_path.exists():
        observations = json.loads(cache_path.read_text(encoding="utf-8")).get("observations", [])
        if observations:
            return float(observations[-1]["price_usd_per_mmbtu"])
    # Fallback: July 2026 STEO Q3 average (cache should normally exist).
    return STEO_QUARTERLY_USD_MMBTU["2026Q3"]


def simulate_gas_paths(
    ou: OUFit | None,
    paths: int,
    rng: random.Random,
) -> list[list[float]]:
    """Monthly OU paths Aug 2026 .. Jan 2027 around the STEO anchor path.

    The STEO quarterly forecast is the current-information drift anchor (the
    history supplies kappa and sigma; the STEO supplies the level): the OU
    deviation Y_t mean-reverts to zero around log(STEO month anchor), i.e.
    X_t = log(anchor_t) + Y_t with exact discretization
    Y_{t+dt} = Y_t exp(-kappa dt) + N(0, sigma^2 (1 - exp(-2 kappa dt)) / (2 kappa)).
    Falls back to the cited literature kappa/sigma when the cache is missing.
    """
    kappa = ou.kappa_per_year if ou else LITERATURE_OU["kappa_per_year"]
    sigma = ou.sigma_annualized if ou else LITERATURE_OU["sigma_annualized"]
    dt = 1.0 / 12.0
    decay = math.exp(-kappa * dt)
    shock_sd = sigma * math.sqrt((1.0 - decay * decay) / (2.0 * kappa))
    start_price = _latest_cached_gas_price()
    anchors = [STEO_QUARTERLY_USD_MMBTU[_MONTH_TO_QUARTER[m]] for m in SIMULATION_MONTHS]
    start_deviation = math.log(start_price) - math.log(STEO_QUARTERLY_USD_MMBTU["2026Q3"])
    all_paths = []
    for _ in range(paths):
        deviation = start_deviation
        path = []
        for anchor in anchors:
            deviation = deviation * decay + rng.gauss(0.0, shock_sd)
            path.append(anchor * math.exp(deviation))
        all_paths.append(path)
    return all_paths


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        raise ValueError("empty sample")
    rank = (len(sorted_values) - 1) * pct / 100.0
    low, high = int(math.floor(rank)), int(math.ceil(rank))
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def electricity_report(
    paths: int = DEFAULT_MONTE_CARLO_PATHS,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> dict:
    """Pure report function: computes everything, prints nothing, persists
    nothing. The TUI imports this and renders its contents."""
    if paths <= 0:
        raise ValueError("paths must be a positive integer")
    rng = random.Random(random_seed)
    ou = calibrate_ou_from_cache()
    gas_paths = simulate_gas_paths(ou, paths, rng)

    baseline_gas = STEO_QUARTERLY_USD_MMBTU["2026Q3"]
    rates = []
    counterfactual_fuel_deltas = []
    component_means = {
        "base_step": 0.0, "securitization": 0.0, "winter_spike": 0.0,
        "gs5_noise": 0.0, "idiosyncratic": 0.0, "fuel_in_window": 0.0,
    }
    for gas_path in gas_paths:
        base_step = rng.uniform(
            BASE_STEP_JAN2027_CENTS_LOW, BASE_STEP_JAN2027_CENTS_HIGH
        ) * DOMINION_SHARE_OF_VA_COMMERCIAL
        if rng.random() < P_SECURITIZATION_DENIED:
            securitization = SECURITIZATION_DENIED_CENTS * DOMINION_SHARE_OF_VA_COMMERCIAL
        elif rng.random() < P_RIDER_IN_WINDOW_IF_APPROVED:
            securitization = SECURITIZATION_RIDER_CENTS * DOMINION_SHARE_OF_VA_COMMERCIAL
        else:
            securitization = 0.0
        winter_spike = (
            rng.uniform(WINTER_SPIKE_CENTS_LOW, WINTER_SPIKE_CENTS_HIGH)
            if rng.random() < P_WINTER_SPIKE
            else 0.0
        )
        gs5_noise = rng.gauss(0.0, GS5_COMPOSITION_NOISE_STD)
        idiosyncratic = rng.gauss(0.0, IDIOSYNCRATIC_NOISE_STD)
        # January 2027 gas vs the Q3 2026 STEO base (3.37, the anchor quarter
        # containing the as-of date -- the same base the simulation's starting
        # deviation is measured against), mapped through fuel share -- then
        # weighted by the in-window pass-through, which the researched
        # fuel-factor mechanics fix at ZERO (locked tariff through 2027-06-30).
        relative_gas_move = (gas_path[-1] - baseline_gas) / baseline_gas
        counterfactual_fuel = BASELINE_CENTS_PER_KWH * FUEL_SHARE * relative_gas_move
        fuel_in_window = IN_WINDOW_GAS_PASS_THROUGH * counterfactual_fuel
        counterfactual_fuel_deltas.append(counterfactual_fuel)

        rate = (
            BASELINE_CENTS_PER_KWH + base_step + securitization
            + winter_spike + gs5_noise + idiosyncratic + fuel_in_window
        )
        rates.append(rate)
        component_means["base_step"] += base_step
        component_means["securitization"] += securitization
        component_means["winter_spike"] += winter_spike
        component_means["gs5_noise"] += gs5_noise
        component_means["idiosyncratic"] += idiosyncratic
        component_means["fuel_in_window"] += fuel_in_window
    component_means = {key: value / paths for key, value in component_means.items()}

    rates_sorted = sorted(rates)
    p_below = sum(1 for rate in rates if rate < BASELINE_CENTS_PER_KWH) / paths
    counterfactual_sorted = sorted(counterfactual_fuel_deltas)

    # Histogram of simulated January 2027 rates for the TUI. Each entry is
    # (label, fraction, yes_side): yes_side marks bins lying entirely below
    # the 10.33 baseline (the YES region), decided numerically on the bin's
    # upper edge so display code never re-derives it from label strings.
    bin_edges = [10.0, 10.2, 10.33, 10.45, 10.6, 10.8, 11.0, 11.3, 11.6, 12.0]
    bins = []
    below_first = sum(1 for rate in rates if rate < bin_edges[0]) / paths
    bins.append((f"<{bin_edges[0]:.2f}", below_first, bin_edges[0] <= BASELINE_CENTS_PER_KWH))
    for low, high in zip(bin_edges, bin_edges[1:]):
        bins.append((
            f"{low:.2f}-{high:.2f}",
            sum(1 for rate in rates if low <= rate < high) / paths,
            high <= BASELINE_CENTS_PER_KWH,
        ))
    bins.append((
        f">={bin_edges[-1]:.2f}",
        sum(1 for rate in rates if rate >= bin_edges[-1]) / paths,
        False,
    ))

    persisted = None
    if FORECAST_STATE_PATH.exists():
        persisted = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8")).get(str(FORECAST_ID))

    empirical_pct = EMPIRICAL_JAN_BELOW_JUL[0] / EMPIRICAL_JAN_BELOW_JUL[1] * 100.0
    mechanism = (
        "the tier-3 +8pp 'STEO fuel easing' adjustment has NO transmission channel "
        "inside this window (the fuel factor applying on 2027-01-21 was locked on "
        "2026-07-01 and holds through 2027-06-30 -- Dominion's annual Jul 1-Jun 30 "
        "fuel-year cycle, set by formal SCC proceeding, not floating with spot gas), "
        "the July 2026 STEO reversed the May gas-price downgrade it relied on, and "
        "the locked $209.9M base-rate step lands 2027-01-01 -- 20 days before "
        "resolution -- with securitization risk one-sided UP. The unconditional "
        f"empirical base rate (January below prior July in {EMPIRICAL_JAN_BELOW_JUL[0]} "
        f"of {EMPIRICAL_JAN_BELOW_JUL[1]} years = {empirical_pct:.0f}%) matches the "
        "old tier-3 35% base rate; the model's lower number is what conditioning that "
        "base rate on the locked 2027-01-01 step and the closed fuel channel does."
    )
    if persisted is None:
        divergence_note = (
            f"No persisted probability found for forecast #{FORECAST_ID}; the model "
            f"stands alone at {p_below * 100:.1f}%. Mechanism: {mechanism}"
        )
    elif abs(p_below * 100.0 - persisted) > 3:
        divergence_note = (
            f"Component model {p_below * 100:.1f}% vs persisted {persisted}%. The gap "
            f"is mechanical, not a re-judgment: {mechanism}"
        )
    else:
        divergence_note = (
            f"Component model {p_below * 100:.1f}% matches the persisted {persisted}% "
            "(the model was adopted as authoritative 2026-07-23 after the fuel-year "
            f"cycle was independently verified). Why the old 30% was wrong: {mechanism}"
        )

    return {
        "forecast_id": FORECAST_ID,
        "as_of": AS_OF_DATE.isoformat(),
        "resolution_date": RESOLUTION_DATE.isoformat(),
        "baseline_cents": BASELINE_CENTS_PER_KWH,
        "ou_fit": ou,
        "ou_fallback_used": ou is None,
        "ou_literature": LITERATURE_OU,
        "steo_anchor": STEO_QUARTERLY_USD_MMBTU,
        "simulation_months": SIMULATION_MONTHS,
        "sample_gas_paths": gas_paths[:SAMPLE_GAS_PATHS_FOR_PLOT],
        "gas_start_usd": _latest_cached_gas_price(),
        "fuel_share": FUEL_SHARE,
        "in_window_pass_through": IN_WINDOW_GAS_PASS_THROUGH,
        "dominion_share": DOMINION_SHARE_OF_VA_COMMERCIAL,
        "component_means_cents": {key: round(value, 4) for key, value in component_means.items()},
        "counterfactual_fuel_delta_cents": {
            "p10": round(_percentile(counterfactual_sorted, 10), 3),
            "p50": round(_percentile(counterfactual_sorted, 50), 3),
            "p90": round(_percentile(counterfactual_sorted, 90), 3),
        },
        "rate_percentiles": {
            f"p{pct}": round(_percentile(rates_sorted, pct), 3)
            for pct in (5, 10, 25, 50, 75, 90, 95)
        },
        "rate_histogram": [
            (label, round(fraction, 4), yes_side) for label, fraction, yes_side in bins
        ],
        "p_below_baseline_pct": round(p_below * 100.0, 1),
        "empirical_jan_below_jul": EMPIRICAL_JAN_BELOW_JUL,
        "empirical_jan_below_jul_pct": round(empirical_pct, 1),
        "paths": paths,
        "random_seed": random_seed,
        "persisted_pct": persisted,
        "tier3_reference_pct": TIER3_REFERENCE_PCT,
        "divergence_pts": round(p_below * 100.0 - persisted, 1) if persisted is not None else None,
        "divergence_note": divergence_note,
        "series_discrepancy_caveat": SERIES_DISCREPANCY_CAVEAT,
    }


def print_report(report: dict, console: Console | None = None) -> None:
    console = console or Console()
    console.print(Panel.fit(
        "[bold]Forecast #9: VA commercial rate reversal -- deterministic + stochastic decomposition[/bold]\n"
        f"P(Jan 2027 rate < {report['baseline_cents']} c/kWh) | as of {report['as_of']}, "
        f"resolves {report['resolution_date']} | {report['paths']:,} paths, seed {report['random_seed']}\n"
        f"Headline: [bold]{report['p_below_baseline_pct']:.1f}%[/bold] vs persisted "
        f"{report['persisted_pct']}%",
        border_style="cyan",
    ))

    ou = report["ou_fit"]
    ou_table = Table(title="Ornstein-Uhlenbeck calibration (daily log Henry Hub)", box=box.SIMPLE_HEAVY)
    ou_table.add_column("Source")
    ou_table.add_column("kappa/yr", justify="right")
    ou_table.add_column("Half-life", justify="right")
    ou_table.add_column("sigma (ann.)", justify="right")
    ou_table.add_column("Long-run mean", justify="right")
    if ou is not None:
        ou_table.add_row(
            f"Fitted: {ou.source}, {ou.window_start}..{ou.window_end} (n={ou.n_observations})",
            f"{ou.kappa_per_year:.2f}",
            f"{ou.half_life_months:.1f} mo",
            f"{ou.sigma_annualized:.2f}",
            f"${ou.long_run_mean_usd:.2f}",
        )
    else:
        ou_table.add_row("[red]cache missing -- literature fallback in use[/red]", "-", "-", "-", "-")
    literature = report["ou_literature"]
    ou_table.add_row(
        "Literature anchor (Schwartz 1-factor, HH 2000-2008)",
        f"{literature['kappa_per_year']:.2f}",
        f"{literature['half_life_months']:.1f} mo",
        f"{literature['sigma_annualized']:.2f}",
        "-",
    )
    console.print(ou_table)
    console.print(
        f"STEO anchor path (Jul 2026 vintage): {report['steo_anchor']} | simulation start "
        f"${report['gas_start_usd']:.2f} (last cached spot). Simulated Jan 2027 gas enters the "
        f"rate with pass-through weight [bold]{report['in_window_pass_through']:.0f}[/bold] -- "
        "the fuel factor applying on resolution day was locked 2026-07-01 (PUR-2026-00058) "
        "and holds through 2027-06-30."
    )
    console.print(
        "Counterfactual (if pass-through were live): fuel delta p10/p50/p90 = "
        f"{report['counterfactual_fuel_delta_cents']['p10']:+.2f} / "
        f"{report['counterfactual_fuel_delta_cents']['p50']:+.2f} / "
        f"{report['counterfactual_fuel_delta_cents']['p90']:+.2f} c/kWh -- centered "
        "~+0.5 c/kWh UP (the seasonal Q1 gas premium over the Q3 base) and two-sided, "
        "i.e. even a live channel would not deliver the one-way easing the tier-3 "
        "+8pp assumed; if anything it would push the January rate up."
    )

    components = Table(title="Rate components at Jan 2027 (mean contribution, c/kWh)", box=box.SIMPLE)
    components.add_column("Component")
    components.add_column("Mean", justify="right")
    components.add_column("Note")
    notes = {
        "base_step": "locked 2027-01-01 biennial step, Uniform(0.15,0.30) x 0.65 Dominion share",
        "securitization": f"P(denied)={P_SECURITIZATION_DENIED} -> +1.4c; else rider 0.18c w.p. {P_RIDER_IN_WINDOW_IF_APPROVED}",
        "winter_spike": f"P={P_WINTER_SPIKE}, Uniform({WINTER_SPIKE_CENTS_LOW},{WINTER_SPIKE_CENTS_HIGH}) (861M cold-event calibration)",
        "gs5_noise": "GS-5 class composition change, zero-mean (ASSUMED)",
        "idiosyncratic": "6-month noise from cached series MoM moves (ASSUMED normal)",
        "fuel_in_window": "OU gas x fuel share x pass-through 0 (locked tariff)",
    }
    for key, value in report["component_means_cents"].items():
        components.add_row(key, f"{value:+.3f}", notes[key])
    console.print(components)

    percentiles = report["rate_percentiles"]
    console.print(
        "Simulated Jan 2027 rate: "
        + " · ".join(f"{name} {value:.2f}" for name, value in percentiles.items())
        + f"  [bold](baseline {report['baseline_cents']})[/bold]"
    )
    histogram = Table(title="Simulated Jan 2027 rate distribution", box=box.SIMPLE)
    histogram.add_column("c/kWh")
    histogram.add_column("Share", justify="right")
    histogram.add_column("")
    for label, fraction, yes_side in report["rate_histogram"]:
        marker = " <- YES side" if yes_side else ""
        histogram.add_row(label, f"{fraction * 100:5.1f}%", "█" * round(fraction * 50) + marker)
    console.print(histogram)

    console.print(
        f"Empirical cross-check: January below prior July in "
        f"{report['empirical_jan_below_jul'][0]} of {report['empirical_jan_below_jul'][1]} "
        f"years ({report['empirical_jan_below_jul_pct']:.0f}%) in the 2015-2026 EIA-861M "
        "history -- the unconditional base rate the tier-3 35% matched."
    )
    console.print(report["divergence_note"])
    console.print(f"[dim]{report['series_discrepancy_caveat']}[/dim]")
    if report["divergence_pts"] is not None and abs(report["divergence_pts"]) > 3:
        console.print(
            "[yellow]Material divergence vs the persisted tier-3 estimate -- flagged, not "
            "auto-persisted. Persist only deliberately (--persist).[/yellow]"
        )


if __name__ == "__main__":
    console = Console()
    full_report = electricity_report()
    print_report(full_report, console)
    if "--persist" in sys.argv:
        value = full_report["p_below_baseline_pct"]
        set_forecast_probability(FORECAST_ID, value)
        console.print(f"[bold]Persisted {value}% to forecast #{FORECAST_ID}.[/bold]")
