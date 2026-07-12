from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock, Thread, current_thread

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash as werkzeug_check_password_hash
from werkzeug.security import generate_password_hash

import player_wiki.auth as auth_module
from player_wiki.auth import AUTH_SESSION_KEY
from player_wiki.auth_store import AuthStore
from player_wiki.db import get_db
from player_wiki.login_throttle import (
    LoginThrottle,
    UNKNOWN_CLIENT_KEY,
    account_digest,
    canonical_client_key,
)


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self._value = value
        self._lock = Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._value

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    @value.setter
    def value(self, value: float) -> None:
        with self._lock:
            self._value = value


class CompletionInversionClock(FakeClock):
    """Expose clock-before-lock completion inversion without flaky sleeps."""

    def __init__(self) -> None:
        super().__init__()
        self.older_clock_entered = Event()
        self.newer_finished = Event()
        self.clock_advanced = Event()
        self.arm_older = Event()
        self.transition_lock_locked = lambda: False

    def __call__(self) -> float:
        if current_thread().name != "older-completion" or not self.arm_older.is_set():
            return super().__call__()

        captured = super().__call__()
        self.older_clock_entered.set()
        assert self.clock_advanced.wait(timeout=2)
        if self.transition_lock_locked():
            # With clock sampling under the throttle lock, serialize this
            # append at the advanced time. The newer completion follows.
            return super().__call__()
        # The old clock-before-lock implementation leaves the transition lock
        # free here, so force the newer completion to append first and then
        # return the captured stale value to expose the inversion.
        assert self.newer_finished.wait(timeout=2)
        return captured


def _fail(throttle: LoginThrottle, account: str, client: str):
    attempt = throttle.precheck(account_key=account, client_key=client)
    if attempt.decision.blocked:
        return attempt.decision
    return throttle.record_failure(attempt)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.0.2.1", "192.0.2.1"),
        (" 192.0.2.1 ", "192.0.2.1"),
        ("::ffff:192.0.2.1", "192.0.2.1"),
        ("2001:0DB8:0:0:0:0:0:1", "2001:db8::1"),
        (None, UNKNOWN_CLIENT_KEY),
        ("", UNKNOWN_CLIENT_KEY),
        ("not-an-ip", UNKNOWN_CLIENT_KEY),
        ("[2001:db8::1]:443", UNKNOWN_CLIENT_KEY),
        ("192.0.2.1:443", UNKNOWN_CLIENT_KEY),
        ("fe80::1%eth0", UNKNOWN_CLIENT_KEY),
    ],
)
def test_client_key_canonicalization(raw, expected):
    assert canonical_client_key(raw) == expected


def test_account_key_matches_store_normalization_and_has_fixed_shape():
    assert account_digest("  USER@Example.COM  ") == account_digest("user@example.com")
    assert account_digest("\u212a" * 100_000) == account_digest("k" * 100_000)
    assert len(account_digest("\U0001f409" * 100_000)) == 64
    assert account_digest("attacker@example.com") != "attacker@example.com"


def test_exact_threshold_boundary_retry_rounding_and_no_sliding():
    clock = FakeClock()
    throttle = LoginThrottle(clock=clock)

    for _ in range(4):
        assert not _fail(throttle, "account", "client").blocked
    fifth = _fail(throttle, "account", "client")
    assert fifth.blocked
    assert fifth.retry_after == 300

    clock.value = 100.25
    probe = throttle.precheck(account_key="account", client_key="client")
    assert probe.decision.blocked
    assert probe.decision.retry_after == 200

    clock.value = 299.01
    probe = throttle.precheck(account_key="account", client_key="client")
    assert probe.decision.blocked
    assert probe.decision.retry_after == 1

    clock.value = 300.0
    allowed = throttle.precheck(account_key="account", client_key="client")
    assert not allowed.decision.blocked
    throttle.cancel(allowed)


