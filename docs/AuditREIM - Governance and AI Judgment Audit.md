# AuditREIM: Governance and AI Judgment Audit

## Purpose

AuditREIM is a domain-specific extension of REIM for AI governance: auditing judgments made by agents, models, prompts, policies, or human reviewers over claims, tasks, decisions, and generated outputs.

The goal is not to replace Base REIM, H-REIM, Online REIM, or MultiDimensionalREIM. The goal is to separate governance-specific concepts from product-review analysis and make explicit the additional epistemic quantities needed for responsible AI oversight:

- reliability by domain;
- systematic bias;
- calibration against gold cases;
- disagreement among credible observers;
- drift across model, prompt, and policy versions;
- fragility of consensus under observer removal.

In REIM terms, AuditREIM remains a model of distributed, noisy, partial observation. It simply treats AI judgments as epistemic observations inside a governance system.

---

## Mapping to REIM

| REIM Concept | AuditREIM Interpretation |
|---|---|
| Observer `u` | agent, model, prompt version, evaluator, policy checker, human reviewer |
| System `p` | claim, task, generated answer, decision, incident, evaluation item |
| Observation `r_{u,p}` | judgment score, verdict, risk rating, correctness estimate |
| Dimension `d` | factuality, safety, legal, policy compliance, quality, bias, usefulness |
| Reliability `α_u` | inferred precision of an observer's judgments |
| Epistemic horizon | what an observer can validly judge given role, tools, access, and domain |
| Hierarchy | organization, workflow, task taxonomy, model chain, policy stack |
| Temporal decay | model/prompt/policy drift over time |

AuditREIM should be a separate variant because governance judgments have structure that ordinary product reviews do not: known calibration cases, explicit policies, versioned observers, domain-specific authority, and high-stakes disagreement.

---

## Generative Model

Base REIM assumes:

```text
r_u,p = θ_p + ε_u,p
ε_u,p ~ Normal(0, σ²_u)
```

AuditREIM extends this with domain and bias:

```text
r_u,p,d = θ_p,d + b_u,d + ε_u,p,d
ε_u,p,d ~ Normal(0, σ²_u,d)
```

Where:

- `θ_p,d` is the latent audit truth or quality for item `p` in domain `d`;
- `b_u,d` is systematic observer bias in that domain;
- `σ²_u,d` is observer noise in that domain;
- `α_u,d = 1 / σ²_u,d` is domain-specific reliability.

This distinction matters in governance because an observer can be consistent but biased. Without `b_u,d`, REIM may confuse systematic severity, leniency, or policy skew with reliability.

---

## Calibration Anchors

AuditREIM should support a subset of systems with known or externally adjudicated values:

```text
G = {p : θ_p,d is known for one or more domains}
```

These are gold cases, red-team fixtures, resolved incidents, human-adjudicated decisions, or benchmark tasks.

Gold cases perform three functions:

1. anchor the latent truth estimate and reduce circularity;
2. estimate observer bias directly;
3. detect drift after model, prompt, policy, or tool changes.

For gold items:

```text
θ_p,d := y_p,d
```

or, more softly:

```text
θ_p,d ~ Normal(y_p,d, τ_gold²)
```

The soft form is preferable when human adjudication itself may be noisy.

---

## Epistemic Horizons for Agents

AuditREIM should not let every observer judge every domain equally.

Each observer has a domain horizon:

```text
H(u) ⊆ D
```

and optionally a hierarchical horizon:

```text
Ω(u) = {p^(k) : k ≤ level(u)} ∩ H(u)
```

This preserves the original REIM principle that observers are internal to a system and have limited, directional knowledge. In AI audit terms:

- a factuality checker should not dominate legal judgment;
- a policy checker should not be treated as a UX evaluator;
- a model with no tool access should be attenuated on claims requiring retrieval;
- an upstream agent should not be assumed to know downstream emergent effects.

When an observer judges outside its horizon, AuditREIM should either reject the observation or attenuate precision:

```text
α_eff(u,d) = α_u,d · h_u,d
```

where `h_u,d ∈ [0,1]` is a horizon weight.

---

## Inference Loop

AuditREIM can use coordinate ascent like Base REIM:

1. initialize `θ_p,d` from observed means or gold anchors;
2. estimate observer bias `b_u,d`;
3. estimate latent item truth `θ_p,d` using bias-corrected observations;
4. estimate observer variance `σ²_u,d`;
5. compute uncertainty, disagreement, and risk metrics;
6. repeat until convergence.

Bias update:

```text
b_u,d = mean_p(r_u,p,d - θ_p,d)
```

Truth update:

```text
θ_p,d = Σ_u α_u,d · h_u,d · (r_u,p,d - b_u,d) / Σ_u α_u,d · h_u,d
```

Variance update:

```text
σ²_u,d = mean_p((r_u,p,d - b_u,d - θ_p,d)²)
```

Bayesian priors are important for sparse governance data:

- weak prior over `θ_p,d`;
- shrinkage prior over `b_u,d`;
- inverse-gamma prior over `σ²_u,d`;
- stronger prior for gold-calibrated domains.

---

## Governance Metrics

AuditREIM should output more than scores.

### Observer Metrics

| Metric | Meaning |
|---|---|
| `domain_reliability` | precision by domain |
| `observer_bias` | systematic severity/leniency by domain |
| `calibration_error` | mismatch between confidence and correctness |
| `drift_score` | change in reliability or bias across versions/time |
| `coverage` | portion of domains/items within observer horizon |

### Item Metrics

