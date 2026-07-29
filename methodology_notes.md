# Methodology notes

Per-forecast notes on modeling choices, data limitations, and how to read the
numbers. These are qualitative caveats meant to travel with the quantitative
outputs in `forecast_state.json`.

## Forecast #1 — Does the US tighten export controls on next-gen AI chips to China?

**Authoritative probability: 87.1% (YES = BIS tightens China advanced-chip
restrictions at some point in the window; NO = relaxed/unchanged), from the
Poisson point-process model described in the quantitative-upgrade subsection
below (`export_controls_poisson.py`).** The tier 3 reference-class /
base-rate-plus-adjustments estimate documented next (90%) is retained as the
judgment cross-check — the two agree within three points. The earlier 55%
placeholder base rate (and the 60% it produced) is retired.

### Base rate: 93% — from a full audit, not a guess

Reference class: *"China advanced-computing/semiconductor export control actions,
2022-2026, Federal Register."* The base rate is the **tightening share of
substantive actions** in a hand-audit of the cached BIS docket
(`federal_register_bis_export_controls.json`), restricted to the China
advanced-chip subset:

- **35 rules** in the China subset: **26 tightening / 2 loosening / 7 noise**.
- **Base rate = 26 / (26 + 2) = 93%** (noise excluded from the denominator by
  design).
- The **2 loosening actions are routine entity de-listings after review**
  (removals of a single entity/aliases once bona fides were re-established), **not
  a relaxation of chip controls**. There is no substantive loosening of China
  advanced-chip *policy* anywhere in the window.
- **Robust to the inclusion definition** (the one real judgment call is how to
  treat multi-country Entity List rules where China is the majority): core
  chip-tech rules only = 9/0 = **100%**; core + China-only entity additions =
  16/2 = **89%**; full China-majority set = 26/2 = **93%**. The band is **89-100%**.
- **Not clustered:** the yearly tightening share is 100% (2022), 89% (2023), 100%
  (2024), 91% (2025); 2026 is a partial year whose only China-subset action is
  administrative noise. The full-docket 2026 "loosening wobble" (UAE #135,
  Cambodia #133) falls **outside** this reference class entirely — neither is a
  China chip action.

This replaces the broader whole-docket rate (82% over all 136 BIS rules), which
was diluted by Russia/Belarus sanctions and is the wrong reference class for a
China-chip question.

### Adjustment factors (sized conservatively — the base rate is near the ceiling)

- **+2pp — Bipartisan political momentum.** The mercantilist/tech-restriction
  posture toward China has bipartisan support and has continued across
  administrations. Only a small nudge: with the base rate already near the
  ceiling, there is little headroom for an upward move.
- **−3pp — Diminishing room to tighten further.** After four years of
  near-continuous tightening, controls are already extensive and fewer high-value
  targets may remain to add before the Dec 2026 resolution; a rate near 100% has
  mild mean-reversion room and cannot rise. Small, and it does not threaten a YES
  on its own — YES needs only one tightening action, which the cadence still
  easily supplies.
- **−2pp — 2025 H20 licensing reversal / transactional posture.** In 2025 the
  administration reversed an earlier restriction and authorized resumption of
  Nvidia H20 (and AMD) advanced-AI-chip sales to China under a licensing
  arrangement — a concrete, item-specific relaxation that is **not** in the
  audited rule set (it is a licensing-policy action, not an Entity List/EAR rule),
  so it adds genuinely new downside information rather than double-counting the
  base rate. It signals willingness to relax specific China-chip controls for
  leverage/revenue, nudging toward the "relax/unchanged" pole. Kept small: it is a
  per-item carve-out, not a repeal of the Entity List or the broad
  advanced-computing controls, and the resolution bar (any tightening action in
  the window) remains easily met.

**Net: 93 + 2 − 3 − 2 = 90%.** A small net markdown from the base rate that
acknowledges the near-ceiling and two genuine countervailing signals, while
staying consistent with an audited posture that has tightened every year without
pause.

### Quantitative upgrade — Poisson point process, now the primary method (2026-07-22)

**Authoritative probability: 87.1%**, from a homogeneous Poisson point-process
model (`export_controls_poisson.py`, runnable standalone) fit to the audited
tightening history; the reference-class estimate above (90%) is retained as the
documented judgment cross-check, the same primary/cross-check pattern #5 uses
for its HMM vs FedWatch.

The resolution criterion is an *arrival* question — does at least one
tightening action land in the remaining 162 days — so the right tool is a point
process, not a share-of-actions rate. The model:

- **Events**: the same 26 audited tightening rules (the full 35-rule audited
  subset is embedded in the module with per-rule provenance). BIS ships
  same-day rule packages (five zero-day inter-arrival gaps), and P(≥1 rule) =
  P(≥1 publication *episode*), so the resolution-relevant arrival unit is the
  **episode** (unique publication day, n=21); the per-rule fit is reported as
  an explicit upper bound.
- **Fit**: episode MLE λ = 21 / 4.553 yr = **4.61 episodes/yr** (full window
  2022-01-01 → 2026-07-22); trailing-24-month rate 4.50/yr — nearly identical.
- **Rate stability**: exact conditional binomial split test at the window
  midpoint: 11 vs 10 episodes, p = 1.00 — homogeneity is *not* rejected, so
  the full-window rate is primary (the decision rule is coded, not asserted).
- **Goodness of fit**: KS of episode inter-arrivals vs Exponential(λ):
  D = 0.209 over 20 gaps, asymptotic p ≈ 0.35 (Lilliefors-type caveat: λ is
  estimated from the same data, so the p-value is approximate). The per-rule
  process fits worse (D = 0.237, p ≈ 0.12, driven by the package ties) — which
  is exactly why episodes carry the headline.
- **Result**: P(≥1 episode in 162 days) = 1 − exp(−4.61 × 0.4435) = **87.1%**
  (per-rule upper bound: 92.1%). A 10,000-path Monte Carlo cross-check
  reproduces the closed form.
- **Drought diagnostic**: 286 days have passed since the last tightening
  episode (2025-10-09); under the fitted rate a gap this long has probability
  ≈ 2.7%. This is a selection-biased statistic (we test it because it is
  long), reported as context for the 2025 H20/transactional-posture slowdown
  story rather than fed into the decision rule — the formal tests do not
  reject homogeneity.

**Comparison**: 87.1% (Poisson) vs 90% (reference class), a −2.9pp difference.
The two methods price different things — a tightening *share* with judgment
adjustments vs an arrival *rate* against a dated window — and their agreement
within three points is mutual corroboration. The Poisson number is persisted as
authoritative because it prices the actual resolution event (an arrival before
a date) with a fitted, testable process.

## Forecast #2 — Will Project Vault's committed capacity expand beyond $12B by year-end 2026?

**Authoritative probability: 61% (YES = Project Vault's committed capacity is
formally expanded beyond its initial $12B — $10B EXIM loan + $2B private — by
Dec 31, 2026), from a tier 3 reference-class / base-rate-plus-adjustments
estimate.** This is a **reframe**: the forecast moved from the vague "does the US
establish/expand a critical-mineral strategic reserve?" (resolution 2027-12-31,
50% placeholder) to a specific, near-term, Vault-only question (resolution moved
up to **2026-12-31**). Ecosystem activity — separate EXIM LOIs, FORGE, bilateral
frameworks — does **not** count unless folded into Vault's committed capacity.

### Base rate: 60% — a reasoned structural prior, stated as such

Reference class: *"first-year federal loan-based industrial-policy financing
vehicles expanding committed capacity within their first calendar year of
operation."* There is **no clean tabulated frequency** for this — it is a sparse,
heterogeneous class (DOE LPO/ATVM, DPA Title III, CHIPS, EXIM facilities all
differ in structure) — so 60% is a **structural prior, not a counted rate**,
anchored on the program's own design:

- **Demand-driven structure (primary):** committed capacity scales with OEM
  purchase commitments rather than sitting under a fixed cap, so *expansion is the
  program's default growth mechanism, not an exceptional event* — a prior above
  50% on its own.
- **Three independent YES-paths,** two of which (EXIM Board additional
  authorization; new private co-investment) do not require Congress.
- **Held at 60%, not higher, by first-calendar-year timing risk:** only ~11 months
  (Feb 2 → Dec 31, 2026) for a *formal* expansion action to actually complete, and
  new programs often spend year one standing up the initial commitment.

### Adjustment factors

- **+9pp — Administration's stated expansion intent.** State Dept on the record:
  "this is only the beginning… dozens of additional projects in the pipeline… with
  more coming online soon." Corroborated by EXIM's demonstrated adjacent pace
  ($14.8B in separate critical-minerals LOIs over the past year). The $14.8B is
  folded in here as **supporting momentum evidence** — not a separate factor and
  not the base rate — because it is related activity, not literally Vault's
  committed capacity.
- **−8pp — Political/budget risk and first-year execution timing.** The
  Congressional-appropriation path is slow and uncertain; formal EXIM Board or
  private-capital actions can slip past Dec 31; general budget/political friction
  applies. The only identified counterfactor, sized to roughly offset the bullish
  intent.

**Net: 60 + 9 − 8 = 61%.** The two adjustments nearly cancel by design — the
specific, on-record push modestly outweighs generic political/budget risk, but
real first-year timing constraints keep the estimate anchored near the structural
base rate.

### Deliberately judgment-anchored — no quantitative model, and why (2026-07-22)

