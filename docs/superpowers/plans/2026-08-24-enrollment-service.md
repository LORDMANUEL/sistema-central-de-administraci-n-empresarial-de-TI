# Enrollment Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independently deployable Enrollment microservice that issues secure one-time asset-bound enrollment tokens, reserves them atomically, orchestrates idempotent PKI certificate issuance from endpoint CSRs, and produces a stable Guardian `device_id` plus `device.enrolled` event.

**Architecture:** Enrollment owns `guardian_enrollment`, its Ed25519 PKI-grant signer and token/device state. Administrators authenticate through Identity and Tenant; Asset is validated via Asset Service API. Endpoint redemption uses only the high-entropy enrollment token. PKI remains the certificate authority and receives a short-lived signed grant; no endpoint or CA private key crosses service boundaries.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic, cryptography, PyJWT EdDSA/JWKS, httpx, NATS JetStream, Prometheus, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-24-enrollment-service-design.md`

## Global Constraints

- Plaintext enrollment tokens are returned once and never persisted.
- Token entropy is >=256 bits from `secrets.token_urlsafe(32)`.
- Default token TTL is 60 minutes; configurable range 5–1440 minutes.
- Endpoint private keys never traverse Guardian APIs; only CSR reaches Enrollment/PKI.
- Enrollment private signing seed is available only to Enrollment API runtime, never PKI or outbox worker.
- Grant lifetime defaults to 60 seconds and must stay <=120 seconds.
- Enrollment uses Identity/Tenant/Asset APIs and never reads their databases.
- Stable `issuance_id` is persisted before PKI call and reused for every retry.
- Identical retry is idempotent; mismatched reuse of a reserved/consumed token is replay and denied.
- Domain changes and events use transactional outbox with at-least-once JetStream delivery.
- Logs/events never contain Authorization, plaintext token, token hash, CSR body or signing seed.

---

### Task 1: Service foundation and signer readiness

**Files:**
- Create: `services/enrollment-service/pyproject.toml`
- Create: `services/enrollment-service/app/__init__.py`
- Create: `services/enrollment-service/app/config.py`
- Create: `services/enrollment-service/app/database.py`
- Create: `services/enrollment-service/app/errors.py`
- Create: `services/enrollment-service/app/signing.py`
- Create: `services/enrollment-service/app/main.py`
- Test: `services/enrollment-service/tests/test_health_and_signing.py`

**Interfaces:**
- Produces `Settings`, `EnrollmentGrantSigner`, `create_app()` and `/.well-known/jwks.json`.

- [ ] Write RED tests proving `/health/live` is 200, readiness rejects missing/invalid signing seed, valid seed makes readiness DB+signer ready, and JWKS exposes only the Ed25519 public key/kid.
- [ ] Run `pytest tests/test_health_and_signing.py -q`; expected RED because Enrollment app/signer do not exist.
- [ ] Implement settings, DB boundary, Guardian error/request-id contract and Ed25519 signer/JWKS.
- [ ] Ensure production signer seed decodes to exactly 32 bytes and is never included in output/logs.
- [ ] Run the targeted test and full suite; expected GREEN.

### Task 2: Token/device persistence and Alembic baseline

**Files:**
- Create: `services/enrollment-service/app/models.py`
- Create: `services/enrollment-service/alembic.ini`
- Create: `services/enrollment-service/migrations/env.py`
- Create: `services/enrollment-service/migrations/script.py.mako`
- Create: `services/enrollment-service/migrations/versions/20260824_0001_create_enrollment_domain.py`
- Test: `services/enrollment-service/tests/test_models.py`

**Interfaces:**
- Produces `EnrollmentToken`, `DeviceEnrollment`, `EnrollmentStatus`, `OutboxEvent`.

- [ ] Write RED tests for unique `token_hash`, unique `device_id`, unique `issuance_id`, one enrollment per token, token reservation/consumption fields and resilient outbox state.
- [ ] Implement SQLAlchemy models and indexes for tenant/asset/status/expiry.
- [ ] Add Alembic baseline matching models.
- [ ] Run tests GREEN.
- [ ] Run SQLite Alembic `upgrade -> downgrade -> upgrade`; expected success.

### Task 3: Token cryptography and request fingerprint

**Files:**
- Create: `services/enrollment-service/app/tokens.py`
- Test: `services/enrollment-service/tests/test_tokens.py`

**Interfaces:**
- Produces `generate_enrollment_token() -> PlainToken`, `hash_token(str) -> str`, `token_hint(str) -> str`, `request_fingerprint(...) -> str`.

- [ ] Write RED test asserting prefix `gdt_`, >=256-bit random payload, stable SHA-256 hash, non-secret hint, and deterministic canonical request fingerprint.
- [ ] Implement using `secrets.token_urlsafe(32)`, `hashlib.sha256` and canonical normalized fields.
- [ ] Run GREEN and prove two generated tokens differ.

### Task 4: Identity/Tenant administrator authorization

**Files:**
- Create: `services/enrollment-service/app/auth.py`
- Create: `services/enrollment-service/app/tenant_client.py`
- Test: `services/enrollment-service/tests/test_admin_auth.py`

**Interfaces:**
- Produces `IdentityAccessVerifier`, `IdentityPrincipal`, `TenantAccessDecision`, `enforce_enrollment_admin()`.

- [ ] Write RED tests with real Ed25519 Identity JWT fixture.
- [ ] Assert `platform_admin` global without Tenant lookup.
- [ ] Assert active `org_admin` tenant access.
- [ ] Assert viewer/nonmember/suspended tenant denied.
- [ ] Implement Identity JWKS cache/refresh and Tenant `/access` client without DB sharing.
- [ ] Run GREEN.

### Task 5: Asset validation client

**Files:**
- Create: `services/enrollment-service/app/asset_client.py`
- Test: `services/enrollment-service/tests/test_asset_client.py`

**Interfaces:**
- Produces `AssetClient.get(asset_id, bearer_token) -> AssetReference` and `validate_asset_tenant()`.

- [ ] Write RED tests for valid asset, 404, 403, 5xx/network and tenant mismatch.
- [ ] Implement GET `/api/v1/assets/{asset_id}` forwarding only admin bearer token.
- [ ] Normalize errors to `enrollment.asset_*` codes.
- [ ] Run GREEN.

### Task 6: Administrative token create/list/revoke API

**Files:**
- Create: `services/enrollment-service/app/schemas.py`
- Create: `services/enrollment-service/app/admin_api.py`
- Test: `services/enrollment-service/tests/test_token_api.py`

**Interfaces:**
- Produces `POST/GET /api/v1/enrollment-tokens` and `POST /api/v1/enrollment-tokens/{id}/revoke`.

- [ ] RED: org/platform admin can create an asset-bound token only after Asset validation.
- [ ] RED: plaintext token appears only in create response; DB/list/revoke never expose token/hash.
- [ ] RED: expiry range 5–1440 enforced.
- [ ] RED: create inserts `enrollment.token.created` in same transaction.
- [ ] RED: revoke is idempotent and emits one `enrollment.token.revoked` event.
- [ ] Implement minimal APIs and schemas.
- [ ] Run GREEN.

### Task 7: CSR validation before reservation

**Files:**
- Create: `services/enrollment-service/app/csr.py`
- Test: `services/enrollment-service/tests/test_csr.py`

**Interfaces:**
- Produces `validate_csr(pem: str) -> ValidatedCSR` with DER SHA-256.

- [ ] RED for RSA-2048, P-256/P-384 success.
- [ ] RED for malformed/tampered CSR, RSA-1024 and P-521 rejection.
- [ ] Implement profile matching PKI without importing PKI code/DB.
- [ ] Run GREEN.

### Task 8: Atomic token reservation and retry/replay state machine

**Files:**
- Create: `services/enrollment-service/app/reservation.py`
- Test: `services/enrollment-service/tests/test_reservation.py`

**Interfaces:**
- Produces `reserve_or_resume(session, token_plaintext, request_data) -> ReservationResult`.

- [ ] RED: unknown/expired/revoked token does not mutate DB.
- [ ] RED: first redemption creates stable `device_id`, stable `issuance_id`, PENDING enrollment and RESERVED token atomically.
- [ ] RED: identical retry while RESERVED returns same enrollment/IDs.
- [ ] RED: mismatched retry while RESERVED raises `enrollment.token_replay`.
- [ ] RED: identical retry after CONSUMED returns existing enrollment.
- [ ] RED: mismatched retry after CONSUMED raises replay.
- [ ] Implement row lock (`SELECT ... FOR UPDATE`) + unique constraints.
- [ ] Add concurrency integration test proving two competing different requests cannot both reserve.
- [ ] Run GREEN.

### Task 9: PKI grant and client

**Files:**
- Modify: `services/enrollment-service/app/signing.py`
- Create: `services/enrollment-service/app/pki_client.py`
- Test: `services/enrollment-service/tests/test_pki_client.py`

**Interfaces:**
- Produces `EnrollmentGrantSigner.create_issue_grant(...) -> str`, `PKIClient.issue(...) -> PKICertificateResult`.

- [ ] RED: grant has correct issuer/audience/type/sub/kid and bound claims; lifetime <=120 s.
- [ ] RED: client sends grant server-to-server and never returns it to endpoint data.
- [ ] RED: 201 and idempotent 200 accepted.
- [ ] RED: network/5xx retries reuse same issuance ID/request.
- [ ] RED: 409 maps to `enrollment.pki_issuance_conflict`; deterministic 4xx maps to `enrollment.pki_rejected`.
- [ ] Implement signer grant and bounded retry client.
- [ ] Run GREEN.

### Task 10: Endpoint enrollment orchestration

**Files:**
- Create: `services/enrollment-service/app/enrollment_api.py`
- Test: `services/enrollment-service/tests/test_enrollment_api.py`

**Interfaces:**
- Produces `POST /api/v1/enrollments` without Identity bearer requirement.

- [ ] RED happy path with real token, real CSR and fake-but-contract-accurate PKI client: reservation -> PKI -> certificate persistence -> ENROLLED -> token CONSUMED.
- [ ] Assert response contains stable device/certificate public data only.
- [ ] Assert `device.enrolled` outbox event is transactional with finalization.
- [ ] Assert identical consumed retry returns same certificate/device and does not call PKI again.
- [ ] Implement orchestration around Tasks 8/9.
- [ ] Run GREEN.

### Task 11: Failure recovery semantics

**Files:**
- Modify: `services/enrollment-service/app/reservation.py`
- Modify: `services/enrollment-service/app/enrollment_api.py`
- Test: `services/enrollment-service/tests/test_enrollment_recovery.py`

**Interfaces:**
- Produces deterministic release vs transient reservation behavior.

- [ ] RED: PKI network/5xx keeps token RESERVED/PENDING with same issuance ID; identical retry resumes.
- [ ] RED: deterministic PKI 4xx before certificate clears reservation, marks attempt FAILED and emits `device.enrollment.failed`.
- [ ] RED: retry after deterministic release can create a new enrollment only if no certificate exists and token remains active/unexpired.
- [ ] RED: PKI response success followed by local finalization retry never creates a new issuance ID.
- [ ] Implement minimal recovery state transitions.
- [ ] Run GREEN.

### Task 12: Enrollment inventory API

**Files:**
- Modify: `services/enrollment-service/app/admin_api.py`
- Test: `services/enrollment-service/tests/test_enrollment_inventory.py`

**Interfaces:**
- Produces `GET /api/v1/enrollments?tenant_id=...` and `GET /api/v1/enrollments/{device_id}`.

- [ ] RED for platform admin global and org admin tenant scope.
- [ ] RED cross-tenant denial.
- [ ] Assert responses never expose token hash, request fingerprint, CSR or signing material.
- [ ] Implement list/get.
- [ ] Run GREEN.

### Task 13: Resilient outbox and observability

**Files:**
- Create: `services/enrollment-service/app/outbox_worker.py`
- Create: `services/enrollment-service/app/metrics.py`
- Create: `services/enrollment-service/app/logging.py`
- Test: `services/enrollment-service/tests/test_outbox.py`
- Test: `services/enrollment-service/tests/test_observability.py`

**Interfaces:**
- Produces Guardian schema-v1 events, JetStream worker and `/metrics`.

- [ ] RED common envelope/ACK/attempts/last_error/one-attempt-per-poll tests.
- [ ] RED metrics endpoint and domain counter names.
- [ ] RED logging test with marker values proving Authorization/token/CSR/body never appear.
- [ ] Implement resilient worker and secret-safe HTTP logging.
- [ ] Run GREEN.

### Task 14: Docker/Compose isolation and CI

**Files:**
- Create: `services/enrollment-service/Dockerfile`
- Create: `services/enrollment-service/.dockerignore`
- Create: `services/enrollment-service/README.md`
- Modify: `compose.yaml`
- Modify: `.env.example`
- Create: `.github/workflows/enrollment-ci.yml`

**Interfaces:**
- Produces `enrollment-db-init`, `enrollment-migrate`, `enrollment-service`, `enrollment-outbox-worker`.

- [ ] Add DB `guardian_enrollment` and loopback port 8005.
- [ ] Mount/present `ENROLLMENT_SIGNING_KEY` only to API runtime; worker must not receive it.
- [ ] Configure PKI `PKI_ENROLLMENT_JWKS_URL=http://enrollment-service:8000/.well-known/jwks.json`.
- [ ] Build non-root Enrollment image and assert UID !=0 in CI.
- [ ] Add compile/tests/migration round-trip/Compose gates.
- [ ] Run CI GREEN before E2E.

