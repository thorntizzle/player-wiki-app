from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
import yaml

from player_wiki.auth_store import AuthStore
from player_wiki.operations import create_backup_archive, restore_backup_archive


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
NODE_CANDIDATES = [
    PROJECT_ROOT / ".task-temp" / "typescript-backend-sqlite-migration-spike-20260625" / "node-v22.12.0-win-x64" / "node.exe",
    PROJECT_ROOT.parent / ".task-temp" / "typescript-backend-sqlite-migration-spike-20260625" / "node-v22.12.0-win-x64" / "node.exe",
]
CONTENT_MANAGER_HEADERS = {"X-CPW-Fixture-Role": "dm"}
CONTENT_PLAYER_HEADERS = {"X-CPW-Fixture-Role": "player"}
TYPESCRIPT_DM_API_TOKEN = "typescript-golden-dm-token"


def _to_json(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    method: str | None = None,
    body: dict | str | None = None,
):
    request_headers = dict(headers or {})
    data = None
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    try:
        request = Request(url, data=data, headers=request_headers, method=method)
        with urlopen(request) as response:
            return response.getcode(), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _to_bytes(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    method: str | None = None,
):
    request = Request(url, headers=dict(headers or {}), method=method)
    try:
        with urlopen(request) as response:
            return response.getcode(), response.headers.get_content_type(), response.read()
    except HTTPError as exc:
        return exc.code, exc.headers.get_content_type(), exc.read()


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
def typescript_node_bin():
    node_bin = _find_local_node_bin()
    _run_npm_command(node_bin, ["run", "build"])
    return node_bin


