# Release plan: develop → main + CI/CD (Week 3)

Owner: Juan José (VOR-42/43/44) · Status of this plan: approved-pending-execution
Baseline when written: develop @ `c264ff5` (52 commits ahead of main), 15/15 tests green,
no workflows or Dockerfiles in the repo yet, `main` unprotected.

## Goal

One motion that satisfies two obligations at once:

1. **The release**: `develop → main` is the project-close merge (team flow).
2. **Sustentación point 6**: *"a merge to the main branch triggers an automatic deployment"* —
   which requires the CI/CD pipeline (W3-03) to exist and to be wired to `main` **before**
   the release merge happens.

Definition of done: a small PR merged into `main` builds, tests, packages and deploys the
system with zero manual steps, live, in front of the evaluators.

---

## Phase 0 — Gates before the release merge (prerequisites)

| # | Gate | Owner | Why it blocks |
|---|------|-------|---------------|
| 0.1 | PR #18 (explainer + doc handling + telemetry) fixed and merged | Tobías | The explainer is a **closure criterion**; merging it after the release would force a second release |
| 0.2 | `feature/argenis` closure work reconciled into develop (docs + persist_trace, BOMs cleaned, no week-3 provision changes mixed in) | Argenis + Juan José | Closure evidence must ship in the release |
| 0.3 | Full suite green on develop (currently 15/15) | all | It becomes the pipeline gate |
| 0.4 | Freeze develop (no new features; fixes only) | all | A moving target cannot be released |

Nothing in Phases 1–3 waits for Phase 0 — they run in parallel. Only the **final release
merge (Phase 4)** waits for these gates.

---

## Phase 1 — Containers (W3-01)

Two multi-stage Dockerfiles, slim base (`python:3.12-slim`), no secrets in any layer:

- **`api/Dockerfile`** — installs `api/requirements.txt`, runs
  `gunicorn -k uvicorn.workers.UvicornWorker app.main:app`. Straightforward.
- **`engine/Dockerfile`** — base image for Azure Functions Python
  (`mcr.microsoft.com/azure-functions/python:4-python3.12`) **plus `msodbcsql18` + `pyodbc`**.

> **Architectural synergy — say this in the defense:** containerizing the engine is not just a
> deployment change; it **solves two standing problems at once**:
> 1. The broken Oryx remote build on the dedicated B1 plan (deps ship inside the image —
>    no more bundled wheels).
> 2. The deferred SQL case rows: the image installs the `msodbcsql18` ODBC driver that the
>    stock worker lacks, so `pyodbc` works and `cases.py` starts writing rows to `casesdb`.

Deliverables per the brief: image sizes documented + measures taken to reduce them
(multi-stage, slim base, `.dockerignore`, no build cache in final layer).

## Phase 2 — Registry + runtime platform (W3-02)

- **Registry**: Azure Container Registry, **Basic** tier (cheapest; limits documented).
  Name: `acrctndevjj15`.
- **Runtime**: **Web App for Containers on the existing B1 plan** for both images.
  This is the fallback VOR-43 already names — chosen as PRIMARY because the quota history of
  this subscription (consumption = zero quota) makes consumption-based container platforms
  (Container Apps) a likely dead end. **Validate early anyway** (VOR-43 requirement): try a
  Container Apps environment once; if quota denies it, the ADR records the attempt.
- Managed identity everywhere is preserved: the web apps pull from ACR with managed identity
  (`AcrPull` role); no registry passwords.
- **Caveat to validate early**: running the *engine* as a custom Functions container on B1
  Linux — verify trigger registration works identically. If it misbehaves, fallback is
  documented: keep the engine on the current bundled-wheels deploy (already working) and
  containerize only the API. The pipeline stages stay identical either way.
- Engine still needs to reach subnet-only SQL → VNet-integrate the Function/container app on
  `snet-app` (the B1 plan supports it; the API already uses it).

## Phase 3 — CI/CD pipeline (W3-03)

**Platform: GitHub Actions.** Justification for the ADR (required by the brief — what we gain,
what we sacrifice, when the opposite choice wins):

