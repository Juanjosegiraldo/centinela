# Centinela — Sprint 2 (cierra domingo 26 de julio)

Documento único: historias, estimaciones, commits y PRs. Reemplaza a los archivos sueltos anteriores.

---

# 1. Historias (10) con estimación y responsable

| Id | Historia | Responsable | Horas | Depende de |
|---|---|---|---|---|
| W2-01 | Provision week 2 infrastructure | Juan José | 4 | — |
| W2-02 | Case store schema with audit trail | Juan José | 2 | W2-01 |
| W2-03 | Document partitioning, consistency and TTL | Juan José | 2 | W2-01 |
| W2-04 | Publish transaction event from the API | Miguel | 3 | W2-01 |
| W2-05 | Migrate secrets to Key Vault | Miguel | 3 | W2-01 |
| W2-06 | Rate limiting returning 429 | Miguel | 2 | — |
| W2-07 | Scoring engine triggered by event | Tobías | 5 | W2-04 |
| W2-08 | Four rules, activation detail, threshold | Tobías | 5 | W2-07 |
| W2-09 | Decoupling and queue durability proof | Argenis | 4 | W2-08 |
| W2-10 | End-to-end pipeline and test report | Argenis | 3 | W2-09 |

**Total: 33 horas.**

## Texto para pegar en Jira

**W2-01 · Provision week 2 infrastructure (4h)** — Juan José
As a team, we want the week 2 data stores, messaging and secret manager provisioned by script, so that every other task of the sprint has infrastructure to build on.
AC: script runs with no manual steps · Cosmos (partition /account_id, TTL 90d, Session), Azure SQL serverless, Service Bus Standard (topic + queue), Key Vault and Function App created · SQL not reachable from the internet · roles granted to both managed identities.
Evidence: script output + resource group screenshot.

**W2-02 · Case store schema with audit trail (2h)** — Juan José
As a compliance officer, I want the case model deployed with an immutable audit trail, so that every state change is traceable.
AC: tables cases, case_states, assignments, resolutions, audit_log created · audit rows written automatically on state change · backup strategy documented (frequency, retention, maximum tolerable loss).
Evidence: schema deployed + a state change producing an audit row.

**W2-03 · Document partitioning, consistency and TTL (2h)** — Juan José
As an architect, I want the transaction-store decisions justified in writing, so that an irreversible choice is defensible.
AC: which query the partition key optimises and which it sacrifices · discarded alternatives · consistency level and latency trade-off · TTL tied to the longest rule window.
Evidence: document in docs/ + ADR entry.

**W2-04 · Publish transaction event from the API (3h)** — Miguel
As the fintech, we want the API to publish an event after persisting and respond immediately, so that the client never waits for fraud analysis.
AC: publishes to the topic after persisting, before acknowledging · does not call the engine and does not wait · valid transaction still returns 202.
Evidence: 202 with latency + message visible in the topic.

**W2-05 · Migrate secrets to Key Vault (3h)** — Miguel
As a security engineer, we want every credential in the secret manager, accessed through managed identity, so that no secret exists in code or history.
AC: no credentials in code, repository or git history · components authenticate with managed identity · git history audited.
Evidence: secret names list + git audit output.

**W2-06 · Rate limiting returning 429 (2h)** — Miguel
As an operator, we want a per-origin request limit, so that synthetic traffic cannot drain credit through the scoring engine.
AC: requests beyond the limit return 429 · limit and window documented and justified · limitations of the approach documented.
Evidence: burst test showing 429.

**W2-07 · Scoring engine triggered by event (5h)** — Tobías
As the fintech, we want a serverless engine that reacts to the transaction event and scores against account history, so that analysis never blocks ingestion.
AC: triggered by the topic subscription, not by an API call · queries history reading a single partition · persists score with the transaction.
Evidence: engine log with scored_at later than the API response.

**W2-08 · Four rules, activation detail and threshold (5h)** — Tobías
As a fraud analyst, we want the four rules recording the values that triggered them, so that week 3 can explain each case.
AC: velocity, atypical amount, geo-impossible and risky merchant implemented · each triggered rule persists observed values, not only its id · threshold read from configuration, changeable without redeploy · cases above threshold enqueued.
Evidence: one screenshot per rule + threshold change altering behaviour without deploying.

**W2-09 · Decoupling and queue durability proof (4h)** — Argenis
As QA, we want a reproducible procedure proving the pipeline is decoupled and loses nothing, so that the architectural requirement is verified rather than assumed.
AC: timestamps show the API responded before the engine finished · with the consumer stopped the API keeps accepting · on restart every queued case is processed with no losses.
Evidence: timestamps + queue count while stopped, then zero.

**W2-10 · End-to-end pipeline and test report (3h)** — Argenis
As a team, we want one transaction to travel from ingestion to case without manual intervention, documented in a test report.
AC: a single transaction produces score and, above threshold, a case · no manual step · report records every test with result and evidence · consumed credit under 40 USD.
Evidence: test report + cost analysis screenshot.

