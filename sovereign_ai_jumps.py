"""
Compound Poisson jump model for forecast #7: sovereign AI funding vs. $250B.

Forecast #7 asks whether strict-scope public commitments to non-US, non-China
sovereign AI compute/chip infrastructure cross $250B cumulative by 2026-12-31,
from a ~$90B base today. The persisted 14% is a tier 3 pace argument: a
run-rate base rate plus judgment adjustments. This module rebuilds the same
question as the stochastic process the resolution quantity literally is.
Sovereign commitments are discrete, lumpy, government-sized events: they
arrive a few times a year, and each lands with a size spanning two orders of
magnitude ($0.7B UK fund to $22.6B Gulf attribution). That is a textbook
compound Poisson process -- arrivals at a rate fitted to the ten dated
commitments observed since the category's first event (IndiaAI, 2024-03-07),
jump sizes drawn from a heavy-tailed distribution fitted to the ten real
historical sizes. Monte Carlo then answers directly: in what fraction of
simulated futures does the cumulative total cross $250B in the 162 days left?

Why this is the right tool: the resolution quantity IS a cumulative sum of
discrete jumps, so simulating it as one honors the mechanism instead of
flattening it into a smooth annual pace. A stationary process fitted to the
observed regime cannot invent a step change, which is a real limitation, not a
verdict -- so the HEADLINE is variant (d), a two-state REGIME-SWITCHING
extension (the same structural move as forecast #5's posture-switching HMM):
the organic fitted process until a Stargate-class trigger arrives (rate fitted
to the one observed trigger, uncertainty propagated via its Jeffreys
posterior), then -- after the empirically observed ~3-week response latency --
a burst regime whose arrival rate is the maximum pace actually observed in
this category and whose size scale is bounded by the largest packages in live
reporting. Variants (a)-(c) remain as the stationary fit, the
rate-uncertainty check, and the cruder labeled stress case; the regime model
is what replaces the old judgment 14% with a modeled quantity whose
step-change component is explicit and adjustable.
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

from forecasts import get, set_forecast_probability


FORECAST_ID = 7

# Repo convention (mirrors fomc_history.CURRENT_AS_OF_DATE): model math never
# calls datetime.now(); every run must be reproducible.
AS_OF_DATE = date(2026, 7, 22)
RESOLUTION_DATE = date(2026, 12, 31)   # forecasts.py forecast #7 resolution date
DAYS_PER_YEAR = 365.2425
HORIZON_DAYS = (RESOLUTION_DATE - AS_OF_DATE).days   # 162 days remaining
HORIZON_YEARS = HORIZON_DAYS / DAYS_PER_YEAR

THRESHOLD_USD_BILLIONS = 250.0   # resolution threshold, forecasts.py #7

# Strict-scope cumulative base at AS_OF_DATE. The itemized commitment history
# below sums to $81.4B; the 2026-07-22 research pass reconciles the full
# strict tally to ~$83.8B (FX-conservative) and surfaces verified
# non-itemized adds: Taiwan Executive Yuan "AI New Ten Major Infrastructure
# Projects" ~$4-6B (2025-08-28,
# https://www.taiwan-healthcare.org/en/news-detail?id=0t1qdtsklt21y3u9,
# accessed 2026-07-22) and the UK GBP1.1B AI hardware plan ~$1.5B (2026-06-08,
# https://www.gov.uk/government/news/a-decisive-shift-to-power-british-ai-new-11-billion-plan-to-back-chip-firms-boost-computing-power-and-skills-for-the-ai-revolution,
# accessed 2026-07-22).
# ASSUMED: adopt $90B, the top of the documented ~$85-90B band
# (methodology_notes.md #7), because the verified misses roughly offset the
# FX trims and the Saudi $9.1B misclassification risk inside the Gulf line.
CURRENT_BASE_USD_BILLIONS = 90.0
BASE_UNCERTAINTY_NOTE = (
    "Base $90B = top of the documented ~$85-90B strict-scope band; itemized "
    "history sums to $81.4B, research-verified tally ~$83.8B, plus "
    "non-itemized Taiwan (~$4-6B) and UK Jun-2026 (~$1.5B) adds. Honest band "
    "~$80-95B, dominated by the Gulf $20-30B domestic-SWF attribution."
)

DEFAULT_MONTE_CARLO_PATHS = 10_000
DEFAULT_RANDOM_SEED = 20260722   # deterministic; mirrors tier1_market convention

# ASSUMED: variant (c) stress parameters. They encode the arms-race
# step-change the tier-3 +7pp "geopolitical momentum" factor argued for
# (methodology_notes.md #7): commitment announcements come twice as often AND
# run 1.5x larger (a China-response package, new EU "AI continent" money,
# fresh Gulf pledges). These multipliers are a documented judgment stress
# case, NOT fitted to any data, and variant (c) is never blended into the
# headline.
ACCELERATION_RATE_MULTIPLIER = 2.0
ACCELERATION_SIZE_MULTIPLIER = 1.5

# --- Regime-switching extension (added 2026-07-23) --------------------------
# A stationary compound Poisson is structurally blind to regime change: it can
# only extrapolate the fitted arrival rate and jump sizes, so it cannot
# represent the coordinated "arms-race burst" world the tier-3 +7pp factor
# argued for. Variant (d) models that world explicitly as a two-state regime
# switch (same structural move as forecast #5's posture-switching HMM), with
# every parameter grounded in the observed record or explicitly ASSUMED:
#
# TRIGGER: Stargate-class escalations -- events that provably set off
# coordinated sovereign responses -- arrived exactly once in the 2.374-yr
# observation window (Stargate, announced 2025-01-21). MLE 0.42/yr; the huge
# n=1 estimation uncertainty is carried by drawing the trigger rate per path
# from its Jeffreys posterior Gamma(1 + 0.5, rate T), the same machinery as
# variant (b). Named live catalysts consistent with a future trigger
# (methodology_notes.md #7): a China-response package, new EU "AI continent"
# money, fresh Gulf domestic pledges.
TRIGGER_EVENTS_OBSERVED = 1
# RESPONSE LATENCY: how fast headline public commitments followed Stargate --
# Bpifrance EUR10B in 17 days (2025-02-07), EU InvestAI EUR20B in 21 days
# (2025-02-11, Paris AI Action Summit). 21 days used; a burst triggered later
# than ~mid-December therefore cannot land before resolution.
# https://techcrunch.com/2025/02/07/bpifrance-to-invest-10b-in-french-ai-ecosystem-by-2029 (accessed 2026-07-22)
# https://ec.europa.eu/commission/presscorner/detail/en/ip_25_467 (accessed 2026-07-22)
RESPONSE_LATENCY_DAYS = 21
# REGIME B ARRIVAL RATE: the maximum ~90-day arrival pace actually OBSERVED in
# the commitment history -- 3 commitments in the 2025-11-22..2025-12-26 window
# (Japan JPY1T, Korea 2026 budget, Japan FY26 budget), ~12/yr annualized.
REGIME_B_RATE_PER_YEAR = 12.0
# REGIME B SIZE MULTIPLIER, drawn per path from Uniform(low, high):
#   low = 1.0: burst commitments drawn from the ordinary size distribution --
#   the observed Feb-2025 post-Stargate burst was exactly that (the two
#   largest historical jumps, $21B and $10.5B, ordinary-scale sizes arriving
#   fast);
#   high = 3.5: ASSUMED ceiling, anchored to the largest concrete packages in
#   live reporting: the EU gigafactory member-state co-funding obligation
#   (Council Regulation (EU) 2026/150 requires member states to at least
#   match the 17% Union share of the EUR 37B ten-facility program => ~EUR
#   15-17B ~ $16-18B of new public money if finalized) and the top of the
#   Gulf domestic-SWF band (~$30B). At 3.5x, the single-jump p95 is ~$100B --
#   already beyond anything any government has floated even informally, so
#   mass above that would be fantasy, not tail risk.
# https://commission.europa.eu/topics/competitiveness/competitiveness-coordination-tool-projects/ai-gigafactories_en (accessed 2026-07-23)
# https://www.datacenterdynamics.com/en/news/eu-allocates-20bn-to-developing-four-ai-gigafactories/ (accessed 2026-07-23)
REGIME_B_SIZE_MULTIPLIER_LOW = 1.0
REGIME_B_SIZE_MULTIPLIER_HIGH = 3.5

# Burnham & Anderson (2002) model-selection convention: delta-AIC < ~4 means
# the trailing model still has substantial support, i.e. it is NOT clearly
# beaten. Used only to phrase the fit-check verdict, never to switch silently.
CLEARLY_BEATEN_AIC_DELTA = 4.0

FORECAST_STATE_PATH = Path(__file__).with_name("forecast_state.json")

# ~12 bins covering the realistic year-end range. A path with zero new
# commitments sits exactly at the $90B base (its own bin); bins at >= $250B
# are the YES region.
HISTOGRAM_BIN_EDGES = (90.0, 100.0, 110.0, 120.0, 135.0, 150.0, 175.0, 200.0, 225.0, 250.0, 300.0)


@dataclass(frozen=True)
class SovereignCommitment:
    """One dated strict-scope public commitment (the jump history)."""

    announced: str          # ISO date of the commitment/announcement
    jurisdiction: str
    usd_billions: float     # strict-scope public-seed USD attribution
    source_url: str         # primary source, accessed 2026-07-22
    note: str


# Dated strict-scope commitment history, 2024-03-07 -> AS_OF_DATE, from the
# 2026-07-22 research verification pass of the methodology_notes.md #7 tally.
# All source URLs accessed 2026-07-22. Known blemishes are carried in notes,
# not hidden: the Gulf row is a band-anchored attribution, and the UK
# 2026-04-16 row has minor double-count risk with the 2025-06-11 envelope.
COMMITMENT_HISTORY: tuple[SovereignCommitment, ...] = (
    # India: window_start -- the earliest commitment in the strict tally.
    SovereignCommitment(
        announced="2024-03-07",
        jurisdiction="India",
        usd_billions=1.25,
        source_url="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2012375&reg=3&lang=2",
        note="Union Cabinet approves IndiaAI Mission, Rs 10,371.92 crore over 5 years",
    ),
    # Canada: C$2B from Budget 2024 treated at USD FX, not par.
    SovereignCommitment(
        announced="2024-12-05",
        jurisdiction="Canada",
        usd_billions=1.45,
        source_url="https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy",
        note="Sovereign AI Compute Strategy launch; C$2B earmarked in Budget 2024 (~US$1.45B)",
    ),
    # France: public portion only; the EUR109B summit headline is excluded.
    SovereignCommitment(
        announced="2025-02-07",
        jurisdiction="France",
        usd_billions=10.5,
        source_url="https://techcrunch.com/2025/02/07/bpifrance-to-invest-10b-in-french-ai-ecosystem-by-2029",
        note="Bpifrance EUR10B by 2029 (public seed of the Feb 2025 summit package)",
    ),
    # EU: public seed only; the EUR200B mobilized figure is excluded.
    SovereignCommitment(
        announced="2025-02-11",
        jurisdiction="EU",
        usd_billions=21.0,
        source_url="https://ec.europa.eu/commission/presscorner/detail/en/ip_25_467",
        note="InvestAI EUR20B public seed for 4-5 AI gigafactories (Paris AI Action Summit)",
    ),
    # Gulf: the loosest row -- a $20-30B domestic-SWF attribution band dated
    # to the HUMAIN launch; only ~$4B of it is discrete/dated appropriations.
    SovereignCommitment(
        announced="2025-05-12",
        jurisdiction="Saudi Arabia (Gulf)",
        usd_billions=22.6,
        source_url="https://vision2030.ai/analysis/humain/",
        note="Gulf domestic-SWF estimate band $20-30B anchored to PIF's HUMAIN launch; "
             "only ~$4B discrete/dated ($1.2B NIF 2026-01-21 + $2.7B Hexagon govt DC)",
    ),
    SovereignCommitment(
        announced="2025-06-11",
        jurisdiction="UK",
        usd_billions=2.7,
        source_url="https://www.techuk.org/resource/spending-review-2025-a-defining-commitment-to-high-performance-compute.html",
        note="Spending Review 2025: GBP2B for the AI Opportunities Action Plan "
             "(~GBP1B sovereign compute, up to GBP500M Sovereign AI Unit)",
    ),
    # Japan arrives as two distinct dated tranches (Nov and Dec 2025).
    SovereignCommitment(
        announced="2025-11-22",
        jurisdiction="Japan",
        usd_billions=6.4,
        source_url="https://asia.nikkei.com/business/tech/semiconductors/japan-pledges-additional-6.4bn-in-support-for-chipmaker-rapidus",
        note="~JPY1T additional Rapidus aid FY2026-27 (METI subsidies + IPA equity)",
    ),
    # Korea: KRW10.1T at ~KRW1460/USD is ~$6.9B (the documented ~$8B was high).
    SovereignCommitment(
        announced="2025-12-03",
        jurisdiction="South Korea",
        usd_billions=6.9,
        source_url="https://www.japantimes.co.jp/business/2025/12/03/tech/south-korea-budget-ai-growth/",
        note="National Assembly approves 2026 budget with KRW10.1T AI allocation",
    ),
    SovereignCommitment(
        announced="2025-12-26",
        jurisdiction="Japan",
        usd_billions=7.9,
        source_url="https://www.japantimes.co.jp/business/2025/12/26/economy/ai-budget-support/",
        note="Cabinet approves FY2026 budget: chips/AI support quadrupled to JPY1.23T",
    ),
    # UK: sits inside the Jun 2025 GBP2B envelope -- minor double-count risk,
    # kept as a distinct arrival because it was a distinct dated announcement.
    SovereignCommitment(
        announced="2026-04-16",
        jurisdiction="UK",
        usd_billions=0.7,
        source_url="https://www.thinkdigitalpartners.com/news/2026/04/16/uk-launches-500m-sovereign-ai-fund-to-scale-homegrown-tech-champions/",
        note="GBP500M Sovereign AI Fund launch (first cohort)",
    ),
)


@dataclass(frozen=True)
class ArrivalRateFit:
    n_commitments: int
    window_start: str
    window_end: str
    window_years: float
    lambda_per_year: float
    expected_jumps_in_horizon: float
    note: str


@dataclass(frozen=True)
class JumpSizeFit:
    n: int
    mu: float                      # lognormal MLE: mean of log sizes
    sigma: float                   # lognormal MLE: population std of log sizes
    implied_median_usd_billions: float
    implied_mean_usd_billions: float
    ks_statistic: float            # log sizes vs Normal(mu, sigma)
    ks_critical_5pct: float        # Lilliefors large-sample approx 0.886/sqrt(n)
    ks_note: str
    loglik: dict[str, float]
    aic: dict[str, float]
    aic_winner: str
    chosen: str
    choice_note: str


@dataclass(frozen=True)
class VariantResult:
    key: str
    label: str
    rate_spec: str
    assumed: bool
    p_cross_pct: float
    mc_standard_error_pct: float
    mean_total_usd_billions: float
    percentiles_usd_billions: dict[str, float]
    histogram: tuple[tuple[str, float], ...]


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def fit_arrival_rate(
    history: tuple[SovereignCommitment, ...] = COMMITMENT_HISTORY,
    window_end: date = AS_OF_DATE,
) -> ArrivalRateFit:
    """lambda = n_commitments / observed_window_years.

    The window is anchored at the FIRST observed commitment, which slightly
    overstates lambda (the category existed with zero events before Mar 2024).
    The bias direction is toward YES -- a true lambda would be lower and
    P(cross) lower still -- so it cannot rescue the headline conclusion.
    """
    announced = sorted(date.fromisoformat(c.announced) for c in history)
    window_start = announced[0]
    if window_end <= window_start:
        raise ValueError("window_end must fall after the first commitment")
    window_years = (window_end - window_start).days / DAYS_PER_YEAR
    lam = len(history) / window_years
    return ArrivalRateFit(
        n_commitments=len(history),
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        window_years=round(window_years, 4),
        lambda_per_year=round(lam, 4),
        expected_jumps_in_horizon=round(lam * HORIZON_YEARS, 4),
        note="Window anchored at first observed event; overstates lambda slightly "
             "(bias toward YES, so the low headline is conservative-against-itself).",
    )


def fit_jump_sizes(history: tuple[SovereignCommitment, ...] = COMMITMENT_HISTORY) -> JumpSizeFit:
    """Lognormal MLE for jump sizes, with the fit CHECKED, not assumed.

    Checks: (1) KS statistic of log sizes vs Normal(mu, sigma) -- parameters
    are estimated from the same 10 points, so this is the Lilliefors regime
    and the 0.886/sqrt(n) 5% critical value is a large-sample approximation;
    at n=10 the whole test is descriptive, not inferential. (2) Log-likelihood
    and AIC against exponential (MLE) and gamma (moment-matched) alternatives.
    The gamma is moment-matched rather than MLE, so its reported likelihood
    understates the best gamma fit -- comparison is indicative only.
    """
    sizes = [c.usd_billions for c in history]
    logs = [math.log(s) for s in sizes]
    n = len(sizes)
    mu = statistics.fmean(logs)
    sigma = statistics.pstdev(logs)   # MLE: divide by n, not n-1

    # KS statistic of the log sizes against the fitted Normal(mu, sigma).
    d_stat = 0.0
    for i, x in enumerate(sorted(logs), start=1):
        f = _normal_cdf((x - mu) / sigma)
        d_stat = max(d_stat, abs(i / n - f), abs((i - 1) / n - f))
    ks_critical = 0.886 / math.sqrt(n)

    ll_lognormal = sum(
        -math.log(s) - math.log(sigma) - 0.5 * math.log(2.0 * math.pi)
        - (math.log(s) - mu) ** 2 / (2.0 * sigma ** 2)
        for s in sizes
    )
    mean_size = statistics.fmean(sizes)
    exp_rate = 1.0 / mean_size   # exponential MLE
    ll_exponential = sum(math.log(exp_rate) - exp_rate * s for s in sizes)
    var_size = statistics.pvariance(sizes)
    gamma_shape = mean_size ** 2 / var_size   # moment matching
    gamma_scale = var_size / mean_size
    ll_gamma = sum(
        (gamma_shape - 1.0) * math.log(s) - s / gamma_scale
        - gamma_shape * math.log(gamma_scale) - math.lgamma(gamma_shape)
        for s in sizes
    )

    loglik = {
        "lognormal": round(ll_lognormal, 3),
        "exponential": round(ll_exponential, 3),
        "gamma_moment_matched": round(ll_gamma, 3),
    }
    aic = {   # AIC = 2k - 2LL; k: lognormal 2, exponential 1, gamma 2
        "lognormal": round(2 * 2 - 2 * ll_lognormal, 3),
        "exponential": round(2 * 1 - 2 * ll_exponential, 3),
        "gamma_moment_matched": round(2 * 2 - 2 * ll_gamma, 3),
    }
    winner = min(aic, key=aic.get)
    delta_vs_best = aic["lognormal"] - aic[winner]
    if winner == "lognormal":
        choice_note = "Lognormal wins AIC outright; used as planned."
    elif delta_vs_best < CLEARLY_BEATEN_AIC_DELTA:
        choice_note = (
            f"AIC winner is {winner} by {delta_vs_best:.1f} points -- entirely the "
            f"parameter-count penalty on a near-tied log-likelihood "
            f"({loglik[winner]:.2f} vs lognormal {loglik['lognormal']:.2f}). That is "
            f"below the ~{CLEARLY_BEATEN_AIC_DELTA:.0f}-point 'clearly beaten' bar and "
            "n=10 makes the ranking noisy, so lognormal is retained as planned. "
            "Robustness: exponential/gamma right tails are thinner, so either "
            "alternative would push P(cross $250B) even LOWER -- the headline "
            "conclusion does not hinge on this choice."
        )
    else:
        # Not reached with the embedded data (delta ~2.2); kept so a future
        # data update cannot silently keep a clearly-beaten lognormal.
        choice_note = (
            f"WARNING: {winner} beats lognormal by {delta_vs_best:.1f} AIC points "
            f"(>= {CLEARLY_BEATEN_AIC_DELTA:.0f}); revisit the lognormal choice."
        )
    return JumpSizeFit(
        n=n,
        mu=round(mu, 4),
        sigma=round(sigma, 4),
        implied_median_usd_billions=round(math.exp(mu), 2),
        implied_mean_usd_billions=round(math.exp(mu + sigma ** 2 / 2.0), 2),
        ks_statistic=round(d_stat, 4),
        ks_critical_5pct=round(ks_critical, 4),
        ks_note=(
            "Parameters estimated from the same 10 points (Lilliefors regime); "
            "0.886/sqrt(n) approximates the 5% critical value. Descriptive only "
            "at n=10 -- power to reject anything is minimal."
        ),
        loglik=loglik,
        aic=aic,
        aic_winner=winner,
        chosen="lognormal",
        choice_note=choice_note,
    )


def _poisson_sample(rng: random.Random, mean: float) -> int:
    """Poisson draw via Knuth multiplication (stdlib only).

    Multiply uniforms until the product drops below e^-mean; the number of
    factors needed, minus one, is Poisson(mean). Exact, and fast for the small
    means used here (< ~6 expected jumps). Guarded against large means where
    e^-mean underflows and the loop degenerates.
    """
    if mean < 0:
        raise ValueError("Poisson mean must be non-negative")
    if mean > 100:
        raise ValueError(f"Knuth sampler is for small means; got {mean}")
    threshold = math.exp(-mean)
    count = 0
    product = rng.random()
    while product > threshold:
        count += 1
        product *= rng.random()
    return count


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile on an ascending pre-sorted list."""
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _histogram(totals: list[float]) -> tuple[tuple[str, float], ...]:
    labels = [f"={HISTOGRAM_BIN_EDGES[0]:.0f} (base; no new commitments)"]
    labels += [f"{lo:.0f}-{hi:.0f}" for lo, hi in zip(HISTOGRAM_BIN_EDGES, HISTOGRAM_BIN_EDGES[1:])]
    labels.append(f">{HISTOGRAM_BIN_EDGES[-1]:.0f}")
    counts = [0] * len(labels)
    for total in totals:
        # Zero-jump paths add nothing to the base, so exact equality is safe.
        if total == CURRENT_BASE_USD_BILLIONS:
            counts[0] += 1
            continue
        for i, hi in enumerate(HISTOGRAM_BIN_EDGES[1:], start=1):
            if total <= hi:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    n = len(totals)
    return tuple((label, count / n) for label, count in zip(labels, counts))


