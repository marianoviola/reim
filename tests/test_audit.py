"""
Tests for AuditREIM governance and AI judgment audit.
"""

import pandas as pd
import pytest

from reim import AuditREIM


@pytest.fixture
def audit_judgments():
    return pd.DataFrame([
        {"observer": "clean", "system": "case_gold", "domain": "factuality", "value": 0.80, "confidence": 0.90, "observer_group": "human"},
        {"observer": "strict", "system": "case_gold", "domain": "factuality", "value": 0.60, "confidence": 0.70, "observer_group": "llm"},
        {"observer": "noisy", "system": "case_gold", "domain": "factuality", "value": 0.20, "confidence": 0.20, "observer_group": "llm"},
        {"observer": "clean", "system": "case_1", "domain": "factuality", "value": 0.70, "confidence": 0.80, "observer_group": "human"},
        {"observer": "strict", "system": "case_1", "domain": "factuality", "value": 0.50, "confidence": 0.65, "observer_group": "llm"},
        {"observer": "noisy", "system": "case_1", "domain": "factuality", "value": 0.10, "confidence": 0.20, "observer_group": "llm"},
        {"observer": "clean", "system": "case_2", "domain": "factuality", "value": 0.30, "confidence": 0.75, "observer_group": "human"},
        {"observer": "strict", "system": "case_2", "domain": "factuality", "value": 0.10, "confidence": 0.70, "observer_group": "llm"},
        {"observer": "noisy", "system": "case_2", "domain": "factuality", "value": 0.90, "confidence": 0.20, "observer_group": "llm"},
        {"observer": "legal_checker", "system": "case_1", "domain": "legal", "value": 0.40, "confidence": 0.80, "observer_group": "policy"},
        {"observer": "legal_checker", "system": "case_2", "domain": "legal", "value": 0.45, "confidence": 0.80, "observer_group": "policy"},
    ])


@pytest.fixture
def gold_labels():
    return pd.DataFrame([
        {"system": "case_gold", "domain": "factuality", "value": 0.80},
    ])


class TestAuditREIM:

    def test_fit_with_bias_and_gold(self, audit_judgments, gold_labels):
        model = AuditREIM(gold_precision=1000.0, bias_prior_precision=0.1)
        model.fit(audit_judgments, gold_labels=gold_labels)

        assert ("case_1", "factuality") in model.system_estimates_
        assert model.system_estimates_[("case_gold", "factuality")] == pytest.approx(0.80, abs=0.02)
        assert model.observer_bias_[("strict", "factuality")] < 0
        assert model.observer_reliability_[("clean", "factuality")] > model.observer_reliability_[("noisy", "factuality")]

    def test_predict_returns_governance_metrics(self, audit_judgments, gold_labels):
        model = AuditREIM()
        model.fit(audit_judgments, gold_labels=gold_labels)

        predictions = model.predict()

        assert {"system", "domain", "estimate", "credible_disagreement", "consensus_fragility", "epistemic_risk"}.issubset(predictions.columns)
        assert len(predictions) >= 3

    def test_observer_horizons_reject_out_of_scope(self, audit_judgments, gold_labels):
        model = AuditREIM()
        model.fit(
            audit_judgments,
            gold_labels=gold_labels,
            observer_horizons={"legal_checker": ["legal"]},
        )

        assert len(model.rejected_observations_) == 0
        assert ("legal_checker", "legal") in model.observer_reliability_

        mixed = pd.concat([
            audit_judgments,
            pd.DataFrame([{
                "observer": "legal_checker",
                "system": "case_1",
                "domain": "factuality",
                "value": 0.95,
            }]),
        ], ignore_index=True)

        model.fit(
            mixed,
            gold_labels=gold_labels,
            observer_horizons={"legal_checker": ["legal"]},
        )

        assert len(model.rejected_observations_) == 1
        assert model.rejected_observations_.iloc[0]["domain"] == "factuality"

    def test_observer_report_and_alerts(self, audit_judgments, gold_labels):
        model = AuditREIM()
        model.fit(audit_judgments, gold_labels=gold_labels)

        report = model.get_observer_report()
        alerts = model.get_alerts(disagreement_threshold=0.0, fragility_threshold=0.0, risk_threshold=0.0)

        assert {"observer", "domain", "reliability", "bias", "coverage"}.issubset(report.columns)
        assert len(alerts) > 0

    def test_invalid_input_raises(self):
        model = AuditREIM()
        with pytest.raises(ValueError):
            model.fit(pd.DataFrame({"observer": ["u1"], "value": [1.0]}))
