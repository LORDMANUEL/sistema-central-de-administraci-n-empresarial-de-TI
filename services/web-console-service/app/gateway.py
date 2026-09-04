from __future__ import annotations

import httpx

from .errors import ConsoleError


class GatewayClient:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(
            base_url=settings.gateway_url,
            timeout=settings.request_timeout_seconds,
        )

    def close(self) -> None:
        self.client.close()

    def _json_response(self, response: httpx.Response, code: str):
        try:
            data = response.json()
        except Exception as exc:
            raise ConsoleError(502, code, "Gateway returned an invalid response") from exc
        if response.status_code >= 400:
            message = (
                data.get("error", {}).get("message", "Gateway request failed")
                if isinstance(data, dict)
                else "Gateway request failed"
            )
            upstream_code = data.get("error", {}).get("code") if isinstance(data, dict) else None
            raise ConsoleError(response.status_code, str(upstream_code or code), message)
        return data

    def bootstrap(self, email: str, display_name: str, password: str):
        try:
            response = self.client.post(
                "/api/v1/auth/bootstrap",
                json={"email": email, "display_name": display_name, "password": password},
            )
        except httpx.HTTPError as exc:
            raise ConsoleError(503, "console.gateway_unavailable", "Gateway is unavailable") from exc
        return self._json_response(response, "console.bootstrap_failed")

    def login(self, email: str, password: str):
        try:
            response = self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        except httpx.HTTPError as exc:
            raise ConsoleError(503, "console.gateway_unavailable", "Gateway is unavailable") from exc
        return self._json_response(response, "console.login_failed")

    def refresh(self, refresh_token: str):
        try:
            response = self.client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        except httpx.HTTPError as exc:
            raise ConsoleError(503, "console.gateway_unavailable", "Gateway is unavailable") from exc
        return self._json_response(response, "console.refresh_failed")

    def request(self, method: str, path: str, *, access_token: str | None = None, json=None, params=None):
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        try:
            return self.client.request(method, path, headers=headers, json=json, params=params)
        except httpx.HTTPError as exc:
            raise ConsoleError(503, "console.gateway_unavailable", "Gateway is unavailable") from exc
