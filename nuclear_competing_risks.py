"""
Forecast #10: competing-risks / parallel-systems reliability model for the
nuclear/SMR permitting fast-track question (resolution 2027-12-31).

The resolution is a textbook parallel (redundant) system: YES if ANY of three
federal actions is formally finalized by 2027-12-31 -- (a) the NRC's Part 57
microreactor licensing rule, (b) DOE fast-track site permitting at its four
AI-data-center sites, or (c) the DOE/DOW reactor-design data-bridge rule. A
parallel system fails only if EVERY component fails, so naive independence
multiplies three modest failure probabilities into an absurdly tiny joint one
(P(NO) ~ 0.2%). But these components share common drivers -- one White House
push, one strained NRC staff pool, one appropriations process, one litigation
environment -- so their failures are positively correlated and independence
overstates P(YES). The standard reliability fix is a series-parallel
decomposition: a common-mode gate in series with the parallel block,

    P(YES) = (1 - p_systemic) * (1 - PROD_i (1 - p_i))

where p_i = P(pathway i finalizes by resolution | no systemic derailment) and
p_systemic = P(a single common-mode event -- program-wide injunction, agenda-
freezing accident, fiscal/leadership crisis -- stalls all three). This keeps
the redundancy benefit honest: the all-idiosyncratic-failure product stays
tiny, and nearly all NO-probability is forced through an explicitly priced
common-mode term instead of hiding inside a hand-waved "slippage" deduction.
Monthly completion curves per pathway (deadline-anchored mixtures for the two
rulemakings, a diffuse ramp for the DOE sites) let the TUI draw the combined
completion/survival curve, and a Monte Carlo run cross-checks the algebra and
adds timing diagnostics.
"""

import json
import random
import sys
from dataclasses import dataclass
from datetime import date

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forecasts import FORECAST_STATE_PATH, set_forecast_probability


FORECAST_ID = 10
# Repo convention (mirrors fomc_history.CURRENT_AS_OF_DATE): a fixed as-of
# date so runs are reproducible. Never datetime.now() in model math.
AS_OF_DATE = date(2026, 7, 22)
RESOLUTION_DATE = date(2027, 12, 31)
DEFAULT_MONTE_CARLO_PATHS = 10_000
DEFAULT_RANDOM_SEED = 20260722  # deterministic runs; same convention as tier1_market.DEFAULT_RANDOM_SEED

# EO 14300 (2025-05-23) directs the NRC to publish final rules within 18
# months -> 2026-11-23. NRC staff said in March 2026 they are "on target".
# https://www.ans.org/news/2026-03-13/article-7842/nrc-provides-timeline-update-on-rules-meeting-eo-deadline/ (accessed 2026-07-22)
EO_14300_FINAL_RULE_DEADLINE = date(2026, 11, 23)
# NRC's own published Part 57 final-rule target per the NIA EO 14300 tracker
# (updated 2026-07-06 from NRC's Planned Rulemaking Activities site) -- 8 days
# PAST the EO deadline, 13 months before the resolution date.
# https://nuclearinnovationalliance.org/sites/default/files/2026-07/Public%20Rule%20timeline%207-6.pdf (accessed 2026-07-22)
PART57_NRC_TARGET_DATE = date(2026, 12, 1)
# Same tracker: DOE/DOW data-bridge rule final target sits exactly on the EO deadline.
DOW_RULE_NRC_TARGET_DATE = date(2026, 11, 23)

