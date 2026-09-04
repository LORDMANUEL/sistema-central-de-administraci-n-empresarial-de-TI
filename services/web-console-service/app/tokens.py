from .errors import ConsoleError


def parse_token_pair(data: dict) -> tuple[str, str]:
    access = data.get("access_token") if isinstance(data, dict) else None
    refresh = data.get("refresh_token") if isinstance(data, dict) else None
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
        raise ConsoleError(502, "console.invalid_token_response", "Identity token response is invalid")
    return access, refresh
