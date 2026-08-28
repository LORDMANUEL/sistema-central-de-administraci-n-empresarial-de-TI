from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from ..authenticated import gateway_request
from ..errors import ConsoleError
from ..tokens import parse_token_pair

router = APIRouter(prefix="/console/api/session", tags=["session"])


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


def _user_from_response(response):
    if response.status_code >= 400:
        raise ConsoleError(response.status_code, "console.me_failed", "Unable to load current user")
    try:
        return response.json()
    except Exception as exc:
        raise ConsoleError(502, "console.invalid_user_response", "Current user response is invalid") from exc


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response):
    access, refresh = parse_token_pair(request.app.state.gateway.login(payload.email, payload.password))
    session_id = request.app.state.sessions.create(access, refresh)
    try:
        user = _user_from_response(
            request.app.state.gateway.request(
                "GET",
                "/api/v1/users/me",
                access_token=access,
            )
        )
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
    return {"user": _user_from_response(gateway_request(request, "GET", "/api/v1/users/me"))}


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
