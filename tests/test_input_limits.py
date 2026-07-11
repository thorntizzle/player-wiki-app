from __future__ import annotations

from io import BytesIO
import json
import logging

from flask import Flask, jsonify, request
import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.test import EnvironBuilder

from player_wiki import input_limits
from player_wiki.config import Config
from player_wiki.input_limits import (
    MAX_CONTENT_LENGTH,
    MAX_FORM_MEMORY_SIZE,
    MAX_FORM_PARTS,
    buffer_terminated_request_body,
)


class ExplodingInput:
    def read(self, *args, **kwargs):
        raise AssertionError("the untrusted request body must not be read")

    def readinto(self, *args, **kwargs):
        raise AssertionError("the untrusted request body must not be read")


class ShortReadInput(BytesIO):
    def __init__(self, data: bytes, *, max_chunk_size: int):
        super().__init__(data)
        self.max_chunk_size = max_chunk_size

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = self.max_chunk_size
        return super().read(min(size, self.max_chunk_size))


class RaisingInput(BytesIO):
    def __init__(self, first_chunk: bytes):
        super().__init__(first_chunk)
        self._did_return_first_chunk = False

    def read(self, size: int = -1) -> bytes:
        if not self._did_return_first_chunk:
            self._did_return_first_chunk = True
            return super().read(size)
        raise OSError("request-stream-secret-read-error")


def _register_data_probe(app, path: str = "/request-envelope-probe") -> None:
    def probe():
        data = request.get_data()
        return jsonify({"body_length": len(data), "body": data.decode("ascii")})

    app.add_url_rule(path, f"request_envelope_probe_{path}", probe, methods=["POST"])


def _register_form_probe(app, path: str = "/request-envelope-form-probe") -> None:
    def probe():
        return jsonify(
            {
                "part_count": len(request.form),
                "field_length": len(request.form.get("field", "")),
            }
        )

    app.add_url_rule(path, f"request_envelope_form_probe_{path}", probe, methods=["POST"])


def _invoke_wsgi(
    app,
    path: str,
    *,
    stream,
    content_length: int | None,
    input_terminated: bool = False,
    content_type: str = "application/octet-stream",
) -> tuple[int, dict[str, str], bytes]:
    environ = EnvironBuilder(path=path, method="POST").get_environ()
    environ["wsgi.input"] = stream
    environ["CONTENT_TYPE"] = content_type
    environ.pop("CONTENT_LENGTH", None)
    if content_length is not None:
        environ["CONTENT_LENGTH"] = str(content_length)
    if input_terminated:
        environ["wsgi.input_terminated"] = True
        environ["HTTP_TRANSFER_ENCODING"] = "chunked"
    else:
        environ.pop("wsgi.input_terminated", None)
        environ.pop("HTTP_TRANSFER_ENCODING", None)

    captured: dict[str, object] = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

    response_iterable = app.wsgi_app(environ, start_response)
    try:
        body = b"".join(response_iterable)
    finally:
        close = getattr(response_iterable, "close", None)
        if close is not None:
            close()

    status_code = int(str(captured["status"]).split(" ", 1)[0])
    headers = {str(key): str(value) for key, value in captured["headers"]}
    return status_code, headers, body


def _multipart_body(field_value: bytes) -> tuple[bytes, str]:
    boundary = "request-envelope-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="field"\r\n'
        "\r\n"
    ).encode("ascii")
    body += field_value
    body += f"\r\n--{boundary}--\r\n".encode("ascii")
    return body, f"multipart/form-data; boundary={boundary}"


def test_approved_request_envelope_is_exact_and_environment_independent():
    assert MAX_CONTENT_LENGTH == 96 * 1024**2
    assert MAX_FORM_MEMORY_SIZE == 1 * 1024**2
    assert MAX_FORM_PARTS == 200

    for environment in ("development", "production"):
        class EnvironmentConfig(Config):
            APP_ENV = environment

        configured_app = Flask(f"input-limits-{environment}")
        configured_app.config.from_object(EnvironmentConfig)
        assert configured_app.config["MAX_CONTENT_LENGTH"] == MAX_CONTENT_LENGTH
        assert configured_app.config["MAX_FORM_MEMORY_SIZE"] == MAX_FORM_MEMORY_SIZE
        assert configured_app.config["MAX_FORM_PARTS"] == MAX_FORM_PARTS


