"""
runner.py

Shared async helpers for shelling out to PowerShell scripts (Windows targets)
and Bash scripts over SSH (Linux/Pi targets).

Imported by both server.py (MCP tool dispatch) and exporter.py (metrics
collection) so the execution logic lives in one place.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).parent / "scripts"
PI_SCRIPTS_DIR = SCRIPTS_DIR / "pi"


async def run_pwsh_script(script_name: str, **params: Any) -> dict:
    """Run a PowerShell script in ./scripts and parse its JSON stdout.

    Params are passed as PowerShell named parameters, e.g.
        run_pwsh_script("Get-DiskUsage.ps1", ComputerName="HOMELAB-DC01")
    becomes:
        pwsh -File Get-DiskUsage.ps1 -ComputerName HOMELAB-DC01
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


async def run_ssh_bash_script(
    script_name: str,
    host: str,
    user: str = "pi",
    args: list[str] | None = None,
    ssh_key_path: str | None = None,
) -> dict:
    """Run a Bash script on a remote Linux host over SSH and parse its JSON stdout.

    The script's contents are piped into `ssh user@host bash -s -- <args>`
    rather than copied over first, so nothing needs to be pre-installed on
    the target beyond a working SSH server and bash.

    Assumes SSH key-based auth (`ssh-copy-id pi@<host>`) — no passwords are
    handled here; BatchMode=yes is set to fail fast rather than hang.
    """
    script_path = PI_SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"error": f"Script not found: {script_name}"}

    script_contents = script_path.read_text()

    cmd = ["ssh"]
    if ssh_key_path:
        cmd += ["-i", ssh_key_path]
    cmd += [
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        # StrictHostKeyChecking=no: skip known_hosts verification.
        # Safe on a private home network where the container has no known_hosts file.
        "-o", "StrictHostKeyChecking=no",
        f"{user}@{host}",
        "bash", "-s", "--",
    ]
    cmd += args or []

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=script_contents.encode()), timeout=20
        )
    except FileNotFoundError:
        return {"error": "ssh not found on PATH."}
    except asyncio.TimeoutError:
        return {"error": f"SSH to {host} timed out after 20s"}

    if proc.returncode != 0:
        return {
            "error": f"{script_name} on {host} exited {proc.returncode}",
            "stderr": stderr.decode(errors="replace").strip(),
        }

    raw = stdout.decode(errors="replace").strip()
    if not raw:
        return {"error": f"{script_name} on {host} produced no output"}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "Failed to parse script output as JSON", "raw": raw}