# ---------------------------------------------------------------------------
# Research-calibrated MARGINAL probabilities (2026-07-22 research pass).
# Each marginal already includes its share of common-mode risk; the model
# factors the common mode out (p_i | no systemic = p_i / (1 - p_systemic))
# before recombining, so the systemic term is not double-counted.
# ---------------------------------------------------------------------------
# P(Part 57 final by the 2026-11-23 EO deadline): NRC's published target
# (2026-12-01) is 8 days past the deadline; hitting the EO date requires
# pulling the schedule in, which NRC has not signaled.
# https://nuclearinnovationalliance.org/sites/default/files/2026-07/Public%20Rule%20timeline%207-6.pdf (accessed 2026-07-22)
# https://www.federalregister.gov/documents/2026/05/01/2026-08550/licensing-requirements-for-microreactors-and-other-reactors-with-comparable-risk-profiles (accessed 2026-07-22)
P_PART57_BY_EO_DEADLINE = 0.20
# P(Part 57 final by end-2027) -- recalibrated 2026-07-23 after itemizing the
# actual EO 14300 record (see EO14300_FINALIZED_RECORD below):
#   (a) The "7-for-7 on schedule" claim VERIFIES as a count of genuinely
#       finalized rules, but its composition is procedural/administrative/
#       deregulatory (practice & procedure, FOIA, fees, hearings, two narrow
#       deregulatory items) -- weak direct evidence that a NOVEL licensing
#       framework can be finalized on a 7-month proposed-to-final schedule.
#       Its evidential weight is downgraded accordingly.
#   (b) The right substantive calibration is Part 53 (outside the tracker's
#       scope): proposed 2024-11-22, final 2026-03-30 = 16.3 months
#       proposed-to-final for a much larger novel framework, WITH a 60-day
#       comment extension and 158 comments, still beating its NEIMA statutory
#       deadline by >1 year. Part 57 proposed 2026-05-01 + the full Part 53
#       pace lands ~Sep 2027 -- inside the window with ~3.5 months margin even
#       in that slow scenario; missing end-2027 requires running >25% slower
#       than Part 53 on a much narrower rule, or a rework/litigation event.
#   Net: end-2027 probability nudged 0.90 -> 0.91 (the Part 53 calibration
#   slightly outweighs the 7-for-7 downgrade at this horizon); the near-term
#   TIMING mass is reduced instead (see PART57_CUM_BY_JITTER_END).
# https://nuclearinnovationalliance.org/sites/default/files/2026-07/Public%20Rule%20timeline%207-6.pdf (accessed 2026-07-23)
# https://www.federalregister.gov/documents/2024/11/22/2024-26937/risk-informed-technology-inclusive-regulatory-framework-for-advanced-reactors (accessed 2026-07-23)
# https://www.ans.org/news/article-7881/nrc-unveils-part-53-final-rule/ (accessed 2026-07-22)
P_PART57_BY_END_2027 = 0.91
# P(any DOE fast-track site permitting finalized by end-2027): DOE proved
# sub-year formal authorization (4 pilot reactors critical by 2026-07-04) and
# holds a NEPA categorical exclusion; Amentum/SRS lease negotiation underway
# since 2026-07-20 with 17 months to go across 4 parallel sites. Discounted
# because no lease is final yet and "finalized" needs a signed formal action.
# https://www.energy.gov/nnsa/articles/nnsa-selects-amentum-ai-data-center-and-energy-project-savannah-river-site (accessed 2026-07-22)
# https://www.federalregister.gov/documents/2026/02/02/2026-02071/categorical-exclusion-for-advanced-nuclear-reactors (accessed 2026-07-22)
P_DOE_SITES_BY_END_2027 = 0.75
# P(DOE/DOW data-bridge rule final by end-2027): shortest, narrowest rule;
# comments closed 2026-05-04; target 2026-11-23 leaves >13 months slack; only
# political-friction and common-mode risks discount it.
# https://www.federalregister.gov/documents/2026/04/02/2026-06414/nrc-reviews-of-reactor-designs-previously-authorized-by-us-department-of-energy-or-department-of-war (accessed 2026-07-22)
# https://fedscoop.com/nrc-fiscal-2027-budget-data-doe-dod/ (accessed 2026-07-22)
P_DOW_RULE_BY_END_2027 = 0.92
# P(common-mode derailment stalling all three before any finalizes).
#
# PROVENANCE (audited 2026-07-23): this parameter is a REASONED JUDGMENT
# CALIBRATION from the 2026-07-22 research pass, NOT a counted base rate --
# no historical frequency of "EO-priority multi-pathway regulatory programs
# derailed program-wide within 18 months" exists to count. It is the single
# most consequential soft parameter in the model: with three semi-independent
# pathways, P(YES) ~ (1 - S) x 0.9999, so the gate IS essentially the answer.
# The model therefore reports a BAND over S (below), not just the central
# point. Component anchors, each tied to what real data exists:
#   - Shutdown stall: 21 appropriations funding gaps since 1977 but only
#     three shutdowns of >= 3 weeks in ~50 years; the NRC is ~90% fee-funded
#     and demonstrably kept EO 14300 work going through the Oct-Nov 2025
#     shutdown on carryover funds. Stalling ALL pathways past end-2027 needs
#     an unprecedented multi-month, carryover-exhausting lapse: <= ~1%.
#     https://www.morganlewis.com/blogs/upandatom/2025/10/what-the-government-shutdown-means-for-the-nrc-and-its-licensees (accessed 2026-07-22)
#   - Program-wide pre-finalization injunction: no suit pending against EO
#     14300, Part 53, Part 57, or the pilot program (searched 2026-07-22 and
#     re-verified 2026-07-23); post-finalization APA challenges do not undo
#     "formally finalized"; three separate finalization vehicles would all
#     need to be frozen: ~1-3%.
#     https://thebreakthrough.org/issues/nuclear-energy-innovation/understanding-the-nrc-independence-debate (accessed 2026-07-22)
#   - Priority reversal / commission incapacity: no presidential transition
#     inside the window (Jan 2029); the Jun 2025 Hanson firing was absorbed
#     with a full commission reconstituted by Jan 2026; residual quorum-loss
#     or fiscal-crisis scenario compounding the documented 14-15% attrition
#     and 8.1% budget-cut request: ~1-2%.
#     https://www.eenews.net/articles/white-house-fires-nrc-commissioner/ (accessed 2026-07-22)
#     https://www.ans.org/news/2026-05-14/article-8030/nrc-commissioners-talk-attrition-recruitment-retention-at-senate-hearing/ (accessed 2026-07-22)
#   - Agenda-freezing test-reactor accident: worldwide core-damage frequency
#     scaled to a handful of micro test reactors over 17 months: < 0.5%.
# Component sum ~3-6.5%: the 0.06 central sits at the TOP of that sum
# (conservative), but the components are order-of-magnitude anchors, not
# counted frequencies -- hence the band.
P_SYSTEMIC_DERAILMENT = 0.06
# Sensitivity band endpoints for the gate. LOW = the optimistic end of the
# component sum above. HIGH = double the central gate, covering common-mode
# correlation beyond a single program-wide event (e.g. the two NRC rules
# sharing staffing/OIRA/rework risk that the one-gate structure understates)
# -- the same doubling the 2026-07-22 adversarial review used as its
# robustness check. ASSUMED endpoints, reasoned as above.
P_SYSTEMIC_LOW = 0.03
P_SYSTEMIC_HIGH = 0.12
# Research status check as of 2026-07-22: NONE of the three pathways is
# already finalized (the adjacent Part 53 framework was finalized 2026-03-30
# but is NOT one of the three resolution pathways). If a Pathway below ever
# carries finalized_on, the report short-circuits to SHORT_CIRCUIT_PCT.
ALREADY_FINALIZED = "none"

# ---------------------------------------------------------------------------
# The itemized EO 14300 record (NIA tracker, last updated 2026-07-06, populated
# from NRC's own Planned Rulemaking Activities site; verified 2026-07-23).
# (name, final publication date, substantive_licensing_framework?)
# All seven finalized rules met their published schedules -- "7-for-7" is an
# accurate COUNT -- but none is an affirmative novel licensing framework, so
# the record's evidential weight for Part 57's pace is limited (see the
# P_PART57_BY_END_2027 comment). The same tracker also shows NRC itself
# scheduling roughly half of the ~27 EO rulemakings PAST the 2026-11-23 EO
# deadline (five at 3/31/2027, one at 10/1/2027, several in Dec 2026-Jan
# 2027), confirming the deadline is directive, not binding.
# https://nuclearinnovationalliance.org/sites/default/files/2026-07/Public%20Rule%20timeline%207-6.pdf (accessed 2026-07-23)
# ---------------------------------------------------------------------------
EO14300_FINALIZED_RECORD = (
    ("Streamlining Select Rules of Practice and Procedure", "2025-11-26", False),
    ("The Sunset Rule (direct final, partial withdrawal)", "2026-01-08", False),
    ("Sunset Rule: Aircraft Impact Assessment (deregulatory)", "2026-04-01", False),
    ("FOIA Implementing Regulations", "2026-03-06", False),
    ("Increased Flexibility in the Mandatory Hearing Process", "2026-04-15", False),
    ("Exceptions from Foreign Ownership, Control, or Domination (direct final)", "2026-04-23", False),
    ("Revision of Fee Schedules: FY 2026", "2026-06-22", False),
)
# The substantive calibration point (outside the tracker's scope): Part 53,
# proposed 2024-11-22, final 2026-03-30 = 16.3 months proposed-to-final for a
# major novel framework, with a 60-day comment extension and 158 comments,
# beating its NEIMA statutory deadline by more than a year.
# https://www.federalregister.gov/documents/2024/11/22/2024-26937/risk-informed-technology-inclusive-regulatory-framework-for-advanced-reactors (accessed 2026-07-23)
PART53_PROPOSED = date(2024, 11, 22)
PART53_FINAL = date(2026, 3, 30)
PART53_MONTHS_PROPOSED_TO_FINAL = 16.3
# ASSUMED: probability to report once a pathway is verified finalized; the
# residual 1% covers only resolution-criteria ambiguity / reporting error,
# since post-finalization APA challenges do not undo "formally finalized".
SHORT_CIRCUIT_PCT = 99.0

