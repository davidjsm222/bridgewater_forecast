"""
Forecast #3 backlog model: a queueing/throughput view of the US 2027
data-center capacity gap.

The forecast asks whether the share of announced-for-2027 capacity not yet
under construction falls below 30% by 2027-12-31. That gap is a ratio of two
stocks -- the announced pipeline A(t) and the under-construction stock U(t) --
each moved by a flow with a researched range: new announcements (plus
2026-cohort slippage) flow INTO A, while construction starts convert the
backlog A-U into U at a rate hard-capped by physical constraints (5-year
median interconnection queues, 128-160-week transformer lead times, gas
turbines sold out through 2029, a ~500k-worker labor gap). Backlog arithmetic
is therefore the right tool: the question is whether a throughput-limited
conversion flow can outrun a faster inflow for six straight quarters -- a
flow-balance question, not a trend-fit question (the tier-2 fit on n=4
mixed-tracker points was rejected as perverse; see methodology_notes.md #3).

Given the hard caps, the dynamics are nearly deterministic, so the Monte Carlo
here is parameter uncertainty only: each path draws constant inflow and
conversion rates from triangular distributions over the researched ranges.
The honest output is therefore BOTH the deterministic midpoint trajectory with
a p10/p90 band AND P(gap < 30%) counted at resolution. The one documented
non-fanciful YES path that is not a flow acceleration -- an AI-capex pullback
cancelling the announced denominator -- is reported as a labeled stress case,
never blended into the headline number.
"""

import random
import statistics
import sys
from dataclasses import dataclass
from datetime import date

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forecasts import get, set_forecast_probability


FORECAST_ID = 3
AS_OF_DATE = date(2026, 7, 22)   # repo convention, mirrors fomc_history.CURRENT_AS_OF_DATE
DEFAULT_MONTE_CARLO_PATHS = 10_000
DEFAULT_RANDOM_SEED = 20260722
MONTHS_PER_QUARTER = 3
GAP_RESOLUTION_THRESHOLD = 0.30  # resolution bar: gap < 30% at 2027-12-31

# --- Anchor: latest observed (A, U) level reading for the 2027 cohort ----------
# The last reading with explicit GW LEVELS is the April 2026 Sightline snapshot;
# the June 2026 Jefferies ~80% is a ratio-only read (no A/U levels published) and
# is kept as context below, not as the anchor. Simulation therefore steps monthly
# from April 2026 through December 2027 (20 months).
ANCHOR_YEAR_MONTH = (2026, 4)
RESOLUTION_YEAR_MONTH = (2027, 12)
# 25 GW announced for 2027 delivery: Sightline Climate via Network World,
# 2026-04-14, accessed 2026-07-22:
# https://www.networkworld.com/article/4158559/data-centers-are-moving-inland-away-from-some-traditional-locations.html
ANNOUNCED_2027_GW_ANCHOR = 25.0
# 6.3 GW under construction for 2027: Sightline via Bloomberg, Apr 2026, accessed
# 2026-07-22: https://futurism.com/science-energy/data-centers-construction-supply
# (also https://www.zerohedge.com/technology/half-us-data-centers-are-set-be-canceled-or-delayed-2026)
# ASSUMED: the 25.0 denominator (mid-April, quoted with "~6 GW" u/c) is paired
# with the more precise 6.3 numerator (early April, quoted against 21.5 GW).
# Both are April 2026 Sightline reads; the pairing gives anchor gap 74.8%,
# between the two published gaps (70.7% and 76%).
UNDER_CONSTRUCTION_2027_GW_ANCHOR = 6.3

