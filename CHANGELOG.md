# Changelog

All notable IT Guardian changes are documented here.

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

### Current gate
- Asset administrative endpoints intentionally require `platform_admin` until tenant-scoped inter-service authorization is completed and tested before promotion to v0.3.0.

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
