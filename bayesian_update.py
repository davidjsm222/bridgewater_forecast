"""
Bayesian reframing of the tier 3 adjustment factors for forecasts #4 and #6.

The additive point-scoring system ("+6pp because X, -5pp because Y") is honest
but mathematically loose: percentage points do not compose -- the same +6pp is
a different evidential weight at a 10% prior than at a 50% prior. The proper
formalism is Bayes' rule in odds form: each named factor becomes a likelihood
ratio LR = P(observed evidence | YES) / P(observed evidence | NO), the prior is
the existing tier 3 base rate, and

    posterior odds = prior odds x LR_1 x LR_2 x ... x LR_k.

The named factors, their rationales, and the underlying data are unchanged from
the tier 3 estimates (forecast_state.json tier3["4"] / tier3["6"],
methodology_notes.md #4 / #6); only the arithmetic that combines them is
reframed. Each LR is estimated as honestly as possible from the data already
gathered, with a reasoned range where a point estimate would be false
precision. For comparison, the module also computes the LR that each additive
step *implied* (by replaying the +/-pp path in odds space), which makes any
disagreement between the two formulations visible factor by factor instead of
hidden in the total.

This module deliberately does NOT model #4 or #6 as a stochastic process:
both are single-event questions whose evidence set is a handful of named
observations, which is exactly the regime where an explicit Bayesian update is
the right level of formality.
"""

import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forecasts import get, set_forecast_probability


DATA_CACHE_DIR = Path(__file__).with_name("data_cache")


def _odds(probability_pct: float) -> float:
    p = probability_pct / 100.0
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be strictly between 0 and 100 to form odds")
    return p / (1.0 - p)


def _pct(odds: float) -> float:
    return odds / (1.0 + odds) * 100.0


@dataclass(frozen=True)
class LikelihoodFactor:
    """One named piece of evidence, expressed as a likelihood ratio.

    ``lr`` is the point estimate of P(evidence | YES) / P(evidence | NO);
    ``lr_range`` is the reasoned low/high band carried through to the posterior
    sensitivity range. ``rationale`` is the original tier 3 factor text (the
    named reasoning is preserved, not replaced); ``derivation`` explains how
    the ratio itself was sized from the real data.
    """

    name: str
    lr: float
    lr_range: tuple[float, float]
    rationale: str
    derivation: str

    def __post_init__(self):
        low, high = self.lr_range
        if not (0 < low <= self.lr <= high):
            raise ValueError(f"LR range {self.lr_range} must bracket the point estimate {self.lr}")


@dataclass(frozen=True)
class BayesianUpdate:
    forecast_id: int
    prior_pct: float
    prior_source: str
    factors: tuple[LikelihoodFactor, ...]
    additive_result_pct: float   # what the additive tier 3 arithmetic produced

    def prior_odds(self) -> float:
        return _odds(self.prior_pct)

    def lr_product(self) -> float:
        product = 1.0
        for factor in self.factors:
            product *= factor.lr
        return product

    def posterior_pct(self) -> float:
        return _pct(self.prior_odds() * self.lr_product())

    def posterior_range_pct(self) -> tuple[float, float]:
        """Sensitivity band: all LRs at their low ends vs all at their highs.

        This is a bounding box, not a distribution -- the factors' errors are
        treated as independent and simultaneously extreme, so the band is
        deliberately wide.
        """
        low_product = 1.0
        high_product = 1.0
        for factor in self.factors:
            low_product *= factor.lr_range[0]
            high_product *= factor.lr_range[1]
        return (_pct(self.prior_odds() * low_product), _pct(self.prior_odds() * high_product))

    def implied_additive_lrs(self) -> list[float]:
        """The LR each additive +/-pp step *implied*, by replaying it in odds.

        The additive system moved the probability from p_i to p_{i+1} by adding
        points; the equivalent multiplicative weight is odds(p_{i+1})/odds(p_i).
        Comparing these to the honestly estimated LRs shows exactly where the
        two formulations disagree.
        """
        implied = []
        running_pct = self.prior_pct
        for factor, signed_pts in zip(self.factors, self._additive_steps()):
            next_pct = running_pct + signed_pts
            implied.append(_odds(next_pct) / _odds(running_pct))
            running_pct = next_pct
        return implied

    def _additive_steps(self) -> list[float]:
        """Signed +/-pp magnitudes of the original tier 3 factors, in order."""
        return list(ADDITIVE_STEPS[self.forecast_id])

    def divergence_pts(self) -> float:
        return self.posterior_pct() - self.additive_result_pct


