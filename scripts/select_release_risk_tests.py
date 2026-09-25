"""Resolve a frozen candidate's compact release-risk pytest selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def _selectors(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty selector list")
    for selector in value:
        if not isinstance(selector, str) or not selector or ".." in selector or "\\" in selector:
            raise ValueError(f"{label} has an unsafe test selector: {selector!r}")
        path, *nodes = selector.split("::")
        if not re.fullmatch(r"tests/test_[A-Za-z0-9_]+\.py", path):
            raise ValueError(f"{label} selector must name a test file: {selector!r}")
        if any(not node or "/" in node or "\\" in node or any(ord(c) < 32 for c in node)
               for node in nodes):
            raise ValueError(f"{label} has an unsafe test node: {selector!r}")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} contains duplicate selectors")
    return value


def _manifest(raw: bytes) -> dict:
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported release-risk manifest schema")
    if set(manifest) != {"schema_version", "baseline_linux", "baseline_windows", "domains", "source_rules"}:
        raise ValueError("release-risk manifest has missing or unexpected fields")
    _selectors(manifest["baseline_linux"], "baseline_linux")
    _selectors(manifest["baseline_windows"], "baseline_windows")
    domains = manifest["domains"]
    if not isinstance(domains, dict) or not domains:
        raise ValueError("domains must be a nonempty mapping")
    for name, selectors in domains.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"invalid risk domain: {name!r}")
        _selectors(selectors, f"domains.{name}")
    rules = manifest["source_rules"]
    if not isinstance(rules, list) or not rules:
        raise ValueError("source_rules must be a nonempty list")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or set(rule) != {"pattern", "domains"}:
            raise ValueError(f"source_rules[{index}] must have pattern and domains")
        pattern = rule["pattern"]
        if not isinstance(pattern, str) or not pattern.startswith("^") or len(pattern) < 2:
            raise ValueError(f"source_rules[{index}] needs an anchored pattern")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(f"source_rules[{index}] has an invalid pattern") from error
        rule_domains = rule["domains"]
        if not isinstance(rule_domains, list) or not rule_domains or any(
            not isinstance(name, str) or name not in domains for name in rule_domains
        ) or len(rule_domains) != len(set(rule_domains)):
            raise ValueError(f"source_rules[{index}] has invalid domains")
    return manifest


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    ).stdout


def _changed_paths(root: Path, base: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("base commit must be a full lowercase 40-character SHA")
    _git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", base, "HEAD"],
        check=True, capture_output=True,
    )
    changed = _git(root, "diff", "--name-only", "-z", base, "--")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted({p.decode("utf-8").replace("\\", "/") for p in
                   (changed + untracked).split(b"\0") if p})


def _changed_digest(root: Path, relative: str) -> str | None:
    path = root
    for component in relative.split("/"):
        path = path / component
        if path.is_symlink():
            raise ValueError(f"changed path traverses a link: {relative}")
    if not path.exists():
        return None  # Tracked deletion.
    if not path.is_file():
        raise ValueError(f"changed path is not a plain file: {relative}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(root: Path, base: str, manifest_path: Path) -> dict:
    raw = manifest_path.read_bytes()
    manifest = _manifest(raw)
    domains = manifest["domains"]
    linux = set(manifest["baseline_linux"])
    windows = set(manifest["baseline_windows"])
    changed = _changed_paths(root, base)
    changed_bytes = {path: _changed_digest(root, path) for path in changed}
    selected_domains: set[str] = set()
    unknown: list[str] = []
    for path in changed:
        if path.startswith("docs/") or path in {"AGENTS.md", "README.md"}:
            if path.startswith("docs/workflows/") or path == "AGENTS.md":
                selected_domains.add("validation")
            continue
        if re.fullmatch(r"tests/test_[A-Za-z0-9_]+\.py", path):
            source = (root / path).read_text(encoding="utf-8") if (root / path).exists() else ""
            linux.add(path)
            if "pytest.mark.windows_host" in source:
                windows.add(path)
            continue
        matched = False
        for rule in manifest["source_rules"]:
            if re.search(rule["pattern"], path):
                selected_domains.update(rule["domains"])
                matched = True
        if not matched:
            unknown.append(path)
    if unknown:
        raise ValueError("unmapped candidate paths require a reviewed manifest rule: " + ", ".join(unknown))
    for domain in selected_domains:
        if domain not in domains:
            raise ValueError(f"undefined risk domain: {domain}")
        linux.update(domains[domain])
    _selectors(sorted(linux), "resolved Linux selection")
    _selectors(sorted(windows), "resolved Windows selection")
    for selector in linux | windows:
        if not (root / selector.split("::", 1)[0]).is_file():
            raise ValueError(f"missing selected test: {selector}")
    return {
        "schema_version": 1,
        "base_commit": base,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "changed_paths": changed,
        "changed_bytes": changed_bytes,
        "domains": sorted(selected_domains),
        "linux": sorted(linux),
        "windows": sorted(windows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(select(args.project_root.resolve(), args.base_commit, args.manifest.resolve()),
                         sort_keys=True, separators=(",", ":")))
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError, TypeError) as error:
        print(f"release-risk selection refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
