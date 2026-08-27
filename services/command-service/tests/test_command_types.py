import pytest

from app.command_types import CommandArgumentsInvalid, CommandTypeNotAllowed, normalize_command


@pytest.mark.parametrize(
    ("command_type", "arguments"),
    [
        ("inventory.refresh", {}),
        ("device.reboot", {"delay_seconds": 30}),
        ("service.restart", {"service_name": "Spooler"}),
    ],
)
def test_allowed_command_types_normalize(command_type, arguments):
    assert normalize_command(command_type, arguments) == arguments


def test_inventory_refresh_rejects_arguments():
    with pytest.raises(CommandArgumentsInvalid):
        normalize_command("inventory.refresh", {"scope": "all"})


def test_reboot_delay_outside_range_is_rejected():
    with pytest.raises(CommandArgumentsInvalid):
        normalize_command("device.reboot", {"delay_seconds": 3601})


def test_service_name_with_command_metacharacters_is_rejected():
    with pytest.raises(CommandArgumentsInvalid):
        normalize_command("service.restart", {"service_name": "Spooler; whoami"})


def test_arbitrary_powershell_is_not_supported():
    with pytest.raises(CommandTypeNotAllowed):
        normalize_command("powershell", {"script": "Get-Process"})
