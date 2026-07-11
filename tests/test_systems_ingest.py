from __future__ import annotations

from io import BytesIO
from pathlib import Path
import stat
import zipfile

import pytest

from player_wiki.input_limits import (
    IngressLimitError,
    decode_bounded_base64_to_spool,
    spool_bounded_stream,
)
from tests.helpers.systems_import_helpers import _build_malformed_utf8_systems_import_archive
from player_wiki.systems_ingest import (
    DEFAULT_SYSTEMS_ARCHIVE_LIMITS,
    SystemsArchiveLimits,
    SystemsIngestError,
    _prepare_archive_source,
    _validate_archive_members,
    configured_systems_archive_limits,
    extracted_systems_archive,
)


def _limits(**overrides: int) -> SystemsArchiveLimits:
    values = {
        "max_raw_bytes": 1024,
        "max_compressed_bytes": 1024,
        "max_entries": 10,
        "max_member_bytes": 1024,
        "max_total_uncompressed_bytes": 2048,
        "max_compression_ratio": 200,
    }
    values.update(overrides)
    return SystemsArchiveLimits(**values)


def _info(
    name: str,
    *,
    file_size: int = 1,
    compress_size: int = 1,
    compress_type: int = zipfile.ZIP_DEFLATED,
) -> zipfile.ZipInfo:
    member = zipfile.ZipInfo(name)
    member.file_size = file_size
    member.compress_size = compress_size
    member.compress_type = compress_type
    member.create_system = 3
    member.external_attr = (
        (stat.S_IFDIR | 0o755) if name.endswith("/") else (stat.S_IFREG | 0o600)
    ) << 16
    return member


def _archive_bytes(entries: dict[str, bytes], *, wrapper: str = "") -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(f"{wrapper}{name}", value)
    return output.getvalue()


def test_default_systems_archive_limits_match_approved_policy():
    assert DEFAULT_SYSTEMS_ARCHIVE_LIMITS == SystemsArchiveLimits(
        max_raw_bytes=64 * 1024**2,
        max_compressed_bytes=64 * 1024**2,
        max_entries=20_000,
        max_member_bytes=32 * 1024**2,
        max_total_uncompressed_bytes=512 * 1024**2,
        max_compression_ratio=200,
    )


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "1", None])
def test_systems_archive_limits_reject_bool_and_invalid_values(value):
    with pytest.raises(ValueError, match="positive integer"):
        SystemsArchiveLimits(max_entries=value)

    if value is not None:
        with pytest.raises(ValueError, match="SystemsArchiveLimits instance"):
            configured_systems_archive_limits(value)


def test_metadata_count_compressed_member_total_and_ratio_boundaries():
    members = [_info("one"), _info("two"), _info("three")]
    assert len(_validate_archive_members(members, limits=_limits(max_entries=3))) == 3
    with pytest.raises(SystemsIngestError, match="too many entries"):
        _validate_archive_members(members, limits=_limits(max_entries=2))

    exact_member = _info("member", file_size=32, compress_size=1)
    _validate_archive_members([exact_member], limits=_limits(max_member_bytes=32))
    with pytest.raises(SystemsIngestError, match="file that is too large"):
        _validate_archive_members([exact_member], limits=_limits(max_member_bytes=31))

    total_members = [
        _info("first", file_size=8, compress_size=1),
        _info("second", file_size=8, compress_size=1),
    ]
    _validate_archive_members(total_members, limits=_limits(max_total_uncompressed_bytes=16))
    with pytest.raises(SystemsIngestError, match="expanded content"):
        _validate_archive_members(total_members, limits=_limits(max_total_uncompressed_bytes=15))

    compressed_members = [
        _info("first", file_size=8, compress_size=5),
        _info("second", file_size=8, compress_size=5),
    ]
    _validate_archive_members(compressed_members, limits=_limits(max_compressed_bytes=10))
    with pytest.raises(SystemsIngestError, match="compressed content"):
        _validate_archive_members(compressed_members, limits=_limits(max_compressed_bytes=9))

    ratio_member = _info("ratio", file_size=200, compress_size=1)
    _validate_archive_members([ratio_member], limits=_limits(max_compression_ratio=200))
    with pytest.raises(SystemsIngestError, match="ratio"):
        _validate_archive_members([ratio_member], limits=_limits(max_compression_ratio=199))

    with pytest.raises(SystemsIngestError, match="compression metadata"):
        _validate_archive_members(
            [_info("zero", file_size=1, compress_size=0)],
            limits=_limits(),
        )