def test_content_length_boundary_is_checked_before_body_read_and_route_dispatch(app):
    route_calls: list[str] = []

    def probe():
        route_calls.append("called")
        return "ok"

    app.add_url_rule(
        "/request-envelope-boundary",
        "request_envelope_boundary",
        probe,
        methods=["POST"],
    )

    exact_status, _, _ = _invoke_wsgi(
        app,
        "/request-envelope-boundary",
        stream=ExplodingInput(),
        content_length=MAX_CONTENT_LENGTH,
    )
    over_status, _, over_body = _invoke_wsgi(
        app,
        "/request-envelope-boundary",
        stream=ExplodingInput(),
        content_length=MAX_CONTENT_LENGTH + 1,
    )

    assert exact_status == 200
    assert over_status == 413
    assert route_calls == ["called"]
    assert b"untrusted request body" not in over_body


def test_terminated_stream_without_content_length_rejects_before_route(app):
    route_calls: list[str] = []

    def probe():
        route_calls.append("called")
        return "route side effect"

    app.add_url_rule(
        "/request-envelope-probe",
        "request_envelope_terminated_over_limit",
        probe,
        methods=["POST"],
    )
    app.config["MAX_CONTENT_LENGTH"] = 64
    request_stream = BytesIO(b"x" * 65)

    status_code, _, response_body = _invoke_wsgi(
        app,
        "/request-envelope-probe",
        stream=request_stream,
        content_length=None,
        input_terminated=True,
    )

    assert status_code == 413
    assert route_calls == []
    assert request_stream.tell() == 65
    assert b"route side effect" not in response_body


@pytest.mark.parametrize("payload", (b"short-body", b"x" * 64))
def test_terminated_stream_exact_or_under_limit_reaches_route_intact(app, payload):
    _register_data_probe(app)
    app.config["MAX_CONTENT_LENGTH"] = 64

    status_code, _, response_body = _invoke_wsgi(
        app,
        "/request-envelope-probe",
        stream=ShortReadInput(payload, max_chunk_size=3),
        content_length=None,
        input_terminated=True,
    )

    assert status_code == 200
    assert json.loads(response_body) == {
        "body": payload.decode("ascii"),
        "body_length": len(payload),
    }


def test_valid_json_prefix_at_limit_with_hidden_suffix_is_rejected_before_route(
    app,
    caplog,
):
    route_payloads: list[object] = []

    def json_probe():
        route_payloads.append(request.get_json())
        return jsonify({"ok": True})

    app.add_url_rule(
        "/api/v1/request-envelope-json-probe",
        "request_envelope_json_prefix_probe",
        json_probe,
        methods=["POST"],
    )
    app.config.update(MAX_CONTENT_LENGTH=64, REQUEST_TRAIL_ENABLED=True)
    caplog.set_level(logging.INFO, logger=app.logger.name)
    json_shell_size = len(b'{"value":""}')
    valid_json_prefix = (
        b'{"value":"' + b"x" * (64 - json_shell_size) + b'"}'
    )
    assert len(valid_json_prefix) == 64

    status_code, _, response_body = _invoke_wsgi(
        app,
        "/api/v1/request-envelope-json-probe",
        stream=ShortReadInput(valid_json_prefix + b"hidden-suffix", max_chunk_size=5),
        content_length=None,
        input_terminated=True,
        content_type="application/json",
    )

    assert status_code == 413
    assert route_payloads == []
    assert b"hidden-suffix" not in response_body
    assert "hidden-suffix" not in caplog.text


def test_under_limit_chunked_json_and_urlencoded_forms_are_parsed_intact(app):
    def json_probe():
        return jsonify({"payload": request.get_json()})

    def form_probe():
        return jsonify({"fields": request.form.to_dict(flat=False)})

    app.add_url_rule(
        "/request-envelope-chunked-json",
        "request_envelope_chunked_json",
        json_probe,
        methods=["POST"],
    )
    app.add_url_rule(
        "/request-envelope-chunked-form",
        "request_envelope_chunked_form",
        form_probe,
        methods=["POST"],
    )
    app.config["MAX_CONTENT_LENGTH"] = 256
    json_body = b'{"message":"intact","values":[1,2,3]}'
    form_body = b"field=first&field=second&note=intact"

    json_status, _, json_response = _invoke_wsgi(
        app,
        "/request-envelope-chunked-json",
        stream=ShortReadInput(json_body, max_chunk_size=2),
        content_length=None,
        input_terminated=True,
        content_type="application/json",
    )
    form_status, _, form_response = _invoke_wsgi(
        app,
        "/request-envelope-chunked-form",
        stream=ShortReadInput(form_body, max_chunk_size=3),
        content_length=None,
        input_terminated=True,
        content_type="application/x-www-form-urlencoded",
    )

    assert json_status == 200
    assert json.loads(json_response) == {
        "payload": {"message": "intact", "values": [1, 2, 3]}
    }
    assert form_status == 200
    assert json.loads(form_response) == {
        "fields": {"field": ["first", "second"], "note": ["intact"]}
    }


