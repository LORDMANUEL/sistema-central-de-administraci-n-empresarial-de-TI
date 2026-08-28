from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from ..authenticated import current_session, gateway_request, require_csrf
from ..errors import ConsoleError
from ..tokens import parse_token_pair

router = APIRouter(prefix="/console/api/session", tags=["session"])


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class BootstrapInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)


def _user_from_response(response):
    if response.status_code >= 400:
        raise ConsoleError(response.status_code, "console.me_failed", "Unable to load current user")
    try:
        return response.json()
    except Exception as exc:
        raise ConsoleError(502, "console.invalid_user_response", "Current user response is invalid") from exc


def _establish_session(email: str, password: str, request: Request, response: Response):
    access, refresh = parse_token_pair(request.app.state.gateway.login(email, password))
    session_id = request.app.state.sessions.create(access, refresh)
    try:
        user = _user_from_response(request.app.state.gateway.request("GET", "/api/v1/users/me", access_token=access))
        item = request.app.state.sessions.get(session_id)
        if item is None:
            raise ConsoleError(503, "console.session_store_unavailable", "Session could not be established")
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
    return {"user": user, "csrf_token": item.csrf_token}


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
def bootstrap(payload: BootstrapInput, request: Request, response: Response):
    request.app.state.gateway.bootstrap(payload.email, payload.display_name, payload.password)
    return _establish_session(payload.email, payload.password, request, response)


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response):
    return _establish_session(payload.email, payload.password, request, response)


@router.get("/me")
def me(request: Request):
    _, item = current_session(request)
    return {"user": _user_from_response(gateway_request(request, "GET", "/api/v1/users/me")), "csrf_token": item.csrf_token}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    session_id, _ = require_csrf(request)
    request.app.state.sessions.delete(session_id)
    response.delete_cookie(
        request.app.state.settings.session_cookie_name,
        path="/console",
        secure=request.app.state.settings.cookie_secure,
        samesite="strict",
    )
    return None
