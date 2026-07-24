"""Textual terminal application for the Bridgewater forecasting model."""

import copy
import json
import math
from statistics import mean

from rich.markup import escape
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static
from textual_plotext import PlotextPlot

from bayesian_update import BAYES_UPDATES, bayesian_report
from datacenter_backlog import datacenter_backlog_report
from electricity_simulation import electricity_report
from export_controls_poisson import export_controls_poisson_report
from forecasts import FORECASTS, FORECAST_STATE_PATH, get, set_forecast_probability
from nuclear_competing_risks import nuclear_pathways_report
from sovereign_ai_jumps import sovereign_ai_report
from tier1_market import (
    CME_FEDWATCH_JULY_29_AS_OF,
    CME_FEDWATCH_JULY_29_HIKE_PROBABILITY,
    CME_FEDWATCH_JULY_29_SOURCE,
    DEFAULT_MONTE_CARLO_PATHS,
    DEFAULT_RANDOM_SEED,
    estimate_fed_posture_hmm,
    p_at_least_one_hike_hmm,
)
from fomc_history import CURRENT_POSTURE, CURRENT_SEP_PCE_PROJECTION, POSTURE_STATES
from tier2_trend import (
    TrendPoint,
    distance_to_threshold_in_sigma,
    linear_trend_projection,
    threshold_probability,
    walk_forward_rmse,
)
from tier3_judgment import AdjustmentFactor, ReferenceClassEstimate


# Bridgewater "Forecasting the Future" challenge branding: black + red (the
# "blackred" logo variant), replacing Textual's default navy/orange dark theme.
BRIDGEWATER_THEME = Theme(
    name="bridgewater-blackred",
    # Blood-red maroon (low blue channel, so it reads as deep red -- NOT the
    # crimson/pink that Textual's default red + auto-lighten produced).
    primary="#a61c24",      # drives the selected-row / block-cursor fill
    secondary="#7a1620",    # deeper maroon, used sparingly
    accent="#a61c24",       # same maroon for borders / titles / highlights
    foreground="#f0f0f0",   # off-white primary text
    background="#0a0a0a",   # near-black base
    surface="#141414",      # slightly lifted panels / tables
    panel="#1c1c1c",        # dialogs / model panels, lifted above surface
    success="#3fb950",      # muted green (semantic: up / YES)
    warning="#d29922",      # amber
    error="#ff5c5c",        # error red, lighter than the chrome maroon
    dark=True,
    variables={
        # Explicit muted gray keeps secondary text well above the contrast floor.
        "text-muted": "#9ea0a3",
        # Pin selection/cursor + border tokens directly to the maroon so
        # Textual's auto-lighten never shifts them toward crimson/pink. Light
        # text on the maroon selected-row keeps it readable (~6.8:1).
        "block-cursor-background": "#a61c24",
        "block-cursor-foreground": "#f5f5f5",
        "block-cursor-text-style": "bold",
        "border": "#a61c24",
    },
)

# Small, restrained secondary palette used only where colour carries real
# information (the Tier 3 waterfall's up/down steps). Muted so they read as
# intentional next to the red/black chrome, distinct enough to tell apart.
ADJUSTMENT_UP_COLOR = "#3fb950"    # muted green — factor pushes probability up
ADJUSTMENT_DOWN_COLOR = "#e5484d"  # muted red — factor pushes probability down


# Per-forecast model-type labels for the list view. Forecasts with a tier-1
# quantitative process model show that model's name; #4/#6 are Bayesian
# likelihood-ratio updates; #2/#8 are deliberately judgment-anchored layered
# estimates (see JUDGMENT_ANCHORED_NOTES).
MODEL_TYPE_LABELS = {
    1: "Poisson",
    3: "Backlog",
    4: "Bayesian",
    5: "HMM",
    6: "Bayesian",
    7: "Jump MC",
    9: "OU sim",
    10: "Comp risks",
}


def format_model_type(forecast) -> str:
    """Render a forecast's model type from its id (see MODEL_TYPE_LABELS);
    anything without a dedicated quantitative model is 'Layered'."""
    return MODEL_TYPE_LABELS.get(forecast.id, "Layered")


MODEL_STATE_KEY = "_model_state"
DATA_CACHE_DIR = FORECAST_STATE_PATH.parent / "data_cache"


def _read_cache(filename: str) -> dict | None:
    """Read a data_cache JSON file directly, without triggering an API pull."""
    path = DATA_CACHE_DIR / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _seed_investment_points() -> list[dict]:
    """Real BEA information-processing points forecast #4's trend was fit on."""
    cache = _read_cache("fred_information_processing_investment.json")
    if not cache:
        return []
    observations = cache.get("gdp_contribution_observations", [])[-10:]
    return [
        {"period": observation["date"][:4], "value": observation["total_percentage_points_at_annual_rate"]}
        for observation in observations
        if observation.get("total_percentage_points_at_annual_rate") is not None
    ]


def _seed_pce_config() -> dict:
    """Last 12 PCE YoY observations and the horizon to the Dec 2026 print -- the
    same inputs pce_trend_forecast() in tier2_trend.py fits, so #6's model view
    and the batch script are a single Student-t trend calculation, not two."""
    config = {"points": [], "periods_ahead": 7, "threshold": 3.5, "yes_if_at_or_below": True}
    cache = _read_cache("fred_pcepi.json")
    if not cache:
        return config
    usable = [o for o in cache.get("observations", []) if o.get("year_over_year_pct") is not None]
    selected = usable[-12:]
    if len(selected) < 3:
        return config
    config["points"] = [{"period": o["date"][:7], "value": o["year_over_year_pct"]} for o in selected]
    latest = selected[-1]["date"]
    latest_year, latest_month = int(latest[:4]), int(latest[5:7])
    config["periods_ahead"] = (2026 - latest_year) * 12 + 12 - latest_month
    return config


def _blank_tier3() -> dict:
    """A tier-3 config with nothing researched yet -- every field is editable."""
    return {
        "reference_class": "",
        "base_rate_pct": 50.0,
        "base_rate_source": "",
        "adjustments": [],
    }


