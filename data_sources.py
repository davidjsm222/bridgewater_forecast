"""Live public-data pulls used by forecasts #1, #4, #6, and #9.

Every pull is cache-first and writes a timestamped, cleaned JSON document to
``data_cache/``. API responses are never replaced with estimates or synthetic
values. Set ``FRED_API_KEY`` and ``EIA_API_KEY`` in the environment for the
keyed sources.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv()


PROJECT_DIR = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_DIR / "data_cache"
DEFAULT_CACHE_HOURS = 24.0

FRED_API_BASE = "https://api.stlouisfed.org/fred"
FRED_PCE_SERIES_ID = "PCEPI"
FRED_INFORMATION_PROCESSING_SERIES_ID = "A679RX1Q020SBEA"
FRED_INFORMATION_PROCESSING_GDP_CONTRIBUTION_SERIES = (
    "B985RY2A224NBEA",  # software
    "B935RY2A224NBEA",  # computers and peripheral equipment
    "A937RY2A224NBEA",  # other information processing equipment
    # Physical buildout. NOTE: this is TOTAL nonresidential structures, the
    # deepest structures node BEA publishes as a GDP-growth contribution -- BEA
    # does NOT break out data-center (or even commercial) structures in the
    # contributions framework, so this sweeps in manufacturing, power/comms,
    # and mining structures that are unrelated to AI. See gdp_contribution_notes.
    "A009RY2A224NBEA",  # nonresidential structures (total)
)
FRED_API_KEY_SIGNUP = "https://fred.stlouisfed.org/docs/api/api_key.html"

EIA_API_URL = "https://api.eia.gov/v2/electricity/retail-sales/data/"
EIA_API_KEY_SIGNUP = "https://www.eia.gov/opendata/register.php"
EIA_STATE_ID = "VA"
EIA_STATE_NAME = "Virginia"
# COMMERCIAL sector, not all-sector: data centers are commercial/industrial customers,
# so commercial-rate movement is the honest signal for "is AI/data-center demand raising
# prices," versus residential rates (moving for different, more insulated reasons) or a
# blended all-sector figure. See forecast #9 criteria and methodology_notes.md #9.
EIA_SECTOR_ID = "COM"

FEDERAL_REGISTER_API_URL = "https://www.federalregister.gov/api/v1/documents.json"
FEDERAL_REGISTER_START = "2022-01-01"
FEDERAL_REGISTER_END = "2026-12-31"

CACHE_FILES = {
    "pce": CACHE_DIR / "fred_pcepi.json",
    "investment": CACHE_DIR / "fred_information_processing_investment.json",
    "electricity": CACHE_DIR / "eia_virginia_retail_electricity.json",
    "bis": CACHE_DIR / "federal_register_bis_export_controls.json",
}


class DataSourceError(RuntimeError):
    """Raised when a public data source cannot return a usable response."""


class MissingAPIKeyError(DataSourceError):
    """Raised when a keyed public API has not been configured."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _require_key(variable: str, signup_url: str, supplied: str | None = None) -> str:
    key = supplied or os.environ.get(variable)
    if key:
        return key
    raise MissingAPIKeyError(
        f"{variable} is not configured. Register for a free key at {signup_url} "
        f"and export it as {variable}."
    )


