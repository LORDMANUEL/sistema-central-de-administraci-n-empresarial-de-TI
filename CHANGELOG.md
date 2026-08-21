# Changelog

All notable IT Guardian changes are documented here.

## [0.1.0-dev.1] - 2026-08-21

### Added
- Microservice-first master architecture and Enterprise Stable roadmap.
- Identity Service with one-time transactional platform bootstrap.
- Argon2 password hashing and typed JWT access/refresh tokens.
- Platform-admin RBAC for user management.
- Disabled-account enforcement on login, refresh and protected APIs.
- Stable error envelope with request IDs and sanitized validation details.
- Health/readiness endpoints, Prometheus metrics and structured HTTP logs.
- Initial Alembic identity migration with persistent bootstrap state.
- Non-root Identity Service Docker image definition.
- PostgreSQL + Identity Service Compose deployment.
- CI tests, compile checks, migration smoke test and Compose validation.
