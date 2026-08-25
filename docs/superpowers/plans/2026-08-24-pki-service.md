# PKI Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independently deployable PKI service that initializes a CA hierarchy, validates Enrollment grants and CSRs, issues/rotates/revokes device certificates, publishes a CRL and reliably emits PKI domain events.

**Architecture:** `pki-service` owns `guardian_pki`, online intermediate signing material and certificate state. Device private keys remain on endpoints; issuance is authorized by short-lived Ed25519 Enrollment grants, while management is authorized through Identity JWKS + Tenant Service. PKI events use the existing transactional-outbox/JetStream pattern.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic, cryptography, PyJWT EdDSA/JWKS, httpx, NATS JetStream, Prometheus, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-24-pki-service-design.md`

## Global Constraints

- Device private keys are never uploaded to Guardian.
- Root private key is not mounted into runtime API/worker containers.
- `guardian_pki` is written only by `pki-service`.
- API behavior lives under `/api/v1`.
- Initial CSR keys: RSA >= 2048, EC P-256/P-384.
- Default device certificate lifetime is 30 days; configured range is 1–90 days.
- Issuance grant max lifetime is 120 seconds and must bind CSR SHA-256 + tenant + asset + device + issuance ID.
- `issuance_id` is globally unique and idempotent.
- PKI management uses Identity + Tenant authorization; no shared database reads.
- Outbox delivery is at-least-once with `Nats-Msg-Id=event_id`.
- Service requires health/readiness, metrics, structured logs, Docker, migrations, documentation and CI before DONE.

---

### Task 1: Service foundation, configuration and health

**Files:**
- Create: `services/pki-service/pyproject.toml`
- Create: `services/pki-service/app/__init__.py`
- Create: `services/pki-service/app/config.py`
- Create: `services/pki-service/app/database.py`
- Create: `services/pki-service/app/errors.py`
- Create: `services/pki-service/app/main.py`
- Test: `services/pki-service/tests/test_health.py`

**Interfaces:**
- Produces: `Settings`, `build_engine()`, `build_session_factory()`, `get_db()`, `create_app() -> FastAPI`.

- [ ] Write failing tests proving `/health/live` is 200 and `/health/ready` is 503 when signer material is unavailable.
- [ ] Run `python -m pytest tests/test_health.py -q` and observe RED because `app.main`/readiness do not exist.
- [ ] Implement settings for DB, CA paths, certificate lifetime, Identity JWKS, Enrollment JWKS, Tenant URL and NATS.
- [ ] Implement request-ID Guardian error envelope and DB readiness.
- [ ] Implement minimal FastAPI app with live/ready endpoints; ready requires DB and loadable intermediate signer material.
- [ ] Re-run test and observe GREEN.

### Task 2: Idempotent CA hierarchy initialization

**Files:**
- Create: `services/pki-service/app/ca.py`
- Test: `services/pki-service/tests/test_ca.py`

**Interfaces:**
- Produces: `initialize_ca(root_dir: Path, online_dir: Path) -> CAPaths`, `load_signer(settings) -> SignerMaterial`.

- [ ] Write failing tests that initialize root RSA-4096 + intermediate RSA-3072, verify signatures/CA extensions and verify a second initialization does not replace existing serials/keys.
- [ ] Observe RED.
- [ ] Implement atomic file generation with restrictive modes, self-signed root and intermediate signed by root.
- [ ] Persist root cert into online directory but keep root private key only in root directory.
- [ ] Re-run and observe GREEN.

### Task 3: Certificate persistence and Alembic baseline

**Files:**
- Create: `services/pki-service/app/models.py`
- Create: `services/pki-service/migrations/env.py`
- Create: `services/pki-service/migrations/script.py.mako`
- Create: `services/pki-service/migrations/versions/20260824_0001_create_pki_domain.py`
- Create: `services/pki-service/alembic.ini`
- Test: `services/pki-service/tests/test_models.py`

**Interfaces:**
- Produces: `Certificate`, `CertificateStatus`, `OutboxEvent`.

- [ ] Write tests for unique `issuance_id`, serial/fingerprint uniqueness and revocation fields.
- [ ] Observe RED.
- [ ] Implement models and indexes for tenant/asset/device/status/expiry.
- [ ] Add outbox with attempts/last_error/published_at.
- [ ] Add Alembic baseline.
- [ ] Run tests GREEN and run SQLite migration `upgrade -> downgrade -> upgrade`.

### Task 4: Enrollment grant verification

**Files:**
- Create: `services/pki-service/app/grants.py`
- Test: `services/pki-service/tests/test_grants.py`

**Interfaces:**
- Produces: `EnrollmentGrantVerifier.verify(token: str, expected_type: str) -> EnrollmentGrant`.

- [ ] Write Ed25519 test-key fixture and failing tests for valid grant, expired grant, wrong audience/issuer/type, missing `kid`, unknown key and lifetime >120 seconds.
- [ ] Observe RED.
- [ ] Implement cached Enrollment JWKS retrieval with one forced refresh on unknown `kid`.
- [ ] Require all grant binding claims.
- [ ] Re-run and observe GREEN.

### Task 5: CSR validation and certificate profile

**Files:**
- Create: `services/pki-service/app/certificates.py`
- Test: `services/pki-service/tests/test_certificates.py`

**Interfaces:**
- Produces: `parse_and_validate_csr(pem: str) -> ValidatedCSR`, `issue_device_certificate(...) -> IssuedCertificate`.

- [ ] Write failing tests for valid RSA-2048, EC P-256/P-384, invalid CSR signature, RSA-1024 and unsupported EC curve.
- [ ] Observe RED.
- [ ] Implement CSR SHA-256 and public-key policy checks.
- [ ] Write failing certificate-profile test asserting chain signature, SAN URI, CA=false, CLIENT_AUTH, SKI/AKI and lifetime.
- [ ] Implement certificate signing with intermediate CA and secure random serial.
- [ ] Observe GREEN.

### Task 6: Idempotent issuance API

**Files:**
- Create: `services/pki-service/app/schemas.py`
- Create: `services/pki-service/app/api.py`
- Test: `services/pki-service/tests/test_issue_api.py`

**Interfaces:**
- Produces: `POST /api/v1/certificates/issue`.

- [ ] Write failing tests for successful issuance using a real Ed25519 grant + real CSR.
- [ ] Add tests binding grant claims to CSR SHA, tenant, asset, device and issuance ID.
- [ ] Add retry test: identical issuance ID returns same serial/certificate without a second DB record.
- [ ] Add conflict test: same issuance ID + different CSR/device returns 409.
- [ ] Observe RED.
- [ ] Implement endpoint, binding validation, transaction and `pki.certificate.issued` outbox event.
- [ ] Re-run and observe GREEN.

### Task 7: Identity/Tenant management authorization

**Files:**
- Create: `services/pki-service/app/auth.py`
- Create: `services/pki-service/app/tenant_client.py`
- Test: `services/pki-service/tests/test_admin_auth.py`

**Interfaces:**
- Produces: `IdentityPrincipal`, `require_pki_admin(tenant_id)` behavior.

- [ ] Write failing tests using real Identity-style Ed25519 JWTs.
- [ ] Assert platform admin global access.
- [ ] Assert org admin access only for active tenant resolved by Tenant Service.
- [ ] Assert viewer/nonmember/suspended tenant denied.
- [ ] Observe RED.
- [ ] Implement Identity JWKS verification and Tenant access client without DB sharing.
- [ ] Observe GREEN.

### Task 8: Inventory and revocation API + CRL

**Files:**
- Modify: `services/pki-service/app/api.py`
- Modify: `services/pki-service/app/certificates.py`
- Test: `services/pki-service/tests/test_revocation.py`

**Interfaces:**
- Produces: certificate list/get/revoke endpoints plus `GET /api/v1/ca/chain` and `GET /api/v1/ca/crl`.

- [ ] Write failing list/get tenant-scope tests.
- [ ] Write failing idempotent revocation tests with reason persistence.
- [ ] Write failing CRL test proving revoked serial is present and CRL verifies under intermediate CA.
- [ ] Observe RED.
- [ ] Implement APIs and signed CRL builder with next update + CRL number.
- [ ] Emit `pki.certificate.revoked` transactionally.
- [ ] Observe GREEN.

### Task 9: Rotation

**Files:**
- Modify: `services/pki-service/app/api.py`
- Modify: `services/pki-service/app/certificates.py`
- Test: `services/pki-service/tests/test_rotation.py`

**Interfaces:**
- Produces: `POST /api/v1/certificates/rotate`.

- [ ] Write failing tests requiring `certificate_rotate` grant and matching old tenant/asset/device.
- [ ] Assert a new CSR/new issuance ID yields a new active certificate.
- [ ] Assert old certificate becomes revoked `superseded` only after replacement issuance succeeds.
- [ ] Assert mismatch leaves old certificate active.
- [ ] Observe RED.
- [ ] Implement atomic rotation domain transaction and `pki.certificate.rotated` event.
- [ ] Observe GREEN.

### Task 10: Resilient outbox worker

**Files:**
- Create: `services/pki-service/app/outbox_worker.py`
- Test: `services/pki-service/tests/test_outbox.py`

**Interfaces:**
- Produces: `event_envelope()`, `publish_pending_once()`, `NatsJetStreamPublisher`.

- [ ] Write failing tests for common schema_version=1 envelope, publish-on-ACK, failure retention, attempts/last_error and max-one-attempt-per-event-per-poll.
- [ ] Observe RED.
- [ ] Implement the same proven resilient pattern as Tenant/Asset.
- [ ] Observe GREEN.

### Task 11: Observability and secret-safe logging

**Files:**
- Create: `services/pki-service/app/metrics.py`
- Create: `services/pki-service/app/logging.py`
- Test: `services/pki-service/tests/test_observability.py`

**Interfaces:**
- Produces Prometheus endpoint/counters and structured HTTP logs.

- [ ] Write failing tests for `/metrics`, request IDs and log records without Authorization/CSR/private-key contents.
- [ ] Implement counters for HTTP, issuance, rotation, revocation and outbox results.
- [ ] Observe GREEN.

### Task 12: Docker/Compose isolation

**Files:**
- Create: `services/pki-service/Dockerfile`
- Create: `services/pki-service/.dockerignore`
- Create: `services/pki-service/README.md`
- Modify: `compose.yaml`
- Modify: `.env.example`

**Interfaces:**
- Produces `pki-db-init`, `pki-ca-init`, `pki-migrate`, `pki-service`, `pki-outbox-worker` and PKI volumes.

- [ ] Create fixed non-root runtime UID/GID and image.
- [ ] Add root/online CA volumes; mount root key volume only into `pki-ca-init`.
- [ ] Mount online signer read-only in API/worker containers.
- [ ] Add independent `guardian_pki` database creation/migration.
- [ ] Bind API to loopback until Gateway exists.
- [ ] Run `docker compose config --quiet` in CI.

### Task 13: CI and clean PKI smoke test

**Files:**
- Create: `.github/workflows/pki-ci.yml`
- Create: `tests/e2e/pki_smoke.py`
- Modify: `ROADMAP.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`

**Interfaces:**
- Produces a reproducible v0.4 PKI gate.

- [ ] CI Python 3.12: install, compile, full tests, migration round-trip.
- [ ] Docker build PKI image.
- [ ] Compose config validation.
- [ ] Clean-stack smoke: initialize CA, start DB/migration/API, confirm chain/readiness.
- [ ] Generate endpoint private key + CSR inside smoke client.
- [ ] Use test Enrollment grant signer only inside E2E fixture to exercise actual PKI issuance endpoint.
- [ ] Verify returned certificate chains to Guardian intermediate/root and endpoint private key remains only in smoke client process.
- [ ] Revoke certificate and verify CRL contains serial.
- [ ] Teardown volumes/containers.
- [ ] Require all jobs green before marking PKI DONE and starting Enrollment Service.
