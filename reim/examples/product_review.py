"""
Product-review example configuration.

A ready-made set of lifecycle phases for the retail / e-commerce product
review use case. This is one *example* domain configuration — the core
``MultiDimensionalREIM`` accepts any set of phase types, so adapt or
replace these for other domains (vendor scoring, peer review, etc.).
"""

PRODUCT_REVIEW_PHASE_TYPES = [
    "pre_purchase",
    "purchase",
    "usage",
    "support",
    "closure",
]

PRODUCT_REVIEW_PHASE_LABELS = {
    "pre_purchase": "Pre-purchase / Discovery",
    "purchase": "Purchase / Activation",
    "usage": "Usage / Experience",
    "support": "Support / Assistance",
    "closure": "Closure / End-of-life",
}
