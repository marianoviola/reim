"""
REIM Microservice — FastAPI Application

Endpoints:
  POST /api/v1/batch/fit              — Fit batch REIM on observations
  POST /api/v1/online/init            — Initialize an online REIM instance
  POST /api/v1/online/observe         — Send a single observation
  POST /api/v1/online/observe-batch   — Send multiple observations
  GET  /api/v1/online/{id}/state      — Get current estimates
  DELETE /api/v1/online/{id}          — Delete an online instance
  GET  /api/v1/online                 — List all online instances
  GET  /api/v1/multidim/phase-types   — List configured phase types
  POST /api/v1/multidim/fit           — Fit MultiDimensionalREIM
  GET  /health                        — Health check

Access Control:
  Set ALLOWED_HOSTS to restrict access. See app/middleware.py for details.
  Default: no restriction (development).
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Dict

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from reim import REIM
from reim.online import OnlineREIM
from reim.multidim import MultiDimensionalREIM, DEFAULT_PHASE_TYPES, DEFAULT_PHASE_LABELS
from reim.baselines import SimpleAverage

from app.schemas import (
    BatchFitRequest, BatchFitResponse, SystemEstimate, ObserverReliability,
    OnlineInitRequest, OnlineObserveRequest, OnlineObserveBatchRequest,
    OnlineObserveResponse, OnlineStateResponse,
    MultiDimFitRequest, MultiDimFitResponse, SystemScore, DimensionScore,
    DimensionSummary, ObserverReliabilitySummary,
    HealthResponse, Observation,
)
from app.middleware import AccessControlMiddleware

# ============================================================
# CONFIGURATION
# ============================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MAX_ONLINE_INSTANCES = int(os.getenv("MAX_ONLINE_INSTANCES", "100"))
MAX_BATCH_OBSERVATIONS = int(os.getenv("MAX_BATCH_OBSERVATIONS", "1000000"))

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("reim-service")

# In-memory store for online model instances
online_instances: Dict[str, OnlineREIM] = {}


# ============================================================
# APP LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("REIM Service starting up...")
    yield
    logger.info("REIM Service shutting down. Online instances: %d", len(online_instances))
    online_instances.clear()


app = FastAPI(
    title="REIM Microservice",
    description="Reticular Epistemic Inference Model — API for inferring system truth from distributed noisy observations.",
    version="1.0.0",
    lifespan=lifespan,
)

# Access control — must be added BEFORE CORS
app.add_middleware(AccessControlMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEALTH
# ============================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        models_loaded=len(online_instances),
    )


# ============================================================
# BATCH REIM
# ============================================================

@app.post("/api/v1/batch/fit", response_model=BatchFitResponse, tags=["Batch REIM"])
async def batch_fit(request: BatchFitRequest):
    """
    Fit batch REIM on a set of observations.
    Returns system estimates, observer reliability, and convergence info.
    """
    if len(request.observations) > MAX_BATCH_OBSERVATIONS:
        raise HTTPException(400, f"Too many observations. Max: {MAX_BATCH_OBSERVATIONS}")

    if len(request.observations) < 2:
        raise HTTPException(400, "Need at least 2 observations")

    obs_df = pd.DataFrame([o.model_dump() for o in request.observations])

    model = REIM(
        method=request.method,
        max_iter=request.max_iter,
        prior_precision=request.prior_precision,
    )
    model.fit(obs_df[["observer", "system", "value"]])

    avg = SimpleAverage()
    avg.fit(obs_df[["observer", "system", "value"]])

    systems = [
        SystemEstimate(system=s, estimate=round(e, 4), uncertainty=round(model.uncertainty_.get(s, 0), 4))
        for s, e in sorted(model.system_estimates_.items())
    ]

    observers = [
        ObserverReliability(observer=o, variance=round(v, 4), reliability=round(model.observer_reliability_[o], 4))
        for o, v in sorted(model.observer_variance_.items(), key=lambda x: x[1])
    ]

    return BatchFitResponse(
        systems=systems,
        observers=observers,
        n_iter=model.n_iter_,
        converged=model.converged_,
    )


# ============================================================
# ONLINE REIM
# ============================================================

@app.post("/api/v1/online/init", tags=["Online REIM"])
async def online_init(request: OnlineInitRequest):
    """Initialize a new online REIM instance."""
    if len(online_instances) >= MAX_ONLINE_INSTANCES:
        raise HTTPException(429, f"Max instances reached ({MAX_ONLINE_INSTANCES})")

    if request.instance_id in online_instances:
        raise HTTPException(409, f"Instance '{request.instance_id}' already exists")

    instance = OnlineREIM(
        prior_mean=request.prior_mean,
        prior_precision=request.prior_precision,
        initial_observer_precision=request.initial_observer_precision,
        observer_learning_rate=request.observer_learning_rate,
        temporal_decay=request.temporal_decay,
        recalibrate_every=request.recalibrate_every,
    )
    online_instances[request.instance_id] = instance

    logger.info("Created online instance: %s", request.instance_id)
    return {"status": "created", "instance_id": request.instance_id}


@app.post("/api/v1/online/observe", response_model=OnlineObserveResponse, tags=["Online REIM"])
async def online_observe(request: OnlineObserveRequest):
    """Send a single observation to an online REIM instance."""
    if request.instance_id not in online_instances:
        raise HTTPException(404, f"Instance '{request.instance_id}' not found")

    instance = online_instances[request.instance_id]
    result = instance.observe(
        observer=request.observer,
        system=request.system,
        value=request.value,
        timestamp=request.timestamp,
    )

    return OnlineObserveResponse(
        system_estimate=round(result["system_estimate"], 4),
        system_uncertainty=round(result["system_uncertainty"], 4),
        observer_precision=round(result["observer_precision"], 4),
        delta=round(result["delta"], 4),
        total_observations=instance.n_observations_,
    )


@app.post("/api/v1/online/observe-batch", tags=["Online REIM"])
async def online_observe_batch(request: OnlineObserveBatchRequest):
    """Send multiple observations to an online REIM instance."""
    if request.instance_id not in online_instances:
        raise HTTPException(404, f"Instance '{request.instance_id}' not found")

    instance = online_instances[request.instance_id]
    obs_df = pd.DataFrame([o.model_dump() for o in request.observations])
    instance.observe_batch(obs_df)

    return {
        "status": "ok",
        "observations_processed": len(request.observations),
        "total_observations": instance.n_observations_,
    }


@app.get("/api/v1/online/{instance_id}/state", response_model=OnlineStateResponse, tags=["Online REIM"])
async def online_state(instance_id: str):
    """Get current state of an online REIM instance."""
    if instance_id not in online_instances:
        raise HTTPException(404, f"Instance '{instance_id}' not found")

    instance = online_instances[instance_id]
    estimates = instance.system_estimates_
    uncertainties = instance.system_uncertainty_

    systems = [
        SystemEstimate(
            system=s,
            estimate=round(estimates[s], 4),
            uncertainty=round(uncertainties.get(s, 0), 4),
        )
        for s in sorted(estimates.keys())
    ]

    return OnlineStateResponse(
        instance_id=instance_id,
        total_observations=instance.n_observations_,
        n_systems=len(estimates),
        n_observers=len(instance.observer_precision_),
        systems=systems,
    )


@app.delete("/api/v1/online/{instance_id}", tags=["Online REIM"])
async def online_delete(instance_id: str):
    """Delete an online REIM instance."""
    if instance_id not in online_instances:
        raise HTTPException(404, f"Instance '{instance_id}' not found")

    del online_instances[instance_id]
    logger.info("Deleted online instance: %s", instance_id)
    return {"status": "deleted", "instance_id": instance_id}


@app.get("/api/v1/online", tags=["Online REIM"])
async def online_list():
    """List all active online REIM instances."""
    instances = []
    for iid, inst in online_instances.items():
        instances.append({
            "instance_id": iid,
            "total_observations": inst.n_observations_,
            "n_systems": len(inst.system_estimates_),
            "n_observers": len(inst.observer_precision_),
        })
    return {"instances": instances}


# ============================================================
# MULTI-DIMENSIONAL REIM
# ============================================================

@app.get("/api/v1/multidim/phase-types", tags=["Multi-Dimensional REIM"])
async def multidim_phase_types():
    """List the default phase types for multi-dimensional analysis."""
    return {
        "phase_types": DEFAULT_PHASE_TYPES,
        "labels": DEFAULT_PHASE_LABELS,
    }


@app.post("/api/v1/multidim/fit", response_model=MultiDimFitResponse, tags=["Multi-Dimensional REIM"])
async def multidim_fit(request: MultiDimFitRequest):
    """
    Fit MultiDimensionalREIM on structured review data.

    Accepts reviews with multiple evaluation dimensions:
    - Each review has a phase_type and phase_rating (phase/sentiment score)
    - Each review has ratings[] with criteria_id and rating (criteria scores)
    - Criteria are dynamic per domain (no hardcoded list)
    """
    if not request.reviews:
        raise HTTPException(400, "No reviews provided")

    reviews_data = [r.model_dump() for r in request.reviews]

    criteria_meta = None
    if request.criteria_metadata:
        criteria_meta = {int(k): v for k, v in request.criteria_metadata.items()}

    model = MultiDimensionalREIM(
        temporal_decay=request.temporal_decay,
        method=request.method,
        suspicious_percentile=request.suspicious_percentile,
    )

    try:
        model.fit(reviews_data, criteria_metadata=criteria_meta)
    except ValueError as e:
        raise HTTPException(400, str(e))

    systems = []
    for sid in sorted(model.system_scores_["system_id"].unique()):
        detail = model.get_system_detail(sid)

        phase_dims = [
            DimensionScore(
                dimension=f"phase_{phase}",
                label=info["label"],
                estimate=info["estimate"],
                uncertainty=info["uncertainty"],
            )
            for phase, info in detail["phases"].items()
        ]

        criteria_dims = [
            DimensionScore(
                dimension=key,
                label=info["label"],
                estimate=info["estimate"],
                uncertainty=info["uncertainty"],
            )
            for key, info in detail["criteria"].items()
        ]

        systems.append(SystemScore(
            system_id=sid,
            overall_score=detail["overall_score"],
            phase_score=detail["phase_score"],
            criteria_score=detail["criteria_score"],
            phases=phase_dims,
            criteria=criteria_dims,
        ))

    observer_report = model.get_observer_report()
    observers = [
        ObserverReliabilitySummary(
            observer_id=row["observer_id"],
            overall_reliability=round(row["overall_reliability"], 4),
            min_reliability=round(row["min_reliability"], 4),
            max_reliability=round(row["max_reliability"], 4),
            n_dimensions=int(row["n_dimensions"]),
        )
        for _, row in observer_report.head(200).iterrows()
    ]

    suspicious = model.flag_suspicious_observers()
    suspicious_ids = suspicious["observer_id"].tolist()

    dim_summary = model.get_dimensions_summary()
    dimensions = [
        DimensionSummary(
            dimension=row["dimension"],
            label=row["label"],
            type=row["type"],
            n_systems=int(row["n_systems"]),
            n_observers=int(row["n_observers"]),
            converged=bool(row["converged"]),
        )
        for _, row in dim_summary.iterrows()
    ]

    return MultiDimFitResponse(
        systems=systems,
        observers=observers,
        suspicious_observers=suspicious_ids,
        dimensions=dimensions,
        n_dimensions=len(model.models_),
    )
