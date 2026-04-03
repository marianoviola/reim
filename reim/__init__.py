"""
REIM - Reticular Epistemic Inference Model

A library for inferring true system properties from distributed noisy observations.

Variants:
    REIM                  — Batch MLE/Bayesian estimation
    OnlineREIM            — Incremental real-time updates
    HierarchicalREIM      — Multi-level systems with emergence and directional observability
    MultiDimensionalREIM  — Multi-dimensional structured review analysis
"""

from .model import REIM
from .online import OnlineREIM
from .hierarchical import HierarchicalREIM
from .multidim import MultiDimensionalREIM
from .generators import SyntheticDataGenerator
from .metrics import compute_metrics
from .baselines import SimpleAverage, TrimmedMean

__version__ = "1.0.0"
__all__ = [
    "REIM",
    "OnlineREIM",
    "HierarchicalREIM",
    "MultiDimensionalREIM",
    "SyntheticDataGenerator",
    "compute_metrics",
    "SimpleAverage",
    "TrimmedMean",
]
