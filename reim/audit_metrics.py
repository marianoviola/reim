"""
Audit-specific metrics for AI judgment governance.
"""

import numpy as np


def weighted_variance(values, weights) -> float:
    """Return weighted variance, handling empty or zero-weight inputs."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)

    if len(values) == 0 or weights.sum() <= 0:
        return 0.0

    mean = np.average(values, weights=weights)
    return float(np.average((values - mean) ** 2, weights=weights))


def confidence_calibration_error(confidences, errors, value_range: float) -> float:
    """
    Estimate confidence calibration error from gold-label residuals.

    Confidence is interpreted on [0, 1]. Correctness is approximated as
    1 - normalized absolute error.
    """
    if confidences is None or errors is None or len(confidences) == 0:
        return np.nan

    value_range = max(float(value_range), 1e-12)
    confidences = np.asarray(confidences, dtype=float)
    errors = np.asarray(errors, dtype=float)
    correctness = np.clip(1.0 - np.abs(errors) / value_range, 0.0, 1.0)

    return float(np.mean(np.abs(confidences - correctness)))


def epistemic_risk(uncertainty: float, disagreement: float, fragility: float, stake: float = 1.0) -> float:
    """Combine uncertainty, credible disagreement, and fragility into a risk score."""
    return float(stake * (uncertainty + disagreement + fragility))
