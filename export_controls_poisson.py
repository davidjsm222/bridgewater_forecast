"""
Forecast #1 upgrade: a Poisson point-process model for chip export controls.

YES resolves if BIS takes at least one tightening action on China advanced
chips before 2026-12-31. The persisted tier-3 estimate (90%) prices the
tightening SHARE of substantive actions (26/(26+2) = 93% base rate, net -3pp
of judgment adjustments). But the resolution criterion doesn't ask what share
of actions tighten -- it asks whether at least one tightening event LANDS in
the remaining window. That is an arrival-rate question, and the right tool is
a Poisson point process: the audited Federal Register history shows BIS China
advanced-chip tightening rules arriving as discrete regulatory events at a
roughly steady cadence, so P(YES) has the closed form

    P(at least one event in t years) = 1 - exp(-lambda * t)

with lambda the fitted events-per-year rate and t the time from AS_OF_DATE to
resolution. The job here isn't prediction from scratch, it's fitting lambda
honestly (MLE on the audited event dates), checking whether one homogeneous
rate is even defensible (exact binomial split test, KS/Lilliefors diagnostic
on inter-arrival times), and letting the diagnostics -- not vibes -- pick
between the full-window and recent-window rate.

Arrival unit: BIS ships coordinated same-day rule packages (five zero-day
inter-arrival gaps in the 26-rule history), so individual rules are NOT
independent arrivals. For "at least one tightening action" the package and its
first rule land together -- P(>=1 rule) = P(>=1 publication EPISODE) exactly --
so the correct arrival unit for the headline is the episode (unique publication
day, 21 of them), and treating all 26 rules as independent arrivals overstates
the number of distinct chances for YES. The per-rule fit is therefore reported
as an explicit upper bound, and the episode fit carries the headline.
"""

import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import date

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forecasts import FORECAST_STATE_PATH, set_forecast_probability


FORECAST_ID = 1
AS_OF_DATE = date(2026, 7, 22)          # repo convention, mirrors fomc_history.CURRENT_AS_OF_DATE
RESOLUTION_DATE = date(2026, 12, 31)    # forecast #1 resolution date (forecasts.py)
DAYS_PER_YEAR = 365.2425
# Observation window start matches the cached docket's query window
# (publication_date_start = 2022-01-01 in data_cache/federal_register_bis_export_controls.json,
# Federal Register API https://www.federalregister.gov/api/v1/documents.json,
# retrieved 2026-07-17) and the audited reference class in methodology_notes.md #1
# ("China advanced-computing/semiconductor export control actions, 2022-2026").
OBSERVATION_WINDOW_START = date(2022, 1, 1)
# ASSUMED: trailing 24 months for the recent-window rate -- long enough to hold
# a double-digit event count (13 events land in it), short enough to catch a
# post-2024 cadence change if one exists. No external source pins this width.
RECENT_WINDOW_YEARS = 2
STABILITY_ALPHA = 0.05                  # ASSUMED: conventional 5% test size for the split test
DEFAULT_MONTE_CARLO_PATHS = 10_000      # cross-check only; the headline P(YES) is closed form
DEFAULT_RANDOM_SEED = 20260722          # deterministic seed, same convention as tier1_market.py
# Current persisted tier-3 reference-class estimate for forecast #1:
# 93% base rate (tightening share, methodology_notes.md #1) minus net 3pp of
# adjustments. The Poisson model is compared against this number.
REFERENCE_CLASS_TIER3_PCT = 90.0

# CAVEAT -- event timestamps are Federal Register PUBLICATION dates, not
# decision or effective dates. Multiple rules published on one day (e.g. the
# 2023-10-25 AC/S + SME pair, the 2024-12-05 package, three rules on
# 2025-01-16) are distinct tightening events with zero inter-arrival gaps.
# Those zero gaps are real features of how BIS ships coordinated packages,
# not data errors; see ks_exponential_check for how the ties are handled.
PUBLICATION_DATE_CAVEAT = (
    "Event dates are Federal Register publication dates; simultaneous-publication "
    "rules on one day are distinct events, so zero inter-arrival gaps are real "
    "(coordinated rule packages), and they are counted as-is in the diagnostics."
)


