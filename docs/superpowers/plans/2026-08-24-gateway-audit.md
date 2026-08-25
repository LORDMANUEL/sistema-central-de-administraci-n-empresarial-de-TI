# IT Guardian v0.5.0 Gateway + Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a complete tamper-evident Audit Service first, then a controlled northbound Gateway, both clean-stack certified without weakening downstream service authorization.

**Architecture:** Audit owns `guardian_audit`, consumes Guardian JetStream events with durable/manual-ACK semantics and stores tenant-scoped append-only hash chains. Gateway is stateless, uses an explicit static route registry, validates Identity access tokens at the edge, strips spoofable headers, rate-limits requests and publishes audit intent/completion events while every downstream service retains its own authorization.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic, PyJWT/Ed25519 JWKS, httpx, nats-py JetStream, prometheus-client, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-gateway-audit-design.md`

## Global Constraints

- Finish Audit Service completely before production Gateway code begins.
- No shared cross-service writable database.
- No generic arbitrary-host/path proxy.
- No automatic retry for mutating Gateway requests.
- Downstream microservices keep their own authn/authz.
- No bearer/password/enrollment token/hash/CSR/private key/signing seed/full body in Audit metadata or Gateway logs.
- Audit `source_event_id` is globally unique and redelivery-idempotent.
- Audit record chains are tenant-scoped plus one platform chain.
- Audit records are append-only at API and PostgreSQL trigger level.
- Production images run non-root.
- All new behavior follows RED -> GREEN -> refactor.

---

## Phase A — Audit Service (must reach DONE before Gateway implementation)

### Task 1: Audit package, health and CI RED/GREEN

**Files:**
- Create: `services/audit-service/pyproject.toml`
- Create: `services/audit-service/app/__init__.py`
- Create: `services/audit-service/app/config.py`
- Create: `services/audit-service/app/database.py`
- Create: `services/audit-service/app/errors.py`
- Create: `services/audit-service/app/main.py`
- Create: `services/audit-service/tests/test_health.py`
- Create: `.github/workflows/audit-ci.yml`

**Interfaces:**
- Produces `Settings`, `build_engine()`, `build_session_factory()`, `database_ready()`, `create_app()`.

- [ ] Write `test_health.py` first asserting `/health/live`, `/health/ready` and stable Guardian error envelope.
- [ ] Push and verify RED caused by missing `app.main`.
- [ ] Implement minimal settings/database/error/main modules.
- [ ] Re-run Audit CI and require GREEN before Task 2.

### Task 2: Audit persistence model and migration

**Files:**
- Create: `services/audit-service/app/models.py`
- Create: `services/audit-service/alembic.ini`
- Create: `services/audit-service/migrations/env.py`
- Create: `services/audit-service/migrations/script.py.mako`
- Create: `services/audit-service/migrations/versions/20260824_0001_create_audit_domain.py`
- Create: `services/audit-service/tests/test_models.py`
- Modify: `.github/workflows/audit-ci.yml`

**Interfaces:**
- `AuditRecord`, `AuditChainHead`.
- `source_event_id` unique; `(chain_key, sequence)` unique.

- [ ] Write RED tests for constraints/defaults before models exist.
- [ ] Implement model/migration.
- [ ] Migration creates PostgreSQL trigger `guardian_audit_records_append_only` rejecting UPDATE/DELETE.
- [ ] Add CI Alembic `upgrade -> downgrade -> upgrade`.
- [ ] Require GREEN.

### Task 3: Canonical hash chain

**Files:**
- Create: `services/audit-service/app/chain.py`
- Create: `services/audit-service/tests/test_chain.py`

**Interfaces:**
- `canonical_record_bytes(fields: dict) -> bytes`
- `compute_record_hash(fields: dict) -> str`
- `append_record(session, normalized_event) -> AuditRecord`
- `verify_chain(session, chain_key) -> ChainVerification`

- [ ] RED tests prove deterministic hash independent of dict insertion order.
- [ ] RED tests prove genesis uses 64 zeroes and sequence starts at 1.
- [ ] RED tests prove second record references first hash.
- [ ] RED tests prove duplicate `source_event_id` returns existing record without incrementing chain.
- [ ] Implement with transactional chain-head locking.
- [ ] RED/GREEN tamper verification test mutates an in-memory/SQLite row via raw SQL and detects first invalid sequence (PostgreSQL trigger is tested separately).

### Task 4: Event normalization and secret-safe metadata

**Files:**
- Create: `services/audit-service/app/normalize.py`
- Create: `services/audit-service/tests/test_normalize.py`

**Interfaces:**
- `normalize_event(envelope: dict) -> NormalizedAuditEvent`
- `sanitize_metadata(source_type: str, data: dict) -> dict`

- [ ] RED required-envelope validation tests.
- [ ] RED allowlist tests for tenant/hostname/platform/certificate/provider/Gateway metadata.
- [ ] RED recursive forbidden-fragment tests for Authorization/password/token/token_hash/csr/private_key/signing seed/cookies.
- [ ] Implement explicit allowlists; never store arbitrary payload wholesale.
- [ ] Require GREEN.

### Task 5: Identity + Tenant authorization for Audit read API

**Files:**
- Create: `services/audit-service/app/auth.py`
- Create: `services/audit-service/app/tenant_client.py`
- Create: `services/audit-service/tests/test_auth.py`

**Interfaces:**
- `IdentityAccessVerifier.verify(bearer) -> IdentityPrincipal`
- `TenantAccessClient.resolve(tenant_id, bearer) -> tenant access`
- `require_audit_read(principal, tenant_access)`.

- [ ] RED real Ed25519 JWT tests for platform_admin.
- [ ] RED active org_admin/security_admin/auditor tenant access tests.
- [ ] RED viewer/helpdesk/operator/no-member/suspended denial tests.
- [ ] Implement JWKS verifier + Tenant API resolver.
- [ ] Require GREEN.

### Task 6: Read-only Audit API

**Files:**
- Create: `services/audit-service/app/api.py`
- Create: `services/audit-service/app/schemas.py`
- Create: `services/audit-service/tests/test_api.py`
- Modify: `services/audit-service/app/main.py`

**Interfaces:**
- `GET /api/v1/audit/records`
- `GET /api/v1/audit/records/{id}`
- `GET /api/v1/audit/verify?tenant_id=...`

- [ ] RED tests for tenant-scoped list/detail/verify.
- [ ] RED platform-admin global read.
- [ ] RED cross-tenant and disallowed-role denial.
- [ ] RED bounded `limit <= 500` and deterministic pagination.
- [ ] Implement read-only routes; no mutation route exists.
- [ ] Require GREEN.

### Task 7: JetStream durable consumer and idempotent ingestion

**Files:**
- Create: `services/audit-service/app/consumer.py`
- Create: `services/audit-service/tests/test_consumer.py`

**Interfaces:**
- `ingest_message(session_factory, message, ack_callback) -> IngestResult`
- durable `guardian-audit-v1` on `guardian.>`.

- [ ] RED test ACK only after commit.
- [ ] RED duplicate redelivery ACKs without another chain link.
- [ ] RED invalid envelope does not claim successful ingestion.
- [ ] RED simulated DB failure does not ACK.
- [ ] Implement pull consumer with manual ACK and bounded batches.
- [ ] Require GREEN.

### Task 8: Audit observability and secret-safe logs

**Files:**
- Create: `services/audit-service/app/metrics.py`
- Create: `services/audit-service/app/logging.py`
- Create: `services/audit-service/tests/test_observability.py`
- Modify: `services/audit-service/app/main.py`
- Modify: `services/audit-service/app/consumer.py`

- [ ] RED request metric/log tests without Authorization/body.
- [ ] RED consumer counters for received/inserted/duplicate/failed.
- [ ] Implement metrics, request_id and structured log middleware.
- [ ] Require GREEN.

### Task 9: Audit Docker/Compose and append-only PostgreSQL gate

**Files:**
- Create: `services/audit-service/Dockerfile`
- Create: `services/audit-service/.dockerignore`
- Create: `services/audit-service/README.md`
- Modify: `compose.yaml`
- Modify: `.env.example`
- Modify: `.github/workflows/audit-ci.yml`

**Interfaces:**
- DB `guardian_audit`.
- API loopback port 8006.
- `audit-consumer` receives DB + NATS only, no Identity/Enrollment/PKI private signing material.

- [ ] Build image and assert runtime UID != 0.
- [ ] Validate Compose.
- [ ] Start PostgreSQL, migrate Audit, insert one audit row, attempt UPDATE and DELETE using SQL; both must fail due append-only trigger.
- [ ] Require GREEN.

### Task 10: Audit clean-stack certification

**Files:**
- Create: `tests/e2e/audit_smoke.py`
- Modify: `.github/workflows/audit-ci.yml`

- [ ] Start empty complete v0.4 + Audit stack.
- [ ] Bootstrap Identity; create tenant/site/department/asset; enroll device.
- [ ] Wait for Audit to ingest existing Guardian events.
- [ ] Verify tenant chain valid and records queryable.
- [ ] Publish a duplicate event ID; assert no second record/sequence.
- [ ] Create second tenant and prove tenant-scoped user cannot read first tenant.
- [ ] Attempt PostgreSQL UPDATE/DELETE and require failure.
- [ ] Scan Audit record JSON for seeded secret markers and CSR text; require absent.
- [ ] Teardown volumes.
- [ ] Audit Service is DONE only when this clean-stack job is GREEN.

---

## Phase B — Gateway Service (begins only after Audit is DONE)

### Task 11: Gateway package, route registry and health

**Files:**
- Create `services/gateway-service/pyproject.toml`
- Create package modules `config.py`, `errors.py`, `main.py`, `routes.py`.
- Create `services/gateway-service/tests/test_routes.py` and `test_health.py`.
- Create `.github/workflows/gateway-ci.yml`.

- [ ] RED tests require a static allowlist and reject unknown/internal-only routes.
- [ ] Implement only after RED is verified.

### Task 12: Gateway header sanitization + Identity edge verification

**Files:**
- Create `services/gateway-service/app/headers.py`
- Create `services/gateway-service/app/auth.py`
- Tests `test_headers.py`, `test_auth.py`.

- [ ] RED spoofed `X-Guardian-*`, Forwarded/hop-by-hop removal.
- [ ] RED Ed25519 Identity token verification and invalid/expired token rejection.
- [ ] Implement without generating downstream-trusted role/tenant headers.

### Task 13: Gateway limits, rate limiter and proxy semantics

**Files:**
- Create `limits.py`, `rate_limit.py`, `proxy.py` plus tests.

- [ ] RED 413 before upstream for oversize body.
- [ ] RED deterministic token bucket / 429 + Retry-After.
- [ ] RED mutating request exactly once under connection failure.
- [ ] RED GET/HEAD bounded retry only under pre-response connection failure.
- [ ] Implement fixed upstream URL mapping from route registry only.

### Task 14: Gateway audit-intent fail-closed semantics

**Files:**
- Create `audit_publisher.py`, tests `test_audit_publisher.py`, integrate `main.py`/`proxy.py`.

- [ ] RED required mutation does not call upstream when accepted-event JetStream ACK fails.
- [ ] RED successful mutation publishes accepted then completed metadata with same request_id.
- [ ] RED events contain no Authorization/body/token/password/CSR.
- [ ] Implement.

### Task 15: Gateway observability, Docker and Compose

**Files:**
- Create metrics/logging modules, Dockerfile, .dockerignore, README.
- Modify `compose.yaml`, `.env.example`, Gateway CI.

- [ ] Logs expose route_id/request_id/status/duration/upstream but no credentials/body.
- [ ] Docker runtime non-root.
- [ ] Gateway bound to loopback/configured port 8080.
- [ ] Compose validation GREEN.

### Task 16: Full v0.5 clean-stack Gateway + Audit certification

**Files:**
- Create `tests/e2e/gateway_audit_smoke.py`
- Modify Gateway CI and release docs.

- [ ] Run Core setup through Gateway 8080.
- [ ] Verify unknown/internal route blocked.
- [ ] Verify spoofed identity headers stripped.
- [ ] Verify rate limit 429 and body limit 413.
- [ ] Verify privileged mutation is not executed when audit intent publish is unavailable.
- [ ] Verify accepted/completed Gateway events reach Audit and chain verifies.
- [ ] Existing Identity/Tenant/Asset/Enrollment/PKI CIs remain GREEN.
- [ ] Promote `VERSION`/package API versions from `0.5.0-dev.1` to `0.5.0` only after all candidate gates pass.
- [ ] Update README/MASTER/ROADMAP/CHANGELOG accurately.
- [ ] PR ready for squash merge to `main`.