def test_approved_metadata_limits_accept_exact_values_and_reject_plus_one():
    exact_entry_count = [
        _info(f"directory-{index}/", file_size=0, compress_size=0)
        for index in range(20_000)
    ]
    assert len(
        _validate_archive_members(exact_entry_count, limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS)
    ) == 20_000
    with pytest.raises(SystemsIngestError, match="too many entries"):
        _validate_archive_members(
            exact_entry_count + [_info("one-too-many/", file_size=0, compress_size=0)],
            limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS,
        )

    exact_member = _info(
        "exact-member",
        file_size=32 * 1024**2,
        compress_size=32 * 1024**2,
    )
    _validate_archive_members([exact_member], limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS)
    with pytest.raises(SystemsIngestError, match="file that is too large"):
        _validate_archive_members(
            [
                _info(
                    "large-member",
                    file_size=32 * 1024**2 + 1,
                    compress_size=32 * 1024**2,
                )
            ],
            limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS,
        )

    exact_total = [
        _info(
            f"total-{index}",
            file_size=32 * 1024**2,
            compress_size=1 * 1024**2,
        )
        for index in range(16)
    ]
    _validate_archive_members(exact_total, limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS)
    with pytest.raises(SystemsIngestError, match="expanded content"):
        _validate_archive_members(
            exact_total + [_info("total-plus-one", file_size=1, compress_size=1)],
            limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS,
        )

    exact_compressed = [
        _info("compressed-first", file_size=32 * 1024**2, compress_size=32 * 1024**2),
        _info("compressed-second", file_size=32 * 1024**2, compress_size=32 * 1024**2),
    ]
    _validate_archive_members(exact_compressed, limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS)
    with pytest.raises(SystemsIngestError, match="compressed content"):
        _validate_archive_members(
            [
                exact_compressed[0],
                _info(
                    "compressed-plus-one",
                    file_size=32 * 1024**2,
                    compress_size=32 * 1024**2 + 1,
                ),
            ],
            limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS,
        )


class _SizedSeekable:
    def __init__(self, size: int) -> None:
        self.size = size
        self.position = 0

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.position = offset
        elif whence == 2:
            self.position = self.size + offset
        else:
            self.position += offset
        return self.position


def test_approved_raw_archive_limit_accepts_exact_size_and_rejects_plus_one():
    exact = _SizedSeekable(64 * 1024**2)
    stream, should_close = _prepare_archive_source(
        exact,
        limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS,
    )
    assert stream is exact
    assert should_close is False
    assert exact.tell() == 0

    with pytest.raises(SystemsIngestError, match="too large"):
        _prepare_archive_source(
            _SizedSeekable(64 * 1024**2 + 1),
            limits=DEFAULT_SYSTEMS_ARCHIVE_LIMITS,
        )


@pytest.mark.parametrize(
    "name, message",
    [
        ("../data/file.json", "parent-relative"),
        ("data/../file.json", "parent-relative"),
        ("/data/file.json", "absolute or backslash"),
        (r"\\server\share\file.json", "absolute or backslash"),
        (r"C:\data\file.json", "absolute or backslash"),
        (r"data\file.json", "absolute or backslash"),
        ("data/bad\x01name.json", "invalid file path"),
        ("data/bad\u200bname.json", "invalid file path"),
        ("data/e\u0301.json", "normalized Unicode"),
        ("data/name?.json", "Windows-unsafe"),
        ("data/name. ", "Windows-unsafe"),
        ("data/CON.json", "Windows-reserved"),
        (f"data/{'x' * 256}.json", "invalid file path"),
        (f"data/{'\u00e9' * 128}.json", "invalid file path"),
    ],
)
def test_archive_member_paths_reject_unsafe_cross_platform_names(name, message):
    with pytest.raises(SystemsIngestError, match=message):
        _validate_archive_members([_info(name)], limits=_limits())


def test_windows_superscript_device_aliases_are_rejected_case_insensitively():
    for name in (
        "data/CoM¹.txt",
        "data/cOm².JSON",
        "data/COM³",
        "data/LpT¹.txt",
        "data/lPT².JSON",
        "data/LPT³",
    ):
        with pytest.raises(SystemsIngestError, match="Windows-reserved"):
            _validate_archive_members([_info(name)], limits=_limits())


def test_raw_empty_and_dot_path_segments_are_rejected_before_normalization():
    for name in ("./data/file.json", "data/./file.json", "data//file.json"):
        with pytest.raises(SystemsIngestError, match="parent-relative paths"):
            _validate_archive_members([_info(name)], limits=_limits())


