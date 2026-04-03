FROM python:3.12-slim

LABEL maintainer="Mariano Viola"
LABEL description="REIM Microservice — Reticular Epistemic Inference Model"

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY reim/ /app/reim/
COPY app/ /app/app/

# Non-root user
RUN useradd -m -r reim && chown -R reim:reim /app
USER reim

# Environment
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV MAX_ONLINE_INSTANCES=100
ENV MAX_BATCH_OBSERVATIONS=1000000
ENV CORS_ORIGINS=*
ENV ALLOWED_HOSTS=*

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