# ---------------------------------------------------------------------------
# Curve-shape parameters. Waypoints marked "research hint" come from the
# 2026-07-22 research pass (monthly_curve_hints); everything else is ASSUMED
# with reasoning.
# ---------------------------------------------------------------------------
# Part 57 cumulative by end-Jan 2027 (the NRC 2026-12-01 target plus ~70-day
# OIRA review jitter; NIA OIRA tracker: ~70-day average). Recalibrated
# 2026-07-23 from 0.55 to 0.45: the verified finalized set is administrative/
# deregulatory, so it says little about a novel framework hitting a 7-month
# proposed-to-final target, and the substantive comparable (Part 53) ran 16.3
# months -- partially offset by Part 57 being far narrower and its 45-day
# comment period having closed on schedule with no extension. More mass moves
# into the Feb-Dec 2027 slip tail; the end-2027 marginal barely moves.
# https://nuclearinnovationalliance.org/sites/default/files/2026-06/OIRA%20Tracker%20Fact%20Sheet%206-22.pdf (accessed 2026-07-22)
PART57_CUM_BY_JITTER_END = 0.45
# Research hint waypoint used to FIT the slip-tail hazard: cum ~0.75 by Jun 2027.
PART57_TAIL_WAYPOINT = ("2027-06", 0.75)
# ASSUMED: midpoint of the research's 0.45-0.55 band for the DOW rule hitting
# its 2026-11-23 target month (target sits exactly on the EO deadline).
DOW_CUM_BY_EO_DEADLINE = 0.50
# ASSUMED: DOW cum by end-Jan 2027. Mirrors the Part 57 target+OIRA-jitter
# window but tighter (research: "same shape shifted ~1 week earlier and
# tighter" for a narrower amendment rule): +0.25 across Dec-Jan.
DOW_CUM_BY_JITTER_END = 0.75
# Research hint waypoint used to FIT the DOW slip-tail hazard: cum ~0.80 by Mar 2027.
DOW_TAIL_WAYPOINT = ("2027-03", 0.80)
# ASSUMED: share of the target+OIRA-jitter window mass landing in the target
# month itself (Dec 2026) vs spilling into Jan 2027; 60/40 reflects a
# 2026-12-01 publication target with ~70-day OIRA review jitter around it.
JITTER_FIRST_MONTH_SHARE = 0.60
# Research hint: DOE sites are a diffuse, roughly linear ramp, not a spike --
# gated on sequential formal actions (lease finalization, CX-based NEPA
# determination, DOE authorization, each demonstrated at <6-12 months in the
# pilot program). Ramp starts ~Oct 2026, ~0.35 by mid-2027, 0.75 by Dec 2027.
DOE_RAMP_START_MONTH = "2026-10"
DOE_MID_WAYPOINT = ("2027-06", 0.35)
# NOTE on systemic timing: the common-mode event is modeled as a single
# Bernoulli gate with NO time profile -- by (research) definition it stalls
# all three pathways for the whole window, so only whether it fires matters
# for the resolution question, not when. A time-profiled systemic hazard was
# considered and removed: composing it with pathway curves conditioned on
# "no systemic ever" produced a mathematically inconsistent (non-monotone)
# combined curve. The research hint that common-mode risk is weighted toward
# H2-2027 survives only as color in SYSTEMIC_RATIONALE.

# Current persisted tier-3 estimate this model is benchmarked against:
# 80% timeline-based base rate +6 momentum -7 slippage (forecast_state.json).
TIER3_REFERENCE_PCT = 79.0

PART57_SOURCES = (
    "https://www.federalregister.gov/documents/2026/05/01/2026-08550/licensing-requirements-for-microreactors-and-other-reactors-with-comparable-risk-profiles",
    "https://nuclearinnovationalliance.org/sites/default/files/2026-07/Public%20Rule%20timeline%207-6.pdf",
    "https://nuclearinnovationalliance.org/index.php/expected-nrc-executive-order-14300-rulemaking-timeline",
    "https://www.ans.org/news/2026-03-13/article-7842/nrc-provides-timeline-update-on-rules-meeting-eo-deadline/",
    "https://nuclearinnovationalliance.org/sites/default/files/2026-06/OIRA%20Tracker%20Fact%20Sheet%206-22.pdf",
    "https://www.ans.org/news/article-7881/nrc-unveils-part-53-final-rule/",
)
DOE_SITES_SOURCES = (
    "https://www.energy.gov/nnsa/articles/nnsa-selects-amentum-ai-data-center-and-energy-project-savannah-river-site",
    "https://www.energy.gov/articles/doe-announces-site-selection-ai-data-center-and-energy-infrastructure-development-federal",
    "https://www.federalregister.gov/documents/2026/02/02/2026-02071/categorical-exclusion-for-advanced-nuclear-reactors",
    "https://www.powermag.com/aalo-atomics-test-reactor-reaches-criticality-at-inl-fourth-doe-authorized-advanced-reactor-by-july-4/",
    "https://www.world-nuclear-news.org/articles/criticality-for-fourth-us-microreactor-meets-deadline",
    "https://www.ans.org/news/article-7525/doe-seeks-proposals-for-ai-data-centers-at-paducah/",
)
DOW_RULE_SOURCES = (
    "https://www.federalregister.gov/documents/2026/04/02/2026-06414/nrc-reviews-of-reactor-designs-previously-authorized-by-us-department-of-energy-or-department-of-war",
    "https://nuclearinnovationalliance.org/sites/default/files/2026-07/Public%20Rule%20timeline%207-6.pdf",
    "https://fedscoop.com/nrc-fiscal-2027-budget-data-doe-dod/",
    "https://perkinscoie.com/insights/blog/nrc-proposes-accelerated-licensing-pathway-doe-and-dow-authorized-reactor-designs",
)
SYSTEMIC_SOURCES = (
    "https://www.ans.org/news/2026-05-14/article-8030/nrc-commissioners-talk-attrition-recruitment-retention-at-senate-hearing/",
    "https://fedscoop.com/nrc-fiscal-2027-budget-data-doe-dod/",
    "https://www.eenews.net/articles/white-house-fires-nrc-commissioner/",
    "https://www.morganlewis.com/blogs/upandatom/2026/01/with-a-new-chair-and-full-commission-nrc-enters-2026-poised-for-action",
    "https://www.morganlewis.com/blogs/upandatom/2025/10/what-the-government-shutdown-means-for-the-nrc-and-its-licensees",
    "https://www.counterpunch.org/2026/07/09/environmental-protections-under-attack-the-nrcs-new-nepa-rule/",
    "https://thebreakthrough.org/issues/nuclear-energy-innovation/understanding-the-nrc-independence-debate",
)