def test_client_aggregate_blocks_twenty_fifth_failure_across_accounts():
    throttle = LoginThrottle(clock=FakeClock())
    decisions = []
    for index in range(25):
        decisions.append(_fail(throttle, f"account-{index // 4}", "client"))

    assert all(not decision.blocked for decision in decisions[:24])
    assert decisions[24].blocked
    assert decisions[24].retry_after == 300


def test_success_clears_pair_only_and_client_aggregate_persists():
    throttle = LoginThrottle(clock=FakeClock())
    for _ in range(4):
        assert not _fail(throttle, "account-a", "client").blocked

    successful = throttle.precheck(account_key="account-a", client_key="client")
    throttle.record_success(successful)
    allowed_again = throttle.precheck(account_key="account-a", client_key="client")
    assert not allowed_again.decision.blocked
    throttle.cancel(allowed_again)

    # The four earlier client failures remain, so twenty-one more failures
    # reach the aggregate threshold even though the pair was forgiven.
    for index in range(20):
        assert not _fail(throttle, f"other-{index}", "client").blocked
    assert _fail(throttle, "last", "client").blocked


def test_capacity_allocation_is_atomic_and_fails_closed_without_live_eviction():
    clock = FakeClock()
    throttle = LoginThrottle(clock=clock, max_buckets=4)
    assert not _fail(throttle, "a", "client-a").blocked  # pair + client
    assert not _fail(throttle, "b", "client-a").blocked  # second pair
    assert throttle.bucket_count == 3

    # A new client/account requires two buckets but only one slot remains.
    denied = throttle.precheck(account_key="c", client_key="client-c")
    assert denied.decision.blocked
    assert denied.decision.reason == "capacity"
    assert denied.decision.retry_after == 300
    assert throttle.bucket_count == 3

    # Existing live buckets were not evicted, and their prior failures remain.
    for _ in range(3):
        assert not _fail(throttle, "a", "client-a").blocked
    assert _fail(throttle, "a", "client-a").blocked

    clock.value = 300.0
    admitted = throttle.precheck(account_key="c", client_key="client-c")
    assert not admitted.decision.blocked
    throttle.cancel(admitted)


def test_capacity_retry_reports_when_enough_buckets_expire():
    clock = FakeClock()
    throttle = LoginThrottle(clock=clock, max_buckets=3)
    assert not _fail(throttle, "a", "client-a").blocked
    clock.value = 10.2
    assert not _fail(throttle, "b", "client-a").blocked
    denied = throttle.precheck(account_key="c", client_key="client-c")
    assert denied.decision.blocked
    # Two new buckets are needed with no free slots. Pair-a expires at t=300,
    # while the second removable bucket expires at t=310.2.
    assert denied.decision.retry_after == 300


def test_same_pair_concurrency_keeps_timestamp_counts_bounded():
    throttle = LoginThrottle(clock=FakeClock())
    barrier = Barrier(20)

    def worker():
        attempt = throttle.precheck(account_key="account", client_key="client")
        barrier.wait()
        return throttle.record_failure(attempt)

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(executor.map(lambda _: worker(), range(20)))

    assert sum(decision.blocked for decision in decisions) == 16
    pair_bucket = throttle._pair_buckets[("client", "account")]
    client_bucket = throttle._client_buckets["client"]
    assert len(pair_bucket.timestamps) == 5
    assert len(client_bucket.timestamps) == 5
    assert pair_bucket.in_flight == client_bucket.in_flight == 0