def test_archive_member_path_rejects_nul_even_when_supplied_by_fake_metadata():
    member = _info("placeholder")
    member.filename = "data/bad\x00name.json"
    member.orig_filename = member.filename
    with pytest.raises(SystemsIngestError, match="invalid file path"):
        _validate_archive_members([member], limits=_limits())


@pytest.mark.parametrize(
    "members, message",
    [
        ([_info("data/file"), _info("data/file")], "duplicate"),
        ([_info("data/File"), _info("data/file")], "duplicate"),
        ([_info("data"), _info("data/file")], "conflicting"),
        ([_info("data/file"), _info("data")], "conflicting"),
    ],
)
def test_archive_member_paths_reject_duplicates_and_prefix_collisions(members, message):
    with pytest.raises(SystemsIngestError, match=message):
        _validate_archive_members(members, limits=_limits())


def test_raw_dot_aliases_are_rejected_in_either_archive_order():
    for members in (
        [_info("data/file.json"), _info("data/./file.json")],
        [_info("data/./file.json"), _info("data/file.json")],
    ):
        with pytest.raises(SystemsIngestError, match="parent-relative paths"):
            _validate_archive_members(members, limits=_limits())


def test_archive_rejects_encrypted_unsupported_compression_and_special_types():
    encrypted = _info("encrypted")
    encrypted.flag_bits |= 0x1
    with pytest.raises(SystemsIngestError, match="Encrypted"):
        _validate_archive_members([encrypted], limits=_limits())

    with pytest.raises(SystemsIngestError, match="unsupported compression"):
        _validate_archive_members(
            [_info("bzip", compress_type=zipfile.ZIP_BZIP2)],
            limits=_limits(),
        )

    for special_type in (stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO):
        special = _info(f"special-{special_type}")
        special.external_attr = (special_type | 0o600) << 16
        with pytest.raises(SystemsIngestError, match="special entries"):
            _validate_archive_members([special], limits=_limits())


def test_raw_archive_exact_limit_passes_and_plus_one_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(tmp_path / "temp"))
    archive_bytes = _archive_bytes({"data/example.json": b"{}"})
    with extracted_systems_archive(
        archive_bytes,
        limits=_limits(max_raw_bytes=len(archive_bytes)),
    ) as data_root:
        assert (data_root / "data/example.json").read_bytes() == b"{}"

    with pytest.raises(SystemsIngestError, match="too large"):
        with extracted_systems_archive(
            archive_bytes,
            limits=_limits(max_raw_bytes=len(archive_bytes) - 1),
        ):
            pass
    assert list((tmp_path / "temp").iterdir()) == []


def test_valid_root_and_single_wrapper_data_layouts_extract_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(tmp_path / "temp"))
    for wrapper in ("", "source-export/"):
        archive_bytes = _archive_bytes(
            {"data/bestiary/bestiary-mm.json": b'{"monster": []}'},
            wrapper=wrapper,
        )
        with extracted_systems_archive(archive_bytes, limits=_limits()) as data_root:
            assert (data_root / "data/bestiary/bestiary-mm.json").is_file()
        assert list((tmp_path / "temp").iterdir()) == []


def test_highly_compressible_archive_is_stopped_by_ratio_before_temp_output(tmp_path, monkeypatch):
    archive_bytes = _archive_bytes({"data/repeated.json": b"A" * 4096})
    temp_root = tmp_path / "temp"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))
    with pytest.raises(SystemsIngestError, match="ratio"):
        with extracted_systems_archive(
            archive_bytes,
            limits=_limits(
                max_raw_bytes=len(archive_bytes),
                max_member_bytes=4096,
                max_total_uncompressed_bytes=4096,
                max_compression_ratio=10,
            ),
        ):
            pass
    assert not temp_root.exists()


def test_corrupt_crc_is_safely_translated_and_temp_is_cleaned(tmp_path, monkeypatch):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("data/file.json", b"safe-data")
        member = archive.getinfo("data/file.json")
    corrupted = bytearray(output.getvalue())
    name_length = int.from_bytes(corrupted[member.header_offset + 26 : member.header_offset + 28], "little")
    extra_length = int.from_bytes(corrupted[member.header_offset + 28 : member.header_offset + 30], "little")
    data_offset = member.header_offset + 30 + name_length + extra_length
    corrupted[data_offset] ^= 0x01

    temp_root = tmp_path / "temp"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))
    with pytest.raises(SystemsIngestError, match="safely extracted"):
        with extracted_systems_archive(bytes(corrupted), limits=_limits()):
            pass
    assert list(temp_root.iterdir()) == []


class _ShortChunkStream(BytesIO):
    def read(self, size: int = -1) -> bytes:
        return super().read(1 if size < 0 else min(size, 1))


