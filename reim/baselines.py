"""
Baseline aggregation methods for comparison with REIM.
"""

import numpy as np
import pandas as pd
from scipy.stats import trim_mean


class SimpleAverage:
    """
    Simple average of observations per system.
    """

    def fit(self, observations: pd.DataFrame) -> "SimpleAverage":
        grouped = observations.groupby("system")["value"].mean()
        self.system_estimates_ = grouped.to_dict()
        return self

    def predict(self, systems=None) -> pd.DataFrame:
        if systems is None:
            systems = list(self.system_estimates_.keys())
        rows = [{"system": s, "estimate": self.system_estimates_.get(s, np.nan)} for s in systems]
        return pd.DataFrame(rows)


class TrimmedMean:
    """
    Trimmed mean: removes a fraction of extreme observations before averaging.

    Parameters
    ----------
    trim_fraction : float, default=0.1
        Fraction to trim from each tail.
    """

    def __init__(self, trim_fraction: float = 0.1):
        self.trim_fraction = trim_fraction

    def fit(self, observations: pd.DataFrame) -> "TrimmedMean":
        self.system_estimates_ = {}
        for s, group in observations.groupby("system"):
            vals = group["value"].values
            if len(vals) <= 2:
                self.system_estimates_[s] = np.mean(vals)
            else:
                self.system_estimates_[s] = trim_mean(vals, self.trim_fraction)
        return self

    def predict(self, systems=None) -> pd.DataFrame:
        if systems is None:
            systems = list(self.system_estimates_.keys())
        rows = [{"system": s, "estimate": self.system_estimates_.get(s, np.nan)} for s in systems]
        return pd.DataFrame(rows)


class MedianEstimator:
    """
    Median of observations per system. Robust to outliers.
    """

    def fit(self, observations: pd.DataFrame) -> "MedianEstimator":
        grouped = observations.groupby("system")["value"].median()
        self.system_estimates_ = grouped.to_dict()
        return self

    def predict(self, systems=None) -> pd.DataFrame:
        if systems is None:
            systems = list(self.system_estimates_.keys())
        rows = [{"system": s, "estimate": self.system_estimates_.get(s, np.nan)} for s in systems]
        return pd.DataFrame(rows)
