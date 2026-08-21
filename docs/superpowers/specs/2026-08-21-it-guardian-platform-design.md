# IT Guardian Platform Design

**Date:** 2026-08-21  
**Status:** Approved for implementation  
**Product:** IT Guardian — Sistema Central de Administración Empresarial de TI

## Scope

This design establishes a microservice-first enterprise IT management platform and decomposes the full product into independently deliverable domains. The first implementation slice is `v0.1.0 Foundation + Identity Service`; later domains must integrate through versioned HTTP contracts and canonical NATS events rather than shared database writes.

## Architecture decision

IT Guardian uses full microservices from v0.1.0. Each service owns its domain state, schema/migrations, tests, image, health endpoints, API documentation and release lifecycle. PostgreSQL may share one server/cluster operationally, but every service receives a separate database/schema boundary and credentials.

NATS JetStream is the canonical asynchronous bus. Synchronous calls are reserved for request/response operations that require an immediate answer. Long-running jobs publish commands/events and return a job identifier.

## Frontend decision

The management UI is React + TypeScript with a shared design system, GSAP/CSS motion and a Tauri shell for desktop distribution. The web client consumes Guardian APIs only; it never embeds credentials or directly calls Tactical, Wazuh, GLPI, Zabbix or other engines.

## Agent decision

A common Guardian Agent Protocol defines enrollment, heartbeat, inventory, telemetry, policy, command, result, alert, update, file transfer, ticket and location envelopes. Implementations are platform-specific. Modern Windows/Linux/macOS agents are separated from legacy Windows/macOS implementations. Mobile management uses native/official MDM mechanisms where required.

## Security boundaries

Privileged sessions require MFA in production. Services authorize explicit scopes/roles. Device identity uses certificates or equivalent signed credentials. Integration secrets never reach the browser. Administrative support, location, credential changes, USB exceptions and offline break-glass actions produce audit records.

## First implementation slice: v0.1.0

v0.1.0 creates the repository baseline, developer/run documentation, Docker orchestration primitives and a complete Identity Service baseline. Identity Service owns users, roles, permissions, password hashes, access/refresh tokens and service health. It exposes versioned endpoints and can run standalone with SQLite for tests and PostgreSQL for deployment.

### Identity API v1
- `GET /health/live`
- `GET /health/ready`
- `POST /api/v1/auth/bootstrap`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/users/me`
- `POST /api/v1/users`
- `GET /api/v1/users`
- `PATCH /api/v1/users/{user_id}/status`

Bootstrap is one-time only: it succeeds only when no users exist. It creates the first `platform_admin` user. Passwords are hashed with Argon2. Access tokens are short lived; refresh tokens are longer lived and include token type. Disabled users cannot authenticate or refresh.

### Identity roles
Initial roles are `platform_admin`, `org_admin`, `security_admin`, `it_operator`, `helpdesk`, `auditor`, and `viewer`. v0.1.0 implements role assignment and authorization helpers; fine-grained per-resource ABAC is deferred to Tenant/Asset slices but the role model must not block that extension.

## Operational requirements
- Python 3.12 service target.
- FastAPI and Pydantic v2.
- SQLAlchemy 2.x.
- Alembic-compatible schema layout.
- Argon2 password hashing.
- PyJWT-compatible token handling.
- Docker healthcheck.
- Structured JSON logging baseline.
- `.env` configuration with secrets excluded from source control.
- pytest tests covering health, bootstrap, login, refresh, authorization, duplicate user and disabled-user behavior.

## Error contract

```json
{
  "error": {
    "code": "identity.invalid_credentials",
    "message": "Invalid credentials",
    "request_id": "..."
  }
}
```

No endpoint returns internal tracebacks or password/token material in logs.

## Release rule
`v0.1.0` is not promoted to `main` until Identity Service tests pass, its image definition is present, Compose validates structurally, documentation is complete and the branch is reviewable. The complete product remains pre-1.0 until all Enterprise Stable criteria in `MASTER.md` are met.
