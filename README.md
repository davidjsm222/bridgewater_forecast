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
- `tier1_market.py` -- Fed hike-probability chaining, PCE trend threshold check, electricity price check (forecasts #5, #6, #9)
- `tier2_trend.py` -- linear trend fit + sigma-distance-to-threshold (forecasts #3, #4)
- `tier3_judgment.py` -- reference-class base rate + named adjustment factors (forecasts #1, #2, #7, #8, #10)

## Before using for real numbers
All three tier modules currently run on **placeholder data** in their
`if __name__ == "__main__":` blocks. Before generating the actual submission
numbers, replace those placeholders with:
- Tier 1: live CME FedWatch probabilities per remaining 2026 meeting, current PCE trend, EIA regional price series
- Tier 2: real DC Byte/CBRE/JLL data center capacity reports, BEA nonresidential investment data
- Tier 3: actual historical base rates for each reference class (export control actions, strategic reserve announcements, sovereign AI programs, etc.)

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

The EIA source defines the forecast #9 baseline as the exact Virginia April
2026 monthly observation (12.11 cents/kWh), the latest observation published
before the submission deadline.

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