When the other forecasts were upgraded to explicit quantitative models (Poisson
process for #1, competing risks for #10, compound Poisson for #7, OU simulation
for #9, backlog model for #3, Bayesian recombination for #4/#6), **#2 was
deliberately left as a judgment-anchored reference-class estimate.** This is a
methodological choice, not a gap: Project Vault is a **single, five-month-old,
first-of-its-kind program**, and the question is a **single unprecedented
institutional event** (a formal capacity expansion in its first calendar year).
There is no event history to fit a rate to, no market pricing it, no ensemble of
comparable programs dense enough to define a frequency — the reference class
itself is explicitly "sparse and heterogeneous" (see base-rate source above).
Fitting a stochastic process to a class of one would manufacture parameters out
of assumptions and dress a judgment call in false rigor. The honest quantitative
form for this evidence is exactly what the tier 3 estimate already is: a stated
structural prior plus named, sized, arguable adjustments.

## Forecast #3 — Does the US 2027 data-center capacity shortfall close to <30%?

**Authoritative probability: 5.5% (YES = independent tracking shows the 2027
not-yet-under-construction gap below 30%; NO if the flagged 60%+ persists/widens),
from the backlog/throughput model plus explicit modeled tail-risk channels
(`datacenter_backlog.py`) — adopted 2026-07-23, replacing the earlier 4%
qualitative floor with a fully modeled quantity (see the tail-risk subsection
below).** The section below documents the qualitative reasoning that preceded the
model; it remains the narrative backbone but is no longer the persisted number's
source. Originally reframed from a tier-2 trend fit (same move as #4 and #6)
because the real data cannot support a trustworthy fit.

### The real data (replacing the placeholder 68→65→63→61)

| Date | Gap | Metric | Tracker |
|---|---|---|---|
| Feb 2026 | 68.75% | 2026 pipeline (5GW u/c of 16GW) | Sightline |
| Apr 2026 | ~68% | 2026 pipeline (~⅓ broken ground; 67–69%) | Sightline |
| Apr 2026 | 70.7% | **2027-specific** (6.3GW u/c of 21.5GW) | Sightline/Bloomberg |
| Jun 2026 | ~80% | **2027-specific** | Jefferies |

The old placeholder had the gap *closing* toward 30%; the real data has it
**stable-to-widening in the 68–80% range** — the opposite direction.

### Why the trend fit was abandoned (the perverse small-n result)

The **resolution metric (2027-specific) has only n=2** — below the fit machinery's
3-point floor — and its two points come from **different trackers** (Sightline
70.7% vs Jefferies 80%), so the "widening" from 70.7→80 is confounded with a
methodology switch. Forcing a combined **4-point** fit (both metrics, disclosed):
slope +3.6pp/step (widening), R²=0.72, but **slope t = 2.27 on 2 dof — not
significant** (crit. ≈4.30), and walk-forward RMSE ≈ 8.9. The projected 2027 gap is
**88–99%** (racing *away* from the 30% target), yet the Student-t P(YES <30%) came
out **9–13% and *rising* with the horizon** — a pure artifact of fat-tailed n=4 /
2-dof prediction bands smearing mass across the whole range. That precise-looking
number is misleading and is **rejected**. The real series is archived in
`tui.py` (`tier2["3"]`, commented) and above.

### Base rate / reasoning: 4% (qualitative)

n is far too small (2 points for the resolution metric; 4 mixed-source/mixed-metric
points combined) for any formal significance test, so the estimate leans on
**direction**: the gap is **68–80% and stable-to-widening, against a 30% target.**
A YES requires the gap to roughly **halve (~45pp, ~75%→<30%) within ~18 months while
it is currently widening** — a massive trend break with no supporting evidence. The
only non-fanciful path is a large downward revision of the *planned* pipeline (an
AI-capex pullback shrinking the denominator). No named adjustments are applied: the
qualitative direction is the whole estimate. **Net: 4%** — a strong NO, matching the
resolution criterion's "NO if the flagged 60%+ persists/widens."

### Quantitative upgrade — backlog/throughput model, corroborating the 4% (2026-07-22)

A queueing/backlog model (`datacenter_backlog.py`, runnable standalone) replaces
the abandoned trend fit with the tool that actually matches the physics: the
announced-2027 pipeline grows by a stochastic **inflow** (2–6 GW/quarter,
triangular; new-cohort announcements plus 2026-cohort slippage — CTVC/Sightline,
Network World), the under-construction stock grows by a **throughput-constrained
conversion flow** (1–3 GW/quarter, triangular; Sightline tracker-of-record net
starts vs the BNEF cross-tracker upper bound), capped at the remaining backlog and
held non-accelerating through 2027 by cited physical constraints (LBNL *Queued Up
2026*: >5-year median interconnection request-to-operation; transformer lead
times ~128–160 weeks; gas turbines largely sold out through 2029; up to ~499k
construction-worker shortfall). Anchor: Apr 2026, 25.0 GW announced / 6.3 GW
under construction (gap 74.8%; published readings bracket 70.7–80%).

Results (10,000 paths over parameter uncertainty): **P(gap < 30% by 2027-12-31)
= 0.0% — structural, not sampling**: even the most YES-favorable corner of the
researched flow box (slowest inflow, fastest conversion, held for all 20 months)
ends 2027 at a 31.4% gap. The deterministic midpoint projection ends 2027 at
**62.0%** (p10–p90 band 52.7–70.1%) — the gap narrows, but nowhere near halving.
A labeled stress case models the one non-fanciful YES path (AI-capex pullback:
cancellations at 12 GW/q shrinking the denominator) and resolves YES within ~4
months — confirming that channel, not construction pace, is where any YES lives.

**Comparison**: flow model 0.0% vs the old persisted 4.0%. The model
*corroborates* the strong NO; the residual YES probability lives in two non-flow
channels, which as of 2026-07-23 are no longer an unmodeled judgment floor:

### Explicit tail-risk channels — the 4% floor replaced by modeled terms (2026-07-23)

The two non-flow YES channels are now discrete-scenario terms with named,
inspectable components (`tail_risk_terms()` in the module):

- **Capex-pullback denominator collapse: 2.6%.** P(AI capex disappoints) is not
  assumed — it is pulled live from **forecast #4's own Bayesian posterior**
  (P(#4 NO) = 1 − 56.5% = 43.5%), times an ASSUMED 0.12 share of disappointment
  scenarios that take the form of *large cancellations of already-announced
  2027-cohort capacity* (rather than slower new announcements, which the flow
  model's inflow range already spans; announced-project cancellations
  historically required financing stress — 2001 telecom, 2022 crypto-DC — not
  mere growth slowdown), times an ASSUMED 0.5 conditional P(gap < 30% |
  cancellations), bracketed by the stress case (a full-scale pullback resolves
  YES within ~4 months) and partial-pullback paths that stall above the bar.
- **Tracker/methodology shift: 3.0%.** SemiAnalysis publicly argues Sightline's
  under-construction numerator undercounts by multiples, and resolution accepts
  DC Byte/CBRE/JLL. ASSUMED 0.10 P(the resolution-relevant tracker's counting
  shifts materially by end-2027) × ASSUMED 0.3 P(reported gap < 30% | shift) —
  even a 2–3× numerator restatement of the Apr 2026 anchor lands at ~25–50%,
  straddling the bar.

**Combined (independence across channels, documented): 1 − (1−0.000)(1−0.026)(1−0.030)
= 5.5%, now persisted as authoritative.** Close to the old 4% — the judgment
floor was roughly right — but every component is now named, sourced or
explicitly ASSUMED, and adjustable.

## Forecast #4 — AI capex contribution to 2027 real GDP growth vs. Bridgewater's ~150bp

**Authoritative probability: 57% (YES = 2027 contribution exceeds Bridgewater's
~150bp estimate), from a tier 3 reference-class / base-rate-plus-adjustments
estimate.** Reframed from the earlier tier 2 trend fit (see below).

### Why the trend extrapolation was the wrong tool

The target of this forecast is **Bridgewater's own ~150bp estimate** — a
forward-looking judgment call — not a historical baseline. The tier 2 approach
fit a flat 10-year BEA contribution series and measured the 150bp threshold as
~2–3σ above that history, producing a **2.4%** probability. That framing is
structurally wrong: it compares the outcome *to history* instead of *to the
expert estimate the question actually asks about*. A near-flat historical proxy
makes "beat a credible forward estimate" look like a 2.4% tail event, which does
not hold up. Absent a specific reason to think Bridgewater is biased high, the
honest prior on the outcome exceeding their own central estimate is **close to
50%, not near zero** — you are asking whether reality lands above or below a
competent analyst's midpoint, which is roughly a coin flip before evidence.

### The reference-class estimate now used

Handled with the same machinery as the other tier 3 forecasts
(`tier3_judgment.py` `ReferenceClassEstimate`):

- **Base rate: 50%.** Reference class: *"outcomes relative to a credible,
  forward-looking expert central estimate, absent specific evidence of bias."*
  Source: an explicitly stated **judgment starting point** — no historical
  frequency exists for "beating a specific analyst's forward estimate," so 50%
  is the deliberate uninformed prior, not a measured rate.
- **+6pp — Q1 2026 real investment acceleration.** Real information-processing
  investment jumped QoQ ($1,564B Q4'25 → $1,673B Q1'26 SAAR, ~+7%). Real
  momentum, but kept small because it is a single volatile, seasonally-strong
  quarter (Q1 prints run well above full-year averages), not proof of a
  full-year trend.
- **+6pp — Structures / physical-buildout boom.** Nonresidential structures and
  capex buildout are visibly elevated (data-center and CHIPS-fab construction).
  Sized conservatively because BEA structures data mixes in substantial non-AI
  construction and cannot isolate data centers.
- **−5pp — Resolution metric narrower than the estimate's scope.** The
  resolution line is the BEA IP-equipment/software contribution (historically
  ~0.4pp), narrower than the total AI-capex scope Bridgewater's 150bp covers;
  clearing 150bp on the narrow measured line is a harder bar than beating the
  headline estimate. This is a scope/definitional caveat, **not** a trend
  extrapolation, and is kept modest given genuine ambiguity in how the metric
  will be scoped at resolution.

**Net: 50 + 6 + 6 − 5 = 57%.** A modest lean above a coin flip: real momentum in
the data, tempered by an honest measurement caveat.

### Bayesian reframing — the same factors as an explicit likelihood-ratio update (2026-07-22)

The additive arithmetic above is now formally reframed as a Bayesian update
(`bayesian_update.py`, runnable standalone): the 50% base rate is the prior, and
each named factor is expressed as a likelihood ratio
LR = P(observed evidence | YES) / P(observed evidence | NO), combined in odds
form. The named factors and their rationale text are unchanged — only the
combining arithmetic is upgraded.

| Factor | LR (range) | Additive step | Implied LR of that step |
|---|---|---|---|
| Q1 2026 real investment acceleration | 1.30 (1.10–1.60) | +6pp | 1.27 |
| Structures / physical-buildout boom | 1.25 (1.00–1.55) | +6pp | 1.28 |
| Resolution metric narrower than scope | 0.80 (0.65–0.95) | −5pp | 0.81 |

**Posterior: odds 1.00 × 1.30 × 1.25 × 0.80 = 1.30 → 56.5%** (sensitivity band
42–70% with all LRs at their extremes). The Bayesian recombination **confirms
the additive 57%** to within half a point — the additive steps were implicitly
well-calibrated LRs (compare the implied-LR column). The authoritative persisted
number stays **57%**; the Bayesian formulation is the primary statement of the
math, shown in the TUI's tier 3 view for this forecast.

LR grounding (see `bayesian_update.py` for full derivations): the Q1 print's
evidential value is capped by real Q1 seasonality computed from the same cached
FRED series — mean Q1 QoQ is 3.06% vs 2.30% overall (2016–2026), so a hot Q1 is
partially expected even under NO, though the latest 6.97% QoQ is well above even
the Q1 norm. The structures factor's LR low end is 1.00 because the contaminated
BEA series could look identical with non-AI construction doing the work. The
narrow-metric factor is a hypothesis-scope correction (an ASSUMED mapping onto
odds), not observational evidence, and is flagged as such in the module.

### Archived: the old tier 2 trend fit (2.4%)

The trend work is preserved, not deleted — it is simply no longer authoritative:

- The fit code remains in `tier2_trend.py`
  (`information_processing_investment_trend_forecast`); its
  `__main__` no longer persists #4.
- The old model config is retained (commented) in `tui.py` under `tier2["4"]`.
- For the record, the 10-year fit showed no significant trend (slope t ≈ 0.60
  with structures / 0.43 equipment-only, 8 dof, R² ≈ 0.02–0.04); short-window
  fits (n=4–5) were underpowered and biased upward by the seasonally strong Q1
  print; and the Q1 2026 quarter (+1.15pp contribution / +7% QoQ level) was
  flagged as directionally informative but not statistically reliable at
  quarterly frequency. Those findings now inform the adjustment factors above
  rather than a standalone extrapolation.

## Forecast #5 — Does the Fed raise rates at least once by year-end 2026?

**Authoritative probability: 62.6% (was 77.5%) — a tier 1 hidden Markov model of
FOMC posture, Monte-Carlo'd over the remaining 2026 meetings. Nothing else.**
Resolution: YES if the fed funds target range is raised at any 2026 meeting; NO
if held or cut all year. Code: `fomc_history.py` (data + labeling) and
`tier1_market.py` (model).

The tier 3 market-blend layer that used to sit on top of this model was
**retired on 2026-07-29**, and #5's tier list dropped from `[1, 3]` to `[1]`.
Forecast #5 is now a pure HMM: the Monte Carlo output *is* the answer, and the
two market reads below it are cross-checks that enter the number nowhere. See
"The blend layer, retired" and the named finding that follows it.

### The latent-state formulation

The observable at each meeting is the action — `hike`, `hold`, `cut`. The thing
that actually drives the action is the Committee's *policy posture*, which is
not directly observable and which persists across meetings. That is exactly the
shape of a hidden Markov model, so posture is modeled as a latent chain over
three states:

| State | Meaning |
| --- | --- |
| `hawkish_bias` | dot plot implies materially higher rates ahead |
| `neutral_hold` | dot plot implies roughly the current rate |
| `dovish_bias` | dot plot implies materially lower rates ahead |

**Labeling.** The 84 regular meetings from 2016-01-27 through 2026-07-29 are
labeled off each meeting's *implied 12-month rate change*: take the median
year-end dot from the SEP in force, subtract the post-decision target midpoint,
and annualize by the months remaining to that calendar year-end
(`annualized_dot_change_bps`). A meeting is `hawkish_bias` above +25bps,
`dovish_bias` below −25bps, `neutral_hold` in between
(`ROUGHLY_FLAT_THRESHOLD_BPS`). The labels are therefore derived from published
Fed projections, not assigned by hand.

**Non-SEP meetings carry forward the most recent SEP.** Only four of the eight
annual meetings publish a dot plot. Rather than interpolate or drop the other
four, `build_history` labels every meeting off the last SEP at or before its own
date. Note this is not a copy: the target midpoint and the months-to-year-end
denominator both keep moving, so a carried-forward meeting can and does change
posture as the year progresses. Nine unscheduled events (notation votes, the
canceled March 2020 meeting) are excluded outright and enumerated in
`EXCLUDED_NON_REGULAR_EVENTS`; the run reports zero data gaps across the 84.

Posture counts: 45 `hawkish_bias`, 21 `dovish_bias`, 18 `neutral_hold`.

**Estimated transition matrix, P(next posture | posture):**

| from \ to | hawkish | neutral | dovish |
| --- | --- | --- | --- |
| `hawkish_bias` | **0.818** | 0.091 | 0.091 |
| `neutral_hold` | 0.222 | 0.611 | 0.167 |
| `dovish_bias` | 0.190 | 0.143 | 0.667 |

**Estimated emission matrix, P(action | posture):**

| posture | hike | hold | cut |
| --- | --- | --- | --- |
| `hawkish_bias` | 0.378 | 0.556 | 0.067 |
| `neutral_hold` | 0.056 | 0.889 | 0.056 |
| `dovish_bias` | 0.048 | 0.714 | 0.238 |

The number that does the work is the **hawkish self-persistence of 0.818**: once
the Fed is leaning hawkish it stays leaning hawkish at the next meeting more
than four times in five. That is what makes a three-meeting horizon materially
riskier than three independent draws at the unconditional 37.8% hike emission.

**Known limitation, flagged not hidden:** 2016–2026 pools several distinct rate
regimes (near-zero 2016–19, the 2022–23 hiking cycle, the current one) into one
transition/emission estimate. A regime-switching extension was not attempted;
the pooled estimate is treated as an unconditional historical anchor. This was
once the stated reason for blending it against market pricing; with the blend
retired the limitation stands on its own, unmitigated, and is the main reason to
keep reading the direct market as a check on this number.

### The Monte Carlo procedure

`p_at_least_one_hike_hmm` initializes the chain at the current posture with
probability 1 (`CURRENT_POSTURE`, currently `hawkish_bias` at +41.2 bps
annualized as of 2026-07-29), then for each path advances the posture one step
per remaining meeting and draws an action from that step's emission row.
P(≥1 hike) = 1 − P(zero hikes across all paths). Seed `20260716`, and
**10,000 paths everywhere** — `DEFAULT_MONTE_CARLO_PATHS`, the persisted
`_model_state.tier1["5"].simulations`, and the TUI's paths field all agree, so
the module and the screen report the identical 62.6%. They previously disagreed
(the stored path count was 5,000, giving 62.8% in the TUI against 62.6%
standalone) — a ±0.7pp Monte Carlo artefact of nothing, and exactly the kind of
two-numbers-for-one-quantity ambiguity worth removing rather than annotating.

**The July pin, as originally used — now archived.** For the 2026-07-29 meeting
the emission draw was overridden and P(hike) pinned to a live single-meeting
market read of **10.7%** (Polymarket, ~$78M market, as of 2026-07-21; the
`MEETING_HIKE_PROBABILITY_OVERRIDES` mechanism). The justification was that for
an imminent, precisely-priced meeting a live quote beats an unconditional
historical base rate, while the posture chain still advanced through the
overridden meeting so later meetings stayed state-dependent. The pin was worth
−8.1pp: the four-meeting base was 62.5% with it and 70.6% without.

That pin is now archived in `tier1_market.py` as `ARCHIVED_JULY_29_*`. Two things
are worth recording about how it performed. It was **directionally right** — the
Fed held. It was also **materially too low by the time the meeting arrived**: an
eight-day-old quote missed the July repricing, and CME FedWatch had roughly a
1-in-3 chance of a July hike on the morning of the decision (CNBC, 2026-07-29).
The lesson carried forward is that single-meeting pins decay fast, which is part
of why no meeting is pinned now.

### The calibration impossibility

An attempt was made to calibrate the HMM so that its per-meeting hike hazard
reproduced the market's meeting-by-meeting term structure. **It cannot be done
without breaking the model**, and the reason is structural rather than a
tuning failure.

The chain is stationary and its transition matrix is strongly diagonal. Starting
from a `hawkish_bias` point mass, the posture distribution can only relax
monotonically toward the chain's stationary distribution, so the implied hike
hazard can only drift monotonically across successive meetings. The current fit
makes this concrete — marginal P(hike) by meeting, 200,000 paths:

| | Sep 16 | Oct 28 | Dec 9 |
| --- | --- | --- | --- |
| HMM marginal hazard | 31.8% | 28.3% | 26.0% |
| Live market (2026-07-29) | 52.5% | 26.3% | 31.7% |

The market hazard falls then rises — it is **non-monotonic**, because the market
is pricing a specific September decision and a specific December fallback around
an October meeting nobody expects to act at. A stationary diagonal chain has no
degree of freedom that produces that shape. The only ways to force it are to
invert the states' meanings (make `hawkish_bias` the *low*-hike state, which
destroys the labeling's link to the dot plots) or to collapse the three states
into one (which discards the state-dependence that is the model's entire point).

The conclusion adopted: **do not calibrate.** The HMM is kept as an honest
unconditional historical anchor with a shape it can actually represent, and the
meeting-specific, non-monotonic market information is kept outside the model
entirely, as a displayed cross-check. (This was originally "applied once,
separately, in the tier 3 blend"; with the blend retired the market information is
not applied at all, only reported.) This is a real limitation of the model,
documented rather than papered over.

### Structural limitation: dissent blindness

A second named limitation, in the same shape as the calibration impossibility.

**The HMM measures posture through projections and is blind to voting-record
dispersion.** Every posture label in the training set is derived from a dot-plot
median. Dissent counts are not an input to the labeling, the transition matrix,
the emission matrix, or the simulation — they appear nowhere in the model. But
the dot plot and the voting record are *distinct, contemporaneous* signals about
the same Committee: a median dot summarizes where participants say rates are
headed, while a dissent count measures how much of the Committee is willing to
act *now*. They can diverge, and on 2026-07-29 they did — the June median dot
implied one more 2026 hike (unchanged information), while three officials voted
to deliver it immediately (new information).

Because the label is a median, the model is structurally insensitive to
*dispersion around* that median. A 12-0 hold and a 9-3 hold with three hawkish
dissents produce an identical training row if the SEP in force is the same. The
June 17 and July 29 2026 meetings are exactly that pair.

Dissents were deliberately **not** forced into the posture labeling: the
labeling's virtue is that it is mechanically derived from published projections,
and grafting a second, differently-sourced signal onto it would make the state
definitions incoherent across the 2016–2026 training set (dissent direction is
not even consistently recoverable as "tighter/easier" for guidance-language
dissents). The limitation is instead recorded here, and the dissent signal was
evaluated separately as a candidate adjustment — see "The dissent adjustment was
evaluated and declined" below, where it was **declined as a sized factor** and
retained as qualitative context. (It was evaluated as a tier 3 factor while that
layer existed; the layer is now retired, so there is no longer even a place to put
one.)

### The July 29, 2026 update

The July 29, 2026 FOMC meeting held the target range at 3.50–3.75% on a 9–3 vote,
with Hammack, Kashkari and Logan each preferring +25bp
([FOMC statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm)).
Forecast #5 did not resolve; three meetings remain. What changed:

1. **July 29 entered the training set** as a completed `hold`
   (`fomc_history._RAW_MEETINGS`), taking it from 83 to 84 meetings. As a
   non-SEP meeting it carries forward the 2026-06-17 SEP (2026 median 3.8%)
   under the documented rule above: +41.2 bps annualized → `hawkish_bias`. No
   new labeling rule was invented for it.
2. **The meeting set dropped to three** — `REMAINING_2026_MEETING_DATES` is now
   2026-09-16, 2026-10-28, 2026-12-09.
3. **The July pin was retired** to `ARCHIVED_JULY_29_*`, and
   `MEETING_HIKE_PROBABILITY_OVERRIDES` is now empty. September is 48 days out
   and October/December are thinly traded, so nothing meets the "imminent and
   precisely priced" bar the pin required. Live per-meeting reads are recorded
   as a cross-check in `MARKET_PER_MEETING_HIKE_PROBABILITY` but are not pinned.
4. **`CURRENT_AS_OF_DATE` advanced** 2026-07-16 → 2026-07-29. Posture is
   `hawkish_bias` either way, so the initial state is unaffected.

**The HMM base barely moved: 62.5% → 62.6%.** Two effects nearly cancelled, and
not in the direction one would guess:

| Step | P(≥1 hike) | Δ |
| --- | --- | --- |
| Old: 83 meetings, 4 remaining, July pinned at 10.7% | 62.5% | — |
| Drop the July meeting | 63.0% | **+0.5pp** |
| Retrain on 84 meetings (July 29 hold added) | 62.6% | −0.4pp |

Dropping a meeting *raised* the estimate. The dropped meeting was pinned at
10.7%, far below the 37.8% hawkish emission, so it contributed almost no hike
probability while still consuming one step of posture decay away from the
hawkish initial state. Removing it left the three remaining meetings starting
closer to `hawkish_bias`. The retrain then shaved 0.4pp: adding a hawkish-posture
*hold* nudged the hawkish hike emission down (0.386 → 0.378) while raising
hawkish self-persistence slightly (0.814 → 0.818).

**Archived old values from this step:** HMM base 62.5% (83 meetings, four
remaining, July pinned at 10.7%, seed 20260716). The blend-layer values retired
the same day — the 87.1% anchor, the +15.0pp adjustment and the 77.5% persisted
probability — are tabulated once in "The blend layer, retired" below rather than
duplicated here.

### The blend layer, retired

Forecast #5 carried a tier 3 layer that took the HMM output as its base rate and
moved it toward a live market price:

> **adjustment = 0.60 × (market anchor − HMM base)**

That layer was **retired on 2026-07-29**. The reasoning is worth stating in full,
because the decision was not "the adjustment got small so we dropped it."

**The blend existed to correct the HMM toward a number that may never have
existed.** Its anchor was 87.1% P(≥1 hike), stated as CME FedWatch's
complement of a 12.9% P(0 hikes by December) as of 2026-07-21. On re-audit that
figure could not be verified. The FedWatch tool itself was unreachable
(`cmegroup.com` timed out; the rendered page never loaded the probability
widget), and the 87.1% — along with an adjacent "32% one hike / 40% two / 18%
three" December distribution summing to roughly the same place — appeared **only
in search-engine synthesis, never in the body of any article actually read**. The
+15pp adjustment was therefore a 60%-weighted correction toward an unsourced
quantity, and the blend's stated justification ("the market knows everything
2026-specific") was doing work on behalf of a price no one could produce.

**What replaced it is stronger than a blend.** Polymarket's *"Fed rate hike in
2026?"* resolves YES if the upper bound of the target range is increased at any
point between 2026-01-01 and the December 2026 meeting — the *same event* #5 asks
about, read off the market's own rules text against `forecasts.py`'s
`resolution_criteria`, not a proxy. Post-decision on 2026-07-29 at 15:35 ET it
traded bid 0.62 / ask 0.63 on $5.16M volume: **62.5%** (`MARKET_CUMULATIVE_*`).
The HMM, which sees no market data at any point, computes **62.6%**. Two methods
sharing no inputs, converging to within a rounding error.

Blending those two numbers produces a −0.1pp "correction," which is a no-op
dressed as a method. Worse, keeping the layer would misrepresent what happened:
it would present an agreement that was *found* as though it had been
*manufactured*. A blend is the right tool when two estimates disagree and each
has a known defect. When an independent structural model and a liquid direct
market land on the same number, the correct action is to report the model's own
answer and show the market beside it as the check that it is.

So: the HMM output is authoritative, and the market reads — the 62.5% direct
market and the reported CME FedWatch September read — are displayed as
cross-checks in the same primary-plus-cross-check shape forecast #1 uses for its
reference-class estimate. They are no longer inputs. `MEETING_HIKE_PROBABILITY_OVERRIDES`
is empty and the tier 3 layer is gone, so **no market price enters forecast #5
through any channel at all** — which is the precondition for the convergence
meaning anything.

**A note on the surviving CME read.** It is kept visible *because* it is the
discordant one: 72% for a September +25bp, against Kalshi 52.5% and Polymarket
52.4% for the same meeting priced within the same hour — a ~20pp gap between
sources both quoting live pricing. It is also second-hand, reported by
[Kiplinger's live FOMC blog](https://www.kiplinger.com/) (up from ~55%
pre-announcement and ~30% a month earlier) and corroborated by TheStreet, since
the tool was not reachable first-party. That is the same ordering as the July
meeting, where FedWatch showed ~33% against Polymarket's 10.7% and the Fed held.
Labeled as reported-not-scraped everywhere it appears.

### Named finding: the independence error is the price of correlation

This is the finding that *explains* the convergence, and the reason the direct
market validates the HMM's structure rather than merely its answer.

Chaining the three live per-meeting market hike probabilities (52.5%, 26.3%,
31.7%) under `p_at_least_one_hike`'s independence assumption gives:

| Method (all from the same 2026-07-29 15:35 ET snapshot) | P(≥1 hike) |
| --- | --- |
| Live per-meeting prices, chained as independent | **76.1%** |
| Direct market on the joint event | **62.5%** |
| HMM + Monte Carlo (no market inputs) | **62.6%** |

**The 13.6pp gap is the market pricing correlation between meetings.** Both
market figures come from real money on the same afternoon, so the wedge is not
staleness, a data error, or two different questions — it is the difference between
`1 − Π(1 − pᵢ)` and what traders will actually pay on the joint event. It is
positive because policy is regime-persistent: the conditions that produce a
September hike are largely the conditions that produce an October one, so hike
outcomes are positively correlated and treating them as independent overstates
the chance of at least one.

The HMM lands at 62.6% rather than near 76% **because its latent posture chain
generates exactly that correlation.** Hawkish self-persistence of 0.818 means the
three remaining meetings are not three independent draws at the 37.8%
hawkish emission — they are three draws from a state that mostly stays put, which
concentrates outcomes into "hikes clustered" and "no hikes at all" and thins the
"exactly one, in isolation" mass. Run the same three meetings independently at
market prices and you get 76.1%; run them through the posture chain and you get
62.6%; ask the market directly and you get 62.5%.

That is the substantive point. The direct market is not simply corroborating a
number. It is confirming that **modeling meeting-to-meeting correlation is
required to price this question**, and putting a size on how much it is worth:
13.6 percentage points. The state-dependence delta the module prints (−13.5pp
versus flat independent chaining) is the same quantity computed from the model
side, and it agrees with the market's to within 0.1pp. Two independent routes to
the correlation premium.

The independent-chaining figure is therefore retained *only* as this measurement,
in `tier1_market.__main__`'s comparison table. It is strictly worse information
than the direct market for answering #5 and is never used as an estimate.

**Archived values from the retired layer:**

| Item | Archived value |
| --- | --- |
| Blend rule | adjustment = 0.60 × (market anchor − HMM base) |
| Market anchor | 87.1% (CME FedWatch cumulative, as of 2026-07-21, unverifiable) |
| Tier 3 adjustment | +15.0pp |
| HMM base at the time | 62.5% (83 meetings, four remaining, July pinned at 10.7%, 5,000 paths, seed 20260716) |
| Persisted authoritative probability | 77.5% |
| Code | `forecast5_blended_probability_pct()`, `_persist_forecast5_blend()` (`tier1_market.py`); `forecast5_tier3_estimate()`, `_render_tier3_blend()` (`tui.py`) |
| Config | `_model_state.tier3["5"]` |

The config dict is archived verbatim under the top-level
`"_archived_model_state"` key in `forecast_state.json`, in a commented block near
`tui.DEFAULT_MODEL_STATE`, and the retired functions in a commented block in
`tier1_market.py`. Nothing was deleted.

### The dissent adjustment was evaluated and declined

See the dissent-blindness limitation above for why the 9–3 vote is a real signal
that this model cannot see. It is **not** sized as an adjustment, for one reason:
**there is no defensible way to size it.**

Three unified hawkish dissents is roughly a once-a-decade event — 2026-07-29 was
the first such vote since September 2016 — and the two clean modern precedents
disagree about what follows. September 2016 (George, Mester, Rosengren, each
preferring a hike) was followed by a hike two meetings later, in December 2016.
August–November 2011 (Fisher, Kocherlakota, Plosser, opposing further
accommodation) was followed by *more* easing and no hike for over four years. One
hit, one miss, n ≈ 2, pointing opposite directions. Thornton and Wheelock's
dissent history (St. Louis Fed, 2014) is descriptive, and no study establishing
predictive value of dissent counts for subsequent rate moves was found. A
reference class of two split cases supports a direction of interest, not a
magnitude — so no magnitude is applied. This is the same discipline that declined
the Bayesian refinement on #6: an adjustment whose size would be invented is
worse than no adjustment, because it launders a guess into the arithmetic.

**A second argument was withdrawn.** An earlier version of this section also
argued that the market anchor was a *post-decision* price — Polymarket printed
62.5% at 3:35 PM, ninety minutes after the 2:00 PM statement disclosed the
dissents — so the signal was already inside the anchor and a factor on top would
double-count it. **That argument died with the blend.** It was valid only while a
market price was an input to #5. A pure HMM contains no market price and
genuinely cannot see voting dispersion through any channel, so "already priced
in" is not available as a reason. The decision rests on the reference class
alone; recording the withdrawal because a correct conclusion resting on a
now-false premise is a latent error.

This also makes the dissent-blindness limitation **more** load-bearing than when
it was written. While the blend existed, the model at least *indirectly* absorbed
voting information through a post-decision price. With the blend retired that
channel is closed: there is now no path whatsoever by which forecast #5 can see
that three officials voted to hike immediately. The limitation is unmitigated,
and it is documented rather than patched.

## Forecast #6 — Headline PCE inflation ≤ 3.5% by Dec 2026

**Authoritative probability: 35% (YES = PCE YoY at or below 3.5% at the Dec 2026
print), from a tier 3 reference-class / base-rate-plus-adjustments estimate.**
Reframed from the earlier tier 2 Student-t trend fit (see archive below).

### Why trend extrapolation alone was insufficient

The trend model fit 12 monthly PCE-YoY points, projected ~4.49% for Dec 2026,
and returned a **3.8%** probability of landing ≤3.5%. The problem is not the fit
— it is that a 12-point time-series fit's uncertainty band is *purely
statistical*. It has no way to represent real macro-surprise risk (oil shocks,
tariff changes, base effects, a growth scare that forces faster disinflation)
over a **7-month horizon**. A near-3.8% tail claim implies we can nearly rule out
PCE being ≤3.5% by December, which the actual evidence does not support: the
Fed's own participants are far less certain than that. Trend extrapolation is the
right tool when the future is "more of the same series"; it understates the tails
when the outcome is a macro variable exposed to shocks the sample can't see.

### The reference-class estimate now used

Handled with the same `tier3_judgment.py` `ReferenceClassEstimate` machinery as
the other tier 3 forecasts:

- **Base rate: 34%.** Reference class: *"PCE inflation landing at or below a
  threshold, benchmarked to the FOMC's own contemporaneous year-end projection
  distribution."* This is the **midpoint of the 21–47% bound** on the share of
  the 19 FOMC participants projecting 2026 PCE ≤ 3.5%, derived from the June 2026
  SEP (median 3.6%, central tendency 3.5–3.7%, range 2.7–4.1%;
  `fomcprojtabl20260617.htm`). The bound comes from the central-tendency and
  range definitions: at least the 3 bottom-trimmed participants plus the
  central-tendency floor (p₄ = 3.5%) are ≤3.5% (≥4), and no more than everyone
  below the 3.6% median (≤9). The exact per-participant count is not
  machine-readable (Figure 3.C is a chart image; the Fed publishes no separate
  accessible-data table for it), so the midpoint of the bound is the anchor. This
  is **real, sourced evidence from the body whose decisions drive the outcome** —
  a stronger prior than a naive 50% or the flat historical trend fit.
- **+10pp — Fed's active hawkish posture.** Forecast #5's authoritative
  probability is now 77.5% (its HMM base rate blended with CME FedWatch market
  pricing), up from the 63% HMM-only figure, and the June 2026 SEP median dot
  (3.8%) is above the current 3.625% midpoint (~one more hike signalled). Hiking
  is the Fed's direct tool for pushing inflation toward target, so a materially
  higher, market-corroborated hike probability raises P(PCE → ≤3.5%) more than the
  HMM-only read did. Sized up from +6pp to +10pp accordingly, but still bounded:
  hikes act with long lags and don't guarantee the target is hit by the December
  print.
- **−12pp — Recent trend momentum (wrong direction).** PCE YoY accelerated
  2.87 → 2.87 → 3.54 → 3.80 → 4.07 over the last five prints; the linear trend
  projects ~4.49% for Dec 2026. This is the strongest concrete evidence against
  resolution, hence the largest single adjustment. (This is the one thing the old
  trend fit got right — preserved here as an explicit factor rather than as the
  whole model.)
- **+3pp — Single-print resolution dispersion.** Resolution is a single December
  YoY print, and monthly YoY has swung up to ~0.67pp in one month recently
  (Feb→Mar). That realized-print volatility (distinct from the SEP's dispersion
  of participant *point* views) puts real left-tail mass below 3.5% even with the
  central path above it. Small; it is the same narrow-band-understates-uncertainty
  point that motivated the reframe.

**Net: 34 + 10 − 12 + 3 = 35%.** Clearly below the SEP-implied base rate — recent
momentum dominates — but an order of magnitude above the old trend model's 3.8%,
because the estimate now carries real macro uncertainty instead of a purely
statistical band.

### Bayesian reframing — and a flagged divergence (2026-07-22)

The additive factors are now formally reframed as a Bayesian likelihood-ratio
update (`bayesian_update.py`): prior = the 34% SEP-anchored base rate, each
factor an LR, combined in odds form. Factors and rationales unchanged.

| Factor | LR (range) | Additive step | Implied LR of that step |
|---|---|---|---|
| Fed's active hawkish posture | 1.40 (1.15–1.70) | +10pp | 1.52 |
| Recent trend momentum (wrong direction) | 0.45 (0.30–0.60) | −12pp | 0.60 |
| Single-print resolution dispersion | 1.25 (1.10–1.45) | +3pp | 1.14 |

**Posterior: odds 0.515 × 1.40 × 0.45 × 1.25 = 0.406 → 28.9%** (sensitivity band
16–43%). **This diverges from the additive 35% by −6.1pp — flagged, not silently
adopted.** The persisted number **remains 35%** pending a deliberate decision.

Where the divergence comes from (visible factor-by-factor in the implied-LR
column): almost entirely the momentum factor. The additive −12pp step implied an
LR of only ~0.60, but the estimate used in the update is ~0.45 (range
0.30–0.60), originally corroborated by a real-data cross-check: of 14 historical
months matching today's run-up shape (YoY ≥ 3.5%, rising, up ≥ 0.4pp over four
prints), only **2 of 14** saw YoY fall the required ≥ 0.57pp within 7 months.

### Verification of the run-up sample — Bayesian posterior NOT adopted (2026-07-23)

The 14-month sample was inspected before any adoption decision
(`pce_momentum_crosscheck()` now reports the run structure). Verdict: **the
reference class does not hold up as an independent sample.** The 14 qualifying
months collapse to a *single* 2021–22 inflation surge — one consecutive run
2021-04 → 2022-03 plus 2022-05 → 2022-06, split only by one noise month
(2022-04) — and the 2 "successes" are simply the two sampled months adjacent to
that surge's mid-2022 peak. Effective n = **1 episode**. A month-level 2/14
frequency drawn from one autocorrelated event cannot arbitrate between the
0.45 point estimate and the additive-implied 0.60 (which sits inside the stated
0.30–0.60 range); it supports "LR below 1" directionally and nothing sharper.

**Decision — same small-n discipline applied elsewhere in this project (e.g.
the rejected n=4 trend fit in #3): the additive 35% remains the persisted
authoritative number.** The Bayesian formulation stays displayed in the TUI and
this file as the formal recombination and sensitivity (posterior 28.9%, band
16–43%), but its harsher momentum LR is a reasoned judgment with weak empirical
corroboration, not a calibrated estimate, so it does not override the additive
arithmetic it was meant to check.

### Archived: the old tier 2 trend fit (3.8%)

Preserved, not deleted — simply no longer authoritative:

- The fit code remains in `tier2_trend.py` (`pce_trend_forecast`); its `__main__`
  no longer persists #6.
- The old model config is retained (commented) in `tui.py` under `tier2["6"]`.
- The SEP cross-check display built into `Tier2ModelScreen` is now dead for #6
  (which no longer routes there); its evidence lives on in this forecast's
  base-rate source.
- For the record, the trend work also compared a **linear vs. exponential
  (log-linear)** form on the trailing 12 months: linear R²=0.738 / AIC=−28.15 /
  proj 4.49% / P=3.8%; exponential R²=0.772 / AIC=−29.79 / proj 4.73% / P=1.7%.
  ΔAIC=−1.64 (< 2, near-indistinguishable), so the non-linear shape was weakly
  preferred at most. Both projected well above 3.5% — the finding that motivated
  the SEP cross-check and, ultimately, this reframe.

## Forecast #7 — Does non-US/non-China sovereign AI compute funding cross $250B by year-end 2026?

**Authoritative probability: 1.9% (YES = strict-scope cumulative public-sector
commitment to non-US/non-China sovereign AI compute/chip infrastructure reaches
$250B by Dec 31, 2026), from the regime-switching compound Poisson model
(`sovereign_ai_jumps.py`, variant d) — adopted 2026-07-23 (see the
regime-switching subsection below). The tier 3 pace-based estimate documented
next (14%) is ARCHIVED for comparison: its step-change intuition was real, but
it asserted a regime shift without modeling one; the regime-switching model
prices that same shift explicitly and lands far lower.** A **reframe** from the old open-ended "does any non-US/non-China
government commit >$10B?" (resolution 2027-12-31) to a specific cumulative-dollar
threshold with a fixed resolution date of **2026-12-31**.

### Scope decisions (these dominate the answer — fixed at framing)

The threshold outcome is governed far more by scope than by forecastable
uncertainty, so two rules were fixed before any tally:

1. **Public-seed only, not mobilized.** Count government loans, subsidies, grants,
   direct equity, and SWF commitments tied to state AI-infrastructure strategy —
   **not** privately mobilized capital, corporate capex, or private pledges. So
   EU InvestAI's **€20B public seed counts**; the **€200B mobilized figure does
   not**; France's **€109B private pledge does not**; Korea's **₩150T fund does
   not**.
2. **SWF vehicles at non-US-domestic-infrastructure portion only.** Government-linked
   sovereign-wealth vehicles (MGX, HUMAIN) count **only the portion committed to
   non-US domestic infrastructure — not full announced fund capacity, and not
   deployments into US/global labs.** This matters enormously: MGX ($49B fund)
   "backs every major US frontier lab," and HUMAIN's $100B headline is aspirational
   AUM (with $3B into xAI in the US). Under a broad reading (full vehicle capacity +
   mobilized totals) the category is *already well past $250B*; under this strict
   reading it is ~$90B.

### Current strict tally (as of ~Jul 2026, web-sourced)

| Jurisdiction | Strict public-sector figure (USD) |
|---|---|
| EU — InvestAI public seed (€20B) | ~$22B |
| Gulf — Saudi + UAE domestic SWF portion | ~$25B ($20–30B) |
| Japan — Rapidus/chip+AI budget support | ~$15B |
| France — Bpifrance public portion (€10B) | ~$11B |
| South Korea — direct national AI budget (₩10.1T) | ~$8B |
| UK — Sovereign AI Fund + public compute | ~$3B |
| Canada — Sovereign AI Compute Strategy | ~$2B |
| India — IndiaAI Mission (₹10,300 cr) | ~$1.25B |
| **Strict cumulative** | **~$85–90B** |

The Gulf line was the widest-uncertainty item and was tightened specifically: most
Gulf AI-infra money is either aspirational vehicle capacity or **US-partnered
private** capital (Microsoft's $15.2B via Khazna; the US-partnered Stargate UAE
consortium; MGX's deployments into US labs), all excluded. The clean non-US-partnered
public/SWF domestic slice is only ~$20–30B (Saudi's $1.2B 250MW financing + ~$9.1B
"Year of AI" strategy; a comparable UAE sovereign slice). This pulled the base to
~$90B and widened the gap to **~$160B**.

### Base rate: 12% — pace-based, not a coin flip

The reference class is the **growth pace** of this category, not a symmetric prior.
The category grew from ~$0 to ~$90B in **~18 months** (the 2025–26 wave: EU/France
Feb 2025, Japan's Dec 2025 budget quadrupling, Korea's 2026 budget, UK Apr 2026,
Canada Budget 2025, India FY25-26) — a run-rate of **~$55–65B/yr**.

- At that pace, the ~5 months to Dec 31 add **~$25B → year-end ~$115B**.
- Even at a **doubled/accelerating** pace (~$120B/yr): ~$50B → **year-end ~$140B**.
- Reaching **$250B needs ~$160B in ~5 months = ~$385B/yr annualized — a 4–6×
  acceleration** over an already record pace, i.e. adding ~1.8× the entire
  accumulated base in five months.

So the pace extrapolation lands at **~$115–140B, a little over half the threshold**;
crossing $250B requires a step-change, not continuation. **12%** is the probability
of that step-change in a lumpy but momentum-driven category.

### Adjustment factors

- **+7pp — Geopolitical / administration momentum.** A genuine sovereign-AI arms
  race (US Stargate $500B triggering EU/Gulf/Asia responses). The upside path is a
  *cluster* of large discrete new sovereign commitments (a China-response package,
  new EU "AI continent" money, fresh Gulf domestic pledges). Real and substantial;
  sized to the chance lumpiness + momentum beats the trend pace.
- **−5pp — Budget-cycle deceleration and timing.** Most 2026 public budgets were
  already announced earlier this year (Japan Dec 2025, Korea/UK 2026), so net-new
  *large* public commitments tend to slow in Aug–Dec; and continuation of even the
  record pace still lands ~$110B short.

**Net: 12 + 7 − 5 = 14%.** The estimate resolves **NO** with high probability —
at ~$90B today and a record-but-not-exponential pace reaching ~$115–140B, $250B
needs a 4–6× acceleration in five months. The 14% is the real-but-small chance
arms-race momentum produces a burst of mega-commitments; it sits below a coin flip
because the pace math, not pessimism, puts it there.

### Quantitative upgrade — compound Poisson Monte Carlo, divergence flagged (2026-07-22)

A compound Poisson jump model (`sovereign_ai_jumps.py`, runnable standalone) now
formalizes the pace argument. The dated commitment history was re-verified
line-by-line with primary sources (EC IP/25/467 for InvestAI, PIB for IndiaAI,
ISED for Canada, Nikkei/Japan Times for Japan's two tranches, etc.): **10 dated
arrivals, 2024-03-07 → 2026-04-16**, itemized sum ~$81B (verified tally ~$84B —
the documented ~$85–90B band holds; the Gulf $20–30B attribution dominates the
residual). Model:

- **Arrival rate**: λ = 10 / 2.374 yr = **4.21 commitments/yr** → expected
  jumps in the 162-day horizon: **1.87**.
- **Jump sizes**: lognormal MLE μ = 1.56, σ = 1.14 (median $4.8B, mean $9.1B).
  Fit checked, not assumed: KS on log-sizes passes (0.203 < ~0.28 Lilliefors
  5%); AIC ranks exponential ahead by 2.2 points — pure parameter-count penalty
  on a near-tied likelihood, below the "clearly beaten" bar, and the thinner
  exponential/gamma tails would push P(cross) *lower*, so lognormal is the
  conservative-for-the-conclusion choice.
- **Three variants, none blended**: (a) stationary fit → **P(cross $250B) =
  0.3%** (mean year-end total ~$107B); (b) rate-uncertainty (λ drawn per path
  from its Gamma(10.5, 2.37y) Jeffreys posterior) → **0.5%**; (c) an ASSUMED
  acceleration stress case (λ×2, sizes×1.5 — the arms-race step-change world
  the +7pp factor argued for) → **3.4%**.

The stationary model's divergence from the old 14% was structural: crossing
needs ~$160B of new strict-scope commitments in 162 days (~18× the mean jump),
while the fitted process supplies ~1.9 jumps — so the 14% was almost entirely a
**regime-change belief** that a stationary process cannot represent.

### Regime-switching extension — the step-change modeled explicitly, ADOPTED (2026-07-23)

Rather than choosing between the stationary 0.3% and the judgment 14%, the
model now has a **two-state regime switch** (variant d, the headline — the same
structural move as forecast #5's posture-switching HMM), with every parameter
grounded in the observed record or explicitly ASSUMED with named anchors:

- **Regime A (organic pace)**: the fitted λ = 4.21/yr and lognormal sizes.
- **Trigger into Regime B**: Stargate-class escalations — events that provably
  set off coordinated sovereign responses — arrived exactly **once** in the
  2.374-yr observation window (Stargate, 2025-01-21; MLE 0.42/yr). The n=1
  estimation uncertainty is propagated by drawing the trigger rate per path
  from its Jeffreys posterior Gamma(1.5, T). Response latency: **21 days**, the
  observed Stargate → InvestAI lag (Bpifrance responded in 17). Named live
  catalysts consistent with a future trigger: a China-response package, EU "AI
  continent" money, fresh Gulf domestic pledges.
- **Regime B (arms-race burst)**: arrival rate **12/yr = the maximum ~90-day
  pace actually observed** in this category (Japan + Korea + Japan,
  Nov 22 – Dec 26, 2025); jump sizes scaled by U(1.0, 3.5) — floor 1.0 because
  the observed Feb-2025 post-Stargate burst drew ordinary-scale sizes (the two
  largest historical jumps, $21B and $10.5B); ceiling 3.5 ASSUMED, anchored to
  the largest concrete packages in live reporting (the EU gigafactory
  member-state co-funding obligation under Council Regulation (EU) 2026/150 —
  member states must at least match the 17% Union share of the €37B
  ten-facility program, ≈ $16–18B if finalized — and the ~$30B top of the Gulf
  domestic band). At 3.5× the single-jump p95 is ~$100B, already beyond
  anything any government has floated.
- Once triggered, the burst runs to the resolution date (no reversion — a
  simplification conservative *toward* YES).

**Result: P(cross $250B) = 1.9%** — decomposed as P(burst regime active before
resolution) = **20.5%** × P(cross | burst) ≈ **7%**, plus ~0.3% organic. It
lands between the stationary 0.3–0.5% and the old 14% exactly as the structure
dictates: the transition probability is real but the *observed and
plausibly-reported* burst magnitudes still usually fall short of +$160B in the
remaining window. The old 14% implicitly required a burst regime far outside
anything in the observed record or live reporting. **Adopted and persisted as
1.9%**; the archived 14% remains above for comparison, and variants (a)–(c)
stay in the module as the stationary fit, rate-uncertainty check, and cruder
stress case.

## Forecast #8 — Does a government take a strategic stake in, or grant champion status to, a frontier AI lab by year-end 2026?

**Authoritative probability: 9% (YES = a government finalizes/executes a
strategic sovereign equity stake or a formal national-champion legal designation
in one of 10 listed frontier AI labs by Dec 31, 2026), from a tier 3
reference-class / base-rate-plus-adjustments estimate.** A **reframe** from the
old open-ended "does any government take a stake in / designate a national-champion
AI company?" (resolution 2027-06-30) to a specific, narrow-scope, lab-only question
with a fixed **2026-12-31** date.

### Scope decision (narrow) — and why the SWF/state-bank stakes are excluded

Like #7, the outcome is scope-dominated. Under a *literal* reading of "any
government executes a formal equity stake," #8 would be **already resolved YES**:
government-linked vehicles already hold executed stakes in listed labs — MGX/Mubadala
(Abu Dhabi sovereign) in **OpenAI** and **Anthropic**, HUMAIN/PIF (Saudi sovereign)
in **xAI**, and Bpifrance (French state bank) in **Mistral**. These are **excluded**
by the narrow scope because they are **financial portfolio investments** — passive,
minority, return-seeking — **not deliberate industrial-policy interventions**. The
question requires either **(a)** a strategic/control-oriented sovereign stake (in the
mold of the excluded May 2026 US–Intel intervention) or **(b)** a formal
national-champion legal designation with attached protections, **executed, not
merely proposed**. Chip/hardware/foundry and quantum firms are out of scope entirely
(a separate industrial-policy category — Intel, the $2B quantum deployment — already
resolved there).

### Base rate: 10%

Reference class: *a government executing a strategic/control sovereign stake or a
formal champion designation in a frontier AI lab within a ~5-month window.* There is
**no direct precedent for a lab.** But the policy tool is demonstrably **live** in
adjacent strategic tech — the May 2026 US–Intel strategic stake and the 2025–26 wave
of government stakes in critical-tech firms show the taboo is broken — so the rate is
not ~0. Extending it to a *lab* **and** executing (not proposing) within ~5 months is
a high bar: **10%**.

### Adjustment factors — the France/Mistral vs. US-disinclination tension

- **+5pp — France/Mistral warm path.** The single most plausible near-term catalyst.
  France openly frames Mistral as its national/European champion; the ASML
  foreign-ownership stake fuels an active sovereignty debate; and the state is already
  entangled (Bpifrance stake, Jan 2026 Ministry of Armies contract). A move to a formal
  designation or strategic stake is *the* realistic YES route — tempered because France
  is still at framing/procurement, so a formal executed action in five months would be
  an escalation, not a continuation.
- **−6pp — US disinclination and the execution bar.** **7–8 of the 10 listed labs are
  US-based** (OpenAI, Anthropic, xAI, Meta, Microsoft, Amazon, SSI; DeepMind is
  UK-sited but Google-owned), and the US is moving the *opposite* direction: the
  June 2, 2026 EO creates a "covered frontier model" security-review label while
  **explicitly banning mandatory licensing/protection**, and the DoW designated
  **Anthropic a supply-chain *risk***. That removes the largest slice of the list from
  realistic YES paths. Combined with the "executed by Dec 31, not merely proposed"
  requirement, it is the dominant drag — slightly outweighing the France catalyst,
  which is why the net lands just below the base rate.

**Net: 10 + 5 − 6 = 9%.** A strong **NO**: the qualifying action is unprecedented for
labs, the one warm candidate (France/Mistral) isn't close to a *formal executed*
stake/designation, and the US bloc — most of the list — is actively hands-off. The 9%
is the real-but-small chance France (or a longshot such as Canada/Cohere) formalizes a
champion intervention before year-end.

### Deliberately judgment-anchored — no quantitative model, and why (2026-07-22)

When the other forecasts were upgraded to explicit quantitative models, **#8 was
deliberately left as a judgment-anchored reference-class estimate.** This is a
methodological choice, not a gap. The question asks about a **literally
unprecedented event** — no government has ever taken a strategic/control stake
in, or granted formal champion designation to, a frontier AI *lab* — within a
five-month window, over an enumerated list of ten companies, under a narrow scope
that excludes every executed government-linked stake that does exist (MGX,
HUMAIN, Bpifrance — portfolio investments, out of scope by design). There is no
historical frequency to fit, no arrival process to estimate a rate from (the
adjacent-precedent set is a handful of 2025–26 events in a *different* asset
class), and no market pricing the narrow resolution event. Any stochastic model
here would run on invented parameters — false rigor. The honest quantitative
form for this evidence is the stated structural prior (10%, anchored to the
demonstrated-but-adjacent policy tool) plus the two named, opposing adjustments.

## Forecast #9 — Does Virginia's commercial electricity rate decrease within 6 months (by 2027-01-21)?

**Authoritative probability: 2.3% (YES = the EIA commercial-sector VA rate is below
the current 10.33 ¢/kWh baseline at the 2027-01-21 resolution date; NO if flat or
higher), from the deterministic + OU decomposition model
(`electricity_simulation.py`) — adopted 2026-07-23 after the fuel-year mechanism
was independently verified (see the quantitative-upgrade subsection below). The
tier 3 reference-class estimate documented next (30%) is ARCHIVED for comparison,
the same pattern as #4/#6's archived trend fits: its arithmetic is preserved, but
its +8pp fuel-easing factor is now known to lack a transmission channel in this
specific window.**
Twice-reframed: first the data source was corrected from all-sector to **commercial**
(data centers are commercial/industrial customers, so the commercial rate is the
honest signal — residential is up ~14.5% YoY for different, more insulated reasons,
because Virginia's new dedicated data-center rate class appears to insulate the
general commercial class); then the question itself moved from a ">15% rise" tier-1
threshold to a **directional 6-month reversal** (does the rate *fall below* 10.33?),
handled as a tier-3 judgment. The commercial EIA cache still anchors the 10.33
baseline; the old threshold config is archived in `tui.py` (`tier1["9"]`, commented).

### Base rate: 35%

Reference class: *how often a regulated state's commercial electricity rate posts a
genuine 6-month **net decrease**.* Retail prices drift upward over time (~2–3%/yr
nominal), so a net decrease over a given 6-month window is a **minority event** — but
not rare, because natural-gas fuel pass-through and seasonality produce real declines
a substantial minority of the time. **35%.**

**Mean-reversion note (what keeps it at 35%, not lower):** 10.33 ¢/kWh (Jul 2026) is
the **top of the recent 8-month range (10.21–10.33)** — the rate was *below* 10.33 in
**7 of the last 8 months**. So "below 10.33 in January" sits squarely inside the
recent noise band; mean-reversion from a local high does real work and stops this
from being a longshot.

### Adjustment factors

- **+8pp — Documented fuel-cost easing (STEO gas downgrade).** EIA's own STEO
  forecasts Henry Hub gas ~2% lower in 2026, and the **May 2026 STEO revised the 2026
  forecast down a further 4.4%** — genuine downward pressure on the fuel portion of
  the rate. Sized modestly: fuel is only ~⅓ of the commercial rate (so a ~2–6% gas
  move is ~1–2% on the total), and it is a *forecast*, not a locked certainty — it has
  to be large enough to overcome the base-rate hikes, which is borderline.
- **−13pp — Regulatory-locked base-rate increases.** Dominion's SCC-approved
  base-rate increases are **regulatory-locked through 2027** — a fixed cost component
  that does *not* reverse with fuel prices and pushes the total rate up, certainly.
  Sized larger than the fuel tailwind because it is **certain and structural** while
  the fuel easing is a modest forecast: for YES, the uncertain fuel decline must
  outrun a locked increase.

### No geopolitical wildcard

A "global energy conflict" gas-shock wildcard is **deliberately excluded**: the
research surfaced nothing specific (no current conflict-driven gas shock), so no
speculative geopolitical factor is invented. The fuel-cost easing vs. locked
base-rate mechanism is the whole grounded story.

**Net: 35 + 8 − 13 = 30%.** Expected drift over the window is slightly *up* (locked
base rates edge out modest fuel relief), so a net decrease is a minority outcome —
tempered upward by the fact that the baseline sits at the top of the recent range.
Most sensitive to how fast the locked base-rate hikes phase in *within* this specific
6-month window; if they're back-loaded past January, fuel easing could dominate and
this rises toward ~35–38%.

### Quantitative upgrade — deterministic + OU decomposition, ADOPTED as authoritative (2026-07-23)

The hand-blend above is now decomposed properly (`electricity_simulation.py`,
runnable standalone): rate at Jan 2027 = 10.33 + locked base-rate delta +
regulatory contingencies + fuel delta + winter-spike risk + noise, with the fuel
component modeled as an Ornstein–Uhlenbeck Henry Hub simulation calibrated to
real data (`data_cache/henry_hub_daily.json`, 1,255 daily FRED DHHNGSP
observations 2021–2026; trailing-3yr AR(1) fit κ ≈ 20/yr, σ ≈ 2.1 annualized —
daily-noise-dominated, shown beside the Schwartz one-factor literature anchor
κ = 1.77, σ = 0.74) around the July 2026 STEO quarterly path.

The research that matters most is **regulatory mechanics, not gas prices**:

- **The fuel channel is closed in-window.** Dominion's fuel factor is an annual
  tariff: the rate applying on 2027-01-21 was fixed 2026-07-01 (3.7648 ¢/kWh
  interim, case PUR-2026-00058) and holds through 2027-06-30; interim gas moves
  accrue to a deferral surfacing at the 2027-07-01 reset. The OU simulation
  therefore enters the January rate with **pass-through weight zero** — and the
  counterfactual live-channel fuel delta would be two-sided anyway
  (p10/p50/p90 ≈ −0.9/+0.5/+2.5 ¢), not one-way easing.
- **The STEO leg of the +8pp adjustment is stale**: the July 2026 STEO *raised*
  Henry Hub forecasts ($3.67 for 2026), reversing the May downgrade the
  adjustment cited, and its Q1-2027 forecast ($3.83) is the seasonal *peak*.
- **The locked step is precisely timed**: the biennial-review second step
  (+$209.9M, ~+0.15–0.30 ¢ on Dominion bills, diluted by an ASSUMED 0.65
  Dominion share of VA commercial sales) lands 2027-01-01 — 20 days before
  resolution. Securitization risk (PUR-2026-00078, order due 2026-09-29) is
  one-sided *up* (+~1.4 ¢ if denied, P ASSUMED 0.25). Winter cold-spike risk
  (Jan 2026 printed 11.43 in EIA-861M) is also up.

Result (10,000 paths): median Jan 2027 rate ≈ 10.63 ¢, and **P(below 10.33) =
2.3%** vs the persisted 30%. An empirical cross-check explains the gap cleanly:
January printed below the prior July in 4 of 11 years (36%) of the EIA-861M VA
commercial history — matching the tier-3 35% base rate — but all four came from
the flat-to-declining-rate era; conditioning on the locked Jan-1-2027 step and
the closed fuel channel is what pulls the number to single digits. A flagged
data caveat: the repo's cached smooth series and the preliminary EIA-861M series
disagree about winter 2026 (10.25/10.28 vs 11.43/13.01) — under either reading
the effect on YES is downward or neutral.

**Adoption (2026-07-23)**: the decisive mechanism was independently verified —
Dominion's fuel factor is set on an annual July 1 → June 30 fuel-year cycle via
formal SCC proceeding, not floating with spot gas; the fuel year covering the
resolution window is already locked and does not reset until July 2027, *after*
the January 2027 resolution date. That confirms the model's core finding: the
archived tier-3 estimate's +8pp fuel-easing factor had no real transmission
channel in this window, and its 35% base rate is an unconditional frequency the
locked schedule conditions away. **The model's 2.3% is now the persisted
authoritative probability** (honest band 2–8% allowing for the ASSUMED
parameter bands: the 0.25 securitization-denial probability, the 0.65 Dominion
share, and the winter-spike calibration). The 30% judgment estimate is archived
above for comparison.

## Forecast #10 — Does NRC/DOE finalize an expedited nuclear/SMR licensing or permitting action by year-end 2027?

**Authoritative probability: 94.0%, the central point of an explicitly reported
88–97% gate-sensitivity band (YES = at least one of three specified
EO-accelerated federal nuclear-licensing/permitting actions is formally *finalized*
— not merely proposed — by Dec 31, 2027), from the competing-risks reliability
model (`nuclear_competing_risks.py`) — adopted 2026-07-23 after the EO-era
execution record was itemized and verified (see the reconciliation subsection
below), with the band treatment added the same day after the common-mode gate's
provenance was audited (see the gate-provenance subsection). The tier 3
reference-class estimate documented next (79%) is ARCHIVED for comparison.** The resolution criteria were made explicit
around **three independent paths** (any one satisfies YES): **(a)** the NRC's Part 57
rule (expedited microreactor/SMR licensing, <1-year reviews, fleet approvals);
**(b)** DOE's fast-tracked permitting for its four solicited AI-data-center-plus-nuclear
sites (Idaho NL, Oak Ridge, Paducah, Savannah River); **(c)** the rule letting
DOE/DOW military reactor-testing data fast-track commercial NRC licensing. The
resolution date is **kept at 2027-12-31** (not moved up to 2026-12-31 like #2/#7/#8) —
which materially raises the estimate (a 2026-12-31 window would be ~45%, since it
would hinge entirely on whether the NRC hits one aggressive deadline vs. slips).

### Base rate: 80% — judged against the mandated timeline, not the historical NRC pace

Reference class: *finalization of at least one of the three EO-accelerated actions
within the window.* The anchor is the **stated deadline**, not the historical NRC
cadence:

- **EO 14300 (May 23, 2025) directs the NRC to publish FINAL rules within 18 months —
  by Nov 23, 2026** — which sits **~13 months inside** the 2027-12-31 window, and the
  NRC has publicly committed to a timeline to meet it.
- **Part 57 (path a) is already in finalization:** proposed May 1, 2026; comments
  closed June 15, 2026.
- **DOE's four sites (path b) target operations by end-2027,** forcing permitting to
  finalize in 2026–2027.
- **Only one of three independent paths must finalize.**

Historical NRC proposed-to-final pace is 3–6 years, which would argue for a low rate —
but the operative reference class here is *this* mandate (hard EO deadline + 18-month
runway + three shots), which is why the base rate is 80% rather than the historical
norm. It is held below higher values by the NRC's genuine history of slipping even
statutory/EO deadlines and the strict "finalized-not-proposed" bar.

### Adjustment factors

- **+6pp — Whole-of-government momentum and on-schedule execution.** Not just an
  announced agenda: the NRC already proposed Part 57 on cadence, DOE already selected
  the four sites, and four reinforcing May-2025 nuclear EOs plus the 2024 ADVANCE Act
  all push the same direction. The machine is executing, not just planning.
- **−7pp — NRC finalization slippage and litigation risk.** NRC rulemakings routinely
  slip; EO deadlines are directives agencies miss; the "finalized" bar is strict; final
  rules can be litigated or enjoined; an administration-priority shift is a tail risk.
  Slightly outweighs the momentum factor, so the net lands just under the base rate.

**Net: 80 + 6 − 7 = 79%.** A strong-but-not-certain YES: at least one of three
EO-accelerated nuclear-licensing actions finalizing within an 18-month runway that
already contains a mandated Nov-2026 final-rule deadline. The estimate would fall to
~45% if the window were compressed to 2026-12-31.

### Quantitative upgrade — competing-risks reliability model, divergence flagged (2026-07-22)

The three pathways are a textbook parallel system, now modeled as one
(`nuclear_competing_risks.py`, runnable standalone): P(YES) = (1 − p_systemic) ×
(1 − Π(1 − p_i)), a series-parallel decomposition with an explicit common-mode
gate (one White House push, one strained NRC staff pool, one litigation
environment — pure independence would be false). Per-pathway completion-time
distributions are deadline-anchored mixtures, calibrated to a researched record
(all sources cited in the module):

- **Part 57** (path a): proposed 2026-05-01, comments closed 2026-06-15; NRC's
  *published* final-rule target is 2026-12-01 — 8 days past the EO 14300
  deadline, 13 months before resolution (NIA tracker, 2026-07-06). Curve: mass
  at the Nov-2026 EO window (P(hit deadline) = 0.20 — NRC's own target already
  slips it), a Dec/Jan target+OIRA-jitter window, then a truncated-geometric
  slip tail fitted by bisection to the researched mid-2027 waypoint.
  **P(final by end-2027) = 0.90** — the EO-era NRC is 7-for-7 finalizing rules
  on schedule, and Part 53 (proposed Nov 2024) went final 2026-03-30, more than
  a year ahead of its statutory deadline; the old 3–6-year proposed-to-final
  reference class no longer describes this regime.
- **DOE sites** (path b): diffuse ramp; first selection landed 2026-07-20
  (Amentum, Savannah River phased-lease negotiation), DOE holds a NEPA
  categorical exclusion for advanced reactors (eff. 2026-02-02) and proved
  sub-year formal authorizations (four pilot test reactors critical by
  2026-07-04). **P = 0.75** — no lease is final yet and "finalized" needs a
  signed formal action.
- **DOE/DOW data-bridge rule** (path c): proposed 2026-04-02, comments closed
  2026-05-04, NRC target 2026-11-23 — the shortest-fuse rule. **P = 0.92**.
- **Common-mode gate**: 6% (program-wide injunction, agenda-freezing accident,
  fiscal/leadership crisis compounding 14–15% attrition and an 8.1% budget-cut
  request) — capped low by the researched record: no pending litigation, a
  fee-funded agency that kept EO work going through the Oct–Nov 2025 shutdown,
  a full commission.

Result: **P(YES) = 94.0%** (Monte Carlo cross-check agrees; pure independence
would say 99.8% — the common-mode gate *is* essentially the entire NO side).
Timing diagnostics: median first finalization Nov 2026; P(resolved by end-Dec
2026) ≈ 78% (Monte Carlo, seed 20260722; analytic combined curve 78.1%),
≈ 93% by Jun 2027.

### Reconciliation — the "7-for-7" claim audited, Part 53 as the substantive calibration, ADOPTED (2026-07-23)

Before adoption, the execution-record evidence was itemized from the primary
source (NIA EO 14300 tracker, updated 2026-07-06, populated from NRC's own
Planned Rulemaking Activities site) rather than taken as a slogan:

- **"7-for-7 on schedule" verifies as a count** of genuinely *finalized* rules
  (Practice & Procedure 11/26/25; Sunset Rule 1/8/26 — a direct final with
  partial withdrawal; Aircraft Impact 4/1/26; FOIA 3/6/26; Mandatory Hearing
  Flexibility 4/15/26; FOCD Exceptions 4/23/26; FY2026 Fees 6/22/26 — the full
  list with dates is embedded in the module as `EO14300_FINALIZED_RECORD`). It
  does **not** mix in proposed/in-progress actions. But **all seven are
  procedural, administrative, or narrowly deregulatory** — none is an
  affirmative novel licensing framework — so this record's evidential weight
  for Part 57's pace was *downgraded*. The same tracker also shows NRC itself
  scheduling roughly half of the ~27 EO rulemakings *past* the Nov 23 2026 EO
  deadline (five at 3/31/2027, one at 10/1/2027), confirming the deadline is a
  directive, not a binding constraint.
- **Part 53 is the substantive calibration** (it is NOT one of the three
  resolution pathways and is not counted as satisfying them): proposed
  2024-11-22, final 2026-03-30 = **16.3 months proposed-to-final** for a much
  larger novel framework, *with* a 60-day comment extension and 158 comments,
  still beating its NEIMA statutory deadline by over a year. Part 57 (proposed
  2026-05-01, narrower scope, 45-day comment period closed on schedule with no
  extension) run at even the full Part 53 pace lands ~Sep 2027 — inside the
  window with margin. Missing end-2027 requires running >25% slower than Part
  53 on a much narrower rule, or a rework/litigation event.

Recalibration outcome: P(Part 57 final by end-2027) nudged 0.90 → 0.91 (the
Part 53 calibration slightly outweighs the 7-for-7 downgrade at this horizon),
while the *near-term timing* mass was cut (cumulative by end-Jan 2027: 0.55 →
0.45 — the administrative record says little about a novel framework hitting a
7-month target). The combined P(YES) is **essentially insensitive to this**
(93.99 vs 93.98 before): with three semi-independent shots, the endpoint is
dominated by the common-mode gate, not by Part 57's exact month. The archived
tier-3 79% priced "slippage and litigation" as one large subtraction from a
single blended timeline; holding it requires believing common-mode risk is
~3–4× the evidence-backed level.

### Provenance of the common-mode gate — and why the result is a band (2026-07-23)

Because P(all three pathways fail idiosyncratically) is ~0.01%, **P(YES) ≈
1 − S**: the 6% gate is essentially the entire answer, which makes its
provenance the decisive question. Audited answer: **the 6% is a reasoned
judgment calibration from the 2026-07-22 research pass, informed by real
cited evidence but NOT a counted base rate** — no historical frequency of
"EO-priority multi-pathway regulatory programs derailed program-wide within 18
months" exists to count, and the parameter was carried into the reconciliation
unrevised. What real data *does* anchor its components (full citations in the
module source):

- **Shutdown stall ≲1%**: 21 appropriations funding gaps since 1977 but only
  three shutdowns ≥3 weeks in ~50 years; the NRC is ~90% fee-funded and
  demonstrably kept EO work going through the Oct–Nov 2025 shutdown on
  carryover — stalling all pathways past end-2027 needs an unprecedented
  multi-month, carryover-exhausting lapse.
- **Program-wide pre-finalization injunction ~1–3%**: no suit pending against
  EO 14300 / Part 53 / Part 57 / the pilot program (searched 2026-07-22,
  re-verified 2026-07-23); post-finalization APA challenges do not undo
  "formally finalized"; three separate finalization vehicles would all need
  freezing.
- **Priority reversal / commission incapacity ~1–2%**: no presidential
  transition inside the window; the Jun 2025 Hanson firing was absorbed with a
  full commission reconstituted by Jan 2026.
- **Agenda-freezing test-reactor accident <0.5%**: worldwide core-damage
  frequency scaled to a handful of micro test reactors over 17 months.

Component sum ≈ 3–6.5%; the 6% central sits at its top (conservative). Since
the components are order-of-magnitude anchors rather than counted frequencies,
the model now reports a **gate-sensitivity band as its primary output**:

| Gate S | P(YES) |
|---|---|
| 0.03 (optimistic component sum) | **97.0%** |
| 0.06 (central calibration) | **94.0%** — persisted value |
| 0.12 (doubled, for common-mode correlation beyond a single gate — e.g. the two NRC rules sharing staffing/OIRA/rework risk) | **88.0%** |

**The honest statement of forecast #10 is 88–97%, central 94.0%** (the state
file stores the central point; the module, TUI, and this file always present
the band with it). Note the band's floor still sits 9pp above the archived
79%: the adoption decision survives the most conservative defensible gate.