# --- Inflow: announced-for-2027 pipeline growth, GW/quarter --------------------
# Basis (accessed 2026-07-22): 2026 cohort grew 8.9 -> 16 GW Jul 2025 - Feb 2026
# (~3 GW/q; https://www.ctvc.co/the-data-center-report-we-promise-you-havent-read/
# and https://www.currence.ai/blog/data-center-outlook); 2027 cohort read
# 21.5 -> ~25 GW within April 2026 alone; Texas announced 14 GW in Q2 2026
# (Jefferies via
# https://www.theregister.com/on-prem/2026/06/17/only-half-of-us-datacenter-capacity-planned-for-2026-is-actually-under-construction/5257781);
# plus 30-50% of the 2026 cohort slipping into 2027+ adds ~1-3 GW/q
# (https://www.networkworld.com/article/4158559/data-centers-are-moving-inland-away-from-some-traditional-locations.html,
# https://www.latitudemedia.com/news/up-to-half-of-the-worlds-data-centers-may-be-delayed-this-year/).
# The all-year pipeline grew ~50 GW/q (73.6 -> 190 GW Jul 2025 - Feb 2026), so
# 2-6 GW/q into the single 2027 cohort is conservative.
INFLOW_GW_PER_QUARTER_LOW = 2.0
INFLOW_GW_PER_QUARTER_HIGH = 6.0
# ASSUMED: research gave only the 2-6 range; the triangular mode is set at the
# midpoint for lack of a documented central estimate.
INFLOW_GW_PER_QUARTER_MODE = 4.0

# --- Conversion: announced -> under-construction starts, GW/quarter ------------
# Basis (accessed 2026-07-22): tracker-of-record net starts for the 2027 cohort
# ran ~0-1 GW/q (6.3 GW u/c in April per Sightline/Bloomberg,
# https://futurism.com/science-energy/data-centers-construction-supply, vs ~5 GW
# implied by Jefferies' June ~80%-not-started on ~25 GW,
# https://www.theregister.com/on-prem/2026/06/17/only-half-of-us-datacenter-capacity-planned-for-2026-is-actually-under-construction/5257781).
# Cross-tracker upper bound: BNEF logged 3.8 GW/q of global construction starts
# in Q3 2025 with the US ~69% of activity, i.e. ~2.5-3.8 GW/q US-wide across ALL
# delivery-year cohorts
# (https://about.bnef.com/insights/data-centers/ai-data-center-build-advances-at-full-speed-five-things-to-know/).
CONVERSION_GW_PER_QUARTER_LOW = 1.0
CONVERSION_GW_PER_QUARTER_HIGH = 3.0
# ASSUMED: research gave only the 1-3 range; triangular mode at the midpoint.
CONVERSION_GW_PER_QUARTER_MODE = 2.0

# Why conversion is capped at the researched high rather than allowed to
# accelerate (all accessed 2026-07-22):
# - Grid interconnection: median request-to-commercial-operation duration was
#   OVER 5 YEARS for projects built in 2025 (up from >4 years for 2018-24
#   builds), per LBNL Queued Up 2026 Edition (pub. May 2026):
#   https://emp.lbl.gov/sites/default/files/2026-06/Queued%20Up%202026%20Edition.pdf
#   (also https://emp.lbl.gov/queues,
#   https://www.rtoinsider.com/136008-lbnl-interconnection-report-2026-signs-improvement/).
# - Transformers: standard power transformers average ~128-week lead times, GSUs
#   ~144 weeks (https://www.industrialsage.com/power-transformer-lead-times-us-grid-shortage/);
#   substation transformers >160 weeks in 2026 per Wood Mackenzie
#   (https://www.datacenterknowledge.com/build-design/ai-data-center-boom-rewires-us-power-supply-chain);
#   some deliveries run to 5 years vs 24-30 months pre-2020
#   (https://pv-magazine-usa.com/2026/05/11/u-s-transformer-market-faces-severe-supply-constraints-as-lead-times-extend-to-four-years/).
# - Gas turbines: ~3-year lead times, largely sold out through 2029
#   (https://www.techinvestments.io/p/power-bottlenecks-and-the-ai-data;
#   easing only at the margin per
#   https://www.utilitydive.com/news/natural-gas-equipment-generation-bottleneck-data-centers/812931/).
# - Labor: up to ~499k-worker data-center construction shortfall
#   (https://www.irecruit.co/insights/data-center-construction-labor-market-report);
#   300k+ electricians needed against ~20k retiring/year
#   (https://www.rinvio.com/blog/electrician-shortage-data-center-boom;
#   https://introl.com/blog/data-center-workforce-shortage-340000-unfilled-positions-2026).
# Equipment ordered today lands after the resolution date, so within-horizon
# conversion cannot exceed what is already in flight -- the researched 1-3 GW/q.
# The cap min(conversion, A - U) additionally prevents converting more than the
# remaining backlog.

