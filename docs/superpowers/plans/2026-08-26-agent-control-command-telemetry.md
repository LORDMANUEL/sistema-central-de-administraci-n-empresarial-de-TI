# IT Guardian v0.6.0 Agent Control + Command + Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver three independently deployable services that let enrolled endpoints report heartbeat/capabilities, receive durable typed commands, submit idempotent results, and publish bounded telemetry through certificate-bound device identity.

**Architecture:** `agent-control-service`, `command-service`, and `telemetry-service` own separate PostgreSQL databases and publish domain events through transactional outboxes to NATS JetStream. Gateway exposes only administrative routes; device-facing routes consume a normalized trusted `DevicePrincipal` and never trust client-selected tenant/device identity.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Psycopg 3, Alembic, nats-py, Prometheus client, PostgreSQL, Docker/Compose, pytest 9.

**Spec:** `docs/superpowers/specs/2026-08-26-agent-control-command-telemetry-design.md`

## Global Constraints

- Base branch is `main` containing certified v0.5.0 Gateway + Audit.
- No shared mutable database between services.
- Device identity is server-derived from trusted endpoint authentication context.
- No arbitrary PowerShell/shell/script command in v0.6.0.
- Each service provides `/health/live`, `/health/ready`, `/metrics`, structured logs, request IDs, Alembic migrations, non-root Docker and CI.
- Administrative mutations remain protected by Gateway audit fail-closed behavior.
- Domain events use transactional outbox and `GUARDIAN_EVENTS`; command wake-up uses `device.command.available.<device_id>`.
- TDD RED -> GREEN -> REFACTOR is mandatory for behavior.

---

### Task 1: Agent Control heartbeat domain

**Files:**
- Create: `services/agent-control-service/pyproject.toml`
- Create: `services/agent-control-service/app/__init__.py`
- Create: `services/agent-control-service/app/principal.py`
- Create: `services/agent-control-service/app/models.py`
- Create: `services/agent-control-service/app/schemas.py`
- Create: `services/agent-control-service/app/heartbeat.py`
- Create: `services/agent-control-service/tests/conftest.py`
- Create: `services/agent-control-service/tests/test_heartbeat_domain.py`

**Interfaces:**
- Produces `DevicePrincipal`, `HeartbeatInput`, `HeartbeatOutcome`, `apply_heartbeat(session, principal, payload, now)`.

- [ ] **Step 1: Write RED heartbeat tests**

```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.heartbeat import DeviceBindingConflict, apply_heartbeat
from app.principal import DevicePrincipal
from app.schemas import HeartbeatInput


def make_payload() -> HeartbeatInput:
    return HeartbeatInput(
        session_id=uuid4(),
        agent_version="0.7.0-dev",
        platform="windows",
        platform_version="10.0.26100",
        capabilities=["inventory.basic"],
        capability_version=1,
        sent_at=datetime.now(UTC),
    )


def test_first_heartbeat_transitions_device_online(session):
    principal = DevicePrincipal(uuid4(), uuid4(), uuid4(), "01AB")
    outcome = apply_heartbeat(session, principal, make_payload(), datetime.now(UTC))
    assert outcome.online_transition is True
    assert outcome.capabilities_changed is True
    assert outcome.state == "online"


def test_repeated_heartbeat_does_not_repeat_online_transition(session):
    principal = DevicePrincipal(uuid4(), uuid4(), uuid4(), "01AB")
    now = datetime.now(UTC)
    apply_heartbeat(session, principal, make_payload(), now)
    second = apply_heartbeat(session, principal, make_payload(), now)
    assert second.online_transition is False
    assert second.state == "online"


def test_device_id_cannot_rebind_to_another_asset(session):
    tenant_id = uuid4()
    device_id = uuid4()
    first = DevicePrincipal(tenant_id, uuid4(), device_id, "01AB")
    second = DevicePrincipal(tenant_id, uuid4(), device_id, "01AB")
    apply_heartbeat(session, first, make_payload(), datetime.now(UTC))
    with pytest.raises(DeviceBindingConflict):
        apply_heartbeat(session, second, make_payload(), datetime.now(UTC))
```

- [ ] **Step 2: Run RED**

Run: `cd services/agent-control-service && python -m pytest -q tests/test_heartbeat_domain.py`
Expected: import failure because `app.heartbeat` does not exist.

- [ ] **Step 3: Implement minimal domain**

```python
@dataclass(frozen=True)
class DevicePrincipal:
    tenant_id: UUID
    guardian_asset_id: UUID
    device_id: UUID
    certificate_serial: str

@dataclass(frozen=True)
class HeartbeatOutcome:
    state: str
    online_transition: bool
    capabilities_changed: bool
```