@dataclass(frozen=True)
class BISRule:
    publication_date: str
    document_number: str
    category: str        # "tightening" | "loosening" | "noise"
    short_title: str


# The full 35-rule audited China advanced-computing/semiconductor subset:
# 26 tightening / 2 loosening / 7 noise. Provenance: hand-audit (title/abstract
# read of all 136 cached rules, ambiguous documents resolved by full-text fetch
# from federalregister.gov) of data_cache/federal_register_bis_export_controls.json;
# classification methodology and the documented totals live in
# methodology_notes.md #1 and forecast_state.json _model_state.tier3["1"].
# Audit reconciled 2026-07-22 against the documented yearly tightening shares
# (2022 = 3/3, 2023 = 8/9, 2024 = 5/5, 2025 = 10/11; the sole 2026 subset
# action is administrative noise). Flagged judgment calls kept per the
# documented audit:
#   - 2022-14069 (2022-06-30) EXCLUDED despite ~24/36 China entities: listings
#     were for Russia/Iran military-supply networks, not chip policy
#     (https://www.federalregister.gov/documents/2022/06/30/2022-14069/...).
#   - 2024-19633 included as tightening despite worldwide scope: aimed at
#     advanced-node/GAAFET/quantum capabilities of concern
#     (https://www.federalregister.gov/documents/2024/09/06/2024-19633/...).
#   - 2023-22873 (Samsung/SK hynix China VEU update, 2023-10-17) EXCLUDED even
#     though its correction 2023-23312 is subset noise.
#   - 2025-19001 (50%-affiliates rule) EXCLUDED as not China-specific.
#   - 2023-25557 kept as loosening despite a weak chip nexus (verified single
#     entity de-listing after ERC review,
#     https://www.federalregister.gov/documents/2023/11/17/2023-25557/entity-list-removal).
_SUBSET_RULES = (
    BISRule("2022-04-11", "2022-07643", "noise", "Correction to Huawei Entity List entries (FDP refs, typo)"),
    BISRule("2022-08-24", "2022-18268", "tightening", "7 China entities added to Entity List"),
    BISRule("2022-10-13", "2022-21658", "tightening", "Oct 2022 advanced computing/semiconductor controls IFR"),
    BISRule("2022-10-13", "2022-22037", "noise", "Public briefing procedures for Oct 2022 chip rule"),
    BISRule("2022-12-07", "2022-26662", "noise", "Comment deadline extension for Oct 2022 chip rule"),
    BISRule("2022-12-19", "2022-27151", "tightening", "36 entities added (China/Japan, incl. YMTC); UVL conforming removal"),
    BISRule("2023-01-18", "2023-00888", "tightening", "Advanced computing/semiconductor controls extended to Macau"),
    BISRule("2023-02-14", "2023-03193", "tightening", "6 China entities added to Entity List"),
    BISRule("2023-03-06", "2023-04558", "tightening", "37 entities added, China majority (28 of 38 entries)"),
    BISRule("2023-06-14", "2023-12726", "tightening", "43 entities added, China majority (31 of 50 entries)"),
    BISRule("2023-06-21", "2023-13196", "noise", "Correction adding omitted China entity (Harbin Bearing)"),
    BISRule("2023-10-11", "2023-22536", "tightening", "49 entities added, China majority (42 of 52 entries)"),
    BISRule("2023-10-19", "2023-23048", "tightening", "13 China entities added to Entity List"),
    BISRule("2023-10-25", "2023-23049", "tightening", "Export controls on semiconductor manufacturing items"),
    BISRule("2023-10-25", "2023-23055", "tightening", "Advanced computing/supercomputer controls update (AC/S IFR)"),
    BISRule("2023-11-08", "2023-23312", "noise", "Correction to Samsung/SK hynix China VEU rule"),
    BISRule("2023-11-17", "2023-25557", "loosening", "Removal of one China entity after ERC review"),
    BISRule("2024-04-11", "2024-07760", "tightening", "11 entries added, China majority (6 of 11)"),
    BISRule("2024-05-14", "2024-10485", "tightening", "37 China entities added to Entity List"),
    BISRule("2024-09-06", "2024-19633", "tightening", "CCL controls on semiconductor, quantum, additive mfg items"),
    BISRule("2024-12-04", "2024-28423", "noise", "Public briefing on Dec 2024 chip rules"),
    BISRule("2024-12-05", "2024-28267", "tightening", "140 entities added, China-dominated (SME package)"),
    BISRule("2024-12-05", "2024-28270", "tightening", "FDP additions; advanced computing/SME refinements; HBM controls"),
    BISRule("2025-01-06", "2024-31468", "tightening", "13 entities added, China majority (11 of 13)"),
    BISRule("2025-01-15", "2025-00636", "tightening", "Framework for Artificial Intelligence Diffusion"),
    BISRule("2025-01-16", "2025-00480", "tightening", "16 entities added, China majority (14 of 16)"),
    BISRule("2025-01-16", "2025-00704", "tightening", "11 China entities added to Entity List"),
    BISRule("2025-01-16", "2025-00711", "tightening", "Due diligence measures for advanced computing ICs"),
    BISRule("2025-03-28", "2025-05426", "tightening", "70 entities added, China majority (42 of 70)"),
    BISRule("2025-03-28", "2025-05427", "tightening", "12 entities added, China majority (11 of 12)"),
    BISRule("2025-09-02", "2025-16735", "tightening", "China VEU authorizations revoked (Intel/Samsung/SK hynix)"),
    BISRule("2025-09-16", "2025-17893", "tightening", "32 entities added, China majority (23 of 32)"),
    BISRule("2025-10-09", "2025-19508", "tightening", "29 entries added, China majority (19 of 29)"),
    BISRule("2025-11-12", "2025-19858", "loosening", "Removal of one China entity and six aliases after review"),
    BISRule("2026-04-09", "2026-06851", "noise", "IC designer status/application deadline extended to Dec 2026"),
)