# The original tier 3 additive magnitudes (forecast_state.json tier3["4"] /
# tier3["6"]), kept in the same order as the LikelihoodFactor tuples below so
# implied_additive_lrs() can replay them step by step.
ADDITIVE_STEPS = {
    4: (+6.0, +6.0, -5.0),
    6: (+6.0, -4.0, +4.0),
}


BAYES_4 = BayesianUpdate(
    forecast_id=4,
    prior_pct=50.0,
    prior_source=(
        "The tier 3 base rate: a deliberate uninformed prior on beating a credible, "
        "forward-looking expert central estimate (Bridgewater's ~150bp), absent specific "
        "evidence of bias. See methodology_notes.md #4."
    ),
    additive_result_pct=57.0,
    factors=(
        LikelihoodFactor(
            name="Q1 2026 real investment acceleration",
            lr=1.30,
            lr_range=(1.10, 1.60),
            rationale=(
                "Real information-processing investment jumped QoQ ($1,564B Q4'25 -> $1,673B "
                "Q1'26 SAAR, ~+7%). Genuine momentum, but a single volatile, seasonally-strong "
                "quarter, not proof of a full-year trend."
            ),
            derivation=(
                "Evidence E = the +7.0% QoQ Q1'26 print (fred_information_processing_investment.json). "
                "A print this strong is clearly more likely in worlds where 2027 AI capex beats 150bp "
                "than where it falls short -- but Q1 prints run seasonally hot (see the Q1 seasonality "
                "cross-check computed from the same cache), so E is fairly likely under NO as well. "
                "That caps the ratio well below the ~2x a naive read of '+7%!' would suggest: 1.30, "
                "range 1.10-1.60."
            ),
        ),
        LikelihoodFactor(
            name="Structures / physical-buildout boom",
            lr=1.25,
            lr_range=(1.00, 1.55),
            rationale=(
                "Nonresidential structures/capex buildout is visibly elevated (data-center and "
                "CHIPS-fab construction), but BEA structures data mixes in substantial non-AI "
                "construction and cannot isolate data centers."
            ),
            derivation=(
                "Evidence E = the elevated nonresidential-structures contribution "
                "(A009RY2A224NBEA, bundled in the cached contribution series). The measurement "
                "contamination cuts both ways under Bayes: because the series would look elevated "
                "even if the non-AI share were doing the work, P(E | NO) is not small, so the ratio "
                "is capped at 1.25 with the low end at 1.00 (possibly no evidential value at all)."
            ),
        ),
        LikelihoodFactor(
            name="Resolution metric narrower than the estimate's scope",
            lr=0.80,
            lr_range=(0.65, 0.95),
            rationale=(
                "The resolution line is the BEA IP-equipment/software contribution (historically "
                "~0.4pp), narrower than the total AI-capex scope Bridgewater's 150bp covers; "
                "clearing 150bp on the narrow measured line is a harder bar."
            ),
            derivation=(
                "Not observational evidence but a hypothesis-scope correction, mapped onto the "
                "odds as an LR < 1: P(the narrow measured line clears 150bp | the broad AI-capex "
                "beat happens) < 1. ASSUMED mapping -- the 0.80 (range 0.65-0.95) encodes the same "
                "definitional headwind the additive -5pp did, stated multiplicatively; genuine "
                "resolution-scope ambiguity is why the range is wide."
            ),
        ),
    ),
)


