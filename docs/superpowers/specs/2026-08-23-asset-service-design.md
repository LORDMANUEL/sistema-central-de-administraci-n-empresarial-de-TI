# Asset Service Design — v0.3.0

## Scope

Asset Service owns the canonical identity and metadata of every managed asset in IT Guardian. It does not own tenant membership, authentication credentials, enrollment certificates, telemetry, commands, tickets or external-engine state.

## Domain boundary

Owned data:
- `guardian_asset_id`;
- tenant/site/department references;
- type, name, hostname, serial and lifecycle status;
- external identity mappings;
- domain outbox.

External references are opaque IDs. Asset Service never writes Identity or Tenant databases.

## API boundary

Initial administrative API:
- `POST /api/v1/assets`;
- `GET /api/v1/assets?tenant_id=...`;
- `GET /api/v1/assets/{guardian_asset_id}`;
- `POST /api/v1/assets/{guardian_asset_id}/external-identities`.

The initial dev slice is restricted to `platform_admin`. Tenant-scoped operator authorization is an explicit pre-release gate because Tenant currently owns membership truth and no shared DB read is permitted.

## Security

Identity remains the sole private JWT signer. Asset validates Ed25519 access tokens from Identity JWKS and checks issuer/audience/type. Backend ports remain loopback-bound until Gateway Service exists.

## Reliability

Every externally meaningful change writes an outbox event in the same SQL transaction. A separate worker publishes to NATS JetStream using `event_id` as `Nats-Msg-Id`; `published_at` is set only after publish ACK.

## Data flow

`Admin -> Asset API -> guardian_asset DB -> outbox -> worker -> NATS JetStream`

Identity authorization is read-only through JWKS. Tenant/site/department IDs are stored as references only.

## Tests and release gate

The service is not DONE until unit/integration tests, migration round-trip, Docker build, Compose validation and the cross-service flow `Identity -> Tenant -> Asset -> NATS` are green. No later Core MVP service may bypass this gate.
