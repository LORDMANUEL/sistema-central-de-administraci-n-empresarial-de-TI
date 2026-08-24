# Changelog

All notable IT Guardian changes are documented here.

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
