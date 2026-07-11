from __future__ import annotations

import tempfile
from typing import Any, BinaryIO, MutableMapping

from werkzeug.exceptions import RequestEntityTooLarge


MAX_CONTENT_LENGTH = 96 * 1024**2
MAX_FORM_MEMORY_SIZE = 1 * 1024**2
MAX_FORM_PARTS = 200

_SPOOL_MEMORY_LIMIT = 1 * 1024**2
_STREAM_READ_CHUNK_SIZE = 64 * 1024


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
