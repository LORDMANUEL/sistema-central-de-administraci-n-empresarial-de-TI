from datetime import UTC, datetime, timedelta

import pytest

from app.auth import IdentityAccessVerifier, TenantAccessDecision, enforce_audit_read
from app.config import Settings
from app.errors import GuardianError


def settings():
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        identity_issuer="urn:it-guardian:identity",
        identity_audience="it-guardian-services",
    )


def test_real_identity_access_token_is_verified(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    token = make_identity_token(role="viewer", user_id="auditor-user")
    principal = IdentityAccessVerifier(settings(), jwks=jwks).verify(token)
    assert principal.user_id == "auditor-user"
    assert principal.role == "viewer"
    assert principal.bearer_token == token


def test_expired_identity_token_is_rejected(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    expired = make_identity_token(exp=int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()))
    with pytest.raises(GuardianError) as raised:
        IdentityAccessVerifier(settings(), jwks=jwks).verify(expired)
    assert raised.value.code == "audit.token_expired"


def test_platform_admin_has_global_audit_read_without_tenant_lookup(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    principal = IdentityAccessVerifier(settings(), jwks=jwks).verify(
        make_identity_token(role="platform_admin", user_id="platform-1")
    )

    def must_not_run(*_args):
        raise AssertionError("tenant resolver must not run for platform_admin")

    decision = enforce_audit_read(principal, None, must_not_run)
    assert decision.allowed is True
    assert decision.role == "platform_admin"


@pytest.mark.parametrize("tenant_role", ["org_admin", "security_admin", "auditor"])
def test_privileged_active_tenant_roles_can_read_audit(identity_crypto, make_identity_token, tenant_role):
    _, _, jwks = identity_crypto
    principal = IdentityAccessVerifier(settings(), jwks=jwks).verify(
        make_identity_token(role="viewer", user_id="tenant-user")
    )
    decision = enforce_audit_read(
        principal,
        "tenant-1",
        lambda tenant_id, user_id, token: TenantAccessDecision(
            allowed=True,
            role=tenant_role,
            tenant_status="active",
        ),
    )
    assert decision.role == tenant_role


@pytest.mark.parametrize("tenant_role", ["viewer", "helpdesk", "it_operator"])
def test_non_audit_tenant_roles_are_denied(identity_crypto, make_identity_token, tenant_role):
    _, _, jwks = identity_crypto
    principal = IdentityAccessVerifier(settings(), jwks=jwks).verify(make_identity_token(role="viewer"))
    with pytest.raises(GuardianError) as raised:
        enforce_audit_read(
            principal,
            "tenant-1",
            lambda tenant_id, user_id, token: TenantAccessDecision(
                allowed=True,
                role=tenant_role,
                tenant_status="active",
            ),
        )
    assert raised.value.code == "audit.role_not_allowed"


def test_nonmember_and_suspended_tenant_are_denied(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    principal = IdentityAccessVerifier(settings(), jwks=jwks).verify(make_identity_token(role="viewer"))

    with pytest.raises(GuardianError) as raised:
        enforce_audit_read(
            principal,
            "tenant-1",
            lambda *_args: TenantAccessDecision(False, None, "active"),
        )
    assert raised.value.code == "audit.access_denied"

    with pytest.raises(GuardianError) as raised:
        enforce_audit_read(
            principal,
            "tenant-1",
            lambda *_args: TenantAccessDecision(True, "auditor", "suspended"),
        )
    assert raised.value.code == "audit.tenant_suspended"


def test_non_platform_admin_cannot_request_global_audit(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    principal = IdentityAccessVerifier(settings(), jwks=jwks).verify(make_identity_token(role="viewer"))
    with pytest.raises(GuardianError) as raised:
        enforce_audit_read(principal, None, lambda *_args: None)
    assert raised.value.code == "audit.tenant_required"
