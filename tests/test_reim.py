"""
Tests for the REIM library core modules.
"""

import pytest
import numpy as np
import pandas as pd

from reim import REIM, OnlineREIM, SyntheticDataGenerator, compute_metrics
from reim.baselines import SimpleAverage, TrimmedMean, MedianEstimator


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def simple_observations():
    """Minimal observation set for quick tests."""
    return pd.DataFrame([
        {"observer": "u1", "system": "p1", "value": 4.5},
        {"observer": "u1", "system": "p2", "value": 2.0},
        {"observer": "u2", "system": "p1", "value": 5.0},
        {"observer": "u2", "system": "p2", "value": 2.5},
        {"observer": "u3", "system": "p1", "value": 4.0},
        {"observer": "u3", "system": "p2", "value": 3.0},
    ])


@pytest.fixture
def synthetic_data():
    """Synthetic dataset with known ground truth."""
    gen = SyntheticDataGenerator(
        n_systems=20, n_observers=50,
        adversarial_fraction=0.1, density=0.5, seed=42,
    )
    return gen.generate()


# ============================================================
# BATCH REIM
# ============================================================

class TestBatchREIM:

    def test_fit_mle(self, simple_observations):
        model = REIM(method="mle")
        model.fit(simple_observations)
        assert model.converged_
        assert len(model.system_estimates_) == 2
        assert len(model.observer_reliability_) == 3

    def test_fit_bayesian(self, simple_observations):
        model = REIM(method="bayesian")
        model.fit(simple_observations)
        assert model.converged_
        assert len(model.uncertainty_) == 2
        for unc in model.uncertainty_.values():
            assert unc > 0

    def test_estimates_reasonable(self, simple_observations):
        model = REIM(method="bayesian")
        model.fit(simple_observations)
        # p1 should be higher than p2
        assert model.system_estimates_["p1"] > model.system_estimates_["p2"]

    def test_predict_returns_dataframe(self, simple_observations):
        model = REIM(method="bayesian")
        model.fit(simple_observations)
        df = model.predict()
        assert isinstance(df, pd.DataFrame)
        assert "system" in df.columns
        assert "estimate" in df.columns
        assert "uncertainty" in df.columns
        assert len(df) == 2

    def test_observer_report(self, simple_observations):
        model = REIM(method="bayesian")
        model.fit(simple_observations)
        report = model.get_observer_report()
        assert isinstance(report, pd.DataFrame)
        assert len(report) == 3

    def test_log_likelihood_monotone(self, simple_observations):
        model = REIM(method="mle", max_iter=50, tol=1e-12)
        model.fit(simple_observations)
        ll = model.log_likelihood_history_
        for i in range(1, len(ll)):
            assert ll[i] >= ll[i - 1] - 1e-10, f"LL decreased at step {i}"

    def test_beats_simple_average(self, synthetic_data):
        obs, truth, info = synthetic_data
        model = REIM(method="bayesian")
        model.fit(obs)
        avg = SimpleAverage()
        avg.fit(obs)

        m_reim = compute_metrics(model.system_estimates_, truth)
        m_avg = compute_metrics(avg.system_estimates_, truth)
        assert m_reim["rmse"] < m_avg["rmse"]

    def test_invalid_input_raises(self):
        bad_df = pd.DataFrame({"a": [1], "b": [2]})
        model = REIM()
        with pytest.raises(ValueError):
            model.fit(bad_df)

    def test_nan_values_raise(self):
        df = pd.DataFrame([
            {"observer": "u1", "system": "p1", "value": float("nan")},
        ])
        model = REIM()
        with pytest.raises(ValueError):
            model.fit(df)


# ============================================================
# ONLINE REIM
# ============================================================

class TestOnlineREIM:

    def test_single_observe(self):
        model = OnlineREIM()
        result = model.observe("u1", "p1", 4.5)
        assert "system_estimate" in result
        assert "observer_precision" in result
        assert model.n_observations_ == 1

    def test_multiple_observations(self):
        model = OnlineREIM()
        model.observe("u1", "p1", 4.5)
        model.observe("u2", "p1", 5.0)
        model.observe("u3", "p1", 4.0)
        est = model.system_estimates_
        assert "p1" in est
        assert 3.0 < est["p1"] < 6.0

    def test_observe_batch(self, simple_observations):
        model = OnlineREIM()
        model.observe_batch(simple_observations)
        assert model.n_observations_ == 6
        assert len(model.system_estimates_) == 2

    def test_predict(self):
        model = OnlineREIM()
        model.observe("u1", "p1", 4.0)
        model.observe("u1", "p2", 2.0)
        df = model.predict()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_observer_report(self):
        model = OnlineREIM()
        model.observe("u1", "p1", 4.0)
        model.observe("u2", "p1", 5.0)
        report = model.get_observer_report()
        assert len(report) == 2

    def test_warm_start(self, simple_observations):
        batch = REIM(method="bayesian")
        batch.fit(simple_observations)

        online = OnlineREIM()
        online.warm_start(batch)

        assert len(online.system_estimates_) == 2
        assert len(online.observer_precision_) == 3


