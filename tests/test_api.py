"""
Tests for the FastAPI endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================
# HEALTH
# ============================================================

class TestHealth:

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "version" in data


# ============================================================
# BATCH REIM
# ============================================================

class TestBatchEndpoint:

    def test_fit_basic(self, client):
        r = client.post("/api/v1/batch/fit", json={
            "observations": [
                {"observer": "u1", "system": "p1", "value": 4.5},
                {"observer": "u1", "system": "p2", "value": 2.0},
                {"observer": "u2", "system": "p1", "value": 5.0},
                {"observer": "u2", "system": "p2", "value": 2.5},
            ],
            "method": "bayesian",
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data["systems"]) == 2
        assert len(data["observers"]) == 2
        assert data["converged"] is True

    def test_fit_too_few(self, client):
        r = client.post("/api/v1/batch/fit", json={
            "observations": [
                {"observer": "u1", "system": "p1", "value": 4.5},
            ],
        })
        assert r.status_code == 400

    def test_fit_invalid_value(self, client):
        r = client.post("/api/v1/batch/fit", json={
            "observations": [
                {"observer": "u1", "system": "p1", "value": 10.0},
                {"observer": "u2", "system": "p1", "value": 4.0},
            ],
        })
        assert r.status_code == 422  # Pydantic validation


# ============================================================
# ONLINE REIM
# ============================================================

class TestOnlineEndpoints:

    def test_lifecycle(self, client):
        # Init
        r = client.post("/api/v1/online/init", json={"instance_id": "test-1"})
        assert r.status_code == 200

        # Observe
        r = client.post("/api/v1/online/observe", json={
            "instance_id": "test-1",
            "observer": "u1", "system": "p1", "value": 4.5,
        })
        assert r.status_code == 200
        assert r.json()["total_observations"] == 1

        # State
        r = client.get("/api/v1/online/test-1/state")
        assert r.status_code == 200
        assert r.json()["n_systems"] == 1

        # List
        r = client.get("/api/v1/online")
        assert r.status_code == 200
        assert len(r.json()["instances"]) >= 1

        # Delete
        r = client.delete("/api/v1/online/test-1")
        assert r.status_code == 200

    def test_observe_batch(self, client):
        client.post("/api/v1/online/init", json={"instance_id": "test-batch"})
        r = client.post("/api/v1/online/observe-batch", json={
            "instance_id": "test-batch",
            "observations": [
                {"observer": "u1", "system": "p1", "value": 4.0},
                {"observer": "u2", "system": "p1", "value": 5.0},
            ],
        })
        assert r.status_code == 200
        assert r.json()["observations_processed"] == 2
        client.delete("/api/v1/online/test-batch")

    def test_not_found(self, client):
        r = client.get("/api/v1/online/nonexistent/state")
        assert r.status_code == 404

    def test_duplicate_init(self, client):
        client.post("/api/v1/online/init", json={"instance_id": "test-dup"})
        r = client.post("/api/v1/online/init", json={"instance_id": "test-dup"})
        assert r.status_code == 409
        client.delete("/api/v1/online/test-dup")


# ============================================================
# MULTI-DIMENSIONAL REIM
# ============================================================

class TestMultiDimEndpoints:

    def test_phase_types(self, client):
        r = client.get("/api/v1/multidim/phase-types")
        assert r.status_code == 200
        data = r.json()
        assert "pre_purchase" in data["phase_types"]
        assert len(data["phase_types"]) == 5

    def test_fit(self, client):
        r = client.post("/api/v1/multidim/fit", json={
            "reviews": [
                {
                    "observer_id": 1, "system_id": 1,
                    "phase_type": "usage", "phase_rating": 4,
                    "ratings": [
                        {"criteria_id": 1, "criteria_name": "Display", "rating": 5},
                    ],
                },
                {
                    "observer_id": 2, "system_id": 1,
                    "phase_type": "usage", "phase_rating": 3,
                    "ratings": [
                        {"criteria_id": 1, "criteria_name": "Display", "rating": 4},
                    ],
                },
            ],
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data["systems"]) == 1
        assert data["n_dimensions"] > 0

    def test_fit_empty(self, client):
        r = client.post("/api/v1/multidim/fit", json={"reviews": []})
        assert r.status_code == 400

    def test_fit_with_metadata(self, client):
        r = client.post("/api/v1/multidim/fit", json={
            "reviews": [
                {
                    "observer_id": 1, "system_id": 1,
                    "phase_type": "purchase", "phase_rating": 5,
                    "ratings": [
                        {"criteria_id": 10, "rating": 4},
                    ],
                },
                {
                    "observer_id": 2, "system_id": 1,
                    "phase_type": "purchase", "phase_rating": 4,
                    "ratings": [
                        {"criteria_id": 10, "rating": 3},
                    ],
                },
            ],
            "criteria_metadata": {"10": "Build Quality"},
        })
        assert r.status_code == 200
        data = r.json()
        # Check that the label was applied
        has_label = any(
            d["label"] == "Build Quality"
            for s in data["systems"] for d in s["criteria"]
        )
        assert has_label