def test_inverted_completions_sample_time_under_lock_and_preserve_expiry_order():
    clock = CompletionInversionClock()
    throttle = LoginThrottle(
        clock=clock,
        pair_threshold=3,
        client_threshold=10,
    )
    clock.transition_lock_locked = throttle._lock.locked
    assert not _fail(throttle, "account", "client").blocked
    older_attempt = throttle.precheck(account_key="account", client_key="client")
    newer_attempt = throttle.precheck(account_key="account", client_key="client")
    clock.arm_older.set()

    decisions = []

    def finish_older() -> None:
        decisions.append(throttle.record_failure(older_attempt))

    def finish_newer() -> None:
        try:
            decisions.append(throttle.record_failure(newer_attempt))
        finally:
            clock.newer_finished.set()

    older = Thread(target=finish_older, name="older-completion")
    older.start()
    assert clock.older_clock_entered.wait(timeout=1)
    clock.value = 10.0
    clock.clock_advanced.set()
    newer = Thread(target=finish_newer, name="newer-completion")
    newer.start()
    older.join(timeout=2)
    newer.join(timeout=2)
    assert not older.is_alive()
    assert not newer.is_alive()

    timestamps = list(throttle._pair_buckets[("client", "account")].timestamps)
    assert timestamps == [0.0, 10.0, 10.0]
    assert timestamps == sorted(timestamps)
    assert sum(decision.blocked for decision in decisions) == 1

    clock.value = 299.2
    blocked = throttle.precheck(account_key="account", client_key="client")
    assert blocked.decision.blocked
    assert blocked.decision.retry_after == 1

    clock.value = 300.0
    admitted = throttle.precheck(account_key="account", client_key="client")
    assert not admitted.decision.blocked
    assert list(throttle._pair_buckets[("client", "account")].timestamps) == [10.0, 10.0]
    throttle.cancel(admitted)


def test_distinct_pair_concurrency_caps_client_and_cleans_empty_reservations():
    throttle = LoginThrottle(clock=FakeClock())
    barrier = Barrier(30)

    def worker(index: int):
        attempt = throttle.precheck(account_key=f"account-{index}", client_key="client")
        barrier.wait()
        return throttle.record_failure(attempt)

    with ThreadPoolExecutor(max_workers=30) as executor:
        decisions = list(executor.map(worker, range(30)))

    assert sum(decision.blocked for decision in decisions) == 6
    assert len(throttle._client_buckets["client"].timestamps) == 25
    assert all(bucket.in_flight == 0 for bucket in throttle._pair_buckets.values())
    assert all(bucket.timestamps for bucket in throttle._pair_buckets.values())
    assert throttle.bucket_count <= 26


def test_concurrent_capacity_reservations_never_exceed_cap():
    throttle = LoginThrottle(clock=FakeClock(), max_buckets=10)
    barrier = Barrier(20)

    def worker(index: int):
        barrier.wait()
        return throttle.precheck(account_key=f"account-{index}", client_key=f"client-{index}")

    with ThreadPoolExecutor(max_workers=20) as executor:
        attempts = list(executor.map(worker, range(20)))

    assert throttle.bucket_count <= 10
    assert sum(not attempt.decision.blocked for attempt in attempts) == 5
    for attempt in attempts:
        throttle.cancel(attempt)
    assert throttle.bucket_count == 0


def test_dummy_hash_is_process_constant_and_uses_current_werkzeug_method(app):
    first = auth_module._DUMMY_PASSWORD_HASH
    second = auth_module._DUMMY_PASSWORD_HASH
    assert first is second
    assert first.startswith("scrypt:")
    assert werkzeug_check_password_hash(first, auth_module._DUMMY_PASSWORD)
    assert app.extensions["login_throttle"] is app.extensions["login_throttle"]


