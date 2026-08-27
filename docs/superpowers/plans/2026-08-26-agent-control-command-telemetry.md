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
- Each service must provide `/health/live`, `/health/ready`, `/metrics`, structured logs, request IDs, Alembic migrations, non-root Docker and CI.
- Administrative mutations remain protected by Gateway audit fail-closed behavior.
- Domain events use transactional outbox and `GUARDIAN_EVENTS`; command wake-up uses `device.command.available.<device_id>`.
- TDD RED -> GREEN -> REFACTOR for behavior changes.

---

### Task 1: Agent Control domain and heartbeat

**Files:**
- Create: `services/agent-control-service/pyproject.toml`
- Create: `services/agent-control-service/app/__init__.py`
- Create: `services/agent-control-service/app/principal.py`
- Create: `services/agent-control-service/app/models.py`
- Create: `services/agent-control-service/app/heartbeat.py`
- Create: `services/agent-control-service/app/schemas.py`
- Create: `services/agent-control-service/tests/test_heartbeat_domain.py`

**Interfaces:**
- Produces: `DevicePrincipal`, `HeartbeatInput`, `HeartbeatOutcome`, `apply_heartbeat(session, principal, payload, now)`.
- `apply_heartbeat` returns whether an online transition and capability change occurred so later API/outbox code can emit exactly-once logical events.

- [ ] **Step 1: Write failing heartbeat tests**

```python
from datetime import UTC, datetime
from uuid import uuid4

from app.heartbeat import apply_heartbeat
from app.principal import DevicePrincipal
from app.schemas import HeartbeatInput


def test_first_heartbeat_transitions_device_online(session):
    principal = DevicePrincipal(uuid4(), uuid4(), uuid4(), "01AB")
    payload = HeartbeatInput(
        session_id=uuid4(), agent_version="0.7.0-dev", platform="windows",
        platform_version="10.0.26100", capabilities=["inventory.basic"],
        capability_version=1, sent_at=datetime.now(UTC),
    )
    outcome = apply_heartbeat(session, principal, payload, datetime.now(UTC))
    assert outcome.online_transition is True
    assert outcome.state == "online"


def test_repeated_heartbeat_does_not_repeat_online_transition(session):
    # same principal, second heartbeat
    ...


def test_device_id_cannot_rebind_to_another_asset(session):
    # create first binding then same device_id/different asset
    ...
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/agent-control-service && python -m pytest -q tests/test_heartbeat_domain.py`
Expected: import/module failure because production heartbeat domain does not exist.

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

Persist one `DeviceSession` per device and immutable capability snapshots. Reject binding changes before mutation.

- [ ] **Step 4: Run heartbeat tests GREEN**

Run: `python -m pytest -q tests/test_heartbeat_domain.py`
Expected: all heartbeat tests pass.

- [ ] **Step 5: Commit**

`git commit -m "feat(agent-control): add heartbeat domain"`

---

### Task 2: Agent Control API, outbox, observability and migration

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
- outbox subjects `device.online`, `device.capabilities.changed`, later offline sweeper uses `device.offline`.

- [ ] **Step 1: Write failing API/outbox tests**

```python
def test_heartbeat_rejects_missing_trusted_device_principal(client):
    response = client.post("/api/v1/device/heartbeat", json=VALID_HEARTBEAT)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_auth_required"


def test_first_heartbeat_writes_device_online_outbox(client, trusted_device_headers, session):
    response = client.post("/api/v1/device/heartbeat", headers=trusted_device_headers, json=VALID_HEARTBEAT)
    assert response.status_code == 200
    assert count_outbox(session, "device.online") == 1
```

- [ ] **Step 2: Verify RED**
Run: `python -m pytest -q tests/test_api.py tests/test_outbox.py tests/test_observability.py`

- [ ] **Step 3: Implement API + transactional outbox + health/metrics**

Heartbeat and outbox write must share one SQLAlchemy transaction. Worker publishes with `Nats-Msg-Id=event_id` and records acknowledgement.

- [ ] **Step 4: Verify GREEN + migration round-trip**

Run:
`python -m pytest -q`
`alembic upgrade head && alembic downgrade base && alembic upgrade head`

- [ ] **Step 5: Commit**
`git commit -m "feat(agent-control): expose authenticated heartbeat api"`

