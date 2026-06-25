from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_route_snapshot_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "route_snapshots.py"
    spec = importlib.util.spec_from_file_location("route_snapshots", module_path)
    assert spec and spec.loader is not None, f"Unable to load {module_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, repo_root


def test_api_route_snapshot_matches_tracked_fixture():
    route_module, repo_root = _load_route_snapshot_module()
    snapshot_path = (
        repo_root / "docs" / "typescript-backend-rewrite" / "route-snapshots.json"
    )
    api_file = repo_root / "player_wiki" / "api.py"
    app_file = repo_root / "player_wiki" / "app.py"

    generated = route_module.build_snapshot(api_file=api_file, app_file=app_file)
    tracked = route_module.load_snapshot(snapshot_path)

    assert route_module.snapshots_match(generated, tracked)


def test_route_parser_expands_app_route_methods(tmp_path):
    route_module, repo_root = _load_route_snapshot_module()
    sample_app = tmp_path / "sample_app.py"
    sample_app.write_text(
        """from flask import Flask\n\napp = Flask(__name__)\n\n@app.route('/demo', methods=[\"GET\", \"POST\"])\ndef demo():\n    pass\n\n@app.route('/single')\ndef single():\n    pass\n""",
        encoding="utf-8",
    )

    tree = route_module.ast.parse(sample_app.read_text(encoding="utf-8"))
    parsed = route_module._extract_routes(
        tree,
        sample_app,
        "flask",
        route_prefixes={},
    )
    route_paths = {(route.method, route.path) for route in parsed}

    assert ("GET", "/demo") in route_paths
    assert ("POST", "/demo") in route_paths
    assert ("GET", "/single") in route_paths
    assert len(route_paths) >= 3
