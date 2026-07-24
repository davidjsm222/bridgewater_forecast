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
    6: (+10.0, -12.0, +3.0),
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
    additive_result_pct=35.0,
    factors=(
        LikelihoodFactor(
            name="Fed's active hawkish posture",
            lr=1.40,
            lr_range=(1.15, 1.70),
            rationale=(
                "Forecast #5's authoritative P(>=1 hike in 2026) is 77.5% (HMM blended with CME "
                "FedWatch pricing) and the June 2026 SEP median dot (3.8%) sits above the current "
                "3.625% midpoint. Hiking is the Fed's direct tool for pushing inflation back toward "
                "target."
            ),
            derivation=(
                "Evidence E = the market-corroborated hike odds plus the above-midpoint median dot. "
                "Worlds where December PCE lands at or below 3.5% contain actively-hiking Feds more "
                "often than worlds where it stays above (the causal hike -> disinflation channel). "
                "Discounted for circularity: hawkishness is itself caused by currently-high "
                "inflation, which is evidence for NO -- the posture is expected under both "
                "hypotheses, just more so under YES. 1.40, range 1.15-1.70. The additive +10pp "
                "implied ~1.53 from the same evidence; the Bayesian estimate is slightly more "
                "conservative."
            ),
        ),
        LikelihoodFactor(
            name="Recent trend momentum (wrong direction)",
            lr=0.45,
            lr_range=(0.30, 0.60),
            rationale=(
                "PCE YoY accelerated 2.87 -> 2.87 -> 3.54 -> 3.80 -> 4.07 over the last five "
                "prints; the linear trend projects ~4.49% for Dec 2026. Strongest concrete "
                "evidence against resolution."
            ),
            derivation=(
                "Evidence E = five accelerating prints ending at 4.07 (fred_pcepi.json), 0.57pp "
                "above threshold with ~7 months of prints left. Under YES the December print "
                "requires a genuine turn starting almost immediately; E is much more probable "
                "under NO. Tempered by the fact that turns *follow* run-ups -- conditional on YES "
                "happening at all, a preceding acceleration is common -- so E is not vanishingly "
                "rare under YES. 0.45, range 0.30-0.60 (the additive-implied 0.60 sits inside the "
                "range). VERIFIED 2026-07-23: the historical cross-check's 14 qualifying months "
                "collapse to a SINGLE 2021-22 surge (n = 1 episode; see "
                "pce_momentum_crosscheck()['small_n_verdict']), so the 2/14 month-level frequency "
                "is weak directional corroboration only -- the 0.45 point rests on the reasoning "
                "above, not on a calibrated sample, which is why the additive 35% remains the "
                "persisted authoritative number and the posterior is reported as a sensitivity."
            ),
        ),
        LikelihoodFactor(
            name="Single-print resolution dispersion",
            lr=1.25,
            lr_range=(1.10, 1.45),
            rationale=(
                "Resolution is a single Dec 2026 YoY print, and monthly YoY has swung up to "
                "~0.67pp in one month recently (Feb->Mar 2026). Realized-print volatility puts "
                "real left-tail mass below 3.5% even with the central path above it."
            ),
            derivation=(
                "Evidence E = the realized ~0.67pp single-month YoY swing. With the central path "
                "above the threshold, YES-worlds are disproportionately drawn from high-volatility "
                "worlds (a quiet series ending at ~4.5 cannot resolve YES; a jumpy one can), so "
                "P(E | YES) > P(E | NO). 1.25, range 1.10-1.45."
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
    """How often did an inflation run-up like today's precede a fast decline?

    Evidence months E: PCE YoY at or above 3.5% AND up on the prior print AND
    up at least 0.4pp over the trailing four prints (the shape of the current
    2.87 -> 4.07 run). Success: YoY seven months later had fallen by at least
    the 0.57pp now separating the level from the 3.5% threshold. Small-n by
    construction (the cache holds essentially one full inflation episode,
    2021-22, plus the current one) -- reported as corroboration for the LR
    derivation, never as a standalone frequency.
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
            "Months matching today's run-up shape with a scoreable "
            f"{horizon_months}-month outcome; 'declined' = YoY fell >= {threshold_gap_pp}pp."
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
