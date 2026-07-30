# Deliverable W3-01 — Container images (API + scoring engine)

Owner: Juan José · Maps to: Week 3 §2.2 (containers), VOR-42.

## Images

| Image | Base | Size (uncompressed, local build) | Verified by |
|---|---|---|---|
| `centinela-api` | `python:3.12-slim` | **290 MB** | Container run → `GET /health` = 200 |
| `centinela-engine` | `mcr.microsoft.com/azure-functions/python:4-python3.12` | **2.88 GB** | In-container: `pyodbc 5.2.0` sees `ODBC Driver 18 for SQL Server`; azure SDKs import; `function_app` loads (threshold 50) |

## Why containerizing the engine matters (architecture note)

The engine image solves the two standing deployment problems of the stock worker at once:

1. **Broken remote build.** Oryx never runs for Functions zip-deploys on the dedicated B1
   plan, so dependencies were shipped as pre-downloaded wheels. In the image they are baked
   at build time — deterministic, no deploy-time build at all.
2. **Deferred SQL case rows.** `pyodbc` needs the `msodbcsql18` ODBC driver, absent from the
   stock worker. **Finding:** the `azure-functions/python:4-python3.12` base image *ships
   msodbcsql18 preinstalled* (18.6.2.1-1, registered as "ODBC Driver 18 for SQL Server"),
   so no extra apt layer is needed. `pyodbc==5.2.0` is added only in the image (kept out of
   `requirements.txt` so the current non-container deploy keeps working).

## Size-reduction measures applied

- **Multi-stage builds**: dependencies resolve in a throwaway `python:3.12-slim` builder;
  final images carry no pip cache and no build toolchain (`--no-cache-dir`).
- **Slim base for the API** (`python:3.12-slim`, not full `python:3.12` ≈ 1 GB).
- **`.dockerignore`** in both contexts (`__pycache__`, Dockerfile itself).
- **No apt layer in the engine** after discovering the driver is preinstalled (dropped a
  planned ~50 MB+ layer and its package-manager residue).
- **Non-root user** in the API image (least privilege; no size effect but part of hardening).
- **No secrets in any layer**: both images take all configuration from app settings /
  managed identity at runtime; nothing sensitive is copied or ENV-ed at build time.

## Size discussion (honest)

The engine image is dominated by the Azure Functions runtime base (~2.7 GB of the 2.88 GB);
our layers add ~180 MB (deps + code). Reducing further would mean abandoning the official
Functions base (running the host by hand on `python:slim`), which trades a supported,
Azure-parity runtime for size — not worth it at this scale. The API image (290 MB) is
already near the floor for Python + the Azure SDK set.

## Build & run locally

```bash
# API
cd api && docker build -t centinela-api:dev .
docker run --rm -p 8088:8000 centinela-api:dev   # GET http://localhost:8088/health

# Engine
cd engine && docker build -t centinela-engine:dev .
```

Next step (W3-02): push both to ACR and run them on the existing B1 plan
(see docs/release-and-cicd-plan.md, Phase 2).
