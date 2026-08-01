"""
Tier 3: Structural/policy judgment calls.
No clean market or trend signal. The discipline here is reference-class
forecasting: write down a base rate from a named comparable class of events
BEFORE adjusting, then apply explicit, named adjustment factors. This makes
the reasoning legible and arguable instead of a hidden gut number.
"""

from dataclasses import dataclass, field

# NOTE: this module deliberately does NOT import set_forecast_probability.
# Persistence of tier-3 estimates happens in the TUI's editable screens (tui.py)
# or per-forecast model modules behind --persist -- never from this file.


@dataclass
class AdjustmentFactor:
    name: str
    direction: str   # "up" or "down"
    magnitude_pts: float   # percentage points to shift, e.g. 8 = +/-8pp
    rationale: str

    def __post_init__(self):
        if self.direction not in ("up", "down"):
            raise ValueError(
                f"AdjustmentFactor direction must be exactly 'up' or 'down'; got {self.direction!r}"
            )


@dataclass
class ReferenceClassEstimate:
    forecast_id: int
    reference_class: str
    base_rate_pct: float
    base_rate_source: str
    adjustments: list[AdjustmentFactor] = field(default_factory=list)

    def final_probability(self) -> float:
        p = self.base_rate_pct
        for adj in self.adjustments:
            p += adj.magnitude_pts if adj.direction == "up" else -adj.magnitude_pts
        return max(0.0, min(100.0, p))

    def print_table(self):
        print(f"\nForecast #{self.forecast_id}")
        print(f"Reference class: {self.reference_class}")
        print(f"Base rate: {self.base_rate_pct}% (source: {self.base_rate_source})")
        for adj in self.adjustments:
            sign = "+" if adj.direction == "up" else "-"
            print(f"  {sign}{adj.magnitude_pts}pp  {adj.name} -- {adj.rationale}")
        print(f"Final estimate: {self.final_probability()}%")


if __name__ == "__main__":
    # Example scaffold for forecast #1 (chip export controls) -- ILLUSTRATIVE
    # ONLY. The real #1 estimate is the Poisson model (export_controls_poisson.py,
    # 87.1%) with its audited tier-3 config in forecast_state.json; this stale
    # placeholder (55% base) exists to demo the ReferenceClassEstimate API.
    # FIXED 2026-07-31: this block used to call set_forecast_probability(1, ...)
    # unconditionally, so a plain `python3 tier3_judgment.py` clobbered #1's
    # persisted 87.1% with the placeholder's 60.0 -- the same plain-run-must-
    # not-write bug class as the original tier1_market #5 clobber. Plain runs
    # now only print; this scaffold never persists (there is deliberately no
    # --persist path here, because this config is not a real estimate).
    example = ReferenceClassEstimate(
        forecast_id=1,
        reference_class="US export control tightening actions on China-bound advanced chips, 2022-2026",
        base_rate_pct=55.0,
        base_rate_source="placeholder -- pull actual frequency of BIS tightening actions per 6mo window since 2022",
    )
    example.adjustments.append(AdjustmentFactor(
        name="Bipartisan political momentum",
        direction="up",
        magnitude_pts=10,
        rationale="mercantilist trade posture has bipartisan support per Bridgewater's own framing",
    ))
    example.adjustments.append(AdjustmentFactor(
        name="Existing controls already near-maximal",
        direction="down",
        magnitude_pts=5,
        rationale="less remaining room to tighten further without a new triggering event",
    ))
    example.print_table()
    print(
        "(example scaffold only -- not persisted; forecast #1's authoritative "
        "number comes from export_controls_poisson.py)"
    )
