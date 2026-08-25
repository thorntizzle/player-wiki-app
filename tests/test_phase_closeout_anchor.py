from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import phase_closeout_anchor as anchor
import validation_evidence as evidence


LEDGER_HEADER = (
    "# Phase Closeout Evidence Anchors\n\n"
    "| Phase | Accepted commit | Accepted tree | Relative lifecycle record | Bytes | SHA-256 | Finalized UTC |\n"
    "| --- | --- | --- | --- | ---: | --- | --- |\n"
    "| Prior Phase | `1111111111111111111111111111111111111111` | "
    "`2222222222222222222222222222222222222222` | "
    "`.local/roadmaps/prior.md` | 5 | "
    "`AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | "
    "`2026-01-01T00:00:00Z` |\n\n"
    "Ledger prose.\n"
)
SOURCE_RELATIVE = ".local/roadmaps/phase-nine-lifecycle.md"
FROZEN_RELATIVE = ".local/evidence/frozen.json"
CLASSIFICATION_RELATIVE = ".local/evidence/classification.json"
PLAN_RELATIVE = ".local/evidence/plan.json"
WRITE_RELATIVE = ".local/evidence/write.json"
VERIFY_RELATIVE = ".local/evidence/verify.json"
PHASE = "Flask rewrite Phase 9 (retrospective final)"
FINALIZED = "2026-08-01T12:34:56.123456Z"


