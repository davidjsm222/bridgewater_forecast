"""
Tier 1: quantitative models grounded in a real data-generating process.
Originally market-derived signals only (Fed funds futures, EIA price data);
the tier now also covers the fitted process models added in the quantitative
upgrade -- the Poisson point process (export_controls_poisson.py), competing
risks (nuclear_competing_risks.py), compound Poisson (sovereign_ai_jumps.py),
OU simulation (electricity_simulation.py), and backlog model
(datacenter_backlog.py) -- each living in its own module. This module holds
the Fed posture HMM (forecast #5) and the legacy market helpers. The job here
isn't prediction from scratch, it's correctly translating a fitted or
market-implied process into the specific yes/no threshold the forecast asks
about.
"""

import json
import random
import sys
from dataclasses import dataclass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forecasts import FORECAST_STATE_PATH, set_forecast_probability
from fomc_history import (
    ACTIONS,
    CURRENT_ANNUALIZED_CHANGE_BPS,
    CURRENT_POSTURE,
    DATA_GAPS,
    FOMC_HISTORY,
    POSTURE_STATES,
    ROUGHLY_FLAT_THRESHOLD_BPS,
)


REMAINING_2026_MEETING_DATES = (
    "2026-09-16",
    "2026-10-28",
    "2026-12-09",
)
DEFAULT_MONTE_CARLO_PATHS = 10_000
DEFAULT_RANDOM_SEED = 20260716

# ---------------------------------------------------------------------------
# ARCHIVED 2026-07-29 -- superseded, retained for provenance (same archival
# pattern used for the superseded judgment estimates in methodology_notes.md).
#
# The July 29, 2026 FOMC meeting RESOLVED AS A HOLD: the target range was left
# at 3.50-3.75%, voted 9-3, with Hammack, Kashkari and Logan dissenting in
# favour of +25bp. The meeting therefore leaves the forward sample space and
# enters the HMM training set (fomc_history._RAW_MEETINGS).
#
# The 10.7% below was the PRE-MEETING MARKET PRICE as of 2026-07-21, used to pin
# July's simulated hike odds. Two things are worth recording about it:
#   * It was materially too low by the time the meeting arrived. CME FedWatch
#     had roughly a 1-in-3 chance of a July hike on the morning of the meeting
#     (CNBC, 2026-07-29), and Kalshi/Polymarket had repriced to ~55% odds of a
#     *September* hike pre-announcement. An eight-day-old pin on a fast-moving
#     meeting decayed badly.
#   * It was nonetheless directionally right: the Fed held. Prediction markets
#     were closer to the outcome than CME FedWatch's 33%, which is the same
#     ordering seen in the pre-meeting divergence noted in the original comment.
# See methodology_notes.md, forecast #5, "The July 29, 2026 update".
ARCHIVED_JULY_29_HIKE_PROBABILITY = 0.107
ARCHIVED_JULY_29_AS_OF = "2026-07-21"
ARCHIVED_JULY_29_SOURCE = "Polymarket ($78M market) 10.7%; rateprobability.com 9.6%"
ARCHIVED_JULY_29_OVERRIDES = {"2026-07-29": ARCHIVED_JULY_29_HIKE_PROBABILITY}
ARCHIVED_JULY_29_OUTCOME = "hold (9-3, three dissents preferring +25bp)"
# ---------------------------------------------------------------------------

# Per-meeting emission overrides. The July pin above was justified by the meeting
# being IMMINENT and precisely priced. Nothing on the remaining calendar meets
# that bar: September is 48 days out, and October/December are thinly traded. The
# live per-meeting reads below are therefore recorded as a CROSS-CHECK only and
# are deliberately NOT pinned into the simulation -- the HMM stays a genuinely
# independent historical anchor. With the tier-3 blend retired, no market price
# enters forecast #5 through any channel at all, which is what makes the HMM's
# agreement with the direct market meaningful rather than circular.
MEETING_HIKE_PROBABILITY_OVERRIDES: dict[str, float] = {}

