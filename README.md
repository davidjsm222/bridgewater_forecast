# Bridgewater Forecasting the Future -- Model

## Setup
```
pip install -e . --break-system-packages
```

## Run the TUI
```
forecast
```
Controls: arrow keys navigate, Enter opens detail, `p` edits probability, and `q` quits.

## Structure
- `data_sources.py` -- cache-first FRED, EIA, and Federal Register API pulls
- `manual_research.py` -- empty, structured research templates for forecasts without clean APIs
- `forecasts.py` -- the 10 forecasts, resolution dates/criteria, tier tags
- `tier1_market.py` -- Fed posture HMM + Monte Carlo (forecast #5), legacy chaining/threshold helpers
- `tier2_trend.py` -- linear trend fit + sigma-distance-to-threshold (archived fits for #3, #4, #6)
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
`--persist` writes the market-BLENDED forecast #5 value (raw HMM output plus
the stored tier-3 adjustment layer), refusing if the blend config is missing.

The `ReferenceClassEstimate.print_table()` output in `tier3_judgment.py` is
close to what should land in the appendix's methodology table -- base rate,
named adjustments, final number, all visible.

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

## Trend uncertainty correction

Tier 2 probabilities do not treat the in-sample regression residual as the
complete forecast error. The calculation uses
`max(in-sample residual std, expanding-window one-step RMSE)` as its base,
multiplies it by the standard linear-regression future-prediction factor, and
applies an additional `sqrt(8/n)` scale penalty when fewer than eight points
are available. Threshold probabilities use Student-t tails with `n - 2`
degrees of freedom. This widens uncertainty for validation misses, forecast
horizon, fitted-parameter uncertainty, and small samples without imposing an
arbitrary minimum or maximum probability.
