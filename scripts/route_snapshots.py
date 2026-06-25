"""Route snapshot generator and checker for the TypeScript backend rewrite.

This script inspects Flask/Blueprint decorators in player_wiki/api.py and
player_wiki/app.py and emits a deterministic snapshot suitable for parity
checks.
"""

import argparse
import ast
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping, Sequence


RouteKind = str


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


SCRIPT_DEFAULTS = {
    "api_file": _repo_root() / "player_wiki" / "api.py",
    "app_file": _repo_root() / "player_wiki" / "app.py",
    "snapshot_file": _repo_root() / "docs" / "typescript-backend-rewrite" / "route-snapshots.json",
}


KNOWN_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class ParsedRoute:
    method: str
    path: str
    source_file: str
    line_number: int
    route_family: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _string_constant(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _method_constant(node: ast.AST | None) -> str | None:
    method = _string_constant(node)
    if method is None:
        return None
    method = method.upper()
    return method if method in KNOWN_HTTP_METHODS else None


def _methods_from_expr(node: ast.AST | None) -> list[str] | None:
    if node is None:
        return None
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        methods: list[str] = []
        for element in node.elts:
            method = _method_constant(element)
            if method is None:
                return None
            methods.append(method)
        return methods
    method = _method_constant(node)
    if method is None:
        return None
    return [method]


def _join_prefix(prefix: str, path: str) -> str:
    if not prefix:
        return path
    prefix_clean = prefix.rstrip("/")
    if path.startswith("/"):
        return f"{prefix_clean}{path}"
    return f"{prefix_clean}/{path}"


def _route_family(path: str) -> str:
    if not path:
        return "unknown"
    if path.startswith("/api/v1"):
        return "api_v1"
    if path == "/":
        return "root"
    if not path.startswith("/"):
        return "unknown"
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return "root"
    return segments[0]


def _source_file_label(source_path: Path, source_root: Path) -> str:
    try:
        return source_path.relative_to(source_root).as_posix()
    except ValueError:
        return source_path.as_posix()


def _infer_blueprint_prefixes(tree: ast.Module) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call):
            if not isinstance(statement.value.func, ast.Name):
                continue
            if statement.value.func.id != "Blueprint":
                continue
            if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                continue
            target_name = statement.targets[0].id
            for keyword in statement.value.keywords:
                if keyword.arg == "url_prefix":
                    prefix = _string_constant(keyword.value)
                    if prefix is not None:
                        prefixes[target_name] = prefix
                    break
    return prefixes


def _extract_routes(
    tree: ast.AST,
    source_path: Path,
    route_kind: RouteKind,
    route_prefixes: Mapping[str, str] | None = None,
) -> list[ParsedRoute]:
    source_root = _repo_root()
    if route_prefixes is None:
        route_prefixes = {}

    extracted: list[ParsedRoute] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            object_name = decorator.func.value.id
            method = decorator.func.attr
            path = _string_constant(decorator.args[0]) if decorator.args else None
            if path is None:
                continue

            if object_name == route_kind:
                if route_kind == "api":
                    if method not in {"get", "post", "put", "patch", "delete"}:
                        continue
                    http_methods = [method.upper()]
                elif method == "route":
                    methods = None
                    for keyword in decorator.keywords:
                        if keyword.arg == "methods":
                            methods = _methods_from_expr(keyword.value)
                            break
                    http_methods = methods if methods else ["GET"]
                else:
                    continue

            elif object_name == "app" and route_kind == "flask":
                if method == "route":
                    methods = None
                    for keyword in decorator.keywords:
                        if keyword.arg == "methods":
                            methods = _methods_from_expr(keyword.value)
                            break
                    http_methods = methods if methods else ["GET"]
                elif method in {"get", "post", "put", "patch", "delete"}:
                    http_methods = [method.upper()]
                else:
                    continue
            else:
                continue

            for verb in http_methods:
                if verb not in KNOWN_HTTP_METHODS:
                    continue
                full_path = (
                    _join_prefix(route_prefixes[object_name], path)
                    if object_name in route_prefixes
                    else path
                )
                family = _route_family(full_path)
                extracted.append(
                    ParsedRoute(
                        method=verb,
                        path=full_path,
                        source_file=_source_file_label(source_path, source_root),
                        line_number=decorator.lineno,
                        route_family=family,
                    )
                )

    extracted.sort(
        key=lambda route: (route.source_file, route.line_number, route.method, route.path)
    )
    return extracted


def build_snapshot(api_file: Path, app_file: Path) -> dict[str, Any]:
    api_path = Path(api_file)
    app_path = Path(app_file)
    api_tree = ast.parse(api_path.read_text(encoding="utf-8"))
    app_tree = ast.parse(app_path.read_text(encoding="utf-8"))
    api_prefixes = _infer_blueprint_prefixes(api_tree)

    api_routes = _extract_routes(api_tree, api_path, "api", api_prefixes)
    app_routes = _extract_routes(app_tree, app_path, "flask")

    return {
        "api_v1_routes": [route.as_dict() for route in api_routes],
        "flask_routes": [route.as_dict() for route in app_routes],
    }


def _normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "api_v1_routes": sorted(
            snapshot.get("api_v1_routes", []),
            key=lambda route: (route["source_file"], route["line_number"], route["method"], route["path"]),
        ),
        "flask_routes": sorted(
            snapshot.get("flask_routes", []),
            key=lambda route: (route["source_file"], route["line_number"], route["method"], route["path"]),
        ),
    }


def load_snapshot(snapshot_file: Path) -> dict[str, Any]:
    return json.loads(snapshot_file.read_text(encoding="utf-8"))


def write_snapshot(snapshot: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def snapshots_match(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return _normalize_snapshot(actual) == _normalize_snapshot(expected)


def check_snapshot(snapshot_file: Path, api_file: Path, app_file: Path) -> bool:
    current = build_snapshot(api_file, app_file)
    tracked = load_snapshot(snapshot_file)
    return snapshots_match(current, tracked)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or check route snapshots")
    parser.add_argument(
        "--api-file",
        type=Path,
        default=SCRIPT_DEFAULTS["api_file"],
        help="API module path",
    )
    parser.add_argument(
        "--app-file",
        type=Path,
        default=SCRIPT_DEFAULTS["app_file"],
        help="Flask app path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SCRIPT_DEFAULTS["snapshot_file"],
        help="Output snapshot path",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="Write snapshot to output")
    group.add_argument("--check", action="store_true", help="Validate generated snapshot against output")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    current = build_snapshot(args.api_file, args.app_file)

    if args.check:
        if not args.output.exists():
            print(f"Missing tracked snapshot file: {args.output}")
            return 2
        if snapshots_match(current, load_snapshot(args.output)):
            return 0
        print(
            "Route snapshot check failed: generated routes differ from "
            f"{args.output}\n"
            "Run with --write to regenerate from tracked source."
        )
        return 1

    if args.write:
        write_snapshot(current, args.output)
        print(f"Wrote route snapshot to {args.output}")
        return 0

    print(json.dumps(current, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