SYSTEMIC_RATIONALE = (
    "Single Bernoulli common-mode gate at 6%: a pre-finalization program-wide "
    "injunction (NRC-independence ruling), a catastrophic test-reactor accident "
    "freezing the agenda, or a 2027 fiscal/leadership crisis compounding 14-15% "
    "attrition and an 8.1% budget cut. Evidence caps it low: no pending "
    "litigation, fee-funded shutdown resilience (EO work continued through the "
    "Oct-Nov 2025 shutdown), a full commission, and a White-House-signature "
    "program with a 7-for-7 on-schedule EO-era rulemaking record."
)


def _month_range(start_year: int, start_month: int, end_year: int, end_month: int) -> tuple[str, ...]:
    months = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return tuple(months)


# The TUI's x-axis: every month from next month after as-of through resolution.
CURVE_MONTHS = _month_range(2026, 8, 2027, 12)


@dataclass(frozen=True)
class Pathway:
    key: str
    name: str
    description: str
    # Research marginal P(finalized by 2027-12-31), common-mode risk included.
    p_marginal_research: float
    # p_i in the headline formula: P(finalized by resolution | no systemic
    # derailment) = p_marginal_research / (1 - P_SYSTEMIC_DERAILMENT).
    p_by_resolution: float
    # Monthly cumulative completion curve in the SAME conditional space as
    # p_by_resolution: ((YYYY-MM, cumulative p), ...) over CURVE_MONTHS.
    curve: tuple[tuple[str, float], ...]
    sources: tuple[str, ...]
    # Set to a YYYY-MM-DD string once a pathway is verifiably finalized; the
    # report then short-circuits to SHORT_CIRCUIT_PCT and says so loudly.
    finalized_on: str | None = None


@dataclass(frozen=True)
class SimulationResult:
    paths: int
    p_yes: float
    p_no_systemic: float          # share of paths killed by the common-mode gate
    p_no_idiosyncratic: float     # share where all three pathways individually failed
    p_yes_by_2026_12: float
    p_yes_by_2027_06: float
    median_first_finalization: str | None
    first_finalizer_shares: dict[str, float]
    random_seed: int | None


def fit_truncated_geometric_hazard(waypoint_share: float, waypoint_month: int, total_months: int) -> float:
    """Solve for the monthly hazard h of a geometric slip tail truncated to
    ``total_months``, such that the first ``waypoint_month`` months hold
    ``waypoint_share`` of the tail's mass:

        (1 - (1-h)^k) / (1 - (1-h)^n) = waypoint_share.

    Functional choice: a slipped rulemaking has a roughly constant per-month
    chance of finally clearing (memoryless staff-throughput view), i.e. a
    geometric hazard; truncation pins the cumulative exactly to the researched
    end-2027 marginal instead of leaving untracked post-2027 mass. The ratio
    is monotone increasing in h (h->0 gives k/n, h->1 gives 1), so bisection
    converges; the waypoint share must exceed the uniform-limit k/n.
    """
    uniform_limit = waypoint_month / total_months
    if not uniform_limit < waypoint_share < 1.0:
        raise ValueError(
            f"waypoint share {waypoint_share} must lie in ({uniform_limit:.3f}, 1) "
            f"for k={waypoint_month}, n={total_months}"
        )
    lo, hi = 1e-9, 1.0 - 1e-9
    for _ in range(100):
        mid = (lo + hi) / 2.0
        share = (1.0 - (1.0 - mid) ** waypoint_month) / (1.0 - (1.0 - mid) ** total_months)
        if share < waypoint_share:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _validate_curve(key: str, curve: tuple[tuple[str, float], ...], expected_end: float) -> None:
    previous = 0.0
    for month, cumulative in curve:
        if not 0.0 <= cumulative <= 1.0:
            raise ValueError(f"{key} curve leaves [0, 1] at {month}: {cumulative}")
        if cumulative < previous - 1e-12:
            raise ValueError(f"{key} curve is not monotone at {month}")
        previous = cumulative
    if abs(curve[-1][1] - expected_end) > 1e-9:
        raise ValueError(f"{key} curve ends at {curve[-1][1]}, expected {expected_end}")