# Documented audit totals this embedded subset must reproduce exactly
# (methodology_notes.md #1; forecast_state.json _model_state.tier3["1"]).
_DOCUMENTED_CATEGORY_TOTALS = {"tightening": 26, "loosening": 2, "noise": 7}
_DOCUMENTED_YEARLY_TIGHTENING = {2022: 3, 2023: 8, 2024: 5, 2025: 10, 2026: 0}


def _validate_subset() -> None:
    """Fail loudly at import if the embedded audit drifts from the documented totals."""
    counts = {"tightening": 0, "loosening": 0, "noise": 0}
    yearly = dict.fromkeys(_DOCUMENTED_YEARLY_TIGHTENING, 0)
    for rule in _SUBSET_RULES:
        counts[rule.category] += 1
        if rule.category == "tightening":
            yearly[date.fromisoformat(rule.publication_date).year] += 1
    if counts != _DOCUMENTED_CATEGORY_TOTALS:
        raise ValueError(f"Embedded subset totals {counts} != documented {_DOCUMENTED_CATEGORY_TOTALS}")
    if yearly != _DOCUMENTED_YEARLY_TIGHTENING:
        raise ValueError(f"Yearly tightening counts {yearly} != documented {_DOCUMENTED_YEARLY_TIGHTENING}")
    if list(_SUBSET_RULES) != sorted(_SUBSET_RULES, key=lambda r: r.publication_date):
        raise ValueError("Embedded subset is not sorted by publication date")


_validate_subset()

TIGHTENING_DATES: tuple[date, ...] = tuple(
    date.fromisoformat(rule.publication_date)
    for rule in _SUBSET_RULES
    if rule.category == "tightening"
)

# Unique tightening publication days ("episodes"). Same-day rule packages
# (2023-10-25 x2, 2024-12-05 x2, 2025-01-16 x3, 2025-03-28 x2) collapse to one
# arrival each: a package landing satisfies YES exactly once, so the episode
# process is the resolution-relevant arrival unit (see module docstring).
EPISODE_DATES: tuple[date, ...] = tuple(sorted(set(TIGHTENING_DATES)))


@dataclass(frozen=True)
class PoissonFit:
    lambda_per_year: float
    n_events: int
    window_start: str
    window_end: str
    years: float


