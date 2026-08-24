# Tenant Service

Source of truth for IT Guardian organizations, memberships, sites and departments.

## Responsibilities

- tenant creation and lifecycle (`active` / `suspended`);
- tenant-scoped memberships and roles;
- physical/logical sites with location metadata;
- hierarchical departments with cycle protection;
- Ed25519 JWT validation through Identity JWKS;
- reliable transactional outbox for domain events;
- NATS JetStream worker using at-least-once delivery;
- health/readiness, Prometheus metrics and structured HTTP logs.

Tenant Service never receives `IDENTITY_SIGNING_KEY` and never writes the Identity database.

## Tenant-scoped roles

`org_admin`, `security_admin`, `it_operator`, `helpdesk`, `auditor`, `viewer`.

`platform_admin` is a global Identity role and bypasses tenant membership checks. All other users need an active membership. Only `org_admin` (or `platform_admin`) may mutate tenant structure and memberships.

## API

| Method | Endpoint | Capability |
|---|---|---|
| GET | `/health/live` | process liveness |
| GET | `/health/ready` | DB readiness |
| GET | `/metrics` | Prometheus metrics |
| POST | `/api/v1/tenants` | create tenant (platform admin) |
| GET | `/api/v1/tenants` | visible tenants |
| GET | `/api/v1/tenants/{id}` | tenant detail |
| PATCH | `/api/v1/tenants/{id}` | tenant update |
| POST | `/api/v1/tenants/{id}/memberships` | create/upsert membership |
| GET | `/api/v1/tenants/{id}/memberships` | list memberships |
| PATCH | `/api/v1/tenants/{id}/memberships/{user_id}` | role/status update |
| POST | `/api/v1/tenants/{id}/sites` | create site |
| GET | `/api/v1/tenants/{id}/sites` | list sites |
| PATCH | `/api/v1/tenants/{id}/sites/{site_id}` | update site |
| POST | `/api/v1/tenants/{id}/departments` | create department |
| GET | `/api/v1/tenants/{id}/departments` | list departments |
| PATCH | `/api/v1/tenants/{id}/departments/{department_id}` | update department/hierarchy |

## Events

Mutations persist events in `outbox_events` in the same DB transaction. The worker publishes subjects such as:

```text
guardian.tenant.created
guardian.tenant.updated
guardian.tenant.membership.upserted
guardian.tenant.site.created
guardian.tenant.site.updated
guardian.tenant.department.created
guardian.tenant.department.updated
```

Each envelope has an immutable `event_id`. NATS receives it as `Nats-Msg-Id`; consumers must also use `event_id` idempotently because an acknowledged publish followed by a DB crash can legitimately be delivered again.

## Local tests

```bash
cd services/tenant-service
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

## Migration

```bash
export TENANT_DATABASE_URL='sqlite+pysqlite:///./tenant.db'
alembic upgrade head
```

Production uses PostgreSQL and the root Compose stack creates `guardian_tenant` separately from `guardian_identity`.

## Worker

```bash
python -m app.outbox_worker
```

The API remains available if NATS is temporarily unavailable because writes are buffered transactionally in the outbox.
