from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_MANIFEST_PATH = Path("docs/contracts/route-api-role-visibility-manifest.json")


class PublisherManifestError(ValueError):
    """Raised when release evidence cannot be bound to the accepted candidate."""


def _git(project_root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=project_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PublisherManifestError(
            f"git {' '.join(arguments)} failed: {detail or 'unknown Git error'}"
        )
    return completed.stdout


def _accepted_identity(project_root: Path, commit: str) -> tuple[str, str]:
    if re.fullmatch(r"[0-9a-fA-F]{40}", commit) is None:
        raise PublisherManifestError(
            "accepted commit must be the full 40-character hexadecimal SHA"
        )
    accepted_commit = _git(project_root, "rev-parse", "--verify", f"{commit}^{{commit}}")
    accepted_tree = _git(project_root, "rev-parse", "--verify", f"{commit}^{{tree}}")
    return (
        accepted_commit.decode("ascii").strip(),
        accepted_tree.decode("ascii").strip(),
    )


def _output_path(path: Path, project_root: Path) -> Path:
    output = (path if path.is_absolute() else project_root / path).resolve()
    evidence_root = (project_root / ".local").resolve()
    try:
        relative = output.relative_to(evidence_root)
    except ValueError as exc:
        raise PublisherManifestError(
            "Publisher manifest output must be inside the repository .local evidence root"
        ) from exc
    if not relative.parts:
        raise PublisherManifestError("Publisher manifest output must name a file")
    return output


def _evidence_label(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return resolved.name


def _load_nodeids(path: Path) -> tuple[list[str], bytes]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PublisherManifestError(f"node-id cache is not valid JSON: {exc}") from exc
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise PublisherManifestError("node-id cache must be a JSON array of strings")
    if len(payload) != len(set(payload)):
        raise PublisherManifestError("node-id cache contains duplicate entries")
    return payload, raw


def _normalize_selector(selector: str) -> str:
    normalized = selector.strip().replace("\\", "/")
    test_path = normalized.split("::", 1)[0]
    if (
        not normalized
        or not test_path.startswith("tests/")
        or not test_path.endswith(".py")
        or test_path.startswith("/")
        or ".." in Path(test_path).parts
    ):
        raise PublisherManifestError(
            f"Publisher selector must name a tracked tests/*.py boundary: {selector!r}"
        )
    return normalized


def _selector_matches(nodeid: str, selector: str) -> bool:
    return (
        nodeid == selector
        or nodeid.startswith(f"{selector}::")
        or nodeid.startswith(f"{selector}[")
    )


def _expand_selectors(
    project_root: Path,
    accepted_commit: str,
    nodeids: Sequence[str],
    selectors: Sequence[str],
) -> tuple[list[str], list[str]]:
    normalized_selectors = sorted({_normalize_selector(item) for item in selectors})
    if not normalized_selectors:
        raise PublisherManifestError("at least one Publisher test selector is required")

    expanded: set[str] = set()
    for selector in normalized_selectors:
        test_path = selector.split("::", 1)[0]
        _git(project_root, "cat-file", "-e", f"{accepted_commit}:{test_path}")
        matches = [nodeid for nodeid in nodeids if _selector_matches(nodeid, selector)]
        if not matches:
            raise PublisherManifestError(
                f"Publisher selector matched no retained node IDs: {selector}"
            )
        expanded.update(matches)
    return normalized_selectors, sorted(expanded)


def _route_assertions(
    project_root: Path,
    accepted_commit: str,
    route_selectors: Sequence[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = ROUTE_MANIFEST_PATH.as_posix()
    raw = _git(project_root, "show", f"{accepted_commit}:{manifest_path}")
    blob = _git(project_root, "rev-parse", f"{accepted_commit}:{manifest_path}")
    try:
        route_manifest = json.loads(raw)
        entries = route_manifest["entries"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise PublisherManifestError(
            "accepted route contract manifest is invalid"
        ) from exc
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) for entry in entries
    ):
        raise PublisherManifestError("accepted route contract entries are invalid")

    assertions: list[dict[str, Any]] = []
    for selector in sorted(set(route_selectors)):
        try:
            endpoint, method = selector.rsplit(":", 1)
        except ValueError as exc:
            raise PublisherManifestError(
                f"live route selector must use ENDPOINT:METHOD: {selector!r}"
            ) from exc
        method = method.upper()
        if method != "GET":
            raise PublisherManifestError(
                f"Publisher live assertions must be read-only GET routes: {selector}"
            )
        matches = [
            entry
            for entry in entries
            if entry.get("endpoint") == endpoint and entry.get("method") == method
        ]
        if len(matches) != 1:
            raise PublisherManifestError(
                f"live route selector resolved to {len(matches)} entries: {selector}"
            )
        entry = matches[0]
        assertions.append(
            {
                key: entry[key]
                for key in (
                    "endpoint",
                    "method",
                    "route",
                    "normalized_route",
                    "converters",
                    "surface",
                    "owning_domain",
                    "authentication_policy",
                    "access_policy",
                    "actor_access",
                    "campaign_scope",
                    "visibility_policy",
                    "object_relationship_requirement",
                    "system_restriction",
                    "view_as_policy",
                    "denial_mode",
                )
            }
        )

    return (
        {
            "path": manifest_path,
            "blob": blob.decode("ascii").strip(),
            "sha256": hashlib.sha256(raw).hexdigest().upper(),
        },
        assertions,
    )


def build_publisher_manifest(
    *,
    project_root: Path,
    accepted_commit: str,
    nodeids_cache: Path,
    selectors: Sequence[str],
    live_routes: Sequence[str] = (),
) -> dict[str, Any]:
    root = project_root.resolve()
    cache_path = (
        nodeids_cache if nodeids_cache.is_absolute() else root / nodeids_cache
    ).resolve()
    commit, tree = _accepted_identity(root, accepted_commit)
    nodeids, cache_bytes = _load_nodeids(cache_path)
    normalized_selectors, expanded_nodeids = _expand_selectors(
        root,
        commit,
        nodeids,
        selectors,
    )
    route_source, assertions = _route_assertions(root, commit, live_routes)
    return {
        "schema_version": 1,
        "accepted_candidate": {"commit": commit, "tree": tree},
        "tests": {
            "nodeids_cache": {
                "path": _evidence_label(cache_path, root),
                "sha256": hashlib.sha256(cache_bytes).hexdigest().upper(),
                "nodeid_count": len(nodeids),
            },
            "selectors": normalized_selectors,
            "expanded_nodeids": expanded_nodeids,
            "expanded_nodeid_count": len(expanded_nodeids),
        },
        "live_routes": {
            "source": route_source,
            "assertions": assertions,
        },
    }


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic Publisher test/live assertion manifest "
            "for an exact accepted candidate."
        )
    )
    parser.add_argument("--accepted-commit", required=True)
    parser.add_argument("--nodeids-cache", required=True, type=Path)
    parser.add_argument("--selector", action="append", default=[])
    parser.add_argument("--live-route", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    try:
        manifest = build_publisher_manifest(
            project_root=PROJECT_ROOT,
            accepted_commit=arguments.accepted_commit,
            nodeids_cache=arguments.nodeids_cache,
            selectors=arguments.selector,
            live_routes=arguments.live_route,
        )
        output = _output_path(arguments.output, PROJECT_ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(manifest_bytes(manifest))
    except (OSError, PublisherManifestError) as exc:
        print(f"Publisher manifest error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote Publisher manifest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