def _rule_mixture_curve(
    eo_window_cum: float,
    jitter_end_cum: float,
    end_cum: float,
    tail_waypoint: tuple[str, float],
) -> tuple[tuple[tuple[str, float], ...], float]:
    """Deadline-anchored mixture curve (marginal space) for a rulemaking.

    Three named components, per the spec that this be a mixture and not a
    hand-drawn list:
      1. EO-deadline window: all of ``eo_window_cum`` lands in 2026-11 (the
         month of the 2026-11-23 EO 14300 deadline). Hazard before then is
         zero -- a final rule cannot plausibly publish while comments are
         still being resolved (research: "near-zero hazard until Nov 2026").
      2. NRC-target + OIRA-jitter window: mass ``jitter_end_cum -
         eo_window_cum`` split across Dec 2026 / Jan 2027 by
         JITTER_FIRST_MONTH_SHARE (published target ~2026-12-01, ~70-day OIRA
         review jitter).
      3. Slip tail: the remainder ``end_cum - jitter_end_cum`` over Feb-Dec
         2027 as a truncated geometric with hazard FIT (bisection) to the
         research's mid-2027 cumulative waypoint.

    Returns (curve, fitted_monthly_hazard).
    """
    eo_index = CURVE_MONTHS.index("2026-11")
    december_index = CURVE_MONTHS.index("2026-12")
    january_index = CURVE_MONTHS.index("2027-01")
    tail_months = CURVE_MONTHS[january_index + 1:]  # Feb 2027 .. Dec 2027
    total_tail_months = len(tail_months)
    waypoint_k = tail_months.index(tail_waypoint[0]) + 1
    tail_mass = end_cum - jitter_end_cum
    waypoint_share = (tail_waypoint[1] - jitter_end_cum) / tail_mass
    hazard = fit_truncated_geometric_hazard(waypoint_share, waypoint_k, total_tail_months)

    increments = [0.0] * len(CURVE_MONTHS)
    increments[eo_index] = eo_window_cum
    jitter_mass = jitter_end_cum - eo_window_cum
    increments[december_index] = jitter_mass * JITTER_FIRST_MONTH_SHARE
    increments[january_index] = jitter_mass * (1.0 - JITTER_FIRST_MONTH_SHARE)
    normalizer = 1.0 - (1.0 - hazard) ** total_tail_months
    for j in range(total_tail_months):
        increments[january_index + 1 + j] = (
            tail_mass * ((1.0 - hazard) ** j) * hazard / normalizer
        )

    curve, cumulative = [], 0.0
    for month, increment in zip(CURVE_MONTHS, increments):
        cumulative += increment
        curve.append((month, cumulative))
    return tuple(curve), hazard


def _doe_ramp_curve() -> tuple[tuple[str, float], ...]:
    """Diffuse piecewise-linear ramp for the DOE sites pathway (marginal
    space): zero until the ramp start, linear to the mid-2027 waypoint, then a
    steeper linear leg to the end-2027 marginal (leases and CX-based NEPA
    determinations maturing across four parallel sites flatten single-site
    idiosyncratic risk -- research hint: "roughly linear ramp rather than a
    spike").
    """
    start_index = CURVE_MONTHS.index(DOE_RAMP_START_MONTH)
    mid_index = CURVE_MONTHS.index(DOE_MID_WAYPOINT[0])
    mid_cum = DOE_MID_WAYPOINT[1]
    end_index = len(CURVE_MONTHS) - 1
    curve = []
    for index, month in enumerate(CURVE_MONTHS):
        if index < start_index:
            cumulative = 0.0
        elif index <= mid_index:
            cumulative = mid_cum * (index - start_index + 1) / (mid_index - start_index + 1)
        else:
            cumulative = mid_cum + (P_DOE_SITES_BY_END_2027 - mid_cum) * (
                (index - mid_index) / (end_index - mid_index)
            )
        curve.append((month, cumulative))
    return tuple(curve)


def _to_conditional(curve: tuple[tuple[str, float], ...]) -> tuple[tuple[str, float], ...]:
    """Convert a marginal curve to the conditional (no-systemic-ever) space by
    uniform scaling with 1/(1 - p_systemic).

    Under the model's generative structure -- a single un-timed Bernoulli
    common-mode gate that is independent of pathway timing (exactly what the
    Monte Carlo draws) -- this scaling is EXACT, not an approximation:
    P(finalized by t | gate does not fire) = P(finalized by t) / (1 - p_systemic)
    for every month t. The curve endpoint equals p_by_resolution by
    construction.
    """
    scale = 1.0 / (1.0 - P_SYSTEMIC_DERAILMENT)
    return tuple((month, min(1.0, cumulative * scale)) for month, cumulative in curve)


def build_pathways() -> tuple[tuple[Pathway, ...], dict[str, float]]:
    part57_marginal, part57_hazard = _rule_mixture_curve(
        P_PART57_BY_EO_DEADLINE,
        PART57_CUM_BY_JITTER_END,
        P_PART57_BY_END_2027,
        PART57_TAIL_WAYPOINT,
    )
    dow_marginal, dow_hazard = _rule_mixture_curve(
        DOW_CUM_BY_EO_DEADLINE,
        DOW_CUM_BY_JITTER_END,
        P_DOW_RULE_BY_END_2027,
        DOW_TAIL_WAYPOINT,
    )
    doe_marginal = _doe_ramp_curve()
    _validate_curve("part57", part57_marginal, P_PART57_BY_END_2027)
    _validate_curve("dow_rule", dow_marginal, P_DOW_RULE_BY_END_2027)
    _validate_curve("doe_sites", doe_marginal, P_DOE_SITES_BY_END_2027)

    conditional_scale = 1.0 / (1.0 - P_SYSTEMIC_DERAILMENT)
    pathways = (
        Pathway(
            key="part57",
            name="NRC Part 57 microreactor rule",
            description=(
                "10 CFR Part 57 expedited microreactor/SMR licensing. Proposed "
                "2026-05-01 (FR 2026-08550), comments closed 2026-06-15, NRC "
                "published final-rule target 2026-12-01 -- 8 days past the EO "
                "14300 deadline, 13 months before resolution."
            ),
            p_marginal_research=P_PART57_BY_END_2027,
            p_by_resolution=P_PART57_BY_END_2027 * conditional_scale,
            curve=_to_conditional(part57_marginal),
            sources=PART57_SOURCES,
        ),
        Pathway(
            key="doe_sites",
            name="DOE fast-track site permitting",
            description=(
                "Fast-tracked permitting for AI-data-center-plus-energy projects "
                "at INL, Oak Ridge, Paducah, Savannah River. First selection "
                "2026-07-20 (Amentum, SRS phased-lease negotiation); NEPA "
                "categorical exclusion for advanced reactors effective "
                "2026-02-02; no formal finalized permitting action yet."
            ),
            p_marginal_research=P_DOE_SITES_BY_END_2027,
            p_by_resolution=P_DOE_SITES_BY_END_2027 * conditional_scale,
            curve=_to_conditional(doe_marginal),
            sources=DOE_SITES_SOURCES,
        ),
        Pathway(
            key="dow_rule",
            name="DOE/DOW data-bridge rule",
            description=(
                "Amendment to 10 CFR Parts 50/53 crediting DOE/DOW reactor test "
                "data toward commercial NRC licensing. Proposed 2026-04-02, "
                "comments closed 2026-05-04, NRC final-rule target 2026-11-23 -- "
                "exactly on the EO deadline; shortest-fuse rule of the three."
            ),
            p_marginal_research=P_DOW_RULE_BY_END_2027,
            p_by_resolution=P_DOW_RULE_BY_END_2027 * conditional_scale,
            curve=_to_conditional(dow_marginal),
            sources=DOW_RULE_SOURCES,
        ),
    )
    fitted_hazards = {"part57": part57_hazard, "dow_rule": dow_hazard}
    return pathways, fitted_hazards