DEFAULT_MODEL_STATE = {
    "tier1": {
        "5": {"simulations": DEFAULT_MONTE_CARLO_PATHS},
        # ARCHIVED: #9 was reframed from this tier-1 threshold check (">15% rise above
        # a 10.33 cents/kWh commercial baseline") to a tier-3 directional 6-month
        # reversal question (does the commercial rate fall below 10.33 by 2027-01-21?).
        # See tier3["9"] below and methodology_notes.md #9. The commercial EIA cache
        # (eia_virginia_retail_electricity.json) still anchors the 10.33 baseline.
        # "9": {
        #     "kind": "threshold",
        #     "label": "Virginia commercial-sector retail electricity price",
        #     "current_value": 10.33,
        #     "threshold": 11.88,
        #     "unit": "cents/kWh",
        #     "yes_if_at_or_above": True,
        #     "note": "YES if the commercial rate rises >15% above the 10.33 baseline.",
        # },
    },
    "tier2": {
        # yes_if_at_or_below encodes the resolution direction so the view's
        # probability matches the authoritative batch calculation exactly.
        #
        # ARCHIVED: #3 was reframed from this tier-2 trend fit to a tier-3
        # reference-class estimate (see tier3["3"] below and methodology_notes.md #3).
        # The placeholder points (68/65/63/61 closing toward 30%) were replaced with
        # REAL sourced figures, retained here for reference:
        #   2026 pipeline gap (Sightline, consistent methodology):
        #     Feb 2026 = 68.75% (5GW under construction of 16GW planned)
        #     Apr 2026 = ~68%   (~one-third broken ground; reported 67-69%)
        #   2027-specific gap (the actual resolution metric):
        #     Apr 2026 = 70.7%  (6.3GW of 21.5GW; Sightline/Bloomberg)
        #     Jun 2026 = ~80%   (Jefferies -- DIFFERENT tracker)
        # The tier-2 fit was abandoned as untrustworthy: the resolution-metric
        # series is only n=2 (below the machinery's 3-point floor), the two 2027
        # points come from different trackers (Sightline 70.7% vs Jefferies 80%, so
        # the "widening" is confounded with a methodology switch), and the combined
        # 4-point fit produced a PERVERSE result -- a projected gap of 88-99% (racing
        # AWAY from the 30% target) yet a Student-t P(YES<30%) of 9-13% that RISES
        # with the horizon, a pure artifact of fat-tailed n=4 / 2-dof bands. The
        # authoritative number is now a qualitative tier-3 call (4%). Trend code
        # still lives in tier2_trend.py.
        # "3": {
        #     "points": [
        #         {"period": "2026-02 pipeline (Sightline)", "value": 68.75},
        #         {"period": "2026-04 pipeline (Sightline)", "value": 68.0},
        #         {"period": "2026-04 2027-spec (Sightline/Bloomberg)", "value": 70.7},
        #         {"period": "2026-06 2027-spec (Jefferies)", "value": 80.0},
        #     ],
        #     "periods_ahead": 6,
        #     "threshold": 30.0,
        #     "yes_if_at_or_below": True,   # YES if the capacity gap falls below 30%
        # },
        # ARCHIVED: #4 was reframed from a tier-2 trend fit to a tier-3
        # reference-class estimate (see tier3["4"] below and methodology_notes.md).
        # The old trend config is retained here, unused, for reference. Its fit
        # projected ~0.47pp vs the 1.5pp threshold and produced a 2.4% probability
        # -- a number now judged structurally wrong because it compared the
        # outcome to a flat historical proxy instead of to Bridgewater's forward
        # estimate. The trend code itself still lives in tier2_trend.py.
        # "4": {
        #     "points": _seed_investment_points(),
        #     "periods_ahead": 2,
        #     "threshold": 1.5,
        #     "yes_if_at_or_below": False,  # YES if the contribution exceeds 1.5pp
        #     "nowcast": {"period": "2026-Q1", "value": 1.15, "label": "..."},
        # },
        # ARCHIVED: #6 was reframed from this tier-2 Student-t trend fit to a
        # tier-3 reference-class estimate (see tier3["4"]-style config in tier3
        # below, and methodology_notes.md #6). The trend config is retained here,
        # unused, for reference. Its fit projected ~4.49% PCE for Dec 2026 and
        # produced a 3.8% probability -- a number now judged to understate real
        # uncertainty because a 12-point band cannot represent macro-surprise risk
        # over a 7-month horizon. The trend code itself still lives in
        # tier2_trend.py (pce_trend_forecast).
        # "6": _seed_pce_config(),
    },
    "tier3": {
        "9": {
            "reference_class": (
                "Frequency of a regulated state's commercial electricity rate posting a genuine "
                "6-month net decrease, given a documented fuel-cost easing trend against "
                "regulatory-locked base-rate increases"
            ),
            "base_rate_pct": 35.0,
            "base_rate_source": (
                "35% = the reference-class frequency of a regulated state's commercial electricity "
                "rate posting a genuine 6-month NET DECREASE. Retail prices drift upward over time "
                "(~2-3%/yr nominal), so a net decrease over a given 6-month window is a minority "
                "event -- but not rare, because natural-gas fuel pass-through and seasonality produce "
                "real declines a substantial minority of the time. Mean-reversion note: 10.33 "
                "cents/kWh (Jul 2026) is the TOP of the recent 8-month range (10.21-10.33) -- the "
                "rate was below 10.33 in 7 of the last 8 months -- so 'below 10.33 in January' sits "
                "squarely within the recent noise band, which keeps this from being a longshot. No "
                "'global energy conflict' wildcard is included: the research surfaced nothing "
                "specific (no current conflict-driven gas shock), so no speculative geopolitical "
                "factor is invented; the fuel-cost/base-rate mechanism is the whole grounded story."
            ),
            "adjustments": [
                {
                    "name": "Documented fuel-cost easing (STEO gas downgrade)",
                    "direction": "up",
                    "magnitude_pts": 8.0,
                    "rationale": (
                        "EIA's own STEO forecasts Henry Hub gas ~2% lower in 2026, and the May 2026 "
                        "STEO revised the 2026 forecast down a further 4.4% -- genuine downward pressure "
                        "on the fuel portion of the rate. Sized modestly: fuel is only ~a third of the "
                        "commercial rate (so a ~2-6% gas move is ~1-2% on the total), and it is a "
                        "forecast, not a locked certainty -- it must be large enough to overcome the "
                        "base-rate hikes, which is borderline."
                    ),
                },
                {
                    "name": "Regulatory-locked base-rate increases",
                    "direction": "down",
                    "magnitude_pts": 13.0,
                    "rationale": (
                        "Dominion's SCC-approved base-rate increases are regulatory-locked through "
                        "2027 -- a fixed cost component that does NOT reverse with fuel prices and "
                        "pushes the total rate up, certainly. Sized larger than the fuel tailwind "
                        "because it is certain and structural while the fuel easing is a modest "
                        "forecast: for YES, the uncertain fuel decline must outrun a locked increase."
                    ),
                },
            ],
        },
        "3": {
            "reference_class": (
                "Direction of the reported US 2027 data-center capacity gap versus the <30% "
                "resolution threshold -- a qualitative read, since the trend data is too small "
                "and methodologically mixed to fit"
            ),
            "base_rate_pct": 4.0,
            "base_rate_source": (
                "Qualitative, not a trend fit. Reframed from tier-2 because the real data cannot "
                "support a trustworthy fit (see tier2['3'] archive and methodology_notes.md #3). The "
                "reported gap is 68-80% and stable-to-widening: 2026 pipeline 68.75% (Feb) -> ~68% "
                "(Apr) per Sightline; 2027-specific 70.7% (Apr, Sightline/Bloomberg) -> ~80% (Jun, "
                "Jefferies). YES requires the gap to roughly HALVE -- ~45pp, from ~75% to <30% -- "
                "within ~18 months while it is currently WIDENING, with no supporting trend evidence. "
                "The only non-fanciful path is a large downward revision of the planned pipeline (an "
                "AI-capex pullback shrinking the denominator). CAVEAT: the two 2027-specific points "
                "are from different trackers (Sightline vs Jefferies) and the resolution-metric series "
                "is n=2 -- too small for any formal significance test; the abandoned tier-2 fit "
                "perversely returned 9-13% (rising with horizon) as an artifact of fat-tailed n=4 "
                "bands, which is rejected in favor of this ~4% qualitative call."
            ),
            "adjustments": [],
        },
        "1": {
            "reference_class": "China advanced-computing/semiconductor export control actions, 2022-2026, Federal Register",
            "base_rate_pct": 93.0,
            "base_rate_source": (
                "93% = tightening share of substantive actions in a full audit of 35 China "
                "advanced-computing/semiconductor Federal Register rules, 2022-2026: 26 tightening / "
                "2 loosening / 7 noise, base rate = 26/(26+2). The 2 loosening actions are routine "
                "entity de-listings after review, NOT relaxation of chip controls -- there is no "
                "substantive loosening of China advanced-chip policy in the window. Bracketed 89-100% "
                "by inclusion definition: core chip-tech rules only = 9/0 = 100%; chip rules + "
                "China-only entity additions = 16/2 = 89%; full China-majority set = 26/2 = 93%. "
                "Tightening runs 89-100% every year 2022-2025 with no pause. Derived from the cached "
                "Federal Register docket (federal_register_bis_export_controls.json); replaces the "
                "earlier 55% placeholder."
            ),
            "adjustments": [
                {
                    "name": "Bipartisan political momentum",
                    "direction": "up",
                    "magnitude_pts": 2.0,
                    "rationale": (
                        "The mercantilist/tech-restriction posture toward China has bipartisan "
                        "support and has continued across administrations. Only a small upward nudge: "
                        "the base rate is already near the ceiling, so there is little headroom for an "
                        "upward adjustment to move."
                    ),
                },
                {
                    "name": "Diminishing room to tighten further",
                    "direction": "down",
                    "magnitude_pts": 3.0,
                    "rationale": (
                        "Controls are already extensive after four years of near-continuous "
                        "tightening; fewer high-value targets may remain to add before the Dec 2026 "
                        "resolution, and a base rate near 100% has mild mean-reversion room and cannot "
                        "rise. Small, and it does not threaten a YES on its own -- YES needs only one "
                        "tightening action, which the cadence still easily supplies."
                    ),
                },
                {
                    "name": "2025 H20 licensing reversal / transactional posture",
                    "direction": "down",
                    "magnitude_pts": 2.0,
                    "rationale": (
                        "In 2025 the administration reversed an earlier restriction and authorized "
                        "resumption of Nvidia H20 (and AMD) advanced-AI-chip sales to China under a "
                        "licensing arrangement -- a concrete, item-specific relaxation NOT captured in "
                        "the audited rule set (a licensing-policy action, not an Entity List/EAR rule), "
                        "so it adds genuinely new downside information rather than double-counting. It "
                        "signals willingness to relax specific China-chip controls for leverage/revenue, "
                        "nudging toward the 'relax/unchanged' pole. Kept small: it is a per-item carve-out, "
                        "not a repeal of the Entity List or the broad advanced-computing controls, and "
                        "the resolution bar (any tightening action in the window) remains easily met."
                    ),
                },
            ],
        },
        "4": {
            "reference_class": (
                "outcomes relative to a credible, forward-looking expert central estimate, "
                "absent specific evidence of bias"
            ),
            "base_rate_pct": 50.0,
            "base_rate_source": (
                "Judgment starting point, stated as such: there is no historical frequency for "
                "'beating a specific analyst's forward estimate', so 50% is the deliberate "
                "uninformed prior. Bridgewater's ~150bp is itself a forward judgment call, not a "
                "historical baseline; with no reason to think it is biased high, even odds is the "
                "honest anchor."
            ),
            "adjustments": [
                {
                    "name": "Q1 2026 real investment acceleration",
                    "direction": "up",
                    "magnitude_pts": 6.0,
                    "rationale": (
                        "Real information-processing investment jumped QoQ ($1,564B Q4'25 -> "
                        "$1,673B Q1'26 SAAR, ~+7%). Genuine momentum, but kept small: a single "
                        "volatile, seasonally-strong quarter (Q1 prints run well above full-year "
                        "averages), not proof of a full-year trend."
                    ),
                },
                {
                    "name": "Structures / physical-buildout boom",
                    "direction": "up",
                    "magnitude_pts": 6.0,
                    "rationale": (
                        "Nonresidential structures/capex buildout is visibly elevated (data-center "
                        "and CHIPS-fab construction). Sized conservatively because BEA structures "
                        "data mixes in substantial non-AI construction and cannot isolate data "
                        "centers -- a measurement-contamination caveat."
                    ),
                },
                {
                    "name": "Resolution metric narrower than the estimate's scope",
                    "direction": "down",
                    "magnitude_pts": 5.0,
                    "rationale": (
                        "The resolution line is the BEA IP-equipment/software contribution "
                        "(historically ~0.4pp), narrower than the total AI-capex scope Bridgewater's "
                        "150bp covers; clearing 150bp on the narrow measured line is a harder bar "
                        "than beating the headline estimate. A scope/definitional caveat, not a "
                        "trend extrapolation; kept modest given genuine ambiguity in resolution scope."
                    ),
                },
            ],
        },
        "6": {
            "reference_class": (
                "PCE inflation landing at or below a threshold by a horizon, benchmarked to the "
                "FOMC's own contemporaneous year-end projection distribution for the same variable"
            ),
            "base_rate_pct": 34.0,
            "base_rate_source": (
                "34% = midpoint of the 21-47% bound on the share of the 19 FOMC participants "
                "projecting 2026 PCE at or below 3.5%, derived from the June 2026 SEP (median 3.6%, "
                "central tendency 3.5-3.7%, range 2.7-4.1%; fomcprojtabl20260617.htm). This is "
                "sourced evidence from the body whose policy decisions drive the outcome -- a "
                "stronger anchor than a naive 50% or the flat historical trend fit. The exact "
                "per-participant count is not machine-readable (Figure 3.C is a chart image), so the "
                "bound's midpoint is used."
            ),
            "adjustments": [
                {
                    "name": "Fed's active hawkish posture",
                    "direction": "up",
                    "magnitude_pts": 10.0,
                    "rationale": (
                        "Forecast #5's authoritative probability is now 77.5% (its HMM base rate "
                        "blended with CME FedWatch market pricing), up from the 63% HMM-only figure, "
                        "and the June 2026 SEP median dot (3.8%) sits above the current 3.625% "
                        "midpoint (~one more hike signalled). Hiking is the Fed's direct tool for "
                        "pushing inflation back toward target, so a materially higher, "
                        "market-corroborated hike probability raises P(PCE -> at or below 3.5%) more "
                        "than the HMM-only read did. Sized up from +6pp to +10pp accordingly, but "
                        "still bounded: hikes act with long lags and do not guarantee the target is "
                        "hit by the Dec print."
                    ),
                },
                {
                    "name": "Recent trend momentum (wrong direction)",
                    "direction": "down",
                    "magnitude_pts": 12.0,
                    "rationale": (
                        "PCE YoY accelerated 2.87 -> 2.87 -> 3.54 -> 3.80 -> 4.07 over the last five "
                        "prints -- real, recent, and moving away from YES; the linear trend projects "
                        "~4.49% for Dec 2026. Strongest concrete evidence against resolution, hence "
                        "the largest single adjustment."
                    ),
                },
                {
                    "name": "Single-print resolution dispersion",
                    "direction": "up",
                    "magnitude_pts": 3.0,
                    "rationale": (
                        "Resolution is a single Dec 2026 YoY print, and monthly YoY has swung up to "
                        "~0.67pp in one month recently (Feb->Mar). That realized-print volatility "
                        "(distinct from the SEP's dispersion of participant point views) puts real "
                        "left-tail mass below 3.5% even with the central path above it. Small, and it "
                        "is the same narrow-band-understates-uncertainty point that motivated the "
                        "reframe."
                    ),
                },
            ],
        },
        "5": {
            # Tier-3 layer sitting ON TOP of #5's Tier-1 HMM. The HMM's own Monte
            # Carlo output is the base rate here (not an independent reference
            # class); the single adjustment blends that historical estimate toward
            # current market pricing. The HMM model view is unchanged and remains
            # the base-rate input. base_rate_pct is refreshed from the HMM whenever
            # the simulation is rerun (see Tier1ModelScreen.rerun_simulation).
            "reference_class": (
                "P(>=1 rate hike in 2026) from this project's own Fed-posture HMM "
                "(an unconditional historical base rate), blended toward current "
                "market pricing -- not a separate reference-class frequency"
            ),
            "base_rate_pct": 62.5,
            "base_rate_source": (
                "This model's own unconditional historical estimate: the Fed posture "
                "HMM's Monte Carlo P(at least one hike by year-end 2026), 5,000 paths, "
                "seed 20260716 (tier1_market.py). NOT an independent number -- the HMM "
                "output IS the base rate for this layer."
            ),
            "adjustments": [
                {
                    "name": "CME FedWatch cumulative market pricing",
                    "direction": "up",
                    "magnitude_pts": 15.0,
                    "rationale": (
                        "CME FedWatch (as of 2026-07-21) prices P(0 hikes by Dec) = "
                        "12.9%, i.e. 87.1% P(>=1 hike) -- a +24.6pp gap over the HMM's "
                        "unconditional 62.5%. A real, current, market-priced signal "
                        "incorporating all 2026-specific information the HMM's pooled "
                        "history ignores. Sized as a partial blend (~60% weight to the "
                        "market, +15pp of the 24.6pp gap), NOT a full override: the "
                        "market's per-meeting hazard spikes to 61.5% at September "
                        "(possible overreaction to the May 2026 CPI print) and its July "
                        "read (21.9%) diverges from Polymarket's 10.7%, so the historical "
                        "anchor is retained. Dot-plot posture and inflation are "
                        "deliberately NOT added as separate factors -- they are already "
                        "priced into this CME number (no double-count)."
                    ),
                },
            ],
        },
        "2": {
            "reference_class": (
                "First-year federal loan-based industrial-policy financing vehicles expanding committed "
                "capacity within their first calendar year of operation"
            ),
            "base_rate_pct": 60.0,
            "base_rate_source": (
                "No clean tabulated frequency exists for this sparse, heterogeneous class (DOE LPO/ATVM, "
                "DPA Title III, CHIPS, EXIM facilities all differ in structure), so 60% is a reasoned "
                "structural prior -- stated as such -- not a counted rate. Anchored on Project Vault's own "
                "design: committed capacity scales with OEM purchase commitments rather than a fixed cap, "
                "so expansion is the program's default growth mechanism, not an exceptional event (prior "
                "above 50%). Three independent YES-paths exist (EXIM Board additional authorization; new "
                "private co-investment; Congressional appropriation), two of which do not require Congress. "
                "Held at 60% rather than higher by first-calendar-year timing risk: only ~11 months "
                "(Feb 2 -> Dec 31, 2026) for a formal expansion action to actually complete, and new "
                "programs often spend year one standing up the initial commitment."
            ),
            "adjustments": [
                {
                    "name": "Administration's stated expansion intent",
                    "direction": "up",
                    "magnitude_pts": 9.0,
                    "rationale": (
                        "State Dept on the record: 'this is only the beginning... dozens of additional "
                        "projects in the pipeline... with more coming online soon.' Corroborated by EXIM's "
                        "demonstrated adjacent pace ($14.8B in separate critical-minerals LOIs over the "
                        "past year). The $14.8B is folded in here as supporting momentum evidence -- not a "
                        "separate factor and not the base rate -- because it is related activity, not "
                        "literally Vault's committed capacity."
                    ),
                },
                {
                    "name": "Political/budget risk and first-year execution timing",
                    "direction": "down",
                    "magnitude_pts": 8.0,
                    "rationale": (
                        "The Congressional-appropriation path is slow and uncertain; formal EXIM Board or "
                        "private-capital actions can slip past Dec 31; general budget/political friction "
                        "applies. The only identified counterfactor, sized to roughly offset the bullish "
                        "intent so the estimate stays near the structural base rate."
                    ),
                },
            ],
        },
        "7": {
            "reference_class": (
                "Growth pace of strict-scope non-US/non-China public-sector sovereign AI-infrastructure "
                "commitments -- can the cumulative total cross $250B by Dec 31, 2026 from a ~$90B base"
            ),
            "base_rate_pct": 12.0,
            "base_rate_source": (
                "Pace-based, not a coin flip. Current strict-scope cumulative base is ~$85-90B as of "
                "Jul 2026 (EU InvestAI $22B, Gulf-domestic SWF portion ~$25B, Japan $15B, France $11B, "
                "Korea $8B, UK $3B, Canada $2B, India $1.25B), leaving a ~$160B gap to $250B. This "
                "category grew from ~$0 to ~$90B in ~18 months (the 2025-26 wave), a run-rate of "
                "~$55-65B/yr; even a doubled/accelerating pace (~$120B/yr) reaches only ~$140B by "
                "year-end. Crossing $250B needs ~$160B in ~5 months = ~$385B/yr annualized, a 4-6x "
                "acceleration over an already record pace. 12% = probability of a lumpy but "
                "momentum-driven category adding ~1.8x its entire accumulated base in 5 months."
            ),
            "adjustments": [
                {
                    "name": "Geopolitical / administration momentum",
                    "direction": "up",
                    "magnitude_pts": 7.0,
                    "rationale": (
                        "A genuine sovereign-AI arms race (US Stargate $500B triggering EU/Gulf/Asia "
                        "responses). The upside path is a cluster of large discrete new sovereign "
                        "commitments -- a China-response package, new EU 'AI continent' money, fresh Gulf "
                        "domestic pledges. Real and substantial per all sourcing gathered; sized to the "
                        "chance that lumpiness plus momentum produces a burst that beats the trend pace."
                    ),
                },
                {
                    "name": "Budget-cycle deceleration and timing",
                    "direction": "down",
                    "magnitude_pts": 5.0,
                    "rationale": (
                        "Most 2026 public budgets were already announced earlier this year (Japan "
                        "Dec 2025, Korea and UK 2026), so net-new large PUBLIC commitments tend to slow "
                        "in the Aug-Dec window; and continuation of even the record pace still lands "
                        "~$110B short of the threshold."
                    ),
                },
            ],
        },
        "8": {
            "reference_class": (
                "A government executing a strategic/control sovereign equity stake or a formal "
                "national-champion legal designation in a frontier AI model/lab company within a "
                "~5-month window (narrow scope; portfolio-style SWF/state-bank stakes excluded)"
            ),
            "base_rate_pct": 10.0,
            "base_rate_source": (
                "No direct precedent exists for a strategic/control sovereign stake or a formal "
                "national-champion designation in a frontier AI LAB. But the policy tool is demonstrably "
                "live in adjacent strategic tech -- the May 2026 US-Intel strategic stake and the "
                "2025-26 wave of government stakes in critical-tech firms show the taboo is broken -- so "
                "the rate is not ~0. Extending it to a lab AND executing (not merely proposing) within "
                "the ~5 months to Dec 31, 2026 is a high bar, hence 10%. Portfolio-style stakes by "
                "government-linked SWFs/state banks (MGX, HUMAIN, Bpifrance) are excluded by scope as "
                "financial investments, not industrial-policy interventions."
            ),
            "adjustments": [
                {
                    "name": "France/Mistral warm path",
                    "direction": "up",
                    "magnitude_pts": 5.0,
                    "rationale": (
                        "The single most plausible near-term catalyst. France openly frames Mistral as "
                        "its national/European champion; the ASML foreign-ownership stake fuels an active "
                        "sovereignty debate; and the state is already entangled (Bpifrance stake, Jan 2026 "
                        "Ministry of Armies contract). A move to a formal designation or strategic stake "
                        "is the realistic YES route. Tempered because France is still at framing/procurement "
                        "-- a formal, executed action in 5 months would be an escalation, not a continuation."
                    ),
                },
                {
                    "name": "US disinclination and the execution bar",
                    "direction": "down",
                    "magnitude_pts": 6.0,
                    "rationale": (
                        "7-8 of the 10 listed labs are US-based (OpenAI, Anthropic, xAI, Meta, Microsoft, "
                        "Amazon, SSI; DeepMind is UK-sited but Google-owned), and the US is moving the "
                        "opposite direction: the June 2, 2026 EO creates a 'covered frontier model' "
                        "security-review label while explicitly banning mandatory licensing/protection, and "
                        "the DoW designated Anthropic a supply-chain risk. That takes the largest slice of "
                        "the list off the table. Combined with the 'executed by Dec 31, not merely proposed' "
                        "requirement, it is the dominant drag -- slightly outweighing the France catalyst."
                    ),
                },
            ],
        },
        "10": {
            "reference_class": (
                "Finalization (not mere proposal) of at least one of three EO-accelerated federal "
                "nuclear-licensing/permitting actions within the resolution window, judged against "
                "the mandated rulemaking timeline rather than the historical NRC pace"
            ),
            "base_rate_pct": 80.0,
            "base_rate_source": (
                "Timeline-based, not a generic prior. EO 14300 (May 23, 2025) directs the NRC to "
                "publish FINAL rules within 18 months -- by Nov 23, 2026 -- which sits ~13 months "
                "INSIDE the 2027-12-31 resolution window; the NRC has publicly committed to a timeline "
                "to meet it. Part 57 (path a) was proposed May 1, 2026 with comments closed Jun 15, "
                "2026, so it is already in finalization. DOE's four selected sites (path b) target "
                "operations by end-2027, forcing permitting to be finalized in 2026-2027. Only ONE of "
                "three independent paths must finalize. Tempered from higher by the NRC's genuine "
                "history of slipping even statutory/EO deadlines and the strict 'finalized-not-proposed' "
                "bar. Historical NRC proposed-to-final pace is 3-6 years, but the current mandate + "
                "18-month runway + three shots is the operative reference class here."
            ),
            "adjustments": [
                {
                    "name": "Whole-of-government momentum and on-schedule execution",
                    "direction": "up",
                    "magnitude_pts": 6.0,
                    "rationale": (
                        "Not just an announced agenda: the NRC already proposed Part 57 on cadence, DOE "
                        "already selected the four sites, and four reinforcing May-2025 nuclear EOs plus "
                        "the 2024 ADVANCE Act all push the same direction. The machine is executing, not "
                        "just planning."
                    ),
                },
                {
                    "name": "NRC finalization slippage and litigation risk",
                    "direction": "down",
                    "magnitude_pts": 7.0,
                    "rationale": (
                        "NRC rulemakings routinely slip, and EO deadlines are directives agencies miss; "
                        "the 'finalized, not proposed' bar is strict; final rules can be litigated or "
                        "enjoined; and an administration-priority shift is a tail risk. Slightly "
                        "outweighs the momentum factor, so the net lands just under the base rate."
                    ),
                },
            ],
        },
    },
}


