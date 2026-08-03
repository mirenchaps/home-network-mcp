"""
homebridge.py

Async HTTP client for the Homebridge REST API.

All Homebridge API logic lives here — server.py imports and calls these
functions directly. Credentials are read from environment variables:

    HOMEBRIDGE_HOST       hostname or IP of the Homebridge instance (no port)
    HOMEBRIDGE_USERNAME   Homebridge UI username
    HOMEBRIDGE_PASSWORD   Homebridge UI password

The API uses JWT bearer tokens obtained via POST /api/auth/login. Tokens
are cached in a module-level variable and refreshed automatically on 401.

Homebridge API reference: http://<host>:8581/swagger
"""

import os
import logging

import httpx

log = logging.getLogger(__name__)

HOMEBRIDGE_PORT = 8581

# The /api/accessories endpoint polls the live HAP bridge state for every
# accessory, which can take 30-60s on a Pi with multiple plugins. Other
# endpoints (auth, plugins, status) are fast and use the short timeout.
_TIMEOUT_FAST = 10   # seconds — auth, plugins, status
_TIMEOUT_ACCESSORIES = 60   # seconds — accessories (live HAP poll)

# Module-level token cache — persists for the lifetime of the process.
# Re-acquired automatically if a request returns 401.
_token: str | None = None


def _base_url() -> str:
    host = os.environ.get("HOMEBRIDGE_HOST", "")
    if not host:
        raise ValueError(
            "HOMEBRIDGE_HOST environment variable is not set. "
            "Set it to the hostname or IP of your Homebridge instance."
        )
    return f"http://{host}:{HOMEBRIDGE_PORT}"


async def _get_token() -> str:
    """Obtain a fresh JWT token from Homebridge and cache it."""
    global _token
    username = os.environ.get("HOMEBRIDGE_USERNAME", "")
    password = os.environ.get("HOMEBRIDGE_PASSWORD", "")
    if not username or not password:
        raise ValueError(
            "HOMEBRIDGE_USERNAME and HOMEBRIDGE_PASSWORD must both be set."
        )
    async with httpx.AsyncClient(timeout=_TIMEOUT_FAST) as client:
        resp = await client.post(
            f"{_base_url()}/api/auth/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        _token = resp.json()["access_token"]
        return _token


async def _request(method: str, path: str, timeout: int = _TIMEOUT_FAST, **kwargs) -> httpx.Response:
    """Make an authenticated request, refreshing the token once on 401."""
    global _token
    # Validate host first so the error message is clear regardless of token state
    _base_url()
    if _token is None:
        await _get_token()

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(
            method,
            f"{_base_url()}{path}",
            headers={"Authorization": f"Bearer {_token}"},
            **kwargs,
        )
        if resp.status_code == 401:
            # Token expired — refresh once and retry
            log.info("Homebridge token expired, re-authenticating")
            await _get_token()
            resp = await client.request(
                method,
                f"{_base_url()}{path}",
                headers={"Authorization": f"Bearer {_token}"},
                **kwargs,
            )
        return resp


async def list_accessories() -> dict:
    """Return all Homebridge accessories and their current characteristic values.

    Each accessory includes its uniqueId, name, type, and a list of
    characteristics (e.g. On, Brightness, ColorTemperature) with current values.

    Note: this endpoint polls the live HAP bridge state and can take up to 60s.
    """
    try:
        resp = await _request("GET", "/api/accessories", timeout=_TIMEOUT_ACCESSORIES)
        resp.raise_for_status()
        return {"accessories": resp.json()}
    except ValueError as exc:
        return {"error": str(exc)}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Homebridge API error {exc.response.status_code}: {exc.response.text}"}
    except httpx.RequestError as exc:
        return {"error": f"Could not reach Homebridge: {exc}"}


async def get_accessory(unique_id: str) -> dict:
    """Return a single accessory with refreshed characteristic values.

    Args:
        unique_id: The accessory's uniqueId from list_accessories.

    Note: this endpoint polls the live HAP bridge state and can take up to 60s.
    """
    try:
        resp = await _request("GET", f"/api/accessories/{unique_id}", timeout=_TIMEOUT_ACCESSORIES)
        resp.raise_for_status()
        return resp.json()
    except ValueError as exc:
        return {"error": str(exc)}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Homebridge API error {exc.response.status_code}: {exc.response.text}"}
    except httpx.RequestError as exc:
        return {"error": f"Could not reach Homebridge: {exc}"}


async def set_accessory(unique_id: str, characteristic_type: str, value) -> dict:
    """Set a characteristic value on an accessory.

    Args:
        unique_id: The accessory's uniqueId from list_accessories.
        characteristic_type: The characteristic to set, e.g. "On", "Brightness".
        value: The new value. Booleans for On/Off, integers for Brightness (0-100), etc.
    """
    try:
        resp = await _request(
            "PUT",
            f"/api/accessories/{unique_id}",
            json={"characteristicType": characteristic_type, "value": value},
        )
        resp.raise_for_status()
        return resp.json()
    except ValueError as exc:
        return {"error": str(exc)}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Homebridge API error {exc.response.status_code}: {exc.response.text}"}
    except httpx.RequestError as exc:
        return {"error": f"Could not reach Homebridge: {exc}"}


async def list_plugins() -> dict:
    """Return all installed Homebridge plugins with name, version, and enabled state."""
    try:
        resp = await _request("GET", "/api/plugins")
        resp.raise_for_status()
        return {"plugins": resp.json()}
    except ValueError as exc:
        return {"error": str(exc)}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Homebridge API error {exc.response.status_code}: {exc.response.text}"}
    except httpx.RequestError as exc:
        return {"error": f"Could not reach Homebridge: {exc}"}


async def get_homebridge_status() -> dict:
    """Return the current Homebridge status and any child bridge states."""
    try:
        status_resp = await _request("GET", "/api/status/homebridge")
        status_resp.raise_for_status()
        bridges_resp = await _request("GET", "/api/status/homebridge/child-bridges")
        bridges_resp.raise_for_status()
        return {
            "status": status_resp.json(),
            "child_bridges": bridges_resp.json(),
        }
    except ValueError as exc:
        return {"error": str(exc)}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Homebridge API error {exc.response.status_code}: {exc.response.text}"}
    except httpx.RequestError as exc:
        return {"error": f"Could not reach Homebridge: {exc}"}
