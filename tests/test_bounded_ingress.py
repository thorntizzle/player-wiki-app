from __future__ import annotations

import base64
from io import BytesIO

import pytest

from player_wiki.input_limits import (
    IngressLimitError,
    decode_bounded_base64,
    read_bounded_file,
    read_bounded_stream,
    validate_json_markdown_fields,
    validate_markdown_value,
)
from player_wiki.image_publish import prepare_published_article_image


class ShortChunkStream:
    def __init__(self, payload: bytes, *, chunk_size: int = 1) -> None:
        self.payload = payload
        self.chunk_size = chunk_size
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.payload):
            return b""
        bounded_size = self.chunk_size if size < 0 else min(size, self.chunk_size)
        chunk = self.payload[self.offset : self.offset + bounded_size]
        self.offset += len(chunk)
        return chunk


def build_tiny_image_bytes(image_format: str) -> bytes:
    from PIL import Image

    output = BytesIO()
    Image.new("RGB", (1, 1), color=(20, 40, 60)).save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize("declared_length", [None, 0, 1, "invalid"])
def test_bounded_stream_does_not_trust_missing_or_false_length(declared_length):
    assert read_bounded_stream(
        ShortChunkStream(b"abc", chunk_size=1),
        max_bytes=3,
        declared_length=declared_length,
    ) == b"abc"

    with pytest.raises(IngressLimitError, match="under 8 MB"):
        read_bounded_stream(
            ShortChunkStream(b"abcd", chunk_size=1),
            max_bytes=3,
            declared_length=declared_length,
        )


def test_bounded_stream_uses_declared_length_only_as_an_early_rejection_hint():
    stream = ShortChunkStream(b"abc")
    with pytest.raises(IngressLimitError, match="under 8 MB"):
        read_bounded_stream(stream, max_bytes=3, declared_length=4)
    assert stream.offset == 0


def test_internal_file_copy_is_bounded_without_deleting_legacy_source(tmp_path):
    source = tmp_path / "legacy-image.webp"
    source.write_bytes(b"abcd")
    assert read_bounded_file(source, max_bytes=4) == b"abcd"
    with pytest.raises(IngressLimitError, match="Source files must stay under 8 MB"):
        read_bounded_file(source, max_bytes=3)
    assert source.read_bytes() == b"abcd"


def test_bounded_base64_checks_encoded_length_before_decoder(monkeypatch):
    decoder_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal decoder_called
        decoder_called = True
        raise AssertionError("decoder must not be called")

    monkeypatch.setattr("player_wiki.input_limits.base64.b64decode", fail_if_called)
    with pytest.raises(IngressLimitError, match="invalid or too large"):
        decode_bounded_base64("AAAAAA==", max_decoded_bytes=3)
    assert decoder_called is False


@pytest.mark.parametrize("value", [None, 7, "Y Q==", "YQ=", "YQ===", "not-base64!"])
def test_bounded_base64_rejects_nonstring_whitespace_alphabet_and_padding(value):
    with pytest.raises(IngressLimitError, match="invalid or too large"):
        decode_bounded_base64(value, max_decoded_bytes=8)


def test_bounded_base64_exact_decoded_limit_passes_and_plus_one_fails():
    assert decode_bounded_base64(base64.b64encode(b"abc").decode("ascii"), max_decoded_bytes=3) == b"abc"
    with pytest.raises(IngressLimitError, match="invalid or too large"):
        decode_bounded_base64(base64.b64encode(b"abcd").decode("ascii"), max_decoded_bytes=3)


@pytest.mark.parametrize(("filename", "image_format"), [("tiny.gif", "GIF"), ("tiny.webp", "WEBP")])
def test_valid_tiny_passthrough_images_preserve_bytes(filename, image_format):
    image_bytes = build_tiny_image_bytes(image_format)
    converted_filename, converted_bytes = prepare_published_article_image(filename, image_bytes)
    assert converted_filename == filename
    assert converted_bytes == image_bytes


@pytest.mark.parametrize(("filename", "image_format"), [("tiny.png", "PNG"), ("tiny.jpg", "JPEG")])
def test_valid_tiny_png_and_jpg_images_convert_to_webp(filename, image_format):
    converted_filename, converted_bytes = prepare_published_article_image(
        filename,
        build_tiny_image_bytes(image_format),
    )
    assert converted_filename == "tiny.webp"
    assert converted_bytes[:4] == b"RIFF"
    assert converted_bytes[8:12] == b"WEBP"


def test_markdown_limit_counts_utf8_bytes_not_characters():
    assert validate_markdown_value("éé", max_bytes=4) == "éé"
    with pytest.raises(IngressLimitError, match="under 1 MB"):
        validate_markdown_value("ééé", max_bytes=5)


