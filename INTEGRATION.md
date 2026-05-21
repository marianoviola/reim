# REIM Service — Integration Guide

This guide covers how to integrate the REIM microservice into your application. It includes setup, endpoint reference, data extraction patterns, and practical integration strategies.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Setup & Deployment](#2-setup--deployment)
3. [Endpoint Reference](#3-endpoint-reference)
4. [Data Extraction Patterns](#4-data-extraction-patterns)
5. [Integration Strategies](#5-integration-strategies)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Architecture Overview

REIM runs as a standalone microservice. Your application communicates with it over HTTP.

```
┌──────────────┐         HTTPS          ┌──────────────┐
│  Your App    │ ──────────────────────► │ REIM Service  │
│  (any stack) │                         │ FastAPI :8000 │
└──────────────┘                         └──────────────┘
```

**Key principles:**

- REIM is stateless for batch operations. You send the data, you get the results.
- Online REIM instances are in-memory and ephemeral.
- If REIM is down, your app keeps working with pre-calculated scores.

---

## 2. Setup & Deployment

### 2.1 Environment variables in your application

```env
REIM_SERVICE_URL=http://localhost:8000
```

For production behind a reverse proxy or tunnel:
```env
REIM_SERVICE_URL=https://reim.yourdomain.com
```

### 2.2 Local development with Docker

```yaml
# Add to your docker-compose.yml
services:
  reim:
    build:
      context: ./reim
      dockerfile: Dockerfile
    ports:
      - "8001:8000"
    environment:
      - ALLOWED_HOSTS=*
```

### 2.3 Verify

```bash
curl http://localhost:8001/health
# → {"status":"healthy","version":"1.0.0","models_loaded":0}
```

---

## 3. Endpoint Reference

### 3.1 `POST /api/v1/multidim/fit` — Structured review analysis

The primary endpoint for multi-dimensional review analysis. Send reviews with phase ratings and criteria ratings, get back quality estimates per system.

**Request:**

```json
{
  "reviews": [
    {
      "observer_id": 6,
      "system_id": 2,
      "phase_type": "usage",
      "phase_rating": 5,
      "created_at": "2026-02-16T23:18:09",
      "ratings": [
        {"criteria_id": 25, "criteria_name": "Stability", "rating": 5},
        {"criteria_id": 26, "criteria_name": "Handling", "rating": 4}
      ]
    }
  ],
  "criteria_metadata": {
    "25": "Stability",
    "26": "Handling"
  },
  "temporal_decay": 0.98,
  "method": "bayesian"
}
```

**Response:**

```json
{
  "systems": [
    {
      "system_id": "2",
      "overall_score": 4.12,
      "phase_score": 4.00,
      "criteria_score": 4.25,
      "phases": [
        {"dimension": "phase_usage", "label": "Usage / Experience", "estimate": 4.0, "uncertainty": 0.43}
      ],
      "criteria": [
        {"dimension": "criteria_25", "label": "Stability", "estimate": 5.0, "uncertainty": 0.53}
      ]
    }
  ],
  "observers": [
    {"observer_id": "6", "overall_reliability": 3.5, "min_reliability": 2.1, "max_reliability": 4.8, "n_dimensions": 8}
  ],
  "suspicious_observers": ["42", "87"],
  "dimensions": [
    {"dimension": "phase_usage", "label": "Usage / Experience", "type": "phase", "n_systems": 5, "n_observers": 12, "converged": true}
  ],
  "n_dimensions": 8
}
```

### 3.2 `GET /api/v1/multidim/phase-types`

Returns an *example* set of phase types and their labels (the product-review
lifecycle from `reim.examples.product_review`). `phase_type` is a free-form
string — define your own phases per domain; this endpoint is just a starting
point.

### 3.3 `POST /api/v1/batch/fit` — Generic REIM

For simple observer/system/value triples without multi-dimensional structure.

### 3.4 Online REIM — Real-time updates

```
POST /api/v1/online/init          → create instance
POST /api/v1/online/observe       → send one observation
POST /api/v1/online/observe-batch → send multiple observations
GET  /api/v1/online/{id}/state    → get current estimates
```

---

## 4. Data Extraction Patterns

### Preparing review data

Your application needs to extract reviews into the format REIM expects. Here's a generic example:

```python
# Pseudocode — adapt to your ORM/framework
reviews = []
for review in db.get_approved_reviews():
    reviews.append({
        "id": review.id,
        "observer_id": review.user_id,
        "system_id": review.product_id,
        "phase_type": review.phase_type,
        "phase_rating": review.phase_rating,
        "created_at": review.created_at.isoformat(),
        "ratings": [
            {
                "criteria_id": r.criteria_id,
                "criteria_name": r.criteria.name,
                "rating": r.rating,
            }
            for r in review.criteria_ratings
        ],
    })
```

### Criteria metadata

```python
criteria_metadata = {
    str(c.id): c.name
    for c in db.get_active_criteria()
}
```

---

## 5. Integration Strategies

### Strategy A: Nightly batch (recommended to start)

```
Scheduler (3am) → Extract reviews → POST /multidim/fit → Store results in DB
```

### Strategy B: Real-time + nightly hybrid

```
New review → Observer → POST /online/observe → Instant update
Nightly    → Cron job → POST /multidim/fit   → Full recalibration
```

### Strategy C: Per-system on-demand (with caching)

```python
# Pseudocode
scores = cache.get(f"reim_system_{system_id}")
if not scores:
    scores = reim_client.analyze_system(system_id)
    cache.set(f"reim_system_{system_id}", scores, ttl=6*3600)
```

---

## 6. Troubleshooting

### REIM service not reachable

```bash
# Check locally
curl http://localhost:8000/health
```

### 403 Forbidden

- Check `ALLOWED_HOSTS` on the REIM service
- For local dev, make sure `ALLOWED_HOSTS=*`

### Empty results from `/multidim/fit`

- Send only approved reviews
- At least 2 reviews from 2 different observers needed
- Check `phase_rating` is not null
- Check `ratings` array is not empty (for criteria scores)

### High uncertainty

Normal with few reviews. Bayesian prior dominates with sparse data. Uncertainty decreases as more reviews come in.

### Online instance lost (404)

Online state is in memory — lost on REIM restart. Re-initialize on application boot.

### Performance

| Operation | Time |
|---|---|
| Batch fit (1K reviews) | ~1 second |
| Batch fit (10K reviews) | ~10 seconds |
| Online observe | <1ms |
| Set HTTP timeout accordingly | `timeout(30)` for batch |