# Live per-meeting P(hike) reads, 2026-07-29 ~15:25-15:35 ET (post-decision),
# from the Kalshi (KXFEDDECISION-*) and Polymarket public APIs; bucket mid-prices
# normalised across each meeting's mutually-exclusive outcomes. Recorded so that
# the model's "September is the live meeting" assumption is directly checkable.
MARKET_PER_MEETING_HIKE_PROBABILITY = {
    "2026-09-16": 0.525,   # Kalshi 52.5% / Polymarket 52.4%; cf. CME FedWatch 72%
    "2026-10-28": 0.263,   # Kalshi 27.6% / Polymarket 25.1%
    "2026-12-09": 0.317,   # Kalshi only; Polymarket has no December meeting market
}
MARKET_PER_MEETING_AS_OF = "2026-07-29T15:35-04:00"

# CROSS-CHECK (not an input): the reported CME FedWatch read for September.
# The FedWatch tool itself was not directly reachable -- cmegroup.com timed out
# and the rendered page never loaded the probability widget -- so this is the
# figure as reported by financial press quoting the tool, not a first-party
# scrape, and it is labeled as such wherever it is displayed.
#
# It disagrees sharply with the real-money prediction markets above: 72% versus
# Kalshi 52.5% / Polymarket 52.4% for the same meeting, a ~20pp gap between two
# sources both quoting live pricing within the same hour. That is the same
# CME-runs-hot-versus-prediction-markets ordering seen pre-July (FedWatch 33% vs
# Polymarket 10.7%, where the markets were closer to the realized hold). Kept
# visible precisely because it is the discordant read.
MARKET_CME_FEDWATCH_SEPTEMBER_HIKE_PROBABILITY = 0.72
MARKET_CME_FEDWATCH_AS_OF = "2026-07-29 (~1h post-decision)"
MARKET_CME_FEDWATCH_SOURCE = (
    "CME Group FedWatch as reported by Kiplinger's live FOMC blog, 2026-07-29 "
    "(72% for a September +25bp, up from ~55% pre-announcement and ~30% a month "
    "earlier); corroborated by TheStreet. Tool not reachable first-party."
)

# CROSS-CHECK (not an input): a DIRECT market on forecast #5's exact question
# ("YES if the fed funds target range is raised at any 2026 meeting"). Polymarket
# "Fed rate hike in 2026?" resolves YES if the upper bound of the target range is
# increased at any point between 2026-01-01 and the December 2026 meeting -- the
# same event, not a proxy.
#
# This was briefly the anchor of a tier-3 blend layer (which itself replaced an
# unverifiable 87.1% CME cumulative figure). The blend is now RETIRED -- see the
# archive block above forecast5 persistence below. The 62.5% is retained as a
# displayed cross-check against the HMM's independent 62.6%, not as an input.
MARKET_CUMULATIVE_HIKE_PROBABILITY = 0.625
MARKET_CUMULATIVE_AS_OF = "2026-07-29T15:35-04:00"
MARKET_CUMULATIVE_SOURCE = (
    "Polymarket 'Fed rate hike in 2026?' (bid 0.62 / ask 0.63, $5.16M volume), "
    "post-decision 2026-07-29 15:35 ET, via gamma-api.polymarket.com"
)


@dataclass
class FedMeeting:
    date: str
    p_hike: float   # market-implied probability of a hike at this meeting
    p_hold: float
    p_cut: float

    def __post_init__(self):
        total = self.p_hike + self.p_hold + self.p_cut
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Meeting {self.date} probabilities sum to {total}, not 1.0")


def p_at_least_one_hike(meetings: list[FedMeeting]) -> float:
    """
    Chain per-meeting hold probabilities to get P(at least one hike across all
    meetings) = 1 - P(no hike at every single meeting).
    This treats meetings as independent, which is a simplification worth
    flagging explicitly in the methodology writeup -- in reality a hike at one
    meeting changes the conditional odds at the next. Good enough for a
    first-pass anchor; note the limitation, don't hide it.
    """
    p_no_hike_all = 1.0
    for m in meetings:
        p_no_hike_this_meeting = m.p_hold + m.p_cut
        p_no_hike_all *= p_no_hike_this_meeting
    return 1 - p_no_hike_all


@dataclass(frozen=True)
class FedPostureHMM:
    transition_matrix: dict[str, dict[str, float]]
    emission_matrix: dict[str, dict[str, float]]
    initial_state_distribution: dict[str, float]
    training_meetings: int


@dataclass(frozen=True)
class HikeSimulationResult:
    paths: int
    meeting_dates: tuple[str, ...]
    probability_at_least_one_hike: float
    hike_count_distribution: dict[str, float]
    raw_counts: dict[str, int]
    random_seed: int | None