### Task 15: Clean-stack v0.4 E2E certification

**Files:**
- Create: `tests/e2e/enrollment_core.py`
- Create: `tests/e2e/compose.enrollment-smoke.yaml` only if an overlay is required.
- Modify: `.github/workflows/enrollment-ci.yml`
- Modify: `ROADMAP.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`

**Interfaces:**
- Produces the release gate `Identity -> Tenant -> Asset -> Enrollment -> PKI -> JetStream`.

- [ ] Start from empty Compose volumes and build all images.
- [ ] Bootstrap/login Identity platform admin.
- [ ] Create Tenant, Site and Department.
- [ ] Create Asset bound to the Tenant references.
- [ ] Create Enrollment token through the admin API and capture plaintext only in smoke client memory.
- [ ] Generate endpoint EC P-256 private key locally in smoke client; create CSR.
- [ ] Redeem token through Enrollment and verify returned certificate matches endpoint key and chains to Guardian CA.
- [ ] Verify `device.enrolled` in JetStream schema v1.
- [ ] Retry identical token/CSR and assert same device/certificate with no duplicate PKI certificate/event.
- [ ] Reuse token with different CSR and assert `enrollment.token_replay`.
- [ ] Inspect container mounts/env: PKI cannot access Enrollment signing seed; Enrollment worker cannot access signer seed; endpoint private key exists only in smoke client process.
- [ ] Verify Enrollment/PKI/Asset/Identity/Tenant health/readiness.
- [ ] Tear down containers and volumes.
- [ ] Require Identity, Tenant, Asset, PKI and Enrollment workflows all green on the same candidate SHA.
- [ ] Update v0.4 status to RC only after every gate succeeds.