---

### Task 3: Agent Control Docker/Compose/CI and offline transition

**Files:**
- Create: `services/agent-control-service/Dockerfile`
- Create: `services/agent-control-service/.dockerignore`
- Create: `.github/workflows/agent-control-ci.yml`
- Modify: `compose.yaml`
- Create: `services/agent-control-service/app/offline.py`
- Create: `services/agent-control-service/tests/test_offline.py`

**Interfaces:**
- `mark_stale_devices_offline(session, cutoff, now)` emits only state changes.

- [ ] **Step 1: Write failing offline transition test**

```python
def test_stale_online_device_transitions_offline_once(session):
    mark_stale_devices_offline(session, cutoff, now)
    assert device.state == "offline"
    assert count_outbox(session, "device.offline") == 1
    mark_stale_devices_offline(session, cutoff, now)
    assert count_outbox(session, "device.offline") == 1
```

- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement offline sweeper**
- [ ] **Step 4: Build non-root Docker and validate Compose**
- [ ] **Step 5: Run Agent Control CI GREEN**
- [ ] **Step 6: Commit**

---

### Task 4: Command typed request validation and idempotent creation

**Files:**
- Create: `services/command-service/pyproject.toml`
- Create: `services/command-service/app/__init__.py`
- Create: `services/command-service/app/command_types.py`
- Create: `services/command-service/app/models.py`
- Create: `services/command-service/app/service.py`
- Create: `services/command-service/app/schemas.py`
- Create: `services/command-service/tests/test_command_types.py`
- Create: `services/command-service/tests/test_creation.py`

**Interfaces:**
- `normalize_command(command_type: str, arguments: dict) -> dict`
- `create_command(session, principal, request, now) -> Command`

- [ ] **Step 1: Write failing allowlist tests**

```python
@pytest.mark.parametrize("command_type,args", [
    ("inventory.refresh", {}),
    ("device.reboot", {"delay_seconds": 30}),
    ("service.restart", {"service_name": "Spooler"}),
])
def test_allowed_command_types_normalize(command_type, args):
    assert normalize_command(command_type, args) == args


def test_shell_command_is_not_supported():
    with pytest.raises(CommandTypeNotAllowed):
        normalize_command("powershell", {"script": "Get-Process"})
```

- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement exact schemas/ranges only**
- [ ] **Step 4: Add idempotency tests**

```python
def test_same_idempotency_key_same_payload_returns_same_command(session): ...
def test_same_idempotency_key_different_payload_conflicts(session): ...
```

- [ ] **Step 5: Verify GREEN**
- [ ] **Step 6: Commit**

---

### Task 5: Command acquisition, execution token and result state machine

**Files:**
- Create: `services/command-service/app/acquire.py`
- Create: `services/command-service/app/results.py`
- Create: `services/command-service/app/tokens.py`
- Create: `services/command-service/tests/test_acquire.py`
- Create: `services/command-service/tests/test_results.py`

**Interfaces:**
- `acquire_commands(session, device_principal, now, limit=10)`
- `mark_running(session, device_principal, command_id, execution_token, now)`
- `submit_result(session, device_principal, command_id, payload, now)`

- [ ] **Step 1: RED tests for cross-device acquisition and lease**
- [ ] **Step 2: Implement atomic acquisition**
- [ ] **Step 3: RED tests for running/terminal transitions**
- [ ] **Step 4: Implement execution-token hash validation**
- [ ] **Step 5: RED tests for identical replay vs conflicting replay**
- [ ] **Step 6: Implement result sequence idempotency**
- [ ] **Step 7: Verify all command domain tests GREEN**
- [ ] **Step 8: Commit**

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

**Interfaces:**
- Admin: create/get/list/cancel commands.
- Device: acquire/running/result.

- [ ] **Step 1: RED API authorization and tenant-isolation tests**
- [ ] **Step 2: Implement admin/device routers**
- [ ] **Step 3: RED outbox tests for each state transition**
- [ ] **Step 4: Implement transactional events + command availability notification**
- [ ] **Step 5: Migration round-trip + Docker non-root + Compose**
- [ ] **Step 6: Command CI GREEN**
- [ ] **Step 7: Commit**

---

### Task 7: Telemetry schema, dedupe and latest read