def _probabilities_from_counts(counts: dict[str, int], labels: tuple[str, ...]) -> dict[str, float]:
    total = sum(counts[label] for label in labels)
    if total == 0:
        raise ValueError(f"Cannot estimate probabilities from an empty count row: {counts}")
    return {label: counts[label] / total for label in labels}


def estimate_fed_posture_hmm(history=FOMC_HISTORY) -> FedPostureHMM:
    """Estimate transition and emission probabilities from labeled FOMC history."""
    if len(history) < 2:
        raise ValueError("Need at least two historical meetings to estimate the HMM")

    transition_counts = {
        state: {next_state: 0 for next_state in POSTURE_STATES}
        for state in POSTURE_STATES
    }
    for current, following in zip(history, history[1:]):
        transition_counts[current.posture][following.posture] += 1

    emission_counts = {
        state: {action: 0 for action in ACTIONS}
        for state in POSTURE_STATES
    }
    for meeting in history:
        emission_counts[meeting.posture][meeting.action] += 1

    transition_matrix = {
        state: _probabilities_from_counts(transition_counts[state], POSTURE_STATES)
        for state in POSTURE_STATES
    }
    emission_matrix = {
        state: _probabilities_from_counts(emission_counts[state], ACTIONS)
        for state in POSTURE_STATES
    }
    initial_state_distribution = {
        state: 1.0 if state == CURRENT_POSTURE else 0.0
        for state in POSTURE_STATES
    }
    return FedPostureHMM(
        transition_matrix=transition_matrix,
        emission_matrix=emission_matrix,
        initial_state_distribution=initial_state_distribution,
        training_meetings=len(history),
    )


def _sample_label(probabilities: dict[str, float], rng: random.Random) -> str:
    draw = rng.random()
    cumulative = 0.0
    last_label = ""
    for label, probability in probabilities.items():
        cumulative += probability
        last_label = label
        if draw <= cumulative:
            return label
    return last_label


def p_at_least_one_hike_hmm(
    model: FedPostureHMM,
    meeting_dates: tuple[str, ...] = REMAINING_2026_MEETING_DATES,
    simulations: int = DEFAULT_MONTE_CARLO_PATHS,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
    hike_probability_overrides: dict[str, float] | None = None,
) -> HikeSimulationResult:
    """Monte Carlo P(at least one hike), preserving posture state-dependence.

    ``hike_probability_overrides`` pins P(hike) for specific meetings to an
    externally-supplied value (e.g. a live-market read for an imminent meeting)
    instead of drawing the action from the HMM emission matrix. The posture chain
    still advances through an overridden meeting, so downstream meetings remain
    state-dependent. Defaults to ``MEETING_HIKE_PROBABILITY_OVERRIDES``.
    """
    if simulations <= 0:
        raise ValueError("simulations must be a positive integer")
    if hike_probability_overrides is None:
        hike_probability_overrides = MEETING_HIKE_PROBABILITY_OVERRIDES
    rng = random.Random(random_seed)
    buckets = {"0 hikes": 0, "1 hike": 0, "2+ hikes": 0}

    for _ in range(simulations):
        posture = _sample_label(model.initial_state_distribution, rng)
        hikes = 0
        for meeting_date in meeting_dates:
            posture = _sample_label(model.transition_matrix[posture], rng)
            override = hike_probability_overrides.get(meeting_date)
            if override is not None:
                hiked = rng.random() < override
            else:
                hiked = _sample_label(model.emission_matrix[posture], rng) == "hike"
            if hiked:
                hikes += 1
        if hikes == 0:
            buckets["0 hikes"] += 1
        elif hikes == 1:
            buckets["1 hike"] += 1
        else:
            buckets["2+ hikes"] += 1

    distribution = {label: count / simulations for label, count in buckets.items()}
    return HikeSimulationResult(
        paths=simulations,
        meeting_dates=meeting_dates,
        probability_at_least_one_hike=1.0 - distribution["0 hikes"],
        hike_count_distribution=distribution,
        raw_counts=buckets,
        random_seed=random_seed,
    )


