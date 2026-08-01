# Bridgewater Forecasting the Future -- Model

## Setup
```
pip install -e . --break-system-packages
```

## Run the TUI
```
forecast
```
Controls: arrow keys navigate, Enter opens detail, `m` from a detail view opens
that forecast's model screen, `p` edits probability, and `q` quits.

## Structure
- `data_sources.py` -- cache-first FRED, EIA, and Federal Register API pulls
- `forecasts.py` -- the 10 forecasts, resolution dates/criteria, tier tags
- `tier1_market.py` -- Fed posture HMM + Monte Carlo (forecast #5), legacy chaining/threshold helpers
- `fomc_history.py` -- the 2016-2026 FOMC meeting history and SEP-derived posture labeling that trains the #5 HMM
- `tier2_trend.py` -- shared linear-trend / Student-t fit machinery, plus the archived tier-2
  fits for #4 and #6 (both since reframed to tier-3 estimates; neither fit persists anything).
  #6 additionally carries a live Bayesian likelihood-ratio arm in `bayesian_update.py`.
  #3's abandoned fit is archived as a commented config in `tui.py`, not here.
- `tier3_judgment.py` -- reference-class base rate + named adjustment factors (all layered forecasts)

Quantitative process models (each runnable standalone, `python3 <module>.py`;
persistence only with an explicit `--persist` flag):
- `export_controls_poisson.py` -- forecast #1: Poisson point process fit to the audited
  China-chip tightening actions in the cached Federal Register docket
- `nuclear_competing_risks.py` -- forecast #10: three-pathway competing-risks model with a
  common-mode derailment factor
- `sovereign_ai_jumps.py` -- forecast #7: compound Poisson Monte Carlo over sovereign AI
  commitment arrivals and lognormal jump sizes
- `electricity_simulation.py` -- forecast #9: deterministic Dominion base-rate schedule +
  Ornstein-Uhlenbeck Henry Hub simulation mapped through fuel-factor pass-through
- `datacenter_backlog.py` -- forecast #3: announced-vs-under-construction backlog/throughput
  projection under interconnection and equipment constraints
- `bayesian_update.py` -- forecasts #4/#6: the tier 3 adjustment factors recombined as an
  explicit likelihood-ratio Bayesian update (forecasts #2/#8 stay judgment-anchored by
  design; see methodology_notes.md)

## Persistence conventions
`forecast_state.json` holds every forecast's authoritative probability plus the
`_model_state` model configs the TUI edits. The newer quantitative modules
(`export_controls_poisson.py`, `nuclear_competing_risks.py`,
`sovereign_ai_jumps.py`, `electricity_simulation.py`, `datacenter_backlog.py`,
`bayesian_update.py`) only PRINT on a plain run; they write the state file only
with an explicit `--persist` flag, because several of them intentionally
disagree with the persisted judgment number (each prints a divergence note; see
methodology_notes.md for which divergences are flagged-but-not-adopted).
`tier1_market.py` follows the same convention: a plain run only prints, and
`--persist` writes forecast #5's pure-HMM Monte Carlo output (62.6%; the tier-3
market-blend layer that used to sit on top was retired 2026-07-29 -- see
methodology_notes.md #5). Because #5 is now defined by a single layer, the
persistence guard refuses when a tier-3 blend config for #5 has REAPPEARED in
the state file (two layers each claiming to define one forecast) or when the
state file is absent -- the inverse of the original guard, which protected the
blend from the raw HMM.

`tier2_trend.py` and `tier3_judgment.py` are print-only on any run (the example
scaffold in `tier3_judgment.py` that once persisted #1 unconditionally was
fixed 2026-07-31). All modules were audited plain-run-clean against a
state-file hash on 2026-07-31/08-01.

The `ReferenceClassEstimate.print_table()` output in `tier3_judgment.py`
mirrors the per-forecast methodology tables in `methodology_notes.md` -- base
rate, named adjustments, final number, all visible.

## Live public data

`data_sources.py` writes cleaned, timestamped JSON files to `data_cache/` and
reuses them for 24 hours by default:

```sh
python3 data_sources.py
python3 data_sources.py bis --force
```

FRED and EIA require free API keys:

- Request a FRED key at https://fred.stlouisfed.org/docs/api/api_key.html and set `FRED_API_KEY`.
- Register for an EIA key at https://www.eia.gov/opendata/register.php and set `EIA_API_KEY`.

For example:

```sh
export FRED_API_KEY="your-key"
export EIA_API_KEY="your-key"
```

The EIA source defines the forecast #9 baseline as the most recent Virginia
COMMERCIAL-sector monthly observation (July 2026, 10.33 cents/kWh), the latest
actual published before the submission deadline (see
`data_cache/eia_virginia_retail_electricity.json`, `baseline_period` 2026-07).

## Trend uncertainty correction (archived tier-2 machinery)

No persisted probability resolves on a tier-2 trend fit any more -- #3, #4 and
#6 were all reframed away from trend extrapolation (see methodology_notes.md
for each decision). The machinery below stays in `tier2_trend.py` because the
archived fits are kept runnable for the record; this section documents how
their uncertainty bands were built.

The archived tier-2 probabilities do not treat the in-sample regression
residual as the complete forecast error. The calculation uses
`max(in-sample residual std, expanding-window one-step RMSE)` as its base,
multiplies it by the standard linear-regression future-prediction factor, and
applies an additional `sqrt(8/n)` scale penalty when fewer than eight points
are available. Threshold probabilities use Student-t tails with `n - 2`
degrees of freedom. This widens uncertainty for validation misses, forecast
horizon, fitted-parameter uncertainty, and small samples without imposing an
arbitrary minimum or maximum probability.