BAYES_6 = BayesianUpdate(
    forecast_id=6,
    prior_pct=34.0,
    prior_source=(
        "The tier 3 base rate: midpoint of the 21-47% bound on the share of the 19 FOMC "
        "participants projecting 2026 PCE at or below 3.5% (June 2026 SEP). See "
        "methodology_notes.md #6 and fomc_history.CURRENT_SEP_PCE_PROJECTION."
    ),
    additive_result_pct=40.0,
    factors=(
        LikelihoodFactor(
            name="Fed's active hawkish posture",
            lr=1.19,
            lr_range=(1.00, 1.45),
            rationale=(
                "The June 2026 SEP median dot (3.8%) sits above the current 3.625% midpoint "
                "(~one more hike signalled) and forecast #5 prices P(>=1 hike in 2026) at 62.6% "
                "(pure HMM; the market-blend layer that put it at 77.5% was retired 2026-07-29). "
                "Hiking is the Fed's direct tool for pushing inflation back toward target."
            ),
            derivation=(
                "Derived from the resized additive step rather than picked. The +6pp step from "
                "the 34% base implies LR = odds(40)/odds(34) = 1.29. The previous config applied "
                "a deliberate circularity discount to its step-implied LR (1.40 against an "
                "implied 1.53, a x0.92 haircut: hawkishness is itself caused by currently-high "
                "inflation, so the posture is expected under both hypotheses, just more so under "
                "YES). That discount's premise survives the resize, so the same x0.92 applies: "
                "1.29 x 0.92 = 1.19, range 1.00-1.45. The old 1.40 also anchored to #5 at 77.5% "
                "-- the market blend retired 2026-07-29 -- so it inherited the same stale premise "
                "as the additive +10pp and falls with it."
            ),
        ),
        LikelihoodFactor(
            name="Recent trend momentum (wrong direction)",
            lr=0.85,
            lr_range=(0.70, 1.00),
            rationale=(
                "The five-print acceleration (2.87 -> 2.87 -> 3.54 -> 3.80 -> 4.07) broke with "
                "June 2026: headline PCE fell 0.1% on the month (first monthly decline since "
                "April 2020), YoY 4.08% -> 3.67% (BEA, 2026-07-30). The prints now track the SEP "
                "anchor's implied deceleration path; what survives against YES is the ~0.2pp "
                "residual gap to 3.5%, the energy-driven (and since-lapsed-ceasefire) nature of "
                "the June relief, and core falling only a tenth."
            ),
            derivation=(
                "Derived from the resized additive step. The -4pp step from 40% implies LR = "
                "odds(36)/odds(40) = 0.84; rounded to 0.85, range 0.70-1.00. The previous config "
                "went materially harsher than its step (0.45 against an implied 0.60, x0.75) on "
                "the strength of the unbroken run-up -- an extra severity whose empirical "
                "corroboration was already found wanting on 2026-07-23 (the cross-check's 14 "
                "qualifying months collapse to a single 2021-22 surge, n = 1 episode; see "
                "pce_momentum_crosscheck()['small_n_verdict']) and whose premise the June print "
                "removed outright, so no extra harshening is applied now. The range's 1.00 end "
                "covers the reading that June's energy-driven swing leaves the momentum evidence "
                "roughly uninformative; 0.70 covers relapse (the ceasefire behind the energy "
                "relief has lapsed, and the level still sits above threshold)."
            ),
        ),
        LikelihoodFactor(
            name="Single-print resolution dispersion",
            lr=1.19,
            lr_range=(1.05, 1.40),
            rationale=(
                "Resolution is a single Dec 2026 YoY print, the central path now sits roughly a "
                "tenth above the threshold (SEP median 3.6% vs 3.5%), and realized single-month "
                "moves are the same order as that whole gap: June -0.41pp, Feb->Mar 2026 "
                "+0.67pp, MoM stdev of the YoY series ~0.21-0.25pp (fred_pcepi.json)."
            ),
            derivation=(
                "Derived from the resized additive step. The +4pp step from 36% implies LR = "
                "odds(40)/odds(36) = 1.19, range 1.05-1.40. The previous config sized its LR "
                "slightly above its step's implied value (1.25 vs 1.14, x1.10) because the +3pp "
                "step under-conveyed the volatility evidence; the step itself is now +4pp, which "
                "absorbs exactly that, so applying the upsize again would double-count and the "
                "implied value is taken as-is. Directionally: with the central path just above "
                "the bar, YES-worlds are disproportionately high-volatility worlds, so "
                "P(E | YES) > P(E | NO)."
            ),
        ),
    ),
)


BAYES_UPDATES = {4: BAYES_4, 6: BAYES_6}


