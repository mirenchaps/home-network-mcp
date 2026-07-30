# home-network-mcp

A personal MCP server that lets an LLM client (Claude Desktop, etc.) monitor my home network and home lab: which devices are online, whether key services are healthy, disk space, and uptime.

## Why I built this

I wanted to understand how MCP actually works under the hood — not just use it, but build a server from scratch and see how tool schemas, async dispatch, and client/server message flow fit together. Wiring it up against my own home lab (a Windows Server 2022 environment) rather than a toy example forced me to deal with real problems: WinRM auth, parsing PowerShell's JSON output cleanly, timeouts on unreachable hosts, and so on.

It's also a deliberate split of responsibilities:
- **Python / MCP** — protocol layer: tool definitions, schemas, async orchestration
- **PowerShell** — automation layer: the actual Windows-native work (`Get-Volume`, `Get-Service`, WMI queries, `Invoke-Command` over WinRM)

Rather than reimplementing Windows administration primitives in Python, the server shells out to PowerShell for anything Windows-specific and just handles the plumbing.

## Tools exposed

| Tool | Description |
|---|---|
| `scan_network` | Ping-sweeps a subnet, returns which hosts are up and their latency |
| `check_service_health` | Checks status of named Windows services on a host |
| `check_disk_usage` | Reports free/used space per volume, flags low free space |
| `check_uptime` | Returns last boot time and uptime for a host |

## Requirements

- Python 3.10+
- [PowerShell 7+](https://github.com/PowerShell/PowerShell) (`pwsh`) on PATH
- For remote hosts: WinRM enabled and reachable (`Enable-PSRemoting`), and the account running the server needs appropriate rights on target machines

## Setup

```bash
git clone https://github.com/mirenchaps/home-network-mcp.git
cd home-network-mcp
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp config.example.json config.json  # then edit with your own hosts
```

### Register with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "home-network": {
      "command": "python",
      "args": ["/absolute/path/to/home-network-mcp/server.py"]
    }
  }
}
```

Restart Claude Desktop and the tools above will be available in conversation, e.g. "check disk usage on HOMELAB-FILESRV" or "scan my network and tell me what's online."

## Project structure

```
home-network-mcp/
├── server.py                  # MCP server + tool definitions
├── scripts/
│   ├── Get-DeviceStatus.ps1    # subnet ping sweep
│   ├── Get-ServiceHealth.ps1   # Windows service status
│   ├── Get-DiskUsage.ps1       # disk/volume free space
│   └── Get-SystemUptime.ps1    # uptime / last boot
├── config.example.json        # example host inventory
└── requirements.txt
```

## Notes / limitations

- This is a personal project for my own home lab, not hardened for production or multi-tenant use — no auth on the PowerShell remoting beyond standard WinRM, no rate limiting, no retry logic beyond a basic timeout.
- Local (non-domain) WinRM setups may need `TrustedHosts` configured for cross-machine calls without Kerberos.
- Tested against Windows Server 2022 and Windows 11 hosts on PowerShell 7.4.
