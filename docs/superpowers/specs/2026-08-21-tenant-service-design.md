# Tenant Service Design

**Date:** 2026-08-21  
**Version target:** v0.2.0  
**Status:** Approved by the platform-level module roadmap

## Purpose

Tenant Service is the source of truth for organizations, tenant membership, physical/logical sites and departments. It never writes Identity data and never receives the Identity private signing key. It authorizes callers by verifying Identity access JWTs against public Ed25519 JWKS.

## Domain

- `Tenant`: name, globally unique slug, status, timezone, locale and timestamps.
- `TenantMembership`: maps Identity `user_id` to a tenant-scoped role and active state.
- `Site`: tenant-owned site code/name and optional address/geolocation metadata.
- `Department`: tenant-owned code/name with optional parent department hierarchy.
- `OutboxEvent`: transactional domain event waiting for NATS publication.

No destructive delete API is exposed in v0.2.0. State changes use active/suspended flags so historical references remain valid.

## Authorization

Global `platform_admin` may manage every tenant. Other identities see only tenants with active memberships. Tenant-scoped mutation requires active membership role `org_admin`; read operations accept any active membership. A suspended tenant remains administratively visible to `platform_admin`, while tenant members are denied operational access.

## Authentication

Access tokens must be `type=access`, signed with an Ed25519 key whose `kid` exists in Identity JWKS, and contain valid `iss`, `aud`, `sub`, `role`, `iat`, `exp`, and `jti`. JWKS is cached for a bounded period and refreshed when an unknown `kid` is encountered.

## API v1

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`
- `POST /api/v1/tenants`
- `GET /api/v1/tenants`
- `GET /api/v1/tenants/{tenant_id}`
- `PATCH /api/v1/tenants/{tenant_id}`
- `POST /api/v1/tenants/{tenant_id}/memberships`
- `GET /api/v1/tenants/{tenant_id}/memberships`
- `PATCH /api/v1/tenants/{tenant_id}/memberships/{user_id}`
- `POST /api/v1/tenants/{tenant_id}/sites`
- `GET /api/v1/tenants/{tenant_id}/sites`
- `PATCH /api/v1/tenants/{tenant_id}/sites/{site_id}`
- `POST /api/v1/tenants/{tenant_id}/departments`
- `GET /api/v1/tenants/{tenant_id}/departments`
- `PATCH /api/v1/tenants/{tenant_id}/departments/{department_id}`

## Events

Database transactions write these canonical event types to the outbox:

- `tenant.created`
- `tenant.updated`
- `tenant.membership.upserted`
- `tenant.site.created`
- `tenant.site.updated`
- `tenant.department.created`
- `tenant.department.updated`

The worker publishes them to NATS subjects prefixed with `guardian.` using JetStream acknowledgment before marking `published_at`.

## Operational boundaries

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, NATS JetStream, PyJWT/cryptography, Prometheus and structured JSON HTTP logs. SQLite is used only by tests. The API and outbox worker ship from one non-root Docker image with different commands.