def test_recursive_json_markdown_validation_covers_nested_keys_and_is_bounded():
    validate_json_markdown_fields(
        {"nested": [{"notes_markdown": "éé"}, {"markdown_text": "ok"}]},
        max_bytes=4,
        max_depth=4,
        max_items=10,
    )
    with pytest.raises(IngressLimitError, match="under 1 MB"):
        validate_json_markdown_fields(
            {"nested": {"body_markdown": "ééé"}},
            max_bytes=5,
        )
    with pytest.raises(IngressLimitError, match="nested too deeply"):
        validate_json_markdown_fields({"a": {"b": {"c": {}}}}, max_depth=2)
    with pytest.raises(IngressLimitError, match="too many items"):
        validate_json_markdown_fields({"items": [{"a": 1}, {"b": 2}]}, max_items=3)


def test_content_asset_api_rejects_prebounded_base64_without_writing(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
    caplog,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    monkeypatch.setattr("player_wiki.api.MAX_INGRESS_FILE_BYTES", 3)
    sentinel = "ATTACKER-SENTINEL-CONTENT"
    response = client.put(
        "/api/v1/campaigns/linden-pass/content/assets/notes/oversized.txt",
        json={
            "asset_file": {
                "filename": "oversized.txt",
                "data_base64": base64.b64encode((sentinel + "x").encode()).decode(),
            }
        },
    )
    assert response.status_code == 400
    assert sentinel not in response.get_data(as_text=True)
    assert sentinel not in caplog.text
    asset_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "assets" / "notes" / "oversized.txt"
    assert not asset_path.exists()


def test_content_page_api_rejects_unicode_markdown_over_byte_limit_before_file_write(
    client,
    app,
    users,
    sign_in,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    body = "é" * (512 * 1024 + 1)
    response = client.put(
        "/api/v1/campaigns/linden-pass/content/pages/notes/oversized-unicode",
        json={
            "metadata": {"title": "Oversized Unicode", "section": "Notes", "published": True},
            "body_markdown": body,
        },
    )
    assert response.status_code == 400
    assert "Markdown content must stay under 1 MB." in response.get_data(as_text=True)
    page_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "content" / "notes" / "oversized-unicode.md"
    assert not page_path.exists()


def test_session_article_api_rejects_image_before_article_mutation(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    monkeypatch.setattr("player_wiki.api.MAX_INGRESS_FILE_BYTES", 3)
    response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        json={
            "mode": "manual",
            "title": "Rejected image",
            "body_markdown": "This article must not be created.",
            "image": {
                "filename": "oversized.png",
                "media_type": "image/png",
                "data_base64": base64.b64encode(b"abcd").decode(),
            },
        },
    )
    assert response.status_code == 400
    with app.app_context():
        assert app.extensions["campaign_session_service"].list_articles("linden-pass") == []


def test_character_portrait_api_rejects_image_before_revision_or_file_mutation(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    detail = client.get("/api/v1/campaigns/linden-pass/characters/arden-march").get_json()["character"]
    starting_revision = detail["state_record"]["revision"]
    monkeypatch.setattr("player_wiki.api.MAX_INGRESS_FILE_BYTES", 3)
    response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        json={
            "expected_revision": starting_revision,
            "portrait_file": {
                "filename": "oversized.png",
                "media_type": "image/png",
                "data_base64": base64.b64encode(b"abcd").decode(),
            },
        },
    )
    assert response.status_code == 400
    refreshed = client.get("/api/v1/campaigns/linden-pass/characters/arden-march").get_json()["character"]
    assert refreshed["state_record"]["revision"] == starting_revision
    assert refreshed["portrait"] is None


def test_browser_statblock_upload_rejects_bounded_stream_before_db_mutation(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    monkeypatch.setattr("player_wiki.app.MAX_MARKDOWN_BYTES", 3)
    response = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(b"abcd"), "oversized.md")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert app.extensions["campaign_dm_content_service"].list_statblocks("linden-pass") == []


@pytest.mark.parametrize(
    ("limit_name", "form_data", "expected_message"),
    (
        (
            "MAX_MARKDOWN_BYTES",
            {
                "article_mode": "upload",
                "markdown_file": (BytesIO(b"abcd"), "oversized.md"),
            },
            "Session article markdown files must stay under 1 MB.",
        ),
        (
            "MAX_INGRESS_FILE_BYTES",
            {
                "title": "Oversized image",
                "body_markdown": "The image must be rejected before article creation.",
                "image_file": (BytesIO(b"abcd"), "oversized.png"),
            },
            "Session article images must stay under 8 MB.",
        ),
    ),
)
def test_browser_session_article_authoring_rejects_bounded_uploads_before_db_mutation(
    client,
    app,
    users,
    sign_in,
    monkeypatch,
    limit_name,
    form_data,
    expected_message,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    monkeypatch.setattr(f"player_wiki.app.{limit_name}", 3)
    with pytest.raises(IngressLimitError, match=expected_message):
        client.post(
            "/campaigns/linden-pass/session/articles",
            data=form_data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )

    with app.app_context():
        service = app.extensions["campaign_session_service"]
        assert service.list_articles("linden-pass") == []
        assert service.get_live_revision("linden-pass") == 0
