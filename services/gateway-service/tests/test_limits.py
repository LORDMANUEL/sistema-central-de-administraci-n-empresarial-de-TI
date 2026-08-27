from __future__ import annotations

import pytest

from app.errors import GatewayError
from app.limits import enforce_body_limit, enforce_header_limit


def test_body_limit_allows_boundary_and_rejects_one_byte_over():
    enforce_body_limit(b"x" * 10, 10)

    with pytest.raises(GatewayError) as raised:
        enforce_body_limit(b"x" * 11, 10)

    assert raised.value.status_code == 413
    assert raised.value.code == "gateway.body_too_large"


def test_header_limit_is_computed_from_names_and_values():
    headers = {"X-Test": "1234", "Accept": "json"}
    # len('X-Test') + len('1234') + len('Accept') + len('json') = 20
    enforce_header_limit(headers, 20)

    with pytest.raises(GatewayError) as raised:
        enforce_header_limit(headers, 19)

    assert raised.value.status_code == 431
    assert raised.value.code == "gateway.headers_too_large"
