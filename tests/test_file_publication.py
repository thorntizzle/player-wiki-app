from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from player_wiki import file_publication
from player_wiki.publisher import PublishError, create_frontmatter, write_markdown_file


class InjectedPublicationError(OSError):
    pass


def _temp_siblings(destination: Path) -> list[Path]:
    return sorted(destination.parent.glob(".*.tmp"))


def test_text_and_bytes_create_and_overwrite_match_direct_path_rendering(tmp_path):
    text_path = tmp_path / "article.md"
    reference_path = tmp_path / "reference.md"
    bytes_path = tmp_path / "asset.bin"

    text = "heading\nbody\n"
    reference_path.write_text(text, encoding="utf-8")
    assert file_publication.atomic_write_text(text_path, text) == len(text)
    assert text_path.read_bytes() == reference_path.read_bytes()

    updated_text = "updated\narticle\n"
    reference_path.write_text(updated_text, encoding="utf-8")
    assert file_publication.atomic_write_text(text_path, updated_text) == len(updated_text)
    assert text_path.read_bytes() == reference_path.read_bytes()

    assert file_publication.atomic_write_bytes(bytes_path, b"first\x00asset") == 11
    assert bytes_path.read_bytes() == b"first\x00asset"
    assert file_publication.atomic_write_bytes(bytes_path, b"replacement\xff") == 12
    assert bytes_path.read_bytes() == b"replacement\xff"
    assert _temp_siblings(text_path) == []
    assert _temp_siblings(bytes_path) == []


def test_short_writes_are_retried_until_the_entire_payload_is_written():
    class ShortWriter:
        def __init__(self):
            self.payload = b""

        def write(self, data):
            accepted = data[:2]
            self.payload += accepted
            return len(accepted)

    writer = ShortWriter()
    assert file_publication._write_full_payload(writer, b"complete") == 8
    assert writer.payload == b"complete"


def test_publication_uses_unique_dot_prefixed_siblings_and_replaces_only_after_sync(
    tmp_path,
    monkeypatch,
):
    destination = tmp_path / "visible.txt"
    destination.write_bytes(b"old")
    replacement_sources = []
    original_replace = file_publication._replace_file

    def inspect_replace(source: Path, final: Path) -> None:
        assert final == destination
        assert source.parent == destination.parent
        assert source.name.startswith(".")
        assert source.name.endswith(".tmp")
        expected_visible = b"old" if not replacement_sources else b"new-one"
        assert destination.read_bytes() == expected_visible
        expected = b"new-one" if not replacement_sources else b"new-two"
        assert source.read_bytes() == expected
        replacement_sources.append(source)
        original_replace(source, final)

    monkeypatch.setattr(file_publication, "_replace_file", inspect_replace)

    file_publication.atomic_write_bytes(destination, b"new-one")
    file_publication.atomic_write_bytes(destination, b"new-two")

    assert destination.read_bytes() == b"new-two"
    assert len(replacement_sources) == 2
    assert replacement_sources[0] != replacement_sources[1]
    assert all(not path.exists() for path in replacement_sources)


def test_exclusive_temp_creation_retries_a_name_collision(tmp_path, monkeypatch):
    destination = tmp_path / "publication.bin"
    collided_temp = tmp_path / ".deadbeef.tmp"
    collided_temp.write_bytes(b"unrelated-temp")
    tokens = iter(["deadbeef", "feedface"])
    monkeypatch.setattr(file_publication.secrets, "token_hex", lambda _size: next(tokens))

    file_publication.atomic_write_bytes(destination, b"published")

    assert destination.read_bytes() == b"published"
    assert collided_temp.read_bytes() == b"unrelated-temp"
    assert not (tmp_path / ".feedface.tmp").exists()


def test_overwrite_orders_sync_close_mode_replace_and_directory_sync(tmp_path, monkeypatch):
    destination = tmp_path / "publication.bin"
    destination.write_bytes(b"old")
    events = []

    for function_name, event_name in (
        ("_write_full_payload", "write"),
        ("_flush_file", "flush"),
        ("_fsync_file", "fsync"),
        ("_close_file", "close"),
        ("_set_file_mode", "mode"),
        ("_replace_file", "replace"),
        ("_sync_parent_directory_best_effort", "directory-sync"),
    ):
        original = getattr(file_publication, function_name)

        def record(*args, _original=original, _event=event_name, **kwargs):
            events.append(_event)
            return _original(*args, **kwargs)

        monkeypatch.setattr(file_publication, function_name, record)

    file_publication.atomic_write_bytes(destination, b"new")

    assert events == [
        "write",
        "flush",
        "fsync",
        "close",
        "mode",
        "replace",
        "directory-sync",
    ]
    assert destination.read_bytes() == b"new"


