"""
AuditREIM — governance and AI judgment audit.

This variant extends Base REIM with domain-specific observer reliability,
systematic observer bias, gold-label calibration, observer horizons, and
governance metrics such as credible disagreement and consensus fragility.
"""

from typing import Dict, Iterable, Optional, Literal

import numpy as np
import pandas as pd

from .audit_metrics import (
    confidence_calibration_error,
    epistemic_risk,
    weighted_variance,
)


class AuditREIM:
    """
    REIM variant for auditing AI or human judgments.

    Parameters
    ----------
    method : {"mle", "bayesian"}, default="bayesian"
        Estimation method.
    max_iter : int, default=100
        Maximum number of coordinate-ascent iterations per domain.
    tol : float, default=1e-6
        Convergence tolerance on log-likelihood change.
    prior_mean : float or None, default=None
        Prior mean for latent audit scores. If None, uses global mean.
    prior_precision : float, default=0.01
        Prior precision for latent scores in Bayesian mode.
    bias_prior_precision : float, default=1.0
        Shrinkage precision for observer bias toward zero.
    prior_a : float, default=2.0
        Inverse-Gamma shape parameter for observer variance prior.
    prior_b : float, default=1.0
        Inverse-Gamma scale parameter for observer variance prior.
    gold_precision : float, default=100.0
        Soft-anchor precision for gold labels.
    min_variance : float, default=1e-6
        Minimum observer variance.
    out_of_horizon_weight : float, default=0.0
        Precision multiplier for observations outside observer horizons.
        Set to 0 to reject them.
    """

    def __init__(
        self,
        method: Literal["mle", "bayesian"] = "bayesian",
        max_iter: int = 100,
        tol: float = 1e-6,
        prior_mean: Optional[float] = None,
        prior_precision: float = 0.01,
        bias_prior_precision: float = 1.0,
        prior_a: float = 2.0,
        prior_b: float = 1.0,
        gold_precision: float = 100.0,
        min_variance: float = 1e-6,
        out_of_horizon_weight: float = 0.0,
    ):
        self.method = method
        self.max_iter = max_iter
        self.tol = tol
        self.prior_mean = prior_mean
        self.prior_precision = prior_precision
        self.bias_prior_precision = bias_prior_precision
        self.prior_a = prior_a
        self.prior_b = prior_b
        self.gold_precision = gold_precision
        self.min_variance = min_variance
        self.out_of_horizon_weight = out_of_horizon_weight

    def fit(
        self,
        judgments: pd.DataFrame,
        gold_labels: Optional[pd.DataFrame] = None,
        observer_horizons: Optional[Dict[str, Iterable[str]]] = None,
        stakes: Optional[Dict[tuple, float]] = None,
    ) -> "AuditREIM":
        """
        Fit AuditREIM on judgment observations.

        Parameters
        ----------
        judgments : pd.DataFrame
            Required columns: ['observer', 'system', 'domain', 'value'].
            Optional columns: ['confidence', 'observer_group', 'timestamp'].
        gold_labels : pd.DataFrame, optional
            Columns: ['system', 'domain', 'value'] with optional 'confidence'.
        observer_horizons : dict, optional
            Mapping observer -> allowed domains.
        stakes : dict, optional
            Mapping (system, domain) -> stake multiplier for epistemic risk.
        """
        self._validate_judgments(judgments)

        raw = judgments.copy()
        raw["observer"] = raw["observer"].astype(str)
        raw["system"] = raw["system"].astype(str)
        raw["domain"] = raw["domain"].astype(str)
        raw["value"] = raw["value"].astype(float)

        self.observer_horizons_ = {
            str(observer): {str(domain) for domain in domains}
            for observer, domains in (observer_horizons or {}).items()
        }
        raw["_horizon_weight"] = [
            self._horizon_weight(observer, domain)
            for observer, domain in zip(raw["observer"], raw["domain"])
        ]
        self.rejected_observations_ = raw[raw["_horizon_weight"] <= 0].copy()
        data = raw[raw["_horizon_weight"] > 0].copy()

        if data.empty:
            raise ValueError("No valid judgments remain after applying observer horizons")

        gold = self._prepare_gold(gold_labels)
        self.gold_labels_ = gold

        self.system_estimates_ = {}
        self.uncertainty_ = {}
        self.observer_bias_ = {}
        self.observer_variance_ = {}
        self.observer_reliability_ = {}
        self.credible_disagreement_ = {}
        self.consensus_fragility_ = {}
        self.epistemic_risk_ = {}
        self.log_likelihood_history_ = {}
        self.n_iter_ = {}
        self.converged_ = {}

        self.value_range_ = max(float(data["value"].max() - data["value"].min()), 1.0)
        domains = sorted(data["domain"].unique())

        for domain in domains:
            domain_data = data[data["domain"] == domain].copy()
            domain_gold = gold[gold["domain"] == domain] if gold is not None else None
            self._fit_domain(domain, domain_data, domain_gold)

        self._compute_governance_metrics(data, stakes or {})
        self._compute_observer_reports(data, gold)

        return self

    def predict(self, systems=None, domains=None) -> pd.DataFrame:
        """Return latent audit scores by system and domain."""
        rows = []
        for key, estimate in self.system_estimates_.items():
            system, domain = key
            if systems is not None and system not in systems:
                continue
            if domains is not None and domain not in domains:
                continue
            rows.append({
                "system": system,
                "domain": domain,
                "estimate": estimate,
                "uncertainty": self.uncertainty_.get(key, np.nan),
                "credible_disagreement": self.credible_disagreement_.get(key, np.nan),
                "consensus_fragility": self.consensus_fragility_.get(key, np.nan),
                "epistemic_risk": self.epistemic_risk_.get(key, np.nan),
            })
        return pd.DataFrame(rows)

    def get_observer_report(self) -> pd.DataFrame:
        """Return observer reliability, bias, calibration, and coverage by domain."""
        if not hasattr(self, "observer_report_"):
            raise RuntimeError("Model not fitted.")
        return self.observer_report_.copy()

    def get_alerts(
        self,
        disagreement_threshold: float = 0.1,
        fragility_threshold: float = 0.1,
        risk_threshold: float = 0.3,
    ) -> pd.DataFrame:
        """Return systems that exceed governance alert thresholds."""
        rows = []
        for key, risk in self.epistemic_risk_.items():
            system, domain = key
            disagreement = self.credible_disagreement_.get(key, 0.0)
            fragility = self.consensus_fragility_.get(key, 0.0)

            if disagreement >= disagreement_threshold:
                rows.append({
                    "type": "credible_disagreement",
                    "system": system,
                    "domain": domain,
                    "value": disagreement,
                })
            if fragility >= fragility_threshold:
                rows.append({
                    "type": "consensus_fragility",
                    "system": system,
                    "domain": domain,
                    "value": fragility,
                })
            if risk >= risk_threshold:
                rows.append({
                    "type": "epistemic_risk",
                    "system": system,
                    "domain": domain,
                    "value": risk,
                })

        return pd.DataFrame(rows)

    def _fit_domain(self, domain: str, data: pd.DataFrame, gold: Optional[pd.DataFrame]):
        observers = sorted(data["observer"].unique())
        systems = sorted(set(data["system"].unique()) | self._gold_systems(gold))

        global_mean = data["value"].mean()
        prior_mean = self.prior_mean if self.prior_mean is not None else global_mean
        gold_map = self._gold_map(gold)

        system_obs = {
            system: data[data["system"] == system][["observer", "value", "_horizon_weight"]].to_records(index=False)
            for system in systems
        }
        observer_obs = {
            observer: data[data["observer"] == observer][["system", "value", "_horizon_weight"]].to_records(index=False)
            for observer in observers
        }

        theta = {}
        for system in systems:
            if system in gold_map:
                theta[system] = gold_map[system]
            elif len(system_obs[system]) > 0:
                theta[system] = float(np.mean([row[1] for row in system_obs[system]]))
            else:
                theta[system] = prior_mean

        bias = {observer: 0.0 for observer in observers}
        sigma2 = {observer: 1.0 for observer in observers}
        history = []

        for iteration in range(self.max_iter):
            bias_new = {}
            for observer in observers:
                obs = observer_obs[observer]
                if len(obs) == 0:
                    bias_new[observer] = 0.0
                    continue

                residual_sum = 0.0
                weight_sum = self.bias_prior_precision
                for system, value, horizon_weight in obs:
                    alpha = horizon_weight / sigma2[observer]
                    residual_sum += alpha * (value - theta[system])
                    weight_sum += alpha
                bias_new[observer] = residual_sum / weight_sum if weight_sum > 0 else 0.0

            if not gold_map:
                mean_bias = np.mean(list(bias_new.values())) if bias_new else 0.0
                bias_new = {observer: value - mean_bias for observer, value in bias_new.items()}

            theta_new = {}
            uncertainty = {}
            for system in systems:
                num = 0.0
                denom = 0.0

                if self.method == "bayesian":
                    num += self.prior_precision * prior_mean
                    denom += self.prior_precision

                if system in gold_map:
                    num += self.gold_precision * gold_map[system]
                    denom += self.gold_precision

                for observer, value, horizon_weight in system_obs[system]:
                    alpha = horizon_weight / sigma2[observer]
                    num += alpha * (value - bias_new[observer])
                    denom += alpha

                theta_new[system] = num / denom if denom > 0 else prior_mean
                uncertainty[system] = np.sqrt(1.0 / denom) if denom > 0 else float("inf")

            sigma2_new = {}
            for observer in observers:
                obs = observer_obs[observer]
                n_obs = len(obs)
                if n_obs == 0:
                    sigma2_new[observer] = 1.0
                    continue

                sse = 0.0
                weight_sum = 0.0
                for system, value, horizon_weight in obs:
                    residual = value - bias_new[observer] - theta_new[system]
                    sse += horizon_weight * residual ** 2
                    weight_sum += horizon_weight

                if self.method == "bayesian":
                    a_post = self.prior_a + weight_sum / 2.0
                    b_post = self.prior_b + sse / 2.0
                    sigma2_new[observer] = max(b_post / (a_post + 1.0), self.min_variance)
                else:
                    sigma2_new[observer] = max(sse / max(weight_sum, 1e-12), self.min_variance)

            ll = self._log_likelihood(data, domain, theta_new, bias_new, sigma2_new)
            history.append(ll)

            theta = theta_new
            bias = bias_new
            sigma2 = sigma2_new

            if len(history) > 1 and abs(history[-1] - history[-2]) < self.tol:
                break

        for system in systems:
            key = (system, domain)
            self.system_estimates_[key] = theta[system]
            self.uncertainty_[key] = uncertainty[system]

        for observer in observers:
            key = (observer, domain)
            self.observer_bias_[key] = bias[observer]
            self.observer_variance_[key] = sigma2[observer]
            self.observer_reliability_[key] = 1.0 / sigma2[observer]

        self.log_likelihood_history_[domain] = history
        self.n_iter_[domain] = iteration + 1
        self.converged_[domain] = (iteration + 1) < self.max_iter

    def _compute_governance_metrics(self, data: pd.DataFrame, stakes: Dict[tuple, float]):
        for (system, domain), group in data.groupby(["system", "domain"]):
            key = (system, domain)
            corrected = []
            weights = []

            for _, row in group.iterrows():
                observer_key = (row["observer"], domain)
                corrected.append(row["value"] - self.observer_bias_.get(observer_key, 0.0))
                weights.append(row["_horizon_weight"] * self.observer_reliability_.get(observer_key, 1.0))

            disagreement = weighted_variance(corrected, weights)
            fragility = self._consensus_fragility(group, key)
            uncertainty = self.uncertainty_.get(key, 0.0)
            stake = stakes.get(key, stakes.get(system, 1.0))

            self.credible_disagreement_[key] = disagreement
            self.consensus_fragility_[key] = fragility
            self.epistemic_risk_[key] = epistemic_risk(uncertainty, disagreement, fragility, stake)

    def _compute_observer_reports(self, data: pd.DataFrame, gold: Optional[pd.DataFrame]):
        rows = []
        all_domains = set(data["domain"].unique())
        gold_map = {}
        if gold is not None:
            gold_map = {
                (row["system"], row["domain"]): row["value"]
                for _, row in gold.iterrows()
            }

        for (observer, domain), group in data.groupby(["observer", "domain"]):
            key = (observer, domain)
            gold_errors = []
            confidences = []

            if gold_map:
                for _, row in group.iterrows():
                    label_key = (row["system"], domain)
                    if label_key in gold_map:
                        if "confidence" in row and not pd.isna(row["confidence"]):
                            gold_errors.append(row["value"] - gold_map[label_key])
                            confidences.append(row["confidence"])

            calibration = confidence_calibration_error(confidences, gold_errors, self.value_range_)
            allowed = self.observer_horizons_.get(observer, all_domains)
            coverage = len(set(allowed) & all_domains) / max(len(all_domains), 1)

            rows.append({
                "observer": observer,
                "domain": domain,
                "reliability": self.observer_reliability_.get(key, np.nan),
                "variance": self.observer_variance_.get(key, np.nan),
                "bias": self.observer_bias_.get(key, np.nan),
                "calibration_error": calibration,
                "coverage": coverage,
                "n_observations": len(group),
            })

        self.observer_report_ = pd.DataFrame(rows).sort_values(
            ["domain", "reliability"],
            ascending=[True, False],
        ).reset_index(drop=True)

    def _consensus_fragility(self, group: pd.DataFrame, key: tuple) -> float:
        full_estimate = self.system_estimates_.get(key, np.nan)
        if pd.isna(full_estimate) or len(group) <= 1:
            return 0.0

        domain = key[1]
        cluster_col = "observer_group" if "observer_group" in group.columns else "observer"
        max_delta = 0.0

        for cluster in group[cluster_col].dropna().unique():
            remaining = group[group[cluster_col] != cluster]
            if remaining.empty:
                continue

            num = 0.0
            denom = 0.0
            for _, row in remaining.iterrows():
                observer_key = (row["observer"], domain)
                weight = row["_horizon_weight"] * self.observer_reliability_.get(observer_key, 1.0)
                num += weight * (row["value"] - self.observer_bias_.get(observer_key, 0.0))
                denom += weight

            if denom > 0:
                estimate_without_cluster = num / denom
                max_delta = max(max_delta, abs(full_estimate - estimate_without_cluster))

        return float(max_delta)

    def _horizon_weight(self, observer: str, domain: str) -> float:
        if not self.observer_horizons_:
            return 1.0
        if observer not in self.observer_horizons_:
            return 1.0
        return 1.0 if domain in self.observer_horizons_[observer] else self.out_of_horizon_weight

    def _log_likelihood(self, data, domain, theta, bias, sigma2):
        domain_data = data[data["domain"] == domain]
        total = 0.0
        for _, row in domain_data.iterrows():
            observer = row["observer"]
            residual = row["value"] - bias[observer] - theta[row["system"]]
            variance = sigma2[observer]
            total += row["_horizon_weight"] * (residual ** 2 / variance + np.log(variance))
        return -0.5 * total

    def _prepare_gold(self, gold_labels):
        if gold_labels is None:
            return None
        gold = gold_labels.copy()
        required = {"system", "domain", "value"}
        if not required.issubset(gold.columns):
            missing = required - set(gold.columns)
            raise ValueError(f"Gold labels missing columns: {missing}")
        gold["system"] = gold["system"].astype(str)
        gold["domain"] = gold["domain"].astype(str)
        gold["value"] = gold["value"].astype(float)
        return gold

    def _gold_systems(self, gold):
        if gold is None:
            return set()
        return set(gold["system"].unique())

    def _gold_map(self, gold):
        if gold is None:
            return {}
        return {row["system"]: row["value"] for _, row in gold.iterrows()}

    def _validate_judgments(self, judgments):
        required = {"observer", "system", "domain", "value"}
        if not required.issubset(judgments.columns):
            missing = required - set(judgments.columns)
            raise ValueError(f"Missing columns: {missing}")
        if judgments["value"].isnull().any():
            raise ValueError("Judgment values contain NaN")
        if self.method not in {"mle", "bayesian"}:
            raise ValueError("method must be 'mle' or 'bayesian'")