def _matrix_table(title: str, matrix: dict[str, dict[str, float]], columns: tuple[str, ...]) -> Table:
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("Posture state")
    for column in columns:
        table.add_column(column, justify="right")
    for state in POSTURE_STATES:
        table.add_row(state, *(f"{matrix[state][column]:.3f}" for column in columns))
    return table


def print_hmm_report(
    model: FedPostureHMM,
    result: HikeSimulationResult,
    flat_probability: float,
    console: Console | None = None,
) -> None:
    """Render matrices, side-by-side comparison, and hike-count histogram."""
    console = console or Console()
    console.print(Panel.fit(
        "[bold]Forecast #5: Fed posture HMM + Monte Carlo[/bold]\n"
        f"Training meetings: {model.training_meetings} | "
        f"Flat threshold: ±{ROUGHLY_FLAT_THRESHOLD_BPS:.0f} bps | "
        f"Current posture: {CURRENT_POSTURE} ({CURRENT_ANNUALIZED_CHANGE_BPS:+.2f} bps annualized)",
        border_style="cyan",
    ))
    console.print(_matrix_table("Empirical transition matrix: P(next posture | posture)", model.transition_matrix, POSTURE_STATES))
    console.print(_matrix_table("Empirical emission matrix: P(action | posture)", model.emission_matrix, ACTIONS))

    comparison = Table(title="Old flat chaining vs. state-dependent HMM", box=box.ROUNDED)
    comparison.add_column("Method")
    comparison.add_column("P(at least one hike)", justify="right")
    comparison.add_row("Flat independent chaining (live per-meeting market prices)", f"{flat_probability * 100:.1f}%")
    comparison.add_row("HMM + Monte Carlo", f"{result.probability_at_least_one_hike * 100:.1f}%")
    comparison.add_row(
        "Direct market on the same joint event",
        f"{MARKET_CUMULATIVE_HIKE_PROBABILITY * 100:.1f}%",
    )
    console.print(comparison)
    console.print(
        "[dim]Chaining the live per-meeting prices as if independent overstates the "
        f"direct market on the identical event by "
        f"{(flat_probability - MARKET_CUMULATIVE_HIKE_PROBABILITY) * 100:+.1f}pp -- a "
        "measurement of the independence error p_at_least_one_hike documents, positive "
        "because policy decisions are regime-correlated.[/dim]"
    )
    console.print(
        "Hawkish-state cross-check: "
        f"HMM P(hike | hawkish) = {model.emission_matrix['hawkish_bias']['hike'] * 100:.1f}% | "
        "live per-meeting market P(hike) = "
        + ", ".join(
            f"{meeting_date[5:]} {probability * 100:.1f}%"
            for meeting_date, probability in MARKET_PER_MEETING_HIKE_PROBABILITY.items()
        )
        + f" (as of {MARKET_PER_MEETING_AS_OF})"
    )
    console.print(
        "[dim]The HMM emission is an unconditional historical base rate, while the "
        "market figures are meeting-specific live pricing; divergence is expected, "
        "not an error. No meeting is pinned any more -- the July 29 pin is archived "
        "(ARCHIVED_JULY_29_*) now that the meeting has resolved as a hold, and no "
        "market price enters the model at any point: every market figure printed here "
        "is a cross-check on an independently computed number.[/dim]"
    )

    histogram = Table(title=f"Monte Carlo hike-count distribution ({result.paths:,} paths)", box=box.SIMPLE)
    histogram.add_column("Outcome")
    histogram.add_column("Probability", justify="right")
    histogram.add_column("Histogram")
    for label, probability in result.hike_count_distribution.items():
        histogram.add_row(label, f"{probability * 100:5.1f}%", "█" * round(probability * 40))
    console.print(histogram)

    delta_points = (result.probability_at_least_one_hike - flat_probability) * 100
    console.print(
        "State dependence changes the estimate by "
        f"[bold]{delta_points:+.1f} percentage points[/bold] versus flat independent chaining."
    )
    if DATA_GAPS:
        console.print(f"[yellow]Historical data gaps: {list(DATA_GAPS)}[/yellow]")
    else:
        console.print(
            "[green]Historical data gaps: none across the "
            f"{model.training_meetings} regular training meetings.[/green]"
        )


