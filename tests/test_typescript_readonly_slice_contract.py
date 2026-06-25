from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
NODE_CANDIDATES = [
    PROJECT_ROOT / ".task-temp" / "typescript-backend-sqlite-migration-spike-20260625" / "node-v22.12.0-win-x64" / "node.exe",
    PROJECT_ROOT.parent / ".task-temp" / "typescript-backend-sqlite-migration-spike-20260625" / "node-v22.12.0-win-x64" / "node.exe",
]


def _to_json(url: str):
    with urlopen(url) as response:
        return response.getcode(), __import__("json").loads(response.read().decode("utf-8"))


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _find_local_node_bin() -> Path:
    explicit_node = os.getenv("CPW_NODE_BIN", "").strip()
    if explicit_node:
        candidate = Path(explicit_node)
        if candidate.is_file():
            return candidate
    for candidate in NODE_CANDIDATES:
        if candidate.is_file():
            return candidate
    path_node = shutil.which("node")
    if path_node:
        return Path(path_node)
    pytest.skip("No Node runtime found for TypeScript API slice contract test.")


def _find_npm_bin(node_bin: Path) -> str:
    explicit_npm = os.getenv("CPW_NPM_BIN", "").strip()
    if explicit_npm and Path(explicit_npm).is_file():
        return explicit_npm
    for candidate in (node_bin.parent / "npm.cmd", node_bin.parent / "npm"):
        if candidate.is_file():
            return str(candidate)
    path_npm = shutil.which("npm")
    if path_npm:
        return path_npm
    pytest.skip("No npm runtime found for TypeScript API slice contract test.")


def _run_npm_command(node_bin: Path, command: list[str]) -> None:
    subprocess.run([_find_npm_bin(node_bin), *command], cwd=API_ROOT, check=True)


@pytest.fixture(scope="module")
def typescript_api_server():
    node_bin = _find_local_node_bin()
    _run_npm_command(node_bin, ["run", "build"])

    port = _find_free_port()
    env = os.environ.copy()
    env["NODE_ENV"] = "test"
    env["PORT"] = str(port)
    env["CPW_CAMPAIGNS_DIR"] = str(PROJECT_ROOT / "tests" / "fixtures" / "sample_campaigns")

    process = subprocess.Popen(
        [str(node_bin), str(API_ROOT / "dist" / "server.js")],
        cwd=API_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(120):
            try:
                status, payload = _to_json(f"{url}/healthz")
            except URLError:
                pass
            else:
                if status == 200 and payload.get("status") == "ok":
                    yield url
                    return
            if process.poll() is not None:
                raise RuntimeError("TypeScript API process exited before becoming ready.")
            import time

            time.sleep(0.05)
        raise RuntimeError("TypeScript API did not become ready within timeout.")
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_typescript_campaign_detail_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass")
    assert status == 200

    assert payload["ok"] is True
    assert payload["auth_source"] == "fixture"
    assert payload["permissions"]["can_manage_dm_content"] is False
    assert payload["campaign"] == flask_payload["campaign"]
