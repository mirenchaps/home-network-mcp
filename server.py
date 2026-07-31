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

from mcp.server import MCPServer

from runner import run_pwsh_script, run_ssh_bash_script

mcp = MCPServer("home-network-mcp")


@mcp.tool()
async def scan_network(subnet: str, start_host: int = 1, end_host: int = 254) -> dict:
    """Ping-sweep a home subnet and report which devices are online.

    Args:
        subnet: First three octets, e.g. "192.168.1"
        start_host: First host octet to scan (default 1)
        end_host: Last host octet to scan (default 254)
    """
    return await run_pwsh_script(
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
    return await run_pwsh_script(
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
    return await run_pwsh_script(
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
    return await run_pwsh_script("Get-SystemUptime.ps1", ComputerName=computer_name)


@mcp.tool()
async def check_pi_service(
    host: str,
    service_name: str = "homebridge",
    user: str = "pi",
    ssh_key_path: str | None = None,
) -> dict:
    """Check the status of a systemd service on a Raspberry Pi over SSH.

    Defaults to checking Homebridge, but works for any systemd unit.

    Args:
        host: Pi's hostname or IP, e.g. "raspberrypi.local" or "192.168.0.50"
        service_name: systemd unit name to check. Defaults to "homebridge".
        user: SSH user. Defaults to "pi".
        ssh_key_path: Optional path to a specific SSH private key.
    """
    return await run_ssh_bash_script(
        "check-service.sh",
        host=host,
        user=user,
        args=[service_name],
        ssh_key_path=ssh_key_path,
    )


@mcp.tool()
async def check_pi_disk_usage(
    host: str,
    user: str = "pi",
    warn_threshold_percent: int = 15,
    ssh_key_path: str | None = None,
) -> dict:
    """Check disk usage on a Raspberry Pi's mounted filesystems over SSH.

    Particularly useful for SD-card-based Pis, where logs or media can
    quietly fill a small card over time.

    Args:
        host: Pi's hostname or IP, e.g. "raspberrypi.local" or "192.168.0.50"
        user: SSH user. Defaults to "pi".
        warn_threshold_percent: Percent free space below which a volume is flagged.
        ssh_key_path: Optional path to a specific SSH private key.
    """
    return await run_ssh_bash_script(
        "check-disk.sh",
        host=host,
        user=user,
        args=[str(warn_threshold_percent)],
        ssh_key_path=ssh_key_path,
    )


@mcp.tool()
async def check_pi_uptime(
    host: str,
    user: str = "pi",
    ssh_key_path: str | None = None,
) -> dict:
    """Get system uptime and last boot time for a Raspberry Pi over SSH.

    Args:
        host: Pi's hostname or IP, e.g. "raspberrypi.local" or "192.168.0.50"
        user: SSH user. Defaults to "pi".
        ssh_key_path: Optional path to a specific SSH private key.
    """
    return await run_ssh_bash_script(
        "check-uptime.sh",
        host=host,
        user=user,
        ssh_key_path=ssh_key_path,
    )


if __name__ == "__main__":
    mcp.run()