def pce_threshold_probability(current_pce: float, target: float,
                               trailing_6mo_trend_bps_per_month: float,
                               months_remaining: int) -> dict:
    """
    Simple linear projection of PCE from current level to resolution date
    using the trailing trend, then express distance-to-threshold.
    Returns the projected value and a qualitative read, NOT a manufactured
    precise probability -- this tier should feed your judgment, not replace it.
    """
    projected = current_pce + (trailing_6mo_trend_bps_per_month / 100) * months_remaining
    gap = target - projected
    return {
        "current_pce": current_pce,
        "projected_pce_at_resolution": round(projected, 2),
        "target": target,
        "gap_to_target": round(gap, 2),
        "read": "on track for YES" if gap >= 0 else "trending toward NO",
    }


def electricity_price_check(baseline: float, current: float, threshold_pct: float = 15.0) -> dict:
    """Straight percentage-change check against the EIA baseline for forecast #9."""
    pct_change = ((current - baseline) / baseline) * 100
    return {
        "baseline": baseline,
        "current": current,
        "pct_change": round(pct_change, 2),
        "threshold_pct": threshold_pct,
        "resolves_yes_if_trend_holds": pct_change >= threshold_pct,
    }


# ===========================================================================
# ARCHIVED 2026-07-29 -- the forecast #5 TIER-3 MARKET-BLEND LAYER, retired.
# Retained here for provenance (same archival pattern as ARCHIVED_JULY_29_*
# above and the superseded estimates in methodology_notes.md). Forecast #5 is
# now a PURE HMM: the Monte Carlo output IS the authoritative probability, and
# the market reads are displayed cross-checks only.
#
# WHY IT WAS RETIRED, in full, because the reasoning is the point:
#
# The blend existed to correct the HMM toward a market anchor of 87.1% that
# could not be verified -- it appeared only in search-engine synthesis, never in
# any article body that was actually read. The correction was toward a number
# that may never have existed. What replaced it is stronger than a blend: a
# liquid direct market on the identical resolution question prices 62.5% and the
# HMM computes 62.6% -- two methods sharing no inputs, converging to within a
# rounding error. A blend between two such numbers is a no-op dressed up as a
# method (it computed a -0.1pp "correction"), and keeping it would imply the
# agreement was manufactured rather than found.
#
# The mechanical reason they converge is the finding worth recording. Chaining
# the live per-meeting market prices under an independence assumption gives
# 76.1%, against 62.5% from the direct market on the joint event. That 13.6pp
# gap IS the market pricing correlation between meetings. The HMM lands where it
# does because its sticky posture states (hawkish self-persistence 0.818)
# generate exactly that correlation instead of treating meetings as independent
# draws. So the direct market is not merely agreeing with the HMM's answer -- it
# is validating the HMM's structural choice. See methodology_notes.md #5,
# "Named finding: the independence error is the correlation price".
#
# ARCHIVED VALUES:
#   forecast5_blended_probability_pct()  -- summed _model_state.tier3["5"]
#     adjustments onto the HMM base; returned None when the config was absent.
#   _persist_forecast5_blend()           -- wrote the blended value to #5 and
#     refreshed tier3["5"].base_rate_pct to the HMM output.
#   market anchor                        87.1% (CME FedWatch cumulative, as of
#                                        2026-07-21, never verifiable)
#   tier-3 adjustment                    +15.0pp ("~60% weight to the market",
#                                        i.e. +15pp of a claimed 24.6pp gap)
#   HMM base rate at the time            62.5% (5,000 paths, seed 20260716)
#   persisted authoritative probability  77.5%
#   blend rule                           adjustment = 0.60 x (anchor - base)
# The full tier-3 config dict is archived under the top-level
# "_archived_model_state" key in forecast_state.json and quoted verbatim in
# methodology_notes.md #5.
# ===========================================================================


