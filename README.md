# REIM

**Reticular Epistemic Inference Model.** A framework for inferring the true properties of a system from distributed, noisy, partial observations, by weighting each observation according to the inferred reliability of its source.

---

## The problem

Whenever many observers report on the same thing (product ratings, sensor readings, evaluations, survey responses, model judgements) the naive answer is to average them. Averaging assumes every observer is equally reliable. They never are. Some are consistent and well calibrated, some are vague, some are adversarial, and some are reporting on a version of the system that no longer exists.

REIM replaces the average with statistical inference. It estimates jointly the true property of each system and the reliability of each observer, then uses the second to weight the first. A reading from a consistently reliable source counts for more; a reading from a noisy or adversarial source counts for less. The model discovers which is which without being told.

## Why not a simple average

A simple average gives every voice equal weight, so a handful of careless or malicious observers can move the result at will. REIM instead learns a precision for each observer from the consistency of their observations, corrects for the age of an observation, and propagates estimates across a system hierarchy when one exists. Reliability is inferred from behaviour, not declared in advance.

## Origins: the Reticular Theory of Reality

REIM is derived from the Reticular Theory of Reality, a framework of ten axioms describing how an observer located inside a complex system must infer the system's properties from incomplete, local observations. The premise is general: every observer is internal to what they describe, their view is partial and noisy, and truth has to be reconstructed from the interaction of many limited viewpoints. The same condition holds for cosmological observation, scientific measurement, distributed sensing, and collective evaluation.

The full derivation, from the ten axioms to the computational model, is in the technical report (see [Documentation](#documentation)).

## How it works

Each observer `u` reports `r = θ + noise`, where `θ` is the system's true property and the observer's reliability is the inverse of their noise variance. The algorithm alternates two closed-form steps until convergence:

```
θ_p   = Σ( α_u · r_u,p ) / Σ( α_u )      # precision-weighted estimate of the system's truth
σ²_u  = mean( (r_u,p − θ_p)² )           # observer noise, so reliability is α_u = 1 / σ²_u
```

Convergence is guaranteed: each step is a closed-form maximiser of the log-likelihood, so the likelihood is monotonically non-decreasing and the process reaches a stationary point. A Bayesian variant adds priors, giving regularisation for sparsely observed systems and an uncertainty estimate per result.

## Variants

| Variant | For |
|---|---|
| Base (MLE / Bayesian) | standard batch estimation, with uncertainty quantification |
| H-REIM | hierarchical systems, with bottom-up emergence and directional observability |
| Online | real-time, incremental `O(1)` updates per new observation |
| MultiDimensional | multi-phase, multi-criteria analysis with temporal decay |
| AuditREIM (design) | AI governance and audit of model/agent judgments |

## Validated results

On synthetic data with known ground truth:

- Up to **93% RMSE reduction** versus simple averaging with 20% adversarial observers. As the adversarial share rises to 40% the REIM error stays nearly flat while simple averaging degrades linearly.
- **Fake-source detection F1 of 85.7%** (100% precision, 75% recall) on the review-platform demo.
- The online variant processes roughly **16,000 observations per second**.

Full tables, baselines, and methodology are in the technical report.

## Documentation

The complete framework, from the ten axioms through the mathematics, the hierarchical extension, the online and multidimensional variants, and the experimental results, is documented in the technical report:

> [Reticular Epistemic Inference Model (REIM): full technical report](<docs/Reticular Epistemic Inference Model (REIM).md>)

A proposed governance extension is documented separately:

> [AuditREIM: Governance and AI Judgment Audit](<docs/AuditREIM - Governance and AI Judgment Audit.md>)

## Quick start

```bash
# With Docker Compose
docker compose up --build

# Without Docker
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API docs at `http://localhost:8000/docs`. Tests with `pytest tests/ -v`.

## API

**Batch** (fit a model on a complete set of observations; best for periodic recalculation):

```bash
curl -X POST http://localhost:8000/api/v1/batch/fit \
  -H "Content-Type: application/json" \
  -d '{"observations":[{"observer":"u1","system":"a","value":4.5},
                       {"observer":"u2","system":"a","value":5.0}],
       "method":"bayesian"}'
```

**Online** (real-time, each observation updates estimates in `O(1)`):

```bash
curl -X POST http://localhost:8000/api/v1/online/init    -d '{"instance_id":"my-platform"}'
curl -X POST http://localhost:8000/api/v1/online/observe -d '{"instance_id":"my-platform","observer":"u1","system":"a","value":4.5}'
curl      http://localhost:8000/api/v1/online/my-platform/state
```

**Multi-dimensional** (structured, multi-phase analysis; `phase_type` is a free-form domain label):

```bash
curl http://localhost:8000/api/v1/multidim/phase-types   # example product-review lifecycle
curl -X POST http://localhost:8000/api/v1/multidim/fit -H "Content-Type: application/json" -d '{ ... }'
```

## Configuration

Configured through environment variables (see `.env.example`). Key values:

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Service port |
| `MAX_ONLINE_INSTANCES` | `100` | Max concurrent online models |
| `MAX_BATCH_OBSERVATIONS` | `1000000` | Max observations per batch |
| `REIM_VALUE_MIN` / `REIM_VALUE_MAX` | `1.0` / `5.0` | Observation value bounds (domain-dependent) |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `ALLOWED_HOSTS` | `*` | Access control (IPs, CIDR, hostnames, domains, `docker`) |

**Access control.** The service restricts connections via `ALLOWED_HOSTS`. Set it explicitly in production (for example `docker,yourdomain.com`) so only your application reaches the API; external requests receive `403`. The `/health` endpoint and loopback are always allowed. For defence in depth, combine with network-level restrictions.

## Project structure

```
reim/
├── app/         # FastAPI: endpoints, schemas, access-control middleware
├── reim/        # model: base, online, hierarchical, multidim, metrics, baselines
├── tests/       # library, API, and middleware tests
├── docs/        # technical report (the full framework)
├── INTEGRATION.md
└── Dockerfile / docker-compose.yml
```

## License

REIM uses a dual licensing structure:

- Source code is licensed under the **GNU Affero General Public License v3.0 or later**. See [LICENSE](LICENSE).
- Documentation, technical reports, diagrams, and explanatory theory text are licensed under **Creative Commons Attribution-NonCommercial 4.0 International** unless otherwise stated. See [LICENSE-DOCS.md](LICENSE-DOCS.md).

Commercial licensing is available separately by written agreement with the author.

## Author

REIM is designed and built by Mariano Viola, as part of ongoing work on inference and governance for AI-native systems. The theory behind it is the author's own.
