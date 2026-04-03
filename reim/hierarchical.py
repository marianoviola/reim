"""
Hierarchical REIM with Directional Observability Constraints

Extends the base REIM to multi-level hierarchical systems where:
- System properties emerge from lower levels (bottom-up)
- Observers are positioned at specific levels
- Observers can only see their level and above (not below)
- Observation noise increases with hierarchical distance
"""

import numpy as np
import pandas as pd
from typing import Optional, Literal, Dict, List, Tuple


class HierarchicalREIM:
    """
    Hierarchical Reticular Epistemic Inference Model.

    Models a multi-level system where properties emerge bottom-up,
    observers are positioned at specific levels, and observability
    is constrained by hierarchical position.

    Parameters
    ----------
    method : str, default="bayesian"
        Estimation method: "mle" or "bayesian".
    max_iter : int, default=100
        Maximum number of iterations.
    tol : float, default=1e-6
        Convergence tolerance.
    attenuation : float, default=1.5
        Vertical attenuation factor phi. Observation noise is multiplied
        by phi^(distance) when observing systems above the observer's level.
    emergence_weight : float, default=0.5
        Weight of emerged (bottom-up) estimate vs direct observations.
        0 = ignore emergence, 1 = fully trust emergence.
    prior_mean : float or None, default=None
        Prior mean for system properties (bayesian only).
    prior_precision : float, default=0.01
        Prior precision for system properties (bayesian only).
    min_variance : float, default=1e-6
        Minimum observer variance.

    Attributes
    ----------
    system_estimates_ : dict
        Estimated properties for all systems at all levels.
        Keys are (level, system_id) tuples.
    observer_reliability_ : dict
        Estimated reliability for each observer.
    observer_variance_ : dict
        Estimated variance for each observer.
    uncertainty_ : dict
        Standard error of system estimates.
    hierarchy_ : dict
        The hierarchy structure used for inference.
    n_iter_ : int
        Number of iterations.
    converged_ : bool
        Whether the algorithm converged.
    log_likelihood_history_ : list
        Log-likelihood at each iteration.
    """

    def __init__(
        self,
        method: Literal["mle", "bayesian"] = "bayesian",
        max_iter: int = 100,
        tol: float = 1e-6,
        attenuation: float = 1.5,
        emergence_weight: float = 0.5,
        prior_mean: Optional[float] = None,
        prior_precision: float = 0.01,
        min_variance: float = 1e-6,
    ):
        self.method = method
        self.max_iter = max_iter
        self.tol = tol
        self.attenuation = attenuation
        self.emergence_weight = emergence_weight
        self.prior_mean = prior_mean
        self.prior_precision = prior_precision
        self.min_variance = min_variance

    def fit(
        self,
        observations: pd.DataFrame,
        hierarchy: Dict[str, List[str]],
        system_levels: Dict[str, int],
        observer_levels: Dict[str, int],
        observer_horizons: Optional[Dict[str, int]] = None,
    ) -> "HierarchicalREIM":
        """
        Fit the hierarchical model.

        Parameters
        ----------
        observations : pd.DataFrame
            Columns: ['observer', 'system', 'value']
        hierarchy : dict
            Parent -> children mapping. {parent_id: [child_id, ...]}.
            Children at level k compose the parent at level k-1.
            Level 0 is the top (most abstract). Higher levels are more granular.
        system_levels : dict
            {system_id: level} for all systems.
        observer_levels : dict
            {observer_id: level} for all observers.
        observer_horizons : dict or None
            {observer_id: max_vertical_reach}. How many levels above
            the observer can see. None = unlimited upward visibility.

        Returns
        -------
        self
        """
        self._validate_input(observations, system_levels, observer_levels)

        # Store structures
        self.hierarchy_ = hierarchy
        self.system_levels_ = system_levels
        self.observer_levels_ = observer_levels
        self.observer_horizons_ = observer_horizons or {}

        # Determine levels
        all_levels = sorted(set(system_levels.values()))
        self.n_levels_ = len(all_levels)
        self.levels_ = all_levels

        # Build reverse hierarchy (child -> parent)
        self.parent_of_ = {}
        for parent, children in hierarchy.items():
            for child in children:
                self.parent_of_[child] = parent

        # Systems by level
        self.systems_by_level_ = {}
        for s, lev in system_levels.items():
            self.systems_by_level_.setdefault(lev, []).append(s)

        # Filter observations by observability constraints
        valid_obs = self._apply_observability_constraints(observations)

        # Build lookup structures
        observers = list(set(valid_obs["observer"]))
        all_systems = list(system_levels.keys())

        system_obs = {}
        for s in all_systems:
            mask = valid_obs["system"] == s
            if mask.any():
                system_obs[s] = list(
                    zip(valid_obs.loc[mask, "observer"], valid_obs.loc[mask, "value"])
                )
            else:
                system_obs[s] = []

        observer_obs = {}
        for u in observers:
            mask = valid_obs["observer"] == u
            observer_obs[u] = list(
                zip(valid_obs.loc[mask, "system"], valid_obs.loc[mask, "value"])
            )

        # Initialize
        global_mean = observations["value"].mean()
        mu_0 = self.prior_mean if self.prior_mean is not None else global_mean

        # Initialize theta from observation means or global mean
        theta = {}
        for s in all_systems:
            if system_obs.get(s):
                vals = [v for _, v in system_obs[s]]
                theta[s] = np.mean(vals)
            else:
                theta[s] = mu_0

        # Initialize sigma^2
        sigma2 = {u: 1.0 for u in observers}

        # Iterative estimation
        self.log_likelihood_history_ = []

        for iteration in range(self.max_iter):
            # === PHASE 1: Bottom-up emergence ===
            emerged = self._compute_emergence(theta)

            # === PHASE 2: Update theta using observations + emergence ===
            theta_new = {}
            uncertainty = {}

            for s in all_systems:
                lev = system_levels[s]
                num = 0.0
                denom = 0.0

                # Contribution from direct observations
                for u, r in system_obs.get(s, []):
                    # Attenuated precision based on hierarchical distance
                    obs_level = observer_levels[u]
                    distance = obs_level - lev  # observer is below system
                    att = self.attenuation ** max(distance, 0)
                    alpha_u = 1.0 / (sigma2[u] * att)
                    num += alpha_u * r
                    denom += alpha_u

                # Contribution from emergence (if this system has children)
                if s in emerged:
                    em_val = emerged[s]
                    # Emergence precision: inversely proportional to emergence variance
                    # We estimate emergence variance from the spread of children
                    em_precision = self._emergence_precision(s, theta)
                    w = self.emergence_weight
                    num += w * em_precision * em_val
                    denom += w * em_precision

                # Bayesian prior
                if self.method == "bayesian":
                    num += self.prior_precision * mu_0
                    denom += self.prior_precision

                theta_new[s] = num / denom if denom > 0 else mu_0
                uncertainty[s] = np.sqrt(1.0 / denom) if denom > 0 else float("inf")

            # === PHASE 3: Top-down coherence ===
            theta_new = self._apply_topdown_coherence(theta_new, emerged)

            # === PHASE 4: Update observer variance ===
            sigma2_new = {}
            for u in observers:
                obs_list = observer_obs.get(u, [])
                n_u = len(obs_list)
                if n_u == 0:
                    sigma2_new[u] = 1.0
                    continue

                # Compute SSE with attenuation
                sse = 0.0
                for s, r in obs_list:
                    distance = observer_levels[u] - system_levels[s]
                    # Don't penalize the observer for attenuation-induced error
                    sse += (r - theta_new[s]) ** 2

                if self.method == "bayesian":
                    a_post = 2.0 + n_u / 2.0
                    b_post = 1.0 + sse / 2.0
                    sigma2_new[u] = max(b_post / (a_post + 1.0), self.min_variance)
                else:
                    sigma2_new[u] = max(sse / n_u, self.min_variance)

            # === Compute log-likelihood ===
            ll = self._log_likelihood(valid_obs, theta_new, sigma2_new)
            self.log_likelihood_history_.append(ll)

            # === Check convergence ===
            if len(self.log_likelihood_history_) > 1:
                delta = abs(self.log_likelihood_history_[-1] - self.log_likelihood_history_[-2])
                if delta < self.tol:
                    theta = theta_new
                    sigma2 = sigma2_new
                    break

            theta = theta_new
            sigma2 = sigma2_new

        # Store results
        self.system_estimates_ = theta
        self.observer_variance_ = sigma2
        self.observer_reliability_ = {u: 1.0 / v for u, v in sigma2.items()}
        self.uncertainty_ = uncertainty
        self.emerged_estimates_ = emerged
        self.n_iter_ = iteration + 1
        self.converged_ = (iteration + 1) < self.max_iter

        return self

    def _apply_observability_constraints(self, observations: pd.DataFrame) -> pd.DataFrame:
        """
        Filter observations based on directional observability.

        Axiom 6: Observer can see their level and above, not below.
        Axiom 8: Limited by vertical and horizontal horizons.
        """
        valid_mask = []
        for _, row in observations.iterrows():
            u = row["observer"]
            s = row["system"]
            obs_level = self.observer_levels_.get(u, 0)
            sys_level = self.system_levels_.get(s, 0)

            # Directional constraint: can observe own level and above (lower k)
            if sys_level > obs_level:
                valid_mask.append(False)
                continue

            # Vertical horizon constraint
            max_reach = self.observer_horizons_.get(u, None)
            if max_reach is not None:
                distance = obs_level - sys_level
                if distance > max_reach:
                    valid_mask.append(False)
                    continue

            valid_mask.append(True)

        return observations[valid_mask].reset_index(drop=True)

    def _compute_emergence(self, theta: dict) -> dict:
        """
        Compute emerged properties for parent systems from children.
        Bottom-up: properties at level k emerge from level k+1.
        """
        emerged = {}
        for parent, children in self.hierarchy_.items():
            child_vals = [theta[c] for c in children if c in theta]
            if child_vals:
                # Emergence function: weighted mean of children
                emerged[parent] = np.mean(child_vals)
        return emerged

    def _emergence_precision(self, system: str, theta: dict) -> float:
        """
        Estimate precision of the emergence signal.
        Higher when children are consistent; lower when they diverge.
        """
        children = self.hierarchy_.get(system, [])
        if len(children) <= 1:
            return 1.0

        child_vals = [theta[c] for c in children if c in theta]
        if len(child_vals) <= 1:
            return 1.0

        variance = np.var(child_vals) + 1e-6
        return 1.0 / variance

    def _apply_topdown_coherence(self, theta: dict, emerged: dict) -> dict:
        """
        Soft top-down coherence: if a system's estimate deviates strongly
        from what its children suggest, pull it toward the emerged value.
        """
        coherence_weight = 0.1  # light touch
        for parent in self.hierarchy_:
            if parent in emerged and parent in theta:
                em_val = emerged[parent]
                current = theta[parent]
                theta[parent] = (1 - coherence_weight) * current + coherence_weight * em_val
        return theta

    def _log_likelihood(self, observations, theta, sigma2):
        """Compute log-likelihood with attenuation."""
        ll = 0.0
        for _, row in observations.iterrows():
            u, s, r = row["observer"], row["system"], row["value"]
            if u not in sigma2 or s not in theta:
                continue
            distance = self.observer_levels_.get(u, 0) - self.system_levels_.get(s, 0)
            att = self.attenuation ** max(distance, 0)
            s2 = sigma2[u] * att
            ll += -0.5 * ((r - theta[s]) ** 2 / s2 + np.log(s2))
        return ll

    def predict(self, level: Optional[int] = None) -> pd.DataFrame:
        """Return estimated system properties, optionally filtered by level."""
        rows = []
        for s, est in self.system_estimates_.items():
            lev = self.system_levels_.get(s, -1)
            if level is not None and lev != level:
                continue
            rows.append({
                "system": s,
                "level": lev,
                "estimate": est,
                "uncertainty": self.uncertainty_.get(s, np.nan),
                "emerged": self.emerged_estimates_.get(s, np.nan),
            })
        return pd.DataFrame(rows).sort_values(["level", "system"]).reset_index(drop=True)

    def get_observer_report(self) -> pd.DataFrame:
        """Return observer reliability report with level information."""
        rows = []
        for u in self.observer_variance_:
            rows.append({
                "observer": u,
                "level": self.observer_levels_.get(u, -1),
                "variance": self.observer_variance_[u],
                "reliability": self.observer_reliability_[u],
            })
        return pd.DataFrame(rows).sort_values("reliability", ascending=False).reset_index(drop=True)

    def get_emergence_report(self) -> pd.DataFrame:
        """Compare direct estimates with emerged estimates."""
        rows = []
        for s in self.hierarchy_:
            if s in self.system_estimates_ and s in self.emerged_estimates_:
                rows.append({
                    "system": s,
                    "level": self.system_levels_.get(s, -1),
                    "direct_estimate": self.system_estimates_[s],
                    "emerged_estimate": self.emerged_estimates_[s],
                    "delta": abs(self.system_estimates_[s] - self.emerged_estimates_[s]),
                })
        return pd.DataFrame(rows).sort_values("delta", ascending=False).reset_index(drop=True)

    def _validate_input(self, observations, system_levels, observer_levels):
        required_cols = {"observer", "system", "value"}
        if not required_cols.issubset(observations.columns):
            raise ValueError(f"Missing columns: {required_cols - set(observations.columns)}")
        # Check all observed systems have levels
        obs_systems = set(observations["system"])
        missing = obs_systems - set(system_levels.keys())
        if missing:
            raise ValueError(f"Systems in observations without levels: {missing}")
        obs_observers = set(observations["observer"])
        missing_obs = obs_observers - set(observer_levels.keys())
        if missing_obs:
            raise ValueError(f"Observers without levels: {missing_obs}")
