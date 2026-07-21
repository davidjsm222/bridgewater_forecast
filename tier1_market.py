"""
Tier 1: Market-derived forecasts.
These have a real, live market pricing the underlying event (Fed funds futures,
EIA regional price data, PCE trend data). The job here isn't prediction from
scratch, it's correctly translating market-implied probabilities into the
specific yes/no threshold the forecast asks about.
"""

import random
from dataclasses import dataclass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forecasts import set_forecast_probability
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
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-09",
)
DEFAULT_MONTE_CARLO_PATHS = 10_000
DEFAULT_RANDOM_SEED = 20260716
# Single-meeting live-market P(hike) for the imminent July 29, 2026 meeting, as of
# 2026-07-21: Polymarket (a ~$78M market) 10.7%, rateprobability.com 9.6%. We adopt
# the deeper Polymarket read. This replaces the stale 0.251, which predated the
# July repricing driven by the May 2026 CPI print (4.2% YoY).
CME_FEDWATCH_JULY_29_HIKE_PROBABILITY = 0.107
CME_FEDWATCH_JULY_29_AS_OF = "2026-07-21"
CME_FEDWATCH_JULY_29_SOURCE = "Polymarket ($78M market) 10.7%; rateprobability.com 9.6%"

# Per-meeting emission overrides. For an imminent, precisely-priced meeting we pin
# P(hike) to the live market instead of drawing it from the HMM's unconditional
# posture emissions (which would put ~39% on a hawkish-state meeting -- far above
# what the market actually prices for July). Sept/Oct/Dec have no comparably clean
# single-meeting read this far out, so they remain fully HMM-driven.
MEETING_HIKE_PROBABILITY_OVERRIDES = {
    "2026-07-29": CME_FEDWATCH_JULY_29_HIKE_PROBABILITY,
}


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
    comparison.add_row("Flat independent chaining (placeholder meeting inputs)", f"{flat_probability * 100:.1f}%")
    comparison.add_row("HMM + Monte Carlo", f"{result.probability_at_least_one_hike * 100:.1f}%")
    console.print(comparison)
    console.print(
        "Hawkish-state cross-check: "
        f"HMM P(hike | hawkish) = {model.emission_matrix['hawkish_bias']['hike'] * 100:.1f}% | "
        "July 29 meeting-specific market P(hike) = "
        f"{CME_FEDWATCH_JULY_29_HIKE_PROBABILITY * 100:.1f}% "
        f"(as of {CME_FEDWATCH_JULY_29_AS_OF}; {CME_FEDWATCH_JULY_29_SOURCE})"
    )
    console.print(
        "[dim]The HMM emission is an unconditional historical base rate, while the "
        "market figure is meeting-specific live pricing; divergence is expected, not "
        "an error. July 29's simulated hike odds are pinned to this market read.[/dim]"
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
        console.print("[green]Historical data gaps: none across the 83 regular training meetings.[/green]")


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


if __name__ == "__main__":
    # The legacy comparison retains placeholder per-meeting market inputs. It is
    # printed for methodological contrast, but it is not persisted.
    meetings_2026 = [
        FedMeeting("2026-09-16", p_hike=0.35, p_hold=0.55, p_cut=0.10),   # placeholder, pull live
        FedMeeting("2026-10-28", p_hike=0.30, p_hold=0.60, p_cut=0.10),  # placeholder, pull live
        FedMeeting("2026-12-09", p_hike=0.25, p_hold=0.65, p_cut=0.10),  # placeholder, pull live
    ]
    flat_probability = p_at_least_one_hike(meetings_2026)
    hmm = estimate_fed_posture_hmm()
    simulation = p_at_least_one_hike_hmm(hmm)
    hmm_probability_pct = round(simulation.probability_at_least_one_hike * 100, 1)
    set_forecast_probability(5, hmm_probability_pct)
    print_hmm_report(hmm, simulation, flat_probability)