def q1_seasonality_crosscheck() -> dict | None:
    """Average QoQ growth of real IP investment by calendar quarter.

    Grounds the 'Q1 prints run seasonally hot' claim in the LR derivation for
    #4's first factor, from the same cached FRED series the factor cites.
    Returns None when the cache is unavailable (the LRs stand on their
    documented reasoning either way; this is corroboration, not an input).
    """
    path = DATA_CACHE_DIR / "fred_information_processing_investment.json"
    if not path.exists():
        return None
    observations = json.loads(path.read_text(encoding="utf-8")).get("observations", [])
    if len(observations) < 8:
        return None
    by_quarter: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
    for previous, current in zip(observations, observations[1:]):
        quarter = (int(current["date"][5:7]) - 1) // 3 + 1
        by_quarter[quarter].append((current["value"] / previous["value"] - 1) * 100)
    means = {q: sum(v) / len(v) for q, v in by_quarter.items() if v}
    overall = sum(sum(v) for v in by_quarter.values()) / sum(len(v) for v in by_quarter.values())
    return {
        "mean_qoq_pct_by_quarter": {q: round(m, 2) for q, m in means.items()},
        "overall_mean_qoq_pct": round(overall, 2),
        "latest_q1_2026_qoq_pct": round(
            (observations[-1]["value"] / observations[-2]["value"] - 1) * 100, 2
        ),
    }


def pce_momentum_crosscheck(
    threshold_gap_pp: float = 0.57, horizon_months: int = 7
) -> dict | None:
    """How often did an inflation run-up like the Jan-May 2026 one precede a fast decline?

    ARCHIVED QUERY (kept verbatim, defaults frozen at the May-2026 vintage): this
    grounded the old -12pp / LR 0.45 momentum sizing while the run-up was intact.
    Evidence months E: PCE YoY at or above 3.5% AND up on the prior print AND
    up at least 0.4pp over the trailing four prints (the shape of the then-current
    2.87 -> 4.07 run). Success: YoY seven months later had fallen by at least the
    0.57pp then separating the level from the 3.5% threshold. The June 2026 print
    (-0.41pp MoM in YoY terms) broke the run-up, so the current month no longer
    matches the evidence filter -- the query is retained as the documented record
    behind the retired sizing, plus its small-n verdict (a single 2021-22 surge,
    n = 1 episode), which is what justified NOT carrying extra momentum severity
    into the resized LR. Never a standalone frequency.
    """
    path = DATA_CACHE_DIR / "fred_pcepi.json"
    if not path.exists():
        return None
    observations = [
        o for o in json.loads(path.read_text(encoding="utf-8")).get("observations", [])
        if o.get("year_over_year_pct") is not None
    ]
    yoy = [o["year_over_year_pct"] for o in observations]
    dates = [o["date"][:7] for o in observations]
    episode_months = []
    successes = []
    for t in range(4, len(yoy)):
        if yoy[t] >= 3.5 and yoy[t] > yoy[t - 1] and (yoy[t] - yoy[t - 4]) >= 0.4:
            if t + horizon_months < len(yoy):
                episode_months.append(dates[t])
                successes.append(yoy[t + horizon_months] <= yoy[t] - threshold_gap_pp)
    if not episode_months:
        return {"episode_months": [], "n_episodes": 0, "n_declined": 0}
    # Collapse the qualifying months into distinct consecutive runs -- the
    # honest unit of independence. Verified 2026-07-23: the 14 qualifying
    # months form essentially ONE surge (2021-04..2022-03 and 2022-05..2022-06,
    # split only by the single non-qualifying month 2022-04), and the 2
    # "declined" months are simply the two sampled months adjacent to that
    # surge's mid-2022 peak. As an independent reference class this is n = 1
    # episode, so the month-level 2/14 frequency must NOT be read as a
    # calibrated probability -- it is weak, directional corroboration only.
    runs: list[list[str]] = [[episode_months[0]]]
    for previous, current in zip(episode_months, episode_months[1:]):
        prev_index = int(previous[:4]) * 12 + int(previous[5:7])
        curr_index = int(current[:4]) * 12 + int(current[5:7])
        if curr_index - prev_index == 1:
            runs[-1].append(current)
        else:
            runs.append([current])
    return {
        "episode_months": episode_months,
        "n_episodes": len(episode_months),
        "n_declined": sum(successes),
        "distinct_runs": [(run[0], run[-1], len(run)) for run in runs],
        "n_distinct_surges": len(runs),
        "small_n_verdict": (
            "The qualifying months collapse to a single 2021-22 inflation surge "
            "(the 2022-04 break is one month of noise); effective n = 1 episode. "
            "Too thin to serve as an independent reference class -- supports "
            "'LR below 1' directionally but cannot arbitrate 0.45 vs 0.60."
        ),
        "note": (
            "Months matching the Jan-May 2026 run-up shape (broken by the June 2026 print; "
            f"archived query) with a scoreable {horizon_months}-month outcome; "
            f"'declined' = YoY fell >= {threshold_gap_pp}pp."
        ),
    }


