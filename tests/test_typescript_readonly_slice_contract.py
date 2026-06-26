from __future__ import annotations

import base64
from datetime import datetime
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
NODE_CANDIDATES = [
    PROJECT_ROOT / ".task-temp" / "typescript-backend-sqlite-migration-spike-20260625" / "node-v22.12.0-win-x64" / "node.exe",
    PROJECT_ROOT.parent / ".task-temp" / "typescript-backend-sqlite-migration-spike-20260625" / "node-v22.12.0-win-x64" / "node.exe",
]


def _to_json(url: str, headers: dict[str, str] | None = None):
    try:
        request = Request(url, headers=headers or {})
        with urlopen(request) as response:
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
    env["CPW_DB_PATH"] = str(PROJECT_ROOT / ".local" / "typescript-fixture.sqlite3")
    env["PLAYER_WIKI_VERSION"] = "test-version"
    env["PLAYER_WIKI_BUILD_ID"] = "test-build"
    env["PLAYER_WIKI_GIT_SHA"] = "test-git-sha"
    env["PLAYER_WIKI_GIT_DIRTY"] = "0"
    env["PLAYER_WIKI_RUNTIME"] = "test-runtime"
    env["PLAYER_WIKI_INSTANCE_NAME"] = "test-instance"
    env["PLAYER_WIKI_BASE_URL"] = "http://127.0.0.1:5000"

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


def test_typescript_app_state_matches_flask_metadata_contract(typescript_api_server, client):
    flask_response = client.get("/api/v1/app")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(f"{typescript_api_server}/api/v1/app")
    assert status == 200

    assert payload["ok"] is True
    for key in (
        "version",
        "build_id",
        "git_sha",
        "git_dirty",
        "runtime",
        "instance_name",
        "environment",
        "base_url",
    ):
        assert payload["app"][key] == flask_payload["app"][key]
    assert payload["app"]["campaigns_dir"] == str(PROJECT_ROOT / "tests" / "fixtures" / "sample_campaigns")
    assert payload["app"]["db_path"].endswith("typescript-fixture.sqlite3")


def test_typescript_campaign_list_matches_flask_campaign_payloads(typescript_api_server, client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/campaigns")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns")
    assert status == 200

    assert payload["ok"] is True
    assert payload["auth"]["mode"] == "fixture_read_only"
    assert isinstance(payload["campaigns"], list)
    assert [entry["campaign"] for entry in payload["campaigns"]] == [
        entry["campaign"] for entry in flask_payload["campaigns"]
    ]
    assert {entry["role"] for entry in payload["campaigns"]} == {"fixture_reader"}


def test_typescript_campaign_help_matches_flask_public_contract(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/help")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/help")
    assert status == 200

    assert payload["ok"] is True
    assert payload["campaign"] == flask_payload["campaign"]
    for key in (
        "viewer_role_label",
        "viewer_role_summary",
        "campaign_system_label",
        "is_authenticated",
        "available_surface_labels",
        "cross_cutting_limits",
        "visibility_rows",
        "surfaces",
        "account_note",
        "links",
    ):
        assert payload[key] == flask_payload[key]


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


def _content_page_record_summary(page):
    return {
        "page_ref": page["page_ref"],
        "relative_path": page["relative_path"],
        "metadata": page["metadata"],
        "page": {key: page["page"][key] for key in (
            "title",
            "route_slug",
            "section",
            "subsection",
            "page_type",
            "display_order",
            "published",
            "aliases",
            "summary",
            "image_path",
            "image_alt",
            "image_caption",
            "reveal_after_session",
            "source_ref",
            "is_pinned",
            "is_visible",
        )},
    }


def _content_asset_record_summary(asset):
    return {
        key: asset[key]
        for key in (
            "asset_ref",
            "relative_path",
            "size_bytes",
            "media_type",
            "url",
        )
    }


def _content_character_summary(character):
    return {
        key: character[key]
        for key in (
            "character_slug",
            "name",
            "status",
            "import_status",
        )
    }