def _read_fresh_cache(path: Path, max_age_hours: float, force: bool) -> dict[str, Any] | None:
    if force or not path.exists():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        retrieved = datetime.fromisoformat(cached["retrieved_at_utc"].replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None
    age_hours = (_utc_now() - retrieved).total_seconds() / 3600
    return cached if age_hours <= max_age_hours else None


def _write_cache(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _get_json(url: str, params: list[tuple[str, str]] | dict[str, str]) -> dict[str, Any]:
    query = urlencode(params)
    request = Request(
        f"{url}?{query}",
        headers={"Accept": "application/json", "User-Agent": "bridgewater-forecast/0.1"},
    )
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise DataSourceError(f"{url} returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise DataSourceError(f"Could not reach {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DataSourceError(f"{url} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise DataSourceError(f"{url} returned an unexpected JSON structure")
    if "error_code" in payload or "error_message" in payload:
        raise DataSourceError(f"{url} API error: {payload.get('error_message', payload)}")
    return payload


def _fred_payload(series_id: str, observation_start: str, api_key: str) -> tuple[dict, list[dict]]:
    common = {"api_key": api_key, "file_type": "json", "series_id": series_id}
    metadata_response = _get_json(f"{FRED_API_BASE}/series", common)
    observations_response = _get_json(
        f"{FRED_API_BASE}/series/observations",
        common | {"observation_start": observation_start, "sort_order": "asc"},
    )
    series = metadata_response.get("seriess", [])
    observations = observations_response.get("observations", [])
    if len(series) != 1 or not isinstance(observations, list):
        raise DataSourceError(f"FRED returned no usable data for series {series_id}")
    return series[0], observations


def pull_pce_inflation(
    *, force: bool = False, max_age_hours: float = DEFAULT_CACHE_HOURS, api_key: str | None = None
) -> dict[str, Any]:
    """Pull PCEPI and calculate exact month-over-same-month-year-ago inflation."""
    cache = _read_fresh_cache(CACHE_FILES["pce"], max_age_hours, force)
    if cache is not None:
        return cache
    key = _require_key("FRED_API_KEY", FRED_API_KEY_SIGNUP, api_key)
    metadata, raw = _fred_payload(FRED_PCE_SERIES_ID, "2015-01-01", key)
    values: dict[str, float] = {}
    missing_dates: list[str] = []
    for observation in raw:
        try:
            value = float(observation["value"])
        except (KeyError, TypeError, ValueError):
            missing_dates.append(str(observation.get("date", "unknown")))
            continue
        if math.isfinite(value):
            values[observation["date"]] = value

    clean = []
    for date, value in values.items():
        year, month, day = map(int, date.split("-"))
        previous_date = f"{year - 1:04d}-{month:02d}-{day:02d}"
        previous = values.get(previous_date)
        yoy = None if previous is None or previous == 0 else (value / previous - 1) * 100
        clean.append(
            {
                "date": date,
                "index_value": value,
                "year_over_year_pct": None if yoy is None else round(yoy, 6),
            }
        )

    return _write_cache(
        CACHE_FILES["pce"],
        {
            "schema_version": 1,
            "forecast_id": 6,
            "retrieved_at_utc": _timestamp(),
            "source": "Federal Reserve Bank of St. Louis FRED API",
            "source_url": f"https://fred.stlouisfed.org/series/{FRED_PCE_SERIES_ID}",
            "series": {
                "id": metadata.get("id"),
                "title": metadata.get("title"),
                "frequency": metadata.get("frequency"),
                "units": metadata.get("units"),
                "seasonal_adjustment": metadata.get("seasonal_adjustment"),
            },
            "calculation": "100 * (PCEPI_t / PCEPI_t_minus_12_months - 1)",
            "observations": clean,
            "source_missing_observation_dates": missing_dates,
        },
    )


def pull_information_processing_investment(
    *, force: bool = False, max_age_hours: float = DEFAULT_CACHE_HOURS, api_key: str | None = None
) -> dict[str, Any]:
    """Pull the BEA/FRED real information-processing equipment/software series."""
    cache = _read_fresh_cache(CACHE_FILES["investment"], max_age_hours, force)
    if cache is not None:
        return cache
    key = _require_key("FRED_API_KEY", FRED_API_KEY_SIGNUP, api_key)
    metadata, raw = _fred_payload(FRED_INFORMATION_PROCESSING_SERIES_ID, "2016-01-01", key)
    clean = []
    missing_dates = []
    for observation in raw:
        try:
            value = float(observation["value"])
        except (KeyError, TypeError, ValueError):
            missing_dates.append(str(observation.get("date", "unknown")))
            continue
        if math.isfinite(value):
            clean.append({"date": observation["date"], "value": value})

    contribution_metadata = []
    contribution_values: dict[str, dict[str, float]] = {}
    for series_id in FRED_INFORMATION_PROCESSING_GDP_CONTRIBUTION_SERIES:
        component_metadata, component_raw = _fred_payload(series_id, "2016-01-01", key)
        contribution_metadata.append(
            {
                "id": component_metadata.get("id"),
                "title": component_metadata.get("title"),
                "frequency": component_metadata.get("frequency"),
                "units": component_metadata.get("units"),
                "seasonal_adjustment": component_metadata.get("seasonal_adjustment"),
            }
        )
        for observation in component_raw:
            try:
                value = float(observation["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(value):
                contribution_values.setdefault(observation["date"], {})[series_id] = value

    contribution_observations = []
    required_components = set(FRED_INFORMATION_PROCESSING_GDP_CONTRIBUTION_SERIES)
    for date, components in sorted(contribution_values.items()):
        if set(components) != required_components:
            continue
        contribution_observations.append(
            {
                "date": date,
                "component_percentage_points": components,
                "total_percentage_points_at_annual_rate": round(sum(components.values()), 6),
            }
        )

    return _write_cache(
        CACHE_FILES["investment"],
        {
            "schema_version": 1,
            "forecast_id": 4,
            "retrieved_at_utc": _timestamp(),
            "source": "U.S. Bureau of Economic Analysis via FRED API",
            "source_url": f"https://fred.stlouisfed.org/series/{FRED_INFORMATION_PROCESSING_SERIES_ID}",
            "series": {
                "id": metadata.get("id"),
                "title": metadata.get("title"),
                "frequency": metadata.get("frequency"),
                "units": metadata.get("units"),
                "seasonal_adjustment": metadata.get("seasonal_adjustment"),
            },
            "observations": clean,
            "source_missing_observation_dates": missing_dates,
            "gdp_contribution_components": contribution_metadata,
            "gdp_contribution_calculation": (
                "Sum of BEA contributions to real GDP growth from software, computers/peripherals, "
                "other information-processing equipment, and total nonresidential structures; "
                "150 basis points equals 1.5 percentage points."
            ),
            "gdp_contribution_notes": (
                "Structures uses total nonresidential structures (A009RY2A224NBEA): BEA publishes "
                "no data-center-specific or commercial-only structures contribution in the "
                "contributions-to-real-GDP framework. This total therefore includes manufacturing, "
                "power/communication, and mining structures unrelated to AI capex, so it OVERSTATES "
                "the AI/data-center physical buildout. Treat the structures component as an upper "
                "bound on the buildout contribution, not a clean data-center measure."
            ),
            "gdp_contribution_observations": contribution_observations,
        },
    )


def pull_virginia_electricity_prices(
    *, force: bool = False, max_age_hours: float = DEFAULT_CACHE_HOURS, api_key: str | None = None
) -> dict[str, Any]:
    """Pull Virginia monthly COMMERCIAL-sector retail electricity prices from EIA."""
    cache = _read_fresh_cache(CACHE_FILES["electricity"], max_age_hours, force)
    if cache is not None:
        return cache
    key = _require_key("EIA_API_KEY", EIA_API_KEY_SIGNUP, api_key)
    response = _get_json(
        EIA_API_URL,
        [
            ("api_key", key),
            ("frequency", "monthly"),
            ("data[0]", "price"),
            ("facets[stateid][]", EIA_STATE_ID),
            ("facets[sectorid][]", EIA_SECTOR_ID),
            ("start", "2016-01"),
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "asc"),
            ("offset", "0"),
            ("length", "5000"),
        ],
    )
    response_body = response.get("response", {})
    rows = response_body.get("data", [])
    if not isinstance(rows, list):
        raise DataSourceError("EIA returned no usable Virginia retail-price data")
    observations = []
    for row in rows:
        try:
            price = float(row["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(price):
            observations.append(
                {
                    "period": row["period"],
                    "price_cents_per_kwh": price,
                    "state": row.get("stateDescription"),
                    "sector": row.get("sectorName"),
                }
            )
    # Baseline is the MOST RECENT actual commercial-sector observation (not a fixed
    # calendar month): the forecast asks whether commercial prices rise >15% above the
    # current level by the resolution date.
    baseline = observations[-1] if observations else None
    baseline_status = (
        "most recent actual EIA commercial-sector observation"
        if baseline is not None
        else "no usable commercial-sector observations returned"
    )
    return _write_cache(
        CACHE_FILES["electricity"],
        {
            "schema_version": 1,
            "forecast_id": 9,
            "retrieved_at_utc": _timestamp(),
            "source": "U.S. Energy Information Administration Open Data API",
            "source_url": EIA_API_URL,
            "region_choice": {
                "state_id": EIA_STATE_ID,
                "state": EIA_STATE_NAME,
                "sector_id": EIA_SECTOR_ID,
                "rationale": (
                    "Virginia is a data-center-heavy state; the commercial-sector retail price is "
                    "the honest signal for data-center-driven cost pass-through (data centers are "
                    "commercial/industrial customers), versus residential or blended all-sector rates."
                ),
            },
            "series_description": response_body.get("description"),
            "baseline_period": baseline["period"] if baseline else None,
            "baseline": baseline,
            "baseline_status": baseline_status,
            "observations": observations,
        },
    )


def pull_bis_export_control_rules(
    *, force: bool = False, max_age_hours: float = DEFAULT_CACHE_HOURS
) -> dict[str, Any]:
    """Pull final BIS rules and retain Entity List/EAR changes from 2022-2026."""
    cache = _read_fresh_cache(CACHE_FILES["bis"], max_age_hours, force)
    if cache is not None:
        return cache
    response = _get_json(
        FEDERAL_REGISTER_API_URL,
        [
            ("per_page", "1000"),
            ("order", "oldest"),
            ("conditions[agencies][]", "industry-and-security-bureau"),
            ("conditions[publication_date][gte]", FEDERAL_REGISTER_START),
            ("conditions[publication_date][lte]", FEDERAL_REGISTER_END),
            ("conditions[type][]", "RULE"),
        ],
    )
    raw_results = response.get("results", [])
    if not isinstance(raw_results, list):
        raise DataSourceError("Federal Register returned no usable BIS rule data")

    patterns = {
        "Entity List": re.compile(r"\bentity list\b", re.IGNORECASE),
        "Export Administration Regulations": re.compile(
            r"\bexport administration regulations?\b", re.IGNORECASE
        ),
    }
    rules = []
    for result in raw_results:
        searchable = " ".join(
            str(result.get(field) or "") for field in ("title", "abstract", "excerpts")
        )
        matched = [label for label, pattern in patterns.items() if pattern.search(searchable)]
        if not matched:
            continue
        rules.append(
            {
                "publication_date": result.get("publication_date"),
                "document_number": result.get("document_number"),
                "title": result.get("title"),
                "type": result.get("type"),
                "abstract": result.get("abstract"),
                "html_url": result.get("html_url"),
                "matched_filters": matched,
            }
        )
    counts_by_year = Counter(rule["publication_date"][:4] for rule in rules if rule["publication_date"])
    return _write_cache(
        CACHE_FILES["bis"],
        {
            "schema_version": 1,
            "forecast_id": 1,
            "retrieved_at_utc": _timestamp(),
            "source": "Federal Register API",
            "source_url": FEDERAL_REGISTER_API_URL,
            "query": {
                "agency": "Industry and Security Bureau",
                "document_type": "Rule",
                "publication_date_start": FEDERAL_REGISTER_START,
                "publication_date_end": FEDERAL_REGISTER_END,
                "local_text_filters": list(patterns),
            },
            "api_rule_count_before_text_filter": response.get("count"),
            "matched_rule_count": len(rules),
            "matched_rule_counts_by_publication_year": dict(sorted(counts_by_year.items())),
            "rules": rules,
            "methodology_note": (
                "Counts are publication events, not a forecast probability. Review rule substance and define "
                "the reference-class denominator before turning these records into a base rate."
            ),
        },
    )


PULLERS = {
    "pce": pull_pce_inflation,
    "investment": pull_information_processing_investment,
    "electricity": pull_virginia_electricity_prices,
    "bis": pull_bis_export_control_rules,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache real public API data for supported forecasts")
    parser.add_argument("sources", nargs="*", choices=sorted(PULLERS), default=list(PULLERS))
    parser.add_argument("--force", action="store_true", help="ignore fresh caches and fetch again")
    parser.add_argument(
        "--cache-hours", type=float, default=DEFAULT_CACHE_HOURS, help="cache freshness window"
    )
    args = parser.parse_args()
    failures = 0
    for name in args.sources:
        try:
            payload = PULLERS[name](force=args.force, max_age_hours=args.cache_hours)
            print(f"{name}: {CACHE_FILES[name]} ({payload['retrieved_at_utc']})")
        except DataSourceError as exc:
            failures += 1
            print(f"{name}: ERROR: {exc}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