**Files:**
- Create: `services/telemetry-service/pyproject.toml`
- Create: `services/telemetry-service/app/__init__.py`
- Create: `services/telemetry-service/app/metrics_schema.py`
- Create: `services/telemetry-service/app/models.py`
- Create: `services/telemetry-service/app/ingest.py`
- Create: `services/telemetry-service/app/schemas.py`
- Create: `services/telemetry-service/tests/test_metric_schema.py`
- Create: `services/telemetry-service/tests/test_ingest.py`

**Interfaces:**
- `validate_sample(sample) -> NormalizedSample`
- `ingest_batch(session, principal, batch, now) -> BatchAck`

- [ ] **Step 1: RED allowlist/range/label tests**
- [ ] **Step 2: Implement bounded metric schema**
- [ ] **Step 3: RED batch dedupe/conflict tests**
- [ ] **Step 4: Implement batch+sample persistence**
- [ ] **Step 5: RED latest-per-metric tests**
- [ ] **Step 6: Implement tenant/device scoped latest read**
- [ ] **Step 7: GREEN full telemetry domain suite**
- [ ] **Step 8: Commit**

---

### Task 8: Telemetry API, outbox, migration, Docker and CI

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

- [ ] **Step 1: RED authentication/body-limit/API tests**
- [ ] **Step 2: Implement ingestion/read routers**
- [ ] **Step 3: Implement `telemetry.batch.accepted` outbox event**
- [ ] **Step 4: Migration round-trip + Docker non-root + Compose**
- [ ] **Step 5: Telemetry CI GREEN**
- [ ] **Step 6: Commit**

---

### Task 9: Gateway route integration

**Files:**
- Modify: `services/gateway-service/app/routes.py`
- Modify: `services/gateway-service/app/config.py`
- Modify: `services/gateway-service/tests/test_routes.py`
- Modify: `compose.yaml`

**Interfaces:**
- Gateway exposes administrative command routes and telemetry reads only.
- Device heartbeat/acquire/result/telemetry ingest are not bearer-admin routes.

- [ ] **Step 1: RED tests proving admin routes exist and device routes remain unreachable**
- [ ] **Step 2: Add static upstream/route allowlist**
- [ ] **Step 3: Verify Gateway suite GREEN**
- [ ] **Step 4: Commit**

---

### Task 10: v0.6 clean-stack device simulator certification

**Files:**
- Create: `tests/e2e/v06_device_simulator.py`
- Create: `tests/e2e/v06_agent_command_telemetry_smoke.py`
- Create: `.github/workflows/v06-core-ci.yml`

**Interfaces:**
- Simulator uses the same heartbeat/acquire/running/result/telemetry contracts intended for v0.7 Windows Agent.

- [ ] **Step 1: Write E2E that fails before the complete integration exists**
- [ ] **Step 2: Start clean stack from empty volumes**
- [ ] **Step 3: Enroll simulator device through Gateway/Enrollment/PKI**
- [ ] **Step 4: Heartbeat -> `device.online` -> Audit**
- [ ] **Step 5: Create `inventory.refresh` through Gateway -> acquire -> running -> success**
- [ ] **Step 6: Replay identical result and assert logical exactly-once terminal event**
- [ ] **Step 7: Telemetry batch + duplicate -> one persisted batch -> latest read**
- [ ] **Step 8: NATS outage/recovery test for pending outbox**
- [ ] **Step 9: Cross-device spoof/result rejection**
- [ ] **Step 10: Inspect secret isolation and non-root containers**
- [ ] **Step 11: Teardown volumes**
- [ ] **Step 12: v0.6 core CI GREEN**
- [ ] **Step 13: Commit**

---

### Task 11: Release metadata and same-SHA certification

**Files:**
- Modify: `ROADMAP.md`
- Modify: `MASTER.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`

- [ ] **Step 1: Mark v0.5.0 DONE/main PR #7 and v0.6 active/certified only after all gates are green**
- [ ] **Step 2: Set `VERSION` to `0.6.0` only on certified candidate**
- [ ] **Step 3: Verify all existing v0.1-v0.5 workflows plus Agent Control, Command, Telemetry and v0.6 Core succeed on the same head SHA**
- [ ] **Step 4: Mark PR ready and merge with expected head SHA**
