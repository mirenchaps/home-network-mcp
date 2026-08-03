"""
tests/test_server.py

Unit tests for server.py tool dispatch.

Each test calls the tool function directly (bypassing the MCP transport layer)
and mocks the underlying runner/winrm_collect helpers. This verifies that:
  - the right helper is called with the right arguments
  - the tool returns whatever the helper returns unchanged
  - async helpers (SSH) and sync helpers (pywinrm, run via executor) both work

Run with: pytest tests/ -v
Docs: https://docs.pytest.org  /  https://pytest-asyncio.readthedocs.io
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server


# ---------------------------------------------------------------------------
# scan_network — runs PowerShell via runner.run_pwsh_script
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_network_calls_pwsh():
    """scan_network should delegate to run_pwsh_script with the right params."""
    expected = {"subnet": "192.168.0", "devices_up": [], "device_count": 0}

    with patch("server.run_pwsh_script", new_callable=AsyncMock, return_value=expected) as mock_run:
        result = await server.scan_network(subnet="192.168.0", start_host=1, end_host=10)

    mock_run.assert_called_once_with(
        "Get-DeviceStatus.ps1", Subnet="192.168.0", StartHost=1, EndHost=10
    )
    assert result == expected


# ---------------------------------------------------------------------------
# check_service_health — now calls pywinrm via run_in_executor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_service_health_calls_winrm():
    """check_service_health should call get_service_health via run_in_executor."""
    expected = {"services": [{"name": "WinRM", "status": "Running"}]}

    with patch("server.get_service_health", MagicMock(return_value=expected)) as mock_svc:
        result = await server.check_service_health(
            service_names=["WinRM"], computer_name="192.168.0.124"
        )

    mock_svc.assert_called_once_with("192.168.0.124", ["WinRM"])
    assert result == expected


# ---------------------------------------------------------------------------
# check_disk_usage — calls pywinrm + applies warn_threshold in Python
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_disk_usage_applies_warning_threshold():
    """check_disk_usage should flag volumes below the threshold as warning=True."""
    winrm_response = {"volumes": [{"drive": "C:", "percent_free": 10}]}

    with patch("server.get_disk_usage", MagicMock(return_value=winrm_response)):
        result = await server.check_disk_usage(
            computer_name="192.168.0.124", warn_threshold_percent=15
        )

    assert result["volumes"][0]["warning"] is True


@pytest.mark.asyncio
async def test_check_disk_usage_no_warning_when_above_threshold():
    """Volumes above the threshold should be flagged warning=False."""
    winrm_response = {"volumes": [{"drive": "C:", "percent_free": 50}]}

    with patch("server.get_disk_usage", MagicMock(return_value=winrm_response)):
        result = await server.check_disk_usage(
            computer_name="192.168.0.124", warn_threshold_percent=15
        )

    assert result["volumes"][0]["warning"] is False


@pytest.mark.asyncio
async def test_check_disk_usage_propagates_error():
    """If pywinrm returns an error, it should be passed through unchanged."""
    winrm_response = {"error": "WinRM connection refused"}

    with patch("server.get_disk_usage", MagicMock(return_value=winrm_response)):
        result = await server.check_disk_usage(computer_name="192.168.0.124")

    assert result == winrm_response


# ---------------------------------------------------------------------------
# check_uptime — calls pywinrm via run_in_executor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_uptime_returns_winrm_result():
    """check_uptime should return whatever get_uptime returns."""
    expected = {"uptime_seconds": 259200}

    with patch("server.get_uptime", MagicMock(return_value=expected)):
        result = await server.check_uptime(computer_name="192.168.0.124")

    assert result == expected


# ---------------------------------------------------------------------------
# Pi tools — delegate to run_ssh_bash_script
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_pi_service_calls_ssh():
    """check_pi_service should call run_ssh_bash_script with the service name as arg."""
    expected = {"active_state": "active", "service": "homebridge"}

    with patch("server.run_ssh_bash_script", new_callable=AsyncMock, return_value=expected) as mock_ssh:
        result = await server.check_pi_service(
            host="192.168.0.113", service_name="homebridge", user="mchapane"
        )

    mock_ssh.assert_called_once_with(
        "check-service.sh",
        host="192.168.0.113",
        user="mchapane",
        args=["homebridge"],
        ssh_key_path=None,
    )
    assert result == expected


@pytest.mark.asyncio
async def test_check_pi_disk_usage_passes_threshold_as_arg():
    """check_pi_disk_usage should pass warn_threshold_percent as a string CLI arg."""
    expected = {"volumes": [{"mount": "/", "percent_free": 60}]}

    with patch("server.run_ssh_bash_script", new_callable=AsyncMock, return_value=expected) as mock_ssh:
        result = await server.check_pi_disk_usage(
            host="192.168.0.113", user="mchapane", warn_threshold_percent=20
        )

    mock_ssh.assert_called_once_with(
        "check-disk.sh",
        host="192.168.0.113",
        user="mchapane",
        args=["20"],
        ssh_key_path=None,
    )
    assert result == expected


@pytest.mark.asyncio
async def test_check_pi_uptime_returns_ssh_result():
    """check_pi_uptime should return whatever run_ssh_bash_script returns."""
    expected = {"uptime_seconds": 86400, "uptime_readable": "1d 0h 0m"}

    with patch("server.run_ssh_bash_script", new_callable=AsyncMock, return_value=expected):
        result = await server.check_pi_uptime(host="192.168.0.113", user="mchapane")

    assert result == expected


# ---------------------------------------------------------------------------
# Homebridge tools — delegate to homebridge module
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_accessories_delegates_to_homebridge():
    """list_accessories should return whatever homebridge.list_accessories returns."""
    expected = {"accessories": [{"uniqueId": "aaa", "serviceName": "Bedroom Fan"}]}

    with patch("server.homebridge.list_accessories", new_callable=AsyncMock, return_value=expected):
        result = await server.list_accessories()

    assert result == expected


@pytest.mark.asyncio
async def test_set_accessory_passes_args_to_homebridge():
    """set_accessory should call homebridge.set_accessory with the right args."""
    expected = {"uniqueId": "aaa", "values": {"On": True}}

    with patch("server.homebridge.set_accessory", new_callable=AsyncMock, return_value=expected) as mock_set:
        result = await server.set_accessory(
            unique_id="aaa",
            characteristic_type="On",
            value="true",
        )

    mock_set.assert_called_once_with("aaa", "On", "true")
    assert result == expected


@pytest.mark.asyncio
async def test_list_homebridge_plugins_delegates():
    """list_homebridge_plugins should return whatever homebridge.list_plugins returns."""
    expected = {"plugins": [{"name": "homebridge-tuya", "version": "3.2.0"}]}

    with patch("server.homebridge.list_plugins", new_callable=AsyncMock, return_value=expected):
        result = await server.list_homebridge_plugins()

    assert result == expected


@pytest.mark.asyncio
async def test_get_homebridge_status_delegates():
    """get_homebridge_status should return whatever homebridge.get_homebridge_status returns."""
    expected = {"status": {"status": "up"}, "child_bridges": []}

    with patch("server.homebridge.get_homebridge_status", new_callable=AsyncMock, return_value=expected):
        result = await server.get_homebridge_status()

    assert result == expected
