# IT Guardian v0.6.0 — Agent Control + Command + Telemetry Design

## Status

Approved architecture for v0.6.0. Base release: `main` at v0.5.0 Gateway + Audit.

## Goal

Add the first server-side endpoint operations plane so an enrolled Guardian device can authenticate as a device, report liveness/capabilities, receive durable remote jobs, submit idempotent results, and publish bounded telemetry without sharing databases or trusting client-supplied tenant/device identity.

v0.6.0 deliberately stops before the real Windows Agent implementation. The release is certified with a deterministic device simulator using the same public contracts that v0.7.0 will consume.

## Non-negotiable boundaries

1. `agent-control-service` owns device connection state, heartbeat state, capability snapshots and online/offline transitions.
2. `command-service` owns administrative remote jobs, dispatch lifecycle, leases, retries, expiry, cancellation and results.
3. `telemetry-service` owns bounded metric ingestion, normalization, deduplication and retention metadata.
4. Each domain has its own PostgreSQL database and migrations. No service reads or writes another domain database.
5. Cross-domain communication uses HTTP contracts for synchronous validation and NATS JetStream for durable asynchronous delivery.
6. Gateway remains the northbound administrative HTTP edge. Device endpoints are a separate endpoint-authenticated surface and never accept administrative JWT identity as device identity.
7. Audit remains the canonical tamper-evident administrative record. v0.6 domain events are also consumed by Audit through `GUARDIAN_EVENTS`.
8. No arbitrary shell/PowerShell command type is exposed in v0.6.0. Command types are allowlisted and structurally validated.

## Identity model

### Canonical identifiers

Every device operation is bound to:

- `tenant_id`
- `guardian_asset_id`
- `device_id`
- active device certificate identity

The server derives device identity from trusted endpoint authentication context. `tenant_id`, `guardian_asset_id` and `device_id` supplied in JSON are treated only as consistency assertions and must match trusted identity when present.

### Device authentication contract

The production contract is mTLS-compatible and certificate-bound. In v0.6 clean-stack CI, the simulator sends certificate-derived trusted headers only through an internal test proxy/fixture that is not exposed by Gateway. Application code receives a normalized `DevicePrincipal` containing:

```text
DevicePrincipal(
  tenant_id: UUID,
  guardian_asset_id: UUID,
  device_id: UUID,
  certificate_serial: str,
)
```

Direct internet clients cannot set or override this normalized principal through `X-Guardian-*` headers.

## agent-control-service

### Responsibilities

- Accept authenticated heartbeat from enrolled devices.
- Maintain one current row per `device_id` with tenant/asset binding.
- Record agent version, platform, boot/session identifier, last seen timestamp and capability version.
- Persist immutable capability snapshots when the normalized capability set changes.
- Compute online/offline state from persisted last-seen state and configured timeout.
- Emit transition events only when state changes; repeated heartbeat while online does not emit repeated `device.online`.
- Reject device identity rebinding: one `device_id` cannot move to another tenant or asset.

### Heartbeat request

`POST /api/v1/device/heartbeat`

Fields:

```json
{
  "session_id": "uuid",
  "agent_version": "0.7.0-dev",
  "platform": "windows",
  "platform_version": "10.0.26100",
  "capabilities": ["inventory.basic", "command.reboot", "command.service.restart"],
  "capability_version": 1,
  "sent_at": "RFC3339 UTC"
}
```

Limits:

- body <= 64 KiB
- capabilities <= 128 entries
- capability string <= 96 characters
- clock skew accepted: -10 minutes to +2 minutes relative to server receive time
- agent version/platform strings <= 128 characters

### Heartbeat response

```json
{
  "device_id": "uuid",
  "server_time": "RFC3339 UTC",
  "state": "online",
  "heartbeat_interval_seconds": 60,
  "command_poll_interval_seconds": 10
}
```

### Device state

States: `online`, `offline`, `disabled`.

`disabled` is administrative and dominates heartbeat. A disabled device receives `403 device_disabled` and cannot revive itself through heartbeat.

### Events