@dataclass(frozen=True)
class RateStabilityResult:
    split_date: str                          # calendar midpoint of the window
    first_half_events: int
    second_half_events: int
    n_events: int
    binomial_p_success: float                # T1/(T1+T2); 0.5 for a midpoint split
    p_value: float                           # exact two-sided binomial p-value
    alpha: float
    homogeneous: bool                        # True -> full-window rate is primary
    per_year_counts: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class KSResult:
    n_gaps: int
    n_zero_gaps: int                         # simultaneous-publication ties, counted as-is
    lambda_per_day: float
    mean_gap_days: float
    theoretical_mean_gap_days: float
    d_statistic: float
    p_value_asymptotic: float                # Lilliefors-type: conservative/approximate


def fit_poisson(events: tuple[date, ...], window_start: date, window_end: date) -> PoissonFit:
    """Homogeneous-Poisson MLE: lambda-hat = n_events / observation_years.

    Counts events with window_start <= event <= window_end. This is the exact
    MLE for a homogeneous Poisson process observed over a fixed window.
    """
    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")
    years = (window_end - window_start).days / DAYS_PER_YEAR
    n = sum(1 for event in events if window_start <= event <= window_end)
    return PoissonFit(
        lambda_per_year=n / years,
        n_events=n,
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        years=years,
    )


def _binomial_pmf(n: int, k: int, p: float) -> float:
    return math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))


def exact_two_sided_binomial_p(n: int, k_observed: int, p: float) -> float:
    """Exact two-sided binomial p-value (minimum-likelihood method, no scipy).

    Sums P(X = k) over every k whose probability does not exceed the observed
    outcome's probability -- the standard exact two-sided test, computed with
    math.comb. A small relative tolerance absorbs float rounding at ties.
    """
    observed_pmf = _binomial_pmf(n, k_observed, p)
    return min(1.0, sum(
        pmf for k in range(n + 1)
        if (pmf := _binomial_pmf(n, k, p)) <= observed_pmf * (1.0 + 1e-9)
    ))


def rate_stability_check(
    events: tuple[date, ...],
    window_start: date,
    window_end: date,
    alpha: float = STABILITY_ALPHA,
) -> RateStabilityResult:
    """Split test for rate homogeneity.

    Under H0 (one homogeneous rate), conditional on n total events in the
    window, arrival times are iid Uniform, so the first-half count is
    Binomial(n, T1/(T1+T2)). The window is split at its calendar midpoint
    (T1 = T2, p = 0.5) and the exact two-sided binomial p-value is computed.
    Rejection at alpha means the cadence shifted, and the recent-window rate
    becomes the primary lambda; otherwise the full-window rate does.
    """
    total_days = (window_end - window_start).days
    half_days = total_days / 2.0
    in_window = tuple(e for e in events if window_start <= e <= window_end)
    first = sum(1 for e in in_window if (e - window_start).days < half_days)
    n = len(in_window)
    p_success = half_days / total_days
    p_value = exact_two_sided_binomial_p(n, first, p_success)
    yearly: dict[int, int] = {}
    for year in range(window_start.year, window_end.year + 1):
        yearly[year] = sum(1 for e in in_window if e.year == year)
    return RateStabilityResult(
        split_date=(window_start + (window_end - window_start) / 2).isoformat(),
        first_half_events=first,
        second_half_events=n - first,
        n_events=n,
        binomial_p_success=p_success,
        p_value=p_value,
        alpha=alpha,
        homogeneous=p_value >= alpha,
        per_year_counts=tuple(sorted(yearly.items())),
    )


def inter_arrival_gaps_days(events: tuple[date, ...]) -> tuple[int, ...]:
    """Gaps in days between consecutive events (sorted by date).

    Ties (simultaneous-publication rule packages) yield zero-day gaps. They are
    kept as-is -- no jitter -- because they are genuine features of the process
    (see PUBLICATION_DATE_CAVEAT), at the cost of some KS distortion at the
    origin, which the caveat owns explicitly.
    """
    ordered = sorted(events)
    return tuple((b - a).days for a, b in zip(ordered, ordered[1:]))


def _kolmogorov_sf(x: float, terms: int = 100) -> float:
    """Asymptotic Kolmogorov survival function P(sqrt(n) D_n > x).

    The standard series 2 * sum_{k>=1} (-1)^(k-1) exp(-2 k^2 x^2), truncated at
    ``terms`` (ample for the x values arising here) and clamped to [0, 1].
    """
    if x <= 0.0:
        return 1.0
    total = sum((-1.0) ** (k - 1) * math.exp(-2.0 * k * k * x * x) for k in range(1, terms + 1))
    return max(0.0, min(1.0, 2.0 * total))


