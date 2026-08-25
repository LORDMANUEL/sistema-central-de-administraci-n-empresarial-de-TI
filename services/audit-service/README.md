# IT Guardian Audit Service

Append-only, tenant-scoped and tamper-evident audit microservice for IT Guardian.

## Responsibilities

- Consume Guardian events from NATS JetStream using durable manual-ACK semantics.
- Normalize events into a strict secret-safe audit schema.
- Persist one SHA-256 hash chain per tenant plus a platform chain.
- Reject redelivery duplicates by globally unique `source_event_id`.
- Expose read-only audit list, detail and chain verification APIs.
- Enforce Identity JWT verification and Tenant Service authorization for reads.
- Reject PostgreSQL `UPDATE` and `DELETE` against `audit_records` with a database trigger.
- Expose health and Prometheus metrics without logging request bodies or credentials.

## Runtime topology

The production Compose stack runs three Audit processes around one dedicated database:

- `audit-migrate`: one-shot Alembic migration job.
- `audit-service`: FastAPI read-only API on container port `8000`, mapped by default to host loopback `8006`.
- `audit-consumer`: JetStream consumer running `python -m app.consumer`.

The database is created separately as `guardian_audit`. Audit does not share writable tables with Identity, Tenant, Asset, Enrollment or PKI.

## Required configuration

All application settings use the `AUDIT_` prefix.

| Variable | Purpose |
| --- | --- |
| `AUDIT_DATABASE_URL` | SQLAlchemy PostgreSQL URL for `guardian_audit`. |
| `AUDIT_IDENTITY_JWKS_URL` | Identity public JWKS endpoint used by the read API. |
| `AUDIT_IDENTITY_ISSUER` | Expected Identity issuer. |
| `AUDIT_IDENTITY_AUDIENCE` | Expected Identity audience. |
| `AUDIT_TENANT_SERVICE_URL` | Tenant authorization service base URL. |
| `AUDIT_NATS_URL` | NATS connection URL used by the consumer. |
| `AUDIT_NATS_STREAM` | JetStream stream, default `GUARDIAN_EVENTS`. |
| `AUDIT_NATS_DURABLE` | Durable consumer name, default `guardian-audit-v1`. |
| `AUDIT_CONSUMER_BATCH_SIZE` | Pull batch size, bounded to 1..500. |

The consumer container intentionally receives only its database/NATS settings. It must never receive Identity, Enrollment or PKI private signing material.

## API

Health and metrics:

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`

Read-only audit endpoints:

- `GET /api/v1/audit/records`
- `GET /api/v1/audit/records/{id}`
- `GET /api/v1/audit/verify?tenant_id=<tenant-id>`

There are no API routes that mutate or delete audit records.

## Authorization

- `platform_admin`: global read access.
- Active tenant members with `org_admin`, `security_admin` or `auditor`: read access only to the authorized tenant.
- Other roles, non-members and suspended tenants are denied.

The Audit Service validates Ed25519 Identity access tokens with public JWKS and asks Tenant Service for tenant membership. It does not read Identity/Tenant databases directly.

## Event ingestion guarantees

`audit-consumer` uses JetStream durable `guardian-audit-v1` on `guardian.>`.

1. Pull message.
2. Parse and normalize using explicit metadata allowlists.
3. Append to the tenant/platform hash chain inside a database transaction.
4. Commit.
5. ACK only after the commit succeeds, or after an existing duplicate is confirmed.

Malformed events or database failures are left unacknowledged for JetStream redelivery. Driver exception text and raw event payloads are not written to logs.

## Tamper evidence and append-only enforcement

Each record contains `prev_hash` and `record_hash`; the first record uses 64 zeroes as the genesis previous hash. `GET /api/v1/audit/verify` recomputes a chain and reports the first invalid sequence if tampering is detected.

PostgreSQL additionally installs trigger `guardian_audit_records_append_only`, which raises on `UPDATE` or `DELETE` of `audit_records`. CI verifies this behavior against real PostgreSQL, not only SQLite tests.

## Local verification

From the repository root, with required Compose secrets configured:

```bash
docker compose config --quiet
docker compose build audit-service audit-consumer
docker compose up -d postgres nats
docker compose up audit-db-init audit-migrate
docker compose up -d audit-service audit-consumer
```

Then verify:

```bash
curl -fsS http://127.0.0.1:8006/health/ready
curl -fsS http://127.0.0.1:8006/metrics
```

For a complete release candidate, use the repository Audit CI clean-stack certification rather than treating these commands as certification.

## Security invariants

Never persist or log full request/event bodies, Authorization headers, passwords, enrollment tokens, token hashes, cookies, CSRs, private keys or signing seeds. New event types must extend an explicit allowlist and receive RED/GREEN tests before additional metadata is admitted.
