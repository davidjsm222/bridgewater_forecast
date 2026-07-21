"""
Tier 2: Trend-extrapolation forecasts.
No live market prices this directly, but there's real reported trend data
(data center construction reports, BEA investment data). Fit a simple trend,
project to resolution date, and express how far the threshold sits from that
projection in standard-deviation terms -- an explicit uncertainty band instead
of a bare guess.
"""

import math
import statistics
from dataclasses import dataclass
from datetime import date

from data_sources import pull_information_processing_investment, pull_pce_inflation
from forecasts import set_forecast_probability


PCE_TREND_MONTHS = 12
PCE_TARGET_PCT = 3.5
PCE_RESOLUTION_MONTH = date(2026, 12, 1)
INVESTMENT_TREND_YEARS = 10
INVESTMENT_TARGET_CONTRIBUTION_PP = 1.5
INVESTMENT_TARGET_YEAR = 2027
SMALL_SAMPLE_REFERENCE_N = 8


@dataclass
class TrendPoint:
    period: str   # e.g. "2025-Q4"
    value: float


def linear_trend_projection(points: list[TrendPoint], periods_ahead: int) -> dict:
    """
    Fits a simple linear trend (least squares over point index) and projects
    forward. Returns projection plus residual std dev so you can talk about
    uncertainty honestly instead of a single fake-precise number.
    """
    n = len(points)
    if n < 3:
        raise ValueError("Need at least 3 data points for a trend fit worth trusting")

    xs = list(range(n))
    ys = [p.value for p in points]

    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = numerator / denominator if denominator else 0
    intercept = y_mean - slope * x_mean

    fitted = [slope * x + intercept for x in xs]
    residuals = [y - f for y, f in zip(ys, fitted)]
    residual_std = statistics.stdev(residuals) if n > 2 else 0

    # Fit diagnostics -- reported only, they do not feed the projection or the
    # probability. They answer "is this fitted slope statistically meaningful,
    # or is it noise?" using the standard OLS formulas:
    #   s^2 = SSE / (n - 2)          (regression standard error, n-2 dof)
    #   SE(slope) = s / sqrt(Sxx)
    #   t = slope / SE(slope)        (H0: true slope = 0, n-2 dof)
    #   R^2 = 1 - SSE / SST
    sse = sum(r ** 2 for r in residuals)
    sst = sum((y - y_mean) ** 2 for y in ys)
    slope_std_error = None
    t_statistic = None
    if n > 2 and denominator > 0:
        regression_std_error = math.sqrt(sse / (n - 2))
        slope_std_error = regression_std_error / math.sqrt(denominator)
        t_statistic = slope / slope_std_error if slope_std_error > 0 else None
    r_squared = 1 - sse / sst if sst > 0 else None

    projection_x = (n - 1) + periods_ahead
    projected_value = slope * projection_x + intercept

    return {
        "slope_per_period": round(slope, 4),
        "projected_value": round(projected_value, 3),
        "residual_std": round(residual_std, 3),
        "n_points": n,
        "slope_std_error": round(slope_std_error, 4) if slope_std_error is not None else None,
        "slope_t_statistic": round(t_statistic, 3) if t_statistic is not None else None,
        "slope_t_dof": n - 2,
        "r_squared": round(r_squared, 4) if r_squared is not None else None,
    }


def walk_forward_rmse(points: list[TrendPoint]) -> float | None:
    """One-step-ahead RMSE from expanding-window fits, used as an uncertainty floor."""
    if len(points) < 4:
        return None
    errors = []
    for end in range(3, len(points)):
        prior_fit = linear_trend_projection(points[:end], periods_ahead=1)
        errors.append(points[end].value - prior_fit["projected_value"])
    return math.sqrt(sum(error ** 2 for error in errors) / len(errors))


