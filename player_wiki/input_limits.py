from __future__ import annotations

import base64
import binascii
import math
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Mapping, MutableMapping

from werkzeug.exceptions import RequestEntityTooLarge


MAX_CONTENT_LENGTH = 96 * 1024**2
MAX_FORM_MEMORY_SIZE = 1 * 1024**2
MAX_FORM_PARTS = 200
MAX_INGRESS_FILE_BYTES = 8 * 1024**2
MAX_MARKDOWN_BYTES = 1 * 1024**2
MAX_JSON_MARKDOWN_DEPTH = 32
MAX_JSON_MARKDOWN_ITEMS = 10_000

_SPOOL_MEMORY_LIMIT = 1 * 1024**2
_STREAM_READ_CHUNK_SIZE = 64 * 1024


class IngressLimitError(ValueError):
    """Raised when endpoint input exceeds an approved bounded-ingress policy."""


def utf8_size(value: str) -> int:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return len(value.encode("utf-8"))


def validate_markdown_value(
    value: object,
    *,
    max_bytes: int = MAX_MARKDOWN_BYTES,
    message: str = "Markdown content must stay under 1 MB.",
) -> str:
    if not isinstance(value, str):
        raise IngressLimitError("Markdown content must be a string.")
    if utf8_size(value) > max_bytes:
        raise IngressLimitError(message)
    return value


def validate_json_markdown_fields(
    payload: object,
    *,
    max_bytes: int = MAX_MARKDOWN_BYTES,
    max_depth: int = MAX_JSON_MARKDOWN_DEPTH,
    max_items: int = MAX_JSON_MARKDOWN_ITEMS,
) -> None:
    """Bound traversal and validate every incoming Markdown-named JSON string."""
    if max_depth < 0 or max_items < 0:
        raise ValueError("JSON traversal limits must be zero or greater")

    pending: list[tuple[object, int]] = [(payload, 0)]
    visited_items = 0
    while pending:
        current, depth = pending.pop()
        if depth > max_depth:
            raise IngressLimitError("JSON content is nested too deeply.")

        if isinstance(current, Mapping):
            visited_items += len(current)
            if visited_items > max_items:
                raise IngressLimitError("JSON content contains too many items.")
            for key, value in current.items():
                if isinstance(key, str) and (
                    key == "markdown_text" or key.endswith("_markdown")
                ) and isinstance(value, str):
                    validate_markdown_value(value, max_bytes=max_bytes)
                if isinstance(value, (Mapping, list, tuple)):
                    pending.append((value, depth + 1))
        elif isinstance(current, (list, tuple)):
            visited_items += len(current)
            if visited_items > max_items:
                raise IngressLimitError("JSON content contains too many items.")
            pending.extend(
                (value, depth + 1)
                for value in current
                if isinstance(value, (Mapping, list, tuple))
            )


def read_bounded_stream(
    stream: BinaryIO,
    *,
    max_bytes: int,
    declared_length: object = None,
    message: str = "Uploaded files must stay under 8 MB.",
) -> bytes:
    """Read at most ``max_bytes + 1`` without trusting a declared length."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be zero or greater")
    try:
        normalized_declared_length = int(declared_length)
    except (TypeError, ValueError):
        normalized_declared_length = 0
    if normalized_declared_length > max_bytes:
        raise IngressLimitError(message)

    chunks: list[bytes] = []
    total_bytes = 0
    while total_bytes <= max_bytes:
        read_size = min(_STREAM_READ_CHUNK_SIZE, max_bytes + 1 - total_bytes)
        chunk = stream.read(read_size)
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("Uploaded file streams must return bytes")
        if not chunk:
            break
        chunk_bytes = bytes(chunk)
        chunks.append(chunk_bytes)
        total_bytes += len(chunk_bytes)
        if total_bytes > max_bytes:
            raise IngressLimitError(message)
    return b"".join(chunks)


def read_bounded_upload(
    upload: object,
    *,
    max_bytes: int = MAX_INGRESS_FILE_BYTES,
    message: str = "Uploaded files must stay under 8 MB.",
) -> bytes:
    stream = getattr(upload, "stream", upload)
    declared_length = getattr(upload, "content_length", None)
    return read_bounded_stream(
        stream,
        max_bytes=max_bytes,
        declared_length=declared_length,
        message=message,
    )


def read_bounded_file(
    path: Path,
    *,
    max_bytes: int = MAX_INGRESS_FILE_BYTES,
    message: str = "Source files must stay under 8 MB.",
) -> bytes:
    with path.open("rb") as stream:
        return read_bounded_stream(
            stream,
            max_bytes=max_bytes,
            declared_length=path.stat().st_size,
            message=message,
        )


def decode_bounded_base64(
    value: object,
    *,
    max_decoded_bytes: int,
    message: str = "Embedded file data is invalid or too large.",
) -> bytes:
    """Reject oversized/non-ASCII input before strict base64 decoding."""
    if max_decoded_bytes < 0:
        raise ValueError("max_decoded_bytes must be zero or greater")
    if not isinstance(value, str) or not value:
        raise IngressLimitError(message)
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise IngressLimitError(message) from exc
    max_encoded_bytes = 4 * math.ceil(max_decoded_bytes / 3)
    if len(encoded) > max_encoded_bytes:
        raise IngressLimitError(message)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise IngressLimitError(message) from exc
    if len(decoded) > max_decoded_bytes:
        raise IngressLimitError(message)
    return decoded


def buffer_terminated_request_body(
    environ: MutableMapping[str, Any],
    *,
    max_content_length: int,
    spool_memory_limit: int | None = None,
) -> BinaryIO:
    """Replace an unknown-length terminated WSGI input with a bounded spool."""
    if max_content_length < 0:
        raise ValueError("max_content_length must be zero or greater")

    raw_stream = environ["wsgi.input"]
    spool = tempfile.SpooledTemporaryFile(
        max_size=(
            _SPOOL_MEMORY_LIMIT
            if spool_memory_limit is None
            else spool_memory_limit
        ),
        mode="w+b",
    )
    total_bytes = 0
    try:
        while True:
            remaining_probe_bytes = max_content_length + 1 - total_bytes
            read_size = min(_STREAM_READ_CHUNK_SIZE, remaining_probe_bytes)
            chunk = raw_stream.read(read_size)
            if not isinstance(chunk, bytes):
                raise TypeError("WSGI input streams must return bytes")
            if not chunk:
                break
            if len(chunk) > remaining_probe_bytes:
                raise RequestEntityTooLarge()

            spool.write(chunk)
            total_bytes += len(chunk)
            if total_bytes > max_content_length:
                raise RequestEntityTooLarge()

        spool.seek(0)
    except BaseException:
        spool.close()
        raise

    environ["wsgi.input"] = spool
    environ["CONTENT_LENGTH"] = str(total_bytes)
    environ.pop("HTTP_TRANSFER_ENCODING", None)
    environ.pop("wsgi.input_terminated", None)
    return spool