---

# 2. Cronograma (viernes 24 a domingo 26)

| Día | Horas | Historia | Responsable |
|---|---|---|---|
| Vie 24 | 14:00–18:00 | W2-01 infraestructura | Juan |
| Vie 24 | 18:00–21:00 | W2-04 publicar evento | Miguel |
| Sáb 25 | 08:00–13:00 | W2-07 motor de scoring | Tobías |
| Sáb 25 | 14:00–19:00 | W2-08 cuatro reglas | Tobías |
| Sáb 25 | 19:00–21:00 | W2-02 esquema de casos | Juan |
| Dom 26 | 08:00–12:00 | W2-09 prueba de desacoplamiento | Argenis |
| Dom 26 | 12:00–15:00 | W2-10 pipeline E2E y reporte | Argenis |
| Dom 26 | 15:00–18:00 | W2-05 secretos a Key Vault | Miguel |
| Dom 26 | 18:00–20:00 | W2-06 límite de tasa | Miguel |
| Dom 26 | 20:00–22:00 | W2-03 documentación de decisiones | Juan |

**Prioridad si el tiempo no alcanza** (núcleo evaluable): W2-01 → W2-04 → W2-07 → W2-08 → W2-09. Las demás pueden entregarse parciales declarando alcance reducido.

---

# 3. Commits y PRs

Un PR por persona, con los commits que le corresponden. Se mergean en el orden 1→2→3→4.

## PR 1 · rama `juanjose` → `develop`
**Título:** Week 2 — Infrastructure: data stores, messaging and secrets

```bash
git checkout develop && git pull origin develop
git checkout -b juanjose

git add infra/provision-week2.sh
git commit -m "feat: provision week 2 infrastructure (cosmos, sql, service bus, key vault, function app)"

git add docs/schema.sql
git commit -m "feat: add case store schema with immutable audit trail"

git add docs/adr.md
git commit -m "docs: record partitioning, consistency and ttl decisions"

git push -u origin juanjose
```
Cierra: W2-01, W2-02, W2-03.

## PR 2 · rama `miguel` → `develop`
**Título:** Week 2 — API: event publishing, secrets and rate limiting

```bash
git checkout develop && git pull origin develop
git checkout -b miguel

git add api/app/events.py
git commit -m "feat: publish transaction event to service bus topic"

git add api/app/config.py
git commit -m "feat: read configuration from key vault via managed identity"

git add api/app/ratelimit.py api/app/main.py
git commit -m "feat: add per-origin rate limiting returning 429"

git add api/requirements.txt
git commit -m "chore: add service bus and key vault dependencies"

git push -u origin miguel
```
Cierra: W2-04, W2-05, W2-06.

## PR 3 · rama `tobias` → `develop`
**Título:** Week 2 — Scoring engine: four rules, configurable threshold

```bash
git checkout develop && git pull origin develop
git checkout -b tobias

git add engine/scoring/rules.py engine/scoring/__init__.py
git commit -m "feat: add four detection rules with activation detail"

git add engine/function_app.py
git commit -m "feat: add scoring engine triggered by transaction event"

git add engine/requirements.txt engine/host.json
git commit -m "chore: add scoring engine runtime configuration"

git push -u origin tobias
```
Cierra: W2-07, W2-08.

## PR 4 · rama `argenis` → `develop`
**Título:** Week 2 — QA: acceptance suite and decoupling proof

```bash
git checkout develop && git pull origin develop
git checkout -b argenis

git add tests/week2-acceptance.sh
git commit -m "test: add week 2 acceptance suite"

git add docs/test-report-week2.md
git commit -m "docs: add week 2 test report with evidence"

git push -u origin argenis
```
Cierra: W2-09, W2-10.

## Cierre del sprint
Cuando los 4 PR estén en `develop`: PR final `develop` → `main`, título **Week 2 — Scoring engine and event-driven architecture**.

---

# 4. Relación con las historias de cierre de la semana 1

Tres historias de la semana 1 **no se cierran definitivamente**: son documentos vivos que cada sprint actualiza.

| Historia semana 1 | Qué le agrega la semana 2 |
|---|---|
| VOR-28 · ADR | Decisiones nuevas: clave de partición, consistencia, TTL, umbral, evento vs invocación directa, topic vs cola |
| VOR-29 · README de despliegue | Pasos nuevos: ejecutar provision-week2.sh, crear el esquema SQL, desplegar la Function |
| VOR-30 · Validación de cierre | La secuencia crece: ahora incluye score generado, caso abierto y prueba de desacoplamiento |

Las demás historias de la semana 1 (VOR-7 a VOR-27) sí quedan cerradas con sus evidencias.

En Jira: deja VOR-28, VOR-29 y VOR-30 en "Hecho" para el Sprint 1, y crea sus equivalentes de la semana 2 dentro de W2-03 (ADR), W2-10 (reporte) y el README, que ya están contemplados en las historias nuevas. No dupliques tarjetas.