Persist one current `DeviceSession` per `device_id`; normalize capabilities with sorted unique values; create a capability snapshot only when normalized capabilities change; reject tenant/asset rebinding before mutation.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest -q tests/test_heartbeat_domain.py`
Expected: all heartbeat domain tests pass.

- [ ] **Step 5: Commit**

`git commit -m "feat(agent-control): add heartbeat domain"`

---

### Task 2: Agent Control API, outbox, migration and observability

**Files:**
- Create: `services/agent-control-service/app/api.py`
- Create: `services/agent-control-service/app/main.py`
- Create: `services/agent-control-service/app/config.py`
- Create: `services/agent-control-service/app/database.py`
- Create: `services/agent-control-service/app/errors.py`
- Create: `services/agent-control-service/app/metrics.py`
- Create: `services/agent-control-service/app/outbox_worker.py`
- Create: `services/agent-control-service/alembic.ini`
- Create: `services/agent-control-service/migrations/env.py`
- Create: `services/agent-control-service/migrations/versions/20260826_0001_create_agent_control_domain.py`
- Create: `services/agent-control-service/tests/test_api.py`
- Create: `services/agent-control-service/tests/test_outbox.py`
- Create: `services/agent-control-service/tests/test_observability.py`

**Interfaces:**
- `POST /api/v1/device/heartbeat`
- Outbox subjects: `device.online`, `device.capabilities.changed`.

- [ ] **Step 1: Write RED API/outbox tests**

```python
def test_heartbeat_requires_trusted_device_identity(client, valid_heartbeat):
    response = client.post("/api/v1/device/heartbeat", json=valid_heartbeat)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_auth_required"


def test_first_heartbeat_writes_one_online_event(client, trusted_headers, valid_heartbeat, session):
    response = client.post("/api/v1/device/heartbeat", headers=trusted_headers, json=valid_heartbeat)
    assert response.status_code == 200
    assert session.execute(select(OutboxEvent).where(OutboxEvent.subject == "device.online")).scalars().all().__len__() == 1
```

- [ ] **Step 2: Run RED**
Run: `python -m pytest -q tests/test_api.py tests/test_outbox.py tests/test_observability.py`
Expected: missing API/main/outbox implementation.

- [ ] **Step 3: Implement API and transactional outbox**

`POST /api/v1/device/heartbeat` parses only trusted normalized device context, calls `apply_heartbeat`, writes outbox rows in the same transaction, commits once, and returns heartbeat/command polling intervals.

- [ ] **Step 4: Add migration and verify round-trip**

Run: `alembic upgrade head && alembic downgrade base && alembic upgrade head`
Expected: exit 0.

- [ ] **Step 5: Run GREEN**
Run: `python -m pytest -q`
Expected: zero failures.

- [ ] **Step 6: Commit**
`git commit -m "feat(agent-control): expose authenticated heartbeat api"`

---

### Task 3: Agent Control offline state, Docker, Compose and CI

**Files:**
- Create: `services/agent-control-service/app/offline.py`
- Create: `services/agent-control-service/tests/test_offline.py`
- Create: `services/agent-control-service/Dockerfile`
- Create: `services/agent-control-service/.dockerignore`
- Create: `.github/workflows/agent-control-ci.yml`
- Modify: `compose.yaml`

- [ ] **Step 1: Write RED offline transition test**

```python
def test_stale_device_emits_offline_once(session, online_device, now):
    changed = mark_stale_devices_offline(session, now - timedelta(seconds=180), now)
    assert changed == 1
    assert online_device.state == "offline"
    changed_again = mark_stale_devices_offline(session, now - timedelta(seconds=180), now)
    assert changed_again == 0
