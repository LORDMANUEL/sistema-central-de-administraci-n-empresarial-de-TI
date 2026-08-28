from secrets import compare_digest

from fastapi import Request

from .errors import ConsoleError
from .tokens import parse_token_pair


def current_session(request: Request):
    session_id = request.cookies.get(request.app.state.settings.session_cookie_name)
    item = request.app.state.sessions.get(session_id)
    if item is None:
        raise ConsoleError(401, "console.session_required", "Authentication required")
    return session_id, item


def require_csrf(request: Request):
    session_id, item = current_session(request)
    supplied = request.headers.get("X-Guardian-CSRF", "")
    if not supplied or not compare_digest(supplied, item.csrf_token):
        raise ConsoleError(403, "console.csrf_invalid", "CSRF token is missing or invalid")
    return session_id, item


def gateway_request(request: Request, method: str, path: str, *, json=None, params=None):
    session_id, item = current_session(request)
    response = request.app.state.gateway.request(method, path, access_token=item.access_token, json=json, params=params)
    if response.status_code == 401:
        try:
            access, refresh = parse_token_pair(request.app.state.gateway.refresh(item.refresh_token))
        except ConsoleError:
            request.app.state.sessions.delete(session_id)
            raise ConsoleError(401, "console.session_expired", "Session expired")
        request.app.state.sessions.replace_tokens(session_id, access, refresh)
        response = request.app.state.gateway.request(method, path, access_token=access, json=json, params=params)
    if response.status_code == 401:
        request.app.state.sessions.delete(session_id)
    return response
