#!/usr/bin/env python3
"""Generates steady serial load against the MCP server so Prometheus has
something to measure.

Counterpart to home-lab-gitops/scripts/baseline-load.sh, which does the same job
for the Qwen predictor. Re-run this unchanged during chaos experiments -- a
baseline is only comparable if the load that produced it is identical.

Unlike the Qwen script this cannot be curl: MCP is a session-based protocol, so
the client has to initialise a session before any tool can be invoked.
"""

import argparse
import asyncio
import time

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

DEFAULT_URL = "http://192.168.0.38:30081/mcp"


async def run(url: str, duration: int, subnet: str, start: int, end: int) -> None:
    # scan_network is the only tool with no external dependency -- it shells out
    # to pwsh inside the pod. The Windows and Pi tools need WinRM/SSH to hosts
    # that may be unreachable, which would make failures ambiguous during a
    # chaos experiment.
    args = {"subnet": subnet, "start_host": start, "end_host": end}

    deadline = time.monotonic() + duration
    ok = fail = 0

    print(f"Load against {url}")
    print(f"Duration {duration}s, tool scan_network {subnet}.{start}-{end}, serial")
    print(f"Started {time.strftime('%H:%M:%S')} -- note this, you need it to read the graphs\n")

    # trust_env=False ignores ALL_PROXY/HTTPS_PROXY. On a corporate laptop those
    # point at a SOCKS proxy that cannot reach the home LAN.
    http_client = httpx2.AsyncClient(trust_env=False, timeout=120)

    async with http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                while time.monotonic() < deadline:
                    try:
                        await session.call_tool("scan_network", args)
                        ok += 1
                    except Exception as exc:
                        fail += 1
                        if fail == 1:
                            print(f"first failure: {type(exc).__name__}: {exc}")
                    remaining = int(deadline - time.monotonic())
                    print(f"\rok={ok} fail={fail} remaining={remaining}s ", end="", flush=True)

    print(f"\n\nFinished {time.strftime('%H:%M:%S')}")
    print(f"Completed {ok}, failed {fail}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--duration", type=int, default=300)
    p.add_argument("--subnet", default="192.168.0")
    p.add_argument("--start-host", type=int, default=1)
    # A narrow range keeps each call a few seconds rather than a few minutes,
    # so a 5 minute run produces enough samples for a percentile to mean anything.
    p.add_argument("--end-host", type=int, default=10)
    a = p.parse_args()

    asyncio.run(run(a.url, a.duration, a.subnet, a.start_host, a.end_host))


if __name__ == "__main__":
    main()
