"""
Core REIM model implementation.

Supports two estimation methods:
- MLE: Maximum Likelihood Estimation via coordinate ascent
- Bayesian (MAP): Maximum A Posteriori with Gaussian prior on theta
  and Inverse-Gamma prior on observer variance
"""

import numpy as np
import pandas as pd
from typing import Optional, Literal


class REIM:
    """
    Reticular Epistemic Inference Model.

    Estimates true system properties and observer reliability from
    distributed noisy observations.

    Parameters
    ----------
    method : str, default="bayesian"
        Estimation method: "mle" or "bayesian".
    max_iter : int, default=100
        Maximum number of iterations.
    tol : float, default=1e-6
        Convergence tolerance on log-likelihood change.
    prior_mean : float or None, default=None
        Prior mean for system properties (bayesian only).
        If None, uses the global mean of observations.
    prior_precision : float, default=0.01
        Prior precision (1/variance) for system properties (bayesian only).
        Small values = weak prior.
    prior_a : float, default=2.0
        Inverse-Gamma shape parameter for observer variance prior.
    prior_b : float, default=1.0
        Inverse-Gamma scale parameter for observer variance prior.
    min_variance : float, default=1e-6
        Minimum observer variance to prevent numerical issues.

    Attributes
    ----------
    system_estimates_ : dict
        Estimated true property for each system.
    observer_reliability_ : dict
        Estimated reliability (precision = 1/variance) for each observer.
    observer_variance_ : dict
        Estimated variance for each observer.
    uncertainty_ : dict
        Standard error of system estimates (bayesian only).
    n_iter_ : int
        Number of iterations until convergence.
    log_likelihood_history_ : list
        Log-likelihood at each iteration.
    converged_ : bool
        Whether the algorithm converged within max_iter.
    """

    def __init__(
        self,
        method: Literal["mle", "bayesian"] = "bayesian",
        max_iter: int = 100,
        tol: float = 1e-6,
        prior_mean: Optional[float] = None,
        prior_precision: float = 0.01,
        prior_a: float = 2.0,
        prior_b: float = 1.0,
        min_variance: float = 1e-6,
    ):
        self.method = method
        self.max_iter = max_iter
        self.tol = tol
        self.prior_mean = prior_mean
        self.prior_precision = prior_precision
        self.prior_a = prior_a
        self.prior_b = prior_b
        self.min_variance = min_variance

    def fit(self, observations: pd.DataFrame) -> "REIM":
        """
        Fit the model to observations.

        Parameters
        ----------
        observations : pd.DataFrame
            Must have columns: ['observer', 'system', 'value']

        Returns
        -------
        self
        """
        self._validate_input(observations)

        # Extract unique entities
        observers = observations["observer"].unique()
        systems = observations["system"].unique()

        # Build observation lookup structures
        # For each system: list of (observer, value)
        system_obs = {}
        for s in systems:
            mask = observations["system"] == s
            system_obs[s] = list(
                zip(observations.loc[mask, "observer"], observations.loc[mask, "value"])
            )

        # For each observer: list of (system, value)
        observer_obs = {}
        for u in observers:
            mask = observations["observer"] == u
            observer_obs[u] = list(
                zip(observations.loc[mask, "system"], observations.loc[mask, "value"])
            )

        # Initialize
        global_mean = observations["value"].mean()
        mu_0 = self.prior_mean if self.prior_mean is not None else global_mean

        # Initialize theta as mean of observations per system
        theta = {}
        for s in systems:
            vals = [v for _, v in system_obs[s]]
            theta[s] = np.mean(vals)

        # Initialize sigma^2 uniformly
        sigma2 = {u: 1.0 for u in observers}

        # Iterative estimation
        self.log_likelihood_history_ = []

        for iteration in range(self.max_iter):
            # --- Update theta ---
            theta_new = {}
            uncertainty = {}

            for s in systems:
                num = 0.0
                denom = 0.0

                for u, r in system_obs[s]:
                    alpha_u = 1.0 / sigma2[u]
                    num += alpha_u * r
                    denom += alpha_u

                if self.method == "bayesian":
                    num += self.prior_precision * mu_0
                    denom += self.prior_precision

                theta_new[s] = num / denom if denom > 0 else global_mean
                uncertainty[s] = np.sqrt(1.0 / denom) if denom > 0 else float("inf")

            # --- Update sigma^2 ---
            sigma2_new = {}

            for u in observers:
                obs_list = observer_obs[u]
                n_u = len(obs_list)

                if n_u == 0:
                    sigma2_new[u] = 1.0
                    continue

                sse = sum((r - theta_new[s]) ** 2 for s, r in obs_list)

                if self.method == "bayesian":
                    # MAP estimate with Inverse-Gamma prior
                    # Mode of Inv-Gamma posterior: b / (a + 1)
                    # Posterior: a_post = a_0 + n/2, b_post = b_0 + SSE/2
                    a_post = self.prior_a + n_u / 2.0
                    b_post = self.prior_b + sse / 2.0
                    sigma2_new[u] = max(b_post / (a_post + 1.0), self.min_variance)
                else:
                    # MLE
                    sigma2_new[u] = max(sse / n_u, self.min_variance)

            # --- Compute log-likelihood ---
            ll = self._log_likelihood(observations, theta_new, sigma2_new)
            self.log_likelihood_history_.append(ll)

            # --- Check convergence ---
            if len(self.log_likelihood_history_) > 1:
                delta = abs(
                    self.log_likelihood_history_[-1] - self.log_likelihood_history_[-2]
                )
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
        self.n_iter_ = iteration + 1
        self.converged_ = (iteration + 1) < self.max_iter

        return self

    def predict(self, systems=None) -> pd.DataFrame:
        """
        Return estimated system properties.

        Parameters
        ----------
        systems : list or None
            Systems to predict. If None, returns all.

        Returns
        -------
        pd.DataFrame with columns: ['system', 'estimate', 'uncertainty']
        """
        if systems is None:
            systems = list(self.system_estimates_.keys())

        rows = []
        for s in systems:
            rows.append(
                {
                    "system": s,
                    "estimate": self.system_estimates_.get(s, np.nan),
                    "uncertainty": self.uncertainty_.get(s, np.nan),
                }
            )
        return pd.DataFrame(rows)

    def get_observer_report(self) -> pd.DataFrame:
        """
        Return observer reliability estimates.

        Returns
        -------
        pd.DataFrame with columns: ['observer', 'variance', 'reliability']
        """
        rows = []
        for u in self.observer_variance_:
            rows.append(
                {
                    "observer": u,
                    "variance": self.observer_variance_[u],
                    "reliability": self.observer_reliability_[u],
                }
            )
        df = pd.DataFrame(rows)
        return df.sort_values("reliability", ascending=False).reset_index(drop=True)

    def _log_likelihood(self, observations, theta, sigma2):
        """Compute log-likelihood of observations given parameters."""
        t_vals = observations["system"].map(theta).values
        s_vals = observations["observer"].map(sigma2).values
        r_vals = observations["value"].values
        return -0.5 * np.sum((r_vals - t_vals) ** 2 / s_vals + np.log(s_vals))

    def _validate_input(self, df):
        """Validate input DataFrame."""
        required_cols = {"observer", "system", "value"}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            raise ValueError(f"Missing columns: {missing}")
        if df["value"].isnull().any():
            raise ValueError("Observation values contain NaN")
