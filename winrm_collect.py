"""
winrm_collect.py

Collects metrics from Windows hosts via WinRM/HTTPS using pywinrm.
Replaces the PSWSMan-based PowerShell script approach, which timed out on Linux.

Functions are synchronous — call them with asyncio.get_running_loop().run_in_executor()
to avoid blocking the async collection loop.
"""

import json
import os

import winrm

WINRM_PORT = 5986
CA_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"


def _session(host: str) -> winrm.Session:
    return winrm.Session(
        f"https://{host}:{WINRM_PORT}/wsman",
        auth=(os.environ.get("WINRM_USERNAME", ""), os.environ.get("WINRM_PASSWORD", "")),
        transport="basic",
        server_cert_validation="validate",
        ca_trust_path=CA_BUNDLE,
    )


def get_disk_usage(host: str) -> dict:
    """Returns {"volumes": [{"drive": "C:", "percent_free": 45.2}]} or {"error": "..."}"""
    try:
        result = _session(host).run_ps(
            "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | "
            "Select-Object DeviceID,Size,FreeSpace | ConvertTo-Json -Compress"
        )
    except Exception as exc:
        return {"error": str(exc)}

    if result.status_code != 0:
        return {"error": result.std_err.decode(errors="replace").strip()}

    data = json.loads(result.std_out.decode())
    if isinstance(data, dict):
        data = [data]

    volumes = []
    for disk in data:
        if disk.get("Size"):
            pct = (disk["FreeSpace"] / disk["Size"]) * 100
            volumes.append({"drive": disk["DeviceID"], "percent_free": round(pct, 1)})
    return {"volumes": volumes}


def get_service_health(host: str, service_names: list) -> dict:
    """Returns {"services": [{"name": "WinRM", "status": "Running"}]} or {"error": "..."}"""
    names_ps = ",".join(f'"{n}"' for n in service_names)
    try:
        result = _session(host).run_ps(
            f"Get-Service -Name {names_ps} | "
            "Select-Object Name,@{Name='Status';Expression={$_.Status.ToString()}} | "
            "ConvertTo-Json -Compress"
        )
    except Exception as exc:
        return {"error": str(exc)}

    if result.status_code != 0:
        return {"error": result.std_err.decode(errors="replace").strip()}

    data = json.loads(result.std_out.decode())
    if isinstance(data, dict):
        data = [data]
    return {"services": [{"name": s["Name"], "status": s["Status"]} for s in data]}


def get_uptime(host: str) -> dict:
    """Returns {"uptime_seconds": 123456} or {"error": "..."}"""
    try:
        result = _session(host).run_ps(
            "[math]::Round(((Get-Date) - "
            "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime).TotalSeconds)"
        )
    except Exception as exc:
        return {"error": str(exc)}

    if result.status_code != 0:
        return {"error": result.std_err.decode(errors="replace").strip()}

    try:
        return {"uptime_seconds": int(result.std_out.decode().strip())}
    except ValueError:
        return {"error": f"Unexpected uptime output: {result.std_out.decode().strip()}"}