def sep_print_distribution_route(
    threshold_pct: float = 3.5,
    sep_median_pct: float = 3.6,
    path_sd_candidates: tuple[float, ...] = (0.10, 0.30, 0.35),
) -> dict | None:
    """Third, scheme-independent route to P(YES) for #6 (added 2026-07-31).

    The additive arm and the Bayesian arm share the same 34% base rate and the
    same three pieces of evidence, so their agreement is weaker than it looks.
    This route uses neither scheme: treat the December print as
    N(SEP median, path_sd^2 + print_sd^2) -- dispersion in where the true
    central path lands, plus noise in the single monthly print that resolves
    the forecast -- and read off P(print <= threshold).

    path_sd candidates come from the June 2026 SEP's published dispersion read
    two defensible ways: the 3.5-3.7 central tendency as roughly +/-1 sd (0.10)
    and the 2.7-4.1 full range of 19 participants as roughly +/-2 to +/-2.3 sd
    (0.35 and 0.30). print_sd is estimated from realized month-over-month moves
    of the YoY series in the cache (trailing 12m/24m/36m standard deviations),
    NOT assumed. Reported as a grid because single-point precision would be
    false; the central cell is the one pairing the range-based path sd with the
    trailing-24m print sd.
    """
    path = DATA_CACHE_DIR / "fred_pcepi.json"
    if not path.exists():
        return None
    observations = [
        o for o in json.loads(path.read_text(encoding="utf-8")).get("observations", [])
        if o.get("year_over_year_pct") is not None
    ]
    yoy = [o["year_over_year_pct"] for o in observations]
    deltas = [b - a for a, b in zip(yoy, yoy[1:])]
    if len(deltas) < 36:
        return None
    print_sds = {
        f"trailing_{months}m": round(statistics.stdev(deltas[-months:]), 3)
        for months in (12, 24, 36)
    }
    normal = statistics.NormalDist()
    grid = []
    for path_sd in path_sd_candidates:
        for label, print_sd in print_sds.items():
            total_sd = (path_sd**2 + print_sd**2) ** 0.5
            grid.append({
                "path_sd": path_sd,
                "print_sd_source": label,
                "print_sd": print_sd,
                "total_sd": round(total_sd, 3),
                "p_yes_pct": round(
                    normal.cdf((threshold_pct - sep_median_pct) / total_sd) * 100, 1
                ),
            })
    p_values = [cell["p_yes_pct"] for cell in grid]
    central = next(
        cell for cell in grid
        if cell["path_sd"] == 0.30 and cell["print_sd_source"] == "trailing_24m"
    )
    return {
        "center_pct": sep_median_pct,
        "threshold_pct": threshold_pct,
        "print_sd_realized": print_sds,
        "grid": grid,
        "p_yes_range_pct": (min(p_values), max(p_values)),
        "central_p_yes_pct": central["p_yes_pct"],
        "note": (
            "Independent of both the additive and Bayesian arms (shares neither their "
            "base-rate arithmetic nor their factor list beyond the SEP itself). "
            "Model: Dec print ~ N(SEP median, path_sd^2 + print_sd^2)."
        ),
    }