PATHWAYS, FITTED_SLIP_HAZARDS = build_pathways()


def combined_curve(pathways: tuple[Pathway, ...] = PATHWAYS) -> tuple[tuple[str, float], ...]:
    """Month-by-month combined P(at least one pathway finalized by t):

        c(t) = (1 - p_systemic) * (1 - PROD_i (1 - p_i(t)))

    with the CONSTANT common-mode gate and p_i(t) the conditional (no-
    systemic-ever) pathway curves -- the same generative model the Monte
    Carlo draws, so the analytic milestones and the simulation agree by
    construction, and at the resolution date this is exactly the headline
    formula. (An earlier revision composed a time-profiled systemic hazard
    s(t) with these same conditional curves; that mixed two conditioning
    spaces and produced a non-monotone cumulative curve -- caught in review
    and removed. The monotonicity assertion below guards the invariant.)
    """
    curve = []
    previous = 0.0
    for index, month in enumerate(CURVE_MONTHS):
        product_none = 1.0
        for pathway in pathways:
            product_none *= 1.0 - pathway.curve[index][1]
        value = (1.0 - P_SYSTEMIC_DERAILMENT) * (1.0 - product_none)
        if value < previous - 1e-12:
            raise ValueError(f"combined curve is not monotone at {month}")
        previous = value
        curve.append((month, value))
    return tuple(curve)


def survival_curve(pathways: tuple[Pathway, ...] = PATHWAYS) -> tuple[tuple[str, float], ...]:
    """Survival view: P(NO pathway finalized by t) = 1 - combined_curve(t)."""
    return tuple((month, 1.0 - p) for month, p in combined_curve(pathways))


