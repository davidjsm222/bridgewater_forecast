# Methodology notes

Per-forecast notes on modeling choices, data limitations, and how to read the
numbers. These are qualitative caveats meant to travel with the quantitative
outputs in `forecast_state.json`.

## Forecast #1 — Does the US tighten export controls on next-gen AI chips to China?

**Authoritative probability: 90% (YES = BIS tightens China advanced-chip
restrictions at some point in the window; NO = relaxed/unchanged), from a tier 3
reference-class / base-rate-plus-adjustments estimate.** The earlier 55%
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

## Forecast #3 — Does the US 2027 data-center capacity shortfall close to <30%?

**Authoritative probability: 4% (YES = independent tracking shows the 2027
not-yet-under-construction gap below 30%; NO if the flagged 60%+ persists/widens),
from a tier 3 reference-class / base-rate-plus-adjustments estimate — a qualitative
call.** Reframed from a tier-2 trend fit (same move as #4 and #6) because the real
data cannot support a trustworthy fit.

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

**Authoritative probability: 14% (YES = strict-scope cumulative public-sector
commitment to non-US/non-China sovereign AI compute/chip infrastructure reaches
$250B by Dec 31, 2026), from a tier 3 reference-class / base-rate-plus-adjustments
estimate.** A **reframe** from the old open-ended "does any non-US/non-China
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

## Forecast #9 — Does Virginia's commercial electricity rate decrease within 6 months (by 2027-01-21)?

**Authoritative probability: 30% (YES = the EIA commercial-sector VA rate is below
the current 10.33 ¢/kWh baseline at the 2027-01-21 resolution date; NO if flat or
higher), from a tier 3 reference-class / base-rate-plus-adjustments estimate.**
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

## Forecast #10 — Does NRC/DOE finalize an expedited nuclear/SMR licensing or permitting action by year-end 2027?

**Authoritative probability: 79% (YES = at least one of three specified
EO-accelerated federal nuclear-licensing/permitting actions is formally *finalized*
— not merely proposed — by Dec 31, 2027), from a tier 3 reference-class /
base-rate-plus-adjustments estimate.** The resolution criteria were made explicit
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
