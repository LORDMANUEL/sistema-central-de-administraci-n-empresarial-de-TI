from app.session import SessionStore


def test_session_store_uses_opaque_token_and_never_returns_guardian_tokens():
    store = SessionStore(ttl_seconds=300, max_sessions=10)
    session_id = store.create("access-secret", "refresh-secret")
    assert session_id not in {"access-secret", "refresh-secret"}
    assert len(session_id) >= 32
    item = store.get(session_id)
    assert item is not None
    assert item.access_token == "access-secret"
    assert item.refresh_token == "refresh-secret"


def test_session_destroy_is_idempotent():
    store = SessionStore(ttl_seconds=300, max_sessions=10)
    session_id = store.create("a", "r")
    store.delete(session_id)
    store.delete(session_id)
    assert store.get(session_id) is None
