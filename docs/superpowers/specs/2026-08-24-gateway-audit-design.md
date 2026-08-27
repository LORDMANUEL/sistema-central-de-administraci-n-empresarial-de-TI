# IT Guardian v0.5.0 — Gateway + Audit Design

## Status

- Base: `main` v0.4.0 stable.
- Branch: `feature/v0.5.0-gateway-audit`.
- Construction rule: finish one microservice completely before beginning the next.
- Order: **Audit Service first**, then **Gateway Service**.
- Out of scope for v0.5.0: Agent Control, Command, Telemetry and endpoint agents. Those remain v0.6+.

## Goal

Add a controlled northbound HTTP edge and a durable, tenant-aware, tamper-evident audit ledger without weakening the authentication/authorization already enforced by Identity, Tenant, Asset, Enrollment or PKI.

## Non-negotiable security boundaries

1. Gateway is not a universal trust oracle. Downstream microservices continue validating Identity JWTs and their own authorization rules.
2. Gateway never accepts caller-controlled identity context such as `X-Guardian-User`, `X-Guardian-Role` or `X-Guardian-Tenant` as authoritative.
3. Gateway uses an explicit route allowlist. There is no generic `/{path:path}` proxy to arbitrary hosts or service names.
4. Internal-only service routes are not exposed northbound.
5. Mutating requests are never automatically retried by Gateway.
6. Audit records are append-only by application contract and PostgreSQL protection.
7. Audit metadata is allowlisted. Bearer tokens, passwords, enrollment token values/hashes, CSR bodies, private keys, CA private material, signing seeds and full arbitrary request/response bodies are forbidden.
8. Domain services never write `guardian_audit` directly.
9. Audit Service never writes another service database.
10. All database, event and API operations carrying tenant-scoped data enforce tenant isolation.

## Service inventory for this release

### `audit-service`

Responsibilities:
- consume canonical `guardian.>` JetStream events;
- deduplicate by immutable `source_event_id`;
- persist a tenant-scoped append-only audit ledger;
- maintain tamper-evident hash chains;
- ingest Gateway edge audit events;
- expose read-only administrative search/detail/verification APIs;
- enforce Identity + Tenant authorization;
- expose health/readiness, Prometheus and structured secret-safe logs.

Own database: `guardian_audit`.

Port: `8006`.

### `gateway-service`

Responsibilities:
- become the controlled northbound HTTP entrypoint for current Core services;
- explicit route registry mapping public/admin/endpoint routes to fixed upstreams;
- sanitize spoofable and hop-by-hop headers;
- propagate/generate `X-Request-ID`;
- validate Identity JWTs at the edge for administrative routes while preserving downstream auth;
- enforce body/header limits, route timeouts and rate limiting;
- publish `gateway.request.accepted` / `gateway.request.completed` / `gateway.request.rejected` audit events;
- fail closed for high-value administrative mutations when required audit intent cannot be persisted to JetStream;
- never proxy internal-only routes.

Gateway is stateless in v0.5.0 except in-memory rate-limit state. A distributed rate-limit backend is deferred until multi-replica deployment requires it.

Port: `8080`.

## Audit canonical record

`audit_records` fields:

- `id`: UUID, primary key.
- `tenant_id`: nullable UUID. Null is reserved for genuinely platform-global records.
- `sequence`: monotonically increasing integer within one audit chain.
- `chain_key`: `tenant:<uuid>` or `platform`.
- `source_event_id`: unique string/UUID from JetStream event. For locally generated import records it remains globally unique.
- `source_type`: event type such as `asset.created`, `device.enrolled`, `gateway.request.accepted`.
- `source_service`: normalized source (`identity`, `tenant`, `asset`, `enrollment`, `pki`, `gateway`).
- `actor_user_id`: nullable UUID/string.
- `actor_type`: `user`, `device`, `service`, `system`, `unknown`.
- `action`: normalized action name.
- `resource_type`: normalized resource category.
- `resource_id`: nullable string.
- `outcome`: `success`, `failure`, `denied`, `accepted`, `unknown`.
- `request_id`: nullable string.
- `occurred_at`: source event timestamp.
- `ingested_at`: audit ingestion timestamp.
- `metadata`: JSON object after allowlist/sanitization.
- `prev_hash`: lowercase SHA-256 hex or 64 zeroes for genesis.
- `record_hash`: lowercase SHA-256 hex.

`audit_chain_heads` fields:
- `chain_key`: primary key.
- `tenant_id`: nullable UUID.
- `last_sequence`: integer.
- `last_hash`: SHA-256 hex.
- `updated_at`.

Uniqueness:
- `source_event_id` globally unique.
- `(chain_key, sequence)` unique.

## Hash-chain algorithm

Every record is hashed over canonical JSON with sorted keys and compact separators. The hashed structure contains all immutable record fields except `record_hash`, including `prev_hash` and `sequence`.

Algorithm:

