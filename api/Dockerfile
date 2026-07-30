# Centinela — Ingestion API container (W3-01)
# Multi-stage: dependencies are resolved in a throwaway builder layer so the
# final image ships no pip cache, no build tools and no secrets in any layer.
# All configuration arrives via app settings at runtime (never baked in).

# ---------- build stage: resolve dependencies ----------
FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- final stage: slim runtime ----------
FROM python:3.12-slim
WORKDIR /app

# Dependencies from the builder (no cache, no toolchain)
COPY --from=build /install /usr/local

# Application code only
COPY app/ ./app/

# Run as a non-root user (least privilege inside the container too)
RUN useradd --system --uid 10001 centinela
USER centinela

# Web App for Containers reads this port via the WEBSITES_PORT app setting
EXPOSE 8000

# Same startup command the Web App uses today — behavior parity with the
# non-container deployment.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "app.main:app"]
