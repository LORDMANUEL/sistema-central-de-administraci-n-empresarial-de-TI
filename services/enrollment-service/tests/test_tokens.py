from app.tokens import generate_enrollment_token, hash_token, request_fingerprint, token_hint


def test_generated_token_has_guardian_prefix_and_high_entropy_payload():
    first = generate_enrollment_token()
    second = generate_enrollment_token()

    assert first.plaintext.startswith("gdt_")
    assert len(first.plaintext.removeprefix("gdt_")) >= 43
    assert first.plaintext != second.plaintext
    assert first.token_hash == hash_token(first.plaintext)
    assert len(first.token_hash) == 64
    assert first.hint == token_hint(first.plaintext)
    assert first.plaintext not in first.hint
    assert first.token_hash not in first.hint


def test_hash_and_hint_are_stable_but_hint_is_non_secret():
    value = "gdt_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"

    assert hash_token(value) == hash_token(value)
    hint = token_hint(value)
    assert hint.startswith("gdt_")
    assert "..." in hint
    assert value not in hint
    assert len(hint) < len(value)


def test_request_fingerprint_is_canonical_for_normalized_endpoint_fields():
    a = request_fingerprint(
        tenant_id=" tenant-1 ",
        asset_id=" asset-1 ",
        csr_sha256="A" * 64,
        platform=" Windows ",
        hostname=" WS-SPS-001 ",
        agent_version=" 0.7.0-dev.1 ",
    )
    b = request_fingerprint(
        tenant_id="tenant-1",
        asset_id="asset-1",
        csr_sha256="a" * 64,
        platform="windows",
        hostname="ws-sps-001",
        agent_version="0.7.0-dev.1",
    )

    assert a == b
    assert len(a) == 64


def test_request_fingerprint_changes_when_bound_identity_changes():
    base = dict(
        tenant_id="tenant-1",
        asset_id="asset-1",
        csr_sha256="a" * 64,
        platform="windows",
        hostname="ws-sps-001",
        agent_version=None,
    )
    original = request_fingerprint(**base)

    for field, changed in (
        ("tenant_id", "tenant-2"),
        ("asset_id", "asset-2"),
        ("csr_sha256", "b" * 64),
        ("platform", "linux"),
        ("hostname", "ws-sps-002"),
        ("agent_version", "0.7.1"),
    ):
        candidate = dict(base)
        candidate[field] = changed
        assert request_fingerprint(**candidate) != original
