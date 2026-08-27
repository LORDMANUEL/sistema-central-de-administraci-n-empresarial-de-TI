from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.outbox_worker import event_envelope


def test_telemetry_event_envelope_matches_audit_contract():
    event = SimpleNamespace(
        event_id=uuid4(),
        subject="guardian.telemetry.batch.accepted",
        aggregate_id=str(uuid4()),
        created_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        payload={"tenant_id": str(uuid4())},
    )

    envelope = event_envelope(event)

    assert envelope["schema_version"] == 1
    assert envelope["type"] == "telemetry.batch.accepted"
    assert envelope["aggregate_type"] == "telemetry_batch"
    assert envelope["aggregate_id"] == event.aggregate_id
    assert envelope["data"] == event.payload