def test_unknown_length_spool_rolls_to_disk_and_reframes_the_request():
    raw_stream = ShortReadInput(b"rollover-body", max_chunk_size=2)
    environ = {
        "wsgi.input": raw_stream,
        "wsgi.input_terminated": True,
        "HTTP_TRANSFER_ENCODING": "chunked",
    }

    spool = buffer_terminated_request_body(
        environ,
        max_content_length=64,
        spool_memory_limit=4,
    )
    try:
        assert getattr(spool, "_rolled") is True
        assert spool.read() == b"rollover-body"
        assert environ["wsgi.input"] is spool
        assert environ["CONTENT_LENGTH"] == str(len(b"rollover-body"))
        assert "wsgi.input_terminated" not in environ
        assert "HTTP_TRANSFER_ENCODING" not in environ
    finally:
        spool.close()
    assert spool.closed


def test_unknown_length_spools_close_on_success_over_limit_and_read_error(
    app,
    monkeypatch,
):
    _register_data_probe(app, "/request-envelope-spool-success")

    def ignored_body_probe():
        return "should not run"

    app.add_url_rule(
        "/request-envelope-spool-over-limit",
        "request_envelope_spool_over_limit",
        ignored_body_probe,
        methods=["POST"],
    )
    app.add_url_rule(
        "/request-envelope-spool-read-error",
        "request_envelope_spool_read_error",
        ignored_body_probe,
        methods=["POST"],
    )
    app.config["MAX_CONTENT_LENGTH"] = 64
    created_spools = []
    real_spool_factory = input_limits.tempfile.SpooledTemporaryFile

    def tracking_spool_factory(*args, **kwargs):
        spool = real_spool_factory(*args, **kwargs)
        created_spools.append(spool)
        return spool

    monkeypatch.setattr(
        input_limits.tempfile,
        "SpooledTemporaryFile",
        tracking_spool_factory,
    )

    success_status, _, _ = _invoke_wsgi(
        app,
        "/request-envelope-spool-success",
        stream=BytesIO(b"success"),
        content_length=None,
        input_terminated=True,
    )
    assert success_status == 200
    assert len(created_spools) == 1
    assert created_spools[0].closed

    over_status, _, _ = _invoke_wsgi(
        app,
        "/request-envelope-spool-over-limit",
        stream=BytesIO(b"x" * 65),
        content_length=None,
        input_terminated=True,
    )
    assert over_status == 413
    assert len(created_spools) == 2
    assert created_spools[1].closed

    with pytest.raises(OSError, match="request-stream-secret-read-error"):
        _invoke_wsgi(
            app,
            "/request-envelope-spool-read-error",
            stream=RaisingInput(b"first"),
            content_length=None,
            input_terminated=True,
        )
    assert len(created_spools) == 3
    assert created_spools[2].closed


def test_unterminated_stream_without_content_length_uses_safe_empty_fallback(app):
    _register_data_probe(app)
    app.config["MAX_CONTENT_LENGTH"] = 64

    status_code, _, response_body = _invoke_wsgi(
        app,
        "/request-envelope-probe",
        stream=ExplodingInput(),
        content_length=None,
    )

    assert status_code == 200
    assert json.loads(response_body)["body_length"] == 0


def test_declared_shorter_content_length_does_not_read_past_declared_body(app):
    _register_data_probe(app)
    app.config["MAX_CONTENT_LENGTH"] = 64

    status_code, _, response_body = _invoke_wsgi(
        app,
        "/request-envelope-probe",
        stream=BytesIO(b"safe" + b"untrusted-tail" * 10),
        content_length=4,
    )

    assert status_code == 200
    assert json.loads(response_body) == {"body": "safe", "body_length": 4}
    assert b"untrusted-tail" not in response_body