def _seed_threshold_defaults() -> None:
    """Fill in current/threshold values for the #9 threshold check from the latest
    cached observations, when the cache is present. No-op after #9 was reframed to a
    tier-3 estimate (tier1['9'] no longer exists); kept for any future threshold check."""
    config = DEFAULT_MODEL_STATE["tier1"].get("9")
    if not config:
        return
    electricity = _read_cache("eia_virginia_retail_electricity.json")
    if electricity:
        baseline = electricity.get("baseline") or {}
        base_price = baseline.get("price_cents_per_kwh")
        if base_price:
            config["threshold"] = round(base_price * 1.15, 3)
        observations = electricity.get("observations", [])
        if observations:
            config["current_value"] = observations[-1]["price_cents_per_kwh"]


_seed_threshold_defaults()


def load_model_state() -> dict:
    state = copy.deepcopy(DEFAULT_MODEL_STATE)
    if not FORECAST_STATE_PATH.exists():
        return state
    stored = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8")).get(MODEL_STATE_KEY, {})
    for tier, models in stored.items():
        if tier not in state or not isinstance(models, dict):
            continue
        for forecast_id, configuration in models.items():
            if forecast_id in state[tier] and isinstance(configuration, dict):
                state[tier][forecast_id].update(configuration)
    return state


MODEL_STATE = load_model_state()


def persist_model_state() -> None:
    state = {}
    if FORECAST_STATE_PATH.exists():
        state = json.loads(FORECAST_STATE_PATH.read_text(encoding="utf-8"))
    state[MODEL_STATE_KEY] = MODEL_STATE
    FORECAST_STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def forecast5_tier3_estimate(hmm_probability_pct: float) -> ReferenceClassEstimate:
    """Build #5's Tier-3 blend layer with the HMM output as the base rate.

    The HMM's Monte Carlo P(>=1 hike) is passed in as ``hmm_probability_pct`` so
    the layer always blends the *current* HMM output (not a stale stored base
    rate) with the market-pricing adjustment stored in MODEL_STATE.
    """
    config = MODEL_STATE["tier3"]["5"]
    return ReferenceClassEstimate(
        forecast_id=5,
        reference_class=config["reference_class"],
        base_rate_pct=hmm_probability_pct,
        base_rate_source=config["base_rate_source"],
        adjustments=[AdjustmentFactor(**factor) for factor in config["adjustments"]],
    )


def probability_text(value: float | None) -> str:
    # Display-only formatting: one decimal place with a percent sign, regardless
    # of the precision each script persisted to forecast_state.json.
    return "not set" if value is None else f"{value:.1f}%"


def validate_probability(raw_value: str) -> tuple[float | None, str | None]:
    try:
        probability = float(raw_value)
    except ValueError:
        return None, "Probability must be a number between 0 and 100 inclusive; value not changed."
    if not math.isfinite(probability) or not 0 <= probability <= 100:
        return None, "Probability must be a finite number between 0 and 100 inclusive; value not changed."
    return probability, None


def detail_markup(forecast_id: int) -> str:
    forecast = get(forecast_id)
    notes = forecast.notes if forecast.notes else "not set"
    return (
        f"[bold]Question[/bold]\n{escape(forecast.question)}\n\n"
        f"[bold]Resolution date[/bold]\n{escape(forecast.resolution_date)}\n\n"
        f"[bold]Resolution criteria[/bold]\n{escape(forecast.resolution_criteria)}\n\n"
        f"[bold]Model type[/bold]\n{escape(format_model_type(forecast))}\n\n"
        f"[bold]Probability[/bold]\n{escape(probability_text(forecast.probability))}\n\n"
        f"[bold]Notes[/bold]\n{escape(notes)}"
    )


class ForecastDetailScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close", show=False),
        Binding("m", "open_model", "Model"),
    ]

    def __init__(self, forecast_id: int) -> None:
        super().__init__()
        self.forecast_id = forecast_id

    def compose(self) -> ComposeResult:
        forecast = get(self.forecast_id)
        with Container(id="detail-panel"):
            yield Label(f"Forecast #{forecast.id}: {forecast.title}", id="detail-title")
            yield Static(detail_markup(self.forecast_id), id="detail-body", markup=True)
            yield Label("m model · Esc or Enter to close", id="detail-hint")

    def action_open_model(self) -> None:
        views = available_model_views(self.forecast_id)
        if not views:
            self.app.notify("No tier-specific model inputs are configured", severity="warning")
            return
        if len(views) == 1:
            self._open_tier_view(views[0][0])
            return
        # Multi-tier forecast: let the user pick rather than defaulting to one.
        self.app.push_screen(
            TierViewPickerScreen(self.forecast_id, views),
            callback=self._tier_picked,
        )

    def _tier_picked(self, tier: int | None) -> None:
        if tier is not None:
            self._open_tier_view(tier)

    def _open_tier_view(self, tier: int) -> None:
        screen = build_model_screen(self.forecast_id, tier)
        if screen is None:
            self.app.notify("That tier has no model view", severity="warning")
            return
        self.app.push_screen(screen, callback=self.model_closed)

    def model_closed(self, changed: bool | None) -> None:
        if changed:
            self.query_one("#detail-body", Static).update(detail_markup(self.forecast_id))
            app = self.app
            if isinstance(app, ForecastApp):
                app.refresh_probability(self.forecast_id)


class ProbabilityEditScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, forecast_id: int) -> None:
        super().__init__()
        self.forecast_id = forecast_id

    def compose(self) -> ComposeResult:
        forecast = get(self.forecast_id)
        current = "" if forecast.probability is None else str(forecast.probability)
        with Vertical(id="probability-dialog"):
            yield Label(f"Set probability — Forecast #{forecast.id}", id="probability-title")
            yield Label(forecast.title, id="probability-forecast-title")
            yield Input(value=current, placeholder="0 to 100", id="probability-input", select_on_focus=True)
            yield Static("", id="probability-error")
            yield Label("Enter to save · Esc to cancel", id="probability-hint")

    def on_mount(self) -> None:
        self.query_one("#probability-input", Input).focus()

    @on(Input.Submitted, "#probability-input")
    def save_probability(self, event: Input.Submitted) -> None:
        probability, error = validate_probability(event.value.strip())
        if error is not None:
            self.query_one("#probability-error", Static).update(f"[red]{escape(error)}[/red]")
            return
        assert probability is not None
        set_forecast_probability(self.forecast_id, probability)
        persist_model_state()
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class Tier1ModelScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "close", "Close"), Binding("q", "close", "Close")]

    def __init__(self) -> None:
        super().__init__()
        self.model = estimate_fed_posture_hmm()
        self.simulations = int(MODEL_STATE["tier1"]["5"]["simulations"])
        self.result = p_at_least_one_hike_hmm(
            self.model,
            simulations=self.simulations,
            random_seed=DEFAULT_RANDOM_SEED,
        )
        self.changed = False

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label("Tier 1 model — Forecast #5 (Fed posture HMM)", classes="model-title")
            with Horizontal(classes="input-row"):
                yield Label("Monte Carlo paths:", classes="input-label")
                yield Input(str(self.simulations), id="simulation-paths", select_on_focus=True)
            yield Static("", id="model-error")
            yield Static("", id="current-state")
            yield Static(self._state_diagram_markup(), id="state-diagram")
            yield Label("Simulated hike-count distribution", classes="section-label")
            yield DataTable(id="outcome-table", zebra_stripes=True)
            yield Static("", id="outcome-histogram")
            yield Static("", id="fedwatch-crosscheck")
            yield Static("", id="tier3-blend")
            yield Label("Enter in paths field to rerun · Esc to close", classes="model-hint")

    def _state_diagram_markup(self) -> str:
        """Render the HMM as a left-to-right posture chain: three state nodes
        (each showing its P(hike/hold/cut) emissions), bidirectional transition
        arrows between neighbours, a distinct self-loop (↺) above each node, and
        the direct hawkish<->dovish link as an arc beneath."""
        tm, em = self.model.transition_matrix, self.model.emission_matrix
        states = list(POSTURE_STATES)
        color = {"hawkish_bias": "red", "neutral_hold": "yellow", "dovish_bias": "green"}
        W, GAP = 13, 8

        def box(state: str) -> list[str]:
            return [
                "┌" + "─" * W + "┐",
                "│" + state.upper().ljust(W) + "│",
                "│" + f"hike {em[state]['hike']:.2f}".ljust(W) + "│",
                "│" + f"hold {em[state]['hold']:.2f}".ljust(W) + "│",
                "│" + f"cut  {em[state]['cut']:.2f}".ljust(W) + "│",
                "└" + "─" * W + "┘",
            ]

        boxes = [box(state) for state in states]

        def tint(state: str, text: str) -> str:
            return f"[{color[state]}]{text}[/]"

        def gap(line_index: int, left: str, right: str) -> str:
            if line_index == 1:
                return f"──{tm[left][right]:.2f}─►"   # forward, along the top
            if line_index == 3:
                return f"◄─{tm[right][left]:.2f}──"   # return, along the bottom
            return " " * GAP

        lines = []
        self_loops = ""
        for index, state in enumerate(states):
            self_loops += tint(state, ("↺" + f"{tm[state][state]:.2f}").center(W + 2))
            if index < len(states) - 1:
                self_loops += " " * GAP
        lines.append(self_loops)
        for line_index in range(6):
            lines.append(
                tint(states[0], boxes[0][line_index])
                + gap(line_index, states[0], states[1])
                + tint(states[1], boxes[1][line_index])
                + gap(line_index, states[1], states[2])
                + tint(states[2], boxes[2][line_index])
            )
        total = (W + 2) * 3 + GAP * 2
        arc = (
            f" hawkish ⇄ dovish (direct):  →{tm['hawkish_bias']['dovish_bias']:.2f}"
            f"  ←{tm['dovish_bias']['hawkish_bias']:.2f} "
        )
        lines.append("╰" + arc.center(total - 2, "─") + "╯")
        legend = (
            "[dim]Nodes = posture states with P(hike/hold/cut) emissions · arrows = "
            "transition probs · ↺ = stay (self-transition)[/dim]"
        )
        return "\n".join(lines) + "\n" + legend

    def on_mount(self) -> None:
        self.query_one("#current-state", Static).update(
            "[bold]Starting posture[/bold] (initial state distribution): "
            + " · ".join(
                f"{state}=[bold]{self.model.initial_state_distribution[state]:.2f}[/bold]"
                for state in POSTURE_STATES
            )
        )
        outcome = self.query_one("#outcome-table", DataTable)
        outcome.add_column("Outcome", key="outcome")
        outcome.add_column("Probability", key="probability")
        outcome.add_column("Paths", key="paths")
        for label in ("0 hikes", "1 hike", "2+ hikes"):
            outcome.add_row(label, "", "", key=label)
        self.update_result_widgets()

    def update_result_widgets(self) -> None:
        outcome = self.query_one("#outcome-table", DataTable)
        bars = []
        for label, probability in self.result.hike_count_distribution.items():
            outcome.update_cell(label, "probability", f"{probability * 100:.1f}%")
            outcome.update_cell(label, "paths", f"{self.result.raw_counts[label]:,}")
            bars.append(f"{label:8} {'█' * round(probability * 36)} {probability * 100:.1f}%")
        self.query_one("#outcome-histogram", Static).update("\n".join(bars))
        historical_hike = self.model.emission_matrix["hawkish_bias"]["hike"]
        self.query_one("#fedwatch-crosscheck", Static).update(
            f"HMM P(hike | hawkish): [bold]{historical_hike * 100:.1f}%[/bold] · "
            f"July 29 market P(hike): [bold]{CME_FEDWATCH_JULY_29_HIKE_PROBABILITY * 100:.1f}%[/bold] "
            f"(as of {CME_FEDWATCH_JULY_29_AS_OF})\n"
            f"[dim]Source: {CME_FEDWATCH_JULY_29_SOURCE}. Historical state base rate versus "
            "meeting-specific live pricing; divergence is expected. July 29's simulated hike "
            "odds are pinned to this market read, not the HMM emission.[/dim]"
        )
        self._render_tier3_blend()

    def _render_tier3_blend(self) -> None:
        """Show the Tier-3 layer that sits on top of this HMM: the HMM's own
        P(>=1 hike) is the base rate, blended toward CME market pricing. The HMM
        itself (matrices, diagram, histogram) is unchanged -- this is a separate
        layer whose output is #5's authoritative probability."""
        hmm_pct = round(self.result.probability_at_least_one_hike * 100, 1)
        estimate = forecast5_tier3_estimate(hmm_pct)
        line = (
            f"[bold]Tier-3 blend layer[/bold] (this HMM is the base-rate input): "
            f"base [bold]{hmm_pct:.1f}%[/bold]"
        )
        for adj in estimate.adjustments:
            sign = "+" if adj.direction == "up" else "-"
            line += f" · {adj.name} [bold]{sign}{adj.magnitude_pts:.0f}pp[/bold]"
        line += (
            f"\n→ authoritative #5 = [bold]{estimate.final_probability():.1f}%[/bold] "
            "[dim](blended P(>=1 hike); persisted value)[/dim]"
        )
        self.query_one("#tier3-blend", Static).update(line)

    @on(Input.Submitted, "#simulation-paths")
    def rerun_simulation(self, event: Input.Submitted) -> None:
        try:
            simulations = int(event.value)
        except ValueError:
            simulations = 0
        if not 1 <= simulations <= 1_000_000:
            self.query_one("#model-error", Static).update(
                "[red]Paths must be a whole number between 1 and 1,000,000.[/red]"
            )
            return
        self.query_one("#model-error", Static).update("")
        self.simulations = simulations
        self.result = p_at_least_one_hike_hmm(
            self.model,
            simulations=simulations,
            random_seed=DEFAULT_RANDOM_SEED,
        )
        hmm_pct = round(self.result.probability_at_least_one_hike * 100, 1)
        MODEL_STATE["tier1"]["5"]["simulations"] = simulations
        # The HMM output is the base rate of #5's Tier-3 blend layer; refresh it
        # and persist the *blended* probability, never the raw HMM value.
        MODEL_STATE["tier3"]["5"]["base_rate_pct"] = hmm_pct
        blended = round(forecast5_tier3_estimate(hmm_pct).final_probability(), 1)
        set_forecast_probability(5, blended)
        persist_model_state()
        self.changed = True
        self.update_result_widgets()

    def action_close(self) -> None:
        self.dismiss(self.changed)


class Tier2ModelScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "close", "Close"), Binding("q", "close", "Close")]

    def __init__(self, forecast_id: int) -> None:
        super().__init__()
        self.forecast_id = forecast_id
        self.configuration = MODEL_STATE["tier2"][str(forecast_id)]
        self.changed = False
        self.projection: dict = {}
        self.distance: dict = {}
        self.recalculate()

    @property
    def points(self) -> list[TrendPoint]:
        return [TrendPoint(item["period"], float(item["value"])) for item in self.configuration["points"]]

    def recalculate(self) -> None:
        # A trend fit needs at least 3 points; below that, leave the projection
        # empty so the view opens as a blank table the user can populate.
        if len(self.points) < 3:
            self.projection = {}
            self.distance = {}
            return
        periods_ahead = int(self.configuration["periods_ahead"])
        self.projection = linear_trend_projection(self.points, periods_ahead)
        # Identical pipeline to the batch trend forecasts in tier2_trend.py:
        # walk-forward RMSE floor + regression prediction-error multiplier +
        # small-sample penalty, so this view is the one authoritative number.
        self.distance = distance_to_threshold_in_sigma(
            self.projection["projected_value"],
            float(self.configuration["threshold"]),
            self.projection["residual_std"],
            n_points=len(self.points),
            periods_ahead=periods_ahead,
            out_of_sample_rmse=walk_forward_rmse(self.points),
        )

    def trend_probability(self) -> float | None:
        if not self.projection or not self.distance:
            return None
        effective_std = self.distance.get("effective_residual_std")
        if not effective_std or effective_std <= 0:
            return None
        return threshold_probability(
            self.projection["projected_value"],
            float(self.configuration["threshold"]),
            effective_std,
            yes_if_at_or_below=bool(self.configuration["yes_if_at_or_below"]),
            degrees_of_freedom=self.distance.get("degrees_of_freedom"),
        )

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label(f"Trend model — Forecast #{self.forecast_id}", classes="model-title")
            yield PlotextPlot(id="trend-chart")
            yield Static("", id="trend-statistics")
            if self.configuration.get("nowcast"):
                yield Static("", id="trend-nowcast")
            yield Label("Observed data (editable)", classes="section-label")
            yield DataTable(id="trend-points", zebra_stripes=True)
            with Horizontal(classes="input-row"):
                yield Input(placeholder="Period label", id="new-period")
                yield Input(placeholder="Value", id="new-value")
            yield Static("", id="trend-error")
            yield Label("Enter in Value to add and refit · Esc to close", classes="model-hint")

    def on_mount(self) -> None:
        table = self.query_one("#trend-points", DataTable)
        table.add_columns("Period", "Observed", "Fitted")
        self.update_widgets()

    def fitted_values(self) -> list[float]:
        if not self.projection or not self.points:
            return []
        values = [point.value for point in self.points]
        slope = self.projection["slope_per_period"]
        intercept = mean(values) - slope * mean(range(len(values)))
        return [slope * index + intercept for index in range(len(values))]

    def _replot(self) -> None:
        """Draw the scatter of observed points, the fitted trend line extended
        to the projection, and the resolution threshold as a horizontal
        reference line -- so the distance from projection to threshold is
        visible at a glance. This is the primary view; numbers sit below it."""
        chart = self.query_one("#trend-chart", PlotextPlot)
        plt = chart.plt
        plt.clear_figure()
        threshold = float(self.configuration["threshold"])
        xs = list(range(len(self.points)))
        ys = [point.value for point in self.points]
        labels = [point.period for point in self.points]
        tick_positions, tick_labels = xs, labels
        if ys:
            plt.scatter(xs, ys, marker="dot", color="cyan")
        if self.projection:
            slope = self.projection["slope_per_period"]
            intercept = self.fitted_values()[0]
            proj_x = (len(self.points) - 1) + int(self.configuration["periods_ahead"])
            line_xs = list(range(proj_x + 1))
            plt.plot(line_xs, [slope * x + intercept for x in line_xs], color="yellow")
            plt.scatter([proj_x], [self.projection["projected_value"]], marker="+", color="yellow")
            tick_positions, tick_labels = xs + [proj_x], labels + ["proj"]
        plt.horizontal_line(threshold, color="red")
        if tick_positions:
            plt.xticks(tick_positions, tick_labels)
        plt.title(
            f"cyan dots = observed · yellow = fitted trend + projection · "
            f"red line = threshold ({threshold:g})"
        )
        chart.refresh()

    def update_widgets(self) -> None:
        self._replot()
        table = self.query_one("#trend-points", DataTable)
        table.clear()
        fitted_values = self.fitted_values()
        for index, point in enumerate(self.points):
            fitted = f"{fitted_values[index]:.3f}" if fitted_values else "—"
            table.add_row(point.period, f"{point.value:.3f}", fitted)
        nowcast = self.configuration.get("nowcast")
        if nowcast:
            self.query_one("#trend-nowcast", Static).update(
                f"[bold]Nowcast overlay — {escape(str(nowcast['period']))}: "
                f"{float(nowcast['value']):+.2f}[/bold]  [dim](not in the fit)[/dim]\n"
                f"[dim]{escape(nowcast['label'])}[/dim]"
            )
        statistics_widget = self.query_one("#trend-statistics", Static)
        if not self.projection:
            statistics_widget.update(
                f"[dim]{len(self.points)} of 3 data points needed to fit a trend. "
                "Add a period label and value below to build the series.[/dim]\n"
                f"Threshold: {float(self.configuration['threshold']):.1f}"
            )
            return
        probability = self.trend_probability()
        probability_text = "not set" if probability is None else f"{probability:.1f}%"
        direction = "at or below" if self.configuration["yes_if_at_or_below"] else "above"
        statistics_widget.update(
            f"Fitted line: y = {self.projection['slope_per_period']:.4f}x + "
            f"{fitted_values[0]:.4f}\n"
            f"Projection ({self.configuration['periods_ahead']} periods ahead): "
            f"[bold]{self.projection['projected_value']:.3f}[/bold] · "
            f"Residual std: [bold]{self.projection['residual_std']:.3f}[/bold]\n"
            f"Threshold: YES if {direction} {float(self.configuration['threshold']):.1f} · "
            f"Sigma distance: [bold]{self.distance['z']}[/bold] · {escape(self.distance['read'])}\n"
            f"Student-t trend YES probability: [bold]{probability_text}[/bold]"
        )

    @on(Input.Submitted, "#new-value")
    def add_point(self, event: Input.Submitted) -> None:
        period = self.query_one("#new-period", Input).value.strip()
        try:
            value = float(event.value)
        except ValueError:
            value = math.nan
        if not period or not math.isfinite(value):
            self.query_one("#trend-error", Static).update(
                "[red]Provide a period label and a finite numeric value.[/red]"
            )
            return
        self.query_one("#trend-error", Static).update("")
        self.configuration["points"].append({"period": period, "value": value})
        self.recalculate()
        probability = self.trend_probability()
        if probability is not None:
            set_forecast_probability(self.forecast_id, probability)
        persist_model_state()
        self.changed = True
        self.update_widgets()
        self.query_one("#new-period", Input).value = ""
        event.input.value = ""

    def action_close(self) -> None:
        self.dismiss(self.changed)


