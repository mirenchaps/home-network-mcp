"""
exporter.py

Prometheus metrics exporter for home-network-mcp.

Runs a collection loop every SCRAPE_INTERVAL seconds, polling Windows hosts
via pywinrm (winrm_collect.py) and the Raspberry Pi over SSH (runner.py),
and serves the results at http://localhost:8000/metrics for Grafana Alloy
to scrape.

Run alongside server.py as a separate process:
    python exporter.py
"""

import asyncio
import json
import logging
from pathlib import Path

from prometheus_client import Gauge, start_http_server

from runner import run_ssh_bash_script
from winrm_collect import get_disk_usage, get_service_health, get_uptime

# How often (in seconds) to re-poll all hosts
SCRAPE_INTERVAL = 30

CONFIG_PATH = Path(__file__).parent / "config.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def load_config() -> dict:
    """Read config.json from the project root.

    Raises FileNotFoundError with a helpful message if it hasn't been created
    yet (i.e. the user hasn't copied config.example.json to config.json).
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"config.json not found at {CONFIG_PATH}. "
            "Copy config.example.json to config.json and fill in your hosts."
        )
    return json.loads(CONFIG_PATH.read_text())


# ---------------------------------------------------------------------------
# Metric definitions
# Each Gauge takes: (metric_name, description, [label_names])
# ---------------------------------------------------------------------------
#Gauge that tracks whether a device on your network responded to a ping

device_up = Gauge(
    "home_device_up",
    "1 if the device responded to ping, 0 if unreachable",
    ["host"],
)

#Gauge that tracks how much disk space is free on a Windows volume (%)
disk_free_ratio = Gauge(
    "home_disk_free_ratio",
    "Fraction of disk space currently free (0.0 - 1.0)",
    ["host", "volume"],
)

#Gauge that tracks whether a Windows service is running (1) or stopped (0)
service_up = Gauge(
    "home_service_up",
    "1 if the Windows service is running, 0 otherwise",
    ["host", "service"],
)

#Gauge that tracks how long a Windows host has been up (in seconds)
uptime_seconds = Gauge(
    "home_uptime_seconds",
    "System uptime in seconds",
    ["host"],
)

#Same as above, but for Raspberry Pi hosts (via SSH)
pi_service_up = Gauge(
    "home_pi_service_up",
    "1 if the systemd service is active on the Pi, 0 otherwise",
    ["host", "service"],
)

pi_disk_free_ratio = Gauge(
    "home_pi_disk_free_ratio",
    "Fraction of disk space currently free on the Pi (0.0 - 1.0)",
    ["host", "mount"],
)

pi_uptime_seconds = Gauge(
    "home_pi_uptime_seconds",
    "Pi system uptime in seconds",
    ["host"],
)


# ---------------------------------------------------------------------------
# Collection functions
# One function per host type — each calls the runner helpers, parses the
# result, and updates the gauges defined above.
# ---------------------------------------------------------------------------

async def collect_windows_host(host_cfg: dict) -> None:
    """Collect all metrics for a single Windows host via WinRM/HTTPS using pywinrm."""
    name = host_cfg["name"]
    loop = asyncio.get_running_loop()

    # pywinrm is synchronous — run in a thread pool to avoid blocking the event loop
    disk_result = await loop.run_in_executor(None, get_disk_usage, name)
    if disk_result.get("error"):
        device_up.labels(host=name).set(0)
        log.warning("Host %s unreachable: %s", name, disk_result["error"])
        return

    device_up.labels(host=name).set(1)
    for vol in disk_result.get("volumes", []):
        ratio = vol["percent_free"] / 100.0
        disk_free_ratio.labels(host=name, volume=vol["drive"]).set(ratio)

    services = host_cfg.get("watch_services", [])
    if services:
        svc_result = await loop.run_in_executor(None, get_service_health, name, services)
        for svc in svc_result.get("services", []):
            val = 1 if svc["status"] == "Running" else 0
            service_up.labels(host=name, service=svc["name"]).set(val)

    up_result = await loop.run_in_executor(None, get_uptime, name)
    if "uptime_seconds" in up_result:
        uptime_seconds.labels(host=name).set(up_result["uptime_seconds"])


async def collect_pi(pi_cfg: dict) -> None:
    """Collect all metrics for the Raspberry Pi over SSH."""
    host = pi_cfg["host"]
    user = pi_cfg.get("user", "pi")
    key  = pi_cfg.get("ssh_key_path")

    # --- disk (also tells us if the Pi is reachable) ---
    disk_result = await run_ssh_bash_script("check-disk.sh", host=host, user=user, ssh_key_path=key)
    if disk_result.get("error"):
        pi_disk_free_ratio.labels(host=host, mount="/").set(0)
        log.warning("Pi %s unreachable: %s", host, disk_result["error"])
        return

    for vol in disk_result.get("volumes", []):
        ratio = vol["percent_free"] / 100.0
        pi_disk_free_ratio.labels(host=host, mount=vol["mount"]).set(ratio)

    # --- services ---
    for svc_name in pi_cfg.get("watch_services", []):
        svc_result = await run_ssh_bash_script(
            "check-service.sh", host=host, user=user, args=[svc_name], ssh_key_path=key
        )
        val = 1 if svc_result.get("active_state") == "active" else 0
        pi_service_up.labels(host=host, service=svc_name).set(val)

    # --- uptime ---
    up_result = await run_ssh_bash_script("check-uptime.sh", host=host, user=user, ssh_key_path=key)
    if "uptime_seconds" in up_result:
        pi_uptime_seconds.labels(host=host).set(up_result["uptime_seconds"])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def collection_loop(config: dict) -> None:
    """Poll all hosts on a fixed interval, updating gauges each cycle."""
    while True:
        log.info("Starting collection cycle...")

        tasks = [collect_windows_host(h) for h in config.get("known_hosts", [])]

        if "pi" in config:
            tasks.append(collect_pi(config["pi"]))

        await asyncio.gather(*tasks)

        log.info("Collection cycle complete. Sleeping %ss.", SCRAPE_INTERVAL)
        await asyncio.sleep(SCRAPE_INTERVAL)


if __name__ == "__main__":
    cfg = load_config()

    # Start the /metrics HTTP server on port 8000
    start_http_server(8000)
    log.info("Metrics server started on http://localhost:8000/metrics")

    asyncio.run(collection_loop(cfg))
