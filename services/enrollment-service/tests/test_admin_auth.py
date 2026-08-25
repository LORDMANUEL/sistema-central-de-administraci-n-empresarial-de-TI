import pytest

from app.auth import IdentityAccessVerifier, TenantAccessDecision, enforce_enrollment_admin
from app.config import Settings
from app.errors import GuardianError


def _settings():
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        identity_issuer="urn:it-guardian:identity",
        identity_audience="it-guardian-services",
    )


def test_real_identity_access_token_is_verified(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    token = make_identity_token(role="viewer", user_id="operator-7")

    principal = IdentityAccessVerifier(_settings(), jwks=jwks).verify(token)

    assert principal.user_id == "operator-7"
    assert principal.role == "viewer"
    assert principal.bearer_token == token


def test_platform_admin_has_global_enrollment_admin_without_tenant_lookup(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    principal = IdentityAccessVerifier(_settings(), jwks=jwks).verify(
        make_identity_token(role="platform_admin", user_id="platform-1")
    )

    def must_not_run(*_args):
        raise AssertionError("tenant resolver must not run for platform_admin")

    decision = enforce_enrollment_admin(principal, "tenant-1", must_not_run)
    assert decision.allowed is True
    assert decision.role == "platform_admin"
    assert decision.tenant_status == "active"


def test_org_admin_is_allowed_only_for_active_tenant(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    principal = IdentityAccessVerifier(_settings(), jwks=jwks).verify(
        make_identity_token(role="viewer", user_id="org-operator")
    )

    allowed = enforce_enrollment_admin(
        principal,
        "tenant-1",
        lambda tenant_id, user_id, token: TenantAccessDecision(
            allowed=True,
            role="org_admin",
            tenant_status="active",
        ),
    )
    assert allowed.role == "org_admin"

    with pytest.raises(GuardianError) as raised:
        enforce_enrollment_admin(
            principal,
            "tenant-1",
            lambda tenant_id, user_id, token: TenantAccessDecision(
                allowed=True,
                role="org_admin",
                tenant_status="suspended",
            ),
        )
    assert raised.value.code == "enrollment.tenant_suspended"


def test_viewer_and_nonmember_are_denied(identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    principal = IdentityAccessVerifier(_settings(), jwks=jwks).verify(
        make_identity_token(role="viewer", user_id="viewer-1")
    )

    with pytest.raises(GuardianError) as raised:
        enforce_enrollment_admin(
            principal,
            "tenant-1",
            lambda tenant_id, user_id, token: TenantAccessDecision(
                allowed=True,
                role="viewer",
                tenant_status="active",
            ),
        )
    assert raised.value.code == "enrollment.org_admin_required"

    with pytest.raises(GuardianError) as raised:
        enforce_enrollment_admin(
            principal,
            "tenant-1",
            lambda tenant_id, user_id, token: TenantAccessDecision(
                allowed=False,
                role=None,
                tenant_status="active",
            ),
        )
    assert raised.value.code == "enrollment.access_denied"