# ============================================================
# MULTI-DIMENSIONAL REIM
# ============================================================

class TestMultiDimensionalREIM:

    @pytest.fixture
    def sample_reviews(self):
        return [
            {
                "id": 1, "observer_id": 10, "system_id": 1,
                "phase_type": "usage", "phase_rating": 4,
                "created_at": "2026-03-01T10:00:00",
                "ratings": [
                    {"criteria_id": 1, "criteria_name": "Display", "rating": 5},
                    {"criteria_id": 2, "criteria_name": "Battery", "rating": 3},
                ],
            },
            {
                "id": 2, "observer_id": 11, "system_id": 1,
                "phase_type": "usage", "phase_rating": 5,
                "created_at": "2026-03-02T10:00:00",
                "ratings": [
                    {"criteria_id": 1, "criteria_name": "Display", "rating": 4},
                    {"criteria_id": 2, "criteria_name": "Battery", "rating": 4},
                ],
            },
            {
                "id": 3, "observer_id": 10, "system_id": 1,
                "phase_type": "purchase", "phase_rating": 5,
                "created_at": "2026-02-15T10:00:00",
                "ratings": [],
            },
            {
                "id": 4, "observer_id": 12, "system_id": 2,
                "phase_type": "usage", "phase_rating": 3,
                "created_at": "2026-03-01T10:00:00",
                "ratings": [
                    {"criteria_id": 3, "criteria_name": "Comfort", "rating": 4},
                ],
            },
        ]

    def test_fit(self, sample_reviews):
        from reim.multidim import MultiDimensionalREIM
        model = MultiDimensionalREIM(method="bayesian")
        model.fit(sample_reviews)
        assert model.system_scores_ is not None
        assert model.observer_reliability_ is not None

    def test_system_detail(self, sample_reviews):
        from reim.multidim import MultiDimensionalREIM
        model = MultiDimensionalREIM(method="bayesian")
        model.fit(sample_reviews)
        detail = model.get_system_detail("1")
        assert detail["overall_score"] is not None
        assert "usage" in detail["phases"]

    def test_dimensions_summary(self, sample_reviews):
        from reim.multidim import MultiDimensionalREIM
        model = MultiDimensionalREIM(method="bayesian")
        model.fit(sample_reviews)
        summary = model.get_dimensions_summary()
        assert len(summary) > 0
        assert "phase" in summary["type"].values or "criteria" in summary["type"].values

    def test_flag_suspicious(self, sample_reviews):
        from reim.multidim import MultiDimensionalREIM
        model = MultiDimensionalREIM(method="bayesian")
        model.fit(sample_reviews)
        flagged = model.flag_suspicious_observers(percentile=50)
        assert isinstance(flagged, pd.DataFrame)

    def test_empty_reviews_raises(self):
        from reim.multidim import MultiDimensionalREIM
        model = MultiDimensionalREIM()
        with pytest.raises(ValueError):
            model.fit([])

    def test_arbitrary_phase_types_accepted(self):
        """Any phase_type string works without configuration, used as its own label."""
        from reim.multidim import MultiDimensionalREIM
        reviews = [
            {"observer_id": 1, "system_id": 1, "phase_type": "onboarding", "phase_rating": 4, "ratings": []},
            {"observer_id": 2, "system_id": 1, "phase_type": "onboarding", "phase_rating": 5, "ratings": []},
        ]
        model = MultiDimensionalREIM(method="bayesian")
        model.fit(reviews)
        detail = model.get_system_detail("1")
        assert "onboarding" in detail["phases"]
        assert detail["phases"]["onboarding"]["label"] == "onboarding"


# ============================================================
# BASELINES
# ============================================================

class TestBaselines:

    def test_simple_average(self, simple_observations):
        model = SimpleAverage()
        model.fit(simple_observations)
        assert len(model.system_estimates_) == 2

    def test_trimmed_mean(self, simple_observations):
        model = TrimmedMean(trim_fraction=0.1)
        model.fit(simple_observations)
        assert len(model.system_estimates_) == 2

    def test_median(self, simple_observations):
        model = MedianEstimator()
        model.fit(simple_observations)
        assert len(model.system_estimates_) == 2


# ============================================================
# METRICS
# ============================================================

class TestMetrics:

    def test_compute_metrics(self):
        estimates = {"p1": 4.5, "p2": 2.5}
        truth = {"p1": 4.0, "p2": 3.0}
        m = compute_metrics(estimates, truth)
        assert "rmse" in m
        assert "kendall_tau" in m
        assert m["rmse"] > 0