class FactorEditScreen(ModalScreen[dict | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, factor: dict | None = None) -> None:
        super().__init__()
        self.factor = factor or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="factor-dialog"):
            yield Label("Adjustment factor", classes="model-title")
            yield Input(self.factor.get("name", ""), placeholder="Name", id="factor-name")
            yield Input(self.factor.get("direction", "up"), placeholder="up or down", id="factor-direction")
            yield Input(str(self.factor.get("magnitude_pts", "")), placeholder="Magnitude (percentage points)", id="factor-magnitude")
            yield Input(self.factor.get("rationale", ""), placeholder="Rationale", id="factor-rationale")
            yield Static("", id="factor-error")
            with Horizontal(classes="button-row"):
                yield Button("Save", id="save-factor", variant="primary")
                yield Button("Cancel", id="cancel-factor")

    @on(Button.Pressed)
    def button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-factor":
            self.dismiss(None)
            return
        name = self.query_one("#factor-name", Input).value.strip()
        direction = self.query_one("#factor-direction", Input).value.strip()
        rationale = self.query_one("#factor-rationale", Input).value.strip()
        try:
            magnitude = float(self.query_one("#factor-magnitude", Input).value)
            if not math.isfinite(magnitude) or magnitude < 0:
                raise ValueError
            factor = AdjustmentFactor(name, direction, magnitude, rationale)
        except ValueError as exc:
            message = str(exc) or "Magnitude must be a finite non-negative number."
            self.query_one("#factor-error", Static).update(f"[red]{escape(message)}[/red]")
            return
        if not name or not rationale:
            self.query_one("#factor-error", Static).update("[red]Name and rationale are required.[/red]")
            return
        self.dismiss({
            "name": factor.name,
            "direction": factor.direction,
            "magnitude_pts": factor.magnitude_pts,
            "rationale": factor.rationale,
        })

    def action_cancel(self) -> None:
        self.dismiss(None)


# Forecasts #2 and #8 deliberately carry NO quantitative model. The note is a
# first-class part of the model view: the absence of a stochastic model is a
# documented methodological choice, not a gap. See methodology_notes.md #2/#8.
JUDGMENT_ANCHORED_NOTES = {
    2: (
        "[bold]Deliberately judgment-anchored — no stochastic model, by design.[/bold]\n"
        "Project Vault is a single, five-month-old, first-of-its-kind program and the "
        "question is a single unprecedented institutional event. There is no event history "
        "to fit a rate to, no market pricing it, and the reference class is explicitly "
        "sparse and heterogeneous. Fitting a stochastic process to a class of one would "
        "manufacture parameters out of assumptions — false rigor, not real rigor. The "
        "honest quantitative form for this evidence is exactly this estimate: a stated "
        "structural prior plus named, sized, arguable adjustments."
    ),
    8: (
        "[bold]Deliberately judgment-anchored — no stochastic model, by design.[/bold]\n"
        "The question asks about a literally unprecedented event (no government has ever "
        "taken a strategic/control stake in, or granted formal champion designation to, a "
        "frontier AI lab) over an enumerated 10-company list in a five-month window, under "
        "a scope that excludes every executed government-linked stake that does exist. "
        "There is no historical frequency to fit and no arrival process to estimate — a "
        "stochastic model here would run on invented parameters. The honest quantitative "
        "form is this stated structural prior plus the two named, opposing adjustments."
    ),
}


class Tier3ModelScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("a", "add_factor", "Add"),
        Binding("e", "edit_factor", "Edit"),
        Binding("delete", "remove_factor", "Remove"),
        Binding("escape", "close", "Save & close"),
        Binding("q", "close", "Save & close"),
    ]

    def __init__(self, forecast_id: int) -> None:
        super().__init__()
        self.forecast_id = forecast_id
        self.configuration = MODEL_STATE["tier3"][str(forecast_id)]
        self.changed = False

    def estimate(self) -> ReferenceClassEstimate:
        return ReferenceClassEstimate(
            forecast_id=self.forecast_id,
            reference_class=self.configuration["reference_class"],
            base_rate_pct=float(self.configuration["base_rate_pct"]),
            base_rate_source=self.configuration["base_rate_source"],
            adjustments=[AdjustmentFactor(**factor) for factor in self.configuration["adjustments"]],
        )

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label(f"Tier 3 model — Forecast #{self.forecast_id}", classes="model-title")
            yield Label("Reference class", classes="input-label")
            yield Input(
                self.configuration["reference_class"],
                placeholder="Named comparable class of events",
                id="tier3-reference",
            )
            with Horizontal(classes="input-row"):
                yield Input(
                    str(self.configuration["base_rate_pct"]),
                    placeholder="Base rate %",
                    id="tier3-base-rate",
                )
                yield Input(
                    self.configuration["base_rate_source"],
                    placeholder="Base rate source",
                    id="tier3-source",
                )
            yield Static("", id="tier3-base-error")
            # For #6, the base rate is anchored to the Fed's SEP; show that
            # evidence right here alongside the number it justifies.
            if self.forecast_id == 6:
                yield Static("", id="sep-crosscheck")
            # #2/#8: the documented absence-of-a-model note is part of the view.
            if self.forecast_id in JUDGMENT_ANCHORED_NOTES:
                yield Static(JUDGMENT_ANCHORED_NOTES[self.forecast_id], id="judgment-note")
            yield Label("Reasoning build-up", classes="section-label")
            yield Static("", id="waterfall")
            # #4/#6: the same factors recombined as an explicit Bayesian update
            # (prior odds x likelihood ratios). The additive waterfall above
            # remains the editable store; this panel is the formal math.
            if self.forecast_id in BAYES_UPDATES:
                yield Static("", id="bayes-panel")
            yield Label("Adjustment factors (editable)", classes="section-label")
            yield DataTable(id="adjustment-table", zebra_stripes=True)
            yield Static("", id="final-probability")
            yield Label("a add · e edit · Delete remove · Esc save and close", classes="model-hint")

    @on(Input.Changed, "#tier3-reference")
    def reference_changed(self, event: Input.Changed) -> None:
        # Ignore no-op events, including the ones Textual fires when the inputs
        # first mount with their initial values -- otherwise merely opening a
        # blank forecast would mark it dirty and persist a probability on close.
        if event.value == self.configuration["reference_class"]:
            return
        self.configuration["reference_class"] = event.value
        self.changed = True

    @on(Input.Changed, "#tier3-source")
    def source_changed(self, event: Input.Changed) -> None:
        if event.value == self.configuration["base_rate_source"]:
            return
        self.configuration["base_rate_source"] = event.value
        self.changed = True

    @on(Input.Changed, "#tier3-base-rate")
    def base_rate_changed(self, event: Input.Changed) -> None:
        raw = event.value.strip()
        error = self.query_one("#tier3-base-error", Static)
        try:
            value = float(raw)
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError
        except ValueError:
            error.update("[red]Base rate must be a number between 0 and 100.[/red]" if raw else "")
            return
        error.update("")
        if value == float(self.configuration["base_rate_pct"]):
            return
        self.configuration["base_rate_pct"] = value
        self.changed = True
        self.update_widgets()

    def on_mount(self) -> None:
        table = self.query_one("#adjustment-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Name", "Direction", "Magnitude", "Rationale")
        if self.forecast_id == 6:
            self._render_sep_crosscheck()
        self.update_widgets()
        table.focus()

    def _render_sep_crosscheck(self) -> None:
        """Show the SEP evidence that anchors #6's base rate -- the Fed's own
        year-end PCE projection distribution and the participant-share bound the
        base rate is the midpoint of -- in the same screen as that base rate.
        These are point projections, not a probability distribution."""
        sep = CURRENT_SEP_PCE_PROJECTION
        low_ct, high_ct = sep["central_tendency_pct"]
        low_r, high_r = sep["full_range_pct"]
        threshold = sep["threshold_pct"]
        n = sep["participants"]
        low_n, high_n = sep["count_at_or_below_threshold_bound"]
        low_share, high_share = low_n / n * 100, high_n / n * 100
        # Midpoint is a fact about the SEP bound, not the editable base-rate
        # field, so the panel stays accurate even if the base rate is changed.
        midpoint = (low_share + high_share) / 2
        self.query_one("#sep-crosscheck", Static).update(
            "[bold]SEP evidence behind the base rate[/bold]\n"
            f"Fed {sep['sep_date']} SEP — median {sep['target_year']} {sep['measure']}: "
            f"[bold]{sep['median_pct']:.1f}%[/bold] · central tendency {low_ct:.1f}–{high_ct:.1f}% · "
            f"range {low_r:.1f}–{high_r:.1f}%\n"
            f"Participants projecting {sep['target_year']} PCE at or below {threshold:.1f}%: "
            f"[bold]{low_n}–{high_n} of {n}[/bold] → [bold]{low_share:.0f}–{high_share:.0f}%[/bold] "
            f"(midpoint ≈ [bold]{midpoint:.0f}%[/bold], the anchor for this base rate).\n"
            f"[dim]The {low_n}–{high_n} bound follows from the SEP's central-tendency floor "
            f"({low_ct:.1f}%) and median ({sep['median_pct']:.1f}%); the exact per-participant count "
            f"is not machine-readable (Figure 3.C is a chart image). SEP figures are point "
            f"projections, not a probability distribution.[/dim]\n"
            f"[dim]Source: {escape(sep['source_url'])}[/dim]"
        )

    def _waterfall_markup(self) -> str:
        """Horizontal waterfall: base rate as a solid bar from 0, each factor as
        a floating coloured step (green up / red down) positioned between the
        prior running total and the new one, then the final probability as a
        solid bar -- so the accumulation of reasoning is visible at a glance."""
        estimate = self.estimate()
        base = estimate.base_rate_pct
        width, label_width = 36, 24

        def pos(value: float) -> int:
            return round(max(0.0, min(100.0, value)) / 100 * width)

        def solid(value: float) -> str:
            filled = pos(value)
            return "█" * filled + " " * (width - filled)

        def step(prev: float, new: float, up: bool) -> str:
            lead = pos(min(prev, new))
            seg = max(pos(max(prev, new)) - lead, 1)
            trail = max(width - lead - seg, 0)
            glyph, colour = ("▓", ADJUSTMENT_UP_COLOR) if up else ("▒", ADJUSTMENT_DOWN_COLOR)
            return " " * lead + f"[{colour}]{glyph * seg}[/]" + " " * trail

        header = f"{'':<{label_width}}[dim]0%{' ' * (width - 6)}100%[/dim]"
        rows = [
            header,
            f"{'Base rate':<{label_width}}│{solid(base)}│  [bold]{base:.0f}%[/bold]",
        ]
        running = base
        for factor in self.configuration["adjustments"]:
            up = factor["direction"] == "up"
            magnitude = float(factor["magnitude_pts"])
            new = running + (magnitude if up else -magnitude)
            label = f"  {'+' if up else '−'}{magnitude:g} {factor['name']}"
            rows.append(f"{label[:label_width]:<{label_width}}│{step(running, new, up)}│  → {new:.0f}%")
            running = new
        final = estimate.final_probability()
        rows.append(f"{'Final probability':<{label_width}}│{solid(final)}│  [bold]{final:.0f}%[/bold]")
        return "\n".join(rows)

    def _render_bayes_panel(self) -> None:
        """Prior odds x per-factor likelihood ratios -> posterior, next to the
        LR each additive step implied — so agreement or divergence between the
        two formulations is visible factor by factor. LRs are the documented
        estimates in bayesian_update.py; editing the additive factors in this
        screen does not re-derive them."""
        report = bayesian_report(self.forecast_id)
        low, high = report["posterior_range_pct"]
        lines = [
            f"[bold]Bayesian formulation[/bold] — prior {report['prior_pct']:.0f}% "
            f"(odds {report['prior_odds']:.3f})",
            f"{'Factor':<42}{'LR (range)':>18}{'step':>8}{'implied LR':>12}",
        ]
        for factor in report["factors"]:
            colour = ADJUSTMENT_UP_COLOR if factor["lr"] >= 1 else ADJUSTMENT_DOWN_COLOR
            lr_text = (
                f"{factor['lr']:.2f} "
                f"({factor['lr_range'][0]:.2f}-{factor['lr_range'][1]:.2f})"
            )
            step_text = f"{factor['additive_step_pts']:+.0f}pp"
            lines.append(
                f"[{colour}]{factor['name'][:41]:<42}{lr_text:>18}"
                f"{step_text:>8}{factor['implied_additive_lr']:>12.2f}[/]"
            )
        lines.append(
            f"LR product [bold]{report['lr_product']:.3f}[/bold] → posterior odds "
            f"{report['posterior_odds']:.3f} → posterior [bold]{report['posterior_pct']:.1f}%[/bold] "
            f"(band {low:.0f}–{high:.0f}%)"
        )
        divergence = report["divergence_pts"]
        if abs(divergence) > 3:
            lines.append(
                f"[yellow]Diverges from the additive {report['additive_result_pct']:.1f}% by "
                f"{divergence:+.1f}pp — the additive number remains persisted: the momentum LR's "
                "empirical corroboration collapses to a single 2021–22 surge (n=1), too thin to "
                "adopt (decision documented in methodology_notes.md).[/yellow]"
            )
        else:
            lines.append(
                f"[dim]Confirms the additive {report['additive_result_pct']:.1f}% "
                f"({divergence:+.1f}pp). Full LR derivations: python3 bayesian_update.py[/dim]"
            )
        self.query_one("#bayes-panel", Static).update("\n".join(lines))

    def update_widgets(self) -> None:
        self.query_one("#waterfall", Static).update(self._waterfall_markup())
        if self.forecast_id in BAYES_UPDATES:
            self._render_bayes_panel()
        table = self.query_one("#adjustment-table", DataTable)
        table.clear()
        for index, factor in enumerate(self.configuration["adjustments"]):
            table.add_row(
                factor["name"],
                factor["direction"],
                f"{factor['magnitude_pts']}pp",
                factor["rationale"],
                key=str(index),
            )
        self.query_one("#final-probability", Static).update(
            f"Running final probability: [bold]{self.estimate().final_probability():.1f}%[/bold]"
        )

    def selected_factor_index(self) -> int | None:
        table = self.query_one("#adjustment-table", DataTable)
        if not self.configuration["adjustments"]:
            return None
        return table.cursor_row

    def action_add_factor(self) -> None:
        self.app.push_screen(FactorEditScreen(), callback=self.add_factor)

    def add_factor(self, factor: dict | None) -> None:
        if factor is not None:
            self.configuration["adjustments"].append(factor)
            self.changed = True
            self.update_widgets()

    def action_edit_factor(self) -> None:
        index = self.selected_factor_index()
        if index is None:
            self.app.notify("Select an adjustment factor first", severity="warning")
            return
        self.app.push_screen(
            FactorEditScreen(self.configuration["adjustments"][index]),
            callback=lambda factor: self.replace_factor(index, factor),
        )

    def replace_factor(self, index: int, factor: dict | None) -> None:
        if factor is not None:
            self.configuration["adjustments"][index] = factor
            self.changed = True
            self.update_widgets()

    def action_remove_factor(self) -> None:
        index = self.selected_factor_index()
        if index is None:
            self.app.notify("Select an adjustment factor first", severity="warning")
            return
        self.configuration["adjustments"].pop(index)
        self.changed = True
        self.update_widgets()

    def action_close(self) -> None:
        if self.changed:
            set_forecast_probability(self.forecast_id, round(self.estimate().final_probability(), 1))
            persist_model_state()
        self.dismiss(self.changed)


