"""Synthetic, local-only Phase 8 measurement fixture envelope.

This helper deliberately creates no reusable credentials and no production
data.  A caller supplies an approved Git worktree and a unique token; the
result may exist only in that worktree's ignored ``.local/phase8-g1`` tree.
The fixture files are read from the pinned Git object rather than the caller's
working tree, so an uncommitted fixture edit cannot enter a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
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
    "commit": "d99f2eca7c516bc490e962566fc7c1d1706edd04",
    "tree": "b9fab3bfb10ff82d9c8452c1c1bac465faaee8fd",
    "harness_blob": PHASE8_IDENTITY["harness_blob"],
}
PHASE8_ENVELOPE_SUPPORT_PATHS = frozenset(
    {
        "tests/helpers/phase8_measurement_envelope.py",
        "tests/test_campaign_combat_page.py",
        "tests/test_csrf.py",
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
        # The focused support candidate itself is permitted only as a clean,
        # allowlisted test-support descendant of the accepted assembled Phase 8
        # runtime. This lets its own tests exercise the fixture helper without
        # admitting arbitrary application descendants into fixture provenance.
        if candidate_name != "phase8":
            raise ContractError("Synthetic envelope root does not match the pinned candidate commit/tree.")
        ancestor = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", identity["commit"], "HEAD"],
            check=False,
            capture_output=True,
        )
        changed = str(_git(root, "diff", "--name-only", f"{identity['commit']}..HEAD")).splitlines()
        if (
            ancestor.returncode != 0
            or not changed
            or not set(changed).issubset(PHASE8_ENVELOPE_SUPPORT_PATHS)
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
    """Prove the assembled runtime retains the frozen Phase 8 fixture bytes."""

    frozen_proof = fixture_manifest_proof(candidate_root, PHASE8_IDENTITY["commit"])
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
    proof = {"bytes": len(raw), "sha256": sha256(raw).hexdigest().upper()}
    if proof != frozen_proof:
        raise ContractError("Accepted assembled Phase 8 fixture does not match the source-proven frozen fixture.")
    return proof


def _copy_git_fixture(candidate_root: Path, commit: str, campaigns_dir: Path) -> None:
    archive = _git(candidate_root, "archive", "--format=tar", commit, str(_FIXTURE_PREFIX), text=False)
    assert isinstance(archive, bytes)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as bundle:
        for member in bundle.getmembers():
            member_path = PurePosixPath(member.name)
            try:
                relative = member_path.relative_to(_FIXTURE_PREFIX)
            except ValueError as exc:
                if member.isdir() and member_path in _FIXTURE_PREFIX.parents:
                    continue
                raise ContractError("Git fixture archive contained an unexpected path.") from exc
            if not relative.parts:
                if member.isdir():
                    campaigns_dir.mkdir(parents=True, exist_ok=True)
                    continue
                raise ContractError("Git fixture archive did not contain a fixture-relative file path.")
            if any(part in {"", ".", ".."} for part in relative.parts):
                raise ContractError("Git fixture archive contained an unsafe path.")
            destination = (campaigns_dir / Path(*relative.parts)).resolve()
            if campaigns_dir not in destination.parents and destination != campaigns_dir:
                raise ContractError("Git fixture archive path escaped the synthetic envelope.")
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ContractError("Git fixture archive must contain only files and directories.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise ContractError("Git fixture archive member could not be read.")
            destination.write_bytes(source.read())


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
    fixture_proof = (
        _accepted_phase8_fixture_proof(root, identity["commit"])
        if candidate_name == "phase8"
        else fixture_manifest_proof(root, identity["commit"])
    )
    player_email = "phase8-player@example.test"
    manager_email = "phase8-manager@example.test"
    player_password = f"p8g1-player-{token}"
    manager_password = f"p8g1-manager-{token}"

    _copy_git_fixture(root, identity["commit"], campaigns_dir)
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
