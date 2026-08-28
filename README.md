# home-network-mcp

A personal [MCP](https://modelcontextprotocol.io) server that lets an LLM client (Claude Desktop, etc.) monitor my home network and home lab: which devices are online, whether key services are healthy, disk space, and uptime — across both my Windows Server 2022 home lab and a Raspberry Pi running Homebridge.

Alongside the MCP server, a Prometheus metrics exporter runs continuously, scraped by the home lab's own kube-prometheus-stack for dashboarding and alerting.

## Why I built this

I wanted to understand how MCP actually works under the hood — not just use it, but build a server from scratch and see how tool schemas, async dispatch, and client/server message flow fit together. Wiring it up against my own home lab (a Windows Server 2022 environment) rather than a toy example forced me to deal with real problems: WinRM auth, parsing PowerShell's JSON output cleanly, timeouts on unreachable hosts, and so on.

Adding observability was a deliberate second layer — the MCP server is reactive (Claude asks, it answers), but a metrics exporter makes the monitoring continuous. Disk usage creeping up over weeks, a service that restarts every Tuesday because of Windows Update, a Pi that's been silently unreachable for hours — none of that is visible from on-demand polling alone.

It's also a deliberate split of responsibilities:
- **Python / MCP** — protocol layer: tool definitions, schemas, async orchestration
- **PowerShell** — automation layer for Windows targets: the actual Windows-native work (`Get-Volume`, `Get-Service`, WMI queries, `Invoke-Command` over WinRM)
- **Bash over SSH** — automation layer for Linux targets: querying `systemd`, `df`, `/proc/uptime` on my Raspberry Pi
- **Prometheus + Grafana** — observability layer: continuous metric collection, time-series storage, dashboarding and alerting

## Status

`scan_network` is built and tested end-to-end on macOS against my home subnet, both via the MCP Inspector and Claude Desktop. The Windows-specific tools (`check_service_health`, `check_disk_usage`, `check_uptime`) are implemented but not yet verified against a live host — next step is pointing them at my Windows Server 2022 home lab over WinRM. The Raspberry Pi / Homebridge tools (`check_pi_service`, `check_pi_disk_usage`, `check_pi_uptime`) are newly added and not yet tested against the real Pi.

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

## Metrics exposed

The exporter (`exporter.py`) continuously collects and serves the following Prometheus metrics:

| Metric | Labels | Description |
| --- | --- | --- |
| `home_device_up` | `host` | 1 if the device responded to ping, 0 if unreachable |
| `home_disk_free_ratio` | `host`, `volume` | Fraction of disk space free (0.0–1.0) on Windows hosts |
| `home_service_up` | `host`, `service` | 1 if the Windows service is running, 0 otherwise |
| `home_uptime_seconds` | `host` | System uptime in seconds for Windows hosts |
| `home_pi_service_up` | `host`, `service` | 1 if the systemd service is active on the Pi |
| `home_pi_disk_free_ratio` | `host`, `mount` | Fraction of disk space free (0.0–1.0) on the Pi |
| `home_pi_uptime_seconds` | `host` | System uptime in seconds for the Pi |

## Requirements

- Python 3.10+
- [PowerShell 7+](https://github.com/PowerShell/PowerShell) (`pwsh`) on PATH
- `mcp[cli]` and `prometheus_client` — see `requirements.txt`
- For remote hosts: WinRM enabled and reachable (`Enable-PSRemoting`), and the account running the server needs appropriate rights on target machines
- For the Raspberry Pi: SSH key-based auth set up (`ssh-copy-id pi@<pi-host>`) — password auth is intentionally not supported
- The home lab's kube-prometheus-stack scrapes both Deployments in-cluster; no external metrics account is needed

## Setup

```bash
git clone https://github.com/mirenchaps/home-network-mcp.git
cd home-network-mcp
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp config.example.json config.json  # then edit with your own hosts
```

### Config

`config.json` (gitignored — never committed) tells both the MCP server and the exporter which hosts and services to monitor:

```json
{
  "subnet": "192.168.1",
  "known_hosts": [
    { "name": "HOMELAB-DC01", "watch_services": ["DNS", "NTDS"] }
  ],
  "disk_warn_threshold_percent": 15,
  "pi": {
    "host": "raspberrypi.local",
    "user": "pi",
    "ssh_key_path": null,
    "watch_services": ["homebridge"]
  }
}
```

### Running the MCP server

```bash
python server.py
```

### Running the metrics exporter

In a separate terminal (or as a Windows service):

```bash
python exporter.py
```

Metrics are served at `http://localhost:8000/metrics`.

### In-cluster Prometheus scraping

Both Deployments are scraped by the home lab's kube-prometheus-stack. Each one ships a
`ServiceMonitor` rendered by the shared Helm chart in `home-lab-gitops`, enabled per app
via `metrics.enabled` in that app's values file.

| App | Port | Path | Metrics |
| --- | --- | --- | --- |
| `home-network-mcp` | 8000 | `/metrics` | `home_device_up`, `home_service_up`, disk/uptime gauges |
| `home-network-mcp-server` | 8001 | `/metrics` | `mcp_tool_calls_total`, `mcp_tool_call_duration_seconds` |

The `ServiceMonitor` must carry `release: prometheus` -- that Prometheus only adopts
ServiceMonitors with that label, and one without it is ignored silently.

Previously the exporter's metrics went to Grafana Cloud via a Grafana Alloy agent running
directly on the Windows box. That was dropped once the app moved into Kubernetes: two
metrics destinations meant two places to look, and the Alloy config still described
scraping `localhost:8000` on a host the app no longer ran on.

### macOS-specific notes

PowerShell isn't native to macOS but runs fine via `pwsh`:

```bash
brew install --cask powershell@preview
```

`scan_network` works locally on macOS since it only uses cross-platform .NET networking APIs. `check_service_health`, `check_disk_usage`, and `check_uptime` call Windows-only cmdlets and will **only work against a remote Windows host** passed via `computer_name`.

### Testing locally with the MCP Inspector

```bash
mcp dev server.py
```

This launches a local web UI where you can call each tool directly and inspect the generated schema and raw JSON-RPC traffic.

### Register with Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

## Project structure

```
home-network-mcp/
├── server.py                   # MCP server + tool definitions
├── runner.py                   # Shared async helpers (pwsh + SSH)
├── exporter.py                 # Prometheus metrics exporter
├── config.example.json         # Example host inventory (copy to config.json)
├── scripts/
│   ├── Get-DeviceStatus.ps1    # subnet ping sweep
│   ├── Get-ServiceHealth.ps1   # Windows service status
│   ├── Get-DiskUsage.ps1       # disk/volume free space (Windows)
│   ├── Get-SystemUptime.ps1    # uptime / last boot (Windows)
│   └── pi/
│       ├── check-service.sh    # systemd service status
│       ├── check-disk.sh       # disk/volume free space (Linux)
│       └── check-uptime.sh     # uptime / last boot (Linux)
└── requirements.txt
```

## Notes / limitations

- Credentials are never hardcoded — `config.json` is gitignored, and WinRM/Homebridge/SSH credentials are injected from Kubernetes Secrets.
- **This is a personal project for my own home lab, not hardened for production or multi-tenant use — no auth on the PowerShell remoting beyond standard WinRM, no rate limiting, no retry logic beyond a basic timeout.**
- Local (non-domain) WinRM setups may need `TrustedHosts` configured for cross-machine calls without Kerberos.
- Tested against Windows Server 2022 and Windows 11 hosts on PowerShell 7.4.