def ks_exponential_check(gaps_days: tuple[int, ...], lambda_per_year: float) -> KSResult:
    """KS goodness-of-fit of inter-arrival gaps vs Exponential(lambda).

    Both sides are in DAYS: lambda_per_year is converted to a per-day rate so
    the theoretical CDF F(x) = 1 - exp(-lambda_day * x) matches the empirical
    gap units. D_n is the usual two-sided sup distance evaluated at the sorted
    sample. Zero-day gaps (simultaneous publications) enter as-is: F(0) = 0,
    so a run of ties pushes the empirical CDF above the exponential at the
    origin and honestly penalizes the fit rather than being smoothed away.

    NOTE on the p-value: lambda is estimated from the same event history the
    gaps come from, so this is a Lilliefors-type situation -- the classical
    asymptotic Kolmogorov p-value printed here is conservative/approximate
    (the true null distribution of D_n with an estimated rate is tighter).
    Treat it as a diagnostic, not a precise tail probability.
    """
    if not gaps_days:
        raise ValueError("Need at least one inter-arrival gap for the KS check")
    lambda_per_day = lambda_per_year / DAYS_PER_YEAR
    ordered = sorted(gaps_days)
    n = len(ordered)
    d_statistic = 0.0
    for i, gap in enumerate(ordered, start=1):
        cdf = 1.0 - math.exp(-lambda_per_day * gap)
        d_statistic = max(d_statistic, i / n - cdf, cdf - (i - 1) / n)
    return KSResult(
        n_gaps=n,
        n_zero_gaps=sum(1 for gap in ordered if gap == 0),
        lambda_per_day=lambda_per_day,
        mean_gap_days=sum(ordered) / n,
        theoretical_mean_gap_days=1.0 / lambda_per_day,
        d_statistic=d_statistic,
        p_value_asymptotic=_kolmogorov_sf(math.sqrt(n) * d_statistic),
    )


def qq_points(gaps_days: tuple[int, ...], lambda_per_year: float) -> tuple[tuple[float, float], ...]:
    """QQ pairs (theoretical exponential quantile, empirical sorted gap), in days.

    Theoretical quantiles at plotting positions (i - 0.5)/n:
    q_i = -ln(1 - (i - 0.5)/n) / lambda_per_day. For the TUI to plot.
    """
    lambda_per_day = lambda_per_year / DAYS_PER_YEAR
    ordered = sorted(gaps_days)
    n = len(ordered)
    return tuple(
        (-math.log(1.0 - (i - 0.5) / n) / lambda_per_day, float(gap))
        for i, gap in enumerate(ordered, start=1)
    )


def _monte_carlo_p_at_least_one(
    lambda_per_year: float,
    horizon_years: float,
    paths: int,
    random_seed: int | None,
) -> float:
    """Simulated cross-check of the closed form 1 - exp(-lambda * t).

    Draws exponential inter-arrival times and counts paths with at least one
    arrival inside the horizon. This validates the arrival-process
    implementation numerically; the headline probability stays closed form.
    """
    if paths <= 0:
        raise ValueError("paths must be a positive integer")
    rng = random.Random(random_seed)
    hits = sum(1 for _ in range(paths) if rng.expovariate(lambda_per_year) < horizon_years)
    return hits / paths


def _read_persisted_probability() -> float | None:
    """Current persisted probability for forecast #1 from forecast_state.json."""
    if not FORECAST_STATE_PATH.exists():
        return None
    state = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8"))
    value = state.get(str(FORECAST_ID))
    return float(value) if value is not None else None


