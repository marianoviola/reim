# REIM Microservice

**Reticular Epistemic Inference Model** — A microservice for inferring true system properties from distributed noisy observations.

## Quick Start

```bash
# With Docker Compose
docker compose up --build

# Without Docker
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API docs at `http://localhost:8000/docs`.

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## API Endpoints

### Batch REIM

Fit a model on a complete set of observations. Best for periodic recalculation.

```bash
curl -X POST http://localhost:8000/api/v1/batch/fit \
  -H "Content-Type: application/json" \
  -d '{
    "observations": [
      {"observer": "user_1", "system": "product_a", "value": 4.5},
      {"observer": "user_2", "system": "product_a", "value": 5.0}
    ],
    "method": "bayesian"
  }'
```

### Online REIM

Real-time incremental updates. Each observation updates estimates in O(1).

```bash
# Create instance
curl -X POST http://localhost:8000/api/v1/online/init \
  -H "Content-Type: application/json" \
  -d '{"instance_id": "my-platform"}'

# Send observation
curl -X POST http://localhost:8000/api/v1/online/observe \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "my-platform",
    "observer": "user_1",
    "system": "product_a",
    "value": 4.5
  }'

# Get estimates
curl http://localhost:8000/api/v1/online/my-platform/state
```

### Multi-Dimensional REIM

Multi-dimensional review analysis with phase types and criteria ratings.

```bash
# List default phase types
curl http://localhost:8000/api/v1/multidim/phase-types

# Fit model
curl -X POST http://localhost:8000/api/v1/multidim/fit \
  -H "Content-Type: application/json" \
  -d '{
    "reviews": [
      {
        "observer_id": 1,
        "system_id": 1,
        "phase_type": "usage",
        "phase_rating": 4,
        "created_at": "2026-03-01",
        "ratings": [
          {"criteria_id": 1, "criteria_name": "Display", "rating": 5},
          {"criteria_id": 2, "criteria_name": "Battery", "rating": 3}
        ]
      }
    ],
    "criteria_metadata": {"1": "Display", "2": "Battery Life"}
  }'
```

## Access Control

The service restricts connections via the `ALLOWED_HOSTS` environment variable. Only requests from authorized sources reach the API endpoints. The `/health` endpoint is always public (for Docker healthchecks and monitoring).

### Configuration

| Value | Effect |
|-------|--------|
| `*` (default) | Allow all connections — **development only** |
| `docker` | Allow Docker internal networks (172.16.0.0/12, 10.0.0.0/8, 192.168.0.0/16) |
| `example.com` | Allow requests with Host/Origin matching `*.example.com` |
| `93.184.216.34` | Allow a specific IP address |
| `172.18.0.0/16` | Allow a CIDR range |
| `myapp` | Allow a Docker container hostname (resolved to IP) |

Values can be combined, comma-separated:

```env
# Development
ALLOWED_HOSTS=*

# Docker containers only
ALLOWED_HOSTS=docker

# Production (your app + Docker internal)
ALLOWED_HOSTS=docker,yourdomain.com

# Specific IP + Docker
ALLOWED_HOSTS=docker,93.184.216.34
```

Requests from `127.0.0.1` (loopback) are always allowed regardless of configuration.

### Production deployment example

```env
ALLOWED_HOSTS=docker,yourdomain.com
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

This ensures only your application (via Docker network or domain) can reach the REIM API. External requests will receive `403 Forbidden` unless they originate from an allowed source.

### What gets blocked

| Source | `ALLOWED_HOSTS=docker,yourdomain.com` | Result |
|--------|---------------------------------------|--------|
| `GET /health` from anywhere | ✅ | Always public |
| App on same Docker network | ✅ | Matched by `docker` |
| Request with matching Host header | ✅ | Matched by domain |
| Random external IP | ❌ | 403 Forbidden |
| Postman from your laptop (localhost) | ✅ | Loopback always allowed |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Service port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MAX_ONLINE_INSTANCES` | `100` | Max concurrent online models |
| `MAX_BATCH_OBSERVATIONS` | `1000000` | Max observations per batch |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated) |
| `ALLOWED_HOSTS` | `*` | Access control — see above |

## Project Structure

```
reim/
├── app/
│   ├── main.py          # FastAPI endpoints
│   ├── schemas.py       # Pydantic request/response models
│   └── middleware.py     # Access control middleware
├── reim/
│   ├── model.py         # Batch REIM (MLE + Bayesian)
│   ├── online.py        # Online REIM (incremental)
│   ├── hierarchical.py  # H-REIM (multi-level)
│   ├── multidim.py      # Multi-dimensional structured analysis
│   ├── generators.py    # Synthetic data generation
│   ├── metrics.py       # Evaluation metrics
│   └── baselines.py     # Baseline methods
├── tests/
│   ├── test_reim.py     # Library tests
│   ├── test_api.py      # API endpoint tests
│   └── test_middleware.py # Access control tests
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml       # Pytest configuration
├── INTEGRATION.md       # Integration guide
├── LICENSE              # Proprietary license
└── requirements.txt
```

## Production Notes

- **Access control** is enforced at the application level via `ALLOWED_HOSTS`. For defense in depth, also configure network-level restrictions (firewall rules, Docker network isolation, reverse proxy IP whitelisting).
- **Online instances are in-memory.** They don't persist across container restarts.
- **Single worker by default.** Use `--workers 1` or add shared state (Redis) for multi-worker.
- **Batch endpoint is stateless.** Safe to scale horizontally.
- **Recommended strategy:** Online REIM for real-time updates, Batch REIM nightly for full recalibration.
