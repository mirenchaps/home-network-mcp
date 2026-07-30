# home-network-mcp

A personal [MCP](https://modelcontextprotocol.io) server that lets an LLM client (Claude Desktop, etc.) monitor my home network and home lab: which devices are online, whether key services are healthy, disk space, and uptime — across both my Windows Server 2022 home lab and a Raspberry Pi running Homebridge.

## Why I built this

I wanted to understand how MCP actually works under the hood — not just use it, but build a server from scratch and see how tool schemas, async dispatch, and client/server message flow fit together. Wiring it up against my own home lab (a Windows Server 2022 environment) rather than a toy example forced me to deal with real problems: WinRM auth, parsing PowerShell's JSON output cleanly, timeouts on unreachable hosts, and so on.

It's also a deliberate split of responsibilities:
- **Python / MCP** — protocol layer: tool definitions, schemas, async orchestration
- **PowerShell** — automation layer for Windows targets: the actual Windows-native work (`Get-Volume`, `Get-Service`, WMI queries, `Invoke-Command` over WinRM)
- **Bash over SSH** — automation layer for Linux targets: querying `systemd`, `df`, `/proc/uptime` on my Raspberry Pi

Rather than reimplementing OS-native administration primitives in Python, the server shells out to the right tool for the target platform (PowerShell for Windows, Bash/SSH for Linux) and just handles the plumbing. Extending it to the Pi was also a deliberate push on Bash specifically — my PowerShell is much stronger day-to-day, so building the disk-usage script's field-parsing logic in pure Bash (rather than reaching for Python) was the point, not just a means to an end.

## Status

`scan_network` is built and tested end-to-end on macOS against my home subnet, both via the MCP Inspector and Claude Desktop. The Windows-specific tools (`check_service_health`, `check_disk_usage`, `check_uptime`) are implemented but not yet verified against a live host — next step is pointing them at my Windows Server 2022 home lab VM over WinRM. The Raspberry Pi / Homebridge tools (`check_pi_service`, `check_pi_disk_usage`, `check_pi_uptime`) are newly added and not yet tested against the real Pi — next step there is confirming SSH key auth is set up and running each tool once against it.

## Tools exposed

| Tool | Description |
|---|---|
| `scan_network` | Ping-sweeps a subnet, returns which hosts are up and their latency |
| `check_service_health` | Checks status of named Windows services on a host |
| `check_disk_usage` | Reports free/used space per volume on a Windows host, flags low free space |
| `check_uptime` | Returns last boot time and uptime for a Windows host |
| `check_pi_service` | Checks status of a systemd service (defaults to Homebridge) on the Pi over SSH |
| `check_pi_disk_usage` | Reports free/used space per mounted filesystem on the Pi, flags low free space |
| `check_pi_uptime` | Returns last boot time and uptime for the Pi |

## Requirements

- Python 3.10+
- [PowerShell 7+](https://github.com/PowerShell/PowerShell) (`pwsh`) on PATH
- `mcp[cli]` — this repo was built and tested against `mcp==2.0.0`. Note that this version's Python SDK exposes `MCPServer` directly from `mcp.server` (not `FastMCP` from `mcp.server.fastmcp`, which is what older versions/tutorials use). If you're on a different version and imports fail, check `python3 -c "import mcp.server as s; print(dir(s))"` to see what's actually available in your installed version before assuming the API.
- For remote hosts: WinRM enabled and reachable (`Enable-PSRemoting`), and the account running the server needs appropriate rights on target machines
- For the Raspberry Pi: SSH key-based auth set up (`ssh-copy-id pi@<pi-host>`) — password auth is intentionally not supported by the SSH tools, since `BatchMode=yes` is used to fail fast rather than hang waiting for a prompt
- [`uv`](https://github.com/astral-sh/uv) — only needed for local dev testing via `mcp dev` (the MCP Inspector shells out to it). Not required to actually run the server day-to-day. Install with `brew install uv`.

## Setup

```bash
git clone https://github.com/mirenchaps/home-network-mcp.git
cd home-network-mcp
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install "mcp[cli]"
cp config.example.json config.json  # then edit with your own hosts
```

### macOS-specific notes

PowerShell isn't native to macOS but runs fine via `pwsh`:

```bash
brew install --cask powershell@preview  # cask name may vary by Homebrew version
```

If `pwsh` isn't found on PATH after install, locate the binary and symlink it manually:

```bash
find /usr/local/microsoft/powershell -name pwsh
sudo ln -sf /usr/local/microsoft/powershell/<version>/pwsh /usr/local/bin/pwsh
```

`scan_network` (`Get-DeviceStatus.ps1`) works locally on macOS since it only uses cross-platform .NET networking APIs. `check_service_health`, `check_disk_usage`, and `check_uptime` call Windows-only cmdlets (`Get-Service`, `Get-Volume`, `Win32_OperatingSystem` via CIM) and will **only work against a remote Windows host** passed via `-ComputerName` / `computer_name` — they can't run locally on a Mac.

### Testing locally with the MCP Inspector

Before wiring this into Claude Desktop, it's worth confirming the server works in isolation:

```bash
mcp dev server.py
```

This launches a local web UI (via `uv run` under the hood) where you can call each tool directly and inspect the generated schema and raw JSON-RPC traffic — much faster to iterate on than restarting Claude Desktop every time.

### Register with Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and point at your venv's Python directly, so it has access to the installed `mcp` package:

```json
{
  "mcpServers": {
    "home-network": {
      "command": "/absolute/path/to/home-network-mcp/.venv/bin/python3",
      "args": ["/absolute/path/to/home-network-mcp/server.py"]
    }
  }
}
```

Fully quit (Cmd+Q) and reopen Claude Desktop — the tools above will then be available in conversation, e.g. "check disk usage on HOMELAB-FILESRV" or "scan my network and tell me what's online."

## Project structure

```
home-network-mcp/
├── server.py                  # MCP server + tool definitions
├── scripts/
│   ├── Get-DeviceStatus.ps1    # subnet ping sweep
│   ├── Get-ServiceHealth.ps1   # Windows service status
│   ├── Get-DiskUsage.ps1       # disk/volume free space (Windows)
│   ├── Get-SystemUptime.ps1    # uptime / last boot (Windows)
│   └── pi/
│       ├── check-service.sh    # systemd service status (e.g. Homebridge)
│       ├── check-disk.sh       # disk/volume free space (Linux)
│       └── check-uptime.sh     # uptime / last boot (Linux)
├── config.example.json        # example host inventory
└── requirements.txt
```

## Notes / limitations

- This is a personal project for my own home lab, not hardened for production or multi-tenant use — no auth on the PowerShell remoting beyond standard WinRM, no rate limiting, no retry logic beyond a basic timeout.
- Local (non-domain) WinRM setups may need `TrustedHosts` configured for cross-machine calls without Kerberos.
- Tested against Windows Server 2022 and Windows 11 hosts on PowerShell 7.4.