def test_sign_in_paths_perform_one_expensive_password_check(app, users, monkeypatch):
    with app.app_context():
        store = AuthStore()
        disabled = store.create_user(
            "disabled@example.com",
            "Disabled",
            status="disabled",
            password_hash=generate_password_hash("disabled-pass"),
        )
        invited = store.create_user(
            "invited@example.com",
            "Invited",
            status="invited",
            password_hash=generate_password_hash("invited-pass"),
        )
        no_hash = store.create_user("nohash@example.com", "No Hash", status="active")

    calls: list[tuple[str, str]] = []

    def spy(password_hash: str, password: str) -> bool:
        calls.append((password_hash, password))
        return werkzeug_check_password_hash(password_hash, password)

    monkeypatch.setattr(auth_module, "check_password_hash", spy)
    cases = [
        ({}, 400, auth_module._DUMMY_PASSWORD_HASH),
        ({"email": "missing@example.com", "password": "secret-a"}, 400, auth_module._DUMMY_PASSWORD_HASH),
        ({"email": users["party"]["email"], "password": "wrong"}, 400, None),
        ({"email": disabled.email, "password": "disabled-pass"}, 400, disabled.password_hash),
        ({"email": invited.email, "password": "invited-pass"}, 400, invited.password_hash),
        ({"email": no_hash.email, "password": "anything"}, 400, auth_module._DUMMY_PASSWORD_HASH),
        (
            {"email": users["party"]["email"], "password": users["party"]["password"]},
            302,
            None,
        ),
    ]
    for index, (data, expected_status, expected_hash) in enumerate(cases):
        before = len(calls)
        client = app.test_client()
        response = client.post("/sign-in", data=data, environ_base={"REMOTE_ADDR": f"192.0.2.{index + 1}"})
        assert response.status_code == expected_status
        assert len(calls) == before + 1
        if expected_hash is not None:
            assert calls[-1][0] == expected_hash


def test_malformed_stored_hash_runs_dummy_work_and_fails_generically(app, monkeypatch):
    with app.app_context():
        malformed = AuthStore().create_user(
            "malformed@example.com",
            "Malformed",
            status="active",
            password_hash="unsupported-method$salt$value",
        )

    calls: list[str] = []

    def spy(password_hash: str, password: str) -> bool:
        calls.append(password_hash)
        return werkzeug_check_password_hash(password_hash, password)

    monkeypatch.setattr(auth_module, "check_password_hash", spy)
    response = app.test_client().post(
        "/sign-in",
        data={"email": malformed.email, "password": "malicious-secret"},
    )
    assert response.status_code == 400
    assert calls == [malformed.password_hash, auth_module._DUMMY_PASSWORD_HASH]
    body = response.get_data(as_text=True)
    assert auth_module.SIGN_IN_FAILURE_MESSAGE in body
    assert "malicious-secret" not in body
    assert "unsupported-method" not in body


def test_shape_invalid_stored_hash_goes_directly_to_dummy_work(app, monkeypatch):
    with app.app_context():
        malformed = AuthStore().create_user(
            "shape-invalid@example.com",
            "Shape Invalid",
            status="active",
            password_hash="legacy-garbage-without-delimiters",
        )

    calls: list[str] = []

    def spy(password_hash: str, password: str) -> bool:
        calls.append(password_hash)
        return werkzeug_check_password_hash(password_hash, password)

    monkeypatch.setattr(auth_module, "check_password_hash", spy)
    response = app.test_client().post(
        "/sign-in",
        data={"email": malformed.email, "password": "malicious-secret"},
    )
    assert response.status_code == 400
    assert calls == [auth_module._DUMMY_PASSWORD_HASH]
    assert "malicious-secret" not in response.get_data(as_text=True)
    assert "legacy-garbage" not in response.get_data(as_text=True)


def test_fifth_failure_returns_neutral_429_without_session_cookie(app, users):
    app.extensions["login_throttle"] = LoginThrottle(clock=FakeClock())
    client = app.test_client()
    data = {"email": users["party"]["email"], "password": "wrong-secret"}
    for _ in range(4):
        response = client.post("/sign-in", data=data)
        assert response.status_code == 400
        assert auth_module.SIGN_IN_FAILURE_MESSAGE in response.get_data(as_text=True)

    response = client.post("/sign-in", data=data)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "300"
    body = response.get_data(as_text=True)
    assert auth_module.SIGN_IN_THROTTLED_MESSAGE in body
    assert auth_module.SIGN_IN_FAILURE_MESSAGE not in body
    assert "wrong-secret" not in body
    # Flash messages may update Flask's signed cookie, but no authenticated
    # browser-session token is created.
    with client.session_transaction() as browser_session:
        assert AUTH_SESSION_KEY not in browser_session

    correct = client.post(
        "/sign-in",
        data={"email": users["party"]["email"], "password": users["party"]["password"]},
    )
    assert correct.status_code == 429
    with client.session_transaction() as browser_session:
        assert AUTH_SESSION_KEY not in browser_session