def test_multipart_part_limit_allows_200_and_rejects_201(app, client):
    _register_form_probe(app)

    allowed = client.post(
        "/request-envelope-form-probe",
        data=MultiDict((f"field-{index}", "x") for index in range(200)),
        content_type="multipart/form-data",
    )
    rejected = client.post(
        "/request-envelope-form-probe",
        data=MultiDict((f"field-{index}", "x") for index in range(201)),
        content_type="multipart/form-data",
    )

    assert allowed.status_code == 200
    assert allowed.get_json()["part_count"] == 200
    assert rejected.status_code == 413


def test_multipart_text_field_limit_is_per_field_and_boundary_inclusive(app, client):
    _register_form_probe(app)
    fast_field_limit = 70 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = fast_field_limit

    exact_body, content_type = _multipart_body(b"x" * fast_field_limit)
    exact = client.post(
        "/request-envelope-form-probe",
        data=exact_body,
        content_type=content_type,
    )
    over_body, content_type = _multipart_body(b"x" * (fast_field_limit + 1))
    over = client.post(
        "/request-envelope-form-probe",
        data=over_body,
        content_type=content_type,
    )

    assert exact.status_code == 200
    assert exact.get_json()["field_length"] == fast_field_limit
    assert over.status_code == 413


def test_urlencoded_form_limit_applies_to_aggregate_encoded_body(app, client):
    _register_form_probe(app)
    fast_form_limit = 70 * 1024
    app.config.update(
        MAX_CONTENT_LENGTH=fast_form_limit * 2,
        MAX_FORM_MEMORY_SIZE=fast_form_limit,
    )
    prefix = b"field="
    exact_body = prefix + b"x" * (fast_form_limit - len(prefix))

    exact = client.post(
        "/request-envelope-form-probe",
        data=exact_body,
        content_type="application/x-www-form-urlencoded",
    )
    over = client.post(
        "/request-envelope-form-probe",
        data=exact_body + b"x",
        content_type="application/x-www-form-urlencoded",
    )

    assert len(exact_body) == fast_form_limit
    assert exact.status_code == 200
    assert exact.get_json()["field_length"] == fast_form_limit - len(prefix)
    assert over.status_code == 413


def test_api_413_is_stable_safe_json_while_browser_keeps_generic_html(
    app,
    caplog,
):
    _register_data_probe(app, "/api/v1/request-envelope-probe")
    _register_data_probe(app, "/request-envelope-browser-probe")
    app.config.update(MAX_CONTENT_LENGTH=64, REQUEST_TRAIL_ENABLED=True)
    caplog.set_level(logging.INFO, logger=app.logger.name)
    secret_sentinel = b"request-body-secret-sentinel"

    api_status, api_headers, api_body = _invoke_wsgi(
        app,
        "/api/v1/request-envelope-probe",
        stream=BytesIO(secret_sentinel),
        content_length=65,
    )
    browser_status, browser_headers, browser_body = _invoke_wsgi(
        app,
        "/request-envelope-browser-probe",
        stream=BytesIO(secret_sentinel),
        content_length=65,
    )

    assert api_status == 413
    assert api_headers["Content-Type"] == "application/json"
    assert json.loads(api_body) == {
        "ok": False,
        "error": {
            "code": "request_too_large",
            "message": "The request is too large.",
        },
    }
    assert browser_status == 413
    assert browser_headers["Content-Type"].startswith("text/html;")
    assert b"Request Entity Too Large" in browser_body
    assert secret_sentinel not in api_body
    assert secret_sentinel not in browser_body
    assert secret_sentinel.decode("ascii") not in caplog.text
    assert "request-body-secret" not in caplog.text


def test_small_auth_wiki_and_api_requests_keep_their_existing_behavior(
    client,
    users,
):
    sign_in_response = client.post(
        "/sign-in",
        data={
            "email": users["owner"]["email"],
            "password": users["owner"]["password"],
        },
        follow_redirects=False,
    )
    wiki_response = client.get("/campaigns/linden-pass/pages/notes/operations-brief")
    api_response = client.get("/api/v1/app")

    assert sign_in_response.status_code == 302
    assert wiki_response.status_code == 200
    assert api_response.status_code == 200
    assert api_response.get_json()["ok"] is True