def simulate_competing_risks(
    pathways: tuple[Pathway, ...] = PATHWAYS,
    paths: int = DEFAULT_MONTE_CARLO_PATHS,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> SimulationResult:
    """Monte Carlo cross-check of the analytic series-parallel formula, plus
    timing diagnostics the algebra alone does not give (first-finalization
    month distribution, which pathway resolves the question).

    The common-mode gate is a single Bernoulli(p_systemic) draw per path --
    by definition (research calibration) the common-mode event stalls all
    three pathways, so a gated path is NO regardless of timing. Conditional
    on the gate not firing, each pathway's finalization month is drawn
    independently from its conditional monthly curve (or never). Ties for
    "first finalizer" go to the earlier-listed pathway (display diagnostic
    only; the YES/NO outcome is unaffected).
    """
    if paths <= 0:
        raise ValueError("paths must be a positive integer")
    rng = random.Random(random_seed)
    pmfs = []
    for pathway in pathways:
        increments, previous = [], 0.0
        for month, cumulative in pathway.curve:
            increments.append((month, cumulative - previous))
            previous = cumulative
        pmfs.append(increments)

    yes = no_systemic = no_idiosyncratic = 0
    yes_by_2026_12 = yes_by_2027_06 = 0
    first_counts = {pathway.key: 0 for pathway in pathways}
    first_months = []
    for _ in range(paths):
        if rng.random() < P_SYSTEMIC_DERAILMENT:
            no_systemic += 1
            continue
        first_month, first_key = None, None
        for increments, pathway in zip(pmfs, pathways):
            draw, cumulative, month_hit = rng.random(), 0.0, None
            for month, increment in increments:
                cumulative += increment
                if draw <= cumulative:
                    month_hit = month
                    break
            if month_hit is not None and (first_month is None or month_hit < first_month):
                first_month, first_key = month_hit, pathway.key
        if first_month is None:
            no_idiosyncratic += 1
            continue
        yes += 1
        first_counts[first_key] += 1
        first_months.append(first_month)
        if first_month <= "2026-12":
            yes_by_2026_12 += 1
        if first_month <= "2027-06":
            yes_by_2027_06 += 1

    first_months.sort()
    return SimulationResult(
        paths=paths,
        p_yes=yes / paths,
        p_no_systemic=no_systemic / paths,
        p_no_idiosyncratic=no_idiosyncratic / paths,
        p_yes_by_2026_12=yes_by_2026_12 / paths,
        p_yes_by_2027_06=yes_by_2027_06 / paths,
        median_first_finalization=first_months[len(first_months) // 2] if first_months else None,
        first_finalizer_shares={
            key: (count / yes if yes else 0.0) for key, count in first_counts.items()
        },
        random_seed=random_seed,
    )


def _persisted_probability() -> float | None:
    if not FORECAST_STATE_PATH.exists():
        return None
    state = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8"))
    return state.get(str(FORECAST_ID))


def nuclear_pathways_report(
    paths: int = DEFAULT_MONTE_CARLO_PATHS,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> dict:
    """Pure report function: computes everything, prints nothing, persists
    nothing. The TUI imports this and renders its contents.
    """
    pathways = PATHWAYS

    product_none_independent = 1.0
    for pathway in pathways:
        product_none_independent *= 1.0 - pathway.p_marginal_research
    independence_pct = (1.0 - product_none_independent) * 100.0

    product_none_conditional = 1.0
    for pathway in pathways:
        product_none_conditional *= 1.0 - pathway.p_by_resolution
    p_yes_given_no_gate = 1.0 - product_none_conditional
    combined = (1.0 - P_SYSTEMIC_DERAILMENT) * p_yes_given_no_gate
    combined_pct = combined * 100.0

    # The common-mode gate is a reasoned calibration, not a counted base rate
    # (see the P_SYSTEMIC_DERAILMENT provenance block), and with three
    # semi-independent pathways P(YES) ~ (1 - S): the gate is essentially the
    # entire answer. So the model's primary output is a BAND over the gate's
    # defensible range, with the persisted single value being its central
    # point.
    combined_band = {
        "low_pct": round((1.0 - P_SYSTEMIC_HIGH) * p_yes_given_no_gate * 100.0, 1),
        "central_pct": round(combined_pct, 1),
        "high_pct": round((1.0 - P_SYSTEMIC_LOW) * p_yes_given_no_gate * 100.0, 1),
        "gate_low": P_SYSTEMIC_LOW,
        "gate_central": P_SYSTEMIC_DERAILMENT,
        "gate_high": P_SYSTEMIC_HIGH,
        "note": (
            "P(YES) is essentially 1 - S because the all-idiosyncratic-failure "
            "product is ~0.01%; S is a reasoned calibration (component anchors in "
            "the module source), not a counted frequency, so the band -- not the "
            "central point alone -- is the honest statement of the result."
        ),
    }

    short_circuit = None
    finalized = [pathway for pathway in pathways if pathway.finalized_on is not None]
    if finalized:
        names = ", ".join(f"{p.name} (finalized {p.finalized_on})" for p in finalized)
        combined_pct = SHORT_CIRCUIT_PCT
        short_circuit = (
            f"PATHWAY ALREADY FINALIZED: {names}. The resolution criterion is "
            f"met -- the model short-circuits to {SHORT_CIRCUIT_PCT}% (residual "
            "covers only resolution-criteria ambiguity; post-finalization APA "
            "challenges do not undo 'formally finalized')."
        )

    simulation = simulate_competing_risks(pathways, paths, random_seed)
    persisted_pct = _persisted_probability()
    divergence_pts = combined_pct - persisted_pct if persisted_pct is not None else None
    if short_circuit is not None:
        divergence_note = short_circuit
    elif persisted_pct is None:
        divergence_note = (
            f"No persisted probability found for forecast #{FORECAST_ID} in "
            f"forecast_state.json; the model stands alone at {combined_pct:.1f}%."
        )
    else:
        divergence_note = (
            f"Model {combined_pct:.1f}% vs persisted {persisted_pct}% "
            f"({divergence_pts:+.1f}pp). The tier-3 additive estimate (80% "
            "timeline base rate +6 momentum -7 slippage) prices slippage and "
            "litigation as one large subtraction from a single blended "
            "timeline. The reliability decomposition shows why that "
            "under-credits redundancy: with three semi-independent shots at "
            f"{P_PART57_BY_END_2027:.2f}/{P_DOE_SITES_BY_END_2027:.2f}/"
            f"{P_DOW_RULE_BY_END_2027:.2f}, the all-idiosyncratic-failure "
            f"product is ~{product_none_conditional * 100:.2f}%, so nearly all "
            "NO-probability must flow through a common-mode event -- calibrated "
            "at 6% (no pending litigation, fee-funded shutdown resilience, full "
            "commission). Pathway probabilities were re-derived 2026-07-23 "
            "against the ITEMIZED EO 14300 record: the '7-for-7 on schedule' "
            "claim verifies as a count of finalized rules but all seven are "
            "administrative/procedural/deregulatory (see EO14300_FINALIZED_RECORD), "
            "so the substantive calibration is Part 53 -- 16.3 months "
            "proposed-to-final for a larger novel framework, beating its "
            "statutory deadline by >1 year; even at that full pace Part 57 "
            "lands ~Sep 2027, inside the window. Holding 79% requires believing "
            "common-mode risk is ~3-4x the evidence-backed level."
        )

    return {
        "forecast_id": FORECAST_ID,
        "as_of": AS_OF_DATE.isoformat(),
        "resolution_date": RESOLUTION_DATE.isoformat(),
        "already_finalized": ALREADY_FINALIZED,
        "short_circuit": short_circuit,
        "formula": "P(YES) = (1 - p_systemic) * (1 - PROD_i (1 - p_i)), p_i conditional on no systemic derailment",
        "pathways": [
            {
                "key": pathway.key,
                "name": pathway.name,
                "description": pathway.description,
                "p_marginal_research": pathway.p_marginal_research,
                "p_by_resolution": round(pathway.p_by_resolution, 4),
                "finalized_on": pathway.finalized_on,
                "curve": [(month, round(p, 4)) for month, p in pathway.curve],
                "sources": list(pathway.sources),
            }
            for pathway in pathways
        ],
        "fitted_slip_hazards": {
            key: round(value, 4) for key, value in FITTED_SLIP_HAZARDS.items()
        },
        "p_systemic": P_SYSTEMIC_DERAILMENT,
        "p_systemic_rationale": SYSTEMIC_RATIONALE,
        "p_systemic_sources": list(SYSTEMIC_SOURCES),
        "eo14300_finalized_record": [
            {"name": name, "final_date": final_date, "substantive_framework": substantive}
            for name, final_date, substantive in EO14300_FINALIZED_RECORD
        ],
        "part53_calibration": {
            "proposed": PART53_PROPOSED.isoformat(),
            "final": PART53_FINAL.isoformat(),
            "months_proposed_to_final": PART53_MONTHS_PROPOSED_TO_FINAL,
        },
        "combined_curve": [(month, round(p, 4)) for month, p in combined_curve(pathways)],
        "survival_curve": [(month, round(p, 4)) for month, p in survival_curve(pathways)],
        "combined_pct": round(combined_pct, 2),
        "combined_band": combined_band,
        "independence_pct": round(independence_pct, 2),
        "correlation_adjustment_pts": round(combined_pct - independence_pct, 2),
        "independence_note": (
            f"Pure independence on the research marginals would give "
            f"{independence_pct:.1f}% -- the common-mode gate pulls it to "
            f"{combined_pct:.1f}% ({combined_pct - independence_pct:+.1f}pp). "
            "The correlation adjustment IS essentially the entire NO side."
        ),
        "monte_carlo": {
            "paths": simulation.paths,
            "random_seed": simulation.random_seed,
            "p_yes_pct": round(simulation.p_yes * 100.0, 2),
            "p_no_systemic_pct": round(simulation.p_no_systemic * 100.0, 2),
            "p_no_idiosyncratic_pct": round(simulation.p_no_idiosyncratic * 100.0, 2),
            "p_yes_by_2026_12_pct": round(simulation.p_yes_by_2026_12 * 100.0, 2),
            "p_yes_by_2027_06_pct": round(simulation.p_yes_by_2027_06 * 100.0, 2),
            "median_first_finalization": simulation.median_first_finalization,
            "first_finalizer_shares": {
                key: round(share, 3)
                for key, share in simulation.first_finalizer_shares.items()
            },
        },
        "persisted_pct": persisted_pct,
        "tier3_reference_pct": TIER3_REFERENCE_PCT,
        "divergence_pts": round(divergence_pts, 1) if divergence_pts is not None else None,
        "divergence_note": divergence_note,
    }


def print_report(report: dict, console: Console | None = None) -> None:
    console = console or Console()
    console.print(Panel.fit(
        f"[bold]Forecast #{report['forecast_id']}: Nuclear/SMR fast-track -- "
        "competing-risks reliability model[/bold]\n"
        f"As of {report['as_of']} | resolution {report['resolution_date']} | "
        f"{report['formula']}\n"
        f"p_systemic = {report['p_systemic']:.2f} | Monte Carlo "
        f"{report['monte_carlo']['paths']:,} paths, seed "
        f"{report['monte_carlo']['random_seed']}",
        border_style="cyan",
    ))

    if report["short_circuit"]:
        console.print(Panel.fit(
            f"[bold red]{report['short_circuit']}[/bold red]",
            border_style="red",
        ))
    else:
        console.print(
            f"[dim]Status check (research, {report['as_of']}): already finalized = "
            f"{report['already_finalized']} -- all three pathways still live.[/dim]"
        )

    milestones = ("2026-11", "2027-01", "2027-06", "2027-12")
    table = Table(title="Pathways (cumulative P(finalized by month), conditional on no common-mode event)", box=box.SIMPLE_HEAVY)
    table.add_column("Pathway")
    table.add_column("p marginal", justify="right")
    table.add_column("p_i | no sys", justify="right")
    for month in milestones:
        table.add_column(month, justify="right")
    for pathway in report["pathways"]:
        cumulative = dict(pathway["curve"])
        table.add_row(
            pathway["name"],
            f"{pathway['p_marginal_research']:.2f}",
            f"{pathway['p_by_resolution']:.3f}",
            *(f"{cumulative[month]:.3f}" for month in milestones),
        )
    console.print(table)
    for pathway in report["pathways"]:
        console.print(f"[bold]{pathway['key']}[/bold]: {pathway['description']}")
        console.print(f"[dim]  primary source: {pathway['sources'][0]}[/dim]")
    console.print(
        "Fitted slip-tail hazards (truncated geometric, bisection on research "
        f"waypoints): {report['fitted_slip_hazards']}"
    )
    console.print(f"[bold]Common-mode gate[/bold] ({report['p_systemic']:.0%}): {report['p_systemic_rationale']}")

    comparison = Table(title="Independence vs correlation-adjusted", box=box.ROUNDED)
    comparison.add_column("Method")
    comparison.add_column("P(YES)", justify="right")
    comparison.add_row("Pure independence on research marginals (overstates)", f"{report['independence_pct']:.1f}%")
    comparison.add_row("Series-parallel with common-mode gate (headline)", f"[bold]{report['combined_pct']:.1f}%[/bold]")
    comparison.add_row(
        f"Monte Carlo cross-check ({report['monte_carlo']['paths']:,} paths)",
        f"{report['monte_carlo']['p_yes_pct']:.1f}%",
    )
    console.print(comparison)
    band = report["combined_band"]
    console.print(
        f"[bold]Gate-sensitivity band (the honest result): "
        f"{band['low_pct']:.1f}% - {band['central_pct']:.1f}% - {band['high_pct']:.1f}%[/bold] "
        f"for S = {band['gate_high']:.2f} / {band['gate_central']:.2f} / {band['gate_low']:.2f}. "
        f"[dim]{band['note']}[/dim]"
    )
    console.print(report["independence_note"])
    mc_gap = report["monte_carlo"]["p_yes_pct"] - report["combined_pct"]
    console.print(
        f"[dim]Monte Carlo vs analytic gap: {mc_gap:+.2f}pp (sampling noise; "
        "the simulation draws the same model). NO decomposes as "
        f"~{report['monte_carlo']['p_no_systemic_pct']:.1f}pp common-mode + "
        f"~{report['monte_carlo']['p_no_idiosyncratic_pct']:.2f}pp all-three-"
        "idiosyncratic-failure.[/dim]"
    )
    console.print(
        "Timing: P(YES already by Dec 2026) = "
        f"{report['monte_carlo']['p_yes_by_2026_12_pct']:.1f}% | by Jun 2027 = "
        f"{report['monte_carlo']['p_yes_by_2027_06_pct']:.1f}% | median first "
        f"finalization {report['monte_carlo']['median_first_finalization']} | "
        f"first finalizer shares {report['monte_carlo']['first_finalizer_shares']}"
    )

    curve_table = Table(title="Combined completion curve c(t) = (1 - s(t)) * (1 - PROD(1 - p_i(t)))", box=box.SIMPLE)
    curve_table.add_column("Month")
    curve_table.add_column("P(>=1 final)", justify="right")
    curve_table.add_column("Survival", justify="right")
    curve_table.add_column("")
    survival = dict(report["survival_curve"])
    for month, probability in report["combined_curve"]:
        curve_table.add_row(
            month,
            f"{probability * 100:5.1f}%",
            f"{survival[month] * 100:5.1f}%",
            "█" * round(probability * 40),
        )
    console.print(curve_table)

    if report["divergence_pts"] is not None:
        console.print(
            f"Headline [bold]{report['combined_pct']:.1f}%[/bold] vs currently persisted "
            f"[bold]{report['persisted_pct']}%[/bold] (tier-3 reference "
            f"{report['tier3_reference_pct']}%): divergence "
            f"[bold]{report['divergence_pts']:+.1f}pp[/bold]"
        )
    else:
        console.print(
            f"Headline [bold]{report['combined_pct']:.1f}%[/bold] (no persisted "
            "probability on file to compare against)"
        )
    console.print(report["divergence_note"])
    if report["divergence_pts"] is not None and abs(report["divergence_pts"]) > 3:
        console.print(
            "[yellow]Material divergence vs the persisted tier-3 estimate; the "
            "structural decomposition above is the argument. Persist only "
            "deliberately (--persist).[/yellow]"
        )


if __name__ == "__main__":
    console = Console()
    report = nuclear_pathways_report()
    print_report(report, console)
    if "--persist" in sys.argv:
        # Persistence is an explicit, deliberate act (repo convention):
        # a plain run must only print.
        value = round(report["combined_pct"], 1)
        set_forecast_probability(FORECAST_ID, value)
        console.print(f"[bold]Persisted {value}% to forecast #{FORECAST_ID}.[/bold]")