class Tier1ThresholdScreen(ModalScreen[bool]):
    """A tier-1 forecast without a wired probabilistic model. Shows a simple,
    editable point-in-time check: does the latest observation clear the
    threshold? The implied YES/NO is deterministic (0 or 100); it can be
    overridden with the p key on the forecast list."""

    BINDINGS = [Binding("escape", "close", "Close"), Binding("q", "close", "Close")]

    def __init__(self, forecast_id: int) -> None:
        super().__init__()
        self.forecast_id = forecast_id
        self.configuration = MODEL_STATE["tier1"][str(forecast_id)]
        self.changed = False

    def current_value(self) -> float:
        return float(self.configuration["current_value"])

    def condition_met(self) -> bool:
        value = self.current_value()
        threshold = float(self.configuration["threshold"])
        if self.configuration["yes_if_at_or_above"]:
            return value >= threshold
        return value <= threshold

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label(f"Tier 1 threshold — Forecast #{self.forecast_id}", classes="model-title")
            direction = "at or above" if self.configuration["yes_if_at_or_above"] else "at or below"
            yield Static(
                f"{escape(self.configuration['label'])}\n"
                f"Resolves YES if the reading is [bold]{direction} "
                f"{self.configuration['threshold']} {escape(self.configuration['unit'])}[/bold].\n"
                f"[dim]{escape(self.configuration['note'])}[/dim]",
                id="threshold-info",
            )
            with Horizontal(classes="input-row"):
                yield Label("Latest observed value:", classes="input-label")
                yield Input(
                    str(self.configuration["current_value"]),
                    placeholder="Observed value",
                    id="threshold-value",
                    select_on_focus=True,
                )
            yield Static("", id="threshold-error")
            yield Static("", id="threshold-result")
            yield Label(
                "Enter in the value field to record the implied YES/NO · Esc to close",
                classes="model-hint",
            )

    def on_mount(self) -> None:
        self.update_result()

    def update_result(self) -> None:
        met = self.condition_met()
        implied = 100.0 if met else 0.0
        verdict = "[bold green]YES[/bold green]" if met else "[bold red]NO[/bold red]"
        margin = self.current_value() - float(self.configuration["threshold"])
        self.query_one("#threshold-result", Static).update(
            f"Latest reading: [bold]{self.current_value()} {escape(self.configuration['unit'])}[/bold] · "
            f"Threshold: [bold]{self.configuration['threshold']} {escape(self.configuration['unit'])}[/bold] · "
            f"Margin: [bold]{margin:+.3f}[/bold]\n"
            f"Implied outcome on current data: {verdict}  →  YES probability [bold]{implied:.1f}%[/bold]"
        )

    @on(Input.Submitted, "#threshold-value")
    def record_value(self, event: Input.Submitted) -> None:
        error = self.query_one("#threshold-error", Static)
        try:
            value = float(event.value)
            if not math.isfinite(value):
                raise ValueError
        except ValueError:
            error.update("[red]Enter a finite numeric observation.[/red]")
            return
        error.update("")
        self.configuration["current_value"] = value
        self.update_result()
        set_forecast_probability(self.forecast_id, 100.0 if self.condition_met() else 0.0)
        persist_model_state()
        self.changed = True

    def action_close(self) -> None:
        self.dismiss(self.changed)


def _text_bar(fraction: float, width: int = 30) -> str:
    return "█" * max(0, min(width, round(fraction * width)))


class QuantModelScreen(ModalScreen[bool]):
    """Shared base for the read-only quantitative model views. Each subclass
    computes its module's report dict in __init__ (fast, deterministic seeds)
    and renders it; the authoritative probability is persisted by running the
    module with --persist (or deliberately via the p key on the list), never
    as a side effect of opening a view."""

    BINDINGS = [Binding("escape", "close", "Close"), Binding("q", "close", "Close")]

    def action_close(self) -> None:
        self.dismiss(False)


class PoissonModelScreen(QuantModelScreen):
    """Forecast #1: Poisson point process over audited BIS tightening episodes."""

    def __init__(self) -> None:
        super().__init__()
        self.report = export_controls_poisson_report()

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label("Quant model — Forecast #1 (Poisson point process)", classes="model-title")
            yield Static("", id="poisson-headline")
            yield PlotextPlot(id="poisson-chart", classes="quant-chart")
            yield Static("", id="poisson-fits")
            yield Static("", id="poisson-diagnostics")
            yield Label("Esc to close · python3 export_controls_poisson.py for the full report", classes="model-hint")

    def on_mount(self) -> None:
        report = self.report
        fit = report["fit_full"] if report["primary"] == "full" else report["fit_recent"]
        self.query_one("#poisson-headline", Static).update(
            f"P(≥1 tightening episode by {report['resolution_date']}) = 1 − exp(−λt) = "
            f"[bold]{report['primary_p_pct']:.1f}%[/bold] · λ = {fit.lambda_per_year:.2f} episodes/yr "
            f"({report['primary']} window) · t = {report['horizon_days']} days\n"
            f"[dim]Tier-3 reference-class cross-check: {report['reference_class_pct']:.1f}% · "
            f"persisted: {probability_text(report['persisted_pct'])}[/dim]"
        )
        self._plot_timeline()
        fits_lines = [
            f"{'Arrival unit / window':<30}{'events':>7}{'λ/yr':>8}{'P(≥1)':>9}",
            f"{'episodes, full 2022–':<30}{report['fit_full'].n_events:>7}"
            f"{report['fit_full'].lambda_per_year:>8.2f}{report['p_full_pct']:>8.1f}%"
            + ("  [bold cyan]← primary[/bold cyan]" if report["primary"] == "full" else ""),
            f"{'episodes, recent 24mo':<30}{report['fit_recent'].n_events:>7}"
            f"{report['fit_recent'].lambda_per_year:>8.2f}{report['p_recent_pct']:>8.1f}%"
            + ("  [bold cyan]← primary[/bold cyan]" if report["primary"] == "recent" else ""),
            f"{'per-rule, full (upper bound)':<30}{report['fit_full_rules'].n_events:>7}"
            f"{report['fit_full_rules'].lambda_per_year:>8.2f}{report['p_full_rules_pct']:>8.1f}%",
        ]
        self.query_one("#poisson-fits", Static).update("\n".join(fits_lines))
        stability = report["stability"]
        ks = report["ks"]
        verdict = (
            "[green]homogeneity NOT rejected → full-window rate primary[/green]"
            if stability.homogeneous
            else "[yellow]homogeneity REJECTED → recent-window rate primary[/yellow]"
        )
        self.query_one("#poisson-diagnostics", Static).update(
            f"Stability: split {stability.first_half_events} vs {stability.second_half_events} "
            f"episodes, exact binomial p = {stability.p_value:.3f} → {verdict}\n"
            f"GOF: KS D = {ks.d_statistic:.3f} over {ks.n_gaps} episode gaps, asymptotic "
            f"p ≈ {ks.p_value_asymptotic:.3f} (Lilliefors-type, conservative) · drought "
            f"{report['drought_days']}d since last episode "
            f"(P(gap this long) ≈ {report['drought_survival_pct']:.1f}%)\n"
            f"[dim]{escape(report['publication_date_caveat'])}[/dim]"
        )

    def _plot_timeline(self) -> None:
        """Cumulative tightening episodes vs the fitted constant-rate line —
        the visual argument that one homogeneous λ describes the cadence."""
        chart = self.query_one("#poisson-chart", PlotextPlot)
        plt = chart.plt
        plt.clear_figure()
        report = self.report
        from datetime import date as _date
        start = _date(2022, 1, 1)
        episodes = sorted({
            rule.publication_date for rule in report["timeline"] if rule.category == "tightening"
        })
        xs = [( _date.fromisoformat(d) - start).days / 365.2425 for d in episodes]
        ys = list(range(1, len(xs) + 1))
        plt.scatter(xs, ys, marker="dot", color="red")
        lam = report["fit_full"].lambda_per_year
        end_x = ( _date.fromisoformat(report["resolution_date"]) - start).days / 365.2425
        plt.plot([0, end_x], [0, lam * end_x], color="yellow")
        as_of_x = ( _date.fromisoformat(report["as_of_date"]) - start).days / 365.2425
        plt.vertical_line(as_of_x, color="cyan")
        plt.xticks([0, 1, 2, 3, 4, 5], ["2022", "2023", "2024", "2025", "2026", "2027"])
        plt.title("red dots = cumulative tightening episodes · yellow = fitted λt · cyan = as-of")
        chart.refresh()


