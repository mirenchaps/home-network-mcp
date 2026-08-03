"""
home-network-mcp

A personal MCP server that exposes home network / home-lab monitoring
capabilities as tools an LLM client (e.g. Claude Desktop) can call.

Design notes
------------
Windows targets (WinRM): tools call pywinrm helpers in winrm_collect.py
directly — no subprocess/PowerShell needed for authenticated WinRM calls.
Credentials are read from WINRM_USERNAME / WINRM_PASSWORD env vars.

Network sweep: still uses PowerShell (Get-DeviceStatus.ps1) via runner.py,
since it uses .NET ping APIs that work cross-platform with pwsh.

Linux/Pi targets: runner.py pipes Bash scripts over SSH.
"""

import asyncio
from typing import Annotated

from pydantic import Field

from mcp.server import MCPServer

from runner import run_pwsh_script, run_ssh_bash_script
from winrm_collect import get_disk_usage, get_service_health, get_uptime

mcp = MCPServer("home-network-mcp")


@mcp.tool(title="Scan Network")
async def scan_network(
    subnet: Annotated[str, Field(description='First three octets of the subnet, e.g. "192.168.0"')],
    start_host: Annotated[int, Field(description="First host octet to scan", ge=1, le=254)] = 1,
    end_host: Annotated[int, Field(description="Last host octet to scan", ge=1, le=254)] = 254,
) -> dict:
    """Ping-sweep a home subnet and report which devices are online."""
    return await run_pwsh_script(
        "Get-DeviceStatus.ps1",
        Subnet=subnet,
        StartHost=start_host,
        EndHost=end_host,
    )


@mcp.tool(title="Check Service Health")
async def check_service_health(
    service_names: Annotated[list[str], Field(description='Service names to check, e.g. ["Spooler", "W32Time"]')],
    computer_name: Annotated[str, Field(description="Target hostname or IP. Defaults to localhost.")] = "localhost",
) -> dict:
    """Check the status of one or more Windows services on a host."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_service_health, computer_name, service_names)


@mcp.tool(title="Check Disk Usage")
async def check_disk_usage(
    computer_name: Annotated[str, Field(description="Target hostname or IP. Defaults to localhost.")] = "localhost",
    warn_threshold_percent: Annotated[int, Field(description="Percent free space below which a volume is flagged as warning.", ge=0, le=100)] = 15,
) -> dict:
    """Check disk usage on all fixed volumes of a Windows host, flagging low free space."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_disk_usage, computer_name)
    if result.get("error"):
        return result
    # apply warning threshold in Python (pywinrm helper doesn't take a threshold param)
    for vol in result.get("volumes", []):
        vol["warning"] = vol["percent_free"] < warn_threshold_percent
    return result


@mcp.tool(title="Check Uptime")
async def check_uptime(
    computer_name: Annotated[str, Field(description="Target hostname or IP. Defaults to localhost.")] = "localhost",
) -> dict:
    """Get system uptime in seconds and last boot time for a Windows host."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_uptime, computer_name)


@mcp.tool(title="Check Pi Service")
async def check_pi_service(
    host: Annotated[str, Field(description='Pi hostname or IP, e.g. "192.168.0.113" or "raspberrypi.local"')],
    service_name: Annotated[str, Field(description="systemd unit name to check")] = "homebridge",
    user: Annotated[str, Field(description="SSH user on the Pi")] = "pi",
    ssh_key_path: Annotated[str | None, Field(description="Path to SSH private key. Uses default SSH key if omitted.")] = None,
) -> dict:
    """Check the status of a systemd service on a Raspberry Pi over SSH."""
    return await run_ssh_bash_script(
        "check-service.sh",
        host=host,
        user=user,
        args=[service_name],
        ssh_key_path=ssh_key_path,
    )


@mcp.tool(title="Check Pi Disk Usage")
async def check_pi_disk_usage(
    host: Annotated[str, Field(description='Pi hostname or IP, e.g. "192.168.0.113" or "raspberrypi.local"')],
    user: Annotated[str, Field(description="SSH user on the Pi")] = "pi",
    warn_threshold_percent: Annotated[int, Field(description="Percent free space below which a volume is flagged as warning.", ge=0, le=100)] = 15,
    ssh_key_path: Annotated[str | None, Field(description="Path to SSH private key. Uses default SSH key if omitted.")] = None,
) -> dict:
    """Check disk usage on a Raspberry Pi's mounted filesystems over SSH."""
    return await run_ssh_bash_script(
        "check-disk.sh",
        host=host,
        user=user,
        args=[str(warn_threshold_percent)],
        ssh_key_path=ssh_key_path,
    )


@mcp.tool(title="Check Pi Uptime")
async def check_pi_uptime(
    host: Annotated[str, Field(description='Pi hostname or IP, e.g. "192.168.0.113" or "raspberrypi.local"')],
    user: Annotated[str, Field(description="SSH user on the Pi")] = "pi",
    ssh_key_path: Annotated[str | None, Field(description="Path to SSH private key. Uses default SSH key if omitted.")] = None,
) -> dict:
    """Get system uptime and last boot time for a Raspberry Pi over SSH."""
    return await run_ssh_bash_script(
        "check-uptime.sh",
        host=host,
        user=user,
        ssh_key_path=ssh_key_path,
    )


if __name__ == "__main__":
    mcp.run()