| Metric | Meaning |
|---|---|
| `latent_score` | bias-corrected inferred judgment |
| `uncertainty` | standard error or posterior uncertainty |
| `credible_disagreement` | disagreement among high-reliability observers |
| `consensus_fragility` | sensitivity to removing observers or observer clusters |
| `epistemic_risk` | high-stakes uncertainty/disagreement score |

### System Metrics

| Metric | Meaning |
|---|---|
| `monoculture_risk` | excessive correlation among observers |
| `collusion_suspicion` | suspiciously aligned residual patterns |
| `domain_coverage_gap` | domains lacking reliable observers |
| `policy_drift` | shift after policy/prompt/model updates |

---

## Consensus Fragility

For high-stakes audit, the question is not only “what is the consensus?” but “how fragile is it?”

Define:

```text
F_p,d = max_g |θ_p,d - θ_p,d^(-g)|
```

where `g` is an observer or observer cluster removed from inference.

High fragility means the result depends too much on a single model family, prompt style, team, or policy checker.

---

## Disagreement as Signal

REIM treats noise as something to reduce. AuditREIM should also treat disagreement as something to inspect.

High disagreement among unreliable observers is expected. High disagreement among reliable observers is epistemically important.

```text
credible_disagreement_p,d =
    weighted_variance({r_u,p,d - b_u,d}, weights=α_u,d)
```

Items with high credible disagreement should be routed to human review, red-team analysis, or policy escalation.

---

## Versioning and Drift

Observers in AuditREIM should be versioned:

```text
observer_id = model_id + prompt_id + policy_version + toolset_version
```

The same base model under a different prompt or policy is a different epistemic observer. This is consistent with REIM's observer-local reliability: reliability belongs to the situated observer, not to an abstract model name.

Drift can be measured as:

```text
drift(u,d,t) =
    distance((α_u,d,t, b_u,d,t), (α_u,d,t-1, b_u,d,t-1))
```

Gold cases should be replayed after every significant version change.

---

## API Shape

### Fit

```http
POST /api/v1/audit/fit
```

```json
{
  "judgments": [
    {
      "observer_id": "gpt-judge:v1:policy-2026-03",
      "system_id": "claim-184",
      "domain": "factuality",
      "value": 0.82,
      "confidence": 0.74,
      "timestamp": "2026-06-05T10:00:00Z",
      "observer_group": "llm_judges",
      "metadata": {
        "model": "judge-model",
        "prompt_version": "v1",
        "tool_access": "retrieval"
      }
    }
  ],
  "gold_labels": [
    {
      "system_id": "claim-184",
      "domain": "factuality",
      "value": 1.0,
      "confidence": 0.95
    }
  ],
  "observer_horizons": {
    "legal-checker:v2": ["legal", "policy"],
    "retrieval-checker:v1": ["factuality"]
  },
  "method": "bayesian"
}
```

### Response

```json
{
  "systems": [
    {
      "system_id": "claim-184",
      "domain": "factuality",
      "latent_score": 0.91,
      "uncertainty": 0.08,
      "credible_disagreement": 0.12,
      "consensus_fragility": 0.19,
      "epistemic_risk": 0.31
    }
  ],
  "observers": [
    {
      "observer_id": "gpt-judge:v1:policy-2026-03",
      "domain": "factuality",
      "reliability": 4.8,
      "bias": -0.07,
      "calibration_error": 0.11,
      "coverage": 0.72
    }
  ],
  "alerts": [
    {
      "type": "credible_disagreement",
      "system_id": "claim-184",
      "domain": "factuality",
      "severity": "medium"
    }
  ]
}
```

---

## Relationship to Original REIM Axioms

AuditREIM is compatible with the original epistemic foundation.

| Axiom | AuditREIM Correspondence |
|---|---|
| Reticularity | agents, tasks, policies, domains, and tools form a graph of judgments |
| System Emergence | governance state emerges from many local judgments |
| Level Generation | audits can be organized by claim, task, workflow, product, organization |
| Subsystem Multiplicity | domains such as safety, factuality, legal, and quality evolve semi-independently |
| Consciousness Emergence | agents/humans are treated as observers inside the governance system |
| Origin-Oriented Awareness | observers know local context and upward artifacts, not all downstream effects |
| Epistemic Hierarchy | observers have role/domain-dependent access |
| Observability Horizons | observer horizons and horizon weights formalize bounded judgment |
| Relative Subsystem Autonomy | domain-specific reliability and bias avoid collapsing all judgment into one score |
| Internal Knowledge Incompleteness | gold anchors reduce uncertainty but do not claim absolute truth |

The most important conceptual addition is `bias`. This is not a break from REIM: it refines the observation-noise model by separating systematic distortion from random error. In epistemic terms, it distinguishes limited perspective from unstable perception.

---

## Recommended Implementation Boundary

Keep AuditREIM separate from MultiDimensionalREIM.

Suggested module layout:

```text
reim/
  audit.py              # AuditREIM model
  audit_metrics.py      # disagreement, fragility, calibration, drift
app/
  audit_schemas.py      # governance request/response schemas
  main.py               # /api/v1/audit endpoints
tests/
  test_audit.py
  test_audit_api.py
docs/
  AuditREIM - Governance and AI Judgment Audit.md
```

This prevents product-review assumptions from leaking into AI governance while preserving the common REIM kernel.

---

## Development Priorities

1. implement `AuditREIM` with domain-specific reliability and observer bias;
2. add gold-label calibration;
3. add credible disagreement and consensus fragility metrics;
4. add observer horizons;
5. add versioned observer drift;
6. add API endpoints only after the library model is tested.

The first production-grade version should prioritize interpretability over complexity. The value of AuditREIM is not only better aggregation; it is the ability to explain why a judgment was trusted, distrusted, escalated, or overridden.
