import re
from typing import Any


class CommandTypeNotAllowed(ValueError):
    pass


class CommandArgumentsInvalid(ValueError):
    pass


_SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_. -]{1,128}$")


def _require_exact_keys(arguments: dict[str, Any], expected: set[str]) -> None:
    if set(arguments) != expected:
        raise CommandArgumentsInvalid("command arguments do not match the required schema")


def normalize_command(command_type: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise CommandArgumentsInvalid("arguments must be an object")

    if command_type == "inventory.refresh":
        _require_exact_keys(arguments, set())
        return {}

    if command_type == "device.reboot":
        _require_exact_keys(arguments, {"delay_seconds"})
        delay = arguments["delay_seconds"]
        if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= 3600:
            raise CommandArgumentsInvalid("delay_seconds must be an integer between 0 and 3600")
        return {"delay_seconds": delay}

    if command_type == "service.restart":
        _require_exact_keys(arguments, {"service_name"})
        service_name = arguments["service_name"]
        if not isinstance(service_name, str) or _SERVICE_NAME_RE.fullmatch(service_name) is None:
            raise CommandArgumentsInvalid("service_name contains unsupported characters or length")
        return {"service_name": service_name}

    raise CommandTypeNotAllowed(f"unsupported command type: {command_type}")