def test_actual_stream_size_is_rechecked_when_metadata_underreports(monkeypatch, tmp_path):
    archive_bytes = _archive_bytes({"data/file.json": b"x"})
    original_open = zipfile.ZipFile.open

    def oversized_open(self, member, *args, **kwargs):
        if isinstance(member, zipfile.ZipInfo) and not member.is_dir():
            return _ShortChunkStream(b"xx")
        return original_open(self, member, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", oversized_open)
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(tmp_path / "temp"))
    with pytest.raises(SystemsIngestError, match="file that is too large"):
        with extracted_systems_archive(
            archive_bytes,
            limits=_limits(max_member_bytes=1),
        ):
            pass
    assert list((tmp_path / "temp").iterdir()) == []


def test_actual_stream_ratio_rechecks_exact_boundary_and_metadata_lies(
    monkeypatch,
    tmp_path,
):
    archive_bytes = _archive_bytes({"data/file.json": b"x"})
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        compressed_size = archive.getinfo("data/file.json").compress_size
    original_open = zipfile.ZipFile.open
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(tmp_path / "temp"))
    for extra_bytes, should_pass in ((0, True), (1, False)):
        actual_size = compressed_size * 200 + extra_bytes

        def lying_open(self, member, *args, **kwargs):
            if isinstance(member, zipfile.ZipInfo) and not member.is_dir():
                return BytesIO(b"x" * actual_size)
            return original_open(self, member, *args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "open", lying_open)
        if should_pass:
            with extracted_systems_archive(
                archive_bytes,
                limits=_limits(max_member_bytes=actual_size, max_total_uncompressed_bytes=actual_size),
            ) as data_root:
                assert (data_root / "data/file.json").stat().st_size == actual_size
        else:
            with pytest.raises(SystemsIngestError, match="ratio"):
                with extracted_systems_archive(
                    archive_bytes,
                    limits=_limits(max_member_bytes=actual_size, max_total_uncompressed_bytes=actual_size),
                ):
                    pass
        assert list((tmp_path / "temp").iterdir()) == []


def test_actual_stream_rejects_zero_compressed_metadata_that_emits_bytes(monkeypatch, tmp_path):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("data/file.json", b"")
    archive_bytes = output.getvalue()
    original_open = zipfile.ZipFile.open

    def lying_open(self, member, *args, **kwargs):
        if isinstance(member, zipfile.ZipInfo) and not member.is_dir():
            return BytesIO(b"x")
        return original_open(self, member, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", lying_open)
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(tmp_path / "temp"))
    with pytest.raises(SystemsIngestError, match="ratio"):
        with extracted_systems_archive(archive_bytes, limits=_limits()):
            pass
    assert list((tmp_path / "temp").iterdir()) == []


def test_bounded_stream_spool_handles_short_reads_and_declared_length_is_hint_only():
    with spool_bounded_stream(
        _ShortChunkStream(b"abc"),
        max_bytes=3,
        declared_length=1,
    ) as spool:
        assert spool.read() == b"abc"
    with pytest.raises(IngressLimitError, match="too large"):
        spool_bounded_stream(_ShortChunkStream(b"abcd"), max_bytes=3)
    with pytest.raises(IngressLimitError, match="too large"):
        spool_bounded_stream(BytesIO(b"abc"), max_bytes=3, declared_length=4)

    class OverreadStream:
        def read(self, size: int) -> bytes:
            return b"x" * (size + 1)

    with pytest.raises(IngressLimitError, match="too large"):
        spool_bounded_stream(OverreadStream(), max_bytes=3)


def test_streaming_base64_prebound_rejects_before_decoder(monkeypatch):
    decoder_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal decoder_called
        decoder_called = True
        raise AssertionError("decoder must not be called")

    monkeypatch.setattr("player_wiki.input_limits.base64.b64decode", fail_if_called)
    with pytest.raises(IngressLimitError, match="invalid or too large"):
        decode_bounded_base64_to_spool("AAAAAA==", max_decoded_bytes=3)
    assert decoder_called is False


def test_streaming_base64_exact_size_rejects_same_quartet_plus_one_before_decoder(
    monkeypatch,
):
    decoder_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal decoder_called
        decoder_called = True
        raise AssertionError("oversized base64 must be rejected before decoding")

    monkeypatch.setattr("player_wiki.input_limits.base64.b64decode", fail_if_called)
    for value, max_decoded_bytes in (("YWI=", 1), ("YWJj", 2)):
        with pytest.raises(IngressLimitError, match="invalid or too large"):
            decode_bounded_base64_to_spool(value, max_decoded_bytes=max_decoded_bytes)
    assert decoder_called is False


