"""Official-source FOMC history used to estimate the Tier 1 posture HMM.

Regular meeting decisions come from Federal Reserve FOMC statements. Median
federal-funds-rate dots come from the Fed's SEP tables. Non-SEP meetings carry
forward the most recent SEP, as documented in ``build_history``.
"""

from dataclasses import dataclass
from datetime import date


POSTURE_STATES = ("hawkish_bias", "neutral_hold", "dovish_bias")
ACTIONS = ("hike", "hold", "cut")
ROUGHLY_FLAT_THRESHOLD_BPS = 25.0
DAYS_PER_MONTH = 365.2425 / 12
FOMC_CALENDAR_SOURCE = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


@dataclass(frozen=True)
class FOMCMeetingHistory:
    meeting_date: str
    action: str
    target_midpoint: float
    sep_as_of_date: str
    median_dot_year: int
    median_dot_rate: float
    annualized_change_bps: float
    posture: str
    statement_source_url: str
    sep_source_url: str


# Known simplification: 2016-2026 spans multiple rate regimes (near-zero in
# 2016-19, hiking in 2022-23, and the current regime), but they are pooled into
# one transition/emission estimate; flag this limitation in any writeup.
# (meeting date, action in that meeting's statement, post-decision target midpoint)
_RAW_MEETINGS = (
    ("2016-01-27", "hold", 0.375),
    ("2016-03-16", "hold", 0.375),
    ("2016-04-27", "hold", 0.375),
    ("2016-06-15", "hold", 0.375),
    ("2016-07-27", "hold", 0.375),
    ("2016-09-21", "hold", 0.375),
    ("2016-11-02", "hold", 0.375),
    ("2016-12-14", "hike", 0.625),
    ("2017-02-01", "hold", 0.625),
    ("2017-03-15", "hike", 0.875),
    ("2017-05-03", "hold", 0.875),
    ("2017-06-14", "hike", 1.125),
    ("2017-07-26", "hold", 1.125),
    ("2017-09-20", "hold", 1.125),
    ("2017-11-01", "hold", 1.125),
    ("2017-12-13", "hike", 1.375),
    ("2018-01-31", "hold", 1.375),
    ("2018-03-21", "hike", 1.625),
    ("2018-05-02", "hold", 1.625),
    ("2018-06-13", "hike", 1.875),
    ("2018-08-01", "hold", 1.875),
    ("2018-09-26", "hike", 2.125),
    ("2018-11-08", "hold", 2.125),
    ("2018-12-19", "hike", 2.375),
    ("2019-01-30", "hold", 2.375),
    ("2019-03-20", "hold", 2.375),
    ("2019-05-01", "hold", 2.375),
    ("2019-06-19", "hold", 2.375),
    ("2019-07-31", "cut", 2.125),
    ("2019-09-18", "cut", 1.875),
    ("2019-10-30", "cut", 1.625),
    ("2019-12-11", "hold", 1.625),
    ("2020-01-29", "hold", 1.625),
    ("2020-04-29", "hold", 0.125),
    ("2020-06-10", "hold", 0.125),
    ("2020-07-29", "hold", 0.125),
    ("2020-09-16", "hold", 0.125),
    ("2020-11-05", "hold", 0.125),
    ("2020-12-16", "hold", 0.125),
    ("2021-01-27", "hold", 0.125),
    ("2021-03-17", "hold", 0.125),
    ("2021-04-28", "hold", 0.125),
    ("2021-06-16", "hold", 0.125),
    ("2021-07-28", "hold", 0.125),
    ("2021-09-22", "hold", 0.125),
    ("2021-11-03", "hold", 0.125),
    ("2021-12-15", "hold", 0.125),
    ("2022-01-26", "hold", 0.125),
    ("2022-03-16", "hike", 0.375),
    ("2022-05-04", "hike", 0.875),
    ("2022-06-15", "hike", 1.625),
    ("2022-07-27", "hike", 2.375),
    ("2022-09-21", "hike", 3.125),
    ("2022-11-02", "hike", 3.875),
    ("2022-12-14", "hike", 4.375),
    ("2023-02-01", "hike", 4.625),
    ("2023-03-22", "hike", 4.875),
    ("2023-05-03", "hike", 5.125),
    ("2023-06-14", "hold", 5.125),
    ("2023-07-26", "hike", 5.375),
    ("2023-09-20", "hold", 5.375),
    ("2023-11-01", "hold", 5.375),
    ("2023-12-13", "hold", 5.375),
    ("2024-01-31", "hold", 5.375),
    ("2024-03-20", "hold", 5.375),
    ("2024-05-01", "hold", 5.375),
    ("2024-06-12", "hold", 5.375),
    ("2024-07-31", "hold", 5.375),
    ("2024-09-18", "cut", 4.875),
    ("2024-11-07", "cut", 4.625),
    ("2024-12-18", "cut", 4.375),
    ("2025-01-29", "hold", 4.375),
    ("2025-03-19", "hold", 4.375),
    ("2025-05-07", "hold", 4.375),
    ("2025-06-18", "hold", 4.375),
    ("2025-07-30", "hold", 4.375),
    ("2025-09-17", "cut", 4.125),
    ("2025-10-29", "cut", 3.875),
    ("2025-12-10", "cut", 3.625),
    ("2026-01-28", "hold", 3.625),
    ("2026-03-18", "hold", 3.625),
    ("2026-04-29", "hold", 3.625),
    ("2026-06-17", "hold", 3.625),
)


