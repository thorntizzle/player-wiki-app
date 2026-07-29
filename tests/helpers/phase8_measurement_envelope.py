"""Synthetic, local-only Phase 8 measurement fixture envelope.

This helper deliberately creates no reusable credentials and no production
data.  A caller supplies an approved Git worktree and a unique token; the
result may exist only in that worktree's ignored ``.local/phase8-g1`` tree.
The fixture files are read from the pinned Git object rather than the caller's
working tree, so an uncommitted fixture edit cannot enter a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Mapping

from werkzeug.security import generate_password_hash

from player_wiki.app import create_app
from player_wiki.auth_store import AuthStore
from player_wiki.config import Config
from player_wiki.db import init_database

from .phase8_measurement_adapter import (
    PHASE4_IDENTITY,
    PHASE8_IDENTITY,
    ContractError,
    canonical_json_bytes,
    fixture_manifest_proof,
)


CAMPAIGN_SLUG = "linden-pass"
COMBAT_CHARACTER_SLUG = "arden-march"
PHASE8_ENVELOPE_IDENTITY = {
    "commit": "8feccab99e3f0776a9f40fb7ffaa64b6fa66c7e2",
    "tree": "b2bfbf27c240c56377cb28c967ef60f53d51f01c",
    "harness_blob": PHASE8_IDENTITY["harness_blob"],
}
PHASE8_ENVELOPE_SUPPORT_PATHS = frozenset(
    {
        "tests/helpers/phase8_measurement_envelope.py",
        "tests/test_phase8_measurement_adapter.py",
    }
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,63}\Z")
_FIXTURE_PREFIX = PurePosixPath("tests/fixtures/sample_campaigns")


@dataclass(frozen=True)
class SyntheticMeasurementEnvelope:
    """Local paths and process-only synthetic credentials for one candidate."""

    candidate_name: str
    root: Path
    campaigns_dir: Path
    database_path: Path
    metadata_path: Path
    player_email: str
    manager_email: str
    _player_password: str
    _manager_password: str

    @property
    def credentials(self) -> Mapping[str, tuple[str, str]]:
        """Return process-only credentials; callers must never serialize them."""

        return {
            "player": (self.player_email, self._player_password),
            "manager": (self.manager_email, self._manager_password),
        }


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=text,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() if text else completed.stderr.decode("utf-8", "replace").strip()
        raise ContractError(f"Unable to verify the synthetic-envelope Git root: {detail or 'git command failed'}")
    return completed.stdout


def _approved_root(candidate_root: Path, candidate_name: str) -> tuple[Path, Mapping[str, str]]:
    identity = {"phase4": PHASE4_IDENTITY, "phase8": PHASE8_ENVELOPE_IDENTITY}.get(candidate_name)
    if identity is None:
        raise ContractError("Synthetic envelopes are limited to the pinned phase4 or phase8 identities.")
    root = candidate_root.resolve()
    if not root.is_dir():
        raise ContractError("Synthetic envelope candidate root must be an existing Git worktree.")
    git_root = Path(str(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if git_root != root:
        raise ContractError("Synthetic envelope destination must be the approved candidate Git root.")
    commit = str(_git(root, "rev-parse", "HEAD")).strip().lower()
    tree = str(_git(root, "rev-parse", "HEAD^{tree}")).strip().lower()
    if commit != identity["commit"] or tree != identity["tree"]:
        # The focused support candidate is permitted only as the exact,
        # non-merge direct child that changes both allowlisted support files.
        # This lets its own tests exercise the fixture helper without admitting
        # partial, deeper, merged, or application descendants.
        if candidate_name != "phase8":
            raise ContractError("Synthetic envelope root does not match the pinned candidate commit/tree.")
        parents = str(_git(root, "show", "-s", "--format=%P", "HEAD")).split()
        changed = str(_git(root, "diff", "--name-only", f"{identity['commit']}..HEAD")).splitlines()
        if (
            parents != [identity["commit"]]
            or len(changed) != len(PHASE8_ENVELOPE_SUPPORT_PATHS)
            or set(changed) != PHASE8_ENVELOPE_SUPPORT_PATHS
        ):
            raise ContractError("Synthetic envelope root does not match the pinned candidate identity or support boundary.")
    return root, identity


def _target_root(candidate_root: Path, token: str) -> Path:
    if not _TOKEN_RE.fullmatch(token):
        raise ContractError("Synthetic envelope token must be 8-64 URL-safe characters.")
    local_root = (candidate_root / ".local").resolve()
    target = (local_root / "phase8-g1" / token).resolve()
    if target.parent != (local_root / "phase8-g1").resolve():
        raise ContractError("Synthetic envelope destination escaped the approved ignored root.")
    if target.exists():
        raise ContractError("Synthetic envelope token already exists and may not be overwritten.")
    ignored = subprocess.run(
        ["git", "-C", str(candidate_root), "check-ignore", "--quiet", "--no-index", str(target.relative_to(candidate_root))],
        check=False,
        capture_output=True,
    )
    if ignored.returncode != 0:
        raise ContractError("Synthetic envelope destination is not ignored by the candidate worktree.")
    return target


def _accepted_phase8_fixture_proof(candidate_root: Path, commit: str) -> dict[str, object]:
    """Prove the frozen fixture source is available and precedes the candidate."""

    source_commit = PHASE8_IDENTITY["commit"]
    source_type = str(_git(candidate_root, "cat-file", "-t", source_commit)).strip()
    source_tree = str(_git(candidate_root, "rev-parse", f"{source_commit}^{{tree}}")).strip().lower()
    if source_type != "commit" or source_tree != PHASE8_IDENTITY["tree"]:
        raise ContractError("Frozen Phase 8 fixture source does not match its pinned Git identity.")
    ancestor = subprocess.run(
        ["git", "-C", str(candidate_root), "merge-base", "--is-ancestor", source_commit, commit],
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise ContractError("Frozen Phase 8 fixture source is not an ancestor of the accepted candidate.")
    return fixture_manifest_proof(candidate_root, source_commit)


def _copy_git_fixture(candidate_root: Path, commit: str, campaigns_dir: Path) -> None:
    raw = _git(
        candidate_root,
        "ls-tree",
        "-r",
        "-z",
        commit,
        "--",
        str(_FIXTURE_PREFIX),
        text=False,
    )
    assert isinstance(raw, bytes)
    destinations: set[str] = set()
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, encoded_path = entry.split(b"\t", 1)
            mode, kind, object_id = metadata.decode("ascii").split()
            member_path = PurePosixPath(encoded_path.decode("utf-8"))
            relative = member_path.relative_to(_FIXTURE_PREFIX)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ContractError("Git fixture tree contained an invalid entry.") from exc
        if mode != "100644" or kind != "blob":
            raise ContractError("Git fixture tree must contain only regular files.")
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ContractError("Git fixture tree contained an unsafe path.")
        destination = (campaigns_dir / Path(*relative.parts)).resolve()
        if campaigns_dir not in destination.parents:
            raise ContractError("Git fixture tree path escaped the synthetic envelope.")
        destination_key = str(destination).casefold()
        if destination_key in destinations:
            raise ContractError("Git fixture tree contained a colliding path.")
        destinations.add(destination_key)
        source = _git(candidate_root, "cat-file", "blob", object_id, text=False)
        assert isinstance(source, bytes)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source)


def _metadata(
    *,
    candidate_name: str,
    identity: Mapping[str, str],
    fixture_proof: Mapping[str, object],
    player_email: str,
    manager_email: str,
) -> dict[str, object]:
    """Non-secret envelope record; passwords intentionally never appear here."""

    return {
        "candidate": {"name": candidate_name, **dict(identity)},
        "combat_character": {"assigned": True, "slug": COMBAT_CHARACTER_SLUG, "turn_value": 18},
        "fixture": dict(fixture_proof),
        "principals": {
            "manager": {"email": manager_email, "membership": "active", "role": "dm"},
            "player": {"email": player_email, "membership": "active", "role": "player"},
        },
        "schema": "phase8-g1-synthetic-envelope-v1",
    }


def create_synthetic_measurement_envelope(
    candidate_root: Path,
    *,
    candidate_name: str,
    token: str,
) -> SyntheticMeasurementEnvelope:
    """Build a pinned, ignored fixture/auth envelope without starting a server.

    Password values exist only in the returned dataclass.  The SQLite store
    contains Werkzeug password hashes solely because the local application
    performs real sign-in checks during the later authorized measurement.
    """

    root, identity = _approved_root(candidate_root, candidate_name)
    target = _target_root(root, token)
    campaigns_dir = target / "campaigns"
    database_path = target / "player_wiki.sqlite3"
    metadata_path = target / "envelope.json"
    if candidate_name == "phase8":
        fixture_source_commit = PHASE8_IDENTITY["commit"]
        fixture_proof = _accepted_phase8_fixture_proof(root, identity["commit"])
    else:
        fixture_source_commit = identity["commit"]
        fixture_proof = fixture_manifest_proof(root, fixture_source_commit)
    player_email = "phase8-player@example.test"
    manager_email = "phase8-manager@example.test"
    player_password = f"p8g1-player-{token}"
    manager_password = f"p8g1-manager-{token}"

    _copy_git_fixture(root, fixture_source_commit, campaigns_dir)
    saved_config = {
        "CAMPAIGNS_DIR": Config.CAMPAIGNS_DIR,
        "DB_PATH": Config.DB_PATH,
        "LIVE_DIAGNOSTICS": Config.LIVE_DIAGNOSTICS,
    }
    try:
        Config.CAMPAIGNS_DIR = campaigns_dir
        Config.DB_PATH = database_path
        Config.LIVE_DIAGNOSTICS = True
        app = create_app()
        app.config.update(
            CAMPAIGNS_DIR=campaigns_dir,
            CSRF_ENABLED=False,
            DB_PATH=database_path,
            LIVE_DIAGNOSTICS=True,
            TESTING=True,
        )
        with app.app_context():
            init_database()
            store = AuthStore()
            player = store.create_user(
                player_email,
                "Phase 8 Synthetic Player",
                status="active",
                password_hash=generate_password_hash(player_password),
            )
            manager = store.create_user(
                manager_email,
                "Phase 8 Synthetic Manager",
                status="active",
                password_hash=generate_password_hash(manager_password),
            )
            store.upsert_membership(player.id, CAMPAIGN_SLUG, role="player", status="active")
            store.upsert_membership(manager.id, CAMPAIGN_SLUG, role="dm", status="active")
            store.upsert_character_assignment(player.id, CAMPAIGN_SLUG, COMBAT_CHARACTER_SLUG)
            app.extensions["campaign_combat_service"].add_player_character(
                CAMPAIGN_SLUG,
                character_slug=COMBAT_CHARACTER_SLUG,
                turn_value=18,
                created_by_user_id=manager.id,
            )
    finally:
        for key, value in saved_config.items():
            setattr(Config, key, value)

    metadata = _metadata(
        candidate_name=candidate_name,
        identity=identity,
        fixture_proof=fixture_proof,
        player_email=player_email,
        manager_email=manager_email,
    )
    metadata_path.write_bytes(canonical_json_bytes(metadata))
    if player_password.encode("utf-8") in metadata_path.read_bytes() or manager_password.encode("utf-8") in metadata_path.read_bytes():
        raise ContractError("Synthetic envelope metadata must not persist plaintext passwords.")
    return SyntheticMeasurementEnvelope(
        candidate_name=candidate_name,
        root=target,
        campaigns_dir=campaigns_dir,
        database_path=database_path,
        metadata_path=metadata_path,
        player_email=player_email,
        manager_email=manager_email,
        _player_password=player_password,
        _manager_password=manager_password,
    )
