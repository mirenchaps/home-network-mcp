"""
tests/test_runner.py

Unit tests for runner.py.

Both run_pwsh_script and run_ssh_bash_script shell out to external processes.
Tests mock asyncio.create_subprocess_exec so they run anywhere (CI, macOS,
no network, no PowerShell) and fail for logic reasons, not environmental ones.

Run with: pytest tests/ -v
Docs: https://docs.pytest.org  /  https://pytest-asyncio.readthedocs.io
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from runner import run_pwsh_script, run_ssh_bash_script


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(stdout: bytes, stderr: bytes = b"", returncode: int = 0):
    """Build a fake asyncio subprocess whose communicate() returns fixed output."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ---------------------------------------------------------------------------
# run_pwsh_script
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_pwsh_script_success():
    """Happy path: valid JSON on stdout is parsed and returned as a dict."""
    payload = {"volumes": [{"drive": "C:", "percent_free": 45}]}
    proc = _make_proc(json.dumps(payload).encode())

    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_pwsh_script("Get-DiskUsage.ps1", ComputerName="HOMELAB-DC01")

    assert result == payload


@pytest.mark.asyncio
async def test_run_pwsh_script_nonzero_exit():
    """Non-zero exit code returns an error dict with the stderr message."""
    proc = _make_proc(b"", stderr=b"Access denied", returncode=1)

    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_pwsh_script("Get-DiskUsage.ps1")

    assert "error" in result
    assert result.get("stderr") == "Access denied"


@pytest.mark.asyncio
async def test_run_pwsh_script_empty_output():
    """Empty stdout returns a descriptive error, not a JSON parse crash."""
    proc = _make_proc(b"")

    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_pwsh_script("Get-DiskUsage.ps1")

    assert "error" in result
    assert "no output" in result["error"]


@pytest.mark.asyncio
async def test_run_pwsh_script_bad_json():
    """Non-JSON stdout returns error with the raw output for debugging."""
    proc = _make_proc(b"not json at all")

    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_pwsh_script("Get-DiskUsage.ps1")

    assert "error" in result
    assert result.get("raw") == "not json at all"


@pytest.mark.asyncio
async def test_run_pwsh_script_timeout():
    """asyncio.TimeoutError is caught and returned as an error dict."""
    async def _hanging_communicate():
        await asyncio.sleep(9999)

    proc = MagicMock()
    proc.communicate = _hanging_communicate

    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        with patch("runner.asyncio.wait_for", AsyncMock(side_effect=asyncio.TimeoutError)):
            result = await run_pwsh_script("Get-DiskUsage.ps1")

    assert "error" in result
    assert "timed out" in result["error"]


@pytest.mark.asyncio
async def test_run_pwsh_script_pwsh_not_found():
    """FileNotFoundError (pwsh missing) returns a helpful error message."""
    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError)):
        result = await run_pwsh_script("Get-DiskUsage.ps1")

    assert "error" in result
    assert "pwsh not found" in result["error"]


@pytest.mark.asyncio
async def test_run_pwsh_script_missing_script():
    """If the script file doesn't exist, return an error before spawning anything."""
    result = await run_pwsh_script("NonExistent.ps1")
    assert "error" in result
    assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# run_ssh_bash_script
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_ssh_bash_script_success():
    """Happy path: JSON from the remote script is parsed and returned."""
    payload = {"active_state": "active", "service": "homebridge"}
    proc = _make_proc(json.dumps(payload).encode())

    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_ssh_bash_script("check-service.sh", host="192.168.0.113", user="pi")

    assert result == payload


@pytest.mark.asyncio
async def test_run_ssh_bash_script_ssh_failure():
    """Non-zero SSH exit (e.g. auth failure) returns error with stderr."""
    proc = _make_proc(b"", stderr=b"Permission denied (publickey)", returncode=255)

    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_ssh_bash_script("check-service.sh", host="192.168.0.113", user="pi")

    assert "error" in result
    assert "Permission denied" in result["stderr"]


@pytest.mark.asyncio
async def test_run_ssh_bash_script_timeout():
    """SSH timeout is caught and returned as an error dict."""
    with patch("runner.asyncio.create_subprocess_exec", AsyncMock(return_value=MagicMock())):
        with patch("runner.asyncio.wait_for", AsyncMock(side_effect=asyncio.TimeoutError)):
            result = await run_ssh_bash_script("check-service.sh", host="192.168.0.113", user="pi")

    assert "error" in result
    assert "timed out" in result["error"]


@pytest.mark.asyncio
async def test_run_ssh_bash_script_missing_script():
    """If the local script file doesn't exist, return an error immediately."""
    result = await run_ssh_bash_script("nonexistent.sh", host="192.168.0.113", user="pi")
    assert "error" in result
    assert "not found" in result["error"]
