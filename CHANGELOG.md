# Changelog

All notable IT Guardian changes are documented here.

## [0.4.0-dev.1] - 2026-08-24

### PKI Service
- Added isolated `guardian_pki` database and Alembic migration.
- Added Guardian Root CA RSA-4096 and Device Intermediate CA RSA-3072 with idempotent fail-safe initialization.
- Device private keys remain on endpoints; PKI accepts signed CSR requests only.
- Added RSA >=2048, EC P-256 and EC P-384 CSR support with weak/unsupported key rejection.
- Added short-lived Enrollment Ed25519 grants bound to tenant, asset, device, issuance ID and CSR SHA-256.
- Added idempotent device certificate issuance, persistent revocation, signed CRL and atomic certificate rotation.
- Added Identity + Tenant scoped certificate administration.
- Added transactional outbox for `pki.certificate.issued`, `pki.certificate.rotated` and `pki.certificate.revoked`.
- Added Prometheus metrics, request IDs and secret-safe HTTP logging.
- Added non-root Docker image and Compose services for DB init, CA init, migration, API and outbox worker.

### PKI Security
- Root private key is mounted only into `pki-ca-init`.
- Runtime PKI API mounts only the online Intermediate material read-only.
- PKI outbox worker mounts no CA material.
- Enrollment signing private key is not available to PKI runtime.
- Certificate rotation rejects reuse of the previous endpoint key.

### PKI Verification
- PKI unit/integration suite and compile: success.
- Alembic `upgrade -> downgrade -> upgrade`: success.
- Docker build and non-root UID check: success.
- Base Compose and PKI smoke overlay validation: success.
- Clean-stack PKI smoke: success.
- Smoke verified issuance -> revocation -> CRL -> JetStream.
- Smoke verified Root key and Enrollment signer isolation.
- Smoke verified CA initialization idempotence and clean volume teardown.

### Enrollment Service
- Development gate opened after PKI certification.
- Target flow: `token -> validate tenant/asset -> reserve one-time token -> CSR -> PKI grant -> certificate -> device.enrolled`.
- Replay policy: identical retries are idempotent; mismatched reuse is rejected.

## [0.3.0-rc.1] - 2026-08-24

### Added
- Tenant-scoped Asset authorization through Tenant Service without cross-service database access.
- `platform_admin` global access, `org_admin` tenant write access and read-only access for other active tenant memberships.
- Tenant suspension enforcement in Asset Service.
- Inter-service validation of `site_id` and `department_id` before asset persistence.
- Clean-stack E2E gate covering `Identity -> Tenant -> Site/Department -> Asset`.
- JetStream E2E assertion for `guardian.asset.created`.
- Versioned event envelope shared with Tenant (`schema_version`, `type`, `data`).
- Asset outbox delivery state with `attempts` and `last_error`.
- Per-poll retry protection so one failed event is attempted at most once per polling cycle.
- Operational Asset Service documentation for authorization, references, outbox recovery and clean-stack validation.

### Security
- Asset Service validates Identity Ed25519 JWTs and forwards only the caller bearer token to Tenant authorization endpoints.
- Asset Service never reads Tenant tables and never receives the Identity private signing key.
- Invalid, inactive or cross-tenant site/department references are rejected before persistence.

### Verification
- Identity Service CI: success on the Asset candidate path.
- Tenant Service CI: success on the Asset candidate path.
- Asset unit/integration suite, compile and Alembic round-trip: success.
- Asset Docker image build and Compose validation: success.
- Clean-stack `core-e2e`: success, including JetStream event delivery and teardown.

## [0.3.0-dev.1] - 2026-08-23

### Added
- Product roadmap focused on end-to-end functional gates.
- Asset Service canonical domain foundation.
- Stable `guardian_asset_id`, tenant/site/department references and asset classification.
- External identity correlation for engines such as Tactical RMM, Wazuh, GLPI and NetBox.
- Transactional outbox events `asset.created` and `asset.external_identity.linked`.
- Identity Ed25519/JWKS token verification.
- Health/readiness, Prometheus metrics and request IDs.
- Asset database migration, non-root Docker image and Compose integration.
- Asset CI gates for tests, migration round-trip, Docker build and Compose validation.

## [0.2.0-dev.1] - 2026-08-21

### Added
- Tenant Service with tenants, memberships, sites and hierarchical departments.
- Tenant-scoped authorization backed by Identity Ed25519 JWKS.
- Suspended-tenant and inactive-membership enforcement.
- Transactional outbox with NATS JetStream worker and idempotent event IDs.
- Tenant Prometheus metrics, structured request logs and stable error contracts.
- Independent `guardian_tenant` database migration and Docker image.

### Tests
- 25 local Tenant Service tests passing before packaging.
- Alembic upgrade/downgrade/upgrade round-trip verified locally.

## [0.1.0-dev.2] - 2026-08-21

### Security
- Replaced shared-secret HS256 signing with Ed25519/EdDSA asymmetric JWT signing.
- Added `kid`, issuer and audience claims to tokens.
- Added public `/.well-known/jwks.json` so downstream microservices verify tokens without receiving the Identity private signing key.
- Production rejects the deterministic development Ed25519 seed.

### Tests
- Added JWKS verification and issuer/audience coverage; full local suite is 22 tests.

## [0.1.0-dev.1] - 2026-08-21

### Added
- Microservice-first master architecture and Enterprise Stable roadmap.
- Identity Service with one-time platform bootstrap.
- Argon2 password hashing and typed JWT access/refresh tokens.
- Platform-admin RBAC for user management.
- Disabled-account enforcement on login, refresh and protected APIs.
- Stable error envelope with request IDs and sanitized validation details.
- Health/readiness endpoints, Prometheus metrics and structured HTTP logs.
- Initial Alembic identity migration.
- Non-root Identity Service Docker image definition.
- PostgreSQL + Identity Service Compose deployment.