def _simulate_variant(
    key: str,
    label: str,
    rate_spec: str,
    assumed: bool,
    paths: int,
    rng: random.Random,
    rate_fit: ArrivalRateFit,
    mu: float,
    sigma: float,
    rate_multiplier: float = 1.0,
    draw_rate_from_posterior: bool = False,
) -> VariantResult:
    """Simulate year-end totals for one variant and summarize them."""
    totals: list[float] = []
    crossings = 0
    for _ in range(paths):
        if draw_rate_from_posterior:
            # Jeffreys prior for a Poisson rate, p(lambda) ~ lambda^-1/2, gives
            # posterior Gamma(shape = n + 1/2, rate = T) after n events in T
            # exposure years; random.gammavariate takes the SCALE, i.e. 1/T.
            # Drawing lambda per path propagates estimation uncertainty and
            # produces the overdispersion a point-lambda model hides.
            lam = rng.gammavariate(rate_fit.n_commitments + 0.5, 1.0 / rate_fit.window_years)
        else:
            lam = rate_fit.lambda_per_year
        lam *= rate_multiplier
        n_jumps = _poisson_sample(rng, lam * HORIZON_YEARS)
        total = CURRENT_BASE_USD_BILLIONS
        for _ in range(n_jumps):
            total += rng.lognormvariate(mu, sigma)
        if total >= THRESHOLD_USD_BILLIONS:
            crossings += 1
        totals.append(total)

    p_cross = crossings / paths
    totals.sort()
    return VariantResult(
        key=key,
        label=label,
        rate_spec=rate_spec,
        assumed=assumed,
        p_cross_pct=round(p_cross * 100.0, 2),
        mc_standard_error_pct=round(math.sqrt(p_cross * (1.0 - p_cross) / paths) * 100.0, 3),
        mean_total_usd_billions=round(statistics.fmean(totals), 1),
        percentiles_usd_billions={
            f"p{p}": round(_percentile(totals, p), 1) for p in (5, 25, 50, 75, 95, 99)
        },
        histogram=_histogram(totals),
    )