# --- Pullback stress case (documented judgment, NOT blended into headline) -----
# ASSUMED: methodology_notes.md #3 identifies exactly one non-fanciful YES path:
# a large AI-capex pullback shrinking the ANNOUNCED denominator. Modeled as the
# inflow reversed -- pipeline cancellations at 2x the high inflow rate
# (2 x 6 = 12 GW/q of cancellations, zero new announcements), conversion held at
# its midpoint. Cancellations remove only not-yet-started backlog (A is floored
# at U: a project already under construction leaves the gap numerator either
# way, and this floor is the conservative choice for the stress narrative).
PULLBACK_CANCELLATION_MULTIPLIER = 2.0
PULLBACK_CANCELLATION_GW_PER_QUARTER = (
    PULLBACK_CANCELLATION_MULTIPLIER * INFLOW_GW_PER_QUARTER_HIGH
)


@dataclass(frozen=True)
class GapReading:
    """A published gap observation, kept as context around the anchor."""
    reading_date: str
    gap_pct: float
    metric: str
    tracker: str
    source_url: str


# The reported-gap record (all accessed 2026-07-22). The 2027-cohort series is
# n=2 and mixed-tracker -- the reason the trend fit was rejected and this model
# works from flows instead of fitting these points.
GAP_READINGS = (
    GapReading("2026-02", 68.75, "2026 cohort: 16 GW slated, ~5 GW under construction",
               "Sightline Climate Q1 2026 Data Center Outlook (pub. 2026-02-24)",
               "https://www.currence.ai/blog/data-center-outlook"),
    GapReading("2026-04", 67.0, "2026 cohort: 12 GW expected online, ~4 GW under active construction",
               "Sightline Climate via Bloomberg (2026-04-03)",
               "https://finance.yahoo.com/sectors/technology/articles/half-planned-us-data-center-150928890.html"),
    GapReading("2026-04", 70.7, "2027 cohort: 21.5 GW announced, 6.3 GW under construction",
               "Sightline Climate via Bloomberg",
               "https://futurism.com/science-energy/data-centers-construction-supply"),
    GapReading("2026-04", 76.0, "2027 cohort: 25 GW announced, ~6 GW under construction",
               "Sightline Climate via Network World (2026-04-14)",
               "https://www.networkworld.com/article/4158559/data-centers-are-moving-inland-away-from-some-traditional-locations.html"),
    GapReading("2026-06", 80.0, "2027/28 cohort: ~80% of planned capacity not yet in substantial construction",
               "Jefferies via The Register (2026-06-17)",
               "https://www.theregister.com/on-prem/2026/06/17/only-half-of-us-datacenter-capacity-planned-for-2026-is-actually-under-construction/5257781"),
)


@dataclass(frozen=True)
class BacklogTrajectoryPoint:
    month: str                    # "YYYY-MM", end-of-month state
    announced_gw: float
    under_construction_gw: float
    gap_pct: float


@dataclass(frozen=True)
class BacklogSimulationResult:
    paths: int
    months: tuple[str, ...]
    gap_p10_pct: tuple[float, ...]
    gap_median_pct: tuple[float, ...]
    gap_p90_pct: tuple[float, ...]
    p_below_30: float             # share of paths with gap < 30% at resolution
    random_seed: int | None


def _simulation_months() -> tuple[str, ...]:
    """Month labels from the first step after the anchor through resolution."""
    months = []
    year, month = ANCHOR_YEAR_MONTH
    while (year, month) < RESOLUTION_YEAR_MONTH:
        month += 1
        if month > 12:
            year, month = year + 1, 1
        months.append(f"{year:04d}-{month:02d}")
    return tuple(months)