# (SEP date, {year-end: median target midpoint}, official SEP source URL)
_SEP_MEDIANS = (
    ("2015-12-16", {2015: 0.4, 2016: 1.4, 2017: 2.4, 2018: 3.3}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20151216.htm"),
    ("2016-03-16", {2016: 0.9, 2017: 1.9, 2018: 3.0}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20160316.htm"),
    ("2016-06-15", {2016: 0.9, 2017: 1.6, 2018: 2.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20160615.htm"),
    ("2016-09-21", {2016: 0.6, 2017: 1.1, 2018: 1.9, 2019: 2.6}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20160921.htm"),
    ("2016-12-14", {2016: 0.6, 2017: 1.4, 2018: 2.1, 2019: 2.9}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20161214.htm"),
    ("2017-03-15", {2017: 1.4, 2018: 2.1, 2019: 3.0}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20170315.htm"),
    ("2017-06-14", {2017: 1.4, 2018: 2.1, 2019: 2.9}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20170614.htm"),
    ("2017-09-20", {2017: 1.4, 2018: 2.1, 2019: 2.7, 2020: 2.9}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20170920.htm"),
    ("2017-12-13", {2017: 1.4, 2018: 2.1, 2019: 2.7, 2020: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20171213.htm"),
    ("2018-03-21", {2018: 2.1, 2019: 2.9, 2020: 3.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20180321.htm"),
    ("2018-06-13", {2018: 2.4, 2019: 3.1, 2020: 3.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20180613.htm"),
    ("2018-09-26", {2018: 2.4, 2019: 3.1, 2020: 3.4, 2021: 3.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20180926.htm"),
    ("2018-12-19", {2018: 2.4, 2019: 2.9, 2020: 3.1, 2021: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20181219.htm"),
    ("2019-03-20", {2019: 2.4, 2020: 2.6, 2021: 2.6}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20190320.htm"),
    ("2019-06-19", {2019: 2.4, 2020: 2.1, 2021: 2.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20190619.htm"),
    ("2019-09-18", {2019: 1.9, 2020: 1.9, 2021: 2.1, 2022: 2.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20190918.htm"),
    ("2019-12-11", {2019: 1.6, 2020: 1.6, 2021: 1.9, 2022: 2.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20191211.htm"),
    ("2020-06-10", {2020: 0.1, 2021: 0.1, 2022: 0.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20200610.htm"),
    ("2020-09-16", {2020: 0.1, 2021: 0.1, 2022: 0.1, 2023: 0.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20200916.htm"),
    ("2020-12-16", {2020: 0.1, 2021: 0.1, 2022: 0.1, 2023: 0.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20201216.htm"),
    ("2021-03-17", {2021: 0.1, 2022: 0.1, 2023: 0.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20210317.htm"),
    ("2021-06-16", {2021: 0.1, 2022: 0.1, 2023: 0.6}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20210616.htm"),
    ("2021-09-22", {2021: 0.1, 2022: 0.3, 2023: 1.0, 2024: 1.8}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20210922.htm"),
    ("2021-12-15", {2021: 0.1, 2022: 0.9, 2023: 1.6, 2024: 2.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20211215.htm"),
    ("2022-03-16", {2022: 1.9, 2023: 2.8, 2024: 2.8}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtable20220316.htm"),
    ("2022-06-15", {2022: 3.4, 2023: 3.8, 2024: 3.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20220615.htm"),
    ("2022-09-21", {2022: 4.4, 2023: 4.6, 2024: 3.9, 2025: 2.9}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20220921.htm"),
    ("2022-12-14", {2022: 4.4, 2023: 5.1, 2024: 4.1, 2025: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20221214.htm"),
    ("2023-03-22", {2023: 5.1, 2024: 4.3, 2025: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20230322.htm"),
    ("2023-06-14", {2023: 5.6, 2024: 4.6, 2025: 3.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20230614.htm"),
    ("2023-09-20", {2023: 5.6, 2024: 5.1, 2025: 3.9, 2026: 2.9}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20230920.htm"),
    ("2023-12-13", {2023: 5.4, 2024: 4.6, 2025: 3.6, 2026: 2.9}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20231213.htm"),
    ("2024-03-20", {2024: 4.6, 2025: 3.9, 2026: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20240320.htm"),
    ("2024-06-12", {2024: 5.1, 2025: 4.1, 2026: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20240612.htm"),
    ("2024-09-18", {2024: 4.4, 2025: 3.4, 2026: 2.9, 2027: 2.9}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20240918.htm"),
    ("2024-12-18", {2024: 4.4, 2025: 3.9, 2026: 3.4, 2027: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20241218.htm"),
    ("2025-03-19", {2025: 3.9, 2026: 3.4, 2027: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250319.htm"),
    ("2025-06-18", {2025: 3.9, 2026: 3.6, 2027: 3.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250618.htm"),
    ("2025-09-17", {2025: 3.6, 2026: 3.4, 2027: 3.1, 2028: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250917.htm"),
    ("2025-12-10", {2025: 3.6, 2026: 3.4, 2027: 3.1, 2028: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20251210.htm"),
    ("2026-03-18", {2026: 3.4, 2027: 3.1, 2028: 3.1}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260318.htm"),
    ("2026-06-17", {2026: 3.8, 2027: 3.6, 2028: 3.4}, "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm"),
)


# These are not missing observations: they are deliberately outside the regular
# meeting sequence requested for the approximately eight-meetings-per-year model.
EXCLUDED_NON_REGULAR_EVENTS = (
    ("2019-10-04", "unscheduled conference call; statement released October 11"),
    ("2020-03-02", "unscheduled meeting; statement released March 3"),
    ("2020-03-15", "unscheduled meeting replacing the canceled March 17-18 meeting"),
    ("2020-03-18", "regular meeting canceled; no decision or SEP"),
    ("2020-03-19", "notation vote"),
    ("2020-03-23", "notation vote"),
    ("2020-03-31", "notation vote"),
    ("2020-08-27", "notation vote"),
    ("2025-08-22", "notation vote"),
)


def label_posture(annualized_change_bps: float) -> str:
    if annualized_change_bps > ROUGHLY_FLAT_THRESHOLD_BPS:
        return "hawkish_bias"
    if annualized_change_bps < -ROUGHLY_FLAT_THRESHOLD_BPS:
        return "dovish_bias"
    return "neutral_hold"


def annualized_dot_change_bps(
    as_of_date: date,
    target_midpoint: float,
    median_dot_rate: float,
) -> float:
    year_end = date(as_of_date.year, 12, 31)
    months_to_year_end = (year_end - as_of_date).days / DAYS_PER_MONTH
    if months_to_year_end <= 0:
        raise ValueError("as_of_date must be before its calendar year-end")
    return (median_dot_rate - target_midpoint) / months_to_year_end * 12 * 100


def build_history() -> tuple[tuple[FOMCMeetingHistory, ...], tuple[str, ...]]:
    history = []
    gaps = []
    for meeting_date, action, target_midpoint in _RAW_MEETINGS:
        meeting_day = date.fromisoformat(meeting_date)
        eligible_seps = [sep for sep in _SEP_MEDIANS if sep[0] <= meeting_date]
        if not eligible_seps:
            gaps.append(f"{meeting_date}: no prior SEP available")
            continue
        sep_date, median_dots, sep_source_url = eligible_seps[-1]
        median_dot_rate = median_dots.get(meeting_day.year)
        if median_dot_rate is None:
            gaps.append(f"{meeting_date}: SEP {sep_date} has no {meeting_day.year} median dot")
            continue
        annualized_change = annualized_dot_change_bps(
            meeting_day,
            target_midpoint,
            median_dot_rate,
        )
        statement_key = meeting_date.replace("-", "")
        history.append(FOMCMeetingHistory(
            meeting_date=meeting_date,
            action=action,
            target_midpoint=target_midpoint,
            sep_as_of_date=sep_date,
            median_dot_year=meeting_day.year,
            median_dot_rate=median_dot_rate,
            annualized_change_bps=round(annualized_change, 2),
            posture=label_posture(annualized_change),
            statement_source_url=(
                "https://www.federalreserve.gov/newsevents/pressreleases/"
                f"monetary{statement_key}a.htm"
            ),
            sep_source_url=sep_source_url,
        ))
    return tuple(history), tuple(gaps)


FOMC_HISTORY, DATA_GAPS = build_history()

CURRENT_AS_OF_DATE = date(2026, 7, 16)
CURRENT_TARGET_MIDPOINT = 3.625
CURRENT_SEP_DATE = "2026-06-17"
CURRENT_MEDIAN_DOT_RATE = 3.8
CURRENT_ANNUALIZED_CHANGE_BPS = annualized_dot_change_bps(
    CURRENT_AS_OF_DATE,
    CURRENT_TARGET_MIDPOINT,
    CURRENT_MEDIAN_DOT_RATE,
)
CURRENT_POSTURE = label_posture(CURRENT_ANNUALIZED_CHANGE_BPS)


# SEP PCE inflation projection (Q4/Q4), pulled from the same June 2026 SEP
# projection table as the federal-funds-rate dots above (funds-rate medians on
# that page -- 2026: 3.8, 2027: 3.6, 2028: 3.4 -- match _SEP_MEDIANS, confirming
# the source). This is the evidence anchoring forecast #6's tier-3 base rate.
#
# These are participant point projections (a median, a central tendency, and a
# full range of the 19 participants' individual forecasts), NOT a probability
# distribution over outcomes. They therefore do not by themselves yield a
# P(PCE <= 3.5%); no probability is derived from them.
#
# count_at_or_below_threshold_bound is the number of the 19 participants
# projecting 2026 PCE at or below 3.5%, bounded 4-9: AT LEAST 4 (the 3 lowest
# projections trimmed below the central-tendency floor, plus the floor
# participant at 3.5%), and AT MOST 9 (no participant from the 3.6% median
# upward can be <= 3.5%). The exact count is not machine-readable -- the
# distribution (Figure 3.C) is published only as a chart image, with no
# accessible-data table. The 4-9 share (21%-47%) has midpoint ~34%, which is
# forecast #6's base rate.
CURRENT_SEP_PCE_PROJECTION = {
    "sep_date": "2026-06-17",
    "target_year": 2026,
    "measure": "Q4/Q4 PCE inflation",
    "median_pct": 3.6,
    "central_tendency_pct": (3.5, 3.7),
    "full_range_pct": (2.7, 4.1),
    "participants": 19,
    "threshold_pct": 3.5,
    "count_at_or_below_threshold_bound": (4, 9),
    "source_url": "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm",
}
