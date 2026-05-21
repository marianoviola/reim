"""
Multi-Dimensional REIM — Structured Review Analysis
=====================================================

Provides multi-dimensional analysis of structured reviews where each
review can contain multiple evaluation axes (e.g., sentiment phases,
criteria ratings, category-specific parameters).

Data Model:
- A Review belongs to a System (product, service, entity) and an Observer (user, rater)
- Each Review has:
    - phase_type: a categorical label for the review's context (e.g., a lifecycle phase)
    - phase_rating: a sentiment/experience score (1-5) for that phase
    - Multiple criteria ratings (one per evaluation criterion, rating 1-5)
- Criteria can be dynamic per domain (not hardcoded)
- Observers can submit multiple reviews for the same system over time

Hierarchy for REIM:
    Level 0: overall_score (emerges from level 1)
    Level 1: phase_score (avg of phase ratings), criteria_score (avg of criteria ratings)
    Level 2: individual phase ratings + individual criteria ratings

Phase types are not hardcoded: by default any categorical string is accepted
as a phase type. Domain-specific presets (e.g. a product-review lifecycle)
live in ``reim.examples``.
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any
from collections import defaultdict


# ============================================================
# DATA EXTRACTION HELPERS
# ============================================================

def extract_observations_from_reviews(reviews_data: List[Dict[str, Any]]) -> Dict[str, pd.DataFrame]:
    """
    Transform structured review data into REIM observation DataFrames.

    Expects a list of dicts with the following structure:
    [
        {
            "id": 1,
            "observer_id": 10,
            "system_id": 5,
            "phase_type": "usage",
            "phase_rating": 4,
            "created_at": "2026-01-15T10:30:00",
            "ratings": [
                {"criteria_id": 1, "criteria_name": "Display", "rating": 5},
                {"criteria_id": 2, "criteria_name": "Battery Life", "rating": 3},
            ]
        },
        ...
    ]

    Only the canonical field names shown above are accepted.

    Returns a dict of DataFrames:
    {
        "phase_<phase_type>": DataFrame[observer, system, value, timestamp],
        "criteria_<criteria_id>": DataFrame[observer, system, value, timestamp],
    }
    """
    dimension_obs: Dict[str, list] = defaultdict(list)

    for review in reviews_data:
        observer_id = str(review.get("observer_id"))
        system_id = str(review.get("system_id"))
        timestamp = review.get("created_at", None)

        # Phase observation (phase_rating for this phase_type)
        phase_type = review.get("phase_type")
        phase_rating = review.get("phase_rating")

        if phase_type and phase_rating is not None:
            dim_key = f"phase_{phase_type}"
            dimension_obs[dim_key].append({
                "observer": observer_id,
                "system": system_id,
                "value": float(phase_rating),
                "timestamp": timestamp,
            })

        # Criteria observations
        for rating_entry in review.get("ratings", []):
            criteria_id = rating_entry.get("criteria_id")
            criteria_name = rating_entry.get("criteria_name", f"criteria_{criteria_id}")
            rating_val = rating_entry.get("rating")

            if criteria_id is not None and rating_val is not None:
                dim_key = f"criteria_{criteria_id}"
                dimension_obs[dim_key].append({
                    "observer": observer_id,
                    "system": system_id,
                    "value": float(rating_val),
                    "timestamp": timestamp,
                    "_criteria_name": criteria_name,
                })

    # Convert to DataFrames
    result = {}
    for dim_key, obs_list in dimension_obs.items():
        result[dim_key] = pd.DataFrame(obs_list)

    return result


# ============================================================
# MULTI-DIMENSIONAL REIM
# ============================================================

class MultiDimensionalREIM:
    """
    Multi-dimensional REIM for structured review analysis.

    Runs independent REIM instances across multiple evaluation dimensions
    (phases and criteria), then aggregates into hierarchical scores.

    Parameters
    ----------
    phase_types : list of str or None
        Known phase type labels. If None (default), any phase_type string
        found in the data is accepted.
    phase_labels : dict or None
        Human-readable labels keyed by phase type. If None (default), each
        phase_type is used as its own label. Phases missing from the map
        also fall back to the phase_type string.
    temporal_decay : float, default=0.98
        Decay factor per month. 0.98 = observations lose 2% weight per month.
        Set to 1.0 to disable.
    method : str, default="bayesian"
        "mle" or "bayesian".
    max_iter : int, default=100
        Max iterations for REIM.
    tol : float, default=1e-6
        Convergence tolerance.
    suspicious_percentile : float, default=10
        Bottom percentile of reliability to flag as suspicious.
    """

    def __init__(
        self,
        phase_types: Optional[List[str]] = None,
        phase_labels: Optional[Dict[str, str]] = None,
        temporal_decay: float = 0.98,
        method: str = "bayesian",
        max_iter: int = 100,
        tol: float = 1e-6,
        suspicious_percentile: float = 10,
    ):
        self.phase_types = phase_types
        self.phase_labels = phase_labels or {}
        self.temporal_decay = temporal_decay
        self.method = method
        self.max_iter = max_iter
        self.tol = tol
        self.suspicious_percentile = suspicious_percentile

        # Results
        self.system_scores_: Optional[pd.DataFrame] = None
        self.observer_reliability_: Optional[pd.DataFrame] = None
        self.dimension_estimates_: Dict[str, dict] = {}
        self.dimension_uncertainty_: Dict[str, dict] = {}
        self.dimension_labels_: Dict[str, str] = {}  # dim_key -> human label
        self.models_: Dict = {}
        self.criteria_map_: Dict[str, str] = {}  # criteria_key -> criteria_name

    def fit(
        self,
        reviews_data: List[Dict[str, Any]],
        criteria_metadata: Optional[Dict[int, str]] = None,
    ) -> "MultiDimensionalREIM":
        """
        Fit the model on structured review data.

        Parameters
        ----------
        reviews_data : list of dict
            Each dict represents a review with structure:
            {
                "id": int,
                "observer_id": int,
                "system_id": int,
                "phase_type": str,
                "phase_rating": int,
                "created_at": str,         # ISO datetime
                "ratings": [
                    {"criteria_id": int, "criteria_name": str, "rating": int},
                    ...
                ]
            }

        criteria_metadata : dict, optional
            {criteria_id: criteria_name} for labeling. If not provided,
            extracted from the ratings data.

        Returns
        -------
        self
        """
        from reim import REIM

        # Extract observations per dimension
        dimension_obs = extract_observations_from_reviews(reviews_data)

        if not dimension_obs:
            raise ValueError("No valid observations found in reviews_data")

        # Build criteria name map
        if criteria_metadata:
            self.criteria_map_ = {f"criteria_{k}": v for k, v in criteria_metadata.items()}
        else:
            # Auto-extract from data
            for dim_key, df in dimension_obs.items():
                if dim_key.startswith("criteria_") and "_criteria_name" in df.columns:
                    crit_name = df["_criteria_name"].iloc[0]
                    self.criteria_map_[dim_key] = crit_name

        # Build dimension labels
        for dim_key in dimension_obs:
            if dim_key.startswith("phase_"):
                phase = dim_key.replace("phase_", "")
                self.dimension_labels_[dim_key] = self.phase_labels.get(phase, phase)
            elif dim_key in self.criteria_map_:
                self.dimension_labels_[dim_key] = self.criteria_map_[dim_key]
            else:
                self.dimension_labels_[dim_key] = dim_key

        # Collect all system and observer IDs
        all_system_ids = set()
        all_observer_ids = set()
        for df in dimension_obs.values():
            all_system_ids.update(df["system"].unique())
            all_observer_ids.update(df["observer"].unique())

        # Fit REIM for each dimension
        observer_reliabilities: Dict[str, Dict[str, float]] = defaultdict(dict)

        for dim_key, obs_df in dimension_obs.items():
            if obs_df.empty:
                continue

            # Drop internal columns
            fit_df = obs_df[["observer", "system", "value"]].copy()

            model = REIM(method=self.method, max_iter=self.max_iter, tol=self.tol)
            model.fit(fit_df)

            self.models_[dim_key] = model
            self.dimension_estimates_[dim_key] = model.system_estimates_
            self.dimension_uncertainty_[dim_key] = model.uncertainty_

            for u, rel in model.observer_reliability_.items():
                observer_reliabilities[u][dim_key] = rel

        # Aggregate scores
        self.system_scores_ = self._aggregate_scores(sorted(all_system_ids))
        self.observer_reliability_ = self._aggregate_observer_reliability(observer_reliabilities)

        return self

    def get_system_report(self, system_id: Optional[str] = None) -> pd.DataFrame:
        """Get system quality report."""
        if self.system_scores_ is None:
            raise RuntimeError("Model not fitted.")
        if system_id:
            return self.system_scores_[self.system_scores_["system_id"] == str(system_id)]
        return self.system_scores_

    def get_system_detail(self, system_id) -> dict:
        """
        Detailed breakdown for a single system.

        Returns:
        {
            "system_id": str,
            "overall_score": float,
            "phase_score": float,
            "criteria_score": float,
            "phases": {phase_type: {"estimate": float, "uncertainty": float, "label": str}},
            "criteria": {criteria_key: {"estimate": float, "uncertainty": float, "label": str}},
        }
        """
        sid = str(system_id)
        result = {
            "system_id": sid,
            "overall_score": None,
            "phase_score": None,
            "criteria_score": None,
            "phases": {},
            "criteria": {},
        }

        phase_vals = []
        criteria_vals = []

        for dim_key in sorted(self.dimension_estimates_.keys()):
            estimates = self.dimension_estimates_[dim_key]
            uncertainties = self.dimension_uncertainty_.get(dim_key, {})

            est = estimates.get(sid, None)
            unc = uncertainties.get(sid, None)
            label = self.dimension_labels_.get(dim_key, dim_key)

            entry = {
                "estimate": round(est, 4) if est is not None else None,
                "uncertainty": round(unc, 4) if unc is not None else None,
                "label": label,
            }

            if dim_key.startswith("phase_"):
                phase = dim_key.replace("phase_", "")
                result["phases"][phase] = entry
                if est is not None:
                    phase_vals.append(est)
            elif dim_key.startswith("criteria_"):
                result["criteria"][dim_key] = entry
                if est is not None:
                    criteria_vals.append(est)

        result["phase_score"] = round(np.mean(phase_vals), 4) if phase_vals else None
        result["criteria_score"] = round(np.mean(criteria_vals), 4) if criteria_vals else None

        components = [v for v in [result["phase_score"], result["criteria_score"]] if v is not None]
        result["overall_score"] = round(np.mean(components), 4) if components else None

        return result

    def get_observer_report(self) -> pd.DataFrame:
        """Get observer reliability report."""
        if self.observer_reliability_ is None:
            raise RuntimeError("Model not fitted.")
        return self.observer_reliability_

    def flag_suspicious_observers(self, percentile: Optional[float] = None) -> pd.DataFrame:
        """Flag observers below the given reliability percentile."""
        pct = percentile if percentile is not None else self.suspicious_percentile
        report = self.observer_reliability_
        threshold = report["overall_reliability"].quantile(pct / 100)
        return report[report["overall_reliability"] <= threshold].copy()

    def get_dimensions_summary(self) -> pd.DataFrame:
        """List all dimensions with their labels and observation counts."""
        rows = []
        for dim_key, model in self.models_.items():
            rows.append({
                "dimension": dim_key,
                "label": self.dimension_labels_.get(dim_key, dim_key),
                "type": "phase" if dim_key.startswith("phase_") else "criteria",
                "n_systems": len(model.system_estimates_),
                "n_observers": len(model.observer_reliability_),
                "converged": model.converged_,
                "n_iter": model.n_iter_,
            })
        return pd.DataFrame(rows)

    # ---- Internal ----

    def _aggregate_scores(self, system_ids: list) -> pd.DataFrame:
        """Build system score table with hierarchical aggregation."""
        rows = []
        for sid in system_ids:
            row: Dict[str, Any] = {"system_id": sid}

            phase_vals = []
            criteria_vals = []

            for dim_key in self.dimension_estimates_:
                est = self.dimension_estimates_[dim_key].get(sid)
                unc = self.dimension_uncertainty_.get(dim_key, {}).get(sid)
                label = self.dimension_labels_.get(dim_key, dim_key)

                row[dim_key] = est
                row[f"{dim_key}_unc"] = unc
                row[f"{dim_key}_label"] = label

                if est is not None:
                    if dim_key.startswith("phase_"):
                        phase_vals.append(est)
                    elif dim_key.startswith("criteria_"):
                        criteria_vals.append(est)

            row["phase_score"] = np.mean(phase_vals) if phase_vals else None
            row["criteria_score"] = np.mean(criteria_vals) if criteria_vals else None

            components = [v for v in [row["phase_score"], row["criteria_score"]] if v is not None]
            row["overall_score"] = np.mean(components) if components else None

            rows.append(row)

        return pd.DataFrame(rows)

    def _aggregate_observer_reliability(self, observer_reliabilities: dict) -> pd.DataFrame:
        """Aggregate per-dimension reliability into overall observer reliability."""
        rows = []
        for observer, dim_rels in observer_reliabilities.items():
            rels = list(dim_rels.values())
            rows.append({
                "observer_id": observer,
                "overall_reliability": np.mean(rels) if rels else 0,
                "min_reliability": np.min(rels) if rels else 0,
                "max_reliability": np.max(rels) if rels else 0,
                "n_dimensions": len(rels),
            })
        df = pd.DataFrame(rows)
        return df.sort_values("overall_reliability", ascending=False).reset_index(drop=True)
