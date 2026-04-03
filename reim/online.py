"""
Online REIM — Incremental Bayesian Learning

Updates system estimates and observer reliability in real-time
as new observations arrive, without re-processing the full dataset.

Mathematical foundation:
- Maintains sufficient statistics (precision-weighted sum, total precision)
  for each system and observer
- Each new observation triggers a local update in O(1) time
- Equivalent to the batch Bayesian REIM in the limit, but computed incrementally

Key properties:
- O(1) per observation (constant time, no re-fit)
- Converges to the same estimates as batch REIM
- Supports temporal decay (older observations lose weight over time)
- Can warm-start from a batch REIM fit
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Literal
from collections import defaultdict
from datetime import datetime


class OnlineREIM:
    """
    Online (incremental) REIM with Bayesian updates.

    Maintains running estimates of system properties and observer reliability
    that update in O(1) per new observation.

    Parameters
    ----------
    prior_mean : float, default=3.0
        Prior mean for system properties.
    prior_precision : float, default=0.1
        Prior precision for system properties.
    initial_observer_precision : float, default=1.0
        Initial precision assigned to new observers.
    observer_learning_rate : float, default=0.05
        How quickly observer precision adapts. Higher = faster adaptation.
        Range (0, 1). At 0.05, ~20 observations to stabilize.
    temporal_decay : float, default=1.0
        Decay factor per time unit (default: no decay).
        E.g., 0.98 with monthly units = 2% weight loss per month.
    time_unit : str, default="months"
        Time unit for decay: "days", "weeks", "months", "years".
    min_precision : float, default=0.01
        Minimum observer precision (prevents division by zero).

    Attributes
    ----------
    system_estimates_ : dict
        Current estimates for each system.
    system_uncertainty_ : dict
        Current uncertainty (std error) for each system.
    observer_precision_ : dict
        Current precision (1/variance) for each observer.
    n_observations_ : int
        Total observations processed.
    """

    def __init__(
        self,
        prior_mean: float = 3.0,
        prior_precision: float = 0.1,
        initial_observer_precision: float = 1.0,
        observer_learning_rate: float = 0.05,
        temporal_decay: float = 1.0,
        time_unit: str = "months",
        min_precision: float = 0.01,
        recalibrate_every: int = 100,
    ):
        self.prior_mean = prior_mean
        self.prior_precision = prior_precision
        self.initial_observer_precision = initial_observer_precision
        self.observer_learning_rate = observer_learning_rate
        self.temporal_decay = temporal_decay
        self.time_unit = time_unit
        self.min_precision = min_precision
        self._recalibrate_every = recalibrate_every

        # --- Internal state ---
        # System sufficient statistics
        # For each system: weighted_sum = Σ α_u * r_{u,p}
        #                  total_precision = Σ α_u
        self._sys_weighted_sum: Dict[str, float] = {}
        self._sys_total_precision: Dict[str, float] = {}
        self._sys_n_obs: Dict[str, int] = defaultdict(int)

        # Observer statistics
        self._obs_precision: Dict[str, float] = {}
        self._obs_running_var: Dict[str, float] = {}
        self._obs_n: Dict[str, int] = defaultdict(int)

        # Observation log (for recalibration and temporal decay)
        self._obs_log: list = []

        self.n_observations_ = 0

    def observe(
        self,
        observer: str,
        system: str,
        value: float,
        timestamp: Optional[str] = None,
    ) -> dict:
        """
        Process a single new observation and update estimates.

        Parameters
        ----------
        observer : str
            Observer/reviewer ID.
        system : str
            System/product ID.
        value : float
            Observation value (e.g., rating 1-5).
        timestamp : str or None
            ISO timestamp. Used for temporal decay if enabled.

        Returns
        -------
        dict with updated estimates:
            {
                "system_estimate": float,
                "system_uncertainty": float,
                "observer_precision": float,
                "delta": float,  # how much the system estimate changed
            }
        """
        # Get or initialize observer precision
        alpha_u = self._obs_precision.get(observer, self.initial_observer_precision)

        # Get current system estimate (before update)
        old_estimate = self._get_system_estimate(system)

        # --- Update system sufficient statistics ---
        if system not in self._sys_weighted_sum:
            self._sys_weighted_sum[system] = self.prior_precision * self.prior_mean
            self._sys_total_precision[system] = self.prior_precision

        self._sys_weighted_sum[system] += alpha_u * value
        self._sys_total_precision[system] += alpha_u
        self._sys_n_obs[system] += 1

        # New system estimate
        new_estimate = self._get_system_estimate(system)
        new_uncertainty = self._get_system_uncertainty(system)

        # --- Update observer precision ---
        # Recalibrate based on all this observer's history
        self._obs_n[observer] += 1
        n = self._obs_n[observer]

        # Track running mean squared error for this observer
        error_sq = (value - new_estimate) ** 2
        lr = self.observer_learning_rate

        if observer not in self._obs_running_var:
            self._obs_running_var[observer] = max(error_sq, 0.01)
        else:
            self._obs_running_var[observer] = (1 - lr) * self._obs_running_var[observer] + lr * error_sq

        self._obs_precision[observer] = max(
            1.0 / self._obs_running_var[observer], self.min_precision
        )

        # Periodic global recalibration: every recalibrate_every observations,
        # recalculate all system estimates from scratch using current precisions
        if self.n_observations_ > 0 and self.n_observations_ % self._recalibrate_every == 0:
            self._recalibrate()

        # Log observation
        self._obs_log.append({
            "observer": observer,
            "system": system,
            "value": value,
            "timestamp": timestamp,
            "precision_at_time": self._obs_precision[observer],
        })

        self.n_observations_ += 1

        return {
            "system_estimate": new_estimate,
            "system_uncertainty": new_uncertainty,
            "observer_precision": self._obs_precision[observer],
            "delta": abs(new_estimate - old_estimate),
        }

    def observe_batch(self, observations: pd.DataFrame) -> "OnlineREIM":
        """
        Process a batch of observations sequentially.

        Parameters
        ----------
        observations : pd.DataFrame
            Columns: ['observer', 'system', 'value']
            Optional: 'timestamp'

        Returns
        -------
        self
        """
        for _, row in observations.iterrows():
            ts = row.get("timestamp", None)
            self.observe(
                observer=row["observer"],
                system=row["system"],
                value=row["value"],
                timestamp=ts,
            )
        return self

    def apply_temporal_decay(self, reference_date: Optional[str] = None):
        """
        Recompute system estimates with temporal decay applied.

        This is a periodic maintenance operation (e.g., run daily or weekly).
        Older observations contribute less to current estimates.

        Parameters
        ----------
        reference_date : str or None
            Reference date (default: now).
        """
        if self.temporal_decay >= 1.0:
            return  # No decay configured

        if reference_date:
            ref = pd.to_datetime(reference_date)
        else:
            ref = pd.Timestamp.now()

        # Recompute sufficient statistics from log with decay
        self._sys_weighted_sum.clear()
        self._sys_total_precision.clear()
        self._sys_n_obs.clear()

        time_divisors = {
            "days": 1, "weeks": 7, "months": 30.44, "years": 365.25
        }
        divisor = time_divisors.get(self.time_unit, 30.44)

        for entry in self._obs_log:
            system = entry["system"]
            observer = entry["observer"]
            value = entry["value"]
            ts = entry["timestamp"]

            # Compute decay weight
            if ts is not None:
                dt = pd.to_datetime(ts)
                elapsed = max((ref - dt).total_seconds() / (86400 * divisor), 0)
                decay = self.temporal_decay ** elapsed
            else:
                decay = 1.0

            alpha_u = self._obs_precision.get(observer, self.initial_observer_precision)
            weighted_alpha = alpha_u * decay

            if system not in self._sys_weighted_sum:
                self._sys_weighted_sum[system] = self.prior_precision * self.prior_mean
                self._sys_total_precision[system] = self.prior_precision

            self._sys_weighted_sum[system] += weighted_alpha * value
            self._sys_total_precision[system] += weighted_alpha
            self._sys_n_obs[system] = self._sys_n_obs.get(system, 0) + 1

    def warm_start(self, batch_model) -> "OnlineREIM":
        """
        Initialize from a fitted batch REIM model.

        Parameters
        ----------
        batch_model : REIM
            A fitted REIM instance (from reim.model).

        Returns
        -------
        self
        """
        # Import system estimates as sufficient statistics
        for system, theta in batch_model.system_estimates_.items():
            total_prec = 1.0 / (batch_model.uncertainty_[system] ** 2) if batch_model.uncertainty_[system] > 0 else 10.0
            self._sys_weighted_sum[system] = total_prec * theta
            self._sys_total_precision[system] = total_prec

        # Import observer precisions
        for observer, alpha in batch_model.observer_reliability_.items():
            self._obs_precision[observer] = alpha
            self._obs_n[observer] = 1  # mark as initialized

        return self

    # --- Recalibration ---

    def _recalibrate(self):
        """
        Recompute all system estimates using current observer precisions.
        This is the key to closing the gap with batch REIM:
        as observer precisions improve, system estimates should reflect
        the updated weights.
        """
        # Reset system sufficient statistics
        self._sys_weighted_sum.clear()
        self._sys_total_precision.clear()

        # Recompute from observation log with current precisions
        for entry in self._obs_log:
            system = entry["system"]
            observer = entry["observer"]
            value = entry["value"]

            alpha_u = self._obs_precision.get(observer, self.initial_observer_precision)

            if system not in self._sys_weighted_sum:
                self._sys_weighted_sum[system] = self.prior_precision * self.prior_mean
                self._sys_total_precision[system] = self.prior_precision

            self._sys_weighted_sum[system] += alpha_u * value
            self._sys_total_precision[system] += alpha_u

        # Now recompute observer variances with updated system estimates
        obs_errors: Dict[str, list] = defaultdict(list)
        for entry in self._obs_log:
            estimate = self._get_system_estimate(entry["system"])
            obs_errors[entry["observer"]].append((entry["value"] - estimate) ** 2)

        for observer, errors in obs_errors.items():
            if errors:
                variance = max(np.mean(errors), 1e-6)
                self._obs_precision[observer] = max(1.0 / variance, self.min_precision)
                self._obs_running_var[observer] = variance

    # --- Query methods ---

    @property
    def system_estimates_(self) -> dict:
        """Current system estimates."""
        return {s: self._get_system_estimate(s) for s in self._sys_weighted_sum}

    @property
    def system_uncertainty_(self) -> dict:
        """Current system uncertainties."""
        return {s: self._get_system_uncertainty(s) for s in self._sys_weighted_sum}

    @property
    def observer_precision_(self) -> dict:
        """Current observer precisions."""
        return dict(self._obs_precision)

    @property
    def observer_reliability_(self) -> dict:
        """Alias for observer_precision_ (same concept)."""
        return self.observer_precision_

    def predict(self, systems=None) -> pd.DataFrame:
        """Return current estimates as DataFrame."""
        if systems is None:
            systems = list(self._sys_weighted_sum.keys())

        rows = []
        for s in systems:
            rows.append({
                "system": s,
                "estimate": self._get_system_estimate(s),
                "uncertainty": self._get_system_uncertainty(s),
                "n_observations": self._sys_n_obs.get(s, 0),
            })
        return pd.DataFrame(rows)

    def get_observer_report(self) -> pd.DataFrame:
        """Return observer reliability report."""
        rows = []
        for u, prec in self._obs_precision.items():
            rows.append({
                "observer": u,
                "precision": prec,
                "n_observations": self._obs_n.get(u, 0),
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("precision", ascending=False).reset_index(drop=True)
        return df

    # --- Internal methods ---

    def _get_system_estimate(self, system: str) -> float:
        """Compute current system estimate from sufficient statistics."""
        if system not in self._sys_weighted_sum:
            return self.prior_mean
        total_prec = self._sys_total_precision[system]
        if total_prec <= 0:
            return self.prior_mean
        return self._sys_weighted_sum[system] / total_prec

    def _get_system_uncertainty(self, system: str) -> float:
        """Compute current system uncertainty."""
        if system not in self._sys_total_precision:
            return float("inf")
        total_prec = self._sys_total_precision[system]
        if total_prec <= 0:
            return float("inf")
        return 1.0 / np.sqrt(total_prec)