def test_streaming_base64_rejects_noncanonical_pad_bits_before_spool(monkeypatch):
    monkeypatch.setattr(
        "player_wiki.input_limits.tempfile.SpooledTemporaryFile",
        lambda *args, **kwargs: pytest.fail("noncanonical input must fail before spool creation"),
    )
    for value in ("Zh==", "Zm9="):
        with pytest.raises(IngressLimitError, match="invalid or too large"):
            decode_bounded_base64_to_spool(value, max_decoded_bytes=8)


def test_streaming_base64_accepts_canonical_final_quartets():
    for value, expected in (("Zg==", b"f"), ("Zm8=", b"fo"), ("Zm9v", b"foo")):
        with decode_bounded_base64_to_spool(value, max_decoded_bytes=len(expected)) as spool:
            assert spool.read() == expected


@pytest.mark.parametrize("value", [None, 1, "Y Q==", "YQ=", "YQ===", "not-base64!", "\u00e9==="])
def test_streaming_base64_rejects_invalid_alphabet_whitespace_and_padding(value):
    with pytest.raises(IngressLimitError, match="invalid or too large"):
        decode_bounded_base64_to_spool(value, max_decoded_bytes=8)


def test_streaming_base64_exact_decoded_limit_passes_and_plus_one_fails():
    with decode_bounded_base64_to_spool("YWJj", max_decoded_bytes=3) as spool:
        assert spool.read() == b"abc"
    with pytest.raises(IngressLimitError, match="invalid or too large"):
        decode_bounded_base64_to_spool("YWJjZA==", max_decoded_bytes=3)


def test_malformed_utf8_central_directory_is_safely_translated_before_temp_output(
    tmp_path,
    monkeypatch,
):
    temp_root = tmp_path / "temp"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))
    with pytest.raises(SystemsIngestError) as failure:
        with extracted_systems_archive(_build_malformed_utf8_systems_import_archive()):
            pass
    message = str(failure.value)
    assert message == "Import archive must be a valid supported ZIP file."
    assert "ATTACKER-SENTINEL" not in message
    assert "codec" not in message
    assert "position" not in message
    assert not temp_root.exists()


def test_seek_tell_failures_are_fixed_safe_and_do_not_close_caller_stream():
    for failure_type in (AttributeError, OSError, ValueError):
        class FailingCallerStream:
            closed = False

            def tell(self):
                raise failure_type("PRIVATE-SENTINEL")

            def seek(self, *_args):
                raise AssertionError("seek must not follow a failed tell")

            def close(self):
                self.closed = True

        stream = FailingCallerStream()
        with pytest.raises(SystemsIngestError) as failure:
            with extracted_systems_archive(stream):
                pass
        assert str(failure.value) == "Import archive must be a seekable binary file."
        assert "PRIVATE-SENTINEL" not in str(failure.value)
        assert stream.closed is False


def test_each_seek_tell_stage_translates_value_errors_without_closing_caller():
    for failure_step in range(4):
        class StagedFailureStream:
            closed = False

            def __init__(self):
                self.step = 0

            def _advance(self):
                current = self.step
                self.step += 1
                if current == failure_step:
                    raise ValueError("PRIVATE-SENTINEL")

            def tell(self):
                self._advance()
                return 0

            def seek(self, *_args):
                self._advance()
                return 0

            def close(self):
                self.closed = True

        stream = StagedFailureStream()
        with pytest.raises(SystemsIngestError) as failure:
            with extracted_systems_archive(stream):
                pass
        assert str(failure.value) == "Import archive must be a seekable binary file."
        assert "PRIVATE-SENTINEL" not in str(failure.value)
        assert stream.closed is False


def test_closed_caller_stream_is_safely_rejected_without_ownership_change():
    stream = BytesIO(b"closed")
    stream.close()
    with pytest.raises(SystemsIngestError, match="seekable binary file"):
        with extracted_systems_archive(stream):
            pass
    assert stream.closed is True


def test_parser_failure_does_not_close_caller_owned_stream():
    stream = BytesIO(b"not-a-zip")
    with pytest.raises(SystemsIngestError, match="valid supported ZIP"):
        with extracted_systems_archive(stream):
            pass
    assert stream.closed is False


def test_internal_path_handle_closes_after_parser_failure(tmp_path):
    archive_path = tmp_path / "invalid.zip"
    archive_path.write_bytes(b"not-a-zip")
    with pytest.raises(SystemsIngestError, match="valid supported ZIP"):
        with extracted_systems_archive(archive_path):
            pass
    archive_path.unlink()
    assert not archive_path.exists()