- *Gain*: the repo, PRs and reviews already live on GitHub → zero context switch; free minutes
  for public/small repos; `azure/login` with **OIDC federated credentials** means the pipeline
  holds **no stored cloud secret at all** (stronger than the requirement "credentials as
  platform secrets").
- *Sacrifice*: no built-in boards/artifacts integration à la Azure DevOps; YAML ecosystem
  differences.
- *Opposite choice*: if the organization standardized on Azure DevOps (boards + repos +
  pipelines in one tenant), Azure Pipelines would win on integration.

**Two workflows:**

1. **`ci.yml`** — on every PR to `develop` and `main`: install deps → run the unit suite
   (15 tests) → build the Next.js console (`npm run build`, TypeScript gate). A failing step
   blocks the merge (branch protection, Phase 4).
2. **`deploy.yml`** — on push to **`main`** (the sustentación demo):
   1. Build (API + engine + console).
   2. **Tests — a failure stops the pipeline here** (brief requirement).
   3. `docker build` both images.
   4. Push to ACR (OIDC login, `AcrPush`).
   5. Deploy: API container → `app-ctn-ingest-dev-jj15`, engine container →
      `func-ctn-scoring-dev-jj15`, console static export → `stctnwebjj15/$web`.
   6. Smoke test: `GET /health` = 200 and one `POST /transactions` = 202.

**Pipeline identity**: one Entra app (or user-assigned MI) with federated credential scoped to
`repo:Juanjosegiraldo/centinela:ref:refs/heads/main`, holding only: `AcrPush`, website
contributor on the two web apps, and blob write on `stctnwebjj15`. No PAT, no publish profile,
no secret in the workflow file — nothing to leak.

## Phase 4 — Branch protection + the release itself

1. **Protect `main`**: require PR, require `ci.yml` green, no direct pushes, no force-push.
2. **Release PR `develop → main`** (after Phase 0 gates): title
   `Release: Centinela weeks 1–3`, body = summary of the three weeks + link to the ADR.
   Merge commit (not squash) to keep every member's authorship in main's history.
3. `deploy.yml` fires on the merge → **first automated production deploy**. Verify smoke tests.
4. Tag `v1.0.0` on main.

## The sustentación demo script (point 6)

1. Open a trivial PR to `main` (e.g. a README line or a version bump) — prepared beforehand.
2. Show `ci.yml` green on the PR → merge it live.
3. Show `deploy.yml` running: tests → images → push → deploy (~ a few minutes on B1).
4. Hit `/health` and send one transaction through the freshly deployed API.
5. (Optional resilience proof) Show an earlier pipeline run where a failing test stopped the
   deploy — prepare one intentionally broken run in advance.

## Order of execution & estimates

| Step | Depends on | Est. |
|------|-----------|------|
| 1. Dockerfiles + local builds (W3-01) | — | 4 h |
| 2. ACR + platform validation + first manual container deploy (W3-02) | 1 | 4 h |
| 3. `ci.yml` (tests on PRs) | — | 1 h |
| 4. `deploy.yml` + OIDC identity (W3-03) | 2 | 3 h |
| 5. Branch protection on `main` | 3 | 15 min |
| 6. Phase-0 gates land (PR #18, Argenis) | team | external |
| 7. **Release PR develop → main** + tag | 4, 5, 6 | 30 min |
| 8. Demo rehearsal (full point-6 run) | 7 | 1 h |

Steps 1–5 do not wait for the team gates; start immediately.

## Risks

| Risk | Mitigation |
|------|------------|
| Container Apps / consumption quota = zero (history repeats) | Primary target is already Web App for Containers on B1; Container Apps is only an early probe |
| Functions custom container quirks on B1 | Validate trigger registration first; fallback = keep bundled-wheels deploy for the engine, containerize API only (pipeline unchanged) |
| Engine container can't reach subnet-only SQL | VNet integration on `snet-app` (same mechanism the API uses) + firewall check |
| B1 deploy slowness makes the live demo drag | Rehearse; keep images slim; warm the plan before the demo |
| Release merge conflicts (Tobías/Argenis landing late) | Freeze develop at Phase 0; rebase feature branches before their PRs (team norm since PR #15) |
| Pipeline identity over-privileged | Scope: AcrPush + the two web apps + `$web` blob only; federated to `main` ref only |