def simulate_backlog_path(
    inflow_gw_per_month: float,
    conversion_gw_per_month: float,
    cancellation_gw_per_month: float = 0.0,
) -> tuple[BacklogTrajectoryPoint, ...]:
    """One deterministic path of the backlog dynamics at fixed monthly rates.

    Each month: inflow adds to A; cancellations (stress case only) remove
    not-yet-started backlog, flooring A at U; conversion moves
    min(rate, A - U) from backlog into U. gap = 1 - U/A.
    """
    announced = ANNOUNCED_2027_GW_ANCHOR
    under_construction = UNDER_CONSTRUCTION_2027_GW_ANCHOR
    points = []
    for month in _simulation_months():
        announced += inflow_gw_per_month
        announced -= min(cancellation_gw_per_month, announced - under_construction)
        under_construction += min(conversion_gw_per_month, announced - under_construction)
        points.append(BacklogTrajectoryPoint(
            month=month,
            announced_gw=round(announced, 2),
            under_construction_gw=round(under_construction, 2),
            gap_pct=round((1.0 - under_construction / announced) * 100, 1),
        ))
    return tuple(points)


def monte_carlo_gap(
    paths: int = DEFAULT_MONTE_CARLO_PATHS,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> BacklogSimulationResult:
    """Monte Carlo over parameter uncertainty only.

    Each path draws one constant inflow rate and one constant conversion rate
    from triangular distributions over the researched ranges, then runs the
    same deterministic dynamics as ``simulate_backlog_path``. There is no
    month-to-month noise: given the hard physical caps, the honest uncertainty
    is in the rates, not the mechanics.
    """
    if paths < 2:
        raise ValueError("paths must be at least 2 (quantiles need >= 2 samples)")
    rng = random.Random(random_seed)
    months = _simulation_months()
    gaps_by_month: list[list[float]] = [[] for _ in months]
    below_at_resolution = 0

    for _ in range(paths):
        inflow = rng.triangular(
            INFLOW_GW_PER_QUARTER_LOW, INFLOW_GW_PER_QUARTER_HIGH,
            INFLOW_GW_PER_QUARTER_MODE,
        ) / MONTHS_PER_QUARTER
        conversion = rng.triangular(
            CONVERSION_GW_PER_QUARTER_LOW, CONVERSION_GW_PER_QUARTER_HIGH,
            CONVERSION_GW_PER_QUARTER_MODE,
        ) / MONTHS_PER_QUARTER
        announced = ANNOUNCED_2027_GW_ANCHOR
        under_construction = UNDER_CONSTRUCTION_2027_GW_ANCHOR
        gap = 1.0
        for month_gaps in gaps_by_month:
            announced += inflow
            under_construction += min(conversion, announced - under_construction)
            gap = 1.0 - under_construction / announced
            month_gaps.append(gap)
        if gap < GAP_RESOLUTION_THRESHOLD:
            below_at_resolution += 1

    p10, median, p90 = [], [], []
    for month_gaps in gaps_by_month:
        deciles = statistics.quantiles(month_gaps, n=10, method="inclusive")
        p10.append(round(deciles[0] * 100, 1))
        median.append(round(deciles[4] * 100, 1))
        p90.append(round(deciles[8] * 100, 1))
    return BacklogSimulationResult(
        paths=paths,
        months=months,
        gap_p10_pct=tuple(p10),
        gap_median_pct=tuple(median),
        gap_p90_pct=tuple(p90),
        p_below_30=below_at_resolution / paths,
        random_seed=random_seed,
    )


# --- Explicit tail-risk terms (added 2026-07-23) ---------------------------
# The flow model's structural ~0% headline deliberately excludes two non-flow
# YES channels, previously carried by an unmodeled judgment floor of 4.0. They
# are now explicit discrete-scenario terms, so the persisted number is a fully
# modeled quantity with named components instead of a judgment patch:
#
# 1. Capex-pullback denominator collapse. Anchored to forecast #4's own model
#    rather than assumed cold: P(AI capex disappoints Bridgewater's central
#    estimate) = 1 - the #4 Bayesian posterior (bayesian_update.BAYES_UPDATES,
#    ~43.5%) -- a live cross-model link, recomputed at import. Conditional
#    share of disappointment scenarios that take the form of LARGE
#    CANCELLATIONS of already-announced 2027-cohort capacity (rather than
#    slower new announcements, which the flow model's 2-6 GW/q inflow range
#    already spans): ASSUMED 0.12 -- announced-project cancellations are the
#    historically rarer form of capex disappointment (the 2001 telecom and
#    2022 crypto-datacenter busts cancelled builds only under financing
#    stress, not mere growth slowdown). P(reported gap < 30% | large
#    cancellations): ASSUMED 0.5, between the stress case (a full-scale
#    pullback resolves YES within ~4 months) and partial-pullback paths that
#    stall above the bar.
PULLBACK_CANCELLATION_SHARE_GIVEN_CAPEX_MISS = 0.12
P_GAP_BELOW_30_GIVEN_PULLBACK = 0.5
# 2. Tracker/methodology switch. SemiAnalysis publicly argues Sightline's
#    under-construction numerator undercounts by multiples
#    (https://newsletter.semianalysis.com/p/stop-saying-half-of-2026-us-datacenter,
#    accessed 2026-07-22), and the resolution criteria accept DC Byte/CBRE/JLL
#    as sources. ASSUMED 0.10 = P(the resolution-relevant tracker's
#    construction counting shifts materially toward the higher methodology by
#    end-2027); ASSUMED 0.3 = P(its reported gap lands < 30% | such a shift)
#    -- even a 2-3x numerator restatement of the Apr 2026 anchor (6.3 GW ->
#    12.6-18.9 GW of 25 GW) puts the measured gap at ~25-50%, straddling the
#    bar.
P_TRACKER_METHOD_SHIFT = 0.10
P_GAP_BELOW_30_GIVEN_SHIFT = 0.3


def tail_risk_terms() -> dict:
    """The two modeled non-flow YES channels; see the constants above."""
    from bayesian_update import BAYES_UPDATES  # deferred: keeps import graph flat
    p_capex_miss = 1.0 - BAYES_UPDATES[4].posterior_pct() / 100.0
    p_pullback_yes = (
        p_capex_miss
        * PULLBACK_CANCELLATION_SHARE_GIVEN_CAPEX_MISS
        * P_GAP_BELOW_30_GIVEN_PULLBACK
    )
    p_tracker_yes = P_TRACKER_METHOD_SHIFT * P_GAP_BELOW_30_GIVEN_SHIFT
    return {
        "p_capex_miss": round(p_capex_miss, 4),
        "p_capex_miss_source": "1 - forecast #4 Bayesian posterior (bayesian_update.py, live link)",
        "cancellation_share_given_miss": PULLBACK_CANCELLATION_SHARE_GIVEN_CAPEX_MISS,
        "p_gap_below_30_given_pullback": P_GAP_BELOW_30_GIVEN_PULLBACK,
        "p_pullback_yes": round(p_pullback_yes, 4),
        "p_tracker_method_shift": P_TRACKER_METHOD_SHIFT,
        "p_gap_below_30_given_shift": P_GAP_BELOW_30_GIVEN_SHIFT,
        "p_tracker_yes": round(p_tracker_yes, 4),
    }


def datacenter_backlog_report(
    paths: int = DEFAULT_MONTE_CARLO_PATHS,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> dict:
    """Everything the TUI needs to render the backlog model for forecast #3."""
    simulation = monte_carlo_gap(paths=paths, random_seed=random_seed)
    midpoint = simulate_backlog_path(
        INFLOW_GW_PER_QUARTER_MODE / MONTHS_PER_QUARTER,
        CONVERSION_GW_PER_QUARTER_MODE / MONTHS_PER_QUARTER,
    )
    # Structural diagnostic: the single most YES-favorable corner of the
    # researched flow box (slowest inflow, fastest conversion, both held for
    # all 20 months). If even this corner cannot reach 30%, no blend of
    # researched flow rates can, and the Monte Carlo zero is structural.
    best_corner = simulate_backlog_path(
        INFLOW_GW_PER_QUARTER_LOW / MONTHS_PER_QUARTER,
        CONVERSION_GW_PER_QUARTER_HIGH / MONTHS_PER_QUARTER,
    )
    stress = simulate_backlog_path(
        0.0,
        CONVERSION_GW_PER_QUARTER_MODE / MONTHS_PER_QUARTER,
        cancellation_gw_per_month=PULLBACK_CANCELLATION_GW_PER_QUARTER / MONTHS_PER_QUARTER,
    )
    stress_first_below = next(
        (p.month for p in stress if p.gap_pct < GAP_RESOLUTION_THRESHOLD * 100), None
    )

    anchor_gap_pct = round(
        (1.0 - UNDER_CONSTRUCTION_2027_GW_ANCHOR / ANNOUNCED_2027_GW_ANCHOR) * 100, 1
    )
    p_below_30_pct = round(simulation.p_below_30 * 100, 1)
    persisted_pct = get(FORECAST_ID).probability

    # Combined headline: flow channel + the two modeled tail-risk channels,
    # treated as independent (documented simplification -- a capex bust and a
    # tracker-methodology shift have no obvious common cause inside the
    # window). This replaces the old unmodeled 4.0 judgment floor.
    tail = tail_risk_terms()
    combined_p_yes = 1.0 - (
        (1.0 - simulation.p_below_30)
        * (1.0 - tail["p_pullback_yes"])
        * (1.0 - tail["p_tracker_yes"])
    )
    combined_p_yes_pct = round(combined_p_yes * 100, 1)

    divergence_note = (
        f"Flow channel alone: {p_below_30_pct}% -- structural, not a sampling "
        f"artifact (even the most YES-favorable corner of the researched flow box, "
        f"inflow {INFLOW_GW_PER_QUARTER_LOW} / conversion "
        f"{CONVERSION_GW_PER_QUARTER_HIGH} GW/q for all 20 months, ends 2027 at "
        f"{best_corner[-1].gap_pct}%). The two non-flow YES channels are now "
        f"modeled explicitly instead of carried as a judgment floor: "
        f"capex-pullback denominator collapse "
        f"{tail['p_pullback_yes'] * 100:.1f}% (= {tail['p_capex_miss'] * 100:.1f}% "
        f"P(capex miss, from forecast #4's posterior) x "
        f"{tail['cancellation_share_given_miss']} cancellation share x "
        f"{tail['p_gap_below_30_given_pullback']} conditional) and "
        f"tracker-methodology shift {tail['p_tracker_yes'] * 100:.1f}% "
        f"(= {tail['p_tracker_method_shift']} x {tail['p_gap_below_30_given_shift']}). "
        f"Combined headline {combined_p_yes_pct}% vs previously persisted "
        f"{persisted_pct}% -- every component is named, sourced or explicitly "
        f"ASSUMED, and adjustable."
    )

    return {
        "forecast_id": FORECAST_ID,
        "as_of": AS_OF_DATE.isoformat(),
        "anchor": {
            "date": f"{ANCHOR_YEAR_MONTH[0]:04d}-{ANCHOR_YEAR_MONTH[1]:02d}",
            "announced_gw": ANNOUNCED_2027_GW_ANCHOR,
            "under_construction_gw": UNDER_CONSTRUCTION_2027_GW_ANCHOR,
            "gap_pct": anchor_gap_pct,
            "sources": [
                "https://www.networkworld.com/article/4158559/data-centers-are-moving-inland-away-from-some-traditional-locations.html",
                "https://futurism.com/science-energy/data-centers-construction-supply",
            ],
        },
        "inflow_gw_per_quarter": {
            "low": INFLOW_GW_PER_QUARTER_LOW,
            "mode": INFLOW_GW_PER_QUARTER_MODE,
            "high": INFLOW_GW_PER_QUARTER_HIGH,
            "basis": "New 2027-cohort announcements ~2-3 GW/q plus 2026-cohort slippage ~1-3 GW/q",
            "sources": [
                "https://www.ctvc.co/the-data-center-report-we-promise-you-havent-read/",
                "https://www.currence.ai/blog/data-center-outlook",
                "https://www.networkworld.com/article/4158559/data-centers-are-moving-inland-away-from-some-traditional-locations.html",
            ],
        },
        "conversion_gw_per_quarter": {
            "low": CONVERSION_GW_PER_QUARTER_LOW,
            "mode": CONVERSION_GW_PER_QUARTER_MODE,
            "high": CONVERSION_GW_PER_QUARTER_HIGH,
            "basis": "Tracker-of-record 2027-cohort net starts ~0-1 GW/q; BNEF cross-tracker US-wide ~2.5-3.8 GW/q across all cohorts",
            "sources": [
                "https://futurism.com/science-energy/data-centers-construction-supply",
                "https://about.bnef.com/insights/data-centers/ai-data-center-build-advances-at-full-speed-five-things-to-know/",
            ],
        },
        "conversion_cap_constraints": {
            "interconnection": ">5-year median request-to-operation for 2025-built projects (LBNL Queued Up 2026)",
            "transformers": "~128-160-week lead times, some to 5 years (IndustrialSage / Wood Mackenzie)",
            "gas_turbines": "~3-year leads, largely sold out through 2029",
            "labor": "up to ~499k-worker construction shortfall; 300k+ electricians needed",
            "sources": [
                "https://emp.lbl.gov/sites/default/files/2026-06/Queued%20Up%202026%20Edition.pdf",
                "https://www.industrialsage.com/power-transformer-lead-times-us-grid-shortage/",
                "https://www.datacenterknowledge.com/build-design/ai-data-center-boom-rewires-us-power-supply-chain",
                "https://www.techinvestments.io/p/power-bottlenecks-and-the-ai-data",
                "https://www.irecruit.co/insights/data-center-construction-labor-market-report",
            ],
        },
        "gap_readings": [
            {"date": r.reading_date, "gap_pct": r.gap_pct, "metric": r.metric,
             "tracker": r.tracker, "source_url": r.source_url}
            for r in GAP_READINGS
        ],
        "paths": simulation.paths,
        "random_seed": simulation.random_seed,
        "trajectory": [
            {
                "month": month,
                "midpoint_announced_gw": mid.announced_gw,
                "midpoint_under_construction_gw": mid.under_construction_gw,
                "midpoint_gap_pct": mid.gap_pct,
                "mc_gap_p10_pct": p10,
                "mc_gap_median_pct": med,
                "mc_gap_p90_pct": p90,
                "stress_gap_pct": stress_point.gap_pct,
            }
            for month, mid, p10, med, p90, stress_point in zip(
                simulation.months, midpoint, simulation.gap_p10_pct,
                simulation.gap_median_pct, simulation.gap_p90_pct, stress,
            )
        ],
        "p_below_30_pct": p_below_30_pct,
        "tail_risk": tail,
        "combined_p_yes_pct": combined_p_yes_pct,
        "midpoint_end_2027_gap_pct": midpoint[-1].gap_pct,
        "best_flow_corner_end_2027_gap_pct": best_corner[-1].gap_pct,
        "stress_case": {
            "label": "AI-capex pullback (denominator collapse) -- NOT in headline",
            "cancellation_gw_per_quarter": PULLBACK_CANCELLATION_GW_PER_QUARTER,
            "conversion_gw_per_quarter": CONVERSION_GW_PER_QUARTER_MODE,
            "end_2027_gap_pct": stress[-1].gap_pct,
            "first_month_below_30": stress_first_below,
        },
        "persisted_pct": persisted_pct,
        "divergence_note": divergence_note,
    }


def print_report(report: dict, console: Console | None = None) -> None:
    """Render the backlog model report with rich."""
    console = console or Console()
    forecast = get(FORECAST_ID)
    anchor = report["anchor"]
    inflow = report["inflow_gw_per_quarter"]
    conversion = report["conversion_gw_per_quarter"]
    console.print(Panel.fit(
        f"[bold]Forecast #{FORECAST_ID}: {forecast.title} -- backlog throughput model[/bold]\n"
        f"Anchor {anchor['date']}: {anchor['announced_gw']:.1f} GW announced / "
        f"{anchor['under_construction_gw']:.1f} GW under construction "
        f"(gap {anchor['gap_pct']:.1f}%) | resolution: gap < 30% by 2027-12-31\n"
        f"Inflow {inflow['low']:.0f}-{inflow['high']:.0f} GW/q (mode {inflow['mode']:.0f}, ASSUMED midpoint) | "
        f"conversion {conversion['low']:.0f}-{conversion['high']:.0f} GW/q (mode {conversion['mode']:.0f}, "
        f"ASSUMED midpoint), capped at remaining backlog\n"
        f"Monte Carlo: {report['paths']:,} paths (parameter uncertainty only), "
        f"seed {report['random_seed']} | P(gap < 30%) = [bold]{report['p_below_30_pct']:.1f}%[/bold]",
        border_style="cyan",
    ))

    table = Table(
        title="Monthly gap trajectory: deterministic midpoint, MC band, pullback stress",
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Month")
    table.add_column("A (GW)", justify="right")
    table.add_column("U (GW)", justify="right")
    table.add_column("Midpoint gap", justify="right")
    table.add_column("p10", justify="right")
    table.add_column("Median", justify="right")
    table.add_column("p90", justify="right")
    table.add_column("Stress gap", justify="right")
    for row in report["trajectory"]:
        table.add_row(
            row["month"],
            f"{row['midpoint_announced_gw']:.1f}",
            f"{row['midpoint_under_construction_gw']:.1f}",
            f"{row['midpoint_gap_pct']:.1f}%",
            f"{row['mc_gap_p10_pct']:.1f}%",
            f"{row['mc_gap_median_pct']:.1f}%",
            f"{row['mc_gap_p90_pct']:.1f}%",
            f"{row['stress_gap_pct']:.1f}%",
        )
    console.print(table)

    console.print(
        f"Deterministic midpoint end-2027 gap: [bold]{report['midpoint_end_2027_gap_pct']:.1f}%[/bold] "
        f"(band {report['trajectory'][-1]['mc_gap_p10_pct']:.1f}-"
        f"{report['trajectory'][-1]['mc_gap_p90_pct']:.1f}%) vs the 30% bar. "
        f"Best researched flow corner (inflow {inflow['low']:.0f}, conversion "
        f"{conversion['high']:.0f} GW/q, 20 straight months): "
        f"[bold]{report['best_flow_corner_end_2027_gap_pct']:.1f}%[/bold] -- the researched "
        f"flow box cannot reach 30%, so the Monte Carlo zero is structural."
    )
    constraints = report["conversion_cap_constraints"]
    console.print(
        "[dim]Conversion cap held through 2027 by: interconnection "
        f"({constraints['interconnection']}); transformers ({constraints['transformers']}); "
        f"gas turbines ({constraints['gas_turbines']}); labor ({constraints['labor']}).[/dim]"
    )
    stress = report["stress_case"]
    console.print(
        f"[yellow]Stress case ({stress['label']}): cancellations at "
        f"{stress['cancellation_gw_per_quarter']:.0f} GW/q shrink the denominator onto the "
        f"under-construction stock -- gap first below 30% in {stress['first_month_below_30']}, "
        f"end-2027 gap {stress['end_2027_gap_pct']:.1f}%. The one non-fanciful YES path is a "
        f"capex pullback, not faster construction.[/yellow]"
    )
    tail = report["tail_risk"]
    console.print(
        f"[bold]Tail-risk channels (modeled 2026-07-23, replacing the old 4.0 judgment "
        f"floor):[/bold] capex-pullback {tail['p_pullback_yes'] * 100:.1f}% "
        f"(P(capex miss) {tail['p_capex_miss'] * 100:.1f}% from forecast #4's Bayesian "
        f"posterior x {tail['cancellation_share_given_miss']} cancellation share "
        f"[ASSUMED] x {tail['p_gap_below_30_given_pullback']} conditional [ASSUMED]) + "
        f"tracker-methodology shift {tail['p_tracker_yes'] * 100:.1f}% "
        f"({tail['p_tracker_method_shift']} x {tail['p_gap_below_30_given_shift']}, both "
        f"ASSUMED, SemiAnalysis-critique grounded)."
    )
    console.print(
        f"Combined headline P(YES) = flow + tail channels = "
        f"[bold]{report['combined_p_yes_pct']:.1f}%[/bold] vs currently persisted "
        f"[bold]{report['persisted_pct']}%[/bold]."
    )
    console.print(f"[dim]{report['divergence_note']}[/dim]")


if __name__ == "__main__":
    report = datacenter_backlog_report()
    print_report(report)
    if "--persist" in sys.argv:
        # Persists the COMBINED headline (flow + modeled tail-risk channels) --
        # a fully modeled quantity with named components, replacing the old
        # unmodeled 4.0 judgment floor.
        set_forecast_probability(FORECAST_ID, round(report["combined_p_yes_pct"], 1))
        Console().print(
            f"[bold]Persisted {round(report['combined_p_yes_pct'], 1)}% to forecast "
            f"#{FORECAST_ID}.[/bold]"
        )
