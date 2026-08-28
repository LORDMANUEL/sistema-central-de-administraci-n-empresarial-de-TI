from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from ..errors import ConsoleError

router = APIRouter(prefix="/console/api/session", tags=["session"])


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


def _token_pair(data: dict) -> tuple[str, str]:
    access = data.get("access_token") if isinstance(data, dict) else None
    refresh = data.get("refresh_token") if isinstance(data, dict) else None
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
        raise ConsoleError(502, "console.invalid_token_response", "Identity token response is invalid")
    return access, refresh


def _session(request: Request):
    session_id = request.cookies.get(request.app.state.settings.session_cookie_name)
    item = request.app.state.sessions.get(session_id)
    if item is None:
        raise ConsoleError(401, "console.session_required", "Authentication required")
    return session_id, item


def _me_with_refresh(request: Request, session_id, item):
    response = request.app.state.gateway.request(
        "GET",
        "/api/v1/users/me",
        access_token=item.access_token,
    )
    if response.status_code == 401:
        try:
            access, refresh = _token_pair(request.app.state.gateway.refresh(item.refresh_token))
        except ConsoleError:
            request.app.state.sessions.delete(session_id)
            raise ConsoleError(401, "console.session_expired", "Session expired")
        request.app.state.sessions.replace_tokens(session_id, access, refresh)
        response = request.app.state.gateway.request(
            "GET",
            "/api/v1/users/me",
            access_token=access,
        )
    if response.status_code >= 400:
        if response.status_code == 401:
            request.app.state.sessions.delete(session_id)
        raise ConsoleError(response.status_code, "console.me_failed", "Unable to load current user")
    try:
        return response.json()
    except Exception as exc:
        raise ConsoleError(502, "console.invalid_user_response", "Current user response is invalid") from exc


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response):
    access, refresh = _token_pair(request.app.state.gateway.login(payload.email, payload.password))
    session_id = request.app.state.sessions.create(access, refresh)
    try:
        user = _me_with_refresh(request, session_id, request.app.state.sessions.get(session_id))
    except Exception:
        request.app.state.sessions.delete(session_id)
        raise
    response.set_cookie(
        key=request.app.state.settings.session_cookie_name,
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=request.app.state.settings.cookie_secure,
        path="/console",
        max_age=request.app.state.settings.session_ttl_seconds,
    )
    return {"user": user}


@router.get("/me")
def me(request: Request):
    session_id, item = _session(request)
    return {"user": _me_with_refresh(request, session_id, item)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    session_id = request.cookies.get(request.app.state.settings.session_cookie_name)
    request.app.state.sessions.delete(session_id)
    response.delete_cookie(
        request.app.state.settings.session_cookie_name,
        path="/console",
        secure=request.app.state.settings.cookie_secure,
        samesite="strict",
    )
    return None