@pytest.mark.parametrize(
    "failure_stage",
    ["write", "flush", "fsync", "close", "mode", "replace"],
)
@pytest.mark.parametrize("destination_exists", [False, True])
def test_precommit_failures_preserve_old_or_absent_destination_and_clean_temp(
    tmp_path,
    monkeypatch,
    failure_stage,
    destination_exists,
):
    if failure_stage == "mode" and not destination_exists:
        pytest.skip("Mode preservation applies only to overwrites.")

    destination = tmp_path / "publication.bin"
    if destination_exists:
        destination.write_bytes(b"old-durable-bytes")

    def fail(*_args, **_kwargs):
        raise InjectedPublicationError(f"injected {failure_stage} failure")

    if failure_stage == "write":
        def fail_after_partial_write(handle, payload):
            handle.write(payload[:4])
            fail()

        monkeypatch.setattr(file_publication, "_write_full_payload", fail_after_partial_write)
    elif failure_stage == "close":
        original_close = file_publication._close_file

        def fail_after_close(handle):
            original_close(handle)
            fail()

        monkeypatch.setattr(file_publication, "_close_file", fail_after_close)
    elif failure_stage == "mode":
        monkeypatch.setattr(file_publication, "_set_file_mode", fail)
    else:
        monkeypatch.setattr(file_publication, f"_{failure_stage}_file", fail)

    with pytest.raises(
        InjectedPublicationError,
        match=f"injected {failure_stage} failure",
    ):
        file_publication.atomic_write_bytes(destination, b"new-partial-bytes")

    if destination_exists:
        assert destination.read_bytes() == b"old-durable-bytes"
    else:
        assert not destination.exists()
    assert _temp_siblings(destination) == []


def test_cleanup_failure_does_not_mask_primary_precommit_error(
    tmp_path,
    monkeypatch,
):
    destination = tmp_path / "publication.bin"
    destination.write_bytes(b"old")
    original_unlink = Path.unlink

    def fail_replace(*_args, **_kwargs):
        raise InjectedPublicationError("primary replace failure")

    def fail_cleanup(path: Path, *_args, **_kwargs):
        if (
            path.parent == destination.parent
            and path.name.startswith(".")
            and path.suffix == ".tmp"
        ):
            raise PermissionError("injected cleanup failure")
        return original_unlink(path, *_args, **_kwargs)

    monkeypatch.setattr(file_publication, "_replace_file", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)

    with pytest.raises(InjectedPublicationError, match="primary replace failure"):
        file_publication.atomic_write_bytes(destination, b"new")

    assert destination.read_bytes() == b"old"
    monkeypatch.setattr(Path, "unlink", original_unlink)
    for temp_path in _temp_siblings(destination):
        temp_path.unlink()


def test_postcommit_directory_sync_failure_keeps_successful_publication(
    tmp_path,
    monkeypatch,
):
    destination = tmp_path / "publication.bin"
    destination.write_bytes(b"old")

    monkeypatch.setattr(
        file_publication,
        "_sync_parent_directory_best_effort",
        lambda _parent: (_ for _ in ()).throw(RuntimeError("injected directory sync bug")),
    )

    assert file_publication.atomic_write_bytes(destination, b"committed") == 9
    assert destination.read_bytes() == b"committed"
    assert _temp_siblings(destination) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode preservation contract")
def test_overwrite_preserves_posix_mode(tmp_path):
    destination = tmp_path / "publication.bin"
    destination.write_bytes(b"old")
    destination.chmod(0o640)

    file_publication.atomic_write_bytes(destination, b"new")

    assert stat.S_IMODE(destination.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name != "posix", reason="POSIX umask contract")
def test_new_file_mode_matches_direct_path_write_under_umask(tmp_path):
    direct_path = tmp_path / "direct.bin"
    atomic_path = tmp_path / "atomic.bin"
    previous_umask = os.umask(0o027)
    try:
        direct_path.write_bytes(b"direct")
        file_publication.atomic_write_bytes(atomic_path, b"atomic")
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(atomic_path.stat().st_mode) == stat.S_IMODE(direct_path.stat().st_mode)


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only overwrite contract")
def test_windows_read_only_destination_still_rejects_overwrite(tmp_path):
    destination = tmp_path / "publication.bin"
    destination.write_bytes(b"old")
    destination.chmod(stat.S_IREAD)

    try:
        with pytest.raises(PermissionError):
            file_publication.atomic_write_bytes(destination, b"new")
        assert destination.read_bytes() == b"old"
    finally:
        destination.chmod(stat.S_IWRITE)
        for temp_path in _temp_siblings(destination):
            temp_path.chmod(stat.S_IWRITE)
            temp_path.unlink()


def test_publisher_preserves_exact_output_force_and_parent_creation(tmp_path):
    destination = tmp_path / "drafts" / "note.md"
    reference = tmp_path / "reference.md"
    metadata = {
        "title": "Atomic Note",
        "slug": "notes/atomic-note",
        "section": "Notes",
        "type": "note",
        "published": False,
    }
    body = "\n Body line one.\n\nBody line two. \n"
    expected = f"{create_frontmatter(metadata)}\n{body.strip()}\n"
    reference.write_text(expected, encoding="utf-8")

    write_markdown_file(destination, metadata, body)

    assert destination.read_bytes() == reference.read_bytes()
    with pytest.raises(PublishError, match="Destination already exists"):
        write_markdown_file(destination, metadata, "refused")
    assert destination.read_bytes() == reference.read_bytes()

    write_markdown_file(destination, metadata, "forced replacement", force=True)
    forced = f"{create_frontmatter(metadata)}\nforced replacement\n"
    reference.write_text(forced, encoding="utf-8")
    assert destination.read_bytes() == reference.read_bytes()