def _persist_forecast5_hmm(hmm_probability_pct: float) -> None:
    """Persist the pure HMM probability as forecast #5's authoritative value and
    refresh the stored path count, so the standalone script and
    tui.Tier1ModelScreen.rerun_simulation write the same two things.

    There is no longer a tier-3 layer to reconcile with: what the HMM computes is
    what #5 is. The silent-overwrite bug this replaced was not "the raw HMM value
    got written" -- it was "a value got written by a plain run at all". That is
    what the __main__ guard below still prevents.
    """
    set_forecast_probability(5, round(hmm_probability_pct, 1))
    state = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8"))
    state.setdefault("_model_state", {}).setdefault("tier1", {}).setdefault("5", {})[
        "simulations"
    ] = DEFAULT_MONTE_CARLO_PATHS
    FORECAST_STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    # The legacy comparison retains placeholder per-meeting market inputs. It is
    # printed for methodological contrast, but it is not persisted.
    # No longer placeholders: these are the live 2026-07-29 post-decision reads in
    # MARKET_PER_MEETING_HIKE_PROBABILITY. The contrast this block draws is now the
    # honest one -- independent chaining of real per-meeting prices versus the
    # direct market on the same joint event (MARKET_CUMULATIVE_HIKE_PROBABILITY),
    # which is the cleanest available measurement of the independence error that
    # p_at_least_one_hike's docstring flags.
    meetings_2026 = [
        FedMeeting("2026-09-16", p_hike=0.525, p_hold=0.455, p_cut=0.020),
        FedMeeting("2026-10-28", p_hike=0.263, p_hold=0.640, p_cut=0.097),
        FedMeeting("2026-12-09", p_hike=0.317, p_hold=0.624, p_cut=0.059),
    ]
    flat_probability = p_at_least_one_hike(meetings_2026)
    hmm = estimate_fed_posture_hmm()
    simulation = p_at_least_one_hike_hmm(hmm)
    hmm_probability_pct = round(simulation.probability_at_least_one_hike * 100, 1)
    print_hmm_report(hmm, simulation, flat_probability)

    console = Console()
    console.print(
        f"Forecast #5 authoritative probability: [bold]{hmm_probability_pct:.1f}%[/bold] "
        f"(pure HMM, {simulation.paths:,} paths, seed {DEFAULT_RANDOM_SEED})\n"
        f"[dim]Cross-checks (not inputs): direct market on the identical question "
        f"{MARKET_CUMULATIVE_HIKE_PROBABILITY * 100:.1f}% "
        f"(as of {MARKET_CUMULATIVE_AS_OF}) · CME FedWatch September "
        f"{MARKET_CME_FEDWATCH_SEPTEMBER_HIKE_PROBABILITY * 100:.0f}% as reported "
        f"({MARKET_CME_FEDWATCH_AS_OF}, tool not reachable first-party). The tier-3 "
        "market-blend layer is retired; see the ARCHIVED block above.[/dim]"
    )

    # PERSISTENCE GUARD. The original silent-overwrite bug was that a plain run
    # of this module wrote to forecast_state.json at all. That is still the thing
    # being prevented: nothing below the `--persist` check executes without the
    # explicit flag, matching the repo convention that plain runs only print.
    #
    # The guard's second job changed when the blend was retired. It used to refuse
    # when _model_state.tier3["5"] was MISSING (because the raw HMM value was not
    # then the authoritative quantity). That test is now inverted: the HMM value
    # IS authoritative, so the dangerous state is a blend config having REAPPEARED
    # -- which would mean two layers each claiming to define #5 and no way to tell
    # from here which one a writer intended. It refuses in that case rather than
    # guessing.
    if "--persist" in sys.argv[1:]:
        if not FORECAST_STATE_PATH.exists():
            console.print(
                "[red]Refusing to persist: forecast_state.json does not exist, so "
                "there is no authoritative file to update.[/red]"
            )
        else:
            _state = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8"))
            _revived_blend = _state.get("_model_state", {}).get("tier3", {}).get("5")
            if isinstance(_revived_blend, dict) and _revived_blend.get("adjustments"):
                console.print(
                    "[red]Refusing to persist: a tier-3 blend config for forecast #5 "
                    "(_model_state.tier3['5']) is present again with adjustments, but "
                    "the blend layer was retired on 2026-07-29 and #5 is a pure HMM. "
                    "Two layers now claim to define #5 and this script cannot tell "
                    "which was intended. Remove the revived config (it is archived "
                    "under _archived_model_state) or restore the blend deliberately "
                    "in code before persisting.[/red]"
                )
            else:
                _old = _state.get("5")
                _persist_forecast5_hmm(hmm_probability_pct)
                console.print(
                    f"[bold]Persisted forecast #5: {_old} -> "
                    f"{hmm_probability_pct:.1f}%[/bold] (pure HMM)"
                )
    else:
        console.print(
            "[dim]Nothing written. Pass --persist to write this probability to "
            "forecast_state.json.[/dim]"
        )