def bayesian_report(forecast_id: int) -> dict:
    """Everything the TUI needs to render the Bayesian formulation."""
    update = BAYES_UPDATES[forecast_id]
    implied = update.implied_additive_lrs()
    low, high = update.posterior_range_pct()
    return {
        "forecast_id": forecast_id,
        "prior_pct": update.prior_pct,
        "prior_source": update.prior_source,
        "prior_odds": round(update.prior_odds(), 4),
        "factors": [
            {
                "name": factor.name,
                "lr": factor.lr,
                "lr_range": factor.lr_range,
                "implied_additive_lr": round(implied_lr, 3),
                "additive_step_pts": step,
                "rationale": factor.rationale,
                "derivation": factor.derivation,
            }
            for factor, implied_lr, step in zip(update.factors, implied, update._additive_steps())
        ],
        "lr_product": round(update.lr_product(), 4),
        "posterior_odds": round(update.prior_odds() * update.lr_product(), 4),
        "posterior_pct": round(update.posterior_pct(), 1),
        "posterior_range_pct": (round(low, 1), round(high, 1)),
        "additive_result_pct": update.additive_result_pct,
        "divergence_pts": round(update.divergence_pts(), 1),
        "crosscheck": (
            q1_seasonality_crosscheck() if forecast_id == 4 else pce_momentum_crosscheck()
        ),
        "independent_route": (
            sep_print_distribution_route() if forecast_id == 6 else None
        ),
    }


def print_report(forecast_id: int, console: Console | None = None) -> None:
    console = console or Console()
    report = bayesian_report(forecast_id)
    forecast = get(forecast_id)
    console.print(Panel.fit(
        f"[bold]Forecast #{forecast_id}: {forecast.title} -- Bayesian update[/bold]\n"
        f"Prior {report['prior_pct']:.0f}% (odds {report['prior_odds']:.3f}) x LR product "
        f"{report['lr_product']:.3f} -> posterior [bold]{report['posterior_pct']:.1f}%[/bold] "
        f"(range {report['posterior_range_pct'][0]:.0f}-{report['posterior_range_pct'][1]:.0f}%)",
        border_style="cyan",
    ))
    table = Table(title="Likelihood ratios vs the additive steps they reframe", box=box.SIMPLE_HEAVY)
    table.add_column("Factor")
    table.add_column("LR (range)", justify="right")
    table.add_column("Additive step", justify="right")
    table.add_column("Implied LR", justify="right")
    for factor in report["factors"]:
        table.add_row(
            factor["name"],
            f"{factor['lr']:.2f} ({factor['lr_range'][0]:.2f}-{factor['lr_range'][1]:.2f})",
            f"{factor['additive_step_pts']:+.0f}pp",
            f"{factor['implied_additive_lr']:.2f}",
        )
    console.print(table)
    for factor in report["factors"]:
        console.print(f"[bold]{factor['name']}[/bold]: {factor['derivation']}")
    if report["crosscheck"]:
        console.print(f"[dim]Data cross-check: {report['crosscheck']}[/dim]")
    if report.get("independent_route"):
        route = report["independent_route"]
        console.print(
            f"[bold]Independent SEP-distribution route[/bold] (shares neither arm's scheme): "
            f"P(Dec print <= {route['threshold_pct']}) = "
            f"{route['p_yes_range_pct'][0]:.1f}-{route['p_yes_range_pct'][1]:.1f}% across the "
            f"documented grid, central {route['central_p_yes_pct']:.1f}% "
            f"(path sd 0.30, print sd {route['print_sd_realized']['trailing_24m']:.3f} realized)"
        )
    persisted = forecast.probability
    console.print(
        f"Posterior [bold]{report['posterior_pct']:.1f}%[/bold] vs additive tier 3 "
        f"[bold]{report['additive_result_pct']:.1f}%[/bold] "
        f"(divergence {report['divergence_pts']:+.1f}pp); currently persisted: {persisted}%"
    )
    if abs(report["divergence_pts"]) > 3:
        console.print(
            "[yellow]Material divergence: the multiplicative recombination disagrees with "
            "the additive arithmetic. See the per-factor implied-LR column for where.[/yellow]"
        )


if __name__ == "__main__":
    console = Console()
    for forecast_id in (4, 6):
        print_report(forecast_id, console)
        console.print()
    if "--persist" in sys.argv:
        # Persistence is an explicit, deliberate act: the maintainer decides per
        # forecast whether the posterior replaces the additive number (the
        # divergence rule in methodology_notes.md governs).
        for forecast_id in (4, 6):
            set_forecast_probability(
                forecast_id, round(BAYES_UPDATES[forecast_id].posterior_pct(), 1)
            )
        console.print("[bold]Persisted Bayesian posteriors for #4 and #6.[/bold]")
