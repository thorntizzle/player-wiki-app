from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if os.name == "nt":
    from _pytest.pathlib import make_numbered_dir, rm_rf
    from _pytest.tmpdir import TempPathFactory

    _ORIGINAL_GET_BASE_TEMP = TempPathFactory.getbasetemp

    def _windows_getbasetemp(self):
        if self._basetemp is not None:
            return self._basetemp
        if self._given_basetemp is None:
            return _ORIGINAL_GET_BASE_TEMP(self)

        basetemp = self._given_basetemp
        if basetemp.exists():
            rm_rf(basetemp)
        # Python 3.14 on this Windows setup creates unreadable dirs with 0o700.
        basetemp.mkdir(mode=0o777)
        self._basetemp = basetemp.resolve()
        self._trace("new basetemp", self._basetemp)
        return self._basetemp

    def _windows_mktemp(self, basename: str, numbered: bool = True) -> Path:
        basename = self._ensure_relative_to_basetemp(basename)
        if numbered:
            path = make_numbered_dir(
                root=self.getbasetemp(),
                prefix=basename,
                mode=0o777,
            )
            self._trace("mktemp", path)
            return path

        path = self.getbasetemp().joinpath(basename)
        path.mkdir(mode=0o777)
        return path

    TempPathFactory.getbasetemp = _windows_getbasetemp
    TempPathFactory.mktemp = _windows_mktemp

from player_wiki.app import create_app
from player_wiki.auth_store import AuthStore
from player_wiki.config import Config
from player_wiki.db import init_database
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG, build_test_campaigns_dir


def pytest_configure(config):
    if config.option.basetemp:
        return
    basetemp = PROJECT_ROOT / ".local" / "pytest-temp" / f"run-{os.getpid()}"
    basetemp.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(basetemp)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)
    monkeypatch.setattr(Config, "APP_VERSION", "test-version")
    monkeypatch.setattr(Config, "APP_BUILD_ID", "test-build")
    monkeypatch.setattr(Config, "APP_GIT_SHA", "test-git-sha")
    monkeypatch.setattr(Config, "APP_GIT_DIRTY", False)
    monkeypatch.setattr(Config, "APP_RUNTIME", "test-runtime")
    monkeypatch.setattr(Config, "APP_INSTANCE_NAME", "test-instance")

    app = create_app()
    app.config.update(
        TESTING=True,
        DB_PATH=tmp_path / "player_wiki.sqlite3",
    )

    with app.app_context():
        init_database()
        store = AuthStore()

        owner_player = store.create_user(
            "owner@example.com",
            "Owner Player",
            status="active",
            password_hash=generate_password_hash("owner-pass"),
        )
        other_player = store.create_user(
            "party@example.com",
            "Party Player",
            status="active",
            password_hash=generate_password_hash("party-pass"),
        )
        dm = store.create_user(
            "dm@example.com",
            "Dungeon Master",
            status="active",
            password_hash=generate_password_hash("dm-pass"),
        )
        observer = store.create_user(
            "observer@example.com",
            "Observer",
            status="active",
            password_hash=generate_password_hash("observer-pass"),
        )
        outsider = store.create_user(
            "outsider@example.com",
            "Outsider",
            status="active",
            password_hash=generate_password_hash("outsider-pass"),
        )
        admin = store.create_user(
            "admin@example.com",
            "Admin User",
            is_admin=True,
            status="active",
            password_hash=generate_password_hash("admin-pass"),
        )

        store.upsert_membership(owner_player.id, TEST_CAMPAIGN_SLUG, role="player")
        store.upsert_membership(other_player.id, TEST_CAMPAIGN_SLUG, role="player")
        store.upsert_membership(dm.id, TEST_CAMPAIGN_SLUG, role="dm")
        store.upsert_membership(observer.id, TEST_CAMPAIGN_SLUG, role="observer")
        store.upsert_character_assignment(owner_player.id, TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG)

        app.config["TEST_USERS"] = {
            "owner": {"email": "owner@example.com", "password": "owner-pass", "id": owner_player.id},
            "party": {"email": "party@example.com", "password": "party-pass", "id": other_player.id},
            "dm": {"email": "dm@example.com", "password": "dm-pass", "id": dm.id},
            "observer": {"email": "observer@example.com", "password": "observer-pass", "id": observer.id},
            "outsider": {"email": "outsider@example.com", "password": "outsider-pass", "id": outsider.id},
            "admin": {"email": "admin@example.com", "password": "admin-pass", "id": admin.id},
        }
        app.config["TEST_CAMPAIGNS_DIR"] = campaigns_dir

    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def users(app):
    return app.config["TEST_USERS"]


@pytest.fixture()
def sign_in(client):
    def _sign_in(email: str, password: str):
        client.post(
            "/sign-out",
            follow_redirects=False,
        )
        return client.post(
            "/sign-in",
            data={"email": email, "password": password},
            follow_redirects=False,
        )

    return _sign_in


@pytest.fixture()
def get_character(app):
    def _get_character(character_slug: str):
        with app.app_context():
            repository = app.extensions["character_repository"]
            return repository.get_visible_character(TEST_CAMPAIGN_SLUG, character_slug)

    return _get_character


@pytest.fixture()
def set_campaign_visibility(app):
    def _set_campaign_visibility(campaign_slug: str, **visibility_by_scope: str):
        with app.app_context():
            store = AuthStore()
            for scope, visibility in visibility_by_scope.items():
                store.upsert_campaign_visibility_setting(
                    campaign_slug,
                    scope,
                    visibility=visibility,
                )

    return _set_campaign_visibility