- `device.online`
- `device.offline`
- `device.capabilities.changed`

All events contain only allowlisted identifiers, versions and timestamps. No certificates, bearer values or command payload bodies are copied into events.

## command-service

### Administrative command creation

`POST /api/v1/commands`

Administrative auth uses the existing Identity JWT + Tenant membership pattern. `platform_admin` can operate globally; `org_admin` is limited to active tenant membership.

Required fields:

```json
{
  "device_id": "uuid",
  "guardian_asset_id": "uuid",
  "command_type": "device.reboot",
  "arguments": {"delay_seconds": 30},
  "idempotency_key": "client-generated-string",
  "expires_in_seconds": 900
}
```

### v0.6 allowlisted command types

1. `device.reboot`
   - arguments: `delay_seconds` integer 0..3600
2. `service.restart`
   - arguments: `service_name` string matching `^[A-Za-z0-9_. -]{1,128}$`
3. `inventory.refresh`
   - arguments: empty object only

No arbitrary executable path, shell text, PowerShell text, URL or script body is accepted.

### Job lifecycle

States:

`queued -> dispatched -> running -> succeeded | failed`

Additional terminal states: `cancelled`, `expired`.

Invariants:

- state transitions are monotonic and validated server-side;
- one `(tenant_id, idempotency_key)` maps to one semantic command request;
- reuse of an idempotency key with a different semantic payload returns `409 idempotency_conflict`;
- expired/cancelled jobs cannot be acquired or completed;
- one result sequence number is accepted once per command;
- duplicate identical result submission returns the existing result without new domain events;
- conflicting replay for the same result sequence returns `409 result_conflict`.

### Device acquisition

`POST /api/v1/device/commands/acquire`

Device identity comes from `DevicePrincipal` and the device can acquire only its own commands. Acquisition uses a short lease. A command remains durable in PostgreSQL and its dispatch notification is delivered through JetStream.

The service may return multiple commands, maximum 10, ordered oldest first. Each dispatched command contains a server-generated `execution_token` bound to command, device and lease expiry. Only a hash of this token is persisted.

### Device acknowledgement/result endpoints

- `POST /api/v1/device/commands/{command_id}/running`
- `POST /api/v1/device/commands/{command_id}/result`

Result body:

```json
{
  "execution_token": "opaque",
  "result_sequence": 1,
  "status": "succeeded",
  "exit_code": 0,
  "summary": "reboot scheduled",
  "started_at": "RFC3339 UTC",
  "finished_at": "RFC3339 UTC"
}
```

Limits:

- summary <= 2048 characters
- no stdout/stderr arbitrary blob in v0.6
- exit code signed 32-bit integer
- result times must not be more than 2 minutes in the future

### Administrative endpoints

- `GET /api/v1/commands/{command_id}`
- `GET /api/v1/commands?device_id=&state=&limit=&after=` with keyset pagination
- `POST /api/v1/commands/{command_id}/cancel`

### Events

- `command.created`
- `command.dispatched`
- `command.running`
- `command.succeeded`
- `command.failed`
- `command.cancelled`
- `command.expired`

Administrative creation/cancellation is fail-closed through Gateway audit semantics already established in v0.5.

## telemetry-service

### Responsibilities

- Ingest authenticated device telemetry batches.
- Normalize a small v0.6 metric vocabulary.
- Enforce size/cardinality limits before persistence.
- Deduplicate by device + batch identifier.
- Persist retention class and received timestamp.
- Expose tenant-scoped administrative reads for latest metrics.

### Ingestion endpoint

`POST /api/v1/device/telemetry`

Request:

```json
{
  "batch_id": "uuid",
  "sent_at": "RFC3339 UTC",
  "samples": [
    {"metric": "cpu.utilization_pct", "value": 31.4, "observed_at": "RFC3339 UTC"},
    {"metric": "memory.used_bytes", "value": 2147483648, "observed_at": "RFC3339 UTC"}
  ]
}
```

### Metric allowlist