def _content_page_removal_summary(page):
    return {
        "can_hard_delete": page["can_hard_delete"],
        "hard_delete_blockers": page["hard_delete_blockers"],
        "removal_status_label": page["removal_status_label"],
        "removal_guidance": page["removal_guidance"],
        "removal_safety": {
            "can_hard_delete": page["removal_safety"]["can_hard_delete"],
            "blockers_by_type": page["removal_safety"]["blockers_by_type"],
            "samples": page["removal_safety"]["samples"],
            "hard_delete_blockers": page["removal_safety"]["hard_delete_blockers"],
            "page_title": page["removal_safety"]["page_title"],
            "removal_status_label": page["removal_safety"]["removal_status_label"],
            "removal_guidance": page["removal_safety"]["removal_guidance"],
        },
    }


def _normalize_timestamp(value: str) -> None:
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_typescript_content_pages_list_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/content/pages")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/pages")
    assert status == 200

    assert payload["ok"] is True
    assert isinstance(payload["pages"], list)
    assert isinstance(flask_payload["pages"], list)
    assert len(payload["pages"]) == len(flask_payload["pages"]) == 29
    assert [page["page_ref"] for page in payload["pages"]] == [page["page_ref"] for page in flask_payload["pages"]]

    for flask_page, ts_page in zip(flask_payload["pages"], payload["pages"]):
        assert "body_markdown" not in ts_page
        ts_summary = _content_page_record_summary(ts_page)
        flask_summary = _content_page_record_summary(flask_page)
        assert ts_summary == flask_summary
        assert isinstance(ts_page["updated_at"], str) and ts_page["updated_at"]
        _normalize_timestamp(ts_page["updated_at"])

    sample_ref = "locations/port-meridian"
    flask_sample = next(page for page in flask_payload["pages"] if page["page_ref"] == sample_ref)
    ts_sample = next(page for page in payload["pages"] if page["page_ref"] == sample_ref)
    assert _content_page_record_summary(ts_sample) == _content_page_record_summary(flask_sample)
    assert ts_sample["can_hard_delete"] is True
    assert ts_sample["hard_delete_blockers"] == []
    assert ts_sample["removal_status_label"] == "Hard delete available"
    assert ts_sample["removal_guidance"] == "Hard delete is available after confirmation."
    assert _content_page_removal_summary(ts_sample) == _content_page_removal_summary(flask_sample)


def test_typescript_content_page_detail_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    target_page_ref = "locations/port-meridian"
    flask_response = client.get(f"/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}"
    )
    assert status == 200

    assert payload["ok"] is True
    flask_page_file = flask_payload["page_file"]
    ts_page_file = payload["page_file"]
    assert _content_page_record_summary(ts_page_file) == _content_page_record_summary(flask_page_file)
    assert _content_page_removal_summary(ts_page_file) == _content_page_removal_summary(flask_page_file)
    assert "body_markdown" in ts_page_file and isinstance(ts_page_file["body_markdown"], str)
    assert ts_page_file["body_markdown"].strip()
    assert isinstance(ts_page_file["updated_at"], str) and ts_page_file["updated_at"]
    _normalize_timestamp(ts_page_file["updated_at"])


def test_typescript_content_assets_list_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/content/assets")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/assets")
    assert status == 200

    assert payload["ok"] is True
    assert isinstance(payload["assets"], list)
    assert isinstance(flask_payload["assets"], list)
    assert len(payload["assets"]) == len(flask_payload["assets"]) == 2
    assert [asset["asset_ref"] for asset in payload["assets"]] == [
        asset["asset_ref"] for asset in flask_payload["assets"]
    ]

    for flask_asset, ts_asset in zip(flask_payload["assets"], payload["assets"]):
        assert "data_base64" not in ts_asset
        assert _content_asset_record_summary(ts_asset) == _content_asset_record_summary(flask_asset)
        assert isinstance(ts_asset["updated_at"], str) and ts_asset["updated_at"]
        _normalize_timestamp(ts_asset["updated_at"])


def test_typescript_content_asset_detail_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    target_asset_ref = "npcs/captain-lyra-vale.png"
    flask_response = client.get(f"/api/v1/campaigns/linden-pass/content/assets/{target_asset_ref}")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/assets/{target_asset_ref}"
    )
    assert status == 200

    assert payload["ok"] is True
    flask_asset_file = flask_payload["asset_file"]
    ts_asset_file = payload["asset_file"]
    assert _content_asset_record_summary(ts_asset_file) == _content_asset_record_summary(flask_asset_file)
    assert ts_asset_file["data_base64"] == flask_asset_file["data_base64"]
    assert len(base64.b64decode(ts_asset_file["data_base64"])) == ts_asset_file["size_bytes"]
    assert isinstance(ts_asset_file["updated_at"], str) and ts_asset_file["updated_at"]
    _normalize_timestamp(ts_asset_file["updated_at"])


