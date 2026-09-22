"""Boot the real app in a subprocess, then talk to it over HTTP and through the MCP stdio bridge."""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from argus.port import free_port

ROOT = Path(__file__).resolve().parent.parent


def wait_health(url: str, process: subprocess.Popen, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"app exited early with code {process.returncode}")
        try:
            if httpx.get(f"{url}/api/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise AssertionError("app did not become healthy")


@pytest.fixture
def app_process(tmp_path):
    port = free_port()
    data_dir = tmp_path / "data"
    env = {
        **os.environ,
        "ARGUS_DATA_DIR": str(data_dir),
        "ARGUS_PORT": str(port),
        "PORT_STRICT": "1",
        "ARGUS_CAPTURE": "fake",
        "ARGUS_WINDOW": "fake",
        "PYTHONUNBUFFERED": "1",
    }
    process = subprocess.Popen([sys.executable, "-m", "argus"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        wait_health(url, process)
        yield url, data_dir, env
    finally:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()


def test_subprocess_http_and_mcp_bridge(app_process):
    url, data_dir, env = app_process
    health = httpx.get(f"{url}/api/health").json()
    assert health["service"] == "argus-hoard" and health["dataDirConfigured"] is True
    tools = httpx.get(f"{url}/api/agent/tools").json()["tools"]
    assert [t["name"] for t in tools][:2] == ["screen_status", "screen_search"]

    token = (data_dir / "mcp-token").read_text().strip()
    assert len(token) == 64
    assert httpx.post(f"{url}/api/agent/call", json={"name": "screen_status"}).status_code == 401
    status = httpx.post(f"{url}/api/agent/call", json={"name": "screen_status"}, headers={"Authorization": f"Bearer {token}"}).json()
    assert status["state"] == "watching" and status["capture_backend"] == "fake"

    # the recorder thread is live with the fake backend: frames appear on their own
    deadline = time.time() + 30
    while time.time() < deadline:
        if httpx.get(f"{url}/api/status").json()["frames_total"] >= 1:
            break
        time.sleep(0.5)
    assert httpx.get(f"{url}/api/status").json()["frames_total"] >= 1

    async def through_mcp():
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "mcp_server.py")],
            env={**env, "ARGUS_URL": url, "ARGUS_TOKEN_FILE": str(data_dir / "mcp-token")},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert "screen_recent" in (init.instructions or "")
                listed = await session.list_tools()
                names = [t.name for t in listed.tools]
                assert names == [t["name"] for t in tools]
                destructive = next(t for t in listed.tools if t.name == "screen_delete_range")
                assert destructive.annotations.destructiveHint is True
                result = await session.call_tool("screen_status", {})
                payload = json.loads(result.content[0].text)
                assert payload["state"] == "watching"
                days = json.loads((await session.call_tool("screen_days", {})).content[0].text)
                assert "days" in days
                bad = json.loads((await session.call_tool("screen_frame_text", {"id": 999999})).content[0].text)
                assert "error" in bad

    asyncio.run(through_mcp())