def distance_to_threshold_in_sigma(
    projected_value: float,
    threshold: float,
    residual_std: float,
    *,
    n_points: int | None = None,
    periods_ahead: int = 0,
    out_of_sample_rmse: float | None = None,
) -> dict:
    """
    Expresses how many standard deviations the threshold sits from the
    projected value. Small |z| = genuinely uncertain / close call.
    Large |z| = trend would have to break sharply for the other outcome.
    This is a framing tool, not a probability -- translate to a probability
    using judgment, informed by how likely a trend break actually is here.

    The effective uncertainty is deliberately wider than an in-sample residual
    standard deviation when validation or sample size warrants it:

    1. Use the larger of in-sample residual std and expanding-window,
       one-step-ahead RMSE.
    2. Apply the standard linear-regression prediction-error multiplier for a
       future point, including forecast-horizon leverage.
    3. When n < 8, multiply the scale by sqrt(8/n). Probabilities then use a
       Student-t distribution with n-2 degrees of freedom.

    This is a documented small-sample/prediction-interval correction, not an
    arbitrary probability cap.
    """
    if residual_std <= 0:
        return {"z": None, "read": "no residual variance in the data -- treat any projection with caution"}
    if periods_ahead < 0:
        raise ValueError("periods_ahead must be non-negative")

    validation_floor = max(residual_std, out_of_sample_rmse or 0.0)
    prediction_factor = 1.0
    small_sample_factor = 1.0
    degrees_of_freedom = None
    if n_points is not None:
        if n_points < 3:
            raise ValueError("n_points must be at least 3")
        x_mean = (n_points - 1) / 2
        sxx = n_points * (n_points ** 2 - 1) / 12
        forecast_x = (n_points - 1) + periods_ahead
        prediction_factor = math.sqrt(
            1 + 1 / n_points + ((forecast_x - x_mean) ** 2 / sxx)
        )
        if n_points < SMALL_SAMPLE_REFERENCE_N:
            small_sample_factor = math.sqrt(SMALL_SAMPLE_REFERENCE_N / n_points)
        degrees_of_freedom = n_points - 2

    effective_std = validation_floor * prediction_factor * small_sample_factor
    z = (threshold - projected_value) / effective_std
    if abs(z) > 2:
        read = "threshold far from trend -- would need a real break to flip"
    elif abs(z) > 1:
        read = "threshold plausible but trend leans against it"
    else:
        read = "genuinely close call -- trend alone doesn't resolve this"
    return {
        "z": round(z, 2),
        "read": read,
        "raw_residual_std": residual_std,
        "walk_forward_rmse": out_of_sample_rmse,
        "validation_floor_std": round(validation_floor, 6),
        "prediction_factor": round(prediction_factor, 6),
        "small_sample_factor": round(small_sample_factor, 6),
        "effective_residual_std": round(effective_std, 6),
        "degrees_of_freedom": degrees_of_freedom,
    }


def _continued_fraction_beta(a: float, b: float, x: float) -> float:
    """Numerical Recipes continued fraction used by the regularized beta CDF."""
    max_iterations = 200
    epsilon = 3e-14
    minimum = 1e-300
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1 - qab * x / qap
    d = minimum if abs(d) < minimum else d
    d = 1 / d
    result = d
    for iteration in range(1, max_iterations + 1):
        twice = 2 * iteration
        numerator = iteration * (b - iteration) * x / ((qam + twice) * (a + twice))
        d = 1 + numerator * d
        d = minimum if abs(d) < minimum else d
        c = 1 + numerator / c
        c = minimum if abs(c) < minimum else c
        d = 1 / d
        result *= d * c
        numerator = -(a + iteration) * (qab + iteration) * x / (
            (a + twice) * (qap + twice)
        )
        d = 1 + numerator * d
        d = minimum if abs(d) < minimum else d
        c = 1 + numerator / c
        c = minimum if abs(c) < minimum else c
        d = 1 / d
        delta = d * c
        result *= delta
        if abs(delta - 1) < epsilon:
            return result
    raise ArithmeticError("Student-t CDF failed to converge")


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if not 0 <= x <= 1:
        raise ValueError("x must be between 0 and 1")
    if x in (0, 1):
        return x
    front = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    if x < (a + 1) / (a + b + 2):
        return front * _continued_fraction_beta(a, b, x) / a
    return 1 - front * _continued_fraction_beta(b, a, 1 - x) / b


def student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    """Student-t cumulative distribution using the incomplete-beta identity."""
    if degrees_of_freedom <= 0:
        raise ValueError("degrees_of_freedom must be positive")
    if value == 0:
        return 0.5
    x = degrees_of_freedom / (degrees_of_freedom + value ** 2)
    tail = 0.5 * _regularized_incomplete_beta(degrees_of_freedom / 2, 0.5, x)
    return tail if value < 0 else 1 - tail


def threshold_probability(
    projected_value: float,
    threshold: float,
    residual_std: float,
    *,
    yes_if_at_or_below: bool,
    degrees_of_freedom: int | None = None,
) -> float:
    """Translate a corrected trend error scale into a 0-100 YES probability."""
    if residual_std <= 0:
        raise ValueError("Residual standard deviation must be positive to estimate a probability")
    standardized_distance = (threshold - projected_value) / residual_std
    probability_at_or_below = (
        student_t_cdf(standardized_distance, degrees_of_freedom)
        if degrees_of_freedom is not None
        else statistics.NormalDist().cdf(standardized_distance)
    )
    probability = probability_at_or_below if yes_if_at_or_below else 1 - probability_at_or_below
    # Preserve very small non-zero tail probabilities instead of rounding them
    # to an artificial absolute 0.0%.
    return round(probability * 100, 12)


