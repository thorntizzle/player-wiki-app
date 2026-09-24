"""Static digest freshness, target identity, bounded retention and URL parity."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import os
from pathlib import Path
import re
from threading import Barrier
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest


def _cell(function, name):
    return dict(zip(function.__code__.co_freevars, function.__closure__ or ()))[name].cell_contents


def _resolver(app):
    helpers = next(fn for fn in app.template_context_processors[None] if fn.__name__ == "inject_helpers")
    build_url = _cell(helpers, "_build_static_asset_url")
    resolve = _cell(build_url, "_resolve_static_asset_version")
    return resolve, build_url, _cell(resolve, "_STATIC_ASSET_VERSION_CACHE")


def _digest(payload):
    return hashlib.sha1(payload).hexdigest()[:16]


def _identity(stat, **changes):
    values = {name: getattr(stat, name) for name in
              ("st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns", "st_size", "st_mode")}
    values.update(changes)
    return SimpleNamespace(**values)


def _create_symlink(link, target):
    try:
        link.symlink_to(target)
    except OSError as error:
        if os.name == "nt" and getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege unavailable; actual target links are mandatory in Linux")
        raise


@pytest.fixture
def static_version(app, tmp_path):
    root = tmp_path / "version-assets"
    root.mkdir()
    app.static_folder = str(root)
    resolve, build_url, cache = _resolver(app)
    return SimpleNamespace(app=app, root=root, resolve=resolve, build_url=build_url, cache=cache)


def test_warm_version_keeps_fresh_stat_without_canonical_resolution(static_version, monkeypatch):
    target = static_version.root / "sample.js"
    target.write_bytes(b"const value = 1;")
    calls = {"stat": 0, "read": 0}
    stat, read, resolve = Path.stat, Path.read_bytes, Path.resolve

    def observed_stat(path, *args, **kwargs):
        if path == target:
            calls["stat"] += 1
        return stat(path, *args, **kwargs)

    def observed_read(path):
        if path == target:
            calls["read"] += 1
        return read(path)

    def forbidden_resolve(path, *args, **kwargs):
        if path == target:
            pytest.fail("qualified target identity must not canonicalize its cache key")
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", observed_stat)
    monkeypatch.setattr(Path, "read_bytes", observed_read)
    monkeypatch.setattr(Path, "resolve", forbidden_resolve)
    assert static_version.resolve("sample.js") == _digest(b"const value = 1;")
    assert static_version.resolve("sample.js") == _digest(b"const value = 1;")
    assert calls == {"stat": 2, "read": 1}


@pytest.mark.skipif(os.name == "nt", reason="Windows stat ctime is creation time; actual POSIX change-time mutation is mandatory in Linux")
def test_supported_ctime_refreshes_same_identity_with_preserved_size_mtime(static_version):
    target = static_version.root / "sample.js"
    target.write_bytes(b"first")
    original = target.stat()
    assert static_version.resolve(target.name) == _digest(b"first")
    # Let the real filesystem timestamp tick advance before the ctime mutation.
    time.sleep(0.02)
    target.write_bytes(b"other")
    os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
    changed = target.stat()
    assert (changed.st_dev, changed.st_ino, changed.st_size, changed.st_mtime_ns) == (
        original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns)
    assert changed.st_ctime_ns != original.st_ctime_ns
    assert static_version.resolve(target.name) == _digest(b"other")
    target.write_bytes(b"larger rewritten content")
    assert static_version.resolve(target.name) == _digest(b"larger rewritten content")


def test_equal_size_mtime_replacement_and_reused_identity_revalidate(static_version, monkeypatch):
    target = static_version.root / "sample.js"
    target.write_bytes(b"first")
    original = target.stat()
    assert static_version.resolve(target.name) == _digest(b"first")
    replacement = static_version.root / "replacement.js"
    replacement.write_bytes(b"other")
    os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
    os.replace(replacement, target)
    changed = target.stat()
    assert changed.st_ino != original.st_ino
    assert (changed.st_size, changed.st_mtime_ns) == (original.st_size, original.st_mtime_ns)
    assert static_version.resolve(target.name) == _digest(b"other")
    # A reused identity must still lose its old signature when change time differs.
    target.write_bytes(b"third")
    real_stat = Path.stat

    def reused_identity(path, *args, **kwargs):
        value = real_stat(path, *args, **kwargs)
        if path == target:
            return _identity(value, st_dev=changed.st_dev, st_ino=changed.st_ino,
                             st_size=changed.st_size, st_mtime_ns=changed.st_mtime_ns,
                             st_ctime_ns=changed.st_ctime_ns + 1)
        return value

    monkeypatch.setattr(Path, "stat", reused_identity)
    assert static_version.resolve(target.name) == _digest(b"third")


def test_actual_symlink_retarget_alias_and_hardlink_use_current_target(static_version):
    first, other = static_version.root / "first.js", static_version.root / "other.js"
    first.write_bytes(b"first")
    other.write_bytes(b"other")
    stamp = first.stat()
    os.utime(other, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    link = static_version.root / "alias.js"
    _create_symlink(link, first)
    assert static_version.resolve(link.name) == static_version.resolve(first.name) == _digest(b"first")
    assert len(static_version.cache) == 1
    link.unlink()
    link.symlink_to(other)
    assert static_version.resolve(link.name) == _digest(b"other")
    hardlink = static_version.root / "hardlink.js"
    os.link(other, hardlink)
    assert static_version.resolve(hardlink.name) == _digest(b"other")
    assert len(static_version.cache) == 2


def test_missing_created_deleted_unreadable_and_empty_targets(static_version, monkeypatch):
    target = static_version.root / "sample.js"
    assert static_version.resolve(target.name) is None
    target.write_bytes(b"first")
    assert static_version.resolve(target.name) == _digest(b"first")
    target.unlink()
    assert static_version.resolve(target.name) is None
    target.write_bytes(b"different")
    original_read = Path.read_bytes

    def unreadable(path):
        if path == target:
            raise PermissionError("synthetic inaccessible asset")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    assert static_version.resolve(target.name) is None
    assert static_version.resolve("") is None
    static_version.app.static_folder = None
    assert static_version.resolve(target.name) is None


def test_unsupported_identity_fields_use_original_canonical_fallback(static_version, monkeypatch):
    target = static_version.root / "sample.js"
    target.write_bytes(b"first")
    actual = target.stat()
    real_stat, real_resolve = Path.stat, Path.resolve
    cases = [
        *( (name, value) for name in ("st_dev", "st_ino", "st_ctime_ns")
           for value in (None, 0, -1, True, 1.5, "42") ),
        ("st_mtime_ns", True), ("st_mtime_ns", 1.5), ("st_mtime_ns", "42"),
        ("st_size", None), ("st_size", -1), ("st_size", True), ("st_size", 1.5),
    ]
    for name, value in cases:
        static_version.cache.clear()
        resolved = []

        def unsupported_stat(path, *args, **kwargs):
            return _identity(actual, **{name: value}) if path == target else real_stat(path, *args, **kwargs)

        def observed_resolve(path, *args, **kwargs):
            if path == target:
                resolved.append(path)
            return real_resolve(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "stat", unsupported_stat)
            patch.setattr(Path, "resolve", observed_resolve)
            assert static_version.resolve(target.name) == _digest(b"first"), (name, value)
            assert static_version.resolve(target.name) == _digest(b"first"), (name, value)
        assert len(resolved) == 2, (name, value)
        assert len(static_version.cache) == 1
        assert all(type(key) is str for key in static_version.cache)


def test_fallback_missing_fields_and_original_resolution_errors(static_version, monkeypatch):
    target = static_version.root / "sample.js"
    target.write_bytes(b"first")
    actual = target.stat()
    real_stat, real_resolve = Path.stat, Path.resolve
    for missing in ("st_dev", "st_ino", "st_ctime_ns"):
        value = _identity(actual)
        delattr(value, missing)
        static_version.cache.clear()
        with monkeypatch.context() as patch:
            patch.setattr(Path, "stat", lambda path, *args, **kwargs: value if path == target else real_stat(path, *args, **kwargs))
            assert static_version.resolve(target.name) == _digest(b"first")
            assert all(type(key) is str for key in static_version.cache)
    # A cold fallback preserves the original read-error precedence over conversion.
    static_version.cache.clear()
    value = _identity(actual, st_mtime_ns=None)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", lambda path, *args, **kwargs: value if path == target else real_stat(path, *args, **kwargs))
        real_read = Path.read_bytes

        def unreadable(path):
            if path == target:
                raise PermissionError("synthetic inaccessible fallback asset")
            return real_read(path)

        patch.setattr(Path, "read_bytes", unreadable)
        assert static_version.resolve(target.name) is None
        patch.setattr(Path, "read_bytes", real_read)
        with pytest.raises(TypeError):
            static_version.resolve(target.name)
    value = _identity(actual, st_dev=0)
    monkeypatch.setattr(Path, "stat", lambda path, *args, **kwargs: value if path == target else real_stat(path, *args, **kwargs))

    def failed_resolve(path, *args, **kwargs):
        if path == target:
            raise RuntimeError("synthetic canonical resolution failure")
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", failed_resolve)
    with pytest.raises(RuntimeError, match="canonical resolution failure"):
        static_version.resolve(target.name)


def test_fallback_rechecks_original_mtime_size_signature_and_aliases(static_version, monkeypatch):
    target = static_version.root / "sample.js"
    target.write_bytes(b"first")
    alias = static_version.root / "alias.js"
    _create_symlink(alias, target)
    real_stat = Path.stat

    def unsupported_stat(path, *args, **kwargs):
        value = real_stat(path, *args, **kwargs)
        return _identity(value, st_dev=0) if path in (target, alias) else value

    monkeypatch.setattr(Path, "stat", unsupported_stat)
    assert static_version.resolve(target.name) == static_version.resolve(alias.name) == _digest(b"first")
    assert len(static_version.cache) == 1
    target.write_bytes(b"longer replacement")
    assert static_version.resolve(alias.name) == _digest(b"longer replacement")


def test_per_app_cache_separates_same_filename_and_simulated_target_identity(static_version, monkeypatch, tmp_path):
    module = importlib.import_module("player_wiki.app")
    other_app = module.create_app()
    other_root = tmp_path / "other-static-root"
    other_root.mkdir()
    other_app.static_folder = str(other_root)
    other_resolve, _, other_cache = _resolver(other_app)
    first, other = static_version.root / "sample.js", other_root / "sample.js"
    first.write_bytes(b"first")
    other.write_bytes(b"other")
    observed = first.stat()
    real_stat = Path.stat
    monkeypatch.setattr(Path, "stat", lambda path, *args, **kwargs: observed if path in (first, other) else real_stat(path, *args, **kwargs))
    assert static_version.cache is not other_cache
    assert static_version.resolve(first.name) == _digest(b"first")
    assert other_resolve(other.name) == _digest(b"other")
    assert static_version.resolve(first.name) == _digest(b"first")


def test_concurrent_mixed_misses_return_computed_digest_and_bound_quiescent_cache(static_version, monkeypatch):
    names = [f"{'fallback' if index % 2 else 'identity'}-{index}.js" for index in range(24)]
    payloads = {name: f"payload-{name}".encode() for name in names}
    for name, payload in payloads.items():
        (static_version.root / name).write_bytes(payload)
    barrier = Barrier(8)
    real_read, real_stat = Path.read_bytes, Path.stat

    def mixed_stat(path, *args, **kwargs):
        value = real_stat(path, *args, **kwargs)
        return _identity(value, st_dev=0) if path.parent == static_version.root and path.name.startswith("fallback") else value

    def synchronized_read(path):
        value = real_read(path)
        if path.parent == static_version.root:
            barrier.wait(timeout=10)
        return value

    monkeypatch.setattr(Path, "stat", mixed_stat)
    monkeypatch.setattr(Path, "read_bytes", synchronized_read)

    def build_versioned_url(name):
        with static_version.app.test_request_context():
            return static_version.build_url(name)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(build_versioned_url, names))
    assert [parse_qs(urlsplit(url).query) for url in results] == [
        {"v": [_digest(payloads[name])]} for name in names]
    assert [urlsplit(url).path for url in results] == [f"/static/{name}" for name in names]
    assert len(static_version.cache) <= 16
    monkeypatch.setattr(Path, "read_bytes", real_read)
    for name in names:
        assert static_version.resolve(name) == _digest(payloads[name])
    assert len(static_version.cache) <= 16


def test_versioned_requests_keep_current_digest_headers_and_path_refusal(static_version):
    app = static_version.app
    app.config["APP_ENV"] = "production"
    target = static_version.root / "sample.js"
    target.write_bytes(b"first")
    with app.test_request_context():
        old_url = static_version.build_url(target.name)
    client = app.test_client()
    current = client.get(old_url)
    assert current.status_code == 200 and current.data == b"first"
    assert "immutable" in current.headers["Cache-Control"]
    assert "max-age=31536000" in current.headers["Cache-Control"]
    assert "cookie" not in current.headers.get("Vary", "").lower()
    assert "script-src 'self'" in current.headers["Content-Security-Policy"]
    current.close()
    for url in ("/static/sample.js", "/static/sample.js?v=wrong", old_url + "&v=duplicate"):
        response = client.get(url)
        assert response.status_code == 200 and response.data == b"first"
        assert "immutable" not in response.headers["Cache-Control"]
        response.close()
    old_stat = target.stat()
    replacement = static_version.root / "replacement.js"
    replacement.write_bytes(b"other")
    os.utime(replacement, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    os.replace(replacement, target)
    response = client.get(old_url)
    assert response.status_code == 200 and response.data == b"other"
    assert "immutable" not in response.headers["Cache-Control"]
    response.close()
    with app.test_request_context():
        new_url = static_version.build_url(target.name)
    assert parse_qs(urlsplit(new_url).query) == {"v": [_digest(b"other")]}
    with client.get(new_url) as current:
        assert "immutable" in current.headers["Cache-Control"]
    outside = static_version.root.parent / "outside.js"
    outside.write_bytes(b"must not be served")
    denied = client.get("/static/../outside.js?v=" + _digest(b"must not be served"))
    assert denied.status_code == 404 and b"must not be served" not in denied.data
    denied.close()


def test_real_character_document_preserves_fixed_bytes_queries_and_asset_urls(app, users):
    from player_wiki.auth_store import AuthStore
    from tests.helpers.character_state_helpers import _write_character_state
    from tests.test_ha_measurement_loading_date import fixed_loading_selection_date

    app.config["LIVE_DIAGNOSTICS"] = True
    client = app.test_client()
    assert client.post("/sign-in", data={"email": users["dm"]["email"], "password": users["dm"]["password"]}).status_code == 302
    assert client.post("/campaigns/linden-pass/combat/player-combatants", data={"character_slug": "arden-march", "turn_value": 18}).status_code == 302
    with app.app_context():
        for scope in ("characters", "combat"):
            AuthStore().upsert_campaign_visibility_setting("linden-pass", scope, visibility="players", updated_by_user_id=users["dm"]["id"])
        service = app.extensions["campaign_combat_service"]
        for index in range(6):
            service.add_npc_combatant("linden-pass", display_name=f"Paired NPC {index + 1}", turn_value=12-index,
                current_hp=10, max_hp=10, movement_total=30, created_by_user_id=users["dm"]["id"])
        for _ in range(3):
            service.sync_player_character_snapshots("linden-pass")
        for changed in (False, True):
            for index in range(28):
                if changed:
                    def set_hp(state):
                        vitals = dict(state.get("vitals") or {})
                        vitals["current_hp"] = 15 + index % 2
                        state["vitals"] = vitals
                    _write_character_state(app, "arden-march", set_hp)
                result = service.sync_player_character_snapshots("linden-pass")
                assert result.sync_changed is changed
    owner = app.test_client()
    assert owner.post("/sign-in", data={"email": users["owner"]["email"], "password": users["owner"]["password"]}).status_code == 302
    with fixed_loading_selection_date():
        owner.get("/campaigns/linden-pass/characters/arden-march?page=quick")
        response = owner.get("/campaigns/linden-pass/characters/arden-march?page=quick")
    assert response.status_code == 200
    assert len(response.data) == int(response.headers["X-Character-Read-Response-Bytes"]) == 70359
    # The integrated target retains six uncached durable-revision checks.
    assert response.headers["X-Character-Read-Query-Count"] == "30"
    assert "private, no-store" in response.headers["Cache-Control"]
    html = response.get_data(as_text=True)
    for filename in ("styles.css", "presentation-controller.js", "live-ui-helper.js", "character-read-shell.js"):
        expected = _digest((Path(app.static_folder) / filename).read_bytes())
        assert html.count(f"/static/{filename}?v={expected}") == 1
    assert re.search(r'nonce="[A-Za-z0-9_-]{43}"', html)
    assert 'data-app-loading-media-url="/campaigns/linden-pass/assets/lore/trade-coast-map.png"' in html