```

- [ ] **Step 2: Run RED**
Run: `python -m pytest -q tests/test_offline.py`
Expected: missing `mark_stale_devices_offline`.

- [ ] **Step 3: Implement offline sweeper**
Select only `state='online'` rows with stale `last_seen_at`, transition each once and write `device.offline` outbox in the same transaction.

- [ ] **Step 4: Verify GREEN + container**
Run: `python -m pytest -q && docker build -t guardian-agent-control:test .`
Expected: tests pass and container user is non-root.

- [ ] **Step 5: Validate Compose and CI**
Run: `docker compose config`
Expected: agent-control service and database resolve without interpolation errors.

- [ ] **Step 6: Commit**
`git commit -m "feat(agent-control): add offline transitions and deployment"`

---

### Task 4: Command type allowlist and idempotent creation

**Files:**
- Create: `services/command-service/pyproject.toml`
- Create: `services/command-service/app/__init__.py`
- Create: `services/command-service/app/command_types.py`
- Create: `services/command-service/app/models.py`
- Create: `services/command-service/app/schemas.py`
- Create: `services/command-service/app/service.py`
- Create: `services/command-service/tests/conftest.py`
- Create: `services/command-service/tests/test_command_types.py`
- Create: `services/command-service/tests/test_creation.py`

**Interfaces:**
- `normalize_command(command_type: str, arguments: dict) -> dict`
- `create_command(session, actor, request, now) -> Command`

- [ ] **Step 1: Write RED type tests**

```python
@pytest.mark.parametrize("command_type,args", [
    ("inventory.refresh", {}),
    ("device.reboot", {"delay_seconds": 30}),
    ("service.restart", {"service_name": "Spooler"}),
])
def test_allowed_command_types(command_type, args):
    assert normalize_command(command_type, args) == args


def test_arbitrary_powershell_is_rejected():
    with pytest.raises(CommandTypeNotAllowed):
        normalize_command("powershell", {"script": "Get-Process"})


def test_reboot_delay_over_limit_is_rejected():
    with pytest.raises(CommandArgumentsInvalid):
        normalize_command("device.reboot", {"delay_seconds": 3601})
```

- [ ] **Step 2: Run RED**
Run: `cd services/command-service && python -m pytest -q tests/test_command_types.py`
Expected: missing `app.command_types`.

- [ ] **Step 3: Implement exact allowlist**
Only `inventory.refresh`, `device.reboot`, and `service.restart` are accepted with the exact argument schemas from the spec.

- [ ] **Step 4: Write RED idempotency tests**

```python
def test_same_key_same_request_returns_same_command(session, actor, request, now):
    first = create_command(session, actor, request, now)
    second = create_command(session, actor, request, now)
    assert second.command_id == first.command_id


def test_same_key_different_request_conflicts(session, actor, request, now):
    create_command(session, actor, request, now)
    changed = request.model_copy(update={"arguments": {"delay_seconds": 60}})
    with pytest.raises(IdempotencyConflict):
        create_command(session, actor, changed, now)
```

- [ ] **Step 5: Run RED then implement idempotent creation**
Run: `python -m pytest -q tests/test_creation.py`
Expected before implementation: missing creation behavior. Persist a semantic request hash and enforce unique `(tenant_id, idempotency_key)`.

- [ ] **Step 6: Run GREEN**
Run: `python -m pytest -q tests/test_command_types.py tests/test_creation.py`
Expected: zero failures.

- [ ] **Step 7: Commit**
`git commit -m "feat(command): add typed idempotent command creation"`

---

### Task 5: Command acquisition and result state machine

**Files:**
- Create: `services/command-service/app/acquire.py`
- Create: `services/command-service/app/tokens.py`
- Create: `services/command-service/app/results.py`
- Create: `services/command-service/tests/test_acquire.py`
- Create: `services/command-service/tests/test_results.py`

- [ ] **Step 1: Write RED acquisition isolation test**

```python
def test_device_acquires_only_its_own_commands(session, device_a, device_b, command_a, command_b, now):
    acquired = acquire_commands(session, device_a, now, limit=10)
    assert [item.command_id for item in acquired] == [command_a.command_id]
    assert command_b.state == "queued"
```

- [ ] **Step 2: Implement atomic oldest-first acquisition**
Use row locking, lease expiry, maximum 10 commands and an opaque execution token whose hash only is persisted.

- [ ] **Step 3: Write RED result replay tests**

```python
def test_identical_terminal_result_replay_is_idempotent(session, running_command, token, principal, success_result, now):
    first = submit_result(session, principal, running_command.command_id, token, success_result, now)
    second = submit_result(session, principal, running_command.command_id, token, success_result, now)
    assert second.result_id == first.result_id


def test_conflicting_terminal_result_replay_is_rejected(session, running_command, token, principal, success_result, now):
    submit_result(session, principal, running_command.command_id, token, success_result, now)
    changed = success_result.model_copy(update={"summary": "different"})
    with pytest.raises(ResultConflict):
        submit_result(session, principal, running_command.command_id, token, changed, now)
