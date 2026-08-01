"""
tests/test_exporter.py

Unit tests for exporter.py.

The exporter calls run_pwsh_script and run_ssh_bash_script to poll real hosts.
In tests we mock those helpers so the tests run anywhere (CI, Mac, no network)
and fail for code-logic reasons, not environmental ones.

Run with: pytest tests/ -v
Docs: https://docs.pytest.org  /  https://pytest-asyncio.readthedocs.io
"""

from unittest.mock import AsyncMock, patch

import pytest
from prometheus_client import REGISTRY

import exporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_gauge(metric_name: str, labels: dict) -> float:
    """Read the current value of a prometheus_client Gauge by name and labels.

    prometheus_client stores metrics in a global REGISTRY. We look up samples
    by name and match the label set to find the specific time series we want.
    """
    for metric in REGISTRY.collect():
        if metric.name == metric_name:
            for sample in metric.samples:
                if all(sample.labels.get(k) == v for k, v in labels.items()):
                    return sample.value
    raise KeyError(f"No sample found for {metric_name} {labels}")


# ---------------------------------------------------------------------------
# Windows host collection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collect_windows_host_marks_device_up_on_success():
    """When disk polling succeeds, device_up should be set to 1."""
    host_cfg = {"name": "HOMELAB-DC01", "watch_services": []}

    mock_disk = {"volumes": [{"drive": "C:", "percent_free": 40}]}

    with patch("exporter.run_pwsh_script", new_callable=AsyncMock) as mock_run:
        # First call is Get-DiskUsage, second would be Get-SystemUptime
        mock_run.side_effect = [
            mock_disk,
            {"uptime_days": 3},
        ]
        await exporter.collect_windows_host(host_cfg)

    assert get_gauge("home_device_up", {"host": "HOMELAB-DC01"}) == 1.0


@pytest.mark.asyncio
async def test_collect_windows_host_marks_device_down_on_error():
    """When disk polling returns an error, device_up should be set to 0."""
    host_cfg = {"name": "HOMELAB-DC01", "watch_services": []}

    with patch("exporter.run_pwsh_script", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"error": "WinRM connection refused"}
        await exporter.collect_windows_host(host_cfg)

    assert get_gauge("home_device_up", {"host": "HOMELAB-DC01"}) == 0.0


@pytest.mark.asyncio
async def test_collect_windows_host_sets_disk_free_ratio():
    """Disk free ratio should be stored as a fraction (percent / 100)."""
    host_cfg = {"name": "HOMELAB-DC01", "watch_services": []}

    mock_disk = {"volumes": [{"drive": "C:", "percent_free": 60}]}

    with patch("exporter.run_pwsh_script", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [mock_disk, {"uptime_days": 1}]
        await exporter.collect_windows_host(host_cfg)

    ratio = get_gauge("home_disk_free_ratio", {"host": "HOMELAB-DC01", "volume": "C:"})
    assert ratio == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Pi collection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collect_pi_sets_disk_free_ratio():
    """Pi disk free ratio should be stored as a fraction."""
    pi_cfg = {"host": "raspberrypi.local", "user": "pi", "watch_services": []}

    mock_disk = {"volumes": [{"mount": "/", "percent_free": 50}]}

    with patch("exporter.run_ssh_bash_script", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            mock_disk,
            {"uptime_days": 10},
        ]
        await exporter.collect_pi(pi_cfg)

    ratio = get_gauge(
        "home_pi_disk_free_ratio",
        {"host": "raspberrypi.local", "mount": "/"},
    )
    assert ratio == pytest.approx(0.50)


@pytest.mark.asyncio
async def test_collect_pi_handles_unreachable_host():
    """When the Pi is unreachable, disk ratio should be set to 0 and no crash."""
    pi_cfg = {"host": "raspberrypi.local", "user": "pi", "watch_services": []}

    with patch("exporter.run_ssh_bash_script", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"error": "ssh: connect to host raspberrypi.local port 22: No route to host"}
        await exporter.collect_pi(pi_cfg)

    ratio = get_gauge(
        "home_pi_disk_free_ratio",
        {"host": "raspberrypi.local", "mount": "/"},
    )
    assert ratio == 0.0