def pce_trend_forecast() -> dict:
    """Fit the latest 12 real PCE YoY observations and project to December 2026."""
    cache = pull_pce_inflation()
    usable = [
        observation
        for observation in cache["observations"]
        if observation["year_over_year_pct"] is not None
    ]
    selected = usable[-PCE_TREND_MONTHS:]
    if len(selected) < 3:
        raise ValueError("Need at least 3 cached PCE YoY observations")
    points = [
        TrendPoint(observation["date"][:7], observation["year_over_year_pct"])
        for observation in selected
    ]
    latest = date.fromisoformat(selected[-1]["date"])
    periods_ahead = (
        (PCE_RESOLUTION_MONTH.year - latest.year) * 12
        + PCE_RESOLUTION_MONTH.month
        - latest.month
    )
    projection = linear_trend_projection(points, periods_ahead)
    validation_rmse = walk_forward_rmse(points)
    distance = distance_to_threshold_in_sigma(
        projection["projected_value"],
        PCE_TARGET_PCT,
        projection["residual_std"],
        n_points=len(points),
        periods_ahead=periods_ahead,
        out_of_sample_rmse=validation_rmse,
    )
    probability = threshold_probability(
        projection["projected_value"],
        PCE_TARGET_PCT,
        distance["effective_residual_std"],
        yes_if_at_or_below=True,
        degrees_of_freedom=distance["degrees_of_freedom"],
    )
    return {
        "forecast_id": 6,
        "source_retrieved_at_utc": cache["retrieved_at_utc"],
        "points": points,
        "periods_ahead": periods_ahead,
        "projection": projection,
        "threshold_distance": distance,
        "probability_yes_pct": probability,
        "probability_method": (
            "Student-t CDF using a walk-forward RMSE floor, regression prediction-error "
            "multiplier, and sqrt(8/n) scale penalty when n < 8"
        ),
    }


def information_processing_investment_trend_forecast() -> dict:
    """Project the annual BEA information-processing/software GDP contribution to 2027."""
    cache = pull_information_processing_investment()
    observations = cache["gdp_contribution_observations"][-INVESTMENT_TREND_YEARS:]
    if len(observations) < 3:
        raise ValueError("Need at least 3 cached annual GDP-contribution observations")
    points = [
        TrendPoint(
            observation["date"][:4],
            observation["total_percentage_points_at_annual_rate"],
        )
        for observation in observations
    ]
    latest_year = int(observations[-1]["date"][:4])
    periods_ahead = INVESTMENT_TARGET_YEAR - latest_year
    projection = linear_trend_projection(points, periods_ahead)
    validation_rmse = walk_forward_rmse(points)
    distance = distance_to_threshold_in_sigma(
        projection["projected_value"],
        INVESTMENT_TARGET_CONTRIBUTION_PP,
        projection["residual_std"],
        n_points=len(points),
        periods_ahead=periods_ahead,
        out_of_sample_rmse=validation_rmse,
    )
    probability = threshold_probability(
        projection["projected_value"],
        INVESTMENT_TARGET_CONTRIBUTION_PP,
        distance["effective_residual_std"],
        yes_if_at_or_below=False,
        degrees_of_freedom=distance["degrees_of_freedom"],
    )
    return {
        "forecast_id": 4,
        "source_retrieved_at_utc": cache["retrieved_at_utc"],
        "points": points,
        "periods_ahead": periods_ahead,
        "projection": projection,
        "threshold_distance": distance,
        "probability_yes_pct": probability,
        "probability_method": (
            "Student-t CDF using a walk-forward RMSE floor, regression prediction-error "
            "multiplier, and sqrt(8/n) scale penalty when n < 8"
        ),
    }


if __name__ == "__main__":
    # ARCHIVED -- forecasts #4 and #6 were BOTH reframed from these trend fits to
    # tier-3 reference-class estimates (see forecasts.py, tui.py tier3["4"] /
    # tier3["6"], and methodology_notes.md). The trend functions below are kept
    # for reference and still run, but NEITHER persists its forecast's
    # authoritative probability anymore:
    #   * #4's 2.4% compared the outcome to a flat 10-year historical proxy
    #     rather than to Bridgewater's forward-looking 150bp estimate;
    #   * #6's 3.8% came from a 12-point band that cannot represent real macro-
    #     surprise risk over a 7-month horizon.
    # Do not re-enable set_forecast_probability(4/6, ...) here without reverting
    # the reframes, or it will clobber the tier-3 answers.
    pce = pce_trend_forecast()
    print("Forecast #6 ARCHIVED PCE trend fit (not persisted):", pce["probability_yes_pct"], "%")
    investment = information_processing_investment_trend_forecast()
    print("Forecast #4 ARCHIVED trend fit (not persisted):", investment["probability_yes_pct"], "%")
