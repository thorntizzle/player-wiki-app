from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.error import HTTPError
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
    try:
        with urlopen(url) as response:
            return response.getcode(), __import__("json").loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, __import__("json").loads(exc.read().decode("utf-8"))


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
    env = os.environ.copy()
    env["PATH"] = f"{node_bin.parent}{os.pathsep}{env.get('PATH', '')}"
    subprocess.run([_find_npm_bin(node_bin), *command], cwd=API_ROOT, check=True, env=env)


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


def _section_summary(payload):
    return [
        (section["section_name"], section["section_slug"], section["page_count"])
        for section in payload["section_navigation"]
    ]


def _page_summary(page):
    return {
        key: page[key]
        for key in (
            "page_ref",
            "title",
            "route_slug",
            "href",
            "section",
            "section_slug",
            "section_href",
            "subsection",
            "page_type",
            "display_type",
            "summary",
            "display_order",
            "reveal_after_session",
            "is_pinned",
        )
    }


def test_typescript_wiki_home_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/wiki")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/wiki")
    assert status == 200

    assert payload["ok"] is True
    assert payload["campaign"] == flask_payload["campaign"]
    assert payload["frontend_mode"] == flask_payload["frontend_mode"]
    assert payload["can_view_wiki"] == flask_payload["can_view_wiki"]
    assert payload["wiki_visibility_label"] == flask_payload["wiki_visibility_label"]
    assert payload["query"] == flask_payload["query"]
    assert payload["result_count"] == flask_payload["result_count"]
    assert payload["overview_page"] == flask_payload["overview_page"]
    assert _section_summary(payload) == _section_summary(flask_payload)
    assert _page_summary(payload["latest_session_summary"]) == _page_summary(
        flask_payload["latest_session_summary"]
    )


def test_typescript_wiki_section_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/wiki/sections/locations")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/wiki/sections/locations")
    assert status == 200

    assert payload["ok"] is True
    assert payload["campaign"] == flask_payload["campaign"]
    assert payload["frontend_mode"] == flask_payload["frontend_mode"]
    assert payload["section_name"] == flask_payload["section_name"]
    assert payload["section_slug"] == flask_payload["section_slug"]
    assert payload["page_count"] == flask_payload["page_count"]
    assert payload["show_subsections"] == flask_payload["show_subsections"]
    assert [_page_summary(page) for page in payload["pages"]] == [
        _page_summary(page) for page in flask_payload["pages"]
    ]
    assert _section_summary(payload) == _section_summary(flask_payload)


def test_typescript_wiki_page_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale"
    )
    assert status == 200

    assert payload["ok"] is True
    assert payload["campaign"] == flask_payload["campaign"]
    assert payload["frontend_mode"] == flask_payload["frontend_mode"]
    assert _page_summary(payload["page"]) == _page_summary(flask_payload["page"])
    assert payload["page"]["body_html"] == flask_payload["page"]["body_html"]
    assert payload["page"]["image"] == flask_payload["page"]["image"]
    assert [_page_summary(page) for page in payload["backlinks"]] == [
        _page_summary(page) for page in flask_payload["backlinks"]
    ]
    assert _section_summary(payload) == _section_summary(flask_payload)


def test_typescript_wiki_missing_resources_return_json(typescript_api_server):
    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/wiki")
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/wiki/sections/definitely-not-a-section"
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "wiki_section_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/wiki/pages/definitely-not-a-page"
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "wiki_page_not_found"