class NuclearPathwaysScreen(QuantModelScreen):
    """Forecast #10: competing-risks model over three finalization pathways."""

    def __init__(self) -> None:
        super().__init__()
        self.report = nuclear_pathways_report()

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label("Quant model — Forecast #10 (competing risks)", classes="model-title")
            yield Static("", id="nuclear-headline")
            yield PlotextPlot(id="nuclear-chart", classes="quant-chart")
            yield Static("", id="nuclear-pathways")
            yield Static("", id="nuclear-notes")
            yield Label("Esc to close · python3 nuclear_competing_risks.py for the full report", classes="model-hint")

    def on_mount(self) -> None:
        report = self.report
        divergence = report["divergence_pts"]
        flag = (
            f"\n[yellow]Diverges {divergence:+.1f}pp from the persisted "
            f"{report['persisted_pct']}% — flagged, not auto-persisted (see methodology_notes.md #10).[/yellow]"
            if divergence is not None and abs(divergence) > 3 else ""
        )
        band = report["combined_band"]
        self.query_one("#nuclear-headline", Static).update(
            f"{escape(report['formula'])}\n"
            f"Combined P(≥1 pathway finalized by {report['resolution_date']}) = "
            f"[bold]{band['low_pct']:.0f}–{band['high_pct']:.0f}%[/bold] "
            f"(central [bold]{report['combined_pct']:.1f}%[/bold], persisted) · pure independence "
            f"would give {report['independence_pct']:.1f}%\n"
            f"[dim]The band is the gate sensitivity S = {band['gate_high']:.2f}/"
            f"{band['gate_central']:.2f}/{band['gate_low']:.2f}: the common-mode gate is a "
            "reasoned calibration, not a counted base rate, and with three semi-independent "
            "pathways it is essentially the entire answer (see methodology_notes.md #10).[/dim]"
            f"{flag}"
        )
        self._plot_curves()
        lines = [f"{'Pathway':<34}{'p_i | no sys':>13}   P(finalized by resolution)"]
        for pathway in report["pathways"]:
            p = pathway["p_by_resolution"]
            lines.append(
                f"{pathway['name'][:33]:<34}{p:>12.1%}   [{ADJUSTMENT_UP_COLOR}]{_text_bar(p)}[/]"
            )
        mc = report["monte_carlo"]
        lines.append(
            f"\nMonte Carlo ({mc['paths']:,} paths): P(YES) {mc['p_yes_pct']:.1f}% · "
            f"by Dec 2026 {mc['p_yes_by_2026_12_pct']:.1f}% · median first finalization "
            f"{mc['median_first_finalization']} · first-finalizer shares "
            + " / ".join(f"{k} {v:.0%}" for k, v in mc["first_finalizer_shares"].items())
        )
        self.query_one("#nuclear-pathways", Static).update("\n".join(lines))
        self.query_one("#nuclear-notes", Static).update(
            f"[bold]Common-mode gate[/bold]: {escape(report['p_systemic_rationale'])}\n"
            f"[dim]{escape(report['independence_note'])}[/dim]"
        )

    def _plot_curves(self) -> None:
        chart = self.query_one("#nuclear-chart", PlotextPlot)
        plt = chart.plt
        plt.clear_figure()
        report = self.report
        months = [month for month, _ in report["combined_curve"]]
        xs = list(range(len(months)))
        colors = {"part57": "red", "doe_sites": "green", "dow_rule": "magenta"}
        for pathway in report["pathways"]:
            plt.plot(xs, [p for _, p in pathway["curve"]], color=colors[pathway["key"]])
        plt.plot(xs, [p for _, p in report["combined_curve"]], color="yellow")
        tick_positions = xs[::3]
        plt.xticks(tick_positions, [months[i] for i in tick_positions])
        plt.title("cumulative P(finalized by month): yellow = combined · red = Part 57 · green = DOE sites · magenta = DOW rule")
        chart.refresh()


class SovereignJumpsScreen(QuantModelScreen):
    """Forecast #7: compound Poisson Monte Carlo over sovereign AI commitments."""

    def __init__(self) -> None:
        super().__init__()
        self.report = sovereign_ai_report()

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label("Quant model — Forecast #7 (compound Poisson Monte Carlo)", classes="model-title")
            yield Static("", id="sovereign-headline")
            yield PlotextPlot(id="sovereign-chart", classes="quant-chart")
            yield Static("", id="sovereign-variants")
            yield Static("", id="sovereign-notes")
            yield Label("Esc to close · python3 sovereign_ai_jumps.py for the full report", classes="model-hint")

    def on_mount(self) -> None:
        report = self.report
        rate = report["arrival_rate"]
        fit = report["jump_size_fit"]
        divergence = report["divergence_pts"]
        if divergence is None:
            divergence_tail = "[dim](no persisted probability on file to compare against)[/dim]"
        elif abs(divergence) > 3:
            divergence_tail = (
                f"vs persisted {report['persisted_probability_pct']}% "
                f"[yellow]— diverges {divergence:+.1f}pp; flagged, not auto-persisted "
                "(see methodology_notes.md #7)[/yellow]"
            )
        else:
            divergence_tail = (
                f"[dim]— persisted authoritative value ({report['persisted_probability_pct']}%; "
                "adopted, see methodology_notes.md #7)[/dim]"
            )
        regime = report["regime_diagnostics"]
        self.query_one("#sovereign-headline", Static).update(
            f"Base ${report['base_usd_billions']:.0f}B → ${report['threshold_usd_billions']:.0f}B in "
            f"{report['horizon_days']} days · λ = {rate['lambda_per_year']:.2f} commitments/yr "
            f"({rate['n_commitments']} arrivals over {rate['window_years']:.2f}y) · jump sizes "
            f"lognormal(μ={fit['mu']:.2f}, σ={fit['sigma']:.2f}), median ${fit['implied_median_usd_billions']:.1f}B\n"
            f"Headline (regime-switching): [bold]{report['headline_probability_pct']:.2f}%[/bold] "
            f"{divergence_tail}\n"
            f"[dim]P(burst regime active) {regime['p_shift_active_pct']:.1f}% (1 observed "
            f"Stargate-class trigger, {regime['response_latency_days']}d latency) × "
            f"P(cross | burst) {regime['p_cross_given_shift_pct']:.1f}% (burst "
            f"{regime['regime_b_rate_per_year']:.0f}/yr, sizes ×U{regime['regime_b_size_multiplier']})[/dim]"
        )
        self._plot_histogram()
        lines = [f"{'Variant':<28}{'P(≥ $250B)':>12}{'mean total':>12}{'p95':>9}{'p99':>9}"]
        for variant in report["variants"]:
            pct = variant["percentiles_usd_billions"]
            lines.append(
                f"{variant['label'][:27]:<28}{variant['p_cross_pct']:>11.2f}%"
                f"{variant['mean_total_usd_billions']:>11.1f}B{pct['p95']:>8.0f}B{pct['p99']:>8.0f}B"
            )
        self.query_one("#sovereign-variants", Static).update("\n".join(lines))
        self.query_one("#sovereign-notes", Static).update(
            f"[dim]{escape(report['divergence_note'])}[/dim]"
        )

    def _plot_histogram(self) -> None:
        chart = self.query_one("#sovereign-chart", PlotextPlot)
        plt = chart.plt
        plt.clear_figure()
        stationary = self.report["variants"][0]
        labels = [label for label, _ in stationary["histogram"]]
        values = [fraction * 100 for _, fraction in stationary["histogram"]]
        plt.bar(labels, values, color="cyan")
        plt.title("Stationary variant: simulated year-end totals ($B); YES region = the ≥250 bars")
        chart.refresh()


class ElectricitySimulationScreen(QuantModelScreen):
    """Forecast #9: deterministic base-rate schedule + OU gas simulation."""

    def __init__(self) -> None:
        super().__init__()
        self.report = electricity_report()

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label("Quant model — Forecast #9 (deterministic + OU simulation)", classes="model-title")
            yield Static("", id="electricity-headline")
            yield PlotextPlot(id="electricity-chart", classes="quant-chart")
            yield Static("", id="electricity-components")
            yield Static("", id="electricity-distribution")
            yield Label("Esc to close · python3 electricity_simulation.py for the full report", classes="model-hint")

    def on_mount(self) -> None:
        report = self.report
        ou = report["ou_fit"]
        ou_text = (
            f"OU fit (3y daily HH): κ={ou.kappa_per_year:.1f}/yr, σ={ou.sigma_annualized:.2f} ann."
            if ou is not None else "[red]OU cache missing — literature fallback[/red]"
        )
        divergence = report["divergence_pts"]
        if divergence is None:
            divergence_tail = "[dim](no persisted probability on file to compare against)[/dim]"
        elif abs(divergence) > 3:
            divergence_tail = (
                f"vs persisted {report['persisted_pct']}% "
                f"[yellow]— diverges {divergence:+.1f}pp; flagged, not auto-persisted "
                "(see methodology_notes.md #9)[/yellow]"
            )
        else:
            divergence_tail = (
                f"[dim]— persisted authoritative value ({report['persisted_pct']}%; "
                "adopted, see methodology_notes.md #9)[/dim]"
            )
        self.query_one("#electricity-headline", Static).update(
            f"P(Jan 2027 commercial rate < {report['baseline_cents']} ¢/kWh) = "
            f"[bold]{report['p_below_baseline_pct']:.1f}%[/bold] {divergence_tail}\n"
            f"[dim]{ou_text} · STEO anchor {report['steo_anchor']} · in-window gas pass-through = "
            f"{report['in_window_pass_through']:.0f} (fuel factor locked 2026-07-01 → 2027-06-30)[/dim]"
        )
        self._plot_gas_paths()
        component_notes = {
            "base_step": "locked 2027-01-01 biennial step ($209.9M)",
            "securitization": "PUR-2026-00078 decision risk (one-sided up)",
            "winter_spike": "861M cold-event Januaries",
            "gs5_noise": "GS-5 class composition change (zero-mean)",
            "idiosyncratic": "6-month series noise",
            "fuel_in_window": "OU gas × fuel share × pass-through 0",
        }
        lines = [f"{'Component (mean ¢/kWh at Jan 2027)':<40}{'mean':>8}"]
        for key, value in report["component_means_cents"].items():
            colour = ADJUSTMENT_DOWN_COLOR if value > 0.001 else "dim"
            lines.append(f"[{colour}]{component_notes[key][:39]:<40}{value:>+8.3f}[/]")
        counterfactual = report["counterfactual_fuel_delta_cents"]
        lines.append(
            f"[dim]Counterfactual live-pass-through fuel delta p10/p50/p90: "
            f"{counterfactual['p10']:+.2f} / {counterfactual['p50']:+.2f} / "
            f"{counterfactual['p90']:+.2f} ¢ — two-sided, not one-way easing[/dim]"
        )
        self.query_one("#electricity-components", Static).update("\n".join(lines))
        histogram_lines = []
        for label, fraction, yes_side in report["rate_histogram"]:
            marker = " ← YES side" if yes_side else ""
            histogram_lines.append(f"{label:>13} {fraction * 100:5.1f}% {_text_bar(fraction, 40)}{marker}")
        empirical = report["empirical_jan_below_jul"]
        histogram_lines.append(
            f"\nEmpirical cross-check: Jan below prior Jul in {empirical[0]}/{empirical[1]} years "
            f"({report['empirical_jan_below_jul_pct']:.0f}%) — the unconditional base the tier-3 35% matched; "
            "the model conditions on the locked Jan-2027 step and the closed fuel channel."
        )
        self.query_one("#electricity-distribution", Static).update("\n".join(histogram_lines))

    def _plot_gas_paths(self) -> None:
        chart = self.query_one("#electricity-chart", PlotextPlot)
        plt = chart.plt
        plt.clear_figure()
        report = self.report
        months = list(report["simulation_months"])
        xs = list(range(len(months)))
        for path in report["sample_gas_paths"]:
            plt.plot(xs, path, color="cyan")
        anchors = [report["steo_anchor"][q] for q in ("2026Q3", "2026Q3", "2026Q4", "2026Q4", "2026Q4", "2027Q1")]
        plt.plot(xs, anchors, color="yellow")
        plt.xticks(xs, months)
        plt.title("cyan = simulated Henry Hub paths ($/MMBtu) · yellow = STEO anchor — pass-through to the Jan 2027 rate is ZERO (locked fuel factor)")
        chart.refresh()