def test_twenty_fifth_client_failure_returns_same_neutral_429(app):
    app.extensions["login_throttle"] = LoginThrottle(clock=FakeClock())
    with app.app_context():
        store = AuthStore()
        users = [
            store.create_user(
                f"rotate-{index}@example.com",
                f"Rotate {index}",
                status="active",
                password_hash=generate_password_hash("correct-pass"),
            )
            for index in range(7)
        ]

    client = app.test_client()
    responses = []
    for index in range(25):
        responses.append(
            client.post(
                "/sign-in",
                data={"email": users[index // 4].email, "password": "wrong"},
            )
        )
    assert all(response.status_code == 400 for response in responses[:24])
    assert responses[24].status_code == 429
    assert responses[24].headers["Retry-After"] == "300"
    assert auth_module.SIGN_IN_THROTTLED_MESSAGE in responses[24].get_data(as_text=True)


def test_success_clears_pair_after_session_and_reenable_still_works(app, users):
    client = app.test_client()
    for _ in range(4):
        assert client.post(
            "/sign-in",
            data={"email": users["party"]["email"], "password": "wrong"},
        ).status_code == 400

    success = client.post(
        "/sign-in",
        data={"email": users["party"]["email"], "password": users["party"]["password"]},
    )
    assert success.status_code == 302
    with client.session_transaction() as browser_session:
        assert AUTH_SESSION_KEY in browser_session

    client.post("/sign-out")
    with app.app_context():
        store = AuthStore()
        store.disable_user(users["party"]["id"])
        store.enable_user(users["party"]["id"])
    assert client.post(
        "/sign-in",
        data={"email": users["party"]["email"], "password": users["party"]["password"]},
    ).status_code == 302


def test_trust_proxy_off_ignores_rotating_forwarded_for(app, users):
    client = app.test_client()
    for index in range(5):
        response = client.post(
            "/sign-in",
            data={"email": users["party"]["email"], "password": "wrong"},
            headers={"X-Forwarded-For": f"198.51.100.{index + 1}"},
            environ_base={"REMOTE_ADDR": "192.0.2.44"},
        )
    assert response.status_code == 429


def test_trust_proxy_one_hop_uses_rightmost_forwarded_address(app, users):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    client = app.test_client()
    for index in range(5):
        response = client.post(
            "/sign-in",
            data={"email": users["party"]["email"], "password": "wrong"},
            headers={"X-Forwarded-For": f"198.51.100.{index + 1}, 203.0.113.9"},
            environ_base={"REMOTE_ADDR": "192.0.2.44"},
        )
    assert response.status_code == 429


def test_mapped_ipv4_and_ipv4_share_route_throttle_bucket(app, users):
    client = app.test_client()
    for remote_addr in ["::ffff:192.0.2.55"] * 4 + ["192.0.2.55"]:
        response = client.post(
            "/sign-in",
            data={"email": users["party"]["email"], "password": "wrong"},
            environ_base={"REMOTE_ADDR": remote_addr},
        )
    assert response.status_code == 429


def test_malicious_password_is_absent_from_response_and_logs(app, users, caplog):
    secret = "\u2603\x00" + "Z" * 100_000
    response = app.test_client().post(
        "/sign-in",
        data={"email": users["party"]["email"], "password": secret},
    )
    assert response.status_code == 400
    assert secret not in response.get_data(as_text=True)
    assert all(secret not in record.getMessage() for record in caplog.records)


def test_auth_store_error_releases_capacity_without_hiding_error(app, monkeypatch):
    throttle = app.extensions["login_throttle"]

    def fail_lookup(_email):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(app.extensions["auth_store"], "get_user_by_email", fail_lookup)
    with pytest.raises(RuntimeError, match="database unavailable"):
        app.test_client().post("/sign-in", data={"email": "user@example.com", "password": "secret"})
    assert throttle.bucket_count == 0