def git(root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def write(path: Path, payload: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8", newline="")


def git_bytes(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout


def tracked_identity(root: Path, accepted: str, relative: str) -> dict[str, str]:
    return {
        "path": relative,
        "sha256": evidence.sha256_bytes(
            git_bytes(root, "show", f"{accepted}:{relative}")
        ),
    }


def build_frozen(source: Path, accepted: str) -> dict[str, object]:
    candidate = {
        "commit": accepted,
        "tree": git(source, "rev-parse", f"{accepted}^{{tree}}"),
        "runtime_tree": git(source, "rev-parse", f"{accepted}:player_wiki"),
        "tests_tree": git(source, "rev-parse", f"{accepted}:tests"),
        "workflow_tree": git(source, "rev-parse", f"{accepted}:docs/workflows"),
    }
    core: dict[str, object] = {
        "schema": evidence.SCHEMA,
        "schema_version": evidence.SCHEMA_VERSION,
        "kind": "FROZEN_IDENTITY",
        "candidate": candidate,
        "fly_blobs": [
            {
                "path": "fly.toml",
                "blob": git(source, "rev-parse", f"{accepted}:fly.toml"),
            }
        ],
        "interpreter": {
            "implementation": "CPython",
            "version": "3.12.12",
            "executable_sha256": "A" * 64,
        },
        "dependencies": {
            **tracked_identity(source, accepted, "requirements-dev.lock"),
            "package_count": 1,
        },
        "runner": tracked_identity(source, accepted, "scripts/runner.py"),
        "envelope": tracked_identity(source, accepted, "evidence/envelope.json"),
        "suite": {
            "verdict": tracked_identity(source, accepted, "evidence/suite-verdict.json"),
            "index": tracked_identity(source, accepted, "evidence/suite-index.json"),
            "seal": tracked_identity(source, accepted, "evidence/suite-seal.json"),
        },
        "invalidators": [
            "APPLICATION_AMBIGUITY",
            "RUNTIME_IDENTITY",
            "TEST_IDENTITY",
        ],
        "root": ".",
    }
    return evidence.seal_receipt(core)


def build_classification(source_payload: bytes) -> dict[str, object]:
    return evidence.seal_receipt(
        {
            "schema": anchor.CLASSIFICATION_SCHEMA,
            "schema_version": anchor.SCHEMA_VERSION,
            "kind": anchor.CLASSIFICATION_KIND,
            "status": "ACCEPT",
            "classification": "SANITIZED_LIFECYCLE",
            "source": {
                "path": SOURCE_RELATIVE,
                "bytes": len(source_payload),
                "sha256": evidence.sha256_bytes(source_payload),
            },
            "reviewed_utc": "2026-08-01T12:00:00Z",
            "reviewer": "independent-lifecycle-sanitization-verifier",
        }
    )


@pytest.fixture
def lane(tmp_path: Path) -> dict[str, object]:
    primary = tmp_path / "repo"
    primary.mkdir()
    git(primary, "init", "-b", "main")
    git(primary, "config", "user.name", "Test User")
    git(primary, "config", "user.email", "test@example.invalid")
    git(primary, "config", "core.autocrlf", "false")
    files = {
        ".gitignore": ".local/\n",
        "player_wiki/__init__.py": "# runtime\n",
        "tests/test_seed.py": "def test_seed():\n    assert True\n",
        "docs/workflows/seed.md": "# workflow\n",
        anchor.LEDGER_RELATIVE: LEDGER_HEADER,
        "requirements-dev.lock": "seed==1 --hash=sha256:" + ("a" * 64) + "\n",
        "scripts/runner.py": "# runner\n",
        "evidence/envelope.json": '{"envelope":1}\n',
        "evidence/suite-verdict.json": '{"verdict":"ACCEPT"}\n',
        "evidence/suite-index.json": '{"files":1}\n',
        "evidence/suite-seal.json": '{"seal":"ok"}\n',
        "fly.toml": "[build]\n",
    }
    for relative, payload in files.items():
        write(primary / relative, payload)
    git(primary, "add", ".")
    git(primary, "commit", "-m", "seed")
    accepted = git(primary, "rev-parse", "HEAD")
    git(primary, "branch", "source")
    git(primary, "branch", "canonical")
    source = tmp_path / "source"
    canonical = tmp_path / "canonical"
    git(primary, "worktree", "add", str(source), "source")
    git(primary, "worktree", "add", str(canonical), "canonical")
    source_payload = b"# Sanitized lifecycle\r\n\r\nExact retained bytes.\r\n"
    write(source / SOURCE_RELATIVE, source_payload)
    frozen = build_frozen(source, accepted)
    write(source / FROZEN_RELATIVE, evidence.canonical_json_bytes(frozen))
    classification = build_classification(source_payload)
    write(
        source / CLASSIFICATION_RELATIVE,
        evidence.canonical_json_bytes(classification),
    )
    return {
        "primary": primary,
        "source": source,
        "canonical": canonical,
        "accepted": accepted,
        "source_payload": source_payload,
    }


def render(lane: dict[str, object], **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "source_root_raw": str(lane["source"]),
        "canonical_root_raw": str(lane["canonical"]),
        "ledger_root_raw": str(lane["primary"]),
        "source_ref": "refs/heads/source",
        "canonical_ref": "refs/heads/canonical",
        "ledger_ref": "refs/heads/main",
        "source_relative": SOURCE_RELATIVE,
        "canonical_relative": SOURCE_RELATIVE,
        "ledger_relative": anchor.LEDGER_RELATIVE,
        "frozen_identity_relative": FROZEN_RELATIVE,
        "classification_relative": CLASSIFICATION_RELATIVE,
        "phase": PHASE,
        "finalized_utc": FINALIZED,
        "replacement_authorized": False,
    }
    values.update(overrides)
    return anchor.render_plan(**values)  # type: ignore[arg-type]


def write_plan(lane: dict[str, object], plan: dict[str, object], **kwargs: object):
    return anchor.write_anchor(
        source_root_raw=str(lane["source"]),
        canonical_root_raw=str(lane["canonical"]),
        ledger_root_raw=str(lane["primary"]),
        plan_value=plan,
        **kwargs,
    )


def verify_plan(lane: dict[str, object], plan: dict[str, object]):
    return anchor.verify_anchor(
        source_root_raw=str(lane["source"]),
        canonical_root_raw=str(lane["canonical"]),
        ledger_root_raw=str(lane["primary"]),
        plan_value=plan,
    )


def test_render_write_verify_is_deterministic_and_byte_exact(lane):
    first = render(lane)
    second = render(lane)
    assert first == second
    assert first["accepted"]["commit"] == lane["accepted"]
    assert first["source_record"]["bytes"] == len(lane["source_payload"])
    assert first["ledger_update"]["mode"] == "INSERT"

    result = write_plan(lane, first)
    assert result["status"] == "PASS"
    canonical = lane["canonical"] / SOURCE_RELATIVE
    assert canonical.read_bytes() == lane["source_payload"]
    ledger = (lane["primary"] / anchor.LEDGER_RELATIVE).read_bytes()
    assert anchor._ledger_payload_state(ledger) == first["ledger_poststate"]
    assert result["ledger"]["bytes"] == first["ledger_poststate"]["bytes"]
    assert result["ledger"]["sha256"] == first["ledger_poststate"]["sha256"]
    assert b"\r\n" not in ledger
    assert first["ledger_update"]["row"].encode() in ledger

    canonical_before = canonical.read_bytes()
    ledger_before = ledger
    verified = verify_plan(lane, first)
    assert verified["status"] == "PASS"
    assert canonical.read_bytes() == canonical_before
    assert (lane["primary"] / anchor.LEDGER_RELATIVE).read_bytes() == ledger_before


@pytest.mark.parametrize(
    ("ledger_key", "ledger_ref"),
    (("source", "refs/heads/source"), ("canonical", "refs/heads/canonical")),
)
def test_expected_ledger_drift_is_allowed_when_ledger_root_overlaps(
    lane, ledger_key, ledger_ref
):
    ledger_root = lane[ledger_key]
    plan = render(
        lane,
        ledger_root_raw=str(ledger_root),
        ledger_ref=ledger_ref,
    )
    written = anchor.write_anchor(
        source_root_raw=str(lane["source"]),
        canonical_root_raw=str(lane["canonical"]),
        ledger_root_raw=str(ledger_root),
        plan_value=plan,
    )
    assert written["status"] == "PASS"
    verified = anchor.verify_anchor(
        source_root_raw=str(lane["source"]),
        canonical_root_raw=str(lane["canonical"]),
        ledger_root_raw=str(ledger_root),
        plan_value=plan,
    )
    assert verified["status"] == "PASS"


@pytest.mark.parametrize(
    ("ledger_key", "ledger_ref"),
    (("source", "refs/heads/source"), ("canonical", "refs/heads/canonical")),
)
def test_overlapping_ledger_root_does_not_exempt_unrelated_verify_drift(
    lane, ledger_key, ledger_ref
):
    ledger_root = lane[ledger_key]
    plan = render(
        lane,
        ledger_root_raw=str(ledger_root),
        ledger_ref=ledger_ref,
    )
    assert (
        anchor.write_anchor(
            source_root_raw=str(lane["source"]),
            canonical_root_raw=str(lane["canonical"]),
            ledger_root_raw=str(ledger_root),
            plan_value=plan,
        )["status"]
        == "PASS"
    )
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = ledger_root / anchor.LEDGER_RELATIVE
    canonical_before = canonical.read_bytes()
    ledger_before = ledger.read_bytes()
    write(ledger_root / "docs/workflows/seed.md", "# unrelated drift\n")

    with pytest.raises(anchor.AnchorError, match="tracked unstaged drift"):
        anchor.verify_anchor(
            source_root_raw=str(lane["source"]),
            canonical_root_raw=str(lane["canonical"]),
            ledger_root_raw=str(ledger_root),
            plan_value=plan,
        )

    assert canonical.read_bytes() == canonical_before
    assert ledger.read_bytes() == ledger_before


def test_exact_state_is_idempotent_with_a_fresh_plan(lane):
    first = render(lane)
    assert write_plan(lane, first)["status"] == "PASS"
    second = render(lane)
    assert second["canonical_prestate"]["exists"] is True
    assert second["ledger_update"]["mode"] == "EXACT"
    before = (lane["primary"] / anchor.LEDGER_RELATIVE).read_bytes()
    assert write_plan(lane, second)["status"] == "PASS"
    assert (lane["primary"] / anchor.LEDGER_RELATIVE).read_bytes() == before


def test_crlf_ledger_style_is_preserved(lane):
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    ledger.write_bytes(LEDGER_HEADER.replace("\n", "\r\n").encode("utf-8"))
    plan = render(lane)
    assert plan["ledger_prestate"]["newline"] == "CRLF"
    assert plan["ledger_poststate"]["newline"] == "CRLF"
    assert write_plan(lane, plan)["status"] == "PASS"
    payload = ledger.read_bytes()
    assert anchor._ledger_payload_state(payload) == plan["ledger_poststate"]
    assert b"\r\n" in payload
    assert b"\n" not in payload.replace(b"\r\n", b"")


def test_ledger_failure_retains_verified_canonical_copy(lane):
    plan = render(lane)

    def fail_ledger(path: Path, payload: bytes, root: Path) -> None:
        raise OSError("injected")

    result = write_plan(lane, plan, ledger_writer=fail_ledger)
    assert result["status"] == "RECOVERING"
    assert result["canonical"]["correct"] is True
    assert (lane["canonical"] / SOURCE_RELATIVE).read_bytes() == lane["source_payload"]
    assert plan["ledger_update"]["row"] not in (
        lane["primary"] / anchor.LEDGER_RELATIVE
    ).read_text(encoding="utf-8")


def test_write_rechecks_ledger_mode_or_type_after_writer(lane, monkeypatch):
    plan = render(lane)
    original = anchor._require_ledger_content_only_drift
    calls = 0

    def inject_postwrite_drift(root: Path, relative: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise anchor.AnchorError("ledger has tracked mode or type drift")
        original(root, relative)

    monkeypatch.setattr(
        anchor, "_require_ledger_content_only_drift", inject_postwrite_drift
    )
    result = write_plan(lane, plan)

    assert calls == 2
    assert result["status"] == "RECOVERING"
    assert result["canonical"]["correct"] is True
    assert result["ledger"]["correct"] is False
    assert result["reason"] == "ledger mode or type drifted during write"


@pytest.mark.parametrize("target", ["source", "ledger", "canonical"])
def test_write_rejects_source_and_prestate_drift(lane, target):
    plan = render(lane)
    if target == "source":
        write(lane["source"] / SOURCE_RELATIVE, b"drift\n")
    elif target == "ledger":
        with (lane["primary"] / anchor.LEDGER_RELATIVE).open("ab") as handle:
            handle.write(b"\n")
    else:
        write(lane["canonical"] / SOURCE_RELATIVE, b"unexpected\n")
    with pytest.raises(anchor.AnchorError, match="drifted"):
        write_plan(lane, plan)


@pytest.mark.parametrize(
    ("root_key", "label"),
    (("source", "source"), ("canonical", "canonical"), ("primary", "ledger")),
)
def test_write_rejects_unrelated_tracked_drift_in_each_distinct_root(
    lane, root_key, label
):
    plan = render(lane)
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    ledger_before = ledger.read_bytes()
    write(lane[root_key] / "player_wiki/__init__.py", f"# {label} drift\n")

    with pytest.raises(anchor.AnchorError, match="tracked unstaged drift"):
        write_plan(lane, plan)

    assert not canonical.exists()
    assert ledger.read_bytes() == ledger_before


@pytest.mark.parametrize(
    ("root_key", "label"),
    (("source", "source"), ("canonical", "canonical"), ("primary", "ledger")),
)
def test_render_rejects_unrelated_tracked_drift_in_each_distinct_root(
    lane, root_key, label
):
    write(lane[root_key] / "docs/workflows/seed.md", f"# {label} drift\n")
    with pytest.raises(anchor.AnchorError, match="tracked unstaged drift"):
        render(lane)


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose executable mode drift")
def test_write_rejects_ledger_mode_only_drift_before_targets(lane):
    plan = render(lane)
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    git(lane["primary"], "config", "core.filemode", "true")
    ledger.chmod(ledger.stat().st_mode | 0o111)

    with pytest.raises(anchor.AnchorError, match="mode or type drift"):
        write_plan(lane, plan)

    assert not (lane["canonical"] / SOURCE_RELATIVE).exists()


def test_resealed_forged_ledger_row_is_rejected_without_target_writes(lane):
    plan = render(lane)
    forged = copy.deepcopy(plan)
    forged.pop("receipt_sha256")
    forged_commit = "f" * 40
    if forged_commit == plan["accepted"]["commit"]:
        forged_commit = "e" * 40
    forged["ledger_update"]["row"] = anchor._expected_row(
        plan["phase"],
        forged_commit,
        plan["accepted"]["tree"],
        plan["paths"]["canonical"],
        plan["source_record"]["bytes"],
        plan["source_record"]["sha256"],
        plan["finalized_utc"],
    )
    forged = evidence.seal_receipt(forged)
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    ledger_before = ledger.read_bytes()

    with pytest.raises(anchor.AnchorError, match="bound evidence"):
        write_plan(lane, forged)
    with pytest.raises(anchor.AnchorError, match="bound evidence"):
        verify_plan(lane, forged)

    assert not canonical.exists()
    assert ledger.read_bytes() == ledger_before


@pytest.mark.parametrize("field", ("bytes", "sha256", "newline"))
def test_resealed_forged_ledger_poststate_is_rejected_without_target_writes(
    lane, field
):
    plan = render(lane)
    forged = copy.deepcopy(plan)
    forged.pop("receipt_sha256")
    if field == "bytes":
        forged["ledger_poststate"][field] += 1
    elif field == "sha256":
        forged["ledger_poststate"][field] = (
            "f" * 64
            if forged["ledger_poststate"][field] != "f" * 64
            else "e" * 64
        )
    else:
        forged["ledger_poststate"][field] = (
            "CRLF" if forged["ledger_poststate"][field] == "LF" else "LF"
        )
    forged = evidence.seal_receipt(forged)
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    ledger_before = ledger.read_bytes()

    with pytest.raises(anchor.AnchorError, match="poststate"):
        write_plan(lane, forged)

    assert not canonical.exists()
    assert ledger.read_bytes() == ledger_before


def test_classification_is_mandatory_sealed_and_source_bound(lane):
    (lane["source"] / CLASSIFICATION_RELATIVE).unlink()
    with pytest.raises(anchor.AnchorError, match="does not exist"):
        render(lane)

    write(
        lane["source"] / CLASSIFICATION_RELATIVE,
        evidence.canonical_json_bytes(build_classification(lane["source_payload"])),
    )
    value = json.loads((lane["source"] / CLASSIFICATION_RELATIVE).read_text())
    value["source"]["bytes"] += 1
    write(
        lane["source"] / CLASSIFICATION_RELATIVE,
        evidence.canonical_json_bytes(value),
    )
    with pytest.raises(anchor.AnchorError, match="hash"):
        render(lane)

    value.pop("receipt_sha256")
    value["source"]["bytes"] -= 1
    value["source"]["path"] = ".local/roadmaps/other.md"
    value = evidence.seal_receipt(value)
    write(
        lane["source"] / CLASSIFICATION_RELATIVE,
        evidence.canonical_json_bytes(value),
    )
    with pytest.raises(anchor.AnchorError, match="source path mismatch"):
        render(lane)


def test_resealed_frozen_identity_tamper_and_foreign_repo_are_rejected(lane, tmp_path):
    path = lane["source"] / FROZEN_RELATIVE
    value = json.loads(path.read_text())
    value.pop("receipt_sha256")
    value["candidate"]["tree"] = "1" * 40
    write(path, evidence.canonical_json_bytes(evidence.seal_receipt(value)))
    with pytest.raises(anchor.AnchorError, match="does not match"):
        render(lane)

    foreign = tmp_path / "foreign"
    foreign.mkdir()
    git(foreign, "init", "-b", "main")
    with pytest.raises(anchor.AnchorError, match="common directory"):
        render(lane, ledger_root_raw=str(foreign))


def test_roots_refs_registration_alias_and_relative_paths_are_strict(lane, tmp_path):
    with pytest.raises(anchor.AnchorError, match="distinct worktrees"):
        render(lane, canonical_root_raw=str(lane["source"]))
    with pytest.raises(anchor.AnchorError, match="configured ref"):
        render(lane, source_ref="refs/heads/missing")
    with pytest.raises(anchor.AnchorError, match="traversal|must be .local/roadmaps"):
        render(lane, source_relative="../escape.md")
    copied = tmp_path / "copied"
    shutil.copytree(lane["source"], copied, ignore=shutil.ignore_patterns(".git"))
    with pytest.raises(anchor.AnchorError):
        render(lane, source_root_raw=str(copied))


def test_reparse_source_is_rejected_when_platform_can_create_it(lane):
    source_path = lane["source"] / SOURCE_RELATIVE
    target = lane["source"] / ".local/evidence/reparse-target.md"
    write(target, lane["source_payload"])
    source_path.unlink()
    try:
        source_path.symlink_to(target)
    except OSError:
        pytest.skip("test host cannot create an unprivileged symlink")
    with pytest.raises(anchor.AnchorError, match="reparse|normal file"):
        render(lane)


def test_source_must_be_ignored_untracked_and_ledger_tracked(lane):
    source = lane["source"]
    git(source, "add", "-f", SOURCE_RELATIVE)
    git(source, "commit", "-m", "track lifecycle")
    with pytest.raises(anchor.AnchorError, match="must be untracked"):
        render(lane)


def test_ledger_must_remain_tracked(lane):
    primary = lane["primary"]
    git(primary, "rm", "--cached", anchor.LEDGER_RELATIVE)
    git(primary, "commit", "-m", "untrack ledger")
    with pytest.raises(anchor.AnchorError, match="ledger must be a tracked"):
        render(lane)


def test_root_head_must_match_configured_ref(lane):
    source = lane["source"]
    write(source / "source-marker.txt", "advance\n")
    git(source, "add", "source-marker.txt")
    git(source, "commit", "-m", "advance source ref")
    old = lane["accepted"]
    git(source, "checkout", "--detach", old)
    with pytest.raises(anchor.AnchorError, match="HEAD does not match"):
        render(lane)


def test_ledger_wrong_path_untracked_and_mixed_newlines_are_rejected(lane):
    with pytest.raises(anchor.AnchorError, match="exactly"):
        render(lane, ledger_relative="docs/contracts/other.md")
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    payload = ledger.read_bytes().replace(b"\n", b"\r\n", 1)
    write(ledger, payload)
    with pytest.raises(anchor.AnchorError, match="uniform"):
        render(lane)


def test_duplicate_or_ambiguous_phase_and_path_rows_are_rejected(lane):
    plan = render(lane)
    row = plan["ledger_update"]["row"]
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    with ledger.open("a", encoding="utf-8", newline="") as handle:
        handle.write(row + "\n" + row + "\n")
    with pytest.raises(anchor.AnchorError, match="duplicate or ambiguous"):
        render(lane)


def test_replacement_requires_explicit_authorization(lane):
    plan = render(lane)
    assert write_plan(lane, plan)["status"] == "PASS"
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            plan["ledger_update"]["row"],
            plan["ledger_update"]["row"].replace(str(len(lane["source_payload"])), "999"),
        ),
        encoding="utf-8",
        newline="",
    )
    with pytest.raises(anchor.AnchorError, match="explicit authorization"):
        render(lane)
    replacement = render(lane, replacement_authorized=True)
    assert replacement["ledger_update"]["mode"] == "REPLACE"


def test_canonical_replacement_requires_explicit_authorization(lane):
    write(lane["canonical"] / SOURCE_RELATIVE, b"different retained bytes\n")
    with pytest.raises(anchor.AnchorError, match="canonical lifecycle replacement"):
        render(lane)
    replacement = render(lane, replacement_authorized=True)
    assert replacement["canonical_prestate"]["exists"] is True
    assert write_plan(lane, replacement)["status"] == "PASS"


def test_private_and_absolute_receipt_values_are_rejected(lane):
    classification_path = lane["source"] / CLASSIFICATION_RELATIVE
    value = json.loads(classification_path.read_text())
    value.pop("receipt_sha256")
    value["reviewer"] = r"C:\Users\person\review.txt"
    write(
        classification_path,
        evidence.canonical_json_bytes(evidence.seal_receipt(value)),
    )
    with pytest.raises(anchor.AnchorError, match="absolute or personal path"):
        render(lane)


def test_posix_absolute_receipt_value_is_rejected(lane):
    classification_path = lane["source"] / CLASSIFICATION_RELATIVE
    value = json.loads(classification_path.read_text())
    value.pop("receipt_sha256")
    value["reviewer"] = "/tmp/reviewer.txt"
    write(
        classification_path,
        evidence.canonical_json_bytes(evidence.seal_receipt(value)),
    )
    with pytest.raises(anchor.AnchorError, match="absolute or personal path"):
        render(lane)


def test_resealed_embedded_posix_absolute_reviewer_is_rejected(lane):
    classification_path = lane["source"] / CLASSIFICATION_RELATIVE
    value = json.loads(classification_path.read_text())
    value.pop("receipt_sha256")
    value["reviewer"] = "reviewer(path=/tmp/private-review.txt)"
    write(
        classification_path,
        evidence.canonical_json_bytes(evidence.seal_receipt(value)),
    )

    with pytest.raises(anchor.AnchorError, match="absolute or personal path"):
        render(lane)


@pytest.mark.parametrize(
    "value",
    (
        "reviewer(path=/tmp/private-review.txt)",
        "reviewer:path=/var/private/review.txt",
        "reviewer[/opt/private/review.txt]",
        "reviewer={/srv/private/review.txt}",
        r"reviewer(path=C:\Users\person\review.txt)",
        "reviewer[path=D:/private/review.txt]",
        "reviewer=C://private/review.txt",
        r"reviewer=\\server\share\review.txt",
        "reviewer(//server/share/review.txt)",
        "reviewer=file:///tmp/review.txt",
        "reviewer=file:/home/person/review.txt",
        "reviewer=file:C:/Users/person/review.txt",
        "reviewer[file://server/share/review.txt]",
        "reviewer=FILE:%2Fhome%2Fperson%2Freview.txt",
        "reviewer=FILE%3A%2Fhome%2Fperson%2Freview.txt",
    ),
)
def test_embedded_absolute_path_boundary_matrix_is_rejected(value):
    with pytest.raises(anchor.AnchorError, match="absolute or personal path"):
        anchor._safe_scalar(value, label="reviewer")


@pytest.mark.parametrize(
    "value",
    (
        "https://example.invalid/reviews/123",
        "reviewer(url=https://example.invalid/reviews/123)",
        "https://example.invalid/a?next=/srv/docs&drive=C:/docs",
        "https://example.invalid/a;b/c?next=/srv/docs&drive=C:/docs",
        "https://example.invalid/a,b/c?next=/srv/docs&drive=C:/docs",
        "reviewer(url=https://example.invalid/a(b)/c?next=/srv/docs&drive=C:/docs)",
        "git+ssh://example.invalid/repository.git",
        ".local/evidence/review.json",
        "refs/heads/main",
        "2026-08-01T12:34:56Z",
        "A / B",
        "phase: A / B",
        "ratio A/B",
    ),
)
def test_path_sanitization_safe_scalar_matrix_is_accepted(value):
    assert anchor._safe_scalar(value, label="reviewer") == value


def test_url_mask_does_not_hide_a_later_absolute_path():
    value = (
        "See https://example.invalid/a?next=/srv/docs&drive=C:/docs; "
        "evidence=/home/person/review.txt"
    )
    with pytest.raises(anchor.AnchorError, match="absolute or personal path"):
        anchor._reject_unsafe_values({"reviewer": value})


@pytest.mark.parametrize(
    "value",
    (
        "https://example.invalid/a;b/c?next=/srv/docs&drive=C:/docs /home/person/x",
        'https://example.invalid/a,b/c?next=/srv/docs&drive=C:/docs"/home/person/x',
        "https://example.invalid/a(b)/c?next=/srv/docs&drive=C:/docs'/home/person/x",
    ),
)
def test_url_mask_stops_before_separate_or_quoted_absolute_path(value):
    with pytest.raises(anchor.AnchorError, match="absolute or personal path"):
        anchor._safe_scalar(value, label="reviewer")


def test_ordinary_slash_phase_survives_recursive_plan_sanitization(lane):
    plan = render(lane, phase="A / B")
    assert plan["phase"] == "A / B"
    assert "| A / B |" in plan["ledger_update"]["row"]


def test_tampered_or_wrong_identity_plan_is_rejected(lane):
    plan = render(lane)
    tampered = copy.deepcopy(plan)
    tampered["accepted"]["commit"] = "1" * 40
    with pytest.raises(anchor.AnchorError, match="hash"):
        write_plan(lane, tampered)
    tampered.pop("receipt_sha256")
    tampered = evidence.seal_receipt(tampered)
    with pytest.raises(anchor.AnchorError, match="bound evidence|accepted identity"):
        write_plan(lane, tampered)


def test_verify_reports_recovering_without_target_writes(lane):
    plan = render(lane)
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    before = ledger.read_bytes()
    result = verify_plan(lane, plan)
    assert result["status"] == "RECOVERING"
    assert not canonical.exists()
    assert ledger.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    ("append", "remove", "alter", "newline", "reorder"),
)
def test_verify_requires_exact_sealed_ledger_poststate(lane, mutation):
    plan = render(lane)
    assert write_plan(lane, plan)["status"] == "PASS"
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    canonical_before = canonical.read_bytes()
    payload = ledger.read_bytes()
    row_line = (plan["ledger_update"]["row"] + "\n").encode("utf-8")

    if mutation == "append":
        mutated = payload + b"Unrelated appended ledger content.\n"
    elif mutation == "remove":
        assert b"Ledger prose.\n" in payload
        mutated = payload.replace(b"Ledger prose.\n", b"", 1)
    elif mutation == "alter":
        assert b"Ledger prose." in payload
        mutated = payload.replace(b"Ledger prose.", b"Changed ledger prose.", 1)
    elif mutation == "newline":
        mutated = payload.replace(b"\n", b"\r\n")
    else:
        assert payload.count(row_line) == 1
        mutated = payload.replace(row_line, b"", 1) + row_line
    assert mutated != payload
    ledger.write_bytes(mutated)

    result = verify_plan(lane, plan)

    assert result["status"] == "RECOVERING"
    assert result["ledger"]["correct"] is False
    assert result["reason"] == (
        "ledger bytes do not match the sealed deterministic poststate"
    )
    assert canonical.read_bytes() == canonical_before
    assert ledger.read_bytes() == mutated


def test_verify_rejects_ledger_type_drift_after_pass(lane):
    plan = render(lane)
    assert write_plan(lane, plan)["status"] == "PASS"
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    canonical_before = canonical.read_bytes()
    ledger.unlink()
    ledger.mkdir()

    with pytest.raises(anchor.AnchorError, match="mode or type drift|normal file"):
        verify_plan(lane, plan)

    assert canonical.read_bytes() == canonical_before
    assert ledger.is_dir()


def test_verify_rejects_ledger_reparse_drift_after_pass_when_supported(lane):
    plan = render(lane)
    assert write_plan(lane, plan)["status"] == "PASS"
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    canonical_before = canonical.read_bytes()
    target = lane["primary"] / ".local/evidence/ledger-target.md"
    write(target, ledger.read_bytes())
    ledger.unlink()
    try:
        ledger.symlink_to(target)
    except OSError:
        pytest.skip("test host cannot create an unprivileged symlink")

    with pytest.raises(
        anchor.AnchorError, match="mode or type drift|reparse|normal file"
    ):
        verify_plan(lane, plan)

    assert canonical.read_bytes() == canonical_before
    assert ledger.is_symlink()


@pytest.mark.parametrize(
    ("root_key", "label"),
    (("source", "source"), ("canonical", "canonical"), ("primary", "ledger")),
)
def test_verify_rejects_unrelated_tracked_drift_in_each_distinct_root(
    lane, root_key, label
):
    plan = render(lane)
    assert write_plan(lane, plan)["status"] == "PASS"
    canonical = lane["canonical"] / SOURCE_RELATIVE
    ledger = lane["primary"] / anchor.LEDGER_RELATIVE
    canonical_before = canonical.read_bytes()
    ledger_before = ledger.read_bytes()
    write(lane[root_key] / "player_wiki/__init__.py", f"# {label} drift\n")

    with pytest.raises(anchor.AnchorError, match="tracked unstaged drift"):
        verify_plan(lane, plan)

    assert canonical.read_bytes() == canonical_before
    assert ledger.read_bytes() == ledger_before


def test_render_uses_only_read_only_git_subcommands(lane, monkeypatch):
    calls: list[list[str]] = []
    original = anchor.subprocess.run

    def record(command, *args, **kwargs):
        if command and command[0] == "git":
            calls.append(list(command))
        return original(command, *args, **kwargs)

    monkeypatch.setattr(anchor.subprocess, "run", record)
    render(lane)
    forbidden = {
        "add",
        "commit",
        "checkout",
        "switch",
        "fetch",
        "push",
        "merge",
        "reset",
        "clean",
        "worktree add",
        "worktree remove",
    }
    joined = [" ".join(call[3:5]) for call in calls]
    assert not any(item in forbidden for item in joined)


def test_cli_writes_canonical_receipts(lane):
    plan_output = lane["source"] / PLAN_RELATIVE
    command = [
        sys.executable,
        str(SCRIPTS / "phase_closeout_anchor.py"),
        "render",
        "--source-root",
        str(lane["source"]),
        "--canonical-root",
        str(lane["canonical"]),
        "--ledger-root",
        str(lane["primary"]),
        "--source-ref",
        "refs/heads/source",
        "--canonical-ref",
        "refs/heads/canonical",
        "--ledger-ref",
        "refs/heads/main",
        "--source-path",
        SOURCE_RELATIVE,
        "--canonical-path",
        SOURCE_RELATIVE,
        "--ledger-path",
        anchor.LEDGER_RELATIVE,
        "--frozen-identity",
        FROZEN_RELATIVE,
        "--classification-receipt",
        CLASSIFICATION_RELATIVE,
        "--phase",
        PHASE,
        "--finalized-utc",
        FINALIZED,
        "--output",
        str(plan_output),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = evidence.load_json(plan_output)
    assert anchor._verify_plan_shape(plan) is plan

    for action, output in (("write", WRITE_RELATIVE), ("verify", VERIFY_RELATIVE)):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "phase_closeout_anchor.py"),
                action,
                "--source-root",
                str(lane["source"]),
                "--canonical-root",
                str(lane["canonical"]),
                "--ledger-root",
                str(lane["primary"]),
                "--plan",
                str(plan_output),
                "--output",
                str(lane["source"] / output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        receipt = evidence.load_json(lane["source"] / output)
        assert receipt["status"] == "PASS"
        assert receipt["receipt_sha256"]


@pytest.mark.skipif(os.name != "nt", reason="PowerShell wrapper contract is Windows-only")
@pytest.mark.windows_host
def test_powershell_wrapper_success_nonzero_and_lock_unwind(lane):
    powershell = shutil.which("powershell.exe")
    assert powershell
    plan_output = lane["source"] / PLAN_RELATIVE
    common = Path(git(lane["source"], "rev-parse", "--path-format=absolute", "--git-common-dir"))
    lock = common / "campaign-player-wiki-complete-validation.lock"
    common_arguments = [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "local.ps1"),
        "-PythonPath",
        sys.executable,
        "-PhaseCloseoutSourceRoot",
        str(lane["source"]),
        "-PhaseCloseoutCanonicalRoot",
        str(lane["canonical"]),
        "-PhaseCloseoutLedgerRoot",
        str(lane["primary"]),
    ]
    render_result = subprocess.run(
        [
            powershell,
            *common_arguments,
            "-Action",
            "phase-closeout-anchor-render",
            "-PhaseCloseoutSourceRef",
            "refs/heads/source",
            "-PhaseCloseoutCanonicalRef",
            "refs/heads/canonical",
            "-PhaseCloseoutLedgerRef",
            "refs/heads/main",
            "-PhaseCloseoutSourcePath",
            SOURCE_RELATIVE,
            "-PhaseCloseoutCanonicalPath",
            SOURCE_RELATIVE,
            "-PhaseCloseoutLedgerPath",
            anchor.LEDGER_RELATIVE,
            "-PhaseCloseoutFrozenIdentity",
            FROZEN_RELATIVE,
            "-PhaseCloseoutClassificationReceipt",
            CLASSIFICATION_RELATIVE,
            "-PhaseCloseoutPhase",
            PHASE,
            "-PhaseCloseoutFinalizedUtc",
            FINALIZED,
            "-PhaseCloseoutOutput",
            str(plan_output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert render_result.returncode == 0, render_result.stderr
    write_result = subprocess.run(
        [
            powershell,
            *common_arguments,
            "-Action",
            "phase-closeout-anchor-write",
            "-PhaseCloseoutPlan",
            str(plan_output),
            "-PhaseCloseoutOutput",
            str(lane["source"] / WRITE_RELATIVE),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert write_result.returncode == 0, write_result.stderr
    probe = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            (
                "& { param([string]$p) "
                "$s=[IO.File]::Open($p,[IO.FileMode]::OpenOrCreate,"
                "[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$s.Dispose() }"
            ),
            str(lock),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr
    bad = subprocess.run(
        [
            powershell,
            *common_arguments,
            "-Action",
            "phase-closeout-anchor-verify",
            "-PhaseCloseoutPlan",
            str(lane["source"] / ".local/evidence/missing.json"),
            "-PhaseCloseoutOutput",
            str(lane["source"] / VERIFY_RELATIVE),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0