def _simulate_regime_switching(
    paths: int,
    rng: random.Random,
    rate_fit: ArrivalRateFit,
    mu: float,
    sigma: float,
) -> tuple[VariantResult, dict]:
    """Two-state regime-switching compound Poisson -- variant (d), the headline.

    Per path:
      1. Draw the trigger rate from its Jeffreys posterior
         Gamma(TRIGGER_EVENTS_OBSERVED + 0.5, rate T) -- n=1 makes the point
         estimate nearly meaningless on its own, so the uncertainty is
         propagated rather than hidden.
      2. Draw the trigger time tau ~ Exp(trigger rate). The burst regime
         activates at tau + RESPONSE_LATENCY_DAYS (the observed
         Stargate -> InvestAI lag) and, once active, runs to the resolution
         date (no reversion inside the 5-month window -- a simplification
         that is conservative TOWARD YES).
      3. Arrivals before the shift follow the fitted organic process
         (lambda_A, ordinary lognormal sizes); arrivals after it follow
         REGIME_B_RATE_PER_YEAR with sizes scaled by a per-path multiplier
         m ~ Uniform(REGIME_B_SIZE_MULTIPLIER_LOW, HIGH) (scaling a lognormal
         by m shifts mu by ln m).

    Returns the VariantResult plus a diagnostics dict decomposing the headline
    into P(shift active before resolution) and P(cross | shift) -- the two
    quantities that actually drive the number.
    """
    latency_years = RESPONSE_LATENCY_DAYS / DAYS_PER_YEAR
    totals: list[float] = []
    crossings = 0
    shift_paths = 0
    crossings_with_shift = 0
    for _ in range(paths):
        trigger_rate = rng.gammavariate(
            TRIGGER_EVENTS_OBSERVED + 0.5, 1.0 / rate_fit.window_years
        )
        tau = rng.expovariate(trigger_rate)
        shift_time = tau + latency_years
        span_organic = min(shift_time, HORIZON_YEARS)
        span_burst = HORIZON_YEARS - span_organic
        total = CURRENT_BASE_USD_BILLIONS
        for _ in range(_poisson_sample(rng, rate_fit.lambda_per_year * span_organic)):
            total += rng.lognormvariate(mu, sigma)
        if span_burst > 0.0:
            shift_paths += 1
            multiplier = rng.uniform(
                REGIME_B_SIZE_MULTIPLIER_LOW, REGIME_B_SIZE_MULTIPLIER_HIGH
            )
            burst_mu = mu + math.log(multiplier)
            for _ in range(_poisson_sample(rng, REGIME_B_RATE_PER_YEAR * span_burst)):
                total += rng.lognormvariate(burst_mu, sigma)
        if total >= THRESHOLD_USD_BILLIONS:
            crossings += 1
            if span_burst > 0.0:
                crossings_with_shift += 1
        totals.append(total)

    p_cross = crossings / paths
    totals.sort()
    variant = VariantResult(
        key="regime_switching",
        label="(d) Regime-switching (headline)",
        rate_spec=(
            f"organic lambda {rate_fit.lambda_per_year:.2f}/yr until a trigger "
            f"(rate ~ Gamma({TRIGGER_EVENTS_OBSERVED}+0.5, T={rate_fit.window_years:.2f}y) "
            f"posterior) + {RESPONSE_LATENCY_DAYS}d latency; then burst at "
            f"{REGIME_B_RATE_PER_YEAR:.0f}/yr, sizes x U({REGIME_B_SIZE_MULTIPLIER_LOW:.1f}, "
            f"{REGIME_B_SIZE_MULTIPLIER_HIGH:.1f})"
        ),
        assumed=False,
        p_cross_pct=round(p_cross * 100.0, 2),
        mc_standard_error_pct=round(math.sqrt(p_cross * (1.0 - p_cross) / paths) * 100.0, 3),
        mean_total_usd_billions=round(statistics.fmean(totals), 1),
        percentiles_usd_billions={
            f"p{p}": round(_percentile(totals, p), 1) for p in (5, 25, 50, 75, 95, 99)
        },
        histogram=_histogram(totals),
    )
    no_shift_paths = paths - shift_paths
    crossings_no_shift = crossings - crossings_with_shift
    diagnostics = {
        "p_shift_active_pct": round(shift_paths / paths * 100.0, 1),
        "p_cross_given_shift_pct": round(
            crossings_with_shift / shift_paths * 100.0, 2
        ) if shift_paths else 0.0,
        "p_cross_given_no_shift_pct": round(
            crossings_no_shift / no_shift_paths * 100.0, 2
        ) if no_shift_paths else 0.0,
        "trigger_rate_mle_per_year": round(
            TRIGGER_EVENTS_OBSERVED / rate_fit.window_years, 3
        ),
        "response_latency_days": RESPONSE_LATENCY_DAYS,
        "regime_b_rate_per_year": REGIME_B_RATE_PER_YEAR,
        "regime_b_size_multiplier": (
            REGIME_B_SIZE_MULTIPLIER_LOW, REGIME_B_SIZE_MULTIPLIER_HIGH
        ),
    }
    return variant, diagnostics