```

- [ ] **Step 4: Implement monotonic state transitions and replay checks**
Persist result sequence and payload digest; terminal states cannot change.

- [ ] **Step 5: Run GREEN**
Run: `python -m pytest -q tests/test_acquire.py tests/test_results.py`
Expected: zero failures.

- [ ] **Step 6: Commit**
`git commit -m "feat(command): add durable acquisition and results"`

---

### Task 6: Command API, auth, outbox, migration, Docker and CI

**Files:**
- Create: `services/command-service/app/api.py`
- Create: `services/command-service/app/auth.py`
- Create: `services/command-service/app/main.py`
- Create: `services/command-service/app/config.py`
- Create: `services/command-service/app/database.py`
- Create: `services/command-service/app/errors.py`
- Create: `services/command-service/app/metrics.py`
- Create: `services/command-service/app/outbox_worker.py`
- Create: `services/command-service/alembic.ini`
- Create: `services/command-service/migrations/env.py`
- Create: `services/command-service/migrations/versions/20260826_0001_create_command_domain.py`
- Create: `services/command-service/Dockerfile`
- Create: `.github/workflows/command-ci.yml`
- Modify: `compose.yaml`

- [ ] **Step 1: RED tenant/auth API test**

```python
def test_org_admin_cannot_create_command_for_other_tenant(client, tenant_a_token, tenant_b_device):
    response = client.post("/api/v1/commands", headers={"Authorization": f"Bearer {tenant_a_token}"}, json=command_json(tenant_b_device))
    assert response.status_code in {403, 404}
```

- [ ] **Step 2: Implement admin and device routers**
Admin routes: create/get/list/cancel. Device routes: acquire/running/result.

- [ ] **Step 3: Implement transactional events**
Emit `command.created`, `command.dispatched`, `command.running`, `command.succeeded`, `command.failed`, `command.cancelled`, `command.expired` and command-available wake-up through the same DB transaction.

- [ ] **Step 4: Verify migration/Docker/Compose/tests**
Run: `python -m pytest -q && alembic upgrade head && alembic downgrade base && alembic upgrade head && docker compose config`
Expected: exit 0.

- [ ] **Step 5: Commit**
`git commit -m "feat(command): expose command service api"`

---

### Task 7: Telemetry metric schema and batch dedupe

**Files:**
- Create: `services/telemetry-service/pyproject.toml`
- Create: `services/telemetry-service/app/__init__.py`
- Create: `services/telemetry-service/app/metrics_schema.py`
- Create: `services/telemetry-service/app/models.py`
- Create: `services/telemetry-service/app/schemas.py`
- Create: `services/telemetry-service/app/ingest.py`
- Create: `services/telemetry-service/tests/conftest.py`
- Create: `services/telemetry-service/tests/test_metric_schema.py`
- Create: `services/telemetry-service/tests/test_ingest.py`

- [ ] **Step 1: Write RED schema tests**

```python
def test_cpu_percentage_above_100_is_rejected():
    with pytest.raises(MetricValueInvalid):
        validate_sample(sample("cpu.utilization_pct", 100.1))


def test_disk_metric_requires_volume_label():
    with pytest.raises(MetricLabelsInvalid):
        validate_sample(sample("disk.free_bytes", 1024, labels={}))
```

- [ ] **Step 2: Implement exact metric/label allowlist**
Use the spec ranges and label limits; no arbitrary metric names or tags.

- [ ] **Step 3: Write RED dedupe test**

```python
def test_duplicate_identical_batch_returns_original_ack(session, principal, batch, now):
    first = ingest_batch(session, principal, batch, now)
    second = ingest_batch(session, principal, batch, now)
    assert second.batch_record_id == first.batch_record_id
```

- [ ] **Step 4: Implement batch identity and conflict digest**
Unique key `(device_id, batch_id)`, semantic digest, samples stored once.

- [ ] **Step 5: Run GREEN**
Run: `python -m pytest -q tests/test_metric_schema.py tests/test_ingest.py`
Expected: zero failures.

- [ ] **Step 6: Commit**
`git commit -m "feat(telemetry): add bounded idempotent ingestion"`

---

### Task 8: Telemetry API, latest read, migration, Docker and CI

**Files:**
- Create: `services/telemetry-service/app/api.py`
- Create: `services/telemetry-service/app/auth.py`
- Create: `services/telemetry-service/app/main.py`
- Create: `services/telemetry-service/app/config.py`
- Create: `services/telemetry-service/app/database.py`
- Create: `services/telemetry-service/app/errors.py`
- Create: `services/telemetry-service/app/metrics.py`
- Create: `services/telemetry-service/app/outbox_worker.py`
- Create: `services/telemetry-service/alembic.ini`
- Create: `services/telemetry-service/migrations/env.py`
- Create: `services/telemetry-service/migrations/versions/20260826_0001_create_telemetry_domain.py`
- Create: `services/telemetry-service/Dockerfile`
- Create: `.github/workflows/telemetry-ci.yml`
- Modify: `compose.yaml`

- [ ] **Step 1: RED latest-read tenant isolation test**

```python
def test_latest_telemetry_is_tenant_scoped(client, tenant_a_token, device_b_id):
    response = client.get(f"/api/v1/telemetry/devices/{device_b_id}/latest", headers={"Authorization": f"Bearer {tenant_a_token}"})
    assert response.status_code in {403, 404}