def export_controls_poisson_report(
    monte_carlo_paths: int = DEFAULT_MONTE_CARLO_PATHS,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> dict:
    """Compute the complete forecast #1 Poisson report (pure; the TUI renders it).

    The headline P(YES) is closed form -- no simulation is needed for it.
    ``monte_carlo_paths`` only sizes the numerical cross-check of the closed
    form (repo convention: Monte Carlo path count stays an exposed parameter).
    """
    horizon_days = (RESOLUTION_DATE - AS_OF_DATE).days
    horizon_years = horizon_days / DAYS_PER_YEAR
    recent_start = date(
        AS_OF_DATE.year - RECENT_WINDOW_YEARS, AS_OF_DATE.month, AS_OF_DATE.day
    )

    # Episode process (unique publication days) -- the resolution-relevant
    # arrival unit and the headline (see module docstring).
    fit_full = fit_poisson(EPISODE_DATES, OBSERVATION_WINDOW_START, AS_OF_DATE)
    fit_recent = fit_poisson(EPISODE_DATES, recent_start, AS_OF_DATE)
    stability = rate_stability_check(EPISODE_DATES, OBSERVATION_WINDOW_START, AS_OF_DATE)
    # Per-rule process -- kept as an explicit upper bound (treats package
    # members as independent arrivals, which the zero-gap ties contradict).
    fit_full_rules = fit_poisson(TIGHTENING_DATES, OBSERVATION_WINDOW_START, AS_OF_DATE)
    fit_recent_rules = fit_poisson(TIGHTENING_DATES, recent_start, AS_OF_DATE)

    # Decision rule: homogeneity not rejected -> the full-window MLE is the
    # better-estimated rate (more events); rejected -> the process rate moved
    # and only the recent window speaks for the remaining 162 days.
    primary = "full" if stability.homogeneous else "recent"
    primary_fit = fit_full if primary == "full" else fit_recent

    p_full = 1.0 - math.exp(-fit_full.lambda_per_year * horizon_years)
    p_recent = 1.0 - math.exp(-fit_recent.lambda_per_year * horizon_years)
    p_full_rules = 1.0 - math.exp(-fit_full_rules.lambda_per_year * horizon_years)
    p_recent_rules = 1.0 - math.exp(-fit_recent_rules.lambda_per_year * horizon_years)
    primary_p = p_full if primary == "full" else p_recent

    # KS diagnostics for BOTH arrival units: the per-rule check carries the
    # zero-day package ties (penalizing independence at the origin); the
    # episode check is the fit the headline actually relies on.
    rule_gaps = inter_arrival_gaps_days(TIGHTENING_DATES)
    episode_gaps = inter_arrival_gaps_days(EPISODE_DATES)
    ks_rules = ks_exponential_check(rule_gaps, fit_full_rules.lambda_per_year)
    ks = ks_exponential_check(episode_gaps, fit_full.lambda_per_year)

    # Current-drought diagnostic: the wait since the last tightening episode,
    # and how surprising a gap that long is under the fitted episode rate.
    # This is a selection-biased test (we look because the gap is long), so it
    # is reported as context for the 2025 H20/transactional-posture slowdown
    # story -- it does not feed the decision rule.
    drought_days = (AS_OF_DATE - max(EPISODE_DATES)).days
    p_drought = math.exp(-fit_full.lambda_per_year * drought_days / DAYS_PER_YEAR)

    mc_p = _monte_carlo_p_at_least_one(
        primary_fit.lambda_per_year, horizon_years, monte_carlo_paths, random_seed
    )

    persisted = _read_persisted_probability()
    persisted_text = f"{persisted:.1f}%" if persisted is not None else "not persisted"
    divergence_note = (
        f"Poisson episode-arrival model says {primary_p * 100:.1f}% "
        f"({primary}-window episode lambda = {primary_fit.lambda_per_year:.2f}/yr, "
        f"t = {horizon_days}/{DAYS_PER_YEAR} yr; per-rule upper bound "
        f"{p_full_rules * 100:.1f}%) vs {REFERENCE_CLASS_TIER3_PCT:.1f}% "
        f"persisted tier-3 reference-class estimate (currently {persisted_text}): "
        f"{primary_p * 100 - REFERENCE_CLASS_TIER3_PCT:+.1f}pp. The two price "
        "different things -- the tier-3 number is a tightening SHARE of "
        "substantive actions with judgment adjustments (incl. the H20 licensing "
        "reversal, which lives outside the rule docket), while this model prices "
        "the arrival RATE of tightening episodes against a 162-day window. Their "
        "agreement within a few points is mutual corroboration, not redundancy."
    )

    return {
        "forecast_id": FORECAST_ID,
        "as_of_date": AS_OF_DATE.isoformat(),
        "resolution_date": RESOLUTION_DATE.isoformat(),
        "horizon_days": horizon_days,
        "horizon_years": horizon_years,
        "fit_full": fit_full,
        "fit_recent": fit_recent,
        "fit_full_rules": fit_full_rules,
        "fit_recent_rules": fit_recent_rules,
        "stability": stability,
        "ks": ks,
        "ks_rules": ks_rules,
        "qq_points": qq_points(episode_gaps, fit_full.lambda_per_year),
        "p_full_pct": p_full * 100.0,
        "p_recent_pct": p_recent * 100.0,
        "p_full_rules_pct": p_full_rules * 100.0,
        "p_recent_rules_pct": p_recent_rules * 100.0,
        "primary": primary,
        "primary_p_pct": primary_p * 100.0,
        "drought_days": drought_days,
        "drought_survival_pct": p_drought * 100.0,
        "monte_carlo_check_pct": mc_p * 100.0,
        "monte_carlo_paths": monte_carlo_paths,
        "random_seed": random_seed,
        "timeline": _SUBSET_RULES,
        "reference_class_pct": REFERENCE_CLASS_TIER3_PCT,
        "persisted_pct": persisted,
        "divergence_note": divergence_note,
        "publication_date_caveat": PUBLICATION_DATE_CAVEAT,
    }


_CATEGORY_STYLES = {"tightening": "red", "loosening": "green", "noise": "dim"}


def print_report(report: dict, console: Console | None = None) -> None:
    """Pretty-print the full report with rich; no side effects beyond printing."""
    console = console or Console()
    console.print(Panel.fit(
        "[bold]Forecast #1: BIS China chip export controls -- Poisson point process[/bold]\n"
        f"P(YES) = 1 - exp(-lambda t), t = {report['horizon_days']}/{DAYS_PER_YEAR} yr "
        f"= {report['horizon_years']:.4f} yr | as of {report['as_of_date']}, "
        f"resolves {report['resolution_date']}",
        border_style="cyan",
    ))

    fits = Table(title="Homogeneous Poisson MLE fits (lambda = n / years)", box=box.SIMPLE_HEAVY)
    fits.add_column("Arrival unit / window")
    fits.add_column("Span")
    fits.add_column("Events", justify="right")
    fits.add_column("Years", justify="right")
    fits.add_column("lambda/yr", justify="right")
    fits.add_column("P(>=1 event)", justify="right")
    for label, fit, p_pct, is_primary in (
        ("episodes, full", report["fit_full"], report["p_full_pct"], report["primary"] == "full"),
        ("episodes, recent 24mo", report["fit_recent"], report["p_recent_pct"], report["primary"] == "recent"),
        ("per-rule, full (upper bound)", report["fit_full_rules"], report["p_full_rules_pct"], False),
        ("per-rule, recent 24mo", report["fit_recent_rules"], report["p_recent_rules_pct"], False),
    ):
        marker = " [bold cyan]<- primary[/bold cyan]" if is_primary else ""
        fits.add_row(
            label,
            f"{fit.window_start} .. {fit.window_end}",
            str(fit.n_events),
            f"{fit.years:.3f}",
            f"{fit.lambda_per_year:.3f}",
            f"{p_pct:.1f}%{marker}",
        )
    console.print(fits)
    console.print(
        "[dim]Episodes = unique tightening publication days (same-day rule "
        "packages collapse to one arrival; P(>=1 rule) = P(>=1 episode), so the "
        "per-rule fit is an upper bound that assumes package members arrive "
        "independently).[/dim]"
    )

    stability = report["stability"]
    per_year = Table(title="Tightening events per year", box=box.SIMPLE)
    per_year.add_column("Year")
    per_year.add_column("Events", justify="right")
    per_year.add_column("")
    for year, count in stability.per_year_counts:
        note = " (partial: through as-of date)" if year == AS_OF_DATE.year else ""
        per_year.add_row(str(year), str(count), "█" * count + note)
    console.print(per_year)

    verdict = (
        "[green]homogeneity NOT rejected -> full-window rate is primary[/green]"
        if stability.homogeneous
        else "[yellow]homogeneity REJECTED -> recent-window rate is primary[/yellow]"
    )
    console.print(
        f"Rate stability (split at {stability.split_date}): "
        f"{stability.first_half_events} vs {stability.second_half_events} events "
        f"of {stability.n_events}; exact two-sided Binomial(n, "
        f"{stability.binomial_p_success:.2f}) p = {stability.p_value:.3f} "
        f"(alpha = {stability.alpha}) -> {verdict}"
    )

    ks = report["ks"]
    ks_rules = report["ks_rules"]
    console.print(
        f"KS, episode gaps vs Exponential(episode lambda): D_n = {ks.d_statistic:.3f} over "
        f"{ks.n_gaps} gaps, mean gap {ks.mean_gap_days:.1f}d vs theoretical "
        f"{ks.theoretical_mean_gap_days:.1f}d, asymptotic p ~ {ks.p_value_asymptotic:.3f}\n"
        f"KS, per-rule gaps vs Exponential(rule lambda): D_n = {ks_rules.d_statistic:.3f} over "
        f"{ks_rules.n_gaps} gaps ({ks_rules.n_zero_gaps} zero-day package ties counted as-is), "
        f"asymptotic p ~ {ks_rules.p_value_asymptotic:.3f} -- the ties are why the "
        "episode process carries the headline"
    )
    console.print(
        f"Current drought: {report['drought_days']} days since the last tightening episode "
        f"(2025-10-09); P(a gap this long | episode lambda) ~ "
        f"{report['drought_survival_pct']:.1f}%. [dim]Selection-biased diagnostic, reported as "
        "context for the 2025 H20/transactional-posture slowdown story; the split test above "
        "is the decision-relevant check.[/dim]"
    )
    console.print(
        "[dim]Lambda was estimated from the same events (Lilliefors-type), so the "
        "KS p-value is conservative/approximate. QQ pairs for the TUI: "
        f"{len(report['qq_points'])} points, e.g. first/last = "
        f"({report['qq_points'][0][0]:.1f}d, {report['qq_points'][0][1]:.0f}d) / "
        f"({report['qq_points'][-1][0]:.1f}d, {report['qq_points'][-1][1]:.0f}d).[/dim]"
    )
    console.print(f"[dim]{report['publication_date_caveat']}[/dim]")

    timeline = Table(
        title="Audited China chip subset, 2022-2026 (26 tightening / 2 loosening / 7 noise)",
        box=box.SIMPLE,
    )
    timeline.add_column("Published")
    timeline.add_column("FR doc #")
    timeline.add_column("Category")
    timeline.add_column("Rule")
    for rule in report["timeline"]:
        style = _CATEGORY_STYLES[rule.category]
        timeline.add_row(
            rule.publication_date,
            rule.document_number,
            f"[{style}]{rule.category}[/{style}]",
            rule.short_title,
        )
    console.print(timeline)

    comparison = Table(title="Headline vs persisted", box=box.ROUNDED)
    comparison.add_column("Method")
    comparison.add_column("P(YES)", justify="right")
    comparison.add_row(
        f"Poisson closed form, {report['primary']}-window lambda [bold cyan](headline)[/bold cyan]",
        f"[bold]{report['primary_p_pct']:.1f}%[/bold]",
    )
    comparison.add_row(
        f"Monte Carlo cross-check ({report['monte_carlo_paths']:,} paths, seed {report['random_seed']})",
        f"{report['monte_carlo_check_pct']:.1f}%",
    )
    persisted = report["persisted_pct"]
    comparison.add_row(
        "Persisted tier-3 reference-class estimate (forecast_state.json)",
        f"{persisted:.1f}%" if persisted is not None else "n/a",
    )
    console.print(comparison)
    console.print(report["divergence_note"])


if __name__ == "__main__":
    full_report = export_controls_poisson_report()
    print_report(full_report)
    if "--persist" in sys.argv[1:]:
        headline = round(full_report["primary_p_pct"], 1)
        set_forecast_probability(FORECAST_ID, headline)
        Console().print(f"[bold]Persisted forecast #{FORECAST_ID} probability = {headline}%[/bold]")