1. begin DB transaction;
2. derive `chain_key` from tenant or `platform`;
3. lock `audit_chain_heads(chain_key)` with `SELECT ... FOR UPDATE`, creating a genesis head if absent;
4. `sequence = last_sequence + 1`;
5. `prev_hash = last_hash` or 64 zeroes;
6. canonicalize immutable audit payload;
7. `record_hash = sha256(canonical_json_utf8).hexdigest()`;
8. insert record;
9. update chain head to sequence/hash;
10. commit;
11. only after commit ACK the JetStream message.

A redelivery with the same `source_event_id` returns the existing record and is ACKed without appending another chain link.

## Append-only database protection

The Alembic PostgreSQL migration installs a trigger function that rejects `UPDATE` and `DELETE` on `audit_records` with an exception. Application code exposes no mutation endpoint for audit records.

This is tamper-evident, not equivalent to an external WORM store. A PostgreSQL superuser that rewrites coordinated rows and disables protections can defeat an in-database chain. External signed checkpoints/object-lock are a later hardening item and must not be falsely claimed in v0.5.0.

## Audit metadata sanitization

The ingestor never stores an arbitrary event payload wholesale.

Allowed common metadata keys:
- `hostname`, `platform`, `agent_version`;
- `site_id`, `department_id`;
- `certificate_id`, `certificate_serial_hex`;
- `provider`, `external_id` only when already present in canonical domain events;
- `route_id`, `method`, `status_code`, `client_ip`, `reason_code` for Gateway events;
- `role`, `membership_role` when explicitly emitted as non-secret authorization context.

Forbidden key fragments are rejected recursively, case-insensitively:
- `authorization`, `bearer`, `password`, `secret`, `private_key`, `privatekey`, `signing_key`, `seed`, `csr`, `token`, `token_hash`, `refresh_token`, `access_token`, `cookie`, `set-cookie`.

Unknown event fields are not automatically persisted in `metadata`.

## Audit event normalization

Input event envelope already used by Guardian services:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "type": "device.enrolled",
  "aggregate_type": "device",
  "aggregate_id": "uuid",
  "occurred_at": "ISO-8601",
  "data": {}
}
```

Normalization rules:
- `source_event_id = event_id`;
- `source_type = type`;
- `resource_type = aggregate_type`;
- `resource_id = aggregate_id`;
- tenant is extracted only from explicit allowlisted locations such as `data.tenant_id`;
- actor fields use explicit event data if present, otherwise `system/unknown`;
- action defaults to `type` unless a Gateway event supplies an explicit normalized action;
- outcome defaults to `success` for completed domain mutation events, otherwise `unknown`.

Events missing required envelope fields are not ACKed as successful ingestion; the consumer records a structured failure metric/log without dumping raw payload secrets.

## Audit API

All administrative routes validate Identity JWT via JWKS and preserve Tenant Service as source of tenant access.

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`
- `GET /api/v1/audit/records`
  - filters: `tenant_id`, `from`, `to`, `actor_user_id`, `source_type`, `action`, `resource_type`, `resource_id`, `outcome`, `request_id`;
  - keyset pagination: `after_sequence` when tenant/chain fixed; otherwise `(occurred_at,id)` cursor;
  - bounded `limit` default 100, max 500.
- `GET /api/v1/audit/records/{id}`
- `GET /api/v1/audit/verify?tenant_id=<uuid>`
  - recomputes the tenant chain in order;
  - returns `valid`, record count, last sequence/hash and first invalid record/sequence when corrupted.

Authorization:
- `platform_admin`: global read and verify;
- active `org_admin`: read/verify only their tenant;
- active `security_admin` and `auditor`: read/verify only their tenant;
- other tenant roles: denied in v0.5.0;
- suspended tenant or inactive/no membership: denied.

## Audit NATS consumer

- durable consumer name: `guardian-audit-v1`;
- subjects: `guardian.>`;
- manual ACK;
- ACK only after DB commit or after confirming duplicate `source_event_id` already exists;
- bounded pull batches;
- poison event failures remain unacked with retry/backoff; logs identify `event_id` only when safely parseable, never raw payload;
- metrics: received, inserted, duplicate, failed, verification failures.

## Gateway route model

Every route is a static `RoutePolicy`:

- `route_id` stable string;
- `method` exact HTTP verb;
- `path_template` exact FastAPI/Starlette template;
- `upstream_base_url` fixed configuration value, not client supplied;
- `upstream_path_template` fixed;
- `auth_mode`: `public`, `identity`, `enrollment_token`, `internal_only`;
- `mutation`: bool;
- `audit_intent_required`: bool;
- `max_body_bytes`;
- `timeout_seconds`;
- `rate_limit_bucket`.

Initial northbound allowlist includes the current useful Core APIs for Identity auth/user administration, Tenant, Asset, Enrollment administrative routes and endpoint enrollment. PKI direct issuance and inter-service JWKS/internal routes are not northbound.

## Header sanitization

