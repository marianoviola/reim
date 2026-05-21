"""
API schemas — Pydantic models for request/response validation.
"""

import os

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

# Rating value bounds are domain-dependent (e.g. 1-5 stars, 0-10 scores).
# Configure them via env vars at deploy time; defaults match a 1-5 scale.
REIM_VALUE_MIN = float(os.getenv("REIM_VALUE_MIN", "1.0"))
REIM_VALUE_MAX = float(os.getenv("REIM_VALUE_MAX", "5.0"))


# ============================================================
# SHARED
# ============================================================

class Observation(BaseModel):
    observer: str = Field(..., description="Observer/reviewer ID")
    system: str = Field(..., description="System/product ID")
    value: float = Field(..., ge=REIM_VALUE_MIN, le=REIM_VALUE_MAX, description="Rating value")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")


# ============================================================
# BATCH REIM
# ============================================================

class BatchFitRequest(BaseModel):
    observations: List[Observation]
    method: Literal["mle", "bayesian"] = "bayesian"
    max_iter: int = Field(100, ge=1, le=1000)
    prior_precision: float = Field(0.01, ge=0.0)

class SystemEstimate(BaseModel):
    system: str
    estimate: float
    uncertainty: float

class ObserverReliability(BaseModel):
    observer: str
    variance: float
    reliability: float

class BatchFitResponse(BaseModel):
    systems: List[SystemEstimate]
    observers: List[ObserverReliability]
    n_iter: int
    converged: bool
    rmse_vs_average: Optional[float] = None


# ============================================================
# ONLINE REIM
# ============================================================

class OnlineInitRequest(BaseModel):
    instance_id: str = Field(..., description="Unique ID for this online model instance")
    prior_mean: float = Field(3.0)
    prior_precision: float = Field(0.1)
    initial_observer_precision: float = Field(1.0)
    observer_learning_rate: float = Field(0.05, ge=0.001, le=1.0)
    temporal_decay: float = Field(1.0, ge=0.0, le=1.0)
    recalibrate_every: int = Field(100, ge=10, le=10000)

class OnlineObserveRequest(BaseModel):
    instance_id: str
    observer: str
    system: str
    value: float = Field(..., ge=REIM_VALUE_MIN, le=REIM_VALUE_MAX)
    timestamp: Optional[str] = None

class OnlineObserveBatchRequest(BaseModel):
    instance_id: str
    observations: List[Observation]

class OnlineObserveResponse(BaseModel):
    system_estimate: float
    system_uncertainty: float
    observer_precision: float
    delta: float
    total_observations: int

class OnlineStateResponse(BaseModel):
    instance_id: str
    total_observations: int
    n_systems: int
    n_observers: int
    systems: List[SystemEstimate]


# ============================================================
# MULTI-DIMENSIONAL REIM — Structured review analysis
# ============================================================

class CriteriaRatingInput(BaseModel):
    """A single criteria rating within a review."""
    criteria_id: int = Field(..., alias="criteria_id")
    criteria_name: Optional[str] = None
    rating: int = Field(..., ge=REIM_VALUE_MIN, le=REIM_VALUE_MAX)

    class Config:
        populate_by_name = True


class ReviewInput(BaseModel):
    """A structured review with phase and criteria ratings."""
    id: Optional[int] = None
    observer_id: int = Field(..., alias="observer_id")
    system_id: int = Field(..., alias="system_id")
    phase_type: str = Field(..., min_length=1, alias="phase_type", description="Categorical phase/context label (domain-defined)")
    phase_rating: Optional[int] = Field(None, ge=REIM_VALUE_MIN, le=REIM_VALUE_MAX, alias="phase_rating")
    created_at: Optional[str] = None
    ratings: List[CriteriaRatingInput] = []

    class Config:
        populate_by_name = True


class MultiDimFitRequest(BaseModel):
    """Request to fit MultiDimensionalREIM."""
    reviews: List[ReviewInput]
    criteria_metadata: Optional[Dict[int, str]] = None
    temporal_decay: float = Field(0.98, ge=0.0, le=1.0)
    method: Literal["mle", "bayesian"] = "bayesian"
    suspicious_percentile: float = Field(10, ge=1, le=50)


class DimensionScore(BaseModel):
    dimension: str
    label: str
    estimate: Optional[float] = None
    uncertainty: Optional[float] = None


class SystemScore(BaseModel):
    system_id: str
    overall_score: Optional[float] = None
    phase_score: Optional[float] = None
    criteria_score: Optional[float] = None
    phases: List[DimensionScore] = []
    criteria: List[DimensionScore] = []


class ObserverReliabilitySummary(BaseModel):
    observer_id: str
    overall_reliability: float
    min_reliability: float
    max_reliability: float
    n_dimensions: int


class DimensionSummary(BaseModel):
    dimension: str
    label: str
    type: str
    n_systems: int
    n_observers: int
    converged: bool


class MultiDimFitResponse(BaseModel):
    systems: List[SystemScore]
    observers: List[ObserverReliabilitySummary]
    suspicious_observers: List[str]
    dimensions: List[DimensionSummary]
    n_dimensions: int


# ============================================================
# HEALTH
# ============================================================

class HealthResponse(BaseModel):
    status: str
    version: str
    models_loaded: int