class DatacenterBacklogScreen(QuantModelScreen):
    """Forecast #3: announced-vs-under-construction backlog throughput model."""

    def __init__(self) -> None:
        super().__init__()
        self.report = datacenter_backlog_report()

    def compose(self) -> ComposeResult:
        with Container(id="model-panel"):
            yield Label("Quant model — Forecast #3 (backlog / throughput)", classes="model-title")
            yield Static("", id="backlog-headline")
            yield PlotextPlot(id="backlog-chart", classes="quant-chart")
            yield Static("", id="backlog-parameters")
            yield Static("", id="backlog-notes")
            yield Label("Esc to close · python3 datacenter_backlog.py for the full report", classes="model-hint")

    def on_mount(self) -> None:
        report = self.report
        anchor = report["anchor"]
        tail = report["tail_risk"]
        self.query_one("#backlog-headline", Static).update(
            f"Anchor {anchor['date']}: {anchor['announced_gw']:.1f} GW announced / "
            f"{anchor['under_construction_gw']:.1f} GW under construction (gap {anchor['gap_pct']:.1f}%) · "
            f"resolution: gap < 30% by 2027-12-31\n"
            f"P(YES) = flow {report['p_below_30_pct']:.1f}% + capex-pullback "
            f"{tail['p_pullback_yes'] * 100:.1f}% (from #4's posterior × ASSUMED shares) + "
            f"tracker-shift {tail['p_tracker_yes'] * 100:.1f}% (ASSUMED) = "
            f"[bold]{report['combined_p_yes_pct']:.1f}%[/bold] · deterministic midpoint "
            f"end-2027 gap [bold]{report['midpoint_end_2027_gap_pct']:.1f}%[/bold] · "
            f"persisted {report['persisted_pct']}%"
        )
        self._plot_trajectory()
        inflow = report["inflow_gw_per_quarter"]
        conversion = report["conversion_gw_per_quarter"]
        constraints = report["conversion_cap_constraints"]
        self.query_one("#backlog-parameters", Static).update(
            f"Inflow {inflow['low']}–{inflow['high']} GW/q (mode {inflow['mode']}) · conversion "
            f"{conversion['low']}–{conversion['high']} GW/q (mode {conversion['mode']}), capped at remaining backlog\n"
            f"[dim]Cap held by: {escape(constraints['interconnection'])}; "
            f"{escape(constraints['transformers'])}; {escape(constraints['gas_turbines'])}; "
            f"{escape(constraints['labor'])}[/dim]"
        )
        stress = report["stress_case"]
        self.query_one("#backlog-notes", Static).update(
            f"Best researched flow corner ends 2027 at {report['best_flow_corner_end_2027_gap_pct']:.1f}% — "
            "still above 30%, so the Monte Carlo zero is structural.\n"
            f"[bold]Stress case[/bold] ({escape(stress['label'])}): cancellations "
            f"{stress['cancellation_gw_per_quarter']:.0f} GW/q → gap first below 30% in "
            f"{stress['first_month_below_30']}, end-2027 gap {stress['end_2027_gap_pct']:.1f}%."
        )

    def _plot_trajectory(self) -> None:
        chart = self.query_one("#backlog-chart", PlotextPlot)
        plt = chart.plt
        plt.clear_figure()
        trajectory = self.report["trajectory"]
        months = [point["month"] for point in trajectory]
        xs = list(range(len(months)))
        plt.plot(xs, [point["mc_gap_p10_pct"] for point in trajectory], color="green")
        plt.plot(xs, [point["mc_gap_median_pct"] for point in trajectory], color="yellow")
        plt.plot(xs, [point["mc_gap_p90_pct"] for point in trajectory], color="magenta")
        plt.plot(xs, [point["stress_gap_pct"] for point in trajectory], color="cyan")
        plt.horizontal_line(30.0, color="red")
        tick_positions = xs[::3]
        plt.xticks(tick_positions, [months[i] for i in tick_positions])
        plt.title("gap %: yellow = median · green/magenta = p10/p90 · cyan = capex-pullback stress · red = 30% bar")
        chart.refresh()


QUANT_SCREEN_BUILDERS = {
    1: PoissonModelScreen,
    3: DatacenterBacklogScreen,
    7: SovereignJumpsScreen,
    9: ElectricitySimulationScreen,
    10: NuclearPathwaysScreen,
}

QUANT_VIEW_LABELS = {
    1: "1 · Poisson process",
    3: "1 · Backlog model",
    7: "1 · Compound Poisson MC",
    9: "1 · OU rate simulation",
    10: "1 · Competing risks",
}


def build_model_screen(forecast_id: int, tier: int) -> ModalScreen[bool] | None:
    """Construct the model view for one (forecast, tier) pair.

    (#6 was previously special-cased to a tier-2 trend view; it is now a tier-3
    reference-class forecast and routes through the tier == 3 branch.)
    """
    if tier == 1:
        # Per-forecast tier-1 quantitative models: #5's HMM plus the process
        # models added in the quantitative upgrade (QUANT_SCREEN_BUILDERS).
        # Anything else routed to tier 1 falls back to the threshold check.
        if forecast_id == 5:
            return Tier1ModelScreen()
        if forecast_id in QUANT_SCREEN_BUILDERS:
            return QUANT_SCREEN_BUILDERS[forecast_id]()
        return Tier1ThresholdScreen(forecast_id)
    if tier == 2:
        return Tier2ModelScreen(forecast_id)
    if tier == 3:
        return Tier3ModelScreen(forecast_id)
    return None


def model_view_label(forecast_id: int, tier: int) -> str:
    """Short, number-first label for a tier's model view (shown in the picker)."""
    if tier == 1:
        if forecast_id == 5:
            return "1 · HMM Monte Carlo"
        return QUANT_VIEW_LABELS.get(forecast_id, "1 · Threshold check")
    if tier == 2:
        return "2 · Trend model"
    if tier == 3:
        return "3 · Reference-class estimate"
    return str(tier)


def available_model_views(forecast_id: int) -> list[tuple[int, str]]:
    """The (tier, label) model views a forecast exposes, in tier order. Every tier
    in {1, 2, 3} has a builder, so this mirrors the forecast's ``tiers`` list."""
    return [(tier, model_view_label(forecast_id, tier)) for tier in get(forecast_id).tiers]


class TierViewPickerScreen(ModalScreen[int | None]):
    """For multi-tier forecasts, let the user choose which tier's model view to
    open instead of silently defaulting to one. Returns the chosen tier number."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("1", "pick('1')", "Tier 1", show=False),
        Binding("2", "pick('2')", "Tier 2", show=False),
        Binding("3", "pick('3')", "Tier 3", show=False),
    ]

    def __init__(self, forecast_id: int, views: list[tuple[int, str]]) -> None:
        super().__init__()
        self.forecast_id = forecast_id
        self.views = views

    def compose(self) -> ComposeResult:
        forecast = get(self.forecast_id)
        with Vertical(id="tier-picker-dialog"):
            yield Label(
                f"Forecast #{forecast.id} — {format_model_type(forecast)} "
                f"({len(self.views)} model views)",
                id="tier-picker-title",
            )
            yield Label("Choose a model view to open:", id="tier-picker-subtitle")
            for tier, label in self.views:
                yield Button(label, id=f"tier-view-{tier}")
            yield Label("Number key or click · Esc to cancel", classes="model-hint")

    def on_mount(self) -> None:
        buttons = self.query(Button)
        if buttons:
            buttons.first().focus()

    def action_pick(self, tier_str: str) -> None:
        tier = int(tier_str)
        if any(available_tier == tier for available_tier, _ in self.views):
            self.dismiss(tier)

    @on(Button.Pressed)
    def button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        self.dismiss(int(event.button.id.removeprefix("tier-view-")))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ForecastApp(App[None]):
    TITLE = "Bridgewater Forecasting the Future"
    SUB_TITLE = "Forecast model"
    BINDINGS = [
        Binding("p", "edit_probability", "Set probability"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = """
    Screen { background: $background; }
    #model-summary { height: auto; padding: 0 1; color: $text-muted; }
    #forecast-table { height: 1fr; margin: 1; border: round $accent; }

    ForecastDetailScreen { align: right middle; background: rgba(0, 0, 0, 0.48); }
    #detail-panel { width: 62%; min-width: 52; height: 92%; padding: 1 2; background: $panel; border-left: tall $accent; }
    #detail-title { width: 100%; height: 3; content-align: center middle; text-style: bold; color: $foreground; }
    #detail-body { height: 1fr; overflow-y: auto; padding: 1; }
    #detail-hint, #probability-hint { height: 1; text-align: center; color: $text-muted; }

    TierViewPickerScreen { align: center middle; background: rgba(0, 0, 0, 0.55); }
    #tier-picker-dialog { width: 56; height: auto; padding: 1 2; background: $panel; border: round $accent; }
    #tier-picker-title { height: 2; content-align: center middle; text-style: bold; color: $foreground; }
    #tier-picker-subtitle { height: 1; text-align: center; color: $text-muted; margin-bottom: 1; }
    #tier-picker-dialog Button { width: 100%; margin-bottom: 1; }

    ProbabilityEditScreen, FactorEditScreen { align: center middle; background: rgba(0, 0, 0, 0.55); }
    #probability-dialog, #factor-dialog { width: 62; height: auto; padding: 1 2; background: $panel; border: round $accent; }
    #probability-title { height: 2; content-align: center middle; text-style: bold; color: $foreground; }
    #probability-forecast-title { height: auto; margin-bottom: 1; text-align: center; }
    #probability-input { width: 100%; }
    #probability-error, #factor-error, #model-error, #trend-error, #tier3-base-error, #threshold-error { height: auto; min-height: 2; margin-top: 1; text-align: center; }

    Tier1ModelScreen, Tier1ThresholdScreen, Tier2ModelScreen, Tier3ModelScreen { align: center middle; background: rgba(0, 0, 0, 0.62); }
    #model-panel { width: 94%; height: 94%; padding: 1 2; background: $panel; border: round $accent; overflow-y: auto; }
    .model-title { height: 2; content-align: center middle; text-style: bold; color: $foreground; }
    .model-hint { height: 1; text-align: center; color: $text-muted; margin-top: 1; }
    .section-label { height: 1; text-style: bold; color: $foreground; margin-top: 1; }
    .input-row { height: 3; align: center middle; }
    .input-label { width: auto; height: 3; content-align: left middle; margin-right: 1; }
    .input-row Input { width: 1fr; }
    .button-row { height: 3; align: center middle; }
    .button-row Button { margin: 0 1; }

    #current-state, #fedwatch-crosscheck, #final-probability, #trend-statistics, #trend-nowcast, #sep-crosscheck, #threshold-info, #threshold-result, #judgment-note { height: auto; padding: 1; }
    #state-diagram, #waterfall, #bayes-panel { height: auto; width: auto; padding: 1; }
    #outcome-table { height: 6; }
    #outcome-histogram { height: 5; padding: 0 1; }
    #trend-chart { height: 18; margin: 1 0; }
    .quant-chart { height: 16; margin: 1 0; }
    #poisson-headline, #poisson-fits, #poisson-diagnostics, #nuclear-headline, #nuclear-pathways, #nuclear-notes, #sovereign-headline, #sovereign-variants, #sovereign-notes, #electricity-headline, #electricity-components, #electricity-distribution, #backlog-headline, #backlog-parameters, #backlog-notes { height: auto; padding: 0 1; }
    #trend-points { height: 9; }
    #adjustment-table { height: 1fr; min-height: 8; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("↑/↓ navigate · Enter view detail · p set probability · q quit", id="model-summary")
        yield DataTable(id="forecast-table", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(BRIDGEWATER_THEME)
        self.theme = "bridgewater-blackred"
        table = self.query_one("#forecast-table", DataTable)
        table.cursor_type = "row"
        table.add_column("#", key="id", width=4)
        table.add_column("Title", key="title")
        table.add_column("Model type", key="model_type", width=11)
        table.add_column("Resolves", key="resolution_date", width=12)
        table.add_column("Probability", key="probability", width=13)
        for forecast in FORECASTS:
            table.add_row(
                str(forecast.id), forecast.title, format_model_type(forecast),
                forecast.resolution_date, probability_text(forecast.probability), key=str(forecast.id),
            )
        table.focus()

    def selected_forecast_id(self) -> int | None:
        table = self.query_one("#forecast-table", DataTable)
        if not FORECASTS or not 0 <= table.cursor_row < len(FORECASTS):
            return None
        return FORECASTS[table.cursor_row].id

    @on(DataTable.RowSelected, "#forecast-table")
    def show_forecast_detail(self, event: DataTable.RowSelected) -> None:
        self.push_screen(ForecastDetailScreen(FORECASTS[event.cursor_row].id))

    def action_edit_probability(self) -> None:
        forecast_id = self.selected_forecast_id()
        if forecast_id is None:
            self.notify("Select a forecast first", severity="warning")
            return
        self.push_screen(
            ProbabilityEditScreen(forecast_id),
            callback=lambda changed: self.refresh_probability(forecast_id) if changed else None,
        )

    def refresh_probability(self, forecast_id: int) -> None:
        table = self.query_one("#forecast-table", DataTable)
        table.update_cell(
            str(forecast_id), "probability", probability_text(get(forecast_id).probability), update_width=False,
        )


def main() -> None:
    ForecastApp().run()


if __name__ == "__main__":
    main()