def _launch_typescript_api(node_bin: Path, campaigns_dir: Path, db_path: Path):
    port = _find_free_port()
    env = os.environ.copy()
    env["NODE_ENV"] = "test"
    env["PORT"] = str(port)
    env["CPW_CAMPAIGNS_DIR"] = str(campaigns_dir)
    env["CPW_DB_PATH"] = str(db_path)
    env["PLAYER_WIKI_VERSION"] = "test-version"
    env["PLAYER_WIKI_BUILD_ID"] = "test-build"
    env["PLAYER_WIKI_GIT_SHA"] = "test-git-sha"
    env["PLAYER_WIKI_GIT_DIRTY"] = "0"
    env["PLAYER_WIKI_RUNTIME"] = "test-runtime"
    env["PLAYER_WIKI_INSTANCE_NAME"] = "test-instance"
    env["PLAYER_WIKI_BASE_URL"] = "http://127.0.0.1:5000"
    env["PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS"] = "300"

    process = subprocess.Popen(
        [str(node_bin), str(API_ROOT / "dist" / "server.js")],
        cwd=API_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                status, payload = _to_json(f"{url}/healthz")
            except URLError:
                pass
            else:
                if status == 200 and payload.get("status") == "ok":
                    return process, url
            if process.poll() is not None:
                raise RuntimeError("TypeScript API process exited before becoming ready.")
            import time

            time.sleep(0.05)
        raise RuntimeError("TypeScript API did not become ready within timeout.")
    except Exception:
        process.terminate()
        process.wait(timeout=5)
        raise


@pytest.fixture(scope="module")
def typescript_api_server(typescript_node_bin):
    process, url = _launch_typescript_api(
        typescript_node_bin,
        PROJECT_ROOT / "tests" / "fixtures" / "sample_campaigns",
        PROJECT_ROOT / ".local" / "typescript-fixture.sqlite3",
    )
    try:
        yield url
    finally:
        process.terminate()
        process.wait(timeout=5)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _seed_typescript_mutation_db(db_path: Path) -> None:
    now = "2026-06-25T08:00:00+00:00"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT NOT NULL UNIQUE,
              display_name TEXT NOT NULL,
              is_admin INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL,
              password_hash TEXT,
              auth_version INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE user_preferences (
              user_id INTEGER PRIMARY KEY,
              theme_key TEXT NOT NULL DEFAULT 'parchment',
              session_chat_order TEXT NOT NULL DEFAULT 'newest_first',
              frontend_mode TEXT NOT NULL DEFAULT 'gen2',
              updated_at TEXT NOT NULL
            );

            CREATE TABLE campaign_memberships (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              campaign_slug TEXT NOT NULL,
              role TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE api_tokens (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              label TEXT NOT NULL,
              token_hash TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              last_used_at TEXT NOT NULL,
              expires_at TEXT,
              revoked_at TEXT,
              created_by_user_id INTEGER
            );

            CREATE TABLE campaign_visibility_settings (
              campaign_slug TEXT NOT NULL,
              scope TEXT NOT NULL,
              visibility TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              updated_by_user_id INTEGER,
              PRIMARY KEY (campaign_slug, scope)
            );

            CREATE TABLE character_assignments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              campaign_slug TEXT NOT NULL,
              character_slug TEXT NOT NULL,
              assignment_type TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE (campaign_slug, character_slug)
            );

            CREATE TABLE auth_audit_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              actor_user_id INTEGER,
              target_user_id INTEGER,
              campaign_slug TEXT,
              character_slug TEXT,
              event_type TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE character_state (
              campaign_slug TEXT NOT NULL,
              character_slug TEXT NOT NULL,
              revision INTEGER NOT NULL,
              state_json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              updated_by_user_id INTEGER,
              PRIMARY KEY (campaign_slug, character_slug)
            );

            CREATE TABLE systems_sources (
              library_slug TEXT NOT NULL,
              source_id TEXT NOT NULL,
              title TEXT NOT NULL,
              PRIMARY KEY (library_slug, source_id)
            );

            CREATE TABLE campaign_enabled_sources (
              campaign_slug TEXT NOT NULL,
              library_slug TEXT NOT NULL,
              source_id TEXT NOT NULL,
              is_enabled INTEGER NOT NULL,
              default_visibility TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              updated_by_user_id INTEGER,
              PRIMARY KEY (campaign_slug, library_slug, source_id)
            );

            CREATE TABLE systems_entries (
              library_slug TEXT NOT NULL,
              source_id TEXT NOT NULL,
              entry_key TEXT NOT NULL,
              entry_type TEXT NOT NULL,
              slug TEXT NOT NULL,
              title TEXT NOT NULL,
              metadata_json TEXT NOT NULL DEFAULT '{}',
              body_json TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY (library_slug, entry_key)
            );

            CREATE TABLE campaign_entry_overrides (
              campaign_slug TEXT NOT NULL,
              library_slug TEXT NOT NULL,
              entry_key TEXT NOT NULL,
              is_enabled_override INTEGER,
              PRIMARY KEY (campaign_slug, library_slug, entry_key)
            );
            """
        )
        connection.execute(
            """
            INSERT INTO users (
              id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (77, "typescript-golden-dm@example.com", "TypeScript Golden DM", 0, "active", None, 1, now, now),
        )
        connection.execute(
            """
            INSERT INTO users (
              id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (79, "typescript-golden-player@example.com", "TypeScript Golden Player", 0, "active", None, 1, now, now),
        )
        connection.execute(
            "INSERT INTO user_preferences (user_id, theme_key, session_chat_order, frontend_mode, updated_at) VALUES (?, ?, ?, ?, ?)",
            (77, "parchment", "newest_first", "gen2", now),
        )
        connection.execute(
            "INSERT INTO campaign_memberships (id, user_id, campaign_slug, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (501, 77, "linden-pass", "dm", "active", now, now),
        )
        connection.execute(
            "INSERT INTO campaign_memberships (id, user_id, campaign_slug, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (502, 79, "linden-pass", "player", "active", now, now),
        )
        connection.execute(
            "INSERT INTO api_tokens (id, user_id, label, token_hash, created_at, last_used_at, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (901, 77, "TypeScript Golden DM Token", _hash_token(TYPESCRIPT_DM_API_TOKEN), now, now, None, None, None),
        )
        connection.execute(
            "INSERT INTO systems_sources (library_slug, source_id, title) VALUES (?, ?, ?)",
            ("DND-5E", "PHB", "Player's Handbook"),
        )
        connection.execute(
            "INSERT INTO campaign_enabled_sources (campaign_slug, library_slug, source_id, is_enabled, default_visibility, updated_at, updated_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("linden-pass", "DND-5E", "PHB", 1, "players", now, 77),
        )
        dnd_entries = [
            ("DND-5E", "PHB", "PHB:class:fighter", "class", "phb-fighter", "Fighter", {"hit_die": 10, "saving_throw_proficiencies": ["Strength", "Constitution"]}),
            ("DND-5E", "PHB", "PHB:race:human", "race", "phb-human", "Human", {"size": "Medium", "speed": 30, "languages": ["Common", "one extra language"]}),
            ("DND-5E", "PHB", "PHB:background:soldier", "background", "phb-soldier", "Soldier", {}),
            ("DND-5E", "PHB", "PHB:subclass:champion", "subclass", "phb-champion", "Champion", {"class_name": "Fighter", "class_source": "PHB"}),
        ]
        connection.executemany(
            "INSERT INTO systems_entries (library_slug, source_id, entry_key, entry_type, slug, title, metadata_json, body_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (library_slug, source_id, entry_key, entry_type, slug, title, json.dumps(metadata), "{}")
                for library_slug, source_id, entry_key, entry_type, slug, title, metadata in dnd_entries
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _seed_xianxia_generic_techniques(db_path: Path) -> None:
    now = "2026-06-25T09:00:00+00:00"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT OR REPLACE INTO systems_sources (library_slug, source_id, title) VALUES (?, ?, ?)",
            ("Xianxia", "XIA", "Xianxia Seed"),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO campaign_enabled_sources (
              campaign_slug, library_slug, source_id, is_enabled, default_visibility, updated_at, updated_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("linden-pass", "Xianxia", "XIA", 1, "players", now, 77),
        )
        entries = [
            (
                "XIA:martial_art:cloud-palm",
                "xia-martial-art-cloud-palm",
                "Cloud Palm",
                "martial_art",
                {
                    "martial_art_catalog_order": 5,
                    "xianxia_martial_art_style": "Open hand",
                    "xianxia_martial_art_rank_records": [
                        {
                            "rank_key": "initiate",
                            "rank_order": 0,
                            "rank_ref": "systems:xia-cloud-palm:initiate",
                            "insight_cost": 0,
                            "energy_maximum_increases": {"jing": 0, "qi": 0, "shen": 0},
                        },
                        {
                            "rank_key": "novice",
                            "rank_order": 1,
                            "rank_ref": "systems:xia-cloud-palm:novice",
                            "insight_cost": 1,
                            "energy_maximum_increases": {"jing": 1, "qi": 0, "shen": 0},
                        },
                    ],
                },
                {"xianxia_martial_art": {"style": "Open hand"}},
            ),
            (
                "XIA:generic_technique:cultivation",
                "xia-generic-technique-cultivation",
                "Cultivation",
                "generic_technique",
                {
                    "generic_technique_catalog_order": 6,
                    "generic_technique_key": "cultivation",
                    "insight_cost": 1,
                    "support_state": "supported",
                },
                {
                    "xianxia_generic_technique": {
                        "key": "cultivation",
                        "insight_cost": 1,
                        "resource_costs": ["1 Insight"],
                    }
                },
            ),
            (
                "XIA:generic_technique:qi-blast",
                "xia-generic-technique-qi-blast",
                "Qi Blast",
                "generic_technique",
                {
                    "generic_technique_catalog_order": 7,
                    "generic_technique_key": "qi_blast",
                    "insight_cost": 1,
                    "support_state": "supported",
                },
                {
                    "xianxia_generic_technique": {
                        "key": "qi_blast",
                        "insight_cost": 1,
                        "resource_costs": ["1 Qi"],
                        "range_tags": ["ranged"],
                        "effort_tags": ["magic"],
                        "reset_cadence": "scene",
                    }
                },
            ),
            (
                "XIA:generic_technique:meteor-step",
                "xia-generic-technique-meteor-step",
                "Meteor Step",
                "generic_technique",
                {
                    "generic_technique_catalog_order": 8,
                    "generic_technique_key": "meteor_step",
                    "insight_cost": 2,
                    "support_state": "supported",
                    "learnable_without_master": True,
                },
                {
                    "xianxia_generic_technique": {
                        "key": "meteor_step",
                        "insight_cost": 2,
                        "resource_costs": ["1 Qi"],
                        "range_tags": ["movement"],
                        "effort_tags": ["basic"],
                        "learnable_without_master": True,
                        "requires_master": False,
                    }
                },
            ),
            (
                "XIA:generic_technique:enhanced-flowing-dao",
                "xia-generic-technique-enhanced-flowing-dao",
                "Enhanced Flowing Dao",
                "generic_technique",
                {
                    "generic_technique_catalog_order": 9,
                    "generic_technique_key": "enhanced_flowing_dao",
                    "insight_cost": 2,
                    "support_state": "supported",
                },
                {
                    "xianxia_generic_technique": {
                        "key": "enhanced_flowing_dao",
                        "insight_cost": 2,
                        "prerequisites": ["Any Dao 1"],
                        "learnable_without_master": True,
                        "requires_master": False,
                    }
                },
            ),
        ]
        connection.executemany(
            """
            INSERT OR REPLACE INTO systems_entries (
              library_slug, source_id, entry_key, entry_type, slug, title, metadata_json, body_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Xianxia", "XIA", entry_key, entry_type, slug, title, json.dumps(metadata), json.dumps(body))
                for entry_key, slug, title, entry_type, metadata, body in entries
            ],
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture()
def typescript_api_mutation_server(tmp_path, typescript_node_bin):
    campaigns_dir = tmp_path / "typescript-campaigns"
    shutil.copytree(PROJECT_ROOT / "tests" / "fixtures" / "sample_campaigns", campaigns_dir)
    db_path = tmp_path / "typescript-player-wiki.sqlite3"
    _seed_typescript_mutation_db(db_path)

    process, url = _launch_typescript_api(typescript_node_bin, campaigns_dir, db_path)
    try:
        yield {
            "url": url,
            "campaigns_dir": campaigns_dir,
            "db_path": db_path,
            "dm_headers": {"Authorization": f"Bearer {TYPESCRIPT_DM_API_TOKEN}", "Accept": "application/json"},
        }
    finally:
        process.terminate()
        process.wait(timeout=5)


def _api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _issue_api_token(app, user_email: str, *, label: str) -> str:
    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_email(user_email)
        assert user is not None
        raw_token, _ = store.create_api_token(user.id, label=label, expires_in=timedelta(days=365))
        return raw_token


def _read_sqlite_character_state(db_path: Path, character_slug: str) -> dict | None:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT revision, state_json
            FROM character_state
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            ("linden-pass", character_slug),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return {"revision": int(row["revision"]), "state": json.loads(row["state_json"])}


def _read_sqlite_api_token_last_used(db_path: Path, token_id: int = 901) -> str:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT last_used_at FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
    finally:
        connection.close()
    assert row is not None
    return str(row[0])


def _write_sqlite_character_state(db_path: Path, character_slug: str, *, revision: int, state: dict) -> None:
    now = "2026-06-25T13:00:00+00:00"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO character_state (
              campaign_slug, character_slug, revision, state_json, updated_at, updated_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_slug, character_slug) DO UPDATE SET
              revision = excluded.revision,
              state_json = excluded.state_json,
              updated_at = excluded.updated_at,
              updated_by_user_id = excluded.updated_by_user_id
            """,
            ("linden-pass", character_slug, revision, json.dumps(state, sort_keys=True), now, 77),
        )
        connection.commit()
    finally:
        connection.close()


def _insert_sqlite_character_assignment(db_path: Path, character_slug: str) -> None:
    now = "2026-06-25T12:30:00+00:00"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO character_assignments (
              user_id, campaign_slug, character_slug, assignment_type, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (79, "linden-pass", character_slug, "owner", now, now),
        )
        connection.commit()
    finally:
        connection.close()


def _sqlite_character_assignment_count(db_path: Path, character_slug: str) -> int:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?",
            ("linden-pass", character_slug),
        ).fetchone()
    finally:
        connection.close()
    return int(row[0])


def _read_flask_character_state(app, character_slug: str) -> dict | None:
    with app.app_context():
        state_record = app.extensions["character_state_store"].get_state("linden-pass", character_slug)
    if state_record is None:
        return None
    return {"revision": state_record.revision, "state": state_record.state}


def _write_campaign_system(campaigns_dir: Path, *, system: str, systems_library: str) -> None:
    config_path = campaigns_dir / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    payload["system"] = system
    payload["systems_library"] = systems_library
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _xianxia_persistence_summary(state: dict) -> dict:
    xianxia = dict(state.get("xianxia") or {})
    return {
        "status": state.get("status"),
        "vitals": state.get("vitals"),
        "resources": state.get("resources"),
        "spell_slots": state.get("spell_slots"),
        "notes": state.get("notes"),
        "xianxia": {
            "vitals": xianxia.get("vitals"),
            "energies": xianxia.get("energies"),
            "yin_yang": xianxia.get("yin_yang"),
            "dao": xianxia.get("dao"),
            "active_stance": xianxia.get("active_stance"),
        },
    }


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


def test_typescript_me_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/me")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/me")
    assert status == 401
    assert payload == flask_payload


def test_typescript_me_fixture_auth_shell(typescript_api_server):
    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/me",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 200
    assert payload["ok"] is True
    assert payload["auth_source"] == "fixture"
    assert payload["user"]["email"] == "fixture-admin@example.com"
    assert payload["user"]["is_admin"] is True
    assert payload["memberships"][0]["campaign_slug"] == "linden-pass"
    assert payload["memberships"][0]["role"] == "dm"
    assert payload["preferences"] == {
        "theme_key": "parchment",
        "session_chat_order": "newest_first",
        "frontend_mode": "gen2",
    }
    assert payload["view_as"]["can_view_as"] is True
    assert payload["view_as"]["active_user"] is None
    assert {user["email"] for user in payload["view_as"]["user_choices"]} == {
        "fixture-player@example.com",
        "fixture-dm@example.com",
    }


def test_typescript_bearer_api_token_updates_last_used_like_flask(typescript_api_mutation_server):
    before = _read_sqlite_api_token_last_used(typescript_api_mutation_server["db_path"])

    status, payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/me",
        headers=typescript_api_mutation_server["dm_headers"],
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["auth_source"] == "api_token"
    after = _read_sqlite_api_token_last_used(typescript_api_mutation_server["db_path"])
    assert datetime.fromisoformat(after) > datetime.fromisoformat(before)


def test_typescript_me_settings_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/me/settings")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/me/settings")
    assert status == 401
    assert payload == flask_payload


def test_typescript_me_settings_fixture_shell_matches_static_flask_choices(
    typescript_api_server,
    client,
    sign_in,
    users,
):
    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/me/settings")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/me/settings",
        headers={"X-CPW-Fixture-Role": "player"},
    )
    assert status == 200
    assert payload["ok"] is True
    assert payload["user"]["email"] == "fixture-player@example.com"
    assert payload["preferences"] == {
        "theme_key": "parchment",
        "session_chat_order": "newest_first",
        "frontend_mode": "gen2",
    }
    assert payload["theme_presets"] == flask_payload["theme_presets"]
    assert payload["session_chat_order_choices"] == flask_payload["session_chat_order_choices"]
    assert "frontend_mode_choices" not in payload


def test_typescript_systems_import_runs_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/systems/import-runs")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/systems/import-runs")
    assert status == 401
    assert payload == flask_payload


def test_typescript_systems_import_run_detail_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/systems/import-runs/999999")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/systems/import-runs/999999")
    assert status == 401
    assert payload == flask_payload


def test_typescript_systems_index_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/systems")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems")
    assert status == 401
    assert payload == flask_payload


def test_typescript_systems_search_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/systems/search?q=chain")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems/search?q=chain")
    assert status == 401
    assert payload == flask_payload


def test_typescript_systems_source_list_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/systems/sources")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems/sources")
    assert status == 401
    assert payload == flask_payload


def test_typescript_systems_source_detail_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/systems/sources/PHB")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems/sources/PHB")
    assert status == 401
    assert payload == flask_payload


def test_typescript_systems_source_category_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/systems/sources/PHB/types/spell")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems/sources/PHB/types/spell")
    assert status == 401
    assert payload == flask_payload


def test_typescript_systems_entry_detail_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/systems/entries/phb-item-chain-mail")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems/entries/phb-item-chain-mail")
    assert status == 401
    assert payload == flask_payload


def test_typescript_combat_systems_monster_search_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob")
    assert status == 401
    assert payload == flask_payload


def test_typescript_combat_state_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/combat")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/combat")
    assert status == 401
    assert payload == flask_payload


def test_typescript_session_article_source_search_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt"
    )
    assert status == 401
    assert payload == flask_payload


def test_typescript_session_article_image_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/session/articles/999999/image")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/session/articles/999999/image"
    )
    assert status == 401
    assert payload == flask_payload


def test_typescript_session_log_detail_requires_auth_like_flask(typescript_api_server, client):
    flask_response = client.get("/api/v1/campaigns/linden-pass/session/logs/999999")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/session/logs/999999")
    assert status == 401
    assert payload == flask_payload


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/campaigns/linden-pass/session/articles", {"mode": "manual"}),
        ("PUT", "/api/v1/campaigns/linden-pass/session/articles/999999", {"title": "Missing"}),
        ("POST", "/api/v1/campaigns/linden-pass/session/articles/999999/reveal", None),
        ("DELETE", "/api/v1/campaigns/linden-pass/session/articles/999999", None),
        ("DELETE", "/api/v1/campaigns/linden-pass/session/articles/revealed", None),
        ("DELETE", "/api/v1/campaigns/linden-pass/session/logs/999999", None),
    ],
)
def test_typescript_session_mutations_require_auth_like_flask(
    typescript_api_server,
    client,
    method,
    path,
    body,
):
    flask_response = client.open(path, method=method, json=body)
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}{path}",
        method=method,
        body=body,
    )
    assert status == 401
    assert payload == flask_payload


def test_typescript_session_article_source_search_fixture_shell(typescript_api_server):
    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/session/article-sources/search?q=c",
        headers={"X-CPW-Fixture-Role": "dm"},
    )
    assert status == 200
    assert payload == {
        "ok": True,
        "results": [],
        "message": "Type at least 2 letters to search published wiki pages and Systems entries.",
    }

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
        headers={"X-CPW-Fixture-Role": "dm"},
    )
    assert status == 200
    assert payload["ok"] is True
    assert payload["message"] == "Found 2 matching articles."
    assert len(payload["results"]) == 2
    captain = next(result for result in payload["results"] if result["source_ref"] == "npcs/captain-lyra-vale")
    assert captain == {
        "source_ref": "npcs/captain-lyra-vale",
        "source_kind": "page",
        "title": "Captain Lyra Vale",
        "subtitle": "NPCs",
        "kind_label": "Wiki",
        "select_label": "Captain Lyra Vale - Wiki - NPCs",
    }

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
        headers={"X-CPW-Fixture-Role": "player"},
    )
    assert status == 403
    assert payload["ok"] is False
    assert payload["error"]["code"] == "forbidden"
    assert payload["error"]["message"] == "You do not have permission to manage this session."


def test_typescript_combat_state_fixture_shell(typescript_api_server):
    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/combat",
        headers={"X-CPW-Fixture-Role": "dm"},
    )
    assert status == 200
    assert payload["ok"] is True
    assert payload["changed"] is True
    assert payload["campaign"]["slug"] == "linden-pass"
    assert payload["combat_system_supported"] is True
    assert payload["live_revision"] == 0
    assert len(payload["live_view_token"]) == 12
    assert payload["tracker"] == {
        "round_number": 1,
        "current_turn_label": "",
        "has_current_turn": False,
        "combatant_count": 0,
        "combatants": [],
    }
    assert payload["selected_combatant_id"] is None
    assert payload["selected_combatant"] is None
    assert payload["selected_player_character"] is None
    assert payload["selected_player_combat_sections"] == []
    assert payload["player_character_targets"] == []
    assert payload["available_character_choices"] == [
        {
            "slug": "arden-march",
            "name": "Arden March",
            "subtitle": "Sorcerer 5",
            "initiative_bonus": "2",
        },
        {
            "slug": "selene-brook",
            "name": "Selene Brook",
            "subtitle": "Ranger 4",
            "initiative_bonus": "3",
        },
        {
            "slug": "tobin-slate",
            "name": "Tobin Slate",
            "subtitle": "Fighter 5",
            "initiative_bonus": "1",
        },
    ]
    assert payload["available_statblock_choices"] == []
    assert "Prone" in payload["combat_condition_options"]
    assert payload["poll_settings"]["active_interval_ms"] == 500
    assert payload["permissions"] == {
        "can_manage_combat": True,
        "can_access_dm_content": True,
        "can_access_systems": True,
    }

    status, unchanged = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/combat/live-state",
        headers={
            "X-CPW-Fixture-Role": "dm",
            "X-Live-Revision": str(payload["live_revision"]),
            "X-Live-View-Token": payload["live_view_token"],
        },
    )
    assert status == 200
    assert unchanged == {
        "ok": True,
        "changed": False,
        "live_revision": payload["live_revision"],
        "live_view_token": payload["live_view_token"],
    }


def test_typescript_systems_import_runs_success_shape_matches_flask(typescript_api_server):
    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/systems/import-runs",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 200
    assert set(payload) == {"ok", "import_runs"}
    assert payload["ok"] is True
    assert isinstance(payload["import_runs"], list)


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


def test_typescript_campaign_control_matches_flask_auth_and_payload_contract(typescript_api_server, client, sign_in, users):
    flask_response = client.get("/api/v1/campaigns/linden-pass/control")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/control")
    assert status == 401
    assert payload == flask_payload

    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/control")
    assert flask_response.status_code == 403
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/control",
        headers={"X-CPW-Fixture-Role": "player"},
    )
    assert status == 403
    assert payload == flask_payload

    sign_in(users["dm"]["email"], users["dm"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/control")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/control",
        headers={"X-CPW-Fixture-Role": "dm"},
    )
    assert status == 200
    assert payload == flask_payload


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


def test_typescript_content_management_auth_matches_flask_contract(typescript_api_server, client, sign_in, users):
    flask_response = client.get("/api/v1/campaigns/linden-pass/content/config")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/config")
    assert status == 401
    assert payload == flask_payload

    sign_in(users["party"]["email"], users["party"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/content/config")
    assert flask_response.status_code == 403
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/config",
        headers=CONTENT_PLAYER_HEADERS,
    )
    assert status == 403
    assert payload == flask_payload


def test_typescript_content_config_mutation_requires_auth_like_flask(typescript_api_server, client):
    body = {"config": {"summary": "Blocked without auth."}}
    flask_response = client.patch("/api/v1/campaigns/linden-pass/content/config", json=body)
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/config",
        method="PATCH",
        body=body,
    )
    assert status == 401
    assert payload == flask_payload


def test_typescript_content_asset_mutations_require_auth_like_flask(typescript_api_server, client):
    asset_ref = "notes/api-sigil.txt"
    body = {
        "asset_file": {
            "filename": "api-sigil.txt",
            "data_base64": base64.b64encode(b"blocked asset bytes").decode("ascii"),
        }
    }

    flask_response = client.put(f"/api/v1/campaigns/linden-pass/content/assets/{asset_ref}", json=body)
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/assets/{asset_ref}",
        method="PUT",
        body=body,
    )
    assert status == 401
    assert payload == flask_payload

    flask_response = client.delete(f"/api/v1/campaigns/linden-pass/content/assets/{asset_ref}")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/assets/{asset_ref}",
        method="DELETE",
    )
    assert status == 401
    assert payload == flask_payload


def test_typescript_content_page_mutations_require_auth_like_flask(typescript_api_server, client):
    page_ref = "notes/api-field-report"
    body = {
        "metadata": {
            "title": "API Field Report",
            "section": "Notes",
            "type": "note",
            "summary": "Blocked without auth.",
            "published": True,
            "reveal_after_session": 0,
        },
        "body_markdown": "Blocked page body.",
    }

    flask_response = client.put(f"/api/v1/campaigns/linden-pass/content/pages/{page_ref}", json=body)
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/pages/{page_ref}",
        method="PUT",
        body=body,
    )
    assert status == 401
    assert payload == flask_payload

    flask_response = client.delete(f"/api/v1/campaigns/linden-pass/content/pages/{page_ref}")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/pages/{page_ref}",
        method="DELETE",
    )
    assert status == 401
    assert payload == flask_payload


def test_typescript_content_character_mutations_require_auth_like_flask(typescript_api_server, client):
    character_slug = "api-scout"
    body = {
        "definition": {
            "name": "API Scout",
            "status": "active",
            "system": "DND-5E",
        }
    }

    flask_response = client.put(f"/api/v1/campaigns/linden-pass/content/characters/{character_slug}", json=body)
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        method="PUT",
        body=body,
    )
    assert status == 401
    assert payload == flask_payload

    flask_response = client.delete(f"/api/v1/campaigns/linden-pass/content/characters/{character_slug}")
    assert flask_response.status_code == 401
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        method="DELETE",
    )
    assert status == 401
    assert payload == flask_payload


def test_typescript_content_character_dnd_persistence_matches_flask_golden(
    typescript_api_mutation_server,
    client,
    app,
    users,
):
    character_slug = "api-scout-golden"
    flask_dm_token = _issue_api_token(app, users["dm"]["email"], label="dm-content-character-dnd-golden")
    flask_campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    source_character_dir = flask_campaigns_dir / "linden-pass" / "characters" / "arden-march"

    definition_payload = yaml.safe_load((source_character_dir / "definition.yaml").read_text(encoding="utf-8"))
    import_payload = yaml.safe_load((source_character_dir / "import.yaml").read_text(encoding="utf-8"))
    definition_payload["name"] = "API Scout Golden"
    definition_payload["profile"]["biography_markdown"] = "A golden parity scout prepared through the API."
    import_payload["source_path"] = "api://campaigns/linden-pass/characters/api-scout-golden"
    import_payload["parser_version"] = "api-golden"
    import_payload["import_status"] = "managed"
    if isinstance(import_payload.get("imported_at_utc"), datetime):
        import_payload["imported_at_utc"] = import_payload["imported_at_utc"].isoformat().replace("+00:00", "Z")
    body = {"definition": definition_payload, "import_metadata": import_payload}

    flask_create = client.put(
        f"/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=_api_headers(flask_dm_token),
        json=body,
    )
    assert flask_create.status_code == 200
    flask_character_file = flask_create.get_json()["character_file"]
    assert flask_character_file["state_created"] is True

    ts_status, ts_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=body,
    )
    assert ts_status == 200
    assert ts_payload["character_file"]["state_created"] is True
    assert ts_payload["character_file"]["definition"]["character_slug"] == flask_character_file["definition"]["character_slug"]
    assert ts_payload["character_file"]["definition"]["system"] == flask_character_file["definition"]["system"] == "DND-5E"

    flask_state = _read_flask_character_state(app, character_slug)
    ts_state = _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug)
    assert flask_state is not None
    assert ts_state is not None
    assert ts_state["revision"] == flask_state["revision"] == 1
    assert ts_state["state"] == flask_state["state"]
    assert ts_state["state"]["hit_dice"]["pools"] == [{"faces": 6, "current": 5, "max": 5}]
    assert ts_state["state"]["spell_slots"][:2] == [
        {"level": 1, "max": 4, "used": 0},
        {"level": 2, "max": 3, "used": 0},
    ]
    assert ts_state["state"]["resources"][0]["current"] == 5
    assert ts_state["state"]["inventory"][0]["is_equipped"] is True

    with app.app_context():
        AuthStore().upsert_character_assignment(users["party"]["id"], "linden-pass", character_slug)
    _insert_sqlite_character_assignment(typescript_api_mutation_server["db_path"], character_slug)

    flask_delete = client.delete(
        f"/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=_api_headers(flask_dm_token),
    )
    assert flask_delete.status_code == 200

    ts_delete_status, ts_delete_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="DELETE",
    )
    assert ts_delete_status == 200
    assert ts_delete_payload["deleted"] == flask_delete.get_json()["deleted"]
    assert ts_delete_payload["deleted"]["deleted_state"] is True
    assert ts_delete_payload["deleted"]["deleted_assignment"] is True

    assert _read_flask_character_state(app, character_slug) is None
    assert _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug) is None
    with app.app_context():
        assert AuthStore().get_character_assignment("linden-pass", character_slug) is None
    assert _sqlite_character_assignment_count(typescript_api_mutation_server["db_path"], character_slug) == 0


def test_typescript_dnd_character_create_pilot_writes_definition_import_and_state(
    typescript_api_mutation_server,
):
    character_slug = "api-dnd-pilot"
    body = {
        "values": {
            "name": "API DND Pilot",
            "character_slug": character_slug,
            "class_slug": "systems:phb-fighter",
            "species_slug": "systems:phb-human",
            "background_slug": "systems:phb-soldier",
            "str": "16",
            "dex": "12",
            "con": "14",
            "int": "10",
            "wis": "10",
            "cha": "10",
        }
    }

    status, payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/create",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body=body,
    )

    assert status == 200
    definition = payload["character"]["definition"]
    import_metadata = payload["character"]["import_metadata"]
    state_record = payload["character"]["state_record"]
    assert definition["character_slug"] == character_slug
    assert definition["system"] == "DND-5E"
    assert definition["profile"]["class_level_text"] == "Fighter 1"
    assert definition["profile"]["classes"][0]["systems_ref"]["entry_key"] == "PHB:class:fighter"
    assert definition["profile"]["species_ref"]["entry_key"] == "PHB:race:human"
    assert definition["profile"]["background_ref"]["entry_key"] == "PHB:background:soldier"
    assert definition["stats"]["max_hp"] == 12
    assert definition["stats"]["armor_class"] == 18
    assert definition["resource_templates"][0]["id"] == "second-wind"
    assert definition["source"]["source_path"] == "builder://dnd5e-create-pilot"
    assert import_metadata["source_path"] == "builder://dnd5e-create-pilot"
    assert import_metadata["import_status"] == "managed"
    assert state_record["revision"] == 1
    assert state_record["state"]["vitals"]["current_hp"] == 12
    assert state_record["state"]["hit_dice"]["pools"] == [{"faces": 10, "current": 1, "max": 1}]
    assert state_record["state"]["resources"][0]["id"] == "second-wind"
    assert state_record["state"]["inventory"][0]["catalog_ref"] == "chain-mail-1"
    assert state_record["state"]["currency"]["gp"] == 10
    assert state_record["state"]["spell_slots"] == []

    state = _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug)
    assert state is not None
    assert state["revision"] == 1
    assert state["state"]["vitals"]["current_hp"] == 12
    assert state["state"]["hit_dice"]["pools"][0]["faces"] == 10

    character_dir = typescript_api_mutation_server["campaigns_dir"] / "linden-pass" / "characters" / character_slug
    written_definition = yaml.safe_load((character_dir / "definition.yaml").read_text(encoding="utf-8"))
    written_import = yaml.safe_load((character_dir / "import.yaml").read_text(encoding="utf-8"))
    assert written_definition["name"] == "API DND Pilot"
    assert written_definition["source"]["source_path"] == "builder://dnd5e-create-pilot"
    assert written_import["import_status"] == "managed"

    duplicate_status, duplicate_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/create",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body=body,
    )
    assert duplicate_status == 409
    assert duplicate_payload["error"]["code"] == "character_exists"

    rejected_status, rejected_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/create",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "values": {
                "name": "Rejected DND Pilot",
                "class_slug": "systems:phb-fighter",
                "species_slug": "systems:phb-human",
                "background_slug": "systems:phb-soldier",
                "subclass_slug": "systems:phb-champion",
            }
        },
    )
    assert rejected_status == 400
    assert rejected_payload["error"]["code"] == "validation_error"
    assert "does not support subclass choices" in rejected_payload["error"]["message"]


def test_typescript_character_advanced_editor_context_matches_flask_shell(
    typescript_api_mutation_server,
    client,
    app,
    users,
):
    character_slug = "arden-march"
    flask_dm_token = _issue_api_token(app, users["dm"]["email"], label="dm-character-advanced-editor-golden")

    flask_response = client.get(
        f"/api/v1/campaigns/linden-pass/characters/{character_slug}/advanced-editor",
        headers=_api_headers(flask_dm_token),
    )
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True
    assert flask_payload["supported"] is True
    assert flask_payload["lane"] == "dnd5e"

    status, payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{character_slug}/advanced-editor",
        headers=typescript_api_mutation_server["dm_headers"],
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["message"] is None
    assert payload["campaign"] == flask_payload["campaign"]
    assert payload["character"]["definition"] == flask_payload["character"]["definition"]
    assert payload["character"]["import_metadata"] == flask_payload["character"]["import_metadata"]
    assert payload["supported"] is True
    assert payload["lane"] == "dnd5e"
    assert payload["unsupported_message"] == ""
    assert payload["links"]["advanced_editor_url"] == flask_payload["links"]["advanced_editor_url"]
    assert payload["links"]["flask_advanced_editor_url"] == flask_payload["links"]["flask_advanced_editor_url"]
    assert payload["links"]["character_url"] == flask_payload["links"]["character_url"]
    assert payload["links"]["flask_character_url"] == flask_payload["links"]["flask_character_url"]

    editor = payload["editor"]
    assert editor["state_revision"] == payload["character"]["state_record"]["revision"]
    assert [field["name"] for field in editor["proficiency_fields"]] == [
        field["name"] for field in flask_payload["editor"]["proficiency_fields"]
    ]
    assert editor["proficiency_fields"][0]["label"] == flask_payload["editor"]["proficiency_fields"][0]["label"]
    assert editor["proficiency_fields"][1]["help_text"] == flask_payload["editor"]["proficiency_fields"][1]["help_text"]
    assert [field["name"] for field in editor["stat_adjustment_fields"]] == [
        field["name"] for field in flask_payload["editor"]["stat_adjustment_fields"]
    ]
    assert editor["stat_adjustment_fields"][0]["label"] == flask_payload["editor"]["stat_adjustment_fields"][0]["label"]
    assert (
        editor["stat_adjustment_fields"][1]["help_text"]
        == flask_payload["editor"]["stat_adjustment_fields"][1]["help_text"]
    )
    assert [row["index"] for row in editor["recoverable_penalty_rows"]] == [
        row["index"] for row in flask_payload["editor"]["recoverable_penalty_rows"]
    ]
    assert editor["recoverable_penalty_target_options"] == flask_payload["editor"]["recoverable_penalty_target_options"]
    assert [field["name"] for field in editor["reference_fields"]] == [
        field["name"] for field in flask_payload["editor"]["reference_fields"]
    ]
    assert editor["reference_fields"][0]["label"] == flask_payload["editor"]["reference_fields"][0]["label"]
    assert editor["reference_fields"][1]["label"] == flask_payload["editor"]["reference_fields"][1]["label"]
    assert [row["index"] for row in editor["feature_rows"]] == [
        row["index"] for row in flask_payload["editor"]["feature_rows"]
    ]
    assert editor["activation_options"] == flask_payload["editor"]["activation_options"]
    assert editor["resource_reset_options"] == flask_payload["editor"]["resource_reset_options"]
    for row, flask_row in zip(editor["feature_rows"], flask_payload["editor"]["feature_rows"]):
        assert {
            key: row.get(key)
            for key in ("id", "name", "page_ref", "activation_type", "description_markdown", "resource_max", "resource_reset_on")
        } == {
            key: flask_row.get(key)
            for key in ("id", "name", "page_ref", "activation_type", "description_markdown", "resource_max", "resource_reset_on")
        }
    assert editor["equipment_rows"]
    assert [row["index"] for row in editor["equipment_rows"]] == [
        row["index"] for row in flask_payload["editor"]["equipment_rows"]
    ]
    for row, flask_row in zip(editor["equipment_rows"], flask_payload["editor"]["equipment_rows"]):
        assert {key: row.get(key) for key in ("id", "name", "page_ref", "quantity", "weight", "notes")} == {
            key: flask_row.get(key) for key in ("id", "name", "page_ref", "quantity", "weight", "notes")
        }


def test_typescript_character_advanced_editor_reference_fields_save_fixture(
    typescript_api_mutation_server,
):
    character_slug = "arden-march"
    route_path = f"/api/v1/campaigns/linden-pass/characters/{character_slug}/advanced-editor"
    route_url = f"{typescript_api_mutation_server['url']}{route_path}"

    get_status, get_payload = _to_json(route_url, headers=typescript_api_mutation_server["dm_headers"])
    assert get_status == 200
    expected_revision = get_payload["editor"]["state_revision"]
    base_stats = dict(get_payload["character"]["definition"]["stats"])
    assert not base_stats.get("manual_adjustments")

    fixture_status, fixture_payload = _to_json(
        route_url,
        headers=CONTENT_MANAGER_HEADERS,
        method="PUT",
        body={
            "expected_revision": expected_revision,
            "values": {"biography_markdown": "Fixture write should be denied."},
        },
    )
    assert fixture_status == 403
    assert fixture_payload["error"]["code"] == "forbidden"
    assert "bearer API authentication" in fixture_payload["error"]["message"]

    unsupported_status, unsupported_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={
            "expected_revision": expected_revision,
            "values": {"feature_rows": []},
        },
    )
    assert unsupported_status == 400
    assert unsupported_payload["error"]["code"] == "validation_error"
    assert "feature_rows" in unsupported_payload["error"]["message"]

    linked_feature_status, linked_feature_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={
            "expected_revision": expected_revision,
            "values": {
                "custom_feature_name_1": "Linked Storm Feature",
                "custom_feature_page_ref_1": "boons/storm-feature",
            },
        },
    )
    assert linked_feature_status == 400
    assert linked_feature_payload["error"]["code"] == "validation_error"
    assert "Linked custom feature pages" in linked_feature_payload["error"]["message"]

    stale_status, stale_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={
            "expected_revision": expected_revision - 1,
            "values": {"biography_markdown": "Stale write should be rejected."},
        },
    )
    assert stale_status == 409
    assert stale_payload["error"]["code"] == "state_conflict"

    values = {
        "languages_text": "Common, Elvish\ncommon\n\nDraconic  ",
        "armor_proficiencies_text": "Light Armor, Medium Armor",
        "weapon_proficiencies_text": "Longswords\nShortbows",
        "tool_proficiencies_text": "Thieves' Tools\nNavigator's Tools",
        "stat_adjustment_max_hp": "4",
        "stat_adjustment_armor_class": "1",
        "stat_adjustment_initiative_bonus": "2",
        "stat_adjustment_speed": "10",
        "stat_adjustment_passive_perception": "3",
        "stat_adjustment_passive_insight": "-1",
        "stat_adjustment_passive_investigation": "2",
        "physical_description_markdown": "Updated physical description from TypeScript.",
        "background_markdown": "Updated background from TypeScript.",
        "biography_markdown": "Updated biography from TypeScript.",
        "personality_markdown": "Updated personality from TypeScript.",
        "additional_notes_markdown": "Updated additional notes from TypeScript.",
        "allies_and_organizations_markdown": "Updated allies from TypeScript.",
    }
    save_status, save_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision, "values": values},
    )
    assert save_status == 200
    assert save_payload["ok"] is True
    assert save_payload["message"] == "Character details updated."
    assert save_payload["editor"]["state_revision"] == expected_revision + 1
    assert save_payload["character"]["state_record"]["revision"] == expected_revision + 1
    assert save_payload["character"]["definition"]["proficiencies"]["languages"] == ["Common", "Elvish", "Draconic"]
    assert save_payload["character"]["definition"]["proficiencies"]["armor"] == ["Light Armor", "Medium Armor"]
    assert save_payload["character"]["definition"]["proficiencies"]["weapons"] == ["Longswords", "Shortbows"]
    assert save_payload["character"]["definition"]["proficiencies"]["tools"] == ["Thieves' Tools", "Navigator's Tools"]
    assert save_payload["character"]["definition"]["stats"]["manual_adjustments"] == {
        "max_hp": 4,
        "armor_class": 1,
        "initiative_bonus": 2,
        "speed": 10,
        "passive_perception": 3,
        "passive_insight": -1,
        "passive_investigation": 2,
    }
    assert save_payload["character"]["definition"]["stats"]["max_hp"] == int(base_stats["max_hp"]) + 4
    assert save_payload["character"]["definition"]["stats"]["armor_class"] == int(base_stats["armor_class"]) + 1
    assert save_payload["character"]["definition"]["stats"]["initiative_bonus"] == int(base_stats["initiative_bonus"]) + 2
    assert save_payload["character"]["definition"]["stats"]["speed"] == "40 ft."
    assert save_payload["character"]["definition"]["stats"]["passive_perception"] == int(base_stats["passive_perception"]) + 3
    assert save_payload["character"]["definition"]["stats"]["passive_insight"] == int(base_stats["passive_insight"]) - 1
    assert (
        save_payload["character"]["definition"]["stats"]["passive_investigation"]
        == int(base_stats["passive_investigation"]) + 2
    )
    assert save_payload["character"]["state_record"]["state"]["notes"]["physical_description_markdown"] == values["physical_description_markdown"]
    assert save_payload["character"]["state_record"]["state"]["notes"]["background_markdown"] == values["background_markdown"]
    assert save_payload["character"]["definition"]["profile"]["biography_markdown"] == values["biography_markdown"]
    assert save_payload["character"]["definition"]["profile"]["personality_markdown"] == values["personality_markdown"]
    assert save_payload["character"]["definition"]["reference_notes"]["additional_notes_markdown"] == values["additional_notes_markdown"]
    assert (
        save_payload["character"]["definition"]["reference_notes"]["allies_and_organizations_markdown"]
        == values["allies_and_organizations_markdown"]
    )
    reference_values = {field["name"]: field["value"] for field in save_payload["editor"]["reference_fields"]}
    for field_name, field_value in values.items():
        if field_name.endswith("_text") or field_name.startswith("stat_adjustment_"):
            continue
        assert reference_values[field_name] == field_value
    proficiency_values = {field["name"]: field["value"] for field in save_payload["editor"]["proficiency_fields"]}
    assert proficiency_values["languages_text"] == "Common\nElvish\nDraconic"
    assert proficiency_values["armor_proficiencies_text"] == "Light Armor\nMedium Armor"
    assert proficiency_values["weapon_proficiencies_text"] == values["weapon_proficiencies_text"]
    assert proficiency_values["tool_proficiencies_text"] == values["tool_proficiencies_text"]
    stat_values = {field["name"]: field["value"] for field in save_payload["editor"]["stat_adjustment_fields"]}
    for field_name, field_value in values.items():
        if field_name.startswith("stat_adjustment_"):
            assert stat_values[field_name] == field_value

    sqlite_state = _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug)
    assert sqlite_state is not None
    assert sqlite_state["revision"] == expected_revision + 1
    assert sqlite_state["state"]["notes"]["physical_description_markdown"] == values["physical_description_markdown"]
    assert sqlite_state["state"]["notes"]["background_markdown"] == values["background_markdown"]

    definition_path = (
        typescript_api_mutation_server["campaigns_dir"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    assert definition["proficiencies"]["languages"] == ["Common", "Elvish", "Draconic"]
    assert definition["proficiencies"]["armor"] == ["Light Armor", "Medium Armor"]
    assert definition["proficiencies"]["weapons"] == ["Longswords", "Shortbows"]
    assert definition["proficiencies"]["tools"] == ["Thieves' Tools", "Navigator's Tools"]
    assert definition["stats"]["manual_adjustments"] == {
        "max_hp": 4,
        "armor_class": 1,
        "initiative_bonus": 2,
        "speed": 10,
        "passive_perception": 3,
        "passive_insight": -1,
        "passive_investigation": 2,
    }
    assert definition["stats"]["max_hp"] == int(base_stats["max_hp"]) + 4
    assert definition["stats"]["armor_class"] == int(base_stats["armor_class"]) + 1
    assert definition["stats"]["initiative_bonus"] == int(base_stats["initiative_bonus"]) + 2
    assert definition["stats"]["speed"] == "40 ft."
    assert definition["profile"]["biography_markdown"] == values["biography_markdown"]
    assert definition["profile"]["personality_markdown"] == values["personality_markdown"]
    assert definition["reference_notes"]["additional_notes_markdown"] == values["additional_notes_markdown"]
    assert definition["reference_notes"]["allies_and_organizations_markdown"] == values["allies_and_organizations_markdown"]

    clear_stat_values = {
        "stat_adjustment_max_hp": "",
        "stat_adjustment_armor_class": "",
        "stat_adjustment_initiative_bonus": "",
        "stat_adjustment_speed": "",
        "stat_adjustment_passive_perception": "",
        "stat_adjustment_passive_insight": "",
        "stat_adjustment_passive_investigation": "",
    }
    clear_status, clear_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 1, "values": clear_stat_values},
    )
    assert clear_status == 200
    assert clear_payload["editor"]["state_revision"] == expected_revision + 2
    cleared_stats = clear_payload["character"]["definition"]["stats"]
    assert "manual_adjustments" not in cleared_stats
    assert cleared_stats["max_hp"] == base_stats["max_hp"]
    assert cleared_stats["armor_class"] == base_stats["armor_class"]
    assert cleared_stats["initiative_bonus"] == base_stats["initiative_bonus"]
    assert cleared_stats["speed"] == base_stats["speed"]
    assert cleared_stats["passive_perception"] == base_stats["passive_perception"]
    assert cleared_stats["passive_insight"] == base_stats["passive_insight"]
    assert cleared_stats["passive_investigation"] == base_stats["passive_investigation"]
    cleared_stat_values = {field["name"]: field["value"] for field in clear_payload["editor"]["stat_adjustment_fields"]}
    assert cleared_stat_values == clear_stat_values

    invalid_penalty_status, invalid_penalty_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={
            "expected_revision": expected_revision + 2,
            "values": {
                "recoverable_penalty_target_1": "max_hp",
                "recoverable_penalty_amount_1": "6",
            },
        },
    )
    assert invalid_penalty_status == 400
    assert invalid_penalty_payload["error"]["code"] == "validation_error"
    assert "source label" in invalid_penalty_payload["error"]["message"]

    base_ability_scores = dict(base_stats["ability_scores"])
    base_cha = dict(base_ability_scores["cha"])
    base_cha_modifier = int(base_cha["modifier"])
    penalized_cha_score = int(base_cha["score"]) - 2
    penalized_cha_modifier = (penalized_cha_score - 10) // 2
    recoverable_values = {
        "recoverable_penalty_source_1": "Wight Drain",
        "recoverable_penalty_target_1": "max_hp",
        "recoverable_penalty_amount_1": "6",
        "recoverable_penalty_notes_1": "Restored by stronger healing magic.",
        "recoverable_penalty_source_2": "Mind Lash",
        "recoverable_penalty_target_2": "ability_score:cha",
        "recoverable_penalty_amount_2": "2",
    }
    recoverable_status, recoverable_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 2, "values": recoverable_values},
    )
    assert recoverable_status == 200
    assert recoverable_payload["editor"]["state_revision"] == expected_revision + 3
    recoverable_stats = recoverable_payload["character"]["definition"]["stats"]
    penalties = list(recoverable_stats["recoverable_penalties"])
    assert len(penalties) == 2
    assert penalties[0]["id"].startswith("recoverable-penalty-wight-drain")
    assert penalties[0]["kind"] == "max_hp"
    assert penalties[0]["amount"] == 6
    assert penalties[0]["source"] == "Wight Drain"
    assert penalties[0]["notes"] == "Restored by stronger healing magic."
    assert penalties[1]["id"].startswith("recoverable-penalty-mind-lash")
    assert penalties[1]["kind"] == "ability_score"
    assert penalties[1]["ability_key"] == "cha"
    assert recoverable_stats["max_hp"] == int(base_stats["max_hp"]) - 6
    assert recoverable_stats["ability_scores"]["cha"]["score"] == penalized_cha_score
    assert recoverable_stats["ability_scores"]["cha"]["modifier"] == penalized_cha_modifier
    assert recoverable_stats["ability_scores"]["cha"]["save_bonus"] == int(base_cha["save_bonus"]) + (
        penalized_cha_modifier - base_cha_modifier
    )
    assert recoverable_payload["character"]["state_record"]["state"]["vitals"]["current_hp"] == int(base_stats["max_hp"]) - 6
    penalty_values = {
        f"recoverable_penalty_{key}_{row['index']}": row[key]
        for row in recoverable_payload["editor"]["recoverable_penalty_rows"]
        for key in ("id", "source", "target", "amount", "notes")
        if row.get("source")
    }
    assert penalty_values["recoverable_penalty_source_1"] == "Wight Drain"
    assert penalty_values["recoverable_penalty_target_1"] == "max_hp"
    assert penalty_values["recoverable_penalty_amount_1"] == "6"
    assert penalty_values["recoverable_penalty_target_2"] == "ability_score:cha"

    reduce_penalty_values = {
        "recoverable_penalty_id_1": penalties[0]["id"],
        "recoverable_penalty_source_1": "Wight Drain",
        "recoverable_penalty_target_1": "max_hp",
        "recoverable_penalty_amount_1": "2",
        "recoverable_penalty_notes_1": "Restored by stronger healing magic.",
    }
    reduce_status, reduce_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 3, "values": reduce_penalty_values},
    )
    assert reduce_status == 200
    assert reduce_payload["editor"]["state_revision"] == expected_revision + 4
    reduced_stats = reduce_payload["character"]["definition"]["stats"]
    reduced_penalties = list(reduced_stats["recoverable_penalties"])
    assert len(reduced_penalties) == 1
    assert reduced_penalties[0]["id"] == penalties[0]["id"]
    assert reduced_penalties[0]["amount"] == 2
    assert reduced_stats["max_hp"] == int(base_stats["max_hp"]) - 2
    assert reduced_stats["ability_scores"]["cha"] == base_cha
    assert reduce_payload["character"]["state_record"]["state"]["vitals"]["current_hp"] == int(base_stats["max_hp"]) - 6

    clear_penalty_status, clear_penalty_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={
            "expected_revision": expected_revision + 4,
            "values": {
                "recoverable_penalty_id_1": "",
                "recoverable_penalty_source_1": "",
                "recoverable_penalty_target_1": "",
                "recoverable_penalty_amount_1": "",
                "recoverable_penalty_notes_1": "",
            },
        },
    )
    assert clear_penalty_status == 200
    assert clear_penalty_payload["editor"]["state_revision"] == expected_revision + 5
    clear_penalty_stats = clear_penalty_payload["character"]["definition"]["stats"]
    assert "recoverable_penalties" not in clear_penalty_stats
    assert clear_penalty_stats["max_hp"] == base_stats["max_hp"]
    assert clear_penalty_stats["ability_scores"]["cha"] == base_cha
    assert clear_penalty_payload["character"]["state_record"]["state"]["vitals"]["current_hp"] == int(base_stats["max_hp"]) - 6

    invalid_equipment_status, invalid_equipment_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={
            "expected_revision": expected_revision + 5,
            "values": {
                "manual_item_name_1": "Broken Token",
                "manual_item_quantity_1": "many",
            },
        },
    )
    assert invalid_equipment_status == 400
    assert invalid_equipment_payload["error"]["code"] == "validation_error"
    assert "whole numbers" in invalid_equipment_payload["error"]["message"]

    linked_equipment_status, linked_equipment_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={
            "expected_revision": expected_revision + 5,
            "values": {
                "manual_item_name_1": "Linked Token",
                "manual_item_page_ref_1": "items/stormglass-compass",
                "manual_item_quantity_1": "1",
            },
        },
    )
    assert linked_equipment_status == 400
    assert linked_equipment_payload["error"]["code"] == "validation_error"
    assert "Linked manual equipment pages" in linked_equipment_payload["error"]["message"]

    equipment_values = {
        "manual_item_name_1": "Storm Token",
        "manual_item_quantity_1": "2",
        "manual_item_weight_1": "light",
        "manual_item_notes_1": "Stamped with blue wax.",
    }
    equipment_status, equipment_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 5, "values": equipment_values},
    )
    assert equipment_status == 200
    assert equipment_payload["editor"]["state_revision"] == expected_revision + 6
    manual_items = [
        item
        for item in equipment_payload["character"]["definition"]["equipment_catalog"]
        if item.get("source_kind") == "manual_edit"
    ]
    assert len(manual_items) == 1
    manual_item = manual_items[0]
    manual_item_id = manual_item["id"]
    assert manual_item_id.startswith("manual-item-storm-token")
    assert manual_item["name"] == "Storm Token"
    assert manual_item["default_quantity"] == 2
    assert manual_item["weight"] == "light"
    assert manual_item["notes"] == "Stamped with blue wax."
    inventory_by_ref = {
        item.get("catalog_ref"): item
        for item in equipment_payload["character"]["state_record"]["state"]["inventory"]
    }
    assert inventory_by_ref[manual_item_id]["name"] == "Storm Token"
    assert inventory_by_ref[manual_item_id]["quantity"] == 2
    assert inventory_by_ref[manual_item_id]["weight"] == "light"
    assert inventory_by_ref[manual_item_id]["notes"] == "Stamped with blue wax."
    equipment_rows = {
        row["index"]: row for row in equipment_payload["editor"]["equipment_rows"]
    }
    assert equipment_rows[1]["id"] == manual_item_id
    assert equipment_rows[1]["name"] == "Storm Token"
    assert equipment_rows[1]["quantity"] == "2"
    assert equipment_rows[1]["weight"] == "light"
    assert equipment_rows[1]["notes"] == "Stamped with blue wax."
    assert [row["index"] for row in equipment_payload["editor"]["equipment_rows"]] == [1, 2, 3]

    sqlite_state = _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug)
    assert sqlite_state is not None
    assert sqlite_state["revision"] == expected_revision + 6
    sqlite_inventory = {
        item.get("catalog_ref"): item for item in sqlite_state["state"]["inventory"]
    }
    assert sqlite_inventory[manual_item_id]["quantity"] == 2

    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    manual_definition_items = [
        item for item in definition["equipment_catalog"] if item.get("source_kind") == "manual_edit"
    ]
    assert len(manual_definition_items) == 1
    assert manual_definition_items[0]["id"] == manual_item_id
    assert manual_definition_items[0]["default_quantity"] == 2

    update_equipment_values = {
        "manual_item_id_1": manual_item_id,
        "manual_item_name_1": "Silver Storm Token",
        "manual_item_quantity_1": "0",
        "manual_item_weight_1": "1 lb.",
        "manual_item_notes_1": "Spent but kept as proof.",
    }
    update_equipment_status, update_equipment_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 6, "values": update_equipment_values},
    )
    assert update_equipment_status == 200
    assert update_equipment_payload["editor"]["state_revision"] == expected_revision + 7
    updated_manual_items = [
        item
        for item in update_equipment_payload["character"]["definition"]["equipment_catalog"]
        if item.get("source_kind") == "manual_edit"
    ]
    assert len(updated_manual_items) == 1
    assert updated_manual_items[0]["id"] == manual_item_id
    assert updated_manual_items[0]["name"] == "Silver Storm Token"
    assert updated_manual_items[0]["default_quantity"] == 0
    updated_inventory_by_ref = {
        item.get("catalog_ref"): item
        for item in update_equipment_payload["character"]["state_record"]["state"]["inventory"]
    }
    assert updated_inventory_by_ref[manual_item_id]["name"] == "Silver Storm Token"
    assert updated_inventory_by_ref[manual_item_id]["quantity"] == 0
    assert updated_inventory_by_ref[manual_item_id]["weight"] == "1 lb."
    assert updated_inventory_by_ref[manual_item_id]["notes"] == "Spent but kept as proof."

    clear_equipment_values = {
        "manual_item_id_1": "",
        "manual_item_name_1": "",
        "manual_item_page_ref_1": "",
        "manual_item_quantity_1": "",
        "manual_item_weight_1": "",
        "manual_item_notes_1": "",
    }
    clear_equipment_status, clear_equipment_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 7, "values": clear_equipment_values},
    )
    assert clear_equipment_status == 200
    assert clear_equipment_payload["editor"]["state_revision"] == expected_revision + 8
    assert all(
        item.get("source_kind") != "manual_edit"
        for item in clear_equipment_payload["character"]["definition"]["equipment_catalog"]
    )
    assert all(
        item.get("catalog_ref") != manual_item_id
        for item in clear_equipment_payload["character"]["state_record"]["state"]["inventory"]
    )
    assert [
        {key: row.get(key) for key in ("id", "name", "page_ref", "quantity", "weight", "notes")}
        for row in clear_equipment_payload["editor"]["equipment_rows"]
    ] == [
        {"id": "", "name": "", "page_ref": "", "quantity": "", "weight": "", "notes": ""},
        {"id": "", "name": "", "page_ref": "", "quantity": "", "weight": "", "notes": ""},
        {"id": "", "name": "", "page_ref": "", "quantity": "", "weight": "", "notes": ""},
    ]

    custom_feature_values = {
        "custom_feature_name_1": "Storm Blessing",
        "custom_feature_activation_type_1": "bonus_action",
        "custom_feature_description_1": "Call the storm once per rest.",
        "custom_feature_resource_max_1": "3",
        "custom_feature_resource_reset_on_1": "long_rest",
    }
    custom_feature_status, custom_feature_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 8, "values": custom_feature_values},
    )
    assert custom_feature_status == 200
    assert custom_feature_payload["editor"]["state_revision"] == expected_revision + 9
    custom_features = [
        feature
        for feature in custom_feature_payload["character"]["definition"]["features"]
        if feature.get("category") == "custom_feature"
    ]
    assert len(custom_features) == 1
    custom_feature = custom_features[0]
    custom_feature_id = custom_feature["id"]
    tracker_id = f"custom_feature:{custom_feature_id}"
    assert custom_feature_id.startswith("custom-feature-storm-blessing")
    assert custom_feature["name"] == "Storm Blessing"
    assert custom_feature["activation_type"] == "bonus_action"
    assert custom_feature["description_markdown"] == "Call the storm once per rest."
    assert custom_feature["source"] == "Campaign"
    assert custom_feature["tracker_ref"] == tracker_id
    custom_templates = [
        template
        for template in custom_feature_payload["character"]["definition"]["resource_templates"]
        if template.get("category") == "custom_feature"
    ]
    assert custom_templates == [
        {
            "id": tracker_id,
            "label": "Storm Blessing",
            "category": "custom_feature",
            "initial_current": 3,
            "max": 3,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "",
            "display_order": 0,
        }
    ]
    custom_resource_by_id = {
        resource.get("id"): resource
        for resource in custom_feature_payload["character"]["state_record"]["state"]["resources"]
    }
    assert custom_resource_by_id[tracker_id]["current"] == 3
    assert custom_resource_by_id[tracker_id]["max"] == 3
    assert custom_resource_by_id[tracker_id]["reset_on"] == "long_rest"
    feature_rows = {
        row["index"]: row for row in custom_feature_payload["editor"]["feature_rows"]
    }
    assert feature_rows[1]["id"] == custom_feature_id
    assert feature_rows[1]["name"] == "Storm Blessing"
    assert feature_rows[1]["activation_type"] == "bonus_action"
    assert feature_rows[1]["description_markdown"] == "Call the storm once per rest."
    assert feature_rows[1]["resource_max"] == "3"
    assert feature_rows[1]["resource_reset_on"] == "long_rest"
    assert [row["index"] for row in custom_feature_payload["editor"]["feature_rows"]] == [1, 2, 3]

    sqlite_state = _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug)
    assert sqlite_state is not None
    assert sqlite_state["revision"] == expected_revision + 9
    sqlite_resources = {resource.get("id"): resource for resource in sqlite_state["state"]["resources"]}
    assert sqlite_resources[tracker_id]["current"] == 3
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition_custom_features = [
        feature for feature in definition["features"] if feature.get("category") == "custom_feature"
    ]
    assert len(definition_custom_features) == 1
    assert definition_custom_features[0]["id"] == custom_feature_id
    assert [
        template for template in definition["resource_templates"] if template.get("category") == "custom_feature"
    ][0]["id"] == tracker_id

    update_custom_feature_values = {
        "custom_feature_id_1": custom_feature_id,
        "custom_feature_name_1": "Storm Blessing, Spent",
        "custom_feature_activation_type_1": "reaction",
        "custom_feature_description_1": "Spend the storm after the first strike.",
        "custom_feature_resource_max_1": "1",
        "custom_feature_resource_reset_on_1": "short_rest",
    }
    update_custom_feature_status, update_custom_feature_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 9, "values": update_custom_feature_values},
    )
    assert update_custom_feature_status == 200
    assert update_custom_feature_payload["editor"]["state_revision"] == expected_revision + 10
    updated_custom_features = [
        feature
        for feature in update_custom_feature_payload["character"]["definition"]["features"]
        if feature.get("category") == "custom_feature"
    ]
    assert len(updated_custom_features) == 1
    assert updated_custom_features[0]["id"] == custom_feature_id
    assert updated_custom_features[0]["name"] == "Storm Blessing, Spent"
    assert updated_custom_features[0]["activation_type"] == "reaction"
    updated_template = [
        template
        for template in update_custom_feature_payload["character"]["definition"]["resource_templates"]
        if template.get("id") == tracker_id
    ][0]
    assert updated_template["max"] == 1
    assert updated_template["reset_on"] == "short_rest"
    assert updated_template["reset_to"] == "max"
    updated_resources = {
        resource.get("id"): resource
        for resource in update_custom_feature_payload["character"]["state_record"]["state"]["resources"]
    }
    assert updated_resources[tracker_id]["current"] == 1
    assert updated_resources[tracker_id]["max"] == 1

    clear_custom_feature_values = {
        "custom_feature_id_1": custom_feature_id,
        "custom_feature_name_1": "",
        "custom_feature_page_ref_1": "",
        "custom_feature_activation_type_1": "",
        "custom_feature_description_1": "",
        "custom_feature_resource_max_1": "",
        "custom_feature_resource_reset_on_1": "",
    }
    clear_custom_feature_status, clear_custom_feature_payload = _to_json(
        route_url,
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"expected_revision": expected_revision + 10, "values": clear_custom_feature_values},
    )
    assert clear_custom_feature_status == 200
    assert clear_custom_feature_payload["editor"]["state_revision"] == expected_revision + 11
    assert all(
        feature.get("category") != "custom_feature"
        for feature in clear_custom_feature_payload["character"]["definition"]["features"]
    )
    assert all(
        template.get("id") != tracker_id
        for template in clear_custom_feature_payload["character"]["definition"]["resource_templates"]
    )
    assert all(
        resource.get("id") != tracker_id
        for resource in clear_custom_feature_payload["character"]["state_record"]["state"]["resources"]
    )
    assert [
        {
            key: row.get(key)
            for key in ("id", "name", "page_ref", "activation_type", "description_markdown", "resource_max", "resource_reset_on")
        }
        for row in clear_custom_feature_payload["editor"]["feature_rows"]
    ] == [
        {"id": "", "name": "", "page_ref": "", "activation_type": "passive", "description_markdown": "", "resource_max": "", "resource_reset_on": "manual"},
        {"id": "", "name": "", "page_ref": "", "activation_type": "passive", "description_markdown": "", "resource_max": "", "resource_reset_on": "manual"},
        {"id": "", "name": "", "page_ref": "", "activation_type": "passive", "description_markdown": "", "resource_max": "", "resource_reset_on": "manual"},
    ]


def test_typescript_character_advancement_context_shells_match_flask_fixture(
    typescript_api_mutation_server,
    client,
    app,
    users,
):
    character_slug = "arden-march"
    flask_dm_token = _issue_api_token(app, users["dm"]["email"], label="dm-character-advancement-shells-golden")
    route_cases = [
        ("level-up", "level_up"),
        ("retraining", "retraining"),
        ("progression-repair", "repair"),
    ]

    for route_suffix, context_key in route_cases:
        route_path = f"/api/v1/campaigns/linden-pass/characters/{character_slug}/{route_suffix}"
        flask_response = client.get(route_path, headers=_api_headers(flask_dm_token))
        assert flask_response.status_code == 200
        flask_payload = flask_response.get_json()
        assert flask_payload["ok"] is True

        status, payload = _to_json(
            f"{typescript_api_mutation_server['url']}{route_path}",
            headers=typescript_api_mutation_server["dm_headers"],
        )

        assert status == 200
        assert payload["ok"] is True
        assert payload["message"] is None
        assert payload["campaign"] == flask_payload["campaign"]
        assert payload["character"]["definition"] == flask_payload["character"]["definition"]
        assert payload["character"]["import_metadata"] == flask_payload["character"]["import_metadata"]
        assert payload["supported"] == flask_payload["supported"] is False
        assert payload["lane"] == flask_payload["lane"] == "unsupported"
        assert payload["unsupported_message"] == flask_payload["unsupported_message"]
        assert payload["readiness"] == flask_payload["readiness"]
        assert payload[context_key] is None
        assert payload[context_key] == flask_payload[context_key]
        for link_key in (
            "advanced_editor_url",
            "flask_advanced_editor_url",
            "character_url",
            "flask_character_url",
            "flask_roster_url",
        ):
            assert payload["links"].get(link_key) == flask_payload["links"].get(link_key)

        flask_post_response = client.post(
            route_path,
            headers=_api_headers(flask_dm_token),
            json={"expected_revision": payload["character"]["state_record"]["revision"], "values": {}},
        )
        assert flask_post_response.status_code == 400
        flask_post_payload = flask_post_response.get_json()

        post_status, post_payload = _to_json(
            f"{typescript_api_mutation_server['url']}{route_path}",
            headers=typescript_api_mutation_server["dm_headers"],
            method="POST",
            body={"expected_revision": payload["character"]["state_record"]["revision"], "values": {}},
        )
        assert post_status == 400
        assert post_payload["error"]["code"] == flask_post_payload["error"]["code"] == "unsupported_campaign_system"
        assert post_payload["error"]["message"] == flask_post_payload["error"]["message"]

    xianxia_character_slug = "api-advancement-crane"
    flask_campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    _write_campaign_system(flask_campaigns_dir, system="Xianxia", systems_library="Xianxia")
    with app.app_context():
        app.extensions["repository_store"].refresh()
    _write_campaign_system(typescript_api_mutation_server["campaigns_dir"], system="Xianxia", systems_library="Xianxia")
    xianxia_definition_payload = {
        "name": "API Advancement Crane",
        "status": "active",
        "system": "xianxia",
        "xianxia": {
            "realm": "Mortal",
            "energy_maxima": {"jing": 1, "qi": 1, "shen": 1},
            "yin_yang": {"yin_max": 1, "yang_max": 1},
            "durability": {"hp_max": 10, "stance_max": 10, "manual_armor_bonus": 0},
            "trained_skills": ["Qi Sense"],
            "martial_arts": [{"name": "Cloud Palm", "current_rank": "Initiate"}],
        },
    }
    xianxia_body = {"definition": xianxia_definition_payload}

    flask_create = client.put(
        f"/api/v1/campaigns/linden-pass/content/characters/{xianxia_character_slug}",
        headers=_api_headers(flask_dm_token),
        json=xianxia_body,
    )
    assert flask_create.status_code == 200
    ts_create_status, _ts_create_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{xianxia_character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=xianxia_body,
    )
    assert ts_create_status == 200

    for route_suffix, context_key in route_cases:
        route_path = f"/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/{route_suffix}"
        flask_response = client.get(route_path, headers=_api_headers(flask_dm_token))
        assert flask_response.status_code == 200
        flask_payload = flask_response.get_json()

        status, payload = _to_json(
            f"{typescript_api_mutation_server['url']}{route_path}",
            headers=typescript_api_mutation_server["dm_headers"],
        )

        assert status == 200
        assert payload["ok"] is True
        assert payload["campaign"] == flask_payload["campaign"]
        assert payload["supported"] == flask_payload["supported"] is False
        assert payload["lane"] == flask_payload["lane"] == "unsupported"
        assert payload["unsupported_message"] == flask_payload["unsupported_message"]
        assert payload["readiness"] == flask_payload["readiness"]
        assert payload[context_key] is None
        assert payload[context_key] == flask_payload[context_key]
        for link_key in (
            "cultivation_url",
            "flask_cultivation_url",
            "character_url",
            "flask_character_url",
            "flask_roster_url",
        ):
            assert payload["links"].get(link_key) == flask_payload["links"].get(link_key)

        flask_post_response = client.post(
            route_path,
            headers=_api_headers(flask_dm_token),
            json={"expected_revision": payload["character"]["state_record"]["revision"], "values": {}},
        )
        assert flask_post_response.status_code == 400
        flask_post_payload = flask_post_response.get_json()

        post_status, post_payload = _to_json(
            f"{typescript_api_mutation_server['url']}{route_path}",
            headers=typescript_api_mutation_server["dm_headers"],
            method="POST",
            body={"expected_revision": payload["character"]["state_record"]["revision"], "values": {}},
        )
        assert post_status == 400
        assert post_payload["error"]["code"] == flask_post_payload["error"]["code"] == "unsupported_campaign_system"
        assert post_payload["error"]["message"] == flask_post_payload["error"]["message"]


def test_typescript_character_cultivation_context_shell_and_supported_xianxia_context(
    typescript_api_mutation_server,
    client,
    app,
    users,
):
    character_slug = "arden-march"
    route_path = f"/api/v1/campaigns/linden-pass/characters/{character_slug}/cultivation"
    flask_dm_token = _issue_api_token(app, users["dm"]["email"], label="dm-character-cultivation-shell-golden")

    flask_response = client.get(route_path, headers=_api_headers(flask_dm_token))
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()
    assert flask_payload["ok"] is True

    status, payload = _to_json(
        f"{typescript_api_mutation_server['url']}{route_path}",
        headers=typescript_api_mutation_server["dm_headers"],
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["campaign"] == flask_payload["campaign"]
    assert payload["character"]["definition"] == flask_payload["character"]["definition"]
    assert payload["character"]["import_metadata"] == flask_payload["character"]["import_metadata"]
    assert payload["supported"] == flask_payload["supported"] is False
    assert payload["lane"] == flask_payload["lane"] == "unsupported"
    assert payload["message"] == flask_payload["message"] is None
    assert payload["anchor"] == flask_payload["anchor"] is None
    assert payload["unsupported_message"] == flask_payload["unsupported_message"]
    assert payload["cultivation"] == flask_payload["cultivation"] is None
    for link_key in (
        "character_url",
        "flask_character_url",
        "cultivation_url",
        "flask_cultivation_url",
        "flask_roster_url",
    ):
        assert payload["links"].get(link_key) == flask_payload["links"].get(link_key)

    player_status, player_payload = _to_json(
        f"{typescript_api_mutation_server['url']}{route_path}",
        headers=CONTENT_PLAYER_HEADERS,
    )
    assert player_status == 403
    assert player_payload["error"]["code"] == "forbidden"
    assert player_payload["error"]["message"] == "You do not have permission to manage cultivation for this character."

    missing_status, missing_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/missing-character/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
    )
    assert missing_status == 404
    assert missing_payload["error"]["code"] == "content_character_not_found"

    xianxia_character_slug = "api-cultivation-crane"
    _write_campaign_system(typescript_api_mutation_server["campaigns_dir"], system="Xianxia", systems_library="Xianxia")
    _seed_xianxia_generic_techniques(typescript_api_mutation_server["db_path"])
    xianxia_body = {
        "definition": {
            "name": "API Cultivation Crane",
            "status": "active",
            "system": "xianxia",
            "xianxia": {
                "realm": "Mortal",
                "attributes": {
                    "str": 1,
                    "dex": 1,
                    "con": 1,
                    "int": 1,
                    "wis": 1,
                    "cha": 1,
                },
                "efforts": {
                    "basic": 1,
                    "weapon": 1,
                    "guns_explosive": 1,
                    "magic": 1,
                    "ultimate": 1,
                },
                "insight": {"available": 0, "spent": 0},
                "energies": {"jing": {"max": 1}, "qi": {"max": 1}, "shen": {"max": 1}},
                "yin_yang": {"yin_max": 1, "yang_max": 1},
                "durability": {"hp_max": 10, "stance_max": 10, "manual_armor_bonus": 0},
                "trained_skills": ["Qi Sense"],
                "martial_arts": [
                    {
                        "name": "Cloud Palm",
                        "systems_ref": {
                            "library_slug": "Xianxia",
                            "source_id": "XIA",
                            "entry_key": "XIA:martial_art:cloud-palm",
                            "slug": "xia-martial-art-cloud-palm",
                            "title": "Cloud Palm",
                            "entry_type": "martial_art",
                        },
                        "current_rank": "Initiate",
                        "current_rank_key": "initiate",
                        "rank_refs": {
                            "initiate": "systems:xia-cloud-palm:initiate",
                            "novice": "systems:xia-cloud-palm:novice",
                        },
                        "learned_rank_refs": ["systems:xia-cloud-palm:initiate"],
                    }
                ],
                "generic_techniques": [
                    {
                        "name": "Qi Blast",
                        "systems_ref": {
                            "library_slug": "Xianxia",
                            "source_id": "XIA",
                            "entry_key": "XIA:generic_technique:qi-blast",
                            "slug": "xia-generic-technique-qi-blast",
                            "title": "Qi Blast",
                            "entry_type": "generic_technique",
                        },
                        "generic_technique_key": "qi_blast",
                        "insight_spent": 1,
                    }
                ],
            },
        }
    }
    ts_create_status, _ts_create_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{xianxia_character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=xianxia_body,
    )
    assert ts_create_status == 200

    xianxia_status, xianxia_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
    )
    assert xianxia_status == 200
    assert xianxia_payload["ok"] is True
    assert xianxia_payload["supported"] is True
    assert xianxia_payload["lane"] == "xianxia"
    assert xianxia_payload["unsupported_message"] == ""
    cultivation = xianxia_payload["cultivation"]
    assert cultivation["insight"] == {"available": 0, "spent": 0}
    assert [row["key"] for row in cultivation["energies"]] == ["jing", "qi", "shen"]
    assert all(row["insight_cost"] == 1 for row in cultivation["energies"])
    assert [row["key"] for row in cultivation["yin_yang"]] == ["yin", "yang"]
    assert cultivation["conditioning"]["hp"]["cap"] == 50
    assert cultivation["conditioning"]["hp"]["projected_max"] == 20
    assert cultivation["training"]["stance"]["cap"] == 50
    assert cultivation["training"]["stance"]["projected_max"] == 20
    assert [row["key"] for row in cultivation["training"]["attributes"]] == [
        "str",
        "dex",
        "con",
        "int",
        "wis",
        "cha",
    ]
    assert [row["key"] for row in cultivation["conditioning"]["efforts"]] == [
        "basic",
        "weapon",
        "guns_explosive",
        "magic",
        "ultimate",
    ]
    assert cultivation["martial_arts"][0]["name"] == "Cloud Palm"
    assert cultivation["martial_arts"][0]["advancement"]["next_rank_key"] == "novice"
    assert cultivation["martial_arts"][0]["advancement"]["shortfall"] == 1
    assert cultivation["realm_ascension"]["current_realm"] == "Mortal"
    assert cultivation["realm_ascension"]["target"]["target_realm"] == "Immortal"
    assert cultivation["realm_ascension"]["can_start_review"] is False
    assert cultivation["history"] == []
    assert cultivation["generic_techniques"][0]["name"] == "Qi Blast"
    assert cultivation["generic_techniques"][0]["href"] == (
        "/app-next/campaigns/linden-pass/systems/entries/xia-generic-technique-qi-blast"
    )
    option_keys = {option["generic_technique_key"] for option in cultivation["generic_technique_options"]}
    assert "qi_blast" not in option_keys
    assert "cultivation" not in option_keys
    assert "meteor_step" in option_keys
    assert "enhanced_flowing_dao" in option_keys
    meteor_option = next(
        option
        for option in cultivation["generic_technique_options"]
        if option["generic_technique_key"] == "meteor_step"
    )
    assert meteor_option["href"] == (
        "/app-next/campaigns/linden-pass/systems/entries/xia-generic-technique-meteor-step"
    )
    assert meteor_option["shortfall"] == 2
    assert meteor_option["learnable_without_master"] is True
    enhanced_option = next(
        option
        for option in cultivation["generic_technique_options"]
        if option["generic_technique_key"] == "enhanced_flowing_dao"
    )
    assert enhanced_option["href"] == (
        "/app-next/campaigns/linden-pass/systems/entries/xia-generic-technique-enhanced-flowing-dao"
    )
    assert enhanced_option["shortfall"] == 2
    assert enhanced_option["prerequisites"] == ["Any Dao 1"]
    assert xianxia_payload["links"]["flask_cultivation_url"] == (
        f"/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation"
    )

    initial_revision = xianxia_payload["character"]["state_record"]["revision"]
    save_status, save_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision,
            "action": "save_insight",
            "values": {"insight_available": "3", "insight_spent": "1"},
        },
    )
    assert save_status == 200
    assert save_payload["ok"] is True
    assert save_payload["message"] == "Insight counters saved."
    assert save_payload["anchor"] == "xianxia-cultivation-insight"
    assert save_payload["supported"] is True
    assert save_payload["lane"] == "xianxia"
    assert save_payload["character"]["state_record"]["revision"] == initial_revision + 1
    saved_xianxia = save_payload["character"]["definition"]["xianxia"]
    assert saved_xianxia["insight"] == {"available": 3, "spent": 1}
    assert save_payload["cultivation"]["insight"] == {"available": 3, "spent": 1}
    history_row = saved_xianxia["advancement_history"][-1]
    assert history_row == {
        "action": "insight_counter_adjustment",
        "target": "Insight",
        "insight_available_before": 0,
        "insight_available_after": 3,
        "insight_available_delta": 3,
        "insight_spent_before": 0,
        "insight_spent_after": 1,
        "insight_spent_delta": 1,
    }

    stale_status, stale_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision,
            "cultivation_action": "save_insight",
            "insight_available": "4",
            "insight_spent": "1",
        },
    )
    assert stale_status == 409
    assert stale_payload["error"]["code"] == "state_conflict"
    assert stale_payload["error"]["message"] == "This sheet changed in another session. Refresh and try again."

    invalid_status, invalid_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 1,
            "action": "save_insight",
            "values": {"insight_available": "-1", "insight_spent": "1"},
        },
    )
    assert invalid_status == 400
    assert invalid_payload["error"]["code"] == "validation_error"
    assert invalid_payload["error"]["message"] == "Insight available must be zero or greater."

    unchanged_status, unchanged_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 1,
            "action": "save_insight",
            "values": {"insight_available": "3", "insight_spent": "1"},
        },
    )
    assert unchanged_status == 200
    assert unchanged_payload["character"]["state_record"]["revision"] == initial_revision + 2
    assert unchanged_payload["character"]["definition"]["xianxia"]["advancement_history"] == saved_xianxia[
        "advancement_history"
    ]

    gathering_status, gathering_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 2,
            "cultivation_action": "record_gathering_insight",
            "values": {
                "insight_gain_amount": "4",
                "gathering_insight_downtime": " 3 days   between sessions ",
                "gathering_insight_notes": " Meditated under storm clouds. ",
            },
        },
    )
    assert gathering_status == 200
    assert gathering_payload["ok"] is True
    assert gathering_payload["message"] == "Gathering Insight recorded."
    assert gathering_payload["anchor"] == "xianxia-cultivation-gathering-insight"
    assert gathering_payload["character"]["state_record"]["revision"] == initial_revision + 3
    gathered_xianxia = gathering_payload["character"]["definition"]["xianxia"]
    assert gathered_xianxia["insight"] == {"available": 7, "spent": 1}
    assert gathering_payload["cultivation"]["insight"] == {"available": 7, "spent": 1}
    assert gathered_xianxia["advancement_history"][-1] == {
        "action": "gathering_insight",
        "amount": 4,
        "target": "Insight",
        "downtime": "3 days between sessions",
        "notes": "Meditated under storm clouds.",
    }

    energy_status, energy_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 3,
            "action": "spend_cultivation_energy",
            "values": {
                "energy_key": " Qi ",
                "cultivation_energy_notes": "  Opened   the\n inner\tbreath gate.  ",
            },
        },
    )
    assert energy_status == 200
    assert energy_payload["ok"] is True
    assert energy_payload["message"] == "Spent 1 Insight on Cultivation to increase Qi."
    assert energy_payload["anchor"] == "xianxia-cultivation-energy"
    assert energy_payload["character"]["state_record"]["revision"] == initial_revision + 4
    energy_xianxia = energy_payload["character"]["definition"]["xianxia"]
    assert energy_xianxia["insight"] == {"available": 6, "spent": 2}
    assert energy_xianxia["energies"] == {
        "jing": {"max": 1},
        "qi": {"max": 2},
        "shen": {"max": 1},
    }
    assert energy_payload["cultivation"]["insight"] == {"available": 6, "spent": 2}
    qi_context = next(row for row in energy_payload["cultivation"]["energies"] if row["key"] == "qi")
    assert qi_context["current"] == 1
    assert qi_context["max"] == 2
    assert energy_payload["character"]["state_record"]["state"]["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert energy_xianxia["advancement_history"][-1] == {
        "action": "cultivation_energy_increase",
        "amount": 1,
        "target": "Qi",
        "energy_key": "qi",
        "energy_maximum_increase": 1,
        "new_energy_maximum": 2,
        "notes": "Opened the inner breath gate.",
    }

    invalid_energy_status, invalid_energy_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 4,
            "cultivation_action": "spend_cultivation_energy",
            "energy_key": "body",
        },
    )
    assert invalid_energy_status == 400
    assert invalid_energy_payload["error"]["code"] == "validation_error"
    assert invalid_energy_payload["error"]["message"] == "Choose Jing, Qi, or Shen for Cultivation."

    zero_insight_save_status, zero_insight_save_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 4,
            "action": "save_insight",
            "values": {"insight_available": "0", "insight_spent": "2"},
        },
    )
    assert zero_insight_save_status == 200
    assert zero_insight_save_payload["character"]["state_record"]["revision"] == initial_revision + 5

    insufficient_energy_status, insufficient_energy_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 5,
            "cultivation_action": "spend_cultivation_energy",
            "energy_key": "qi",
        },
    )
    assert insufficient_energy_status == 400
    assert insufficient_energy_payload["error"]["code"] == "validation_error"
    assert (
        insufficient_energy_payload["error"]["message"]
        == "Cultivation needs 1 Insight to increase Qi; only 0 available."
    )

    restore_insight_status, restore_insight_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 5,
            "action": "save_insight",
            "values": {"insight_available": "2", "insight_spent": "2"},
        },
    )
    assert restore_insight_status == 200
    assert restore_insight_payload["character"]["state_record"]["revision"] == initial_revision + 6

    meditation_status, meditation_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 6,
            "cultivation_action": "spend_meditation_yin_yang",
            "yin_yang_key": " Yang ",
            "meditation_notes": "  Balanced   breath\n at\tdawn.  ",
        },
    )
    assert meditation_status == 200
    assert meditation_payload["ok"] is True
    assert meditation_payload["message"] == "Spent 1 Insight on Meditation to increase Yang."
    assert meditation_payload["anchor"] == "xianxia-cultivation-meditation"
    assert meditation_payload["character"]["state_record"]["revision"] == initial_revision + 7
    meditation_xianxia = meditation_payload["character"]["definition"]["xianxia"]
    assert meditation_xianxia["insight"] == {"available": 1, "spent": 3}
    assert meditation_xianxia["yin_yang"] == {"yin_max": 1, "yang_max": 2}
    assert meditation_payload["cultivation"]["insight"] == {"available": 1, "spent": 3}
    yang_context = next(row for row in meditation_payload["cultivation"]["yin_yang"] if row["key"] == "yang")
    assert yang_context["current"] == 1
    assert yang_context["max"] == 2
    assert meditation_payload["character"]["state_record"]["state"]["xianxia"]["yin_yang"] == {
        "yin_current": 1,
        "yang_current": 1,
    }
    assert meditation_xianxia["advancement_history"][-1] == {
        "action": "meditation_yin_yang_increase",
        "amount": 1,
        "target": "Yang",
        "yin_yang_key": "yang",
        "yin_yang_maximum_increase": 1,
        "new_yin_yang_maximum": 2,
        "notes": "Balanced breath at dawn.",
    }

    invalid_meditation_status, invalid_meditation_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 7,
            "cultivation_action": "spend_meditation_yin_yang",
            "yin_yang_key": "moon",
        },
    )
    assert invalid_meditation_status == 400
    assert invalid_meditation_payload["error"]["code"] == "validation_error"
    assert invalid_meditation_payload["error"]["message"] == "Choose Yin or Yang for Meditation."

    zero_meditation_insight_status, zero_meditation_insight_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 7,
            "action": "save_insight",
            "values": {"insight_available": "0", "insight_spent": "3"},
        },
    )
    assert zero_meditation_insight_status == 200
    assert zero_meditation_insight_payload["character"]["state_record"]["revision"] == initial_revision + 8

    insufficient_meditation_status, insufficient_meditation_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 8,
            "cultivation_action": "spend_meditation_yin_yang",
            "yin_yang_key": "yin",
        },
    )
    assert insufficient_meditation_status == 400
    assert insufficient_meditation_payload["error"]["code"] == "validation_error"
    assert (
        insufficient_meditation_payload["error"]["message"]
        == "Meditation needs 1 Insight to increase Yin; only 0 available."
    )

    invalid_conditioning_target_status, invalid_conditioning_target_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 8,
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "body",
        },
    )
    assert invalid_conditioning_target_status == 400
    assert invalid_conditioning_target_payload["error"]["code"] == "validation_error"
    assert (
        invalid_conditioning_target_payload["error"]["message"]
        == "Choose HP or an Effort for Conditioning."
    )

    restore_conditioning_insight_status, restore_conditioning_insight_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 8,
            "action": "save_insight",
            "values": {"insight_available": "3", "insight_spent": "3"},
        },
    )
    assert restore_conditioning_insight_status == 200
    assert restore_conditioning_insight_payload["character"]["state_record"]["revision"] == initial_revision + 9

    conditioning_hp_status, conditioning_hp_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 9,
            "action": "spend_conditioning",
            "values": {
                "conditioning_target": " HP ",
                "conditioning_notes": "  Stone-body   breathing\n beside\tthe falls.  ",
            },
        },
    )
    assert conditioning_hp_status == 200
    assert conditioning_hp_payload["ok"] is True
    assert conditioning_hp_payload["message"] == "Spent 1 Insight on Conditioning to increase HP."
    assert conditioning_hp_payload["anchor"] == "xianxia-cultivation-conditioning"
    assert conditioning_hp_payload["character"]["state_record"]["revision"] == initial_revision + 10
    conditioning_hp_xianxia = conditioning_hp_payload["character"]["definition"]["xianxia"]
    assert conditioning_hp_xianxia["insight"] == {"available": 2, "spent": 4}
    assert conditioning_hp_xianxia["durability"]["hp_max"] == 20
    assert conditioning_hp_xianxia["efforts"]["magic"] == 1
    hp_context = conditioning_hp_payload["cultivation"]["conditioning"]["hp"]
    assert hp_context["current"] == 10
    assert hp_context["max"] == 20
    assert hp_context["projected_max"] == 30
    assert conditioning_hp_payload["character"]["state_record"]["state"]["vitals"]["current_hp"] == 10
    assert conditioning_hp_payload["character"]["state_record"]["state"]["xianxia"]["vitals"]["current_hp"] == 10
    assert conditioning_hp_xianxia["advancement_history"][-1] == {
        "action": "conditioning_hp_increase",
        "amount": 1,
        "target": "HP",
        "hp_maximum_increase": 10,
        "new_hp_maximum": 20,
        "hp_maximum_cap": 50,
        "notes": "Stone-body breathing beside the falls.",
    }

    conditioning_effort_status, conditioning_effort_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 10,
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "effort",
            "effort_key": "Magic",
            "conditioning_notes": "  Refined   spell-force\n output.  ",
        },
    )
    assert conditioning_effort_status == 200
    assert conditioning_effort_payload["ok"] is True
    assert conditioning_effort_payload["message"] == "Spent 1 Insight on Conditioning to increase Magic."
    assert conditioning_effort_payload["anchor"] == "xianxia-cultivation-conditioning"
    assert conditioning_effort_payload["character"]["state_record"]["revision"] == initial_revision + 11
    conditioning_effort_xianxia = conditioning_effort_payload["character"]["definition"]["xianxia"]
    assert conditioning_effort_xianxia["insight"] == {"available": 1, "spent": 5}
    assert conditioning_effort_xianxia["durability"]["hp_max"] == 20
    assert conditioning_effort_xianxia["efforts"]["magic"] == 3
    magic_context = next(
        row for row in conditioning_effort_payload["cultivation"]["conditioning"]["efforts"] if row["key"] == "magic"
    )
    assert magic_context["score"] == 3
    assert conditioning_effort_xianxia["advancement_history"][-1] == {
        "action": "conditioning_effort_increase",
        "amount": 1,
        "target": "Magic",
        "effort_key": "magic",
        "effort_point_increase": 2,
        "new_effort_score": 3,
        "notes": "Refined spell-force output.",
    }

    invalid_conditioning_effort_status, invalid_conditioning_effort_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 11,
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "effort",
            "effort_key": "body",
        },
    )
    assert invalid_conditioning_effort_status == 400
    assert invalid_conditioning_effort_payload["error"]["code"] == "validation_error"
    assert invalid_conditioning_effort_payload["error"]["message"] == "Choose a valid Effort for Conditioning."

    zero_conditioning_insight_status, zero_conditioning_insight_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 11,
            "action": "save_insight",
            "values": {"insight_available": "0", "insight_spent": "5"},
        },
    )
    assert zero_conditioning_insight_status == 200
    assert zero_conditioning_insight_payload["character"]["state_record"]["revision"] == initial_revision + 12

    insufficient_conditioning_status, insufficient_conditioning_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 12,
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "effort",
            "effort_key": "magic",
        },
    )
    assert insufficient_conditioning_status == 400
    assert insufficient_conditioning_payload["error"]["code"] == "validation_error"
    assert (
        insufficient_conditioning_payload["error"]["message"]
        == "Conditioning needs 1 Insight to increase Magic; only 0 available."
    )

    insufficient_conditioning_precedes_invalid_effort_status, insufficient_conditioning_precedes_invalid_effort_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 12,
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "effort",
            "effort_key": "body",
        },
    )
    assert insufficient_conditioning_precedes_invalid_effort_status == 400
    assert insufficient_conditioning_precedes_invalid_effort_payload["error"]["code"] == "validation_error"
    assert (
        insufficient_conditioning_precedes_invalid_effort_payload["error"]["message"]
        == "Conditioning needs 1 Insight to increase Body; only 0 available."
    )

    invalid_training_target_status, invalid_training_target_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 12,
            "cultivation_action": "spend_training",
            "training_target": "body",
        },
    )
    assert invalid_training_target_status == 400
    assert invalid_training_target_payload["error"]["code"] == "validation_error"
    assert invalid_training_target_payload["error"]["message"] == "Choose Stance or an Attribute for Training."

    restore_training_insight_status, restore_training_insight_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 12,
            "action": "save_insight",
            "values": {"insight_available": "3", "insight_spent": "5"},
        },
    )
    assert restore_training_insight_status == 200
    assert restore_training_insight_payload["character"]["state_record"]["revision"] == initial_revision + 13

    training_stance_status, training_stance_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 13,
            "action": "spend_training",
            "values": {
                "training_target": " Stance ",
                "training_notes": "  Rooted   stance\n drills.  ",
            },
        },
    )
    assert training_stance_status == 200
    assert training_stance_payload["ok"] is True
    assert training_stance_payload["message"] == "Spent 1 Insight on Training to increase Stance."
    assert training_stance_payload["anchor"] == "xianxia-cultivation-training"
    assert training_stance_payload["character"]["state_record"]["revision"] == initial_revision + 14
    training_stance_xianxia = training_stance_payload["character"]["definition"]["xianxia"]
    assert training_stance_xianxia["insight"] == {"available": 2, "spent": 6}
    assert training_stance_xianxia["durability"]["stance_max"] == 20
    assert training_stance_xianxia["attributes"]["str"] == 1
    stance_context = training_stance_payload["cultivation"]["training"]["stance"]
    assert stance_context["current"] == 10
    assert stance_context["max"] == 20
    assert stance_context["projected_max"] == 30
    assert training_stance_payload["character"]["state_record"]["state"]["xianxia"]["vitals"]["current_stance"] == 10
    assert training_stance_xianxia["advancement_history"][-1] == {
        "action": "training_stance_increase",
        "amount": 1,
        "target": "Stance",
        "stance_maximum_increase": 10,
        "new_stance_maximum": 20,
        "stance_maximum_cap": 50,
        "notes": "Rooted stance drills.",
    }

    training_attribute_status, training_attribute_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 14,
            "cultivation_action": "spend_training",
            "training_target": "attribute",
            "attribute_key": "STR",
            "training_notes": "  Iron   frame\n practice.  ",
        },
    )
    assert training_attribute_status == 200
    assert training_attribute_payload["ok"] is True
    assert training_attribute_payload["message"] == "Spent 1 Insight on Training to increase Strength."
    assert training_attribute_payload["anchor"] == "xianxia-cultivation-training"
    assert training_attribute_payload["character"]["state_record"]["revision"] == initial_revision + 15
    training_attribute_xianxia = training_attribute_payload["character"]["definition"]["xianxia"]
    assert training_attribute_xianxia["insight"] == {"available": 1, "spent": 7}
    assert training_attribute_xianxia["durability"]["stance_max"] == 20
    assert training_attribute_xianxia["attributes"]["str"] == 3
    strength_context = next(
        row for row in training_attribute_payload["cultivation"]["training"]["attributes"] if row["key"] == "str"
    )
    assert strength_context["score"] == 3
    assert training_attribute_payload["character"]["state_record"]["state"]["xianxia"]["vitals"]["current_stance"] == 10
    assert training_attribute_xianxia["advancement_history"][-1] == {
        "action": "training_attribute_increase",
        "amount": 1,
        "target": "Strength",
        "attribute_key": "str",
        "attribute_point_increase": 2,
        "new_attribute_score": 3,
        "notes": "Iron frame practice.",
    }

    invalid_training_attribute_status, invalid_training_attribute_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 15,
            "cultivation_action": "spend_training",
            "training_target": "attribute",
            "attribute_key": "body",
        },
    )
    assert invalid_training_attribute_status == 400
    assert invalid_training_attribute_payload["error"]["code"] == "validation_error"
    assert invalid_training_attribute_payload["error"]["message"] == "Choose a valid Attribute for Training."

    zero_training_insight_status, zero_training_insight_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 15,
            "action": "save_insight",
            "values": {"insight_available": "0", "insight_spent": "7"},
        },
    )
    assert zero_training_insight_status == 200
    assert zero_training_insight_payload["character"]["state_record"]["revision"] == initial_revision + 16

    insufficient_training_status, insufficient_training_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 16,
            "cultivation_action": "spend_training",
            "training_target": "attribute",
            "attribute_key": "str",
        },
    )
    assert insufficient_training_status == 400
    assert insufficient_training_payload["error"]["code"] == "validation_error"
    assert (
        insufficient_training_payload["error"]["message"]
        == "Training needs 1 Insight to increase Strength; only 0 available."
    )

    insufficient_training_precedes_invalid_attribute_status, insufficient_training_precedes_invalid_attribute_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 16,
            "cultivation_action": "spend_training",
            "training_target": "attribute",
            "attribute_key": "body",
        },
    )
    assert insufficient_training_precedes_invalid_attribute_status == 400
    assert insufficient_training_precedes_invalid_attribute_payload["error"]["code"] == "validation_error"
    assert (
        insufficient_training_precedes_invalid_attribute_payload["error"]["message"]
        == "Training needs 1 Insight to increase Body; only 0 available."
    )

    missing_martial_art_status, missing_martial_art_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 16,
            "cultivation_action": "advance_martial_art_rank",
            "target_rank_key": "novice",
        },
    )
    assert missing_martial_art_status == 400
    assert missing_martial_art_payload["error"]["code"] == "validation_error"
    assert missing_martial_art_payload["error"]["message"] == "Martial Art selection is required."

    invalid_martial_art_rank_status, invalid_martial_art_rank_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 16,
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "dragon",
        },
    )
    assert invalid_martial_art_rank_status == 400
    assert invalid_martial_art_rank_payload["error"]["code"] == "validation_error"
    assert invalid_martial_art_rank_payload["error"]["message"] == "Choose a valid Martial Art rank to advance."

    insufficient_martial_art_status, insufficient_martial_art_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 16,
            "cultivation_action": "advance_martial_art_rank",
            "martial_art_index": "0",
            "target_rank_key": "novice",
        },
    )
    assert insufficient_martial_art_status == 400
    assert insufficient_martial_art_payload["error"]["code"] == "validation_error"
    assert (
        insufficient_martial_art_payload["error"]["message"]
        == "Cloud Palm needs 1 Insight to advance to Novice; only 0 available."
    )

    restore_martial_art_insight_status, restore_martial_art_insight_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 16,
            "action": "save_insight",
            "values": {"insight_available": "1", "insight_spent": "7"},
        },
    )
    assert restore_martial_art_insight_status == 200
    assert restore_martial_art_insight_payload["character"]["state_record"]["revision"] == initial_revision + 17

    martial_art_status, martial_art_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 17,
            "action": "advance_martial_art_rank",
            "values": {
                "martial_art_index": "0",
                "target_rank_key": "novice",
            },
        },
    )
    assert martial_art_status == 200
    assert martial_art_payload["ok"] is True
    assert martial_art_payload["message"] == "Spent 1 Insight to advance Cloud Palm to Novice."
    assert martial_art_payload["anchor"] == "xianxia-cultivation-martial-arts"
    assert martial_art_payload["character"]["state_record"]["revision"] == initial_revision + 18
    martial_art_xianxia = martial_art_payload["character"]["definition"]["xianxia"]
    assert martial_art_xianxia["insight"] == {"available": 0, "spent": 8}
    assert martial_art_xianxia["energies"] == {
        "jing": {"max": 2},
        "qi": {"max": 2},
        "shen": {"max": 1},
    }
    learned_art = martial_art_xianxia["martial_arts"][0]
    assert learned_art["current_rank_key"] == "novice"
    assert learned_art["current_rank"] == "Novice"
    assert learned_art["learned_rank_refs"] == [
        "systems:xia-cloud-palm:initiate",
        "systems:xia-cloud-palm:novice",
    ]
    assert learned_art["rank_energy_maximum_increases"] == {
        "novice": {"jing": 1, "qi": 0, "shen": 0}
    }
    assert learned_art["insight_spent"] == 1
    assert learned_art["systems_ref"]["entry_key"] == "XIA:martial_art:cloud-palm"
    assert martial_art_payload["character"]["state_record"]["state"]["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    martial_art_context = martial_art_payload["cultivation"]["martial_arts"][0]
    assert martial_art_context["current_rank_key"] == "novice"
    assert martial_art_xianxia["advancement_history"][-1] == {
        "action": "martial_art_rank_advance",
        "amount": 1,
        "target": "Cloud Palm",
        "rank": "Novice",
        "energy_maximum_increases": {"jing": 1, "qi": 0, "shen": 0},
        "rank_ref": "systems:xia-cloud-palm:novice",
        "systems_ref": learned_art["systems_ref"],
    }

    missing_generic_technique_status, missing_generic_technique_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 18,
            "cultivation_action": "learn_generic_technique",
        },
    )
    assert missing_generic_technique_status == 400
    assert missing_generic_technique_payload["error"]["code"] == "validation_error"
    assert missing_generic_technique_payload["error"]["message"] == "Choose a Generic Technique to learn."

    unknown_generic_technique_status, unknown_generic_technique_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 18,
            "cultivation_action": "learn_generic_technique",
            "generic_technique_entry_key": "XIA:generic_technique:unknown",
        },
    )
    assert unknown_generic_technique_status == 400
    assert unknown_generic_technique_payload["error"]["code"] == "validation_error"
    assert unknown_generic_technique_payload["error"]["message"] == "Choose an available Generic Technique to learn."

    duplicate_generic_technique_status, duplicate_generic_technique_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 18,
            "cultivation_action": "learn_generic_technique",
            "generic_technique_entry_key": "XIA:generic_technique:qi-blast",
        },
    )
    assert duplicate_generic_technique_status == 400
    assert duplicate_generic_technique_payload["error"]["code"] == "validation_error"
    assert duplicate_generic_technique_payload["error"]["message"] == "Qi Blast is already learned."

    direct_generic_technique_status, direct_generic_technique_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 18,
            "cultivation_action": "learn_generic_technique",
            "generic_technique_entry_key": "XIA:generic_technique:cultivation",
        },
    )
    assert direct_generic_technique_status == 400
    assert direct_generic_technique_payload["error"]["code"] == "validation_error"
    assert (
        direct_generic_technique_payload["error"]["message"]
        == "Use the dedicated Cultivation spend form for this Insight spend."
    )

    insufficient_generic_technique_status, insufficient_generic_technique_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 18,
            "cultivation_action": "learn_generic_technique",
            "generic_technique_entry_key": "XIA:generic_technique:meteor-step",
        },
    )
    assert insufficient_generic_technique_status == 400
    assert insufficient_generic_technique_payload["error"]["code"] == "validation_error"
    assert (
        insufficient_generic_technique_payload["error"]["message"]
        == "Meteor Step needs 2 Insight to learn; only 0 available."
    )

    restore_generic_technique_insight_status, restore_generic_technique_insight_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 18,
            "action": "save_insight",
            "values": {"insight_available": "2", "insight_spent": "8"},
        },
    )
    assert restore_generic_technique_insight_status == 200
    assert restore_generic_technique_insight_payload["character"]["state_record"]["revision"] == initial_revision + 19

    generic_technique_status, generic_technique_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 19,
            "action": "learn_generic_technique",
            "values": {
                "generic_technique_entry_key": "XIA:generic_technique:meteor-step",
                "generic_technique_notes": "  Stepped   through\n falling\tlight.  ",
            },
        },
    )
    assert generic_technique_status == 200
    assert generic_technique_payload["ok"] is True
    assert generic_technique_payload["message"] == "Spent 2 Insight to learn Meteor Step."
    assert generic_technique_payload["anchor"] == "xianxia-cultivation-techniques"
    assert generic_technique_payload["character"]["state_record"]["revision"] == initial_revision + 20
    generic_technique_xianxia = generic_technique_payload["character"]["definition"]["xianxia"]
    assert generic_technique_xianxia["insight"] == {"available": 0, "spent": 10}
    learned_technique = generic_technique_xianxia["generic_techniques"][-1]
    assert learned_technique == {
        "name": "Meteor Step",
        "systems_ref": {
            "library_slug": "Xianxia",
            "source_id": "XIA",
            "entry_key": "XIA:generic_technique:meteor-step",
            "slug": "xia-generic-technique-meteor-step",
            "title": "Meteor Step",
            "entry_type": "generic_technique",
        },
        "generic_technique_key": "meteor_step",
        "insight_spent": 2,
        "support_state": "supported",
        "learnable_without_master": True,
        "requires_master": False,
        "notes": "Stepped through falling light.",
    }
    refreshed_option_keys = {
        option["generic_technique_key"]
        for option in generic_technique_payload["cultivation"]["generic_technique_options"]
    }
    assert "meteor_step" not in refreshed_option_keys
    assert generic_technique_payload["character"]["state_record"]["state"]["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert generic_technique_xianxia["advancement_history"][-1] == {
        "action": "generic_technique_learned",
        "amount": 2,
        "target": "Meteor Step",
        "generic_technique_key": "meteor_step",
        "systems_ref": learned_technique["systems_ref"],
        "insight_cost": 2,
        "notes": "Stepped through falling light.",
    }

    low_realm_slug = "api-cultivation-realm-low"
    low_realm_body = deepcopy(xianxia_body)
    low_realm_body["definition"]["name"] = "API Cultivation Realm Low"
    low_realm_body["definition"]["xianxia"]["attributes"] = {
        "str": 9,
        "dex": 2,
        "con": 1,
        "int": 1,
        "wis": 1,
        "cha": 1,
    }
    low_realm_body["definition"]["xianxia"]["efforts"] = {
        "basic": 8,
        "weapon": 1,
        "guns_explosive": 1,
        "magic": 1,
        "ultimate": 1,
    }
    low_realm_create_status, _low_realm_create_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{low_realm_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=low_realm_body,
    )
    assert low_realm_create_status == 200
    low_realm_status, low_realm_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{low_realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
    )
    assert low_realm_status == 200
    low_realm_revision = low_realm_payload["character"]["state_record"]["revision"]
    low_prerequisite_status, low_prerequisite_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{low_realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": low_realm_revision,
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": "GM approved the review.",
        },
    )
    assert low_prerequisite_status == 400
    assert low_prerequisite_payload["error"]["code"] == "validation_error"
    assert (
        low_prerequisite_payload["error"]["message"]
        == "Realm ascension prerequisite not met: raise at least one Attribute or Effort to 10 before ascending from Mortal to Immortal. Current highest Stat is Strength at 9."
    )
    assert _read_sqlite_character_state(
        typescript_api_mutation_server["db_path"],
        low_realm_slug,
    )["revision"] == low_realm_revision

    realm_slug = "api-cultivation-realm"
    realm_body = deepcopy(xianxia_body)
    realm_body["definition"]["name"] = "API Cultivation Realm"
    realm_xianxia = realm_body["definition"]["xianxia"]
    realm_xianxia["actions_per_turn"] = 2
    realm_xianxia["attributes"] = {
        "str": 10,
        "dex": 2,
        "con": 4,
        "int": 1,
        "wis": 3,
        "cha": 1,
    }
    realm_xianxia["efforts"] = {
        "basic": 4,
        "weapon": 3,
        "guns_explosive": 2,
        "magic": 5,
        "ultimate": 1,
    }
    realm_xianxia["energies"] = {"jing": {"max": 4}, "qi": {"max": 5}, "shen": {"max": 6}}
    realm_xianxia["yin_yang"] = {"yin_max": 3, "yang_max": 4}
    realm_xianxia["dao"] = {"max": 4}
    realm_xianxia["insight"] = {"available": 11, "spent": 7}
    realm_xianxia["durability"] = {
        "hp_max": 32,
        "stance_max": 34,
        "manual_armor_bonus": 2,
        "defense": 16,
    }
    realm_xianxia["skills"] = {"trained": ["Qi Sense", "Balance"]}
    realm_xianxia["equipment"] = {
        "necessary_weapons": [{"name": "Practice Staff"}],
        "necessary_tools": [{"name": "Meditation Mat"}],
    }
    realm_xianxia["variants"] = [{"name": "Approved variant", "status": "approved"}]
    realm_xianxia["dao_immolating_techniques"] = {
        "prepared": [{"name": "Last Dawn"}],
        "use_history": [{"name": "Old Flame", "approval_status": "pending"}],
    }
    realm_xianxia["approval_requests"] = [{"name": "Constraint", "status": "pending"}]
    realm_xianxia["companions"] = [{"name": "Paper Crane"}]
    realm_create_status, _realm_create_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{realm_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=realm_body,
    )
    assert realm_create_status == 200
    realm_status, realm_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
    )
    assert realm_status == 200
    realm_revision = realm_payload["character"]["state_record"]["revision"]
    realm_state = deepcopy(realm_payload["character"]["state_record"]["state"])
    realm_state["vitals"] = {"current_hp": 21, "temp_hp": 4}
    realm_state["notes"]["player_notes_markdown"] = "Preserve this note."
    realm_state["xianxia"]["vitals"] = {
        "current_hp": 21,
        "temp_hp": 4,
        "current_stance": 18,
        "temp_stance": 3,
    }
    realm_state["xianxia"]["energies"] = {
        "jing": {"current": 2},
        "qi": {"current": 3},
        "shen": {"current": 4},
    }
    realm_state["xianxia"]["yin_yang"] = {"yin_current": 2, "yang_current": 3}
    realm_state["xianxia"]["dao"] = {"current": 2}
    realm_state["xianxia"]["active_stance"] = {"name": "Mountain Root"}
    realm_state["xianxia"]["active_aura"] = {"name": "Quiet Moon"}
    realm_state["xianxia"]["notes"] = {"player_notes_markdown": "Preserve this note."}
    _write_sqlite_character_state(
        typescript_api_mutation_server["db_path"],
        realm_slug,
        revision=realm_revision,
        state=realm_state,
    )

    wrong_realm_review_status, wrong_realm_review_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision,
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Divine",
            "realm_ascension_gm_review_note": "Trying to skip Immortal.",
        },
    )
    assert wrong_realm_review_status == 400
    assert wrong_realm_review_payload["error"]["code"] == "validation_error"
    assert (
        wrong_realm_review_payload["error"]["message"]
        == "Realm ascension must move from Mortal to Immortal."
    )

    blank_realm_review_status, blank_realm_review_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision,
            "cultivation_action": "start_realm_ascension_review",
            "target_realm": "Immortal",
            "realm_ascension_gm_review_note": "   ",
        },
    )
    assert blank_realm_review_status == 400
    assert blank_realm_review_payload["error"]["code"] == "validation_error"
    assert (
        blank_realm_review_payload["error"]["message"]
        == "Record a GM review note before starting Realm ascension review."
    )

    realm_review_status, realm_review_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision,
            "action": "start_realm_ascension_review",
            "values": {
                "target_realm": "Immortal",
                "realm_ascension_gm_review_note": "  GM   approved\n Mortal to\tImmortal review.  ",
                "realm_ascension_seclusion_notes": "  One   year\n seclusion.  ",
                "realm_ascension_hp_stance_trade_notes": "  Trade   later.  ",
            },
        },
    )
    assert realm_review_status == 200
    assert realm_review_payload["ok"] is True
    assert realm_review_payload["message"] == "Started Realm ascension review from Mortal to Immortal."
    assert realm_review_payload["anchor"] == "xianxia-cultivation-realm-ascension"
    assert realm_review_payload["character"]["state_record"]["revision"] == realm_revision + 1
    realm_review_xianxia = realm_review_payload["character"]["definition"]["xianxia"]
    assert realm_review_xianxia["attributes"] == realm_xianxia["attributes"]
    assert realm_review_xianxia["efforts"] == realm_xianxia["efforts"]
    assert realm_review_xianxia["advancement_history"][-1] == {
        "action": "realm_ascension_review_started",
        "target": "Immortal",
        "current_realm": "Mortal",
        "target_realm": "Immortal",
        "status": "pending_gm_review",
        "seclusion_time": "1 year",
        "rebuild_budget": 15,
        "stat_cap": 6,
        "actions_per_turn": 3,
        "stat_max_prerequisite": {
            "required_score": 10,
            "met": True,
            "stat_kind": "Attribute",
            "stat_key": "str",
            "stat_label": "Strength",
            "stat_score": 10,
        },
        "gm_review_note": "GM approved Mortal to Immortal review.",
        "seclusion_notes": "One year seclusion.",
        "hp_stance_trade_notes": "Trade later.",
    }
    assert realm_review_payload["cultivation"]["realm_ascension"]["can_reset_stats"] is True

    stale_realm_reset_status, stale_realm_reset_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision,
            "cultivation_action": "reset_realm_ascension_stats",
            "target_realm": "Immortal",
        },
    )
    assert stale_realm_reset_status == 409
    assert stale_realm_reset_payload["error"]["code"] == "state_conflict"

    realm_reset_status, realm_reset_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision + 1,
            "cultivation_action": "reset_realm_ascension_stats",
            "target_realm": "Immortal",
            "realm_ascension_reset_notes": "  Reset   for\n rebuild.  ",
        },
    )
    assert realm_reset_status == 200
    assert realm_reset_payload["ok"] is True
    assert (
        realm_reset_payload["message"]
        == "Reset Attributes and Efforts for Mortal to Immortal Realm ascension."
    )
    assert realm_reset_payload["anchor"] == "xianxia-cultivation-realm-ascension"
    assert realm_reset_payload["character"]["state_record"]["revision"] == realm_revision + 2
    realm_reset_xianxia = realm_reset_payload["character"]["definition"]["xianxia"]
    assert realm_reset_xianxia["attributes"] == {
        "str": 0,
        "dex": 0,
        "con": 0,
        "int": 0,
        "wis": 0,
        "cha": 0,
    }
    assert realm_reset_xianxia["efforts"] == {
        "basic": 0,
        "weapon": 0,
        "guns_explosive": 0,
        "magic": 0,
        "ultimate": 0,
    }
    assert realm_reset_xianxia["energies"] == realm_xianxia["energies"]
    assert realm_reset_xianxia["yin_yang"] == realm_xianxia["yin_yang"]
    assert realm_reset_xianxia["insight"] == realm_xianxia["insight"]
    assert realm_reset_xianxia["martial_arts"] == realm_xianxia["martial_arts"]
    assert realm_reset_xianxia["generic_techniques"] == realm_xianxia["generic_techniques"]
    assert realm_reset_xianxia["variants"] == realm_xianxia["variants"]
    assert realm_reset_xianxia["approval_requests"] == realm_xianxia["approval_requests"]
    assert realm_reset_xianxia["companions"] == realm_xianxia["companions"]
    reset_history = realm_reset_xianxia["advancement_history"][-1]
    assert reset_history["action"] == "realm_ascension_attributes_efforts_reset"
    assert reset_history["target"] == "Immortal"
    assert reset_history["current_realm"] == "Mortal"
    assert reset_history["target_realm"] == "Immortal"
    assert reset_history["status"] == "pending_rebuild"
    assert reset_history["attributes_before_total"] == 21
    assert reset_history["attributes_after_total"] == 0
    assert reset_history["efforts_before_total"] == 15
    assert reset_history["efforts_after_total"] == 0
    assert reset_history["reset_scope"] == "Attributes and Efforts"
    assert reset_history["preserved_scope"] == (
        "Energies, Yin/Yang, HP, Stance, Insight, Martial Arts, Generic Techniques, "
        "variants, approval records, and notes"
    )
    assert (
        reset_history["pre_ascension_summary"]
        == "Mortal Realm, 2 actions; Attributes 21, Efforts 15; HP max 32, Stance max 34; Insight 11 available/7 spent; Martial Arts 1; Generic Techniques 1"
    )
    assert reset_history["notes"] == "Reset for rebuild."
    pre_ascension_state = reset_history["pre_ascension_state"]
    assert pre_ascension_state["attributes"] == realm_xianxia["attributes"]
    assert pre_ascension_state["efforts"] == realm_xianxia["efforts"]
    assert pre_ascension_state["energies"] == realm_xianxia["energies"]
    assert pre_ascension_state["yin_yang"] == realm_xianxia["yin_yang"]
    assert pre_ascension_state["insight"] == realm_xianxia["insight"]
    assert pre_ascension_state["durability"]["hp_max"] == 32
    assert pre_ascension_state["durability"]["stance_max"] == 34
    assert pre_ascension_state["martial_arts"] == realm_xianxia["martial_arts"]
    assert pre_ascension_state["generic_techniques"] == realm_xianxia["generic_techniques"]
    realm_reset_state = realm_reset_payload["character"]["state_record"]["state"]
    assert realm_reset_state["vitals"] == {"current_hp": 21, "temp_hp": 4}
    assert realm_reset_state["notes"]["player_notes_markdown"] == "Preserve this note."
    assert realm_reset_state["xianxia"]["vitals"] == {
        "current_hp": 21,
        "temp_hp": 4,
        "current_stance": 18,
        "temp_stance": 3,
    }
    assert realm_reset_state["xianxia"]["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 3},
        "shen": {"current": 4},
    }
    assert realm_reset_state["xianxia"]["yin_yang"] == {"yin_current": 2, "yang_current": 3}
    assert realm_reset_state["xianxia"]["dao"] == {"current": 2}
    assert realm_reset_state["xianxia"]["active_stance"] == {"name": "Mountain Root"}
    assert realm_reset_state["xianxia"]["active_aura"] == {"name": "Quiet Moon"}
    assert realm_reset_state["xianxia"]["notes"] == {"player_notes_markdown": "Preserve this note."}
    assert realm_reset_payload["cultivation"]["realm_ascension"]["can_apply_immortal_rebuild"] is True

    duplicate_realm_reset_status, duplicate_realm_reset_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision + 2,
            "cultivation_action": "reset_realm_ascension_stats",
            "target_realm": "Immortal",
        },
    )
    assert duplicate_realm_reset_status == 400
    assert duplicate_realm_reset_payload["error"]["code"] == "validation_error"
    assert (
        duplicate_realm_reset_payload["error"]["message"]
        == "Attributes and Efforts have already been reset for this Realm ascension review."
    )

    invalid_realm_rebuild_status, invalid_realm_rebuild_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision + 2,
            "cultivation_action": "apply_immortal_realm_rebuild",
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "7",
            "realm_rebuild_attribute_dex": "4",
            "realm_rebuild_attribute_con": "2",
            "realm_rebuild_attribute_int": "1",
            "realm_rebuild_attribute_wis": "1",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "1",
            "realm_rebuild_effort_weapon": "1",
            "realm_rebuild_effort_guns_explosive": "1",
            "realm_rebuild_effort_magic": "0",
            "realm_rebuild_effort_ultimate": "0",
            "realm_ascension_trade_hp": "5",
            "realm_ascension_trade_stance": "10",
        },
    )
    assert invalid_realm_rebuild_status == 400
    assert invalid_realm_rebuild_payload["error"]["code"] == "validation_error"
    assert "HP maximum trade must be 0 or a multiple of 10." in invalid_realm_rebuild_payload["error"]["message"]
    assert (
        "Strength cannot exceed 6 for the Immortal rebuild."
        in invalid_realm_rebuild_payload["error"]["message"]
    )
    assert (
        "Immortal rebuild must spend exactly 16 Attribute/Effort points; submitted 18."
        in invalid_realm_rebuild_payload["error"]["message"]
    )

    realm_rebuild_status, realm_rebuild_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision + 2,
            "action": "apply_immortal_realm_rebuild",
            "values": {
                "target_realm": "Immortal",
                "realm_rebuild_attribute_str": "6",
                "realm_rebuild_attribute_dex": "4",
                "realm_rebuild_attribute_con": "2",
                "realm_rebuild_attribute_int": "1",
                "realm_rebuild_attribute_wis": "1",
                "realm_rebuild_attribute_cha": "0",
                "realm_rebuild_effort_basic": "1",
                "realm_rebuild_effort_weapon": "1",
                "realm_rebuild_effort_guns_explosive": "1",
                "realm_rebuild_effort_magic": "0",
                "realm_rebuild_effort_ultimate": "0",
                "realm_ascension_trade_hp": "10",
                "realm_ascension_trade_stance": "10",
                "realm_ascension_rebuild_notes": "  Rebuilt   after\n seclusion.  ",
            },
        },
    )
    assert realm_rebuild_status == 200
    assert realm_rebuild_payload["ok"] is True
    assert realm_rebuild_payload["message"] == "Applied the Immortal rebuild budget for 17 points and 3 actions."
    assert realm_rebuild_payload["anchor"] == "xianxia-cultivation-realm-ascension"
    assert realm_rebuild_payload["character"]["state_record"]["revision"] == realm_revision + 3
    realm_rebuild_xianxia = realm_rebuild_payload["character"]["definition"]["xianxia"]
    assert realm_rebuild_xianxia["realm"] == "Immortal"
    assert realm_rebuild_xianxia["actions_per_turn"] == 3
    assert realm_rebuild_xianxia["attributes"] == {
        "str": 6,
        "dex": 4,
        "con": 2,
        "int": 1,
        "wis": 1,
        "cha": 0,
    }
    assert realm_rebuild_xianxia["efforts"] == {
        "basic": 1,
        "weapon": 1,
        "guns_explosive": 1,
        "magic": 0,
        "ultimate": 0,
    }
    assert realm_rebuild_xianxia["durability"]["hp_max"] == 22
    assert realm_rebuild_xianxia["durability"]["stance_max"] == 24
    assert realm_rebuild_xianxia["energies"] == realm_xianxia["energies"]
    assert realm_rebuild_xianxia["yin_yang"] == realm_xianxia["yin_yang"]
    assert realm_rebuild_xianxia["insight"] == realm_xianxia["insight"]
    rebuild_history = realm_rebuild_xianxia["advancement_history"][-1]
    assert rebuild_history["action"] == "realm_ascension_immortal_rebuild_applied"
    assert rebuild_history["target"] == "Immortal"
    assert rebuild_history["current_realm"] == "Mortal"
    assert rebuild_history["target_realm"] == "Immortal"
    assert rebuild_history["status"] == "applied_pending_final_confirmation"
    assert rebuild_history["rebuild_budget"] == 17
    assert rebuild_history["base_rebuild_budget"] == 15
    assert rebuild_history["stat_cap"] == 6
    assert rebuild_history["actions_per_turn"] == 3
    assert rebuild_history["attributes_after_total"] == 14
    assert rebuild_history["efforts_after_total"] == 3
    assert rebuild_history["total_rebuild_points"] == 17
    assert rebuild_history["hp_stance_trade_points"] == 2
    assert rebuild_history["hp_maximum_trade"] == 10
    assert rebuild_history["stance_maximum_trade"] == 10
    assert rebuild_history["hp_maximum_before"] == 32
    assert rebuild_history["hp_maximum_after"] == 22
    assert rebuild_history["stance_maximum_before"] == 34
    assert rebuild_history["stance_maximum_after"] == 24
    assert rebuild_history["pre_ascension_summary"] == reset_history["pre_ascension_summary"]
    assert rebuild_history["post_ascension_summary"] == (
        "Immortal Realm, 3 actions; Attributes 14, Efforts 3; HP max 22, Stance max 24; "
        "Insight 11 available/7 spent; Martial Arts 1; Generic Techniques 1"
    )
    assert rebuild_history["pre_ascension_state"]["realm"] == "Mortal"
    assert rebuild_history["post_ascension_state"]["realm"] == "Immortal"
    assert rebuild_history["notes"] == "Rebuilt after seclusion."
    realm_rebuild_state = realm_rebuild_payload["character"]["state_record"]["state"]
    assert realm_rebuild_state["vitals"] == {"current_hp": 21, "temp_hp": 4}
    assert realm_rebuild_state["xianxia"]["vitals"] == {
        "current_hp": 21,
        "temp_hp": 4,
        "current_stance": 18,
        "temp_stance": 3,
    }
    assert realm_rebuild_state["xianxia"]["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 3},
        "shen": {"current": 4},
    }
    assert realm_rebuild_state["xianxia"]["yin_yang"] == {"yin_current": 2, "yang_current": 3}
    realm_rebuild_ascension = realm_rebuild_payload["cultivation"]["realm_ascension"]
    assert realm_rebuild_ascension["can_confirm_rebuild"] is True
    assert realm_rebuild_ascension["pending_confirmation_rebuild"]["target_realm"] == "Immortal"
    assert realm_rebuild_ascension["can_start_review"] is False
    assert realm_rebuild_ascension["confirmation_blocking_message"] == (
        "Confirm the latest Realm rebuild before starting another Realm review."
    )

    duplicate_realm_rebuild_status, duplicate_realm_rebuild_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision + 3,
            "cultivation_action": "apply_immortal_realm_rebuild",
            "target_realm": "Immortal",
            "realm_rebuild_attribute_str": "6",
            "realm_rebuild_attribute_dex": "4",
            "realm_rebuild_attribute_con": "2",
            "realm_rebuild_attribute_int": "1",
            "realm_rebuild_attribute_wis": "1",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "1",
            "realm_rebuild_effort_weapon": "1",
            "realm_rebuild_effort_guns_explosive": "1",
            "realm_rebuild_effort_magic": "0",
            "realm_rebuild_effort_ultimate": "0",
        },
    )
    assert duplicate_realm_rebuild_status == 400
    assert duplicate_realm_rebuild_payload["error"]["code"] == "validation_error"
    assert (
        duplicate_realm_rebuild_payload["error"]["message"]
        == "The Immortal rebuild budget applies only to Mortal to Immortal ascension."
    )

    blank_realm_confirmation_status, blank_realm_confirmation_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision + 3,
            "cultivation_action": "confirm_realm_ascension",
            "target_realm": "Immortal",
            "realm_ascension_gm_confirmation_note": "   ",
        },
    )
    assert blank_realm_confirmation_status == 400
    assert blank_realm_confirmation_payload["error"]["code"] == "validation_error"
    assert (
        blank_realm_confirmation_payload["error"]["message"]
        == "Record a GM confirmation note before confirming Realm ascension."
    )

    realm_confirmation_status, realm_confirmation_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision + 3,
            "cultivation_action": "confirm_realm_ascension",
            "target_realm": "Immortal",
            "realm_ascension_gm_confirmation_note": "Approved final ascension.",
        },
    )
    assert realm_confirmation_status == 200
    assert realm_confirmation_payload["ok"] is True
    assert realm_confirmation_payload["message"] == "Recorded GM confirmation for the Immortal Realm ascension."
    assert realm_confirmation_payload["anchor"] == "xianxia-cultivation-realm-ascension"
    assert realm_confirmation_payload["character"]["state_record"]["revision"] == realm_revision + 4
    realm_confirmation_xianxia = realm_confirmation_payload["character"]["definition"]["xianxia"]
    assert realm_confirmation_xianxia["realm"] == "Immortal"
    assert realm_confirmation_xianxia["actions_per_turn"] == 3
    assert realm_confirmation_xianxia["attributes"] == realm_rebuild_xianxia["attributes"]
    assert realm_confirmation_xianxia["efforts"] == realm_rebuild_xianxia["efforts"]
    assert realm_confirmation_xianxia["advancement_history"][-2]["action"] == "realm_ascension_immortal_rebuild_applied"
    assert realm_confirmation_xianxia["advancement_history"][-2]["status"] == "confirmed"
    confirmation_history = realm_confirmation_xianxia["advancement_history"][-1]
    assert confirmation_history == {
        "action": "realm_ascension_gm_confirmation_recorded",
        "target": "Immortal",
        "current_realm": "Mortal",
        "target_realm": "Immortal",
        "confirmed_realm": "Immortal",
        "status": "confirmed",
        "confirmed_rebuild_action": "realm_ascension_immortal_rebuild_applied",
        "confirmed_rebuild_index": len(realm_confirmation_xianxia["advancement_history"]) - 2,
        "actions_per_turn": 3,
        "attributes_after_total": 14,
        "efforts_after_total": 3,
        "gm_confirmation_note": "Approved final ascension.",
        "post_ascension_summary": (
            "Immortal Realm, 3 actions; Attributes 14, Efforts 3; HP max 22, Stance max 24; "
            "Insight 11 available/7 spent; Martial Arts 1; Generic Techniques 1"
        ),
    }
    realm_confirmation_ascension = realm_confirmation_payload["cultivation"]["realm_ascension"]
    assert realm_confirmation_ascension["can_confirm_rebuild"] is False
    assert realm_confirmation_ascension["pending_confirmation_rebuild"] is None
    assert "confirmation_blocking_message" not in realm_confirmation_ascension
    assert realm_confirmation_ascension["can_start_review"] is False

    no_pending_confirmation_status, no_pending_confirmation_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{realm_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": realm_revision + 4,
            "cultivation_action": "confirm_realm_ascension",
            "target_realm": "Immortal",
            "realm_ascension_gm_confirmation_note": "Confirm again.",
        },
    )
    assert no_pending_confirmation_status == 400
    assert no_pending_confirmation_payload["error"]["code"] == "validation_error"
    assert (
        no_pending_confirmation_payload["error"]["message"]
        == "Apply a pending Realm rebuild before recording GM confirmation."
    )

    cap_character_slug = "api-cultivation-cap"
    cap_body = deepcopy(xianxia_body)
    cap_body["definition"]["name"] = "API Cultivation Cap"
    cap_body["definition"]["xianxia"]["insight"] = {"available": 1, "spent": 0}
    cap_body["definition"]["xianxia"]["durability"]["hp_max"] = 50
    cap_body["definition"]["xianxia"]["durability"]["stance_max"] = 50
    cap_create_status, _cap_create_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{cap_character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=cap_body,
    )
    assert cap_create_status == 200
    cap_status, cap_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{cap_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
    )
    assert cap_status == 200
    cap_revision = cap_payload["character"]["state_record"]["revision"]
    hp_cap_status, hp_cap_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{cap_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": cap_revision,
            "cultivation_action": "spend_conditioning",
            "conditioning_target": "hp",
        },
    )
    assert hp_cap_status == 400
    assert hp_cap_payload["error"]["code"] == "validation_error"
    assert hp_cap_payload["error"]["message"] == "Conditioning cannot increase HP above 50."

    stance_cap_status, stance_cap_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{cap_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": cap_revision,
            "cultivation_action": "spend_training",
            "training_target": "stance",
        },
    )
    assert stance_cap_status == 400
    assert stance_cap_payload["error"]["code"] == "validation_error"
    assert stance_cap_payload["error"]["message"] == "Training cannot increase Stance above 50."

    zero_gathering_status, zero_gathering_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 3,
            "action": "record_gathering_insight",
            "values": {"insight_gain_amount": "0"},
        },
    )
    assert zero_gathering_status == 400
    assert zero_gathering_payload["error"]["code"] == "validation_error"
    assert zero_gathering_payload["error"]["message"] == "Gathered Insight must be at least 1."

    fractional_gathering_status, fractional_gathering_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{xianxia_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": initial_revision + 3,
            "cultivation_action": "record_gathering_insight",
            "insight_gain_amount": "1.5",
        },
    )
    assert fractional_gathering_status == 400
    assert fractional_gathering_payload["error"]["code"] == "validation_error"
    assert fractional_gathering_payload["error"]["message"] == "Gathered Insight must be a whole number."

    unsupported_status, unsupported_payload = _to_json(
        f"{typescript_api_mutation_server['url']}{route_path}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={"expected_revision": payload["character"]["state_record"]["revision"], "action": "save_insight"},
    )
    assert unsupported_status == 400
    assert unsupported_payload["error"]["code"] == "unsupported_campaign_system"
    assert unsupported_payload["error"]["message"] == "Cultivation is only available for Xianxia character sheets."

    divine_character_slug = "api-cultivation-divine"
    divine_body = deepcopy(xianxia_body)
    divine_body["definition"]["name"] = "API Cultivation Divine"
    divine_body["definition"]["xianxia"]["realm"] = "Divine"
    divine_body["definition"]["xianxia"]["advancement_history"] = [
        {"action": "realm_ascension_review_started", "current_realm": "Divine", "status": "pending_gm_review"},
        {"action": "realm_ascension_attributes_efforts_reset", "current_realm": "Divine", "status": "pending_rebuild"},
    ]
    divine_create_status, _divine_create_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{divine_character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=divine_body,
    )
    assert divine_create_status == 200

    divine_status, divine_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{divine_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
    )
    assert divine_status == 200
    divine_realm = divine_payload["cultivation"]["realm_ascension"]
    assert divine_realm["current_realm"] == "Divine"
    assert divine_realm["available"] is False
    assert divine_realm["can_apply_rebuild"] is False
    assert divine_realm["can_apply_divine_rebuild"] is False

    immortal_character_slug = "api-cultivation-immortal"
    immortal_body = deepcopy(xianxia_body)
    immortal_body["definition"]["name"] = "API Cultivation Immortal"
    immortal_body["definition"]["xianxia"]["realm"] = "Immortal"
    immortal_body["definition"]["xianxia"]["advancement_history"] = [
        {
            "action": "realm_ascension_review_started",
            "current_realm": "Immortal",
            "target_realm": "Divine",
            "status": "pending_gm_review",
        },
        {
            "action": "realm_ascension_attributes_efforts_reset",
            "current_realm": "Immortal",
            "target_realm": "Divine",
            "status": "pending_rebuild",
        },
    ]
    immortal_create_status, _immortal_create_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{immortal_character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=immortal_body,
    )
    assert immortal_create_status == 200

    immortal_status, immortal_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{immortal_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
    )
    assert immortal_status == 200
    immortal_realm = immortal_payload["cultivation"]["realm_ascension"]
    assert immortal_realm["current_realm"] == "Immortal"
    assert immortal_realm["available"] is True
    assert immortal_realm["target"]["target_realm"] == "Divine"
    assert immortal_realm["can_reset_stats"] is False
    assert immortal_realm["can_apply_rebuild"] is True
    assert immortal_realm["can_apply_divine_rebuild"] is True
    immortal_revision = immortal_payload["character"]["state_record"]["revision"]

    divine_rebuild_status, divine_rebuild_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/characters/{immortal_character_slug}/cultivation",
        headers=typescript_api_mutation_server["dm_headers"],
        method="POST",
        body={
            "expected_revision": immortal_revision,
            "cultivation_action": "apply_divine_realm_rebuild",
            "target_realm": "Divine",
            "realm_rebuild_attribute_str": "12",
            "realm_rebuild_attribute_dex": "4",
            "realm_rebuild_attribute_con": "3",
            "realm_rebuild_attribute_int": "1",
            "realm_rebuild_attribute_wis": "0",
            "realm_rebuild_attribute_cha": "0",
            "realm_rebuild_effort_basic": "2",
            "realm_rebuild_effort_weapon": "1",
            "realm_rebuild_effort_guns_explosive": "0",
            "realm_rebuild_effort_magic": "1",
            "realm_rebuild_effort_ultimate": "1",
            "realm_ascension_rebuild_notes": "Divine rebuild applied.",
        },
    )
    assert divine_rebuild_status == 200
    assert divine_rebuild_payload["ok"] is True
    assert divine_rebuild_payload["message"] == "Applied the Divine rebuild budget for 25 points and 4 actions."
    divine_rebuild_xianxia = divine_rebuild_payload["character"]["definition"]["xianxia"]
    assert divine_rebuild_xianxia["realm"] == "Divine"
    assert divine_rebuild_xianxia["actions_per_turn"] == 4
    assert divine_rebuild_xianxia["attributes"] == {
        "str": 12,
        "dex": 4,
        "con": 3,
        "int": 1,
        "wis": 0,
        "cha": 0,
    }
    assert divine_rebuild_xianxia["efforts"] == {
        "basic": 2,
        "weapon": 1,
        "guns_explosive": 0,
        "magic": 1,
        "ultimate": 1,
    }
    divine_rebuild_history = divine_rebuild_xianxia["advancement_history"][-1]
    assert divine_rebuild_history["action"] == "realm_ascension_divine_rebuild_applied"
    assert divine_rebuild_history["current_realm"] == "Immortal"
    assert divine_rebuild_history["target_realm"] == "Divine"
    assert divine_rebuild_history["status"] == "applied_pending_final_confirmation"
    assert divine_rebuild_history["rebuild_budget"] == 25
    assert divine_rebuild_history["stat_cap"] == 12
    assert divine_rebuild_history["actions_per_turn"] == 4
    assert divine_rebuild_history["attributes_after_total"] == 20
    assert divine_rebuild_history["efforts_after_total"] == 5
    assert divine_rebuild_history["total_rebuild_points"] == 25
    assert divine_rebuild_history["notes"] == "Divine rebuild applied."
    assert divine_rebuild_payload["cultivation"]["realm_ascension"]["can_confirm_rebuild"] is True


def test_typescript_content_character_backup_restore_rehearsal_recovers_files_assets_and_sqlite(
    tmp_path,
    typescript_api_mutation_server,
):
    character_slug = "arden-march"
    campaigns_dir = typescript_api_mutation_server["campaigns_dir"]
    db_path = typescript_api_mutation_server["db_path"]
    character_dir = campaigns_dir / "linden-pass" / "characters" / character_slug
    definition_path = character_dir / "definition.yaml"
    import_path = character_dir / "import.yaml"
    portrait_path = campaigns_dir / "linden-pass" / "assets" / "characters" / character_slug / "portrait.txt"

    original_definition_text = definition_path.read_text(encoding="utf-8")
    original_import_text = import_path.read_text(encoding="utf-8")
    portrait_path.parent.mkdir(parents=True, exist_ok=True)
    portrait_path.write_text("rollback portrait asset\n", encoding="utf-8")

    seed_state = {
        "status": "active",
        "vitals": {"current_hp": 22, "temp_hp": 3, "death_saves": {"successes": 1, "failures": 0}},
        "hit_dice": {"pools": [{"faces": 6, "current": 2, "max": 5}]},
        "resources": [
            {
                "id": "sorcery-points",
                "label": "Sorcery Points",
                "category": "spellcasting",
                "current": 2,
                "max": 5,
                "reset_on": "long_rest",
                "reset_to": "max",
                "rest_behavior": "restore_full",
                "notes": "",
                "display_order": 10,
            }
        ],
        "inventory": [
            {
                "id": "light-crossbow-1",
                "catalog_ref": "light-crossbow-1",
                "name": "Light Crossbow",
                "quantity": 1,
                "weight": "5 lb.",
                "is_equipped": True,
                "is_attuned": False,
                "charges_current": None,
                "charges_max": None,
                "notes": "",
                "tags": ["rehearsal"],
            }
        ],
        "currency": {"cp": 0, "sp": 0, "ep": 0, "gp": 12, "pp": 0, "other": []},
        "spell_slots": [{"level": 1, "max": 4, "used": 2}],
        "attunement": {"max_attuned_items": 3, "attuned_item_refs": []},
        "notes": {
            "player_notes_markdown": "rollback rehearsal state",
            "physical_description_markdown": "",
            "background_markdown": "",
            "session_notes": [],
        },
    }
    _write_sqlite_character_state(db_path, character_slug, revision=7, state=seed_state)
    _insert_sqlite_character_assignment(db_path, character_slug)
    assert _read_sqlite_character_state(db_path, character_slug) == {"revision": 7, "state": seed_state}
    assert _sqlite_character_assignment_count(db_path, character_slug) == 1

    backup = create_backup_archive(
        db_path=db_path,
        campaigns_dir=campaigns_dir,
        backup_root=tmp_path / "typescript-backups",
        label="ts-content-character-rehearsal",
    )

    updated_definition = yaml.safe_load(original_definition_text)
    updated_definition["name"] = "Arden March Rehearsed"
    updated_definition["profile"]["biography_markdown"] = "Temporary TypeScript rehearsal edit."
    update_status, update_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body={"definition": updated_definition},
    )
    assert update_status == 200
    assert update_payload["character_file"]["state_created"] is False
    assert "Arden March Rehearsed" in definition_path.read_text(encoding="utf-8")
    assert _read_sqlite_character_state(db_path, character_slug) == {"revision": 7, "state": seed_state}

    delete_status, delete_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="DELETE",
    )
    assert delete_status == 200
    assert delete_payload["deleted"] == {
        "character_slug": character_slug,
        "deleted_files": True,
        "deleted_state": True,
        "deleted_assignment": True,
        "deleted_assets": True,
    }
    assert not definition_path.exists()
    assert not import_path.exists()
    assert not portrait_path.exists()
    assert _read_sqlite_character_state(db_path, character_slug) is None
    assert _sqlite_character_assignment_count(db_path, character_slug) == 0

    restore = restore_backup_archive(archive_path=backup.archive_path, db_path=db_path, campaigns_dir=campaigns_dir)
    assert restore.database_path == db_path.resolve()
    assert definition_path.read_text(encoding="utf-8") == original_definition_text
    assert import_path.read_text(encoding="utf-8") == original_import_text
    assert portrait_path.read_text(encoding="utf-8") == "rollback portrait asset\n"
    assert _read_sqlite_character_state(db_path, character_slug) == {"revision": 7, "state": seed_state}
    assert _sqlite_character_assignment_count(db_path, character_slug) == 1


def test_typescript_content_character_xianxia_persistence_matches_flask_golden(
    typescript_api_mutation_server,
    client,
    app,
    users,
):
    character_slug = "api-cultivator-golden"
    flask_dm_token = _issue_api_token(app, users["dm"]["email"], label="dm-content-character-xianxia-golden")
    flask_campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    _write_campaign_system(flask_campaigns_dir, system="Xianxia", systems_library="Xianxia")
    _write_campaign_system(typescript_api_mutation_server["campaigns_dir"], system="Xianxia", systems_library="Xianxia")

    definition_payload = {
        "name": "API Cultivator Golden",
        "status": "active",
        "system": "xianxia",
        "xianxia": {
            "realm": "Mortal",
            "energy_maxima": {"jing": 3, "qi": 2, "shen": 1},
            "yin_yang": {"yin_max": 2, "yang_max": 1},
            "dao_max": 3,
            "durability": {
                "hp_max": 18,
                "stance_max": 12,
                "manual_armor_bonus": 1,
                "defense": 11,
            },
            "trained_skills": ["Tea Ceremony"],
            "necessary_weapons": ["Jian"],
            "martial_arts": [{"name": "Heavenly Palm", "current_rank": "Initiate"}],
        },
    }
    body = {"definition": definition_payload}

    flask_create = client.put(
        f"/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=_api_headers(flask_dm_token),
        json=body,
    )
    assert flask_create.status_code == 200
    assert flask_create.get_json()["character_file"]["state_created"] is True

    ts_status, ts_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=body,
    )
    assert ts_status == 200
    assert ts_payload["character_file"]["state_created"] is True
    assert ts_payload["character_file"]["definition"]["system"] == "Xianxia"

    with app.app_context():
        repository = app.extensions["character_repository"]
        state_store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", character_slug)
        assert record is not None
        flask_mutable_state = deepcopy(record.state_record.state)
        flask_mutable_state["vitals"]["current_hp"] = 7
        flask_mutable_state["xianxia"]["vitals"]["current_hp"] = 7
        flask_mutable_state["xianxia"]["vitals"]["current_stance"] = 5
        flask_mutable_state["xianxia"]["energies"]["jing"]["current"] = 2
        flask_mutable_state["xianxia"]["yin_yang"]["yin_current"] = 1
        flask_mutable_state["xianxia"]["dao"]["current"] = 2
        flask_mutable_state["xianxia"]["active_stance"] = {"name": "Stone Root"}
        flask_mutable_state["notes"]["player_notes_markdown"] = "Keep the manual pool edits in SQLite."
        flask_edited_state = state_store.replace_state(
            record.definition,
            flask_mutable_state,
            expected_revision=record.state_record.revision,
        )

    ts_initial_state = _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug)
    assert ts_initial_state is not None
    ts_mutable_state = deepcopy(ts_initial_state["state"])
    ts_mutable_state["vitals"]["current_hp"] = 7
    ts_mutable_state["xianxia"]["vitals"]["current_hp"] = 7
    ts_mutable_state["xianxia"]["vitals"]["current_stance"] = 5
    ts_mutable_state["xianxia"]["energies"]["jing"]["current"] = 2
    ts_mutable_state["xianxia"]["yin_yang"]["yin_current"] = 1
    ts_mutable_state["xianxia"]["dao"]["current"] = 2
    ts_mutable_state["xianxia"]["active_stance"] = {"name": "Stone Root"}
    ts_mutable_state["notes"]["player_notes_markdown"] = "Keep the manual pool edits in SQLite."
    connection = sqlite3.connect(typescript_api_mutation_server["db_path"])
    try:
        connection.execute(
            """
            UPDATE character_state
            SET revision = ?, state_json = ?, updated_at = ?, updated_by_user_id = ?
            WHERE campaign_slug = ? AND character_slug = ?
            """,
            (
                ts_initial_state["revision"] + 1,
                json.dumps(ts_mutable_state),
                "2026-06-25T12:45:00+00:00",
                77,
                "linden-pass",
                character_slug,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    updated_definition_payload = deepcopy(definition_payload)
    updated_definition_payload["xianxia"]["energy_maxima"] = {"jing": 1, "qi": 2, "shen": 1}
    updated_definition_payload["xianxia"]["yin_yang"] = {"yin_max": 1, "yang_max": 1}
    updated_definition_payload["xianxia"]["durability"] = {
        "hp_max": 6,
        "stance_max": 4,
        "manual_armor_bonus": 1,
        "defense": 11,
    }
    update_body = {"definition": updated_definition_payload}

    flask_update = client.put(
        f"/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=_api_headers(flask_dm_token),
        json=update_body,
    )
    assert flask_update.status_code == 200
    assert flask_update.get_json()["character_file"]["state_created"] is False

    ts_update_status, ts_update_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="PUT",
        body=update_body,
    )
    assert ts_update_status == 200
    assert ts_update_payload["character_file"]["state_created"] is False

    flask_final_state = _read_flask_character_state(app, character_slug)
    ts_final_state = _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug)
    assert flask_final_state is not None
    assert ts_final_state is not None
    assert ts_final_state["revision"] == flask_final_state["revision"] == flask_edited_state.revision + 1
    assert _xianxia_persistence_summary(ts_final_state["state"]) == _xianxia_persistence_summary(
        flask_final_state["state"]
    )
    assert ts_final_state["state"]["vitals"] == {"current_hp": 6, "temp_hp": 0}
    assert ts_final_state["state"]["xianxia"]["vitals"]["current_stance"] == 4
    assert ts_final_state["state"]["xianxia"]["energies"]["jing"] == {"current": 1}
    assert ts_final_state["state"]["xianxia"]["dao"] == {"current": 2}
    assert ts_final_state["state"]["xianxia"]["active_stance"] == {"name": "Stone Root"}
    assert ts_final_state["state"]["notes"]["player_notes_markdown"] == "Keep the manual pool edits in SQLite."

    flask_definition_text = (
        flask_campaigns_dir / "linden-pass" / "characters" / character_slug / "definition.yaml"
    ).read_text(encoding="utf-8")
    ts_definition_text = (
        typescript_api_mutation_server["campaigns_dir"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    ).read_text(encoding="utf-8")
    for definition_text in (flask_definition_text, ts_definition_text):
        assert "current_hp" not in definition_text
        assert "active_stance" not in definition_text
        assert "Keep the manual pool edits" not in definition_text

    flask_delete = client.delete(
        f"/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=_api_headers(flask_dm_token),
    )
    assert flask_delete.status_code == 200
    assert flask_delete.get_json()["deleted"]["deleted_state"] is True
    assert flask_delete.get_json()["deleted"]["deleted_assignment"] is False

    ts_delete_status, ts_delete_payload = _to_json(
        f"{typescript_api_mutation_server['url']}/api/v1/campaigns/linden-pass/content/characters/{character_slug}",
        headers=typescript_api_mutation_server["dm_headers"],
        method="DELETE",
    )
    assert ts_delete_status == 200
    assert ts_delete_payload["deleted"]["deleted_state"] is True
    assert ts_delete_payload["deleted"]["deleted_assignment"] is False
    assert _read_sqlite_character_state(typescript_api_mutation_server["db_path"], character_slug) is None


def test_typescript_content_pages_list_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/content/pages")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/pages",
        headers=CONTENT_MANAGER_HEADERS,
    )
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
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}",
        headers=CONTENT_MANAGER_HEADERS,
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

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/assets",
        headers=CONTENT_MANAGER_HEADERS,
    )
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
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/assets/{target_asset_ref}",
        headers=CONTENT_MANAGER_HEADERS,
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


def test_typescript_public_campaign_asset_matches_flask_contract(typescript_api_server, client):
    target_asset_ref = "npcs/captain-lyra-vale.png"

    flask_response = client.get(f"/campaigns/linden-pass/assets/{target_asset_ref}")
    assert flask_response.status_code == 200
    flask_bytes = flask_response.get_data()
    flask_media_type = flask_response.mimetype

    status, media_type, body = _to_bytes(
        f"{typescript_api_server}/campaigns/linden-pass/assets/{target_asset_ref}",
    )
    assert status == 200
    assert media_type == flask_media_type == "image/png"
    assert body == flask_bytes


def test_typescript_protected_campaign_asset_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    target_asset_ref = "npcs/captain-lyra-vale.png"

    flask_response = client.get(f"/campaigns/linden-pass/assets/{target_asset_ref}")
    assert flask_response.status_code == 200
    flask_bytes = flask_response.get_data()
    flask_media_type = flask_response.mimetype

    status, media_type, body = _to_bytes(
        f"{typescript_api_server}/campaigns/linden-pass/assets/{target_asset_ref}",
        headers=CONTENT_MANAGER_HEADERS,
    )
    assert status == 200
    assert media_type == flask_media_type == "image/png"
    assert body == flask_bytes


def test_typescript_protected_campaign_asset_missing_returns_404(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    flask_response = client.get("/campaigns/linden-pass/assets/definitely-not-an-asset.png")
    assert flask_response.status_code == 404

    status, media_type, body = _to_bytes(
        f"{typescript_api_server}/campaigns/linden-pass/assets/definitely-not-an-asset.png",
        headers=CONTENT_MANAGER_HEADERS,
    )
    assert status == 404
    assert media_type == "application/json"
    payload = json.loads(body.decode("utf-8"))
    assert payload["error"]["code"] == "campaign_asset_not_found"


def test_typescript_content_characters_list_matches_flask_contract(typescript_api_server, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    flask_response = client.get("/api/v1/campaigns/linden-pass/content/characters")
    assert flask_response.status_code == 200
    flask_payload = flask_response.get_json()

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/characters",
        headers=CONTENT_MANAGER_HEADERS,
    )
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
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/characters/{target_character_slug}",
        headers=CONTENT_MANAGER_HEADERS,
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

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/config",
        headers=CONTENT_MANAGER_HEADERS,
    )
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
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/pages/definitely-not-a-page",
        headers=CONTENT_MANAGER_HEADERS,
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
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/assets/definitely-not-an-asset.png",
        headers=CONTENT_MANAGER_HEADERS,
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
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/content/characters/missing-character",
        headers=CONTENT_MANAGER_HEADERS,
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "content_character_not_found"

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/systems")
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/systems/search")
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/session/article-sources/search?q=capt",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems/sources/NOPE",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "systems_source_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems/sources/PHB/types/definitely-not-a-type",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "systems_source_category_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/linden-pass/systems/entries/definitely-not-an-entry",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "systems_entry_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/combat",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/combat/live-state",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"

    status, payload = _to_json(
        f"{typescript_api_server}/api/v1/campaigns/definitely-not-a-campaign/combat/systems-monsters/search",
        headers={"X-CPW-Fixture-Role": "admin"},
    )
    assert status == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "campaign_not_found"
