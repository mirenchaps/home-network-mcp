"""
tests/test_homebridge.py

Unit tests for homebridge.py.

All tests mock httpx.AsyncClient so they run without a real Homebridge
instance and fail for code-logic reasons, not network availability.

Run with: pytest tests/ -v
Docs: https://docs.pytest.org  /  https://pytest-asyncio.readthedocs.io
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import homebridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int = 200, json_data=None, text: str = ""):
    """Build a fake httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data or {})
    resp.text = text
    if status_code >= 400:
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                f"HTTP {status_code}", request=MagicMock(), response=resp
            )
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


def _mock_client(responses: list):
    """
    Return a context-manager mock for httpx.AsyncClient whose request()
    method returns each response in `responses` in order.
    """
    client = AsyncMock()
    client.post = AsyncMock(side_effect=responses[:1])
    client.request = AsyncMock(side_effect=responses)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Token acquisition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_token_sets_module_token():
    """_get_token() should POST to /api/auth/login and cache the token."""
    homebridge._token = None

    login_resp = _mock_response(200, {"access_token": "tok-abc"})
    client = AsyncMock()
    client.post = AsyncMock(return_value=login_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {
        "HOMEBRIDGE_HOST": "192.168.0.113",
        "HOMEBRIDGE_USERNAME": "admin",
        "HOMEBRIDGE_PASSWORD": "secret",
    }):
        with patch("homebridge.httpx.AsyncClient", return_value=client):
            token = await homebridge._get_token()

    assert token == "tok-abc"
    assert homebridge._token == "tok-abc"


@pytest.mark.asyncio
async def test_missing_host_returns_error():
    """list_accessories() should return an error dict when HOMEBRIDGE_HOST is unset."""
    homebridge._token = None
    with patch.dict("os.environ", {}, clear=True):
        result = await homebridge.list_accessories()
    assert "error" in result
    assert "HOMEBRIDGE_HOST" in result["error"]


# ---------------------------------------------------------------------------
# list_accessories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_accessories_success():
    """list_accessories() returns {"accessories": [...]} on a 200 response."""
    homebridge._token = "tok-abc"
    accessories = [{"uniqueId": "aaa", "serviceName": "Bedroom Fan"}]
    resp = _mock_response(200, accessories)

    client = AsyncMock()
    client.request = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"HOMEBRIDGE_HOST": "192.168.0.113"}):
        with patch("homebridge.httpx.AsyncClient", return_value=client):
            result = await homebridge.list_accessories()

    assert result == {"accessories": accessories}


@pytest.mark.asyncio
async def test_list_accessories_connection_error():
    """A network error should return {"error": "..."} rather than raising."""
    homebridge._token = "tok-abc"

    client = AsyncMock()
    client.request = AsyncMock(
        side_effect=httpx.RequestError("connection refused", request=MagicMock())
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"HOMEBRIDGE_HOST": "192.168.0.113"}):
        with patch("homebridge.httpx.AsyncClient", return_value=client):
            result = await homebridge.list_accessories()

    assert "error" in result
    assert "connection refused" in result["error"]


# ---------------------------------------------------------------------------
# set_accessory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_accessory_sends_correct_body():
    """set_accessory() should PUT with characteristicType and value in the body."""
    homebridge._token = "tok-abc"
    updated = {"uniqueId": "aaa", "values": {"On": True}}
    resp = _mock_response(200, updated)

    client = AsyncMock()
    client.request = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"HOMEBRIDGE_HOST": "192.168.0.113"}):
        with patch("homebridge.httpx.AsyncClient", return_value=client):
            result = await homebridge.set_accessory("aaa", "On", "true")

    client.request.assert_called_once_with(
        "PUT",
        "http://192.168.0.113:8581/api/accessories/aaa",
        headers={"Authorization": "Bearer tok-abc"},
        json={"characteristicType": "On", "value": "true"},
    )
    assert result == updated


# ---------------------------------------------------------------------------
# 401 → re-auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_retries_on_401():
    """A 401 response should trigger a token refresh and retry the request."""
    homebridge._token = "tok-old"

    stale_resp = _mock_response(401, text="Unauthorized")
    stale_resp.raise_for_status = MagicMock()  # don't raise on 401 — _request checks status_code
    stale_resp.status_code = 401

    fresh_resp = _mock_response(200, [])

    # First call returns 401; after re-auth the second call returns 200.
    client = AsyncMock()
    client.request = AsyncMock(side_effect=[stale_resp, fresh_resp])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    login_resp = _mock_response(200, {"access_token": "tok-new"})
    login_client = AsyncMock()
    login_client.post = AsyncMock(return_value=login_resp)
    login_client.__aenter__ = AsyncMock(return_value=login_client)
    login_client.__aexit__ = AsyncMock(return_value=False)

    call_count = 0

    def client_factory(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # First AsyncClient instantiation is for the initial request (returns 401 + retry).
        # Second is for _get_token's login POST.
        if call_count == 2:
            return login_client
        return client

    with patch.dict("os.environ", {
        "HOMEBRIDGE_HOST": "192.168.0.113",
        "HOMEBRIDGE_USERNAME": "admin",
        "HOMEBRIDGE_PASSWORD": "secret",
    }):
        with patch("homebridge.httpx.AsyncClient", side_effect=client_factory):
            resp = await homebridge._request("GET", "/api/accessories")

    assert homebridge._token == "tok-new"
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# get_homebridge_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_homebridge_status_combines_both_endpoints():
    """get_homebridge_status() should call both /status/homebridge endpoints."""
    homebridge._token = "tok-abc"

    status_data = {"status": "up"}
    bridges_data = [{"name": "child-bridge-1", "status": "ok"}]

    status_resp = _mock_response(200, status_data)
    bridges_resp = _mock_response(200, bridges_data)

    client = AsyncMock()
    client.request = AsyncMock(side_effect=[status_resp, bridges_resp])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"HOMEBRIDGE_HOST": "192.168.0.113"}):
        with patch("homebridge.httpx.AsyncClient", return_value=client):
            result = await homebridge.get_homebridge_status()

    assert result["status"] == status_data
    assert result["child_bridges"] == bridges_data
