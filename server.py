"""
home-network-mcp

A personal MCP server that exposes home network / home-lab monitoring
capabilities as tools an LLM client (e.g. Claude Desktop) can call.

Design notes
------------
The actual work (pinging hosts, querying services, checking disk usage,
reading uptime) is done by PowerShell scripts in ./scripts. This server is a
thin Python/MCP wrapper: it validates input, shells out to `pwsh`, parses the
JSON each script prints to stdout, and returns structured results back to the
client.

"""

import asyncio
import json
import shlex
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

SCRIPTS_DIR = Path(__file__).parent / "scripts"

mcp = MCPServer("home-network-mcp")

async def _run_pwsh_script(script_name: str, **params: Any) -> dict:
    """Run a PowerShell script in ./scripts and parse its JSON stdout.

    Params are passed through as PowerShell named parameters, e.g.
    _run_pwsh_script("Get-DiskUsage.ps1", ComputerName="HOMELAB-DC01")
    becomes: pwsh -File Get-DiskUsage.ps1 -ComputerName HOMELAB-DC01
    """
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"error": f"Script not found: {script_name}"}

    cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(script_path)]
    for key, value in params.items():
        if value is None:
            continue
        cmd.append(f"-{key}")
        if isinstance(value, list):
            # PowerShell string-array parameter, e.g. -ServiceNames Spooler,W32Time
            cmd.append(",".join(str(v) for v in value))
        else:
            cmd.append(str(value))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except FileNotFoundError:
        return {
            "error": "pwsh not found on PATH. Install PowerShell 7+ "
            "(winget install Microsoft.PowerShell) or point this at a "
            "machine that has it."
        }
    except asyncio.TimeoutError:
        return {"error": f"{script_name} timed out after 30s"}

    if proc.returncode != 0:
        return {
            "error": f"{script_name} exited {proc.returncode}",
            "stderr": stderr.decode(errors="replace").strip(),
        }

    raw = stdout.decode(errors="replace").strip()
    if not raw:
        return {"error": f"{script_name} produced no output"}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "Failed to parse script output as JSON", "raw": raw}


@mcp.tool()
async def scan_network(subnet: str, start_host: int = 1, end_host: int = 254) -> dict:
    """Ping-sweep a home subnet and report which devices are online.

    Args:
        subnet: First three octets, e.g. "192.168.1"
        start_host: First host octet to scan (default 1)
        end_host: Last host octet to scan (default 254)
    """
    return await _run_pwsh_script(
        "Get-DeviceStatus.ps1",
        Subnet=subnet,
        StartHost=start_host,
        EndHost=end_host,
    )


@mcp.tool()
async def check_service_health(service_names: list[str], computer_name: str = "localhost") -> dict:
    """Check the status of one or more Windows services on a host.

    Args:
        service_names: Service names to check, e.g. ["Spooler", "W32Time"]
        computer_name: Target hostname. Defaults to localhost.
    """
    return await _run_pwsh_script(
        "Get-ServiceHealth.ps1",
        ComputerName=computer_name,
        ServiceNames=service_names,
    )


@mcp.tool()
async def check_disk_usage(computer_name: str = "localhost", warn_threshold_percent: int = 15) -> dict:
    """Check disk usage on all fixed volumes of a host, flagging low free space.

    Args:
        computer_name: Target hostname. Defaults to localhost.
        warn_threshold_percent: Percent free space below which a volume is flagged.
    """
    return await _run_pwsh_script(
        "Get-DiskUsage.ps1",
        ComputerName=computer_name,
        WarnThresholdPercent=warn_threshold_percent,
    )


@mcp.tool()
async def check_uptime(computer_name: str = "localhost") -> dict:
    """Get system uptime and last boot time for a host.

    Args:
        computer_name: Target hostname. Defaults to localhost.
    """
    return await _run_pwsh_script("Get-SystemUptime.ps1", ComputerName=computer_name)


if __name__ == "__main__":
    mcp.run()