def _persisted_probability_pct() -> float | None:
    """Read the currently persisted probability for #7 from forecast_state.json."""
    if not FORECAST_STATE_PATH.exists():
        return None
    state = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8"))
    return state.get(str(FORECAST_ID))


def sovereign_ai_report(
    paths: int = DEFAULT_MONTE_CARLO_PATHS,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> dict:
    """Everything the TUI needs: fits, diagnostics, three variants, divergence.

    Pure computation -- no printing, no persistence.
    """
    if paths <= 0:
        raise ValueError("paths must be a positive integer")
    rate_fit = fit_arrival_rate()
    size_fit = fit_jump_sizes()

    # Distinct seed offsets so each variant is individually reproducible
    # regardless of which variants a caller runs.
    variant_a = _simulate_variant(
        key="stationary",
        label="(a) Stationary fit",
        rate_spec=f"lambda fixed at fitted {rate_fit.lambda_per_year:.2f}/yr",
        assumed=False,
        paths=paths,
        rng=random.Random(random_seed),
        rate_fit=rate_fit,
        mu=size_fit.mu,
        sigma=size_fit.sigma,
    )
    variant_b = _simulate_variant(
        key="rate_uncertainty",
        label="(b) Rate uncertainty",
        rate_spec=(
            f"lambda ~ Gamma({rate_fit.n_commitments} + 0.5, T={rate_fit.window_years:.2f}y) "
            "posterior per path (Jeffreys prior)"
        ),
        assumed=False,
        paths=paths,
        rng=random.Random(random_seed + 1),
        rate_fit=rate_fit,
        mu=size_fit.mu,
        sigma=size_fit.sigma,
        draw_rate_from_posterior=True,
    )
    variant_c = _simulate_variant(
        key="acceleration",
        label="(c) Acceleration stress (ASSUMED)",
        rate_spec=(
            f"lambda x{ACCELERATION_RATE_MULTIPLIER:.0f} = "
            f"{rate_fit.lambda_per_year * ACCELERATION_RATE_MULTIPLIER:.2f}/yr, "
            f"jump sizes x{ACCELERATION_SIZE_MULTIPLIER:.1f}"
        ),
        assumed=True,
        paths=paths,
        rng=random.Random(random_seed + 2),
        rate_fit=rate_fit,
        mu=size_fit.mu + math.log(ACCELERATION_SIZE_MULTIPLIER),   # scale by c => mu + ln(c)
        sigma=size_fit.sigma,
        rate_multiplier=ACCELERATION_RATE_MULTIPLIER,
    )
    variant_d, regime_diagnostics = _simulate_regime_switching(
        paths=paths,
        rng=random.Random(random_seed + 3),
        rate_fit=rate_fit,
        mu=size_fit.mu,
        sigma=size_fit.sigma,
    )
    variants = (variant_a, variant_b, variant_c, variant_d)

    persisted = _persisted_probability_pct()
    headline = variant_d.p_cross_pct
    gap = THRESHOLD_USD_BILLIONS - CURRENT_BASE_USD_BILLIONS
    persisted_text = f"{persisted:.1f}%" if persisted is not None else "none on file"
    divergence_note = (
        f"Regime-switching headline {headline:.2f}% (variant d) vs persisted "
        f"{persisted_text}. The two-state structure replaces BOTH prior anchors: "
        f"the stationary extrapolation ({variant_a.p_cross_pct:.1f}%), which is "
        "structurally blind to a step-change, and the old judgment 14%, which "
        "asserted a step-change without modeling one. Decomposition: "
        f"P(burst regime activates before resolution) = "
        f"{regime_diagnostics['p_shift_active_pct']:.1f}% (one observed "
        "Stargate-class trigger in the 2.37y window, Jeffreys posterior per "
        f"path, {RESPONSE_LATENCY_DAYS}-day observed response latency), and "
        f"P(cross | burst) = {regime_diagnostics['p_cross_given_shift_pct']:.1f}% "
        f"(burst rate {REGIME_B_RATE_PER_YEAR:.0f}/yr = max observed 90-day "
        "pace; sizes x U(1.0, 3.5), ceiling anchored to the EU gigafactory "
        "member-state co-funding obligation and the Gulf domestic band). Even a "
        "triggered burst usually falls short because crossing needs ~$"
        f"{gap:.0f}B in {HORIZON_DAYS} days, ~"
        f"{gap / size_fit.implied_mean_usd_billions:.0f}x the fitted mean jump -- "
        "the old 14% implicitly required a burst regime far outside anything in "
        "the observed record or live reporting."
    )

    return {
        "forecast_id": FORECAST_ID,
        "title": get(FORECAST_ID).title,
        "as_of_date": AS_OF_DATE.isoformat(),
        "resolution_date": RESOLUTION_DATE.isoformat(),
        "horizon_days": HORIZON_DAYS,
        "horizon_years": round(HORIZON_YEARS, 4),
        "base_usd_billions": CURRENT_BASE_USD_BILLIONS,
        "base_note": BASE_UNCERTAINTY_NOTE,
        "threshold_usd_billions": THRESHOLD_USD_BILLIONS,
        "arrival_rate": {
            "n_commitments": rate_fit.n_commitments,
            "window_start": rate_fit.window_start,
            "window_end": rate_fit.window_end,
            "window_years": rate_fit.window_years,
            "lambda_per_year": rate_fit.lambda_per_year,
            "expected_jumps_in_horizon": rate_fit.expected_jumps_in_horizon,
            "note": rate_fit.note,
        },
        "jump_size_fit": {
            "n": size_fit.n,
            "mu": size_fit.mu,
            "sigma": size_fit.sigma,
            "implied_median_usd_billions": size_fit.implied_median_usd_billions,
            "implied_mean_usd_billions": size_fit.implied_mean_usd_billions,
            "ks_statistic": size_fit.ks_statistic,
            "ks_critical_5pct": size_fit.ks_critical_5pct,
            "ks_note": size_fit.ks_note,
            "loglik": size_fit.loglik,
            "aic": size_fit.aic,
            "aic_winner": size_fit.aic_winner,
            "chosen": size_fit.chosen,
            "choice_note": size_fit.choice_note,
        },
        "variants": [
            {
                "key": v.key,
                "label": v.label,
                "rate_spec": v.rate_spec,
                "assumed": v.assumed,
                "p_cross_pct": v.p_cross_pct,
                "mc_standard_error_pct": v.mc_standard_error_pct,
                "mean_total_usd_billions": v.mean_total_usd_billions,
                "percentiles_usd_billions": v.percentiles_usd_billions,
                "histogram": list(v.histogram),
            }
            for v in variants
        ],
        "paths": paths,
        "random_seed": random_seed,
        "regime_diagnostics": regime_diagnostics,
        "persisted_probability_pct": persisted,
        "headline_probability_pct": headline,
        "divergence_pts": (
            round(headline - persisted, 2) if persisted is not None else None
        ),
        "divergence_note": divergence_note,
        "caveats": [
            "n=10 jumps: every fitted parameter carries wide sampling error. "
            "Variant (b) propagates the RATE's uncertainty; jump-size parameter "
            "uncertainty is NOT propagated (that needs a hierarchical fit).",
            "The Gulf row is a $20-30B band attribution dated to one launch, not "
            "a single dated appropriation -- it overstates arrival-date precision "
            "and carries the Saudi $9.1B private-deal-flow misclassification risk.",
            "The UK 2026-04-16 GBP0.5B row sits inside the Jun 2025 GBP2B "
            "envelope (~$0.7B double-count risk).",
            "Rate window anchored at the first observed event overstates lambda "
            "slightly; the bias is toward YES, so the low headline survives it.",
            "Jump sizes treated i.i.d. and independent of arrivals; real "
            "commitments cluster around summits and budget seasons, so the true "
            "dispersion of the 162-day sum likely exceeds the modeled one.",
        ],
    }


def print_report(report: dict, console: Console | None = None) -> None:
    """Pretty-print the full report: fits, variant comparison, histogram, divergence."""
    console = console or Console()
    persisted = report["persisted_probability_pct"]
    persisted_text = f"{persisted:.1f}%" if persisted is not None else "none on file"
    console.print(Panel.fit(
        f"[bold]Forecast #{report['forecast_id']}: {report['title']}[/bold]\n"
        f"Compound Poisson jump model | base ${report['base_usd_billions']:.0f}B -> "
        f"${report['threshold_usd_billions']:.0f}B in {report['horizon_days']} days "
        f"({report['horizon_years']:.4f}y) | {report['paths']:,} paths, seed {report['random_seed']}\n"
        f"Headline (regime-switching, variant d): "
        f"[bold]{report['headline_probability_pct']:.1f}%[/bold] | "
        f"persisted: {persisted_text}",
        border_style="cyan",
    ))
    regime = report["regime_diagnostics"]
    console.print(
        f"Regime decomposition: P(burst regime active before resolution) = "
        f"[bold]{regime['p_shift_active_pct']:.1f}%[/bold] (trigger MLE "
        f"{regime['trigger_rate_mle_per_year']:.2f}/yr from 1 observed Stargate-class event, "
        f"Jeffreys posterior per path; {regime['response_latency_days']}d observed response "
        f"latency) x P(cross | burst) = [bold]{regime['p_cross_given_shift_pct']:.1f}%[/bold] "
        f"(burst {regime['regime_b_rate_per_year']:.0f}/yr = max observed 90-day pace; sizes x "
        f"U{regime['regime_b_size_multiplier']}) + P(cross | no burst) = "
        f"{regime['p_cross_given_no_shift_pct']:.2f}%"
    )

    rate = report["arrival_rate"]
    fit = report["jump_size_fit"]
    fit_table = Table(title="Fitted compound Poisson parameters", box=box.SIMPLE_HEAVY)
    fit_table.add_column("Parameter")
    fit_table.add_column("Value", justify="right")
    fit_table.add_column("Source / note")
    fit_table.add_row(
        "Arrival rate lambda",
        f"{rate['lambda_per_year']:.3f}/yr",
        f"{rate['n_commitments']} commitments / {rate['window_years']:.3f}y "
        f"({rate['window_start']} -> {rate['window_end']})",
    )
    fit_table.add_row(
        "Expected jumps in horizon",
        f"{rate['expected_jumps_in_horizon']:.2f}",
        f"lambda x {report['horizon_years']:.4f}y",
    )
    fit_table.add_row("Jump-size mu (log)", f"{fit['mu']:.4f}", "lognormal MLE, n=10 log sizes")
    fit_table.add_row("Jump-size sigma (log)", f"{fit['sigma']:.4f}", "lognormal MLE (population std)")
    fit_table.add_row(
        "Implied jump median / mean",
        f"${fit['implied_median_usd_billions']:.1f}B / ${fit['implied_mean_usd_billions']:.1f}B",
        "exp(mu), exp(mu + sigma^2/2)",
    )
    fit_table.add_row(
        "KS stat (log sizes vs fit)",
        f"{fit['ks_statistic']:.3f}",
        f"< ~{fit['ks_critical_5pct']:.3f} 5% Lilliefors approx -> no rejection (n=10: descriptive)",
    )
    console.print(fit_table)

    aic_table = Table(title="Jump-size distribution check (LL / AIC)", box=box.SIMPLE)
    aic_table.add_column("Candidate")
    aic_table.add_column("log-lik", justify="right")
    aic_table.add_column("AIC", justify="right")
    aic_table.add_column("")
    for name in ("lognormal", "exponential", "gamma_moment_matched"):
        marks = []
        if name == fit["aic_winner"]:
            marks.append("AIC winner")
        if name == fit["chosen"]:
            marks.append("[bold]used[/bold]")
        aic_table.add_row(name, f"{fit['loglik'][name]:.2f}", f"{fit['aic'][name]:.2f}", ", ".join(marks))
    console.print(aic_table)
    console.print(f"[dim]{fit['choice_note']}[/dim]")

    comparison = Table(title="Variant comparison (none blended)", box=box.ROUNDED)
    comparison.add_column("Variant")
    comparison.add_column("Rate spec")
    comparison.add_column("P(>= $250B)", justify="right")
    comparison.add_column("+/- MC SE", justify="right")
    comparison.add_column("Mean total", justify="right")
    for v in report["variants"]:
        comparison.add_row(
            v["label"],
            v["rate_spec"],
            f"{v['p_cross_pct']:.2f}%",
            f"{v['mc_standard_error_pct']:.3f}pp",
            f"${v['mean_total_usd_billions']:.1f}B",
        )
    console.print(comparison)

    pct_table = Table(title="Year-end total percentiles ($B)", box=box.SIMPLE)
    pct_table.add_column("Variant")
    for p in ("p5", "p25", "p50", "p75", "p95", "p99"):
        pct_table.add_column(p, justify="right")
    for v in report["variants"]:
        pct_table.add_row(
            v["label"],
            *(f"{v['percentiles_usd_billions'][p]:.1f}" for p in ("p5", "p25", "p50", "p75", "p95", "p99")),
        )
    console.print(pct_table)

    histogram = Table(
        title=f"Year-end total distribution ({report['paths']:,} paths; >= $250B is the YES region)",
        box=box.SIMPLE,
    )
    histogram.add_column("Total ($B)")
    for v in report["variants"]:
        histogram.add_column(v["key"], justify="left")
    for i, (label, _) in enumerate(report["variants"][0]["histogram"]):
        yes_region = label.startswith("250") or label.startswith(">")
        cells = []
        for v in report["variants"]:
            fraction = v["histogram"][i][1]
            cells.append(f"{fraction * 100:5.1f}% {'#' * round(fraction * 40)}")
        style = "[green]" if yes_region else ""
        end_style = "[/green]" if yes_region else ""
        histogram.add_row(f"{style}{label}{end_style}", *cells)
    console.print(histogram)

    console.print(Panel(
        report["divergence_note"],
        title=f"Divergence vs persisted {persisted_text}",
        border_style="yellow",
    ))
    console.print(f"[dim]Base: {report['base_note']}[/dim]")
    for caveat in report["caveats"]:
        console.print(f"[dim]- {caveat}[/dim]")


if __name__ == "__main__":
    report = sovereign_ai_report()
    print_report(report)
    if "--persist" in sys.argv:
        # Persistence is an explicit maintainer decision, taken deliberately and
        # never as a side effect of a plain run. This persists the
        # regime-switching headline (variant d) -- the model that can actually
        # represent the arms-race step-change the old judgment 14% asserted,
        # with its transition probability and burst magnitude stated and
        # grounded rather than implicit.
        headline_pct = round(report["headline_probability_pct"], 1)
        set_forecast_probability(FORECAST_ID, headline_pct)
        Console().print(
            f"[bold]Persisted {headline_pct}% for forecast #{FORECAST_ID} "
            "(regime-switching variant (d)).[/bold]"
        )