```

- [ ] **Step 2: Implement device ingest and admin latest routers**
Device ingest requires `DevicePrincipal`; latest read uses platform-admin/org-admin tenant access.

- [ ] **Step 3: Implement `telemetry.batch.accepted` outbox event**
Event contains batch/device identifiers and accepted sample count only.

- [ ] **Step 4: Verify migration/Docker/Compose/tests**
Run: `python -m pytest -q && alembic upgrade head && alembic downgrade base && alembic upgrade head && docker compose config`
Expected: exit 0.

- [ ] **Step 5: Commit**
`git commit -m "feat(telemetry): expose telemetry service api"`

---

### Task 9: Gateway administrative route integration

**Files:**
- Modify: `services/gateway-service/app/routes.py`
- Modify: `services/gateway-service/app/config.py`
- Modify: `services/gateway-service/tests/test_routes.py`
- Modify: `compose.yaml`

- [ ] **Step 1: Write RED Gateway route tests**

```python
def test_command_admin_route_is_allowlisted():
    match = match_route("POST", "/api/v1/commands")
    assert match.upstream == "command"
    assert match.auth_mode == "bearer_admin"


def test_device_command_acquire_is_not_admin_gateway_route():
    assert match_route("POST", "/api/v1/device/commands/acquire") is None
```

- [ ] **Step 2: Implement static routes/upstreams**
Expose command admin and telemetry latest reads only; keep heartbeat/acquire/result/telemetry ingest outside bearer-admin Gateway matching.

- [ ] **Step 3: Run GREEN**
Run: `cd services/gateway-service && python -m pytest -q`
Expected: zero failures.

- [ ] **Step 4: Commit**
`git commit -m "feat(gateway): route v0.6 administrative APIs"`

---

### Task 10: Clean-stack v0.6 simulator certification

**Files:**
- Create: `tests/e2e/v06_device_simulator.py`
- Create: `tests/e2e/v06_agent_command_telemetry_smoke.py`
- Create: `.github/workflows/v06-core-ci.yml`

- [ ] **Step 1: Write RED E2E sequence**
The script must assert: enroll -> heartbeat -> online audit -> create inventory command -> acquire -> running -> success -> identical result replay -> telemetry batch -> duplicate batch -> latest read -> identity spoof rejection.

- [ ] **Step 2: Run on clean volumes and verify RED before all wiring exists**
Run: `docker compose down -v && docker compose up -d --build && python tests/e2e/v06_agent_command_telemetry_smoke.py`
Expected initially: a missing v0.6 route/service assertion.

- [ ] **Step 3: Complete Compose/wiring until GREEN**
Do not weaken assertions. Fix production integration only.

- [ ] **Step 4: Add NATS outage/recovery assertion**
Stop NATS after a safe domain DB transaction, assert pending outbox, restart NATS and assert logical event delivery.

- [ ] **Step 5: Inspect runtime security**
Assert non-root containers and absence of Root CA private key, Enrollment signing seed and Identity signing key in v0.6 service environments/mounts.

- [ ] **Step 6: Run GREEN twice from empty volumes**
Run full smoke twice with `docker compose down -v` between runs.
Expected: both runs exit 0.

- [ ] **Step 7: Commit**
`git commit -m "test(v0.6): certify endpoint operations core"`

---

### Task 11: Release metadata and same-SHA gate

**Files:**
- Modify: `ROADMAP.md`
- Modify: `MASTER.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`

- [ ] **Step 1: Update roadmap only after functional gates pass**
Mark `v0.5.0 Gateway + Audit` as `DONE / main — PR #7`; mark v0.6 as certified only after Agent Control, Command, Telemetry and Core E2E are green.

- [ ] **Step 2: Set release version**
Write exactly `0.6.0` to `VERSION` only on the certified candidate SHA.

- [ ] **Step 3: Same-SHA verification**
Require Identity, Tenant, Asset, Enrollment, PKI, Gateway, Audit, Agent Control, Command, Telemetry and v0.6 Core workflows all `success` on one head SHA.

- [ ] **Step 4: Merge safely**
Mark PR ready and merge using expected head SHA so no unverified commit can enter between certification and merge.