- `cpu.utilization_pct` float 0..100
- `memory.used_bytes` integer >=0
- `memory.total_bytes` integer >0
- `disk.free_bytes` integer >=0 with required bounded label `volume`
- `disk.total_bytes` integer >0 with required bounded label `volume`
- `network.rx_bytes_total` integer >=0
- `network.tx_bytes_total` integer >=0

Label policy:

- at most 4 labels/sample
- labels are metric-specific allowlists
- key <= 32 chars, value <= 128 chars
- no user-provided arbitrary tags are persisted

Batch limits:

- body <= 256 KiB
- <= 256 samples
- observed timestamp within -24 hours to +2 minutes
- duplicate `batch_id` returns original acknowledgement idempotently

### Administrative read

`GET /api/v1/telemetry/devices/{device_id}/latest`

Returns the latest normalized sample for each metric/label tuple visible to the caller tenant.

v0.6 does not implement charts, long-term rollups or a dedicated time-series database. PostgreSQL is sufficient for the release gate; later versions may add specialized storage behind the same service boundary.

## NATS / JetStream subjects

Existing stream: `GUARDIAN_EVENTS`.

Domain event subjects use:

- `device.online`
- `device.offline`
- `device.capabilities.changed`
- `command.created`
- `command.dispatched`
- `command.running`
- `command.succeeded`
- `command.failed`
- `command.cancelled`
- `command.expired`
- `telemetry.batch.accepted`

Command wake-up delivery uses a separate durable subject namespace:

- `device.command.available.<device_id>`

The database is the command source of truth. JetStream wake-up delivery is a notification, not the canonical command record; loss/redelivery cannot create duplicate commands.

## Database ownership

### guardian_agent_control

Tables:

- `device_sessions`
- `device_capability_snapshots`
- `outbox_events`

### guardian_command

Tables:

- `commands`
- `command_results`
- `outbox_events`

### guardian_telemetry

Tables:

- `telemetry_batches`
- `telemetry_samples`
- `outbox_events`

All IDs are UUIDs. Timestamps are timezone-aware UTC. Unique constraints enforce identity and idempotency invariants at PostgreSQL level, not only application code.

## Outbox and delivery

Every state-changing domain transaction that emits an event writes its outbox row in the same database transaction. Workers publish using `Nats-Msg-Id = event_id` and mark delivery only after JetStream acknowledgement. Redelivery is safe.

Command availability notifications follow the same outbox mechanism. Consumers always re-read authoritative command state before dispatch/execution.

## Gateway integration

Gateway adds only administrative routes for v0.6:

- `/api/v1/commands...`
- `/api/v1/telemetry/devices/...`
- administrative Agent Control reads when added

Device heartbeat/acquire/result/telemetry ingestion endpoints are not exposed as bearer-admin routes through normal Gateway route matching. They use the dedicated endpoint-authenticated listener/path established in Compose for the simulator and future reverse proxy/mTLS edge.

Gateway strips spoofable Guardian identity headers exactly as v0.5 requires.

## Error model

All three services use the existing normalized error envelope with `request_id` and stable error codes.

Important codes:

- `device_identity_mismatch` 403
- `device_disabled` 403
- `device_not_found` 404
- `command_not_found` 404
- `command_expired` 409
- `command_state_conflict` 409
- `idempotency_conflict` 409
- `execution_token_invalid` 403
- `result_conflict` 409
- `telemetry_batch_conflict` 409
- `telemetry_metric_not_allowed` 422
- `telemetry_limit_exceeded` 413/422 depending transport vs semantic limit

## Observability

Each service exposes:

- `/health/live`
- `/health/ready`
- `/metrics`
- structured secret-safe logs
- generated/propagated `request_id`

Minimum Prometheus metrics:

Agent Control:
- heartbeat requests by result
- online device gauge
- capability change counter

Command:
- commands created by type
- command state transition counter
- acquisition count
- expired count
- result replay/conflict count

Telemetry:
- batches accepted/rejected
- samples accepted
- dedupe count
- samples rejected by metric/limit class

No metric label may contain tenant names, device hostnames, command arguments or free-form user values.

