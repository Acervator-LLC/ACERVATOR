# Acervator — Cloud Container
# Base: Python 3.11 slim (no GUI dependencies)
# Copyright (c) 2025 Anthony L. Brown. All rights reserved.

FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────
# No Qt, no PySide6, no display server needed for headless daemon
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libssl-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ──────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ────────────────────────────────────────
# Copy requirements first for layer caching
COPY cloud/requirements_cloud.txt .
RUN pip install --no-cache-dir -r requirements_cloud.txt

# ── Application code ───────────────────────────────────────────
# Copy only the modules needed for headless operation
# Explicitly exclude GUI (PySide6) dependencies
COPY src/ ./src/
COPY cloud/ ./cloud/
COPY RAIntSimBat.py .

# ── Runtime directories ────────────────────────────────────────
RUN mkdir -p logs reports

# ── Non-root user (security best practice) ────────────────────
RUN useradd -m -u 1000 acervator && chown -R acervator:acervator /app
USER acervator

# ── Health check ───────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# ── Default command ────────────────────────────────────────────
CMD ["python", "cloud/acervator_daemon.py", \
     "--config", "cloud/config.json", \
     "--status-port", "8080"]