Inbound headers removed before proxying:
- all `X-Guardian-*` except server-generated values;
- `Forwarded`, caller-supplied `X-Forwarded-*` unless deployment explicitly trusts a configured reverse proxy;
- hop-by-hop headers: `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade`;
- caller-supplied `Host` is replaced with the upstream host;
- request `Authorization` is forwarded only when the route policy requires the original bearer/token for the downstream service.

Gateway generates or validates a bounded `X-Request-ID` and forwards it.

## Authentication at Gateway

For `identity` routes Gateway validates:
- EdDSA signature from Identity JWKS;
- `iss` and `aud`;
- token type `access`;
- expiration;
- active token structure.

Gateway uses the verified actor only for rate limiting and audit metadata. It does not convert the JWT into trusted authorization headers that downstream services accept instead of their own validation.

## Gateway audit semantics

For high-value administrative mutation policies with `audit_intent_required=true`:

1. validate route/auth/limits;
2. publish `guardian.gateway.request.accepted` to JetStream and wait for ACK;
3. if ACK fails, return 503 and do not call upstream;
4. call upstream once;
5. publish `guardian.gateway.request.completed` containing only allowlisted metadata and response status;
6. if completed-event publish fails after upstream mutation, log/metric the audit delivery failure; no retry of the mutation is attempted.

Rejected requests that cross a configured security threshold publish `guardian.gateway.request.rejected` best-effort. The event does not contain credentials or request body.

## Gateway retries

- POST/PATCH/PUT/DELETE: zero automatic retries.
- GET/HEAD: at most one retry only on connection-establishment failure/clearly no upstream response; never after response bytes begin.
- Gateway never invents idempotency keys for downstream mutations.

## Body/header/time limits

Defaults:
- request header aggregate soft limit: 32 KiB;
- default JSON body max: 1 MiB;
- endpoint enrollment CSR route max: 256 KiB;
- default upstream timeout: 10 s;
- login/bootstrap: 10 s;
- enrollment: 30 s;
- health routes: 3 s.

Oversize returns 413 before upstream call. Invalid/oversized headers return 400/431 as applicable.

## Rate limiting

In-memory token-bucket interface in v0.5.0 with deterministic monotonic-clock behavior and injectable storage interface.

Buckets:
- `auth-login`: IP + normalized email hint when safely available without storing body; strict;
- `auth-bootstrap`: IP, very strict;
- `endpoint-enrollment`: IP + token hint hash prefix computed transiently, never logged/persisted;
- `admin-read`: actor user ID + tenant;
- `admin-write`: actor user ID + tenant, stricter.

429 includes a bounded `Retry-After`; no sensitive bucket key is returned.

## Gateway observability

Logs:
- request_id;
- route_id;
- method;
- normalized route template;
- status;
- duration;
- upstream service name;
- actor ID only after successful token verification;
- never Authorization/cookie/body.

Metrics:
- requests by route/status;
- auth rejects;
- route rejects;
- rate-limit rejects;
- upstream latency/status;
- audit-intent publish failures;
- completed-audit publish failures.

## Compose topology

v0.5 adds:
- `audit-db-init`;
- `audit-migrate`;
- `audit-service` on loopback `8006` for direct development/health;
- `audit-consumer` worker;
- `gateway-service` on `8080` as the intended northbound entrypoint.

Existing service ports remain loopback-bound for operational debugging in v0.5. Production hardening may later move them to an internal-only Docker network once Gateway maturity and operator break-glass procedures are proven.

## Clean-stack certification

Audit certification must pass before Gateway implementation begins:

1. start empty Compose volumes;
2. create Identity admin, tenant, site, department and asset;
3. create Enrollment token and enroll a device so existing services emit events;
4. Audit consumer ingests domain events;
5. duplicate redelivery does not append another record;
6. tenant chain verifies valid;
7. direct PostgreSQL UPDATE/DELETE of `audit_records` is rejected;
8. cross-tenant API access is denied;
9. secret marker scan finds no seeded password/token/CSR marker in audit metadata/log assertions;
10. teardown removes stack volumes.

Gateway final certification then repeats the functional Core path through port 8080 and verifies:

1. valid allowed routes proxy successfully;
2. internal/unregistered routes are blocked;
3. spoofed Guardian identity headers are stripped;
4. mutation executes once only;
5. required audit intent failure prevents mutation;
6. accepted/completed events arrive in Audit;
7. rate limit returns 429;
8. oversize body returns 413 before upstream call;
9. request_id correlates Gateway event and downstream response path;
10. full clean teardown.

## Definition of Done v0.5.0

- Audit Service complete, tested, migrated, Dockerized, documented and clean-stack certified.
- Gateway Service complete, tested, Dockerized, documented and clean-stack certified.
- Existing Identity/Tenant/Asset/Enrollment/PKI CIs remain green.
- `VERSION=0.5.0` only after all release gates pass on one candidate SHA.
- README, MASTER, ROADMAP and CHANGELOG accurately describe v0.5.0.
- No placeholder production routes, generic proxying or unaudited privileged mutation path is accepted as DONE.
