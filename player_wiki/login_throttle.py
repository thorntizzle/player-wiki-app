from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import hashlib
import ipaddress
import math
from threading import Lock
import time
from typing import Callable

from .auth_store import normalize_email

LOGIN_THROTTLE_WINDOW_SECONDS = 300.0
LOGIN_THROTTLE_PAIR_THRESHOLD = 5
LOGIN_THROTTLE_CLIENT_THRESHOLD = 25
LOGIN_THROTTLE_MAX_BUCKETS = 10_000
UNKNOWN_CLIENT_KEY = "unknown"


def canonical_client_key(remote_addr: object) -> str:
    if not isinstance(remote_addr, str):
        return UNKNOWN_CLIENT_KEY
    candidate = remote_addr.strip()
    if not candidate or "%" in candidate:
        return UNKNOWN_CLIENT_KEY
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return UNKNOWN_CLIENT_KEY
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return address.compressed.lower()


def account_digest(email: object) -> str:
    normalized = normalize_email(email if isinstance(email, str) else "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ThrottleDecision:
    blocked: bool
    retry_after: int | None = None
    reason: str | None = None


@dataclass(slots=True)
class LoginAttempt:
    pair_key: tuple[str, str]
    client_key: str
    decision: ThrottleDecision
    _active: bool = field(default=False, repr=False)


@dataclass(slots=True)
class _Bucket:
    timestamps: deque[float] = field(default_factory=deque)
    in_flight: int = 0


class LoginThrottle:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        window_seconds: float = LOGIN_THROTTLE_WINDOW_SECONDS,
        pair_threshold: int = LOGIN_THROTTLE_PAIR_THRESHOLD,
        client_threshold: int = LOGIN_THROTTLE_CLIENT_THRESHOLD,
        max_buckets: int = LOGIN_THROTTLE_MAX_BUCKETS,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if pair_threshold <= 0 or client_threshold <= 0:
            raise ValueError("thresholds must be positive")
        if max_buckets < 2:
            raise ValueError("max_buckets must be at least 2")
        self._clock = clock
        self._window_seconds = float(window_seconds)
        self._pair_threshold = int(pair_threshold)
        self._client_threshold = int(client_threshold)
        self._max_buckets = int(max_buckets)
        self._pair_buckets: dict[tuple[str, str], _Bucket] = {}
        self._client_buckets: dict[str, _Bucket] = {}
        self._lock = Lock()

    @property
    def bucket_count(self) -> int:
        with self._lock:
            return len(self._pair_buckets) + len(self._client_buckets)

    def precheck(self, *, account_key: str, client_key: str) -> LoginAttempt:
        pair_key = (client_key, account_key)
        with self._lock:
            now = self._clock()
            self._prune_all(now)
            pair_bucket = self._pair_buckets.get(pair_key)
            client_bucket = self._client_buckets.get(client_key)

            retry_after = self._blocked_retry_after(pair_bucket, client_bucket, now)
            if retry_after is not None:
                return LoginAttempt(
                    pair_key,
                    client_key,
                    ThrottleDecision(True, retry_after, "threshold"),
                )

            missing = int(pair_bucket is None) + int(client_bucket is None)
            current_count = len(self._pair_buckets) + len(self._client_buckets)
            if current_count + missing > self._max_buckets:
                return LoginAttempt(
                    pair_key,
                    client_key,
                    ThrottleDecision(True, self._capacity_retry_after(missing, now), "capacity"),
                )

            if pair_bucket is None:
                pair_bucket = _Bucket()
                self._pair_buckets[pair_key] = pair_bucket
            if client_bucket is None:
                client_bucket = _Bucket()
                self._client_buckets[client_key] = client_bucket
            pair_bucket.in_flight += 1
            client_bucket.in_flight += 1
            return LoginAttempt(pair_key, client_key, ThrottleDecision(False), _active=True)

    def record_failure(self, attempt: LoginAttempt) -> ThrottleDecision:
        if attempt.decision.blocked or not attempt._active:
            return attempt.decision
        with self._lock:
            now = self._clock()
            self._prune_all(now)
            pair_bucket = self._pair_buckets.get(attempt.pair_key)
            client_bucket = self._client_buckets.get(attempt.client_key)
            self._release_reservation(pair_bucket)
            self._release_reservation(client_bucket)
            attempt._active = False

            # A concurrently completed request may have reached a threshold
            # after this request's precheck. Such an already-blocked attempt
            # must not append timestamps or extend the window.
            retry_after = self._blocked_retry_after(pair_bucket, client_bucket, now)
            if retry_after is not None:
                self._remove_if_empty(self._pair_buckets, attempt.pair_key, pair_bucket)
                self._remove_if_empty(self._client_buckets, attempt.client_key, client_bucket)
                return ThrottleDecision(True, retry_after, "threshold")

            if pair_bucket is None or client_bucket is None:
                # Reservations keep these buckets present, so reaching this
                # branch means internal state was unexpectedly lost. Fail
                # closed without partially recreating capacity.
                return ThrottleDecision(True, max(1, math.ceil(self._window_seconds)), "capacity")

            if len(pair_bucket.timestamps) < self._pair_threshold:
                pair_bucket.timestamps.append(now)
            if len(client_bucket.timestamps) < self._client_threshold:
                client_bucket.timestamps.append(now)

            retry_after = self._blocked_retry_after(pair_bucket, client_bucket, now)
            if retry_after is not None:
                return ThrottleDecision(True, retry_after, "threshold")
            return ThrottleDecision(False)

    def cancel(self, attempt: LoginAttempt) -> None:
        """Release an attempt whose authentication path raised an error."""
        if attempt.decision.blocked or not attempt._active:
            return
        with self._lock:
            pair_bucket = self._pair_buckets.get(attempt.pair_key)
            client_bucket = self._client_buckets.get(attempt.client_key)
            self._release_reservation(pair_bucket)
            self._release_reservation(client_bucket)
            attempt._active = False
            self._remove_if_empty(self._pair_buckets, attempt.pair_key, pair_bucket)
            self._remove_if_empty(self._client_buckets, attempt.client_key, client_bucket)

    def record_success(self, attempt: LoginAttempt) -> None:
        if attempt.decision.blocked or not attempt._active:
            return
        with self._lock:
            now = self._clock()
            self._prune_all(now)
            pair_bucket = self._pair_buckets.get(attempt.pair_key)
            client_bucket = self._client_buckets.get(attempt.client_key)
            self._release_reservation(pair_bucket)
            self._release_reservation(client_bucket)
            attempt._active = False

            # A successful login forgives only this account/client pair. The
            # client aggregate remains so rotating accounts cannot reset it.
            if pair_bucket is not None:
                pair_bucket.timestamps.clear()
                if pair_bucket.in_flight == 0:
                    self._pair_buckets.pop(attempt.pair_key, None)
            if client_bucket is not None and client_bucket.in_flight == 0 and not client_bucket.timestamps:
                self._client_buckets.pop(attempt.client_key, None)

    def _prune_all(self, now: float) -> None:
        cutoff = now - self._window_seconds
        for key, bucket in tuple(self._pair_buckets.items()):
            self._prune_bucket(bucket, cutoff)
            if bucket.in_flight == 0 and not bucket.timestamps:
                self._pair_buckets.pop(key, None)
        for key, bucket in tuple(self._client_buckets.items()):
            self._prune_bucket(bucket, cutoff)
            if bucket.in_flight == 0 and not bucket.timestamps:
                self._client_buckets.pop(key, None)

    @staticmethod
    def _prune_bucket(bucket: _Bucket, cutoff: float) -> None:
        while bucket.timestamps and bucket.timestamps[0] <= cutoff:
            bucket.timestamps.popleft()

    @staticmethod
    def _release_reservation(bucket: _Bucket | None) -> None:
        if bucket is not None and bucket.in_flight > 0:
            bucket.in_flight -= 1

    @staticmethod
    def _remove_if_empty(mapping: dict, key: object, bucket: _Bucket | None) -> None:
        if bucket is not None and bucket.in_flight == 0 and not bucket.timestamps:
            mapping.pop(key, None)

    def _blocked_retry_after(
        self,
        pair_bucket: _Bucket | None,
        client_bucket: _Bucket | None,
        now: float,
    ) -> int | None:
        waits: list[float] = []
        if pair_bucket is not None and len(pair_bucket.timestamps) >= self._pair_threshold:
            waits.append(pair_bucket.timestamps[0] + self._window_seconds - now)
        if client_bucket is not None and len(client_bucket.timestamps) >= self._client_threshold:
            waits.append(client_bucket.timestamps[0] + self._window_seconds - now)
        if not waits:
            return None
        return max(1, math.ceil(max(waits)))

    def _capacity_retry_after(self, missing: int, now: float) -> int:
        available = self._max_buckets - len(self._pair_buckets) - len(self._client_buckets)
        needed_expirations = missing - max(0, available)
        expirations: list[float] = []
        for bucket in (*self._pair_buckets.values(), *self._client_buckets.values()):
            if bucket.in_flight == 0 and bucket.timestamps:
                expirations.append(bucket.timestamps[-1] + self._window_seconds - now)
        expirations.sort()
        if needed_expirations > 0 and len(expirations) >= needed_expirations:
            return max(1, math.ceil(expirations[needed_expirations - 1]))
        return max(1, math.ceil(self._window_seconds))
