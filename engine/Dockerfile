# Centinela — Scoring engine container (W3-01)
#
# This image solves the two deployment problems the stock (non-container)
# Functions worker had:
#   1. The Oryx remote build never ran on the dedicated B1 plan, so Python
#      dependencies were never installed (we shipped bundled wheels as a
#      workaround). Here they are baked into the image at build time.
#   2. pyodbc (and therefore SQL case rows in casesdb) was deferred because
#      the stock worker lacked the msodbcsql18 ODBC driver. The
#      azure-functions Python base image SHIPS msodbcsql18 preinstalled
#      (verified: 18.6.2.1-1, registered as "ODBC Driver 18 for SQL Server"),
#      so pyodbc works here with no extra apt layer.
#
# Multi-stage: deps resolve in a slim builder; the final Functions runtime
# image carries no pip cache and no secrets in any layer.

# ---------- build stage: resolve dependencies ----------
FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt .
# pyodbc is intentionally NOT in requirements.txt (it broke the non-container
# deploys that lack the ODBC driver). The container has the driver, so it is
# added here, pinned exactly (open ranges hung the pip resolver before).
RUN pip install --no-cache-dir --target /deps -r requirements.txt pyodbc==5.2.0

# ---------- final stage: Azure Functions Python runtime ----------
FROM mcr.microsoft.com/azure-functions/python:4-python3.12

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true

# Dependencies land where the Functions Python worker already looks for them —
# the exact mechanism proven in production with the bundled-wheels deploy.
COPY --from=build /deps /home/site/wwwroot/.python_packages/lib/site-packages

# Engine code (function_app.py, host.json, store.py, cases.py, ...)
COPY . /home/site/wwwroot
