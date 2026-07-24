"""
Forecast registry for the Bridgewater Forecasting the Future submission.
Each forecast carries one or more tier tags -- a list of ints drawn from {1, 2, 3}
-- that determine which calculation module(s) handle it. A forecast may span more
than one tier: e.g. #5 = [1, 3], an HMM base rate (tier 1) with a tier 3 judgment
blend layered on top. Tiers are referred to by number only.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Forecast:
    id: int
    title: str
    question: str
    resolution_date: str
    resolution_criteria: str
    tiers: list[int]   # one or more of {1, 2, 3}; multi-tier forecasts carry several
    probability: Optional[float] = None  # filled in once calculated
    notes: str = ""


FORECASTS = [
    Forecast(
        id=1,
        title="Chip export controls to China",
        question="Does the US tighten export controls on next-gen AI chips to China (vs. relax/unchanged)?",
        resolution_date="2026-12-31",
        resolution_criteria="YES if BIS tightens restrictions (new licensing, lowered thresholds, entity list additions) in window; NO if relaxed/unchanged.",
        # Tier 1 = Poisson point process over the audited China-chip tightening
        # episodes (export_controls_poisson.py, the primary quantitative method);
        # tier 3 = the reference-class estimate, kept as a documented cross-check.
        tiers=[1, 3],
    ),
    Forecast(
        id=2,
        title="Project Vault capacity expansion",
        question=(
            "Will Project Vault's committed capacity (currently $12B: $10B EXIM loan + $2B private "
            "capital, announced Feb 2, 2026) be formally expanded beyond that initial commitment by "
            "December 31, 2026?"
        ),
        resolution_date="2026-12-31",
        resolution_criteria=(
            "YES if, specifically for Project Vault (not the broader critical-minerals ecosystem -- "
            "separate EXIM LOIs, FORGE, or bilateral frameworks do NOT count unless explicitly folded "
            "into Vault's committed capacity): EXIM's Board approves additional loan authorization "
            "beyond the initial $10B; new private-capital commitments are formally announced that "
            "increase the $2B baseline; or Congress appropriates additional dedicated funding for the "
            "reserve. NO if capacity remains at the initial $12B through year-end."
        ),
        tiers=[3],
    ),
    Forecast(
        id=3,
        title="Data center capacity gap",
        question="Does the US 2027 data center capacity shortfall close to <30% not-yet-under-construction?",
        resolution_date="2027-12-31",
        resolution_criteria="YES if independent tracking (DC Byte/CBRE/JLL) shows gap <30%; NO if Bridgewater's flagged 60%+ persists/widens.",
        # Reframed from tier 2 (trend extrapolation) to tier 3 (reference-class
        # judgment): the real Sightline/Jefferies gap data is too small (n=2 for the
        # resolution metric) and methodologically mixed to support a trustworthy
        # trend fit -- the fit perversely returned 9-13% for a gap racing away from
        # the target. The authoritative number is now a qualitative call. See
        # methodology_notes.md #3. Tier 1 = backlog/throughput model plus
        # explicit modeled tail-risk channels (datacenter_backlog.py) --
        # ADOPTED as authoritative 2026-07-23, replacing the 4% judgment floor
        # with a fully modeled 5.5%.
        tiers=[1, 3],
    ),
    Forecast(
        id=4,
        title="AI capex GDP contribution vs. Bridgewater estimate",
        question="Does AI capex's contribution to 2027 real GDP growth exceed Bridgewater's ~150bp estimate?",
        resolution_date="2028-03-31",
        resolution_criteria="YES if BEA nonresidential IP equipment/software investment contribution exceeds 150bp; NO if at/below.",
        # Reframed from tier 2 (trend extrapolation) to tier 3 (reference-class
        # judgment): the target is Bridgewater's own forward-looking 150bp
        # estimate, not a historical baseline, so a base-rate-plus-adjustments
        # approach is the right tool. See methodology_notes.md #4.
        tiers=[3],
    ),
    Forecast(
        id=5,
        title="Fed rate path (hike risk)",
        question="Does the Fed raise rates at least once by year-end 2026?",
        resolution_date="2026-12-31",
        resolution_criteria="YES if fed funds target range is raised at any 2026 meeting; NO if held/cut all year.",
        tiers=[1, 3],
    ),
    Forecast(
        id=6,
        title="Inflation containment",
        question="Does headline PCE fall back to 3.5% or below by year-end 2026 (from 4.1% today)?",
        resolution_date="2026-12-31",
        resolution_criteria="YES if headline PCE YoY <= 3.5% at Dec 2026 print; NO if above.",
        # Reframed to tier 3 (reference-class judgment). Previously computed by a
        # tier-2 Student-t trend fit (the tier field read 1, but the machinery was
        # tier-2 trend extrapolation); a 12-point fit's narrow band cannot capture
        # real macro-surprise risk over a 7-month horizon. The base rate is now
        # anchored to the Fed's own SEP projection distribution. See
        # methodology_notes.md #6.
        tiers=[3],
    ),
    Forecast(
        id=7,
        title="Non-US/China sovereign AI compute funding crosses $250B",
        question=(
            "Does the combined public-sector funding committed to non-US, non-China sovereign AI "
            "compute/chip infrastructure cross $250 billion cumulative by December 31, 2026?"
        ),
        resolution_date="2026-12-31",
        resolution_criteria=(
            "STRICT scope. Count only PUBLIC-SECTOR commitments -- government loans, subsidies, grants, "
            "direct equity, or sovereign-wealth-fund commitments explicitly tied to state AI "
            "infrastructure strategy -- NOT privately mobilized capital, corporate capex, or private "
            "investment pledges. Two scope rules fixed at framing: (1) government-linked SWF vehicles "
            "(MGX, HUMAIN, etc.) count ONLY their non-US-domestic-infrastructure portion, not full "
            "announced fund capacity, and not deployments into US/global labs; (2) count only the "
            "public-seed figures, excluding mobilized totals (e.g. EU InvestAI's EUR 20B counts, the "
            "EUR 200B mobilized figure does not; France's EUR 109B private pledge does not; Korea's "
            "KRW 150T fund does not). YES if the strict-scope cumulative total reaches $250B by "
            "year-end 2026; NO otherwise. Current strict base ~ $85-90B as of Jul 2026."
        ),
        # Tier 1 = regime-switching compound Poisson over the dated commitment
        # history (sovereign_ai_jumps.py, variant d) -- ADOPTED as authoritative
        # 2026-07-23; the tier-3 pace estimate (14%) is archived in
        # methodology_notes.md #7.
        tiers=[1, 3],
    ),
    Forecast(
        id=8,
        title="Sovereign stake or champion status in a frontier AI lab",
        question=(
            "Does any government take a formal equity stake in, or grant explicit 'national champion' "
            "protected status to, a frontier AI model/lab company (not chip/hardware manufacturers) by "
            "December 31, 2026?"
        ),
        resolution_date="2026-12-31",
        resolution_criteria=(
            "NARROW scope. YES only if, by 2026-12-31, a government either (a) takes a "
            "strategic/control-oriented sovereign equity stake (in the mold of the May 2026 US-Intel "
            "intervention) in, or (b) grants a formal 'national champion' legal designation carrying "
            "attached protections to, one of the 10 listed frontier AI model/lab companies (OpenAI, "
            "Anthropic, xAI, Google DeepMind, Meta AI, Microsoft AI, Amazon AGI, Mistral AI, Cohere, "
            "Safe Superintelligence). The action must be finalized/executed, not merely proposed or "
            "under discussion. EXCLUDED -- and why: portfolio-style equity investments by "
            "government-linked sovereign-wealth funds or state-owned banks -- e.g. MGX/Mubadala in "
            "OpenAI and Anthropic, HUMAIN/PIF in xAI, Bpifrance's minority stake in Mistral. These are "
            "financial portfolio investments (passive, minority, return-seeking), NOT deliberate "
            "industrial-policy interventions, so they do not trigger YES even though they are formally "
            "'government-linked equity stakes.' Chip/hardware/foundry and quantum firms remain out of "
            "scope (separate category; the May 2026 Intel stake and the $2B quantum deployment are "
            "excluded). NO if all qualifying arrangements remain proposals/discussions without "
            "execution by year-end."
        ),
        tiers=[3],
    ),
    Forecast(
        id=9,
        title="Virginia commercial electricity rate reversal",
        question="Does Virginia's commercial electricity rate decrease from its current level (10.33 cents/kWh) within the next 6 months (by 2027-01-21)?",
        resolution_date="2027-01-21",
        # Reframed from a >15% rise threshold (tier 1) to a directional 6-month reversal
        # question (tier 3): whether the EIA commercial-sector VA rate falls below the
        # current 10.33 cents/kWh baseline. Still tracks COMMERCIAL sector (data centers
        # are commercial/industrial customers). See methodology_notes.md #9.
        resolution_criteria=(
            "YES if the EIA commercial-sector retail electricity rate for Virginia at the resolution "
            "date is BELOW the current 10.33 cents/kWh baseline (Jul 2026, the most recent actual "
            "observation). NO if flat or higher. Commercial sector specifically because data centers "
            "are commercial/industrial customers, so the commercial rate is the honest signal for "
            "data-center-driven cost pass-through (residential is up ~14.5% YoY over the same window, "
            "moving for different reasons; commercial is ~flat). A YES requires the documented "
            "fuel-cost easing (EIA STEO gas downgrade) to outweigh Dominion's SCC-approved base-rate "
            "increases, which are regulatory-locked through 2027."
        ),
        # Tier 1 = deterministic Dominion schedule + OU Henry Hub simulation
        # (electricity_simulation.py) -- ADOPTED as authoritative 2026-07-23
        # after the annual fuel-year lock was independently verified; the
        # tier-3 30% judgment estimate is archived in methodology_notes.md #9.
        tiers=[1, 3],
    ),
    Forecast(
        id=10,
        title="Nuclear/SMR permitting fast-track",
        question="Does NRC/DOE establish an expedited licensing pathway for data-center-serving nuclear/SMR?",
        resolution_date="2027-12-31",
        resolution_criteria=(
            "YES if any of the following is formally finalized (not merely proposed or in public "
            "comment) by the resolution date: (a) NRC's proposed Part 57 rule (expedited "
            "microreactor/SMR licensing, review times under 1 year, fleet-based approval); (b) DOE's "
            "fast-tracked permitting for its four solicited AI-data-center-plus-nuclear sites (Idaho "
            "National Laboratory, Oak Ridge, Paducah, Savannah River); or (c) the proposed rule "
            "allowing DOE/DOW military reactor testing data to fast-track commercial NRC licensing. "
            "Any one of these being finalized satisfies YES. NO if all three remain "
            "proposals/in-progress without finalization by the resolution date."
        ),
        # Tier 1 = competing-risks reliability model over the three pathways
        # (nuclear_competing_risks.py) -- ADOPTED as authoritative 2026-07-23
        # after the EO 14300 execution record was itemized (see
        # methodology_notes.md #10); the tier-3 79% estimate is archived.
        tiers=[1, 3],
    ),
]

FORECAST_STATE_PATH = Path(__file__).with_name("forecast_state.json")


def get(forecast_id: int) -> Forecast:
    for f in FORECASTS:
        if f.id == forecast_id:
            return f
    raise ValueError(f"No forecast with id {forecast_id}")


def set_forecast_probability(forecast_id: int, value: float) -> None:
    get(forecast_id).probability = value
    metadata = {}
    if FORECAST_STATE_PATH.exists():
        existing_state = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8"))
        metadata = {key: item for key, item in existing_state.items() if not key.isdigit()}
    state = metadata | {
        str(forecast.id): forecast.probability
        for forecast in FORECASTS
        if forecast.probability is not None
    }
    FORECAST_STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_forecast_state() -> None:
    if not FORECAST_STATE_PATH.exists():
        return
    state = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8"))
    for forecast in FORECASTS:
        if str(forecast.id) in state:
            forecast.probability = state[str(forecast.id)]


_load_forecast_state()