def test_typescript_content_characters_list_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/content/characters")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/characters")
    assert status == 200

    assert payload["ok"] is True
    assert isinstance(payload["characters"], list)
    assert isinstance(flask_payload["characters"], list)
    assert len(payload["characters"]) == len(flask_payload["characters"]) == 3
    assert [character["character_slug"] for character in payload["characters"]] == [
        character["character_slug"] for character in flask_payload["characters"]
    ]

    for flask_character, ts_character in zip(flask_payload["characters"], payload["characters"]):
        assert _content_character_summary(ts_character) == _content_character_summary(flask_character)
        assert isinstance(ts_character["updated_at"], str) and ts_character["updated_at"]
        _normalize_timestamp(ts_character["updated_at"])


def test_typescript_content_character_detail_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    target_character_slug = "arden-march"
    flask_response = client.get(f"/api/v1/campaigns/linden-pass/content/characters/{target_character_slug}")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/characters/{target_character_slug}"
    )
    assert status == 200

    assert payload["ok"] is True
    flask_character_file = flask_payload["character_file"]
    ts_character_file = payload["character_file"]
    assert ts_character_file["character_slug"] == flask_character_file["character_slug"]
    assert ts_character_file["definition"] == flask_character_file["definition"]
    assert ts_character_file["import_metadata"] == flask_character_file["import_metadata"]
    assert ts_character_file["state_created"] == flask_character_file["state_created"] is False
    assert isinstance(ts_character_file["updated_at"], str) and ts_character_file["updated_at"]
    _normalize_timestamp(ts_character_file["updated_at"])


def test_typescript_session_matches_flask_contract_readonly_fixture(typescript_api_server, client, users, sign_in):
    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/session")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/session")
    assert status == 200

    assert payload["ok"] is True
    assert payload["campaign"] == flask_payload["campaign"]
    assert payload["active_session"] == flask_payload["active_session"]
    assert payload["messages"] == flask_payload["messages"]
    assert payload["show_session_dm_passive_scores"] == flask_payload["show_session_dm_passive_scores"]
    assert isinstance(payload["session_revision"], int)
    assert payload["session_revision"] >= 0
    assert isinstance(payload["session_view_token"], str)
    assert len(payload["session_view_token"]) == 12
    assert re.fullmatch(r"[0-9a-f]{12}", payload["session_view_token"], flags=re.IGNORECASE) is not None

    assert "staged_articles" not in payload
    assert "revealed_articles" not in payload
    assert "session_logs" not in payload
    assert "session_dm_passive_scores" not in payload

    short_status, short_payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/session",
        headers={
            "X-Live-Revision": str(payload["session_revision"]),
            "X-Live-View-Token": payload["session_view_token"],
        },
    )
    assert short_status == 200
    assert short_payload == {
        "ok": True,
        "changed": False,
        "session_revision": payload["session_revision"],
        "session_view_token": payload["session_view_token"],
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


def test_typescript_content_config_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/content/config")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/config")
    assert status == 200

    assert payload["ok"] is True
    assert payload["config_file"]["campaign_slug"] == flask_payload["config_file"]["campaign_slug"]
    assert payload["config_file"]["config"] == flask_payload["config_file"]["config"]
    assert payload["config_file"]["editable_fields"] == flask_payload["config_file"]["editable_fields"]

    updated_at = payload["config_file"]["updated_at"]
    assert isinstance(updated_at, str)
    assert updated_at
    try:
        datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssertionError(f"Expected ISO timestamp from TypeScript content config, got {updated_at}") from exc


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

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/session")
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/help")
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/content/config"
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/pages/definitely-not-a-page"
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "content_page_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/content/assets"
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/assets/definitely-not-an-asset.png"
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "content_asset_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/content/characters"
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/characters/missing-character"
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "content_character_not_found"