## Security invariants

1. Device endpoints cannot select another tenant/device through body, query or headers.
2. Administrative JWT cannot impersonate a device.
3. Device certificate/private key material never enters any v0.6 database, logs or events.
4. Execution tokens are opaque, short-lived and persisted only as hashes.
5. Command allowlist prevents arbitrary shell/script execution in this release.
6. Cross-tenant reads and mutations return 404/403 according to existing service conventions without leaking existence.
7. Telemetry cardinality is bounded by schema.
8. Administrative mutations remain audit fail-closed at Gateway.
9. Workers run without Identity signing keys, Enrollment signer or CA private keys.
10. Containers run non-root.

## Failure and recovery

### NATS unavailable

Creation/heartbeat/result/telemetry persistence may proceed when its authoritative database transaction is safe; the outbox remains pending and workers publish later. Gateway administrative mutations still obey v0.5 pre-audit fail-closed behavior.

### Device disconnect during command

Lease expiry makes the command eligible for redispatch only when the command type is declared retry-safe. In v0.6:

- `inventory.refresh`: retry-safe
- `service.restart`: not automatically retried after `running`
- `device.reboot`: not automatically retried after `running`

Before `running`, an expired dispatch lease can return to `queued` for all types.

### Duplicate result

Identical sequence+payload returns existing result. Different payload for the same sequence is rejected and audited as a conflict event without mutating the terminal result.

### Service restart

State is reconstructed from PostgreSQL. No correctness depends on in-memory queues, online maps or timers.

## Clean-stack certification

A release candidate must pass from empty volumes:

1. Start Identity, Tenant, Asset, Enrollment, PKI, Gateway, Audit, NATS and all three v0.6 services.
2. Bootstrap/login `platform_admin` through Gateway.
3. Create tenant/site/asset through Gateway.
4. Enroll a device and obtain a valid certificate through the certified Enrollment/PKI path.
5. Device simulator authenticates using certificate-derived trusted identity.
6. Submit heartbeat and assert `device.online` reaches JetStream/Audit.
7. Create `inventory.refresh` command through Gateway.
8. Simulator acquires exactly that command, marks running and submits success.
9. Query command through Gateway and assert terminal `succeeded` state.
10. Submit duplicate identical result and assert idempotent response/no duplicate terminal event.
11. Submit telemetry batch and then duplicate same batch; assert one persisted batch and stable acknowledgement.
12. Query latest telemetry as admin through Gateway.
13. Stop NATS, persist one safe domain mutation with pending outbox, restart NATS and assert event eventually publishes once logically.
14. Attempt device identity spoofing/cross-device command result and assert rejection.
15. Query Audit and verify command/device/telemetry event metadata is secret-safe.
16. Inspect containers for non-root runtime and absence of CA/Enrollment/Identity private signing secrets.
17. Teardown containers and volumes.

## Definition of Done for v0.6.0

- Three independent services and databases exist.
- Alembic upgrade/downgrade/upgrade succeeds for each database.
- Unit and integration tests cover domain transitions, idempotency, expiry, tenant/device isolation and input limits.
- Docker images run non-root.
- Compose starts cleanly from empty volumes.
- Gateway administrative routes are allowlisted and endpoint routes cannot be reached as bearer-admin routes.
- Outbox/JetStream delivery is durable and replay-safe.
- The complete clean-stack certification above passes on one candidate SHA.
- Existing v0.1-v0.5 workflows remain green on the same PR head.
- `ROADMAP.md`, `MASTER.md`, `README.md`, `CHANGELOG.md` and `VERSION` reflect the certified release only when the gate is complete.

## Explicitly deferred

- Real Windows service/installer: v0.7.0.
- Arbitrary approved PowerShell/script execution: later Command hardening after the Windows agent sandbox/execution policy exists.
- Software deployment, patch rings and policy: v0.9.0.
- Tactical/Mesh remote support: v0.11.0.
- Wazuh/USB security: v0.12.0.
- Long-term telemetry rollups/dashboards: after Web Console needs are measured.
