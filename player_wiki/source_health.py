from __future__ import annotations

import base64
from dataclasses import dataclass, field, replace
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.parse import parse_qsl, urlsplit
import zlib


SOURCE_HEALTH_CLASSIFICATIONS = (
    "ambiguous",
    "missing",
    "wrong-system",
    "unsupported-type",
    "disabled",
    "inaccessible",
    "review-blocked",
    "stale-version",
    "healthy",
)
SOURCE_HEALTH_SEVERITIES = ("healthy", "attention", "blocked")
SOURCE_HEALTH_ACTIONS = (
    "none",
    "inspect_consumer",
    "inspect_source",
    "manage_source_policy",
    "review_source",
    "contact_app_admin",
)
SOURCE_HEALTH_REPORT_STATES = (
    "findings",
    "healthy",
    "empty",
    "partial",
    "error",
    "report_stale",
)
SOURCE_HEALTH_FINDING_LIMIT = 50
SOURCE_HEALTH_TARGET_REFERENCE_LIMIT = 4_096
SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES = 65_536
SOURCE_HEALTH_CURSOR_MAX_BYTES = 12_000
SOURCE_HEALTH_BROWSER_CURSOR_MAX_BYTES = 3_840
SOURCE_HEALTH_BROWSER_STATE_MAX_BYTES = 6_000
SOURCE_HEALTH_BROWSER_REQUEST_TARGET_MAX_BYTES = 4_096
SOURCE_HEALTH_BROWSER_SUCCESS_MAX_BYTES = 131_072
SOURCE_HEALTH_BROWSER_ERROR_MAX_BYTES = 65_536
SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES = 8_388_608
SOURCE_HEALTH_BROWSER_ADAPTER_ROSTER = (
    "characters",
    "mechanics",
    "combat",
    "presets",
)
SOURCE_HEALTH_ERROR_MESSAGE = "Source Health could not complete. Refresh to retry."
SOURCE_HEALTH_STALE_MESSAGE = "This Source Health report is advisory because its source snapshot changed. Refresh to recheck."

SOURCE_HEALTH_CLASSIFICATION_LABELS = MappingProxyType(
    {
        "ambiguous": "Ambiguous target",
        "missing": "Missing target",
        "wrong-system": "Wrong system",
        "unsupported-type": "Unsupported type",
        "disabled": "Disabled source",
        "inaccessible": "Inaccessible target",
        "review-blocked": "Review blocked",
        "stale-version": "Stale version",
        "healthy": "Healthy",
    }
)
SOURCE_HEALTH_ACTION_LABELS = MappingProxyType(
    {
        "none": "No action available",
        "inspect_consumer": "Inspect consumer",
        "inspect_source": "Inspect source",
        "manage_source_policy": "Manage source policy",
        "review_source": "Review source",
        "contact_app_admin": "Contact an app admin",
    }
)
SOURCE_HEALTH_STATE_LABELS = MappingProxyType(
    {
        "findings": "Findings found",
        "healthy": "Campaign references are healthy",
        "empty": "No in-scope consumers",
        "partial": "Partial report",
        "error": "Source Health unavailable",
        "report_stale": "Report is stale",
    }
)

_CLASSIFICATION_ORDER = {
    classification: index
    for index, classification in enumerate(SOURCE_HEALTH_CLASSIFICATIONS)
}
_NUMERIC_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
_COMBAT_SEED_VERSION_RE = re.compile(r"^[0-9a-f]{64}$")
_COMBAT_SEED_VERSION_SCHEME = "combat-seed-v1-sha256"


def _text(value: object) -> str:
    return str(value or "").strip()


def _payload_text(value: object, *, limit: int = 512) -> str:
    return _text(value)[:limit]


@dataclass(frozen=True, slots=True)
class SourceHealthAccessContext:
    """Owner-authorized, effective-actor context supplied before inventory."""

    campaign_slug: str
    system_code: str
    library_slug: str
    can_view_private: bool = False
    source_policy_defaults: tuple[tuple[str, bool, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SourceHealthReference:
    """Durable owner-provided reference; title text is intentionally absent."""

    target_kind: str
    library_slug: str = ""
    entry_key: str = ""
    slug: str = ""
    rule_key: str = ""
    source_id: str = ""
    system_code: str = ""
    target_id: str = ""
    consumer_version: str = ""
    version_scheme: str = ""

    def has_exact_locator(self) -> bool:
        if self.target_kind == "systems":
            return bool(self.entry_key or self.slug or self.rule_key)
        return bool(self.target_id or self.entry_key or self.slug)


@dataclass(frozen=True, slots=True)
class SourceHealthConsumer:
    consumer_type: str
    consumer_key: str
    surface: str
    reference: SourceHealthReference
    accepted_target_types: tuple[str, ...] = ()
    destination: str = ""


@dataclass(frozen=True, slots=True)
class SourceHealthTarget:
    target_kind: str
    canonical_identity: str
    system_code: str = ""
    target_type: str = ""
    source_id: str = ""
    enabled: bool = True
    accessible: bool = True
    review_blocked: bool = False
    wrong_system: bool = False
    target_version: str = ""
    version_scheme: str = ""
    destination: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": _payload_text(self.target_kind, limit=48),
            "identity": _payload_text(self.canonical_identity, limit=192),
            "type": _payload_text(self.target_type, limit=48),
            "source_id": _payload_text(self.source_id, limit=48),
        }


@dataclass(frozen=True, slots=True)
class SourceHealthResolution:
    targets: tuple[SourceHealthTarget, ...] = ()
    ambiguous: bool = False
    policy_destination: str = ""
    contains_inaccessible: bool = False


@dataclass(frozen=True, slots=True)
class SourceHealthResolutionBatch:
    """Immutable exact-resolution payload with honest definition-read metrics."""

    resolutions: Mapping[SourceHealthReference, SourceHealthResolution] = field(
        default_factory=dict
    )
    definition_file_count: int = 0
    definition_bytes: int = 0
    import_file_count: int = 0
    import_bytes: int = 0
    character_definitions: Mapping[str, Mapping[str, object]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        resolutions = dict(self.resolutions)
        if any(
            not isinstance(reference, SourceHealthReference)
            or not isinstance(resolution, SourceHealthResolution)
            for reference, resolution in resolutions.items()
        ):
            raise ValueError("Invalid Source Health resolution batch.")
        if (
            type(self.definition_file_count) is not int
            or type(self.definition_bytes) is not int
            or type(self.import_file_count) is not int
            or type(self.import_bytes) is not int
        ):
            raise ValueError("Invalid Source Health resolution measurements.")
        definition_file_count = self.definition_file_count
        definition_bytes = self.definition_bytes
        import_file_count = self.import_file_count
        import_bytes = self.import_bytes
        raw_character_definitions = dict(self.character_definitions)
        if (
            len(raw_character_definitions) > 50
            or len(raw_character_definitions) > definition_file_count
            or any(
                not isinstance(character_slug, str)
                or not character_slug
                or not isinstance(payload, Mapping)
                for character_slug, payload in raw_character_definitions.items()
            )
        ):
            raise ValueError("Invalid Source Health Character definition batch.")
        if (
            not 0 <= definition_file_count <= 50
            or not 0 <= import_file_count <= 50
            or not 0 <= definition_bytes <= SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
            or not 0 <= import_bytes <= SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
            or definition_bytes + import_bytes
            > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
        ):
            raise ValueError("Invalid Source Health resolution measurements.")
        object.__setattr__(self, "resolutions", MappingProxyType(resolutions))
        object.__setattr__(self, "definition_file_count", definition_file_count)
        object.__setattr__(self, "definition_bytes", definition_bytes)
        object.__setattr__(self, "import_file_count", import_file_count)
        object.__setattr__(self, "import_bytes", import_bytes)
        object.__setattr__(
            self,
            "character_definitions",
            MappingProxyType(
                {
                    character_slug: MappingProxyType(dict(payload))
                    for character_slug, payload in raw_character_definitions.items()
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class SourceHealthFinding:
    consumer: SourceHealthConsumer
    classification: str
    severity: str
    action: str
    target: SourceHealthTarget | None = None
    destination: str = ""

    def __post_init__(self) -> None:
        if self.classification not in SOURCE_HEALTH_CLASSIFICATIONS:
            raise ValueError("Unknown Source Health classification.")
        if self.severity not in SOURCE_HEALTH_SEVERITIES:
            raise ValueError("Unknown Source Health severity.")
        if self.action not in SOURCE_HEALTH_ACTIONS:
            raise ValueError("Unknown Source Health action.")

    def to_payload(self) -> dict[str, object]:
        consumer_payload = {
            "type": _payload_text(self.consumer.consumer_type, limit=48),
            "key": _payload_text(self.consumer.consumer_key, limit=160),
            "surface": _payload_text(self.consumer.surface, limit=64),
        }
        return {
            "classification": self.classification,
            "severity": self.severity,
            "action": self.action,
            "destination": _payload_text(self.destination, limit=256),
            "consumer": consumer_payload,
            "target": self.target.to_payload() if self.target is not None else None,
        }


@dataclass(frozen=True, slots=True)
class SourceHealthInventoryPage:
    consumers: tuple[SourceHealthConsumer, ...] = ()
    targets: tuple[SourceHealthTarget, ...] = ()
    continuation: str = ""
    definition_file_count: int = 0
    definition_bytes: int = 0
    character_definitions: Mapping[str, Mapping[str, object]] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
class SourceHealthMeasurements:
    definition_file_count: int = 0
    definition_bytes: int = 0

    def to_payload(self) -> dict[str, int]:
        return {
            "definition_file_count": max(0, int(self.definition_file_count)),
            "definition_bytes": max(0, int(self.definition_bytes)),
        }


@dataclass(frozen=True, slots=True)
class SourceHealthReport:
    campaign_slug: str
    state: str
    findings: tuple[SourceHealthFinding, ...] = ()
    complete: bool = True
    continuations: tuple[str, ...] = ()
    message: str = ""
    measurements: SourceHealthMeasurements = field(default_factory=SourceHealthMeasurements)

    def __post_init__(self) -> None:
        if self.state not in SOURCE_HEALTH_REPORT_STATES:
            raise ValueError("Unknown Source Health report state.")
        if len(self.findings) > SOURCE_HEALTH_FINDING_LIMIT:
            raise ValueError("Source Health reports are capped at 50 findings.")

    def to_payload(self) -> dict[str, object]:
        return {
            "campaign_slug": _payload_text(self.campaign_slug, limit=128),
            "state": self.state,
            "complete": bool(self.complete),
            "continuations": [
                _payload_text(item, limit=SOURCE_HEALTH_CURSOR_MAX_BYTES)
                for item in self.continuations
                if _payload_text(item, limit=SOURCE_HEALTH_CURSOR_MAX_BYTES)
            ],
            "message": _payload_text(self.message),
            "findings": [finding.to_payload() for finding in self.findings],
            "measurements": self.measurements.to_payload(),
            "payload_policy": {
                "cache_control": "private, no-store",
                "contains_private_data": True,
            },
        }


class SourceHealthDenied(PermissionError):
    """Non-disclosing denial. A caller must use its existing auth response."""


class SourceHealthCursorError(ValueError):
    """Sanitized cursor validation failure."""


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SourceHealthCursorError("Duplicate cursor field.")
        result[key] = value
    return result


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _urlsafe_b64decode(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        return base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeEncodeError) as exc:
        raise SourceHealthCursorError("Invalid cursor encoding.") from exc


class SourceHealthCursorCodec:
    """Deterministic HMAC-authenticated codec injected into the read-only kernel."""

    _PREFIX = "sh1"

    def __init__(self, signing_key: bytes | str) -> None:
        key = signing_key.encode("utf-8") if isinstance(signing_key, str) else bytes(signing_key)
        if len(key) < 16:
            raise ValueError("Source Health cursor signing keys must contain at least 16 bytes.")
        self._signing_key = key

    def encode(self, state: Mapping[str, object]) -> str:
        body = json.dumps(
            dict(state),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(body) > SOURCE_HEALTH_CURSOR_MAX_BYTES // 2:
            raise SourceHealthCursorError("Cursor state exceeds its bounded size.")
        signature = hmac.new(
            self._signing_key,
            self._PREFIX.encode("ascii") + b"." + body,
            sha256,
        ).digest()
        token = f"{self._PREFIX}.{_urlsafe_b64encode(body)}.{_urlsafe_b64encode(signature)}"
        if len(token.encode("ascii")) > SOURCE_HEALTH_CURSOR_MAX_BYTES:
            raise SourceHealthCursorError("Cursor token exceeds its bounded size.")
        return token

    def decode(self, token: str) -> dict[str, object]:
        raw_token = _text(token)
        if not raw_token or len(raw_token.encode("utf-8")) > SOURCE_HEALTH_CURSOR_MAX_BYTES:
            raise SourceHealthCursorError("Invalid cursor token.")
        parts = raw_token.split(".")
        if len(parts) != 3 or parts[0] != self._PREFIX:
            raise SourceHealthCursorError("Unsupported cursor token.")
        body = _urlsafe_b64decode(parts[1])
        supplied_signature = _urlsafe_b64decode(parts[2])
        if _urlsafe_b64encode(body) != parts[1]:
            raise SourceHealthCursorError("Invalid cursor encoding.")
        if _urlsafe_b64encode(supplied_signature) != parts[2]:
            raise SourceHealthCursorError("Invalid cursor encoding.")
        expected_signature = hmac.new(
            self._signing_key,
            self._PREFIX.encode("ascii") + b"." + body,
            sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise SourceHealthCursorError("Invalid cursor authentication.")
        try:
            decoded = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_strict_json_object,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceHealthCursorError("Invalid cursor payload.") from exc
        if not isinstance(decoded, dict):
            raise SourceHealthCursorError("Invalid cursor payload.")
        return decoded


class SourceHealthBrowserCursorCodec:
    """Canonical compressed browser cursor kept distinct from the sh1 kernel codec."""

    _PREFIX = "sh2"

    def __init__(self, signing_key: bytes | str) -> None:
        key = signing_key.encode("utf-8") if isinstance(signing_key, str) else bytes(signing_key)
        if len(key) < 16:
            raise ValueError("Source Health browser cursor keys must contain at least 16 bytes.")
        self._signing_key = key

    def encode(self, state: Mapping[str, object]) -> str:
        body = json.dumps(
            dict(state),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(body) > SOURCE_HEALTH_BROWSER_STATE_MAX_BYTES:
            raise SourceHealthCursorError("Browser cursor state exceeds its bounded size.")
        compressed = zlib.compress(body, level=9)
        signature = hmac.new(
            self._signing_key,
            self._PREFIX.encode("ascii") + b"." + compressed,
            sha256,
        ).digest()
        token = (
            f"{self._PREFIX}.{_urlsafe_b64encode(compressed)}."
            f"{_urlsafe_b64encode(signature)}"
        )
        if len(token.encode("ascii")) > SOURCE_HEALTH_BROWSER_CURSOR_MAX_BYTES:
            raise SourceHealthCursorError("Browser cursor token exceeds its bounded size.")
        return token

    def decode(self, token: str) -> dict[str, object]:
        raw_token = _text(token)
        try:
            raw_size = len(raw_token.encode("ascii"))
        except UnicodeEncodeError as exc:
            raise SourceHealthCursorError("Invalid browser cursor token.") from exc
        if not raw_token or raw_size > SOURCE_HEALTH_BROWSER_CURSOR_MAX_BYTES:
            raise SourceHealthCursorError("Invalid browser cursor token.")
        parts = raw_token.split(".")
        if len(parts) != 3 or parts[0] != self._PREFIX:
            raise SourceHealthCursorError("Unsupported browser cursor token.")
        compressed = _urlsafe_b64decode(parts[1])
        supplied_signature = _urlsafe_b64decode(parts[2])
        if (
            _urlsafe_b64encode(compressed) != parts[1]
            or _urlsafe_b64encode(supplied_signature) != parts[2]
        ):
            raise SourceHealthCursorError("Invalid browser cursor encoding.")
        expected_signature = hmac.new(
            self._signing_key,
            self._PREFIX.encode("ascii") + b"." + compressed,
            sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise SourceHealthCursorError("Invalid browser cursor authentication.")
        try:
            decompressor = zlib.decompressobj()
            body = decompressor.decompress(
                compressed,
                SOURCE_HEALTH_BROWSER_STATE_MAX_BYTES + 1,
            )
        except zlib.error as exc:
            raise SourceHealthCursorError("Invalid browser cursor compression.") from exc
        if (
            len(body) > SOURCE_HEALTH_BROWSER_STATE_MAX_BYTES
            or not decompressor.eof
            or decompressor.unused_data
            or decompressor.unconsumed_tail
        ):
            raise SourceHealthCursorError("Invalid browser cursor compression.")
        if zlib.compress(body, level=9) != compressed:
            raise SourceHealthCursorError("Noncanonical browser cursor compression.")
        try:
            decoded = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_strict_json_object,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceHealthCursorError("Invalid browser cursor payload.") from exc
        if not isinstance(decoded, dict):
            raise SourceHealthCursorError("Invalid browser cursor payload.")
        canonical_body = json.dumps(
            decoded,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if canonical_body != body:
            raise SourceHealthCursorError("Noncanonical browser cursor payload.")
        return decoded

    def decode_for_campaign(
        self,
        token: str,
        *,
        campaign_slug: str,
        roster: tuple[str, ...] = SOURCE_HEALTH_BROWSER_ADAPTER_ROSTER,
    ) -> dict[str, object]:
        """Authenticate one exact browser state before any diagnostic inventory."""

        decoded = self.decode(token)
        state = _parse_composite_cursor_state(decoded)
        if state.campaign_slug != _text(campaign_slug):
            raise SourceHealthCursorError("Browser cursor campaign changed.")
        if state.roster != tuple(roster):
            raise SourceHealthCursorError("Browser cursor adapter roster changed.")
        return decoded


def source_health_action_destination(
    campaign_slug: str,
    action: str,
    destination: str,
) -> str:
    """Return only action-compatible, same-campaign browser destinations."""

    normalized_campaign = _text(campaign_slug)
    candidate = _text(destination)
    segment = r"[A-Za-z0-9][A-Za-z0-9._~-]*"
    if (
        re.fullmatch(segment, normalized_campaign) is None
        or not candidate
        or action in {"none", "contact_app_admin"}
        or "\\" in candidate
        or "%" in candidate
        or any(ord(character) < 32 or ord(character) == 127 for character in candidate)
    ):
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith("/"):
        return ""
    prefix = f"/campaigns/{normalized_campaign}"
    if not parsed.path.startswith(f"{prefix}/") and parsed.path != prefix:
        return ""
    routes: tuple[tuple[str, str], ...]
    if action == "inspect_consumer":
        routes = (
            (rf"{re.escape(prefix)}/characters/{segment}", ""),
            (rf"{re.escape(prefix)}/pages/{segment}(?:/{segment})*", ""),
            (rf"{re.escape(prefix)}/combat/dm", "combatant"),
        )
    elif action == "inspect_source":
        routes = (
            (rf"{re.escape(prefix)}/characters/{segment}", ""),
            (rf"{re.escape(prefix)}/systems/entries/{segment}", ""),
            (rf"{re.escape(prefix)}/dm-content", "statblocks"),
        )
    elif action == "review_source":
        routes = ((rf"{re.escape(prefix)}/systems/entries/{segment}", ""),)
    elif action == "manage_source_policy":
        routes = ((rf"{re.escape(prefix)}/dm-content", "lane"),)
    else:
        return ""
    for path_pattern, query_kind in routes:
        if re.fullmatch(path_pattern, parsed.path) is None:
            continue
        if not query_kind:
            return candidate if not parsed.query else ""
        try:
            query = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
            )
        except ValueError:
            return ""
        if query_kind == "combatant" and len(query) == 1:
            key, value = query[0]
            return candidate if key == "combatant" and value.isdigit() and int(value) > 0 else ""
        if query_kind == "lane" and query == [("lane", "systems")]:
            return candidate
        if query_kind == "statblocks" and query == [("lane", "statblocks")]:
            return candidate
        return ""
    return ""


def present_source_health_report(
    report: SourceHealthReport,
    *,
    campaign_slug: str,
) -> dict[str, object]:
    """Build the only browser-facing Source Health projection and safe href set."""

    if not isinstance(report, SourceHealthReport) or report.campaign_slug != campaign_slug:
        report = SourceHealthReport(
            campaign_slug=campaign_slug,
            state="error",
            complete=False,
            message=SOURCE_HEALTH_ERROR_MESSAGE,
        )

    suppress_findings = report.state == "error"
    suppress_actions = report.state in {"error", "report_stale"}
    presented_findings: list[dict[str, object]] = []
    if not suppress_findings:
        for finding in report.findings:
            target = finding.target
            inaccessible = finding.classification == "inaccessible"
            action = "none" if suppress_actions or inaccessible else finding.action
            destination = (
                source_health_action_destination(
                    campaign_slug,
                    action,
                    finding.destination,
                )
                if action != "none"
                else ""
            )
            target_payload = None
            if target is not None and not inaccessible:
                target_payload = {
                    "kind": _payload_text(target.target_kind, limit=48),
                    "identity": _payload_text(target.canonical_identity, limit=192),
                    "type": _payload_text(target.target_type, limit=48),
                    "source_id": _payload_text(target.source_id, limit=48),
                }
            presented_findings.append(
                {
                    "classification": finding.classification,
                    "classification_label": SOURCE_HEALTH_CLASSIFICATION_LABELS[
                        finding.classification
                    ],
                    "severity": finding.severity,
                    "consumer": {
                        "type": _payload_text(finding.consumer.consumer_type, limit=48),
                        "key": _payload_text(finding.consumer.consumer_key, limit=160),
                        "surface": _payload_text(finding.consumer.surface, limit=64),
                    },
                    "target": target_payload,
                    "action": action,
                    "action_label": SOURCE_HEALTH_ACTION_LABELS[action],
                    "destination": destination,
                }
            )

    next_continuation = ""
    if (
        report.state == "partial"
        and not suppress_actions
        and len(report.continuations) == 1
    ):
        next_continuation = _payload_text(
            report.continuations[0],
            limit=SOURCE_HEALTH_BROWSER_CURSOR_MAX_BYTES,
        )

    return {
        "state": report.state,
        "state_label": SOURCE_HEALTH_STATE_LABELS[report.state],
        "message": _payload_text(report.message),
        "complete": bool(report.complete),
        "findings": tuple(presented_findings),
        "next_continuation": next_continuation,
        "measurements": report.measurements.to_payload(),
    }


def _unique_targets(targets: tuple[SourceHealthTarget, ...]) -> tuple[SourceHealthTarget, ...]:
    by_identity: dict[tuple[str, str], SourceHealthTarget] = {}
    for target in targets:
        marker = (target.target_kind, target.canonical_identity)
        by_identity.setdefault(marker, target)
    return tuple(by_identity.values())


def _version_parts(value: str, scheme: str) -> tuple[int, ...] | None:
    normalized_scheme = _text(scheme).lower()
    normalized_value = _text(value)
    if normalized_scheme == "integer":
        return (int(normalized_value),) if normalized_value.isdigit() else None
    if normalized_scheme in {"numeric", "semver"} and _NUMERIC_VERSION_RE.fullmatch(normalized_value):
        return tuple(int(part) for part in normalized_value.split("."))
    return None


def _is_stale(reference: SourceHealthReference, target: SourceHealthTarget) -> bool:
    if reference.version_scheme == _COMBAT_SEED_VERSION_SCHEME:
        if (
            _COMBAT_SEED_VERSION_RE.fullmatch(reference.consumer_version) is None
            or target.version_scheme != _COMBAT_SEED_VERSION_SCHEME
            or _COMBAT_SEED_VERSION_RE.fullmatch(target.target_version) is None
        ):
            raise ValueError("Invalid combat-seed Source Health fingerprint.")
        return target.target_version != reference.consumer_version
    if not reference.consumer_version or not target.target_version:
        return False
    if not reference.version_scheme or reference.version_scheme != target.version_scheme:
        return False
    consumer_parts = _version_parts(reference.consumer_version, reference.version_scheme)
    target_parts = _version_parts(target.target_version, target.version_scheme)
    return bool(consumer_parts is not None and target_parts is not None and target_parts > consumer_parts)


def classify_source_health(
    consumer: SourceHealthConsumer,
    resolution: SourceHealthResolution,
) -> SourceHealthFinding:
    raw_targets = tuple(resolution.targets or ())
    has_inaccessible_target = bool(
        resolution.contains_inaccessible
        or any(not candidate.accessible for candidate in raw_targets)
    )
    targets = _unique_targets(raw_targets)
    target = targets[0] if len(targets) == 1 else None

    if resolution.ambiguous or len(targets) > 1:
        classification = "ambiguous"
    elif target is None:
        classification = "missing"
    elif target.wrong_system or (
        consumer.reference.system_code
        and target.system_code
        and consumer.reference.system_code != target.system_code
    ) or (
        consumer.reference.library_slug
        and target.target_kind == "systems"
        and not target.canonical_identity.startswith(f"{consumer.reference.library_slug}:")
    ):
        classification = "wrong-system"
    elif consumer.accepted_target_types and target.target_type not in consumer.accepted_target_types:
        classification = "unsupported-type"
    elif not target.enabled:
        classification = "disabled"
    elif has_inaccessible_target:
        classification = "inaccessible"
    elif target.review_blocked:
        classification = "review-blocked"
    elif _is_stale(consumer.reference, target):
        classification = "stale-version"
    else:
        classification = "healthy"

    severity = (
        "healthy"
        if classification == "healthy"
        else "attention"
        if classification == "stale-version"
        else "blocked"
    )
    action = "none"
    destination = ""
    if classification in {"ambiguous", "missing", "wrong-system", "unsupported-type"}:
        if consumer.destination:
            action = "inspect_consumer"
            destination = consumer.destination
    elif classification == "disabled" and resolution.policy_destination:
        action = "manage_source_policy"
        destination = resolution.policy_destination
    elif classification == "review-blocked" and target is not None and target.destination:
        action = "review_source"
        destination = target.destination
    elif classification == "stale-version" and target is not None and target.destination:
        action = "inspect_source"
        destination = target.destination

    # Any inaccessible participant suppresses every navigation and target hint,
    # even when an earlier classification keeps precedence.
    disclosed_target = (
        target
        if target is not None and target.accessible and not has_inaccessible_target
        else None
    )
    if has_inaccessible_target:
        action = "none"
        destination = ""
    return SourceHealthFinding(
        consumer=consumer,
        classification=classification,
        severity=severity,
        action=action,
        target=disclosed_target,
        destination=destination,
    )


InventoryAdapter = Callable[
    [SourceHealthAccessContext, str],
    SourceHealthInventoryPage,
]
ResolutionAdapter = Callable[
    [SourceHealthAccessContext, tuple[SourceHealthReference, ...]],
    Mapping[SourceHealthReference, SourceHealthResolution],
]
FingerprintResolutionAdapter = Callable[
    [
        SourceHealthAccessContext,
        tuple[SourceHealthReference, ...],
        Mapping[SourceHealthReference, SourceHealthResolution],
    ],
    Mapping[SourceHealthReference, SourceHealthResolution],
]
CharacterResolutionAdapter = Callable[
    [SourceHealthAccessContext, tuple[SourceHealthReference, ...]],
    SourceHealthResolutionBatch,
]
CharacterFingerprintAdapter = Callable[
    [
        SourceHealthAccessContext,
        tuple[SourceHealthReference, ...],
        Mapping[SourceHealthReference, SourceHealthResolution],
        Mapping[str, Mapping[str, object]],
        int,
    ],
    SourceHealthResolutionBatch,
]
AuthorizationAdapter = Callable[[str], SourceHealthAccessContext | None]

_ADAPTER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CURSOR_VERSION = 1


@dataclass(frozen=True, slots=True)
class _CursorAdapterState:
    adapter_id: str
    cursor: str = ""
    exhausted: bool = False
    held: bool = False
    completed: tuple[str, ...] = ()
    page_digest: str = ""
    page_count: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "completed": list(self.completed),
            "cursor": self.cursor,
            "exhausted": self.exhausted,
            "held": self.held,
            "id": self.adapter_id,
            "page_count": self.page_count,
            "page_digest": self.page_digest,
        }


@dataclass(frozen=True, slots=True)
class _CursorWindowState:
    digest: str
    count: int
    offset: int

    def to_payload(self) -> dict[str, object]:
        return {
            "count": self.count,
            "digest": self.digest,
            "offset": self.offset,
        }


@dataclass(frozen=True, slots=True)
class _CompositeCursorState:
    campaign_slug: str
    roster: tuple[str, ...]
    adapters: tuple[_CursorAdapterState, ...]
    window: _CursorWindowState | None = None
    saw_any_consumer: bool = False
    saw_nonhealthy: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "adapters": [adapter.to_payload() for adapter in self.adapters],
            "campaign": self.campaign_slug,
            "outcome": {
                "saw_any_consumer": self.saw_any_consumer,
                "saw_nonhealthy": self.saw_nonhealthy,
            },
            "roster": list(self.roster),
            "version": _CURSOR_VERSION,
            "window": self.window.to_payload() if self.window is not None else None,
        }


def _require_exact_keys(value: object, expected: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise SourceHealthCursorError("Invalid cursor schema.")
    return value


def _require_bool(value: object) -> bool:
    if type(value) is not bool:
        raise SourceHealthCursorError("Invalid cursor boolean.")
    return value


def _require_int(value: object) -> int:
    if type(value) is not int:
        raise SourceHealthCursorError("Invalid cursor integer.")
    return value


def _parse_composite_cursor_state(payload: object) -> _CompositeCursorState:
    root = _require_exact_keys(
        payload,
        {"adapters", "campaign", "outcome", "roster", "version", "window"},
    )
    if _require_int(root["version"]) != _CURSOR_VERSION:
        raise SourceHealthCursorError("Unsupported cursor version.")
    campaign_slug = root["campaign"]
    if not isinstance(campaign_slug, str) or not campaign_slug or len(campaign_slug) > 128:
        raise SourceHealthCursorError("Invalid cursor campaign.")
    raw_roster = root["roster"]
    if not isinstance(raw_roster, list) or not 1 <= len(raw_roster) <= 16:
        raise SourceHealthCursorError("Invalid cursor roster.")
    roster: list[str] = []
    for adapter_id in raw_roster:
        if not isinstance(adapter_id, str) or not _ADAPTER_ID_RE.fullmatch(adapter_id):
            raise SourceHealthCursorError("Invalid cursor adapter ID.")
        roster.append(adapter_id)
    if len(set(roster)) != len(roster):
        raise SourceHealthCursorError("Duplicate cursor adapter ID.")

    raw_adapters = root["adapters"]
    if not isinstance(raw_adapters, list) or len(raw_adapters) != len(roster):
        raise SourceHealthCursorError("Invalid cursor adapter state.")
    adapters: list[_CursorAdapterState] = []
    held_count = 0
    for expected_id, raw_adapter in zip(roster, raw_adapters, strict=True):
        adapter = _require_exact_keys(
            raw_adapter,
            {
                "completed",
                "cursor",
                "exhausted",
                "held",
                "id",
                "page_count",
                "page_digest",
            },
        )
        if adapter["id"] != expected_id:
            raise SourceHealthCursorError("Cursor adapter order changed.")
        cursor = adapter["cursor"]
        if not isinstance(cursor, str) or len(cursor) > 512:
            raise SourceHealthCursorError("Invalid adapter cursor.")
        exhausted = _require_bool(adapter["exhausted"])
        held = _require_bool(adapter["held"])
        raw_completed = adapter["completed"]
        if not isinstance(raw_completed, list) or len(raw_completed) > 50:
            raise SourceHealthCursorError("Invalid held consumer state.")
        completed: list[str] = []
        for marker in raw_completed:
            if not isinstance(marker, str) or not _DIGEST_RE.fullmatch(marker):
                raise SourceHealthCursorError("Invalid held consumer marker.")
            completed.append(marker)
        if len(set(completed)) != len(completed):
            raise SourceHealthCursorError("Duplicate held consumer marker.")
        page_digest = adapter["page_digest"]
        page_count = _require_int(adapter["page_count"])
        if not isinstance(page_digest, str):
            raise SourceHealthCursorError("Invalid held page digest.")
        if held:
            held_count += 1
            if exhausted or not _DIGEST_RE.fullmatch(page_digest):
                raise SourceHealthCursorError("Invalid held adapter state.")
            if not 1 <= page_count <= 50 or len(completed) > page_count:
                raise SourceHealthCursorError("Invalid held adapter count.")
        elif completed or page_digest or page_count != 0:
            raise SourceHealthCursorError("Unexpected held adapter state.")
        if exhausted and (cursor or held):
            raise SourceHealthCursorError("Invalid exhausted adapter state.")
        adapters.append(
            _CursorAdapterState(
                adapter_id=expected_id,
                cursor=cursor,
                exhausted=exhausted,
                held=held,
                completed=tuple(completed),
                page_digest=page_digest,
                page_count=page_count,
            )
        )
    if held_count > 1:
        raise SourceHealthCursorError("Too many held owner pages.")

    raw_window = root["window"]
    window: _CursorWindowState | None = None
    if raw_window is not None:
        window_payload = _require_exact_keys(raw_window, {"count", "digest", "offset"})
        digest = window_payload["digest"]
        count = _require_int(window_payload["count"])
        offset = _require_int(window_payload["offset"])
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise SourceHealthCursorError("Invalid finding-window digest.")
        if count <= SOURCE_HEALTH_FINDING_LIMIT:
            raise SourceHealthCursorError("Invalid finding-window count.")
        if (
            offset <= 0
            or offset % SOURCE_HEALTH_FINDING_LIMIT != 0
            or offset >= count
        ):
            raise SourceHealthCursorError("Invalid finding-window offset.")
        window = _CursorWindowState(digest=digest, count=count, offset=offset)

    outcome = _require_exact_keys(
        root["outcome"],
        {"saw_any_consumer", "saw_nonhealthy"},
    )
    saw_any_consumer = _require_bool(outcome["saw_any_consumer"])
    saw_nonhealthy = _require_bool(outcome["saw_nonhealthy"])
    if saw_nonhealthy and not saw_any_consumer:
        raise SourceHealthCursorError("Invalid cumulative cursor outcome.")
    return _CompositeCursorState(
        campaign_slug=campaign_slug,
        roster=tuple(roster),
        adapters=tuple(adapters),
        window=window,
        saw_any_consumer=saw_any_consumer,
        saw_nonhealthy=saw_nonhealthy,
    )


def _consumer_marker(consumer: SourceHealthConsumer) -> str:
    reference = consumer.reference
    payload = {
        "accepted_target_types": list(consumer.accepted_target_types),
        "consumer_key": consumer.consumer_key,
        "consumer_type": consumer.consumer_type,
        "destination": consumer.destination,
        "reference": {
            "consumer_version": reference.consumer_version,
            "entry_key": reference.entry_key,
            "library_slug": reference.library_slug,
            "rule_key": reference.rule_key,
            "slug": reference.slug,
            "source_id": reference.source_id,
            "system_code": reference.system_code,
            "target_id": reference.target_id,
            "target_kind": reference.target_kind,
            "version_scheme": reference.version_scheme,
        },
        "surface": consumer.surface,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _character_reference_group_key(reference: SourceHealthReference) -> object:
    locators = tuple(
        value
        for value in (
            _text(reference.target_id),
            _text(reference.slug),
            _text(reference.entry_key),
        )
        if value
    )
    if locators and len(set(locators)) == 1:
        return ("locator", locators[0])
    return ("reference", reference)


def _character_reference_canonical_identity(
    campaign_slug: str,
    reference: SourceHealthReference,
) -> str:
    group_key = _character_reference_group_key(reference)
    if group_key[0] != "locator":
        return ""
    return f"character:{campaign_slug}:{group_key[1]}"


def _inventory_page_digest(page: SourceHealthInventoryPage) -> str:
    payload = {
        "character_definitions": {
            character_slug: sha256(
                json.dumps(
                    dict(definition),
                    default=str,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            for character_slug, definition in sorted(
                dict(page.character_definitions).items()
            )
        },
        "consumers": [_consumer_marker(consumer) for consumer in page.consumers],
        "continuation": _text(page.continuation),
        "targets": [
            {
                "accessible": target.accessible,
                "canonical_identity": target.canonical_identity,
                "destination": target.destination,
                "enabled": target.enabled,
                "review_blocked": target.review_blocked,
                "source_id": target.source_id,
                "system_code": target.system_code,
                "target_kind": target.target_kind,
                "target_type": target.target_type,
                "target_version": target.target_version,
                "version_scheme": target.version_scheme,
                "wrong_system": target.wrong_system,
            }
            for target in page.targets
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _finding_window_digest(findings: list[SourceHealthFinding]) -> str:
    encoded = json.dumps(
        [finding.to_payload() for finding in findings],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class SourceHealthService:
    """Read-only orchestration with authorization strictly before inventory."""

    def __init__(
        self,
        *,
        authorize: AuthorizationAdapter,
        inventory_adapters: tuple[tuple[str, InventoryAdapter], ...],
        resolver: ResolutionAdapter,
        character_resolver: CharacterResolutionAdapter,
        cursor_codec: SourceHealthCursorCodec,
        fingerprint_resolver: FingerprintResolutionAdapter | None = None,
        character_fingerprint_resolver: CharacterFingerprintAdapter | None = None,
    ) -> None:
        self._authorize = authorize
        registered: list[tuple[str, InventoryAdapter]] = []
        for registration in inventory_adapters:
            if not isinstance(registration, tuple) or len(registration) != 2:
                raise ValueError("Source Health inventory adapters require stable IDs.")
            adapter_id, adapter = registration
            if not isinstance(adapter_id, str) or not _ADAPTER_ID_RE.fullmatch(adapter_id):
                raise ValueError("Invalid Source Health adapter ID.")
            if not callable(adapter):
                raise ValueError("Invalid Source Health inventory adapter.")
            registered.append((adapter_id, adapter))
        if not registered or len(registered) > 16:
            raise ValueError("Source Health requires one to sixteen inventory adapters.")
        adapter_ids = tuple(adapter_id for adapter_id, _adapter in registered)
        if len(set(adapter_ids)) != len(adapter_ids):
            raise ValueError("Source Health adapter IDs must be unique.")
        self._inventory_adapters = tuple(registered)
        self._adapter_ids = adapter_ids
        self._adapters_by_id = dict(registered)
        self._resolver = resolver
        if not callable(character_resolver):
            raise ValueError("Invalid Character Source Health resolution adapter.")
        self._character_resolver = character_resolver
        if fingerprint_resolver is not None and not callable(fingerprint_resolver):
            raise ValueError("Invalid Source Health fingerprint resolution adapter.")
        self._fingerprint_resolver = fingerprint_resolver
        if character_fingerprint_resolver is not None and not callable(
            character_fingerprint_resolver
        ):
            raise ValueError("Invalid Character fingerprint resolution adapter.")
        self._character_fingerprint_resolver = character_fingerprint_resolver
        self._cursor_codec = cursor_codec

    def _initial_cursor_state(self, campaign_slug: str) -> _CompositeCursorState:
        return _CompositeCursorState(
            campaign_slug=campaign_slug,
            roster=self._adapter_ids,
            adapters=tuple(
                _CursorAdapterState(adapter_id=adapter_id)
                for adapter_id in self._adapter_ids
            ),
        )

    def _load_cursor_state(
        self,
        context: SourceHealthAccessContext,
        continuation: str,
    ) -> _CompositeCursorState:
        if not _text(continuation):
            return self._initial_cursor_state(context.campaign_slug)
        decoded = self._cursor_codec.decode(continuation)
        state = _parse_composite_cursor_state(decoded)
        if state.campaign_slug != context.campaign_slug:
            raise SourceHealthCursorError("Cursor campaign changed.")
        if state.roster != self._adapter_ids:
            raise SourceHealthCursorError("Cursor adapter roster changed.")
        return state

    @staticmethod
    def _error_report(context: SourceHealthAccessContext) -> SourceHealthReport:
        return SourceHealthReport(
            campaign_slug=context.campaign_slug,
            state="error",
            complete=False,
            message=SOURCE_HEALTH_ERROR_MESSAGE,
        )

    def build_report(self, campaign_slug: str, *, continuation: str = "") -> SourceHealthReport:
        context = self._authorize(_text(campaign_slug))
        if context is None:
            raise SourceHealthDenied()

        try:
            state = self._load_cursor_state(context, _text(continuation))
        except Exception:
            return self._error_report(context)

        try:
            state_by_id = {adapter.adapter_id: adapter for adapter in state.adapters}
            pages_by_id: dict[str, SourceHealthInventoryPage] = {}
            for adapter_id in self._adapter_ids:
                adapter_state = state_by_id[adapter_id]
                if adapter_state.exhausted:
                    continue
                page = self._adapters_by_id[adapter_id](context, adapter_state.cursor)
                if not isinstance(page, SourceHealthInventoryPage):
                    raise ValueError("Invalid Source Health inventory page.")
                page_continuation = _text(page.continuation)
                if len(page_continuation) > 512 or (
                    page_continuation and page_continuation == adapter_state.cursor
                ):
                    raise ValueError("Invalid Source Health adapter continuation.")
                if adapter_state.held and (
                    len(page.consumers) != adapter_state.page_count
                    or _inventory_page_digest(page) != adapter_state.page_digest
                ):
                    raise ValueError("Held Source Health owner page changed.")
                pages_by_id[adapter_id] = page

            consumers_by_id = {
                adapter_id: tuple(page.consumers or ())
                for adapter_id, page in pages_by_id.items()
            }
            consumers = tuple(
                consumer
                for adapter_id in self._adapter_ids
                for consumer in consumers_by_id.get(adapter_id, ())
            )
            pending_consumers_by_id = {
                adapter_id: tuple(
                    consumer
                    for consumer in consumers_by_id.get(adapter_id, ())
                    if _consumer_marker(consumer)
                    not in set(state_by_id[adapter_id].completed)
                )
                for adapter_id in self._adapter_ids
            }
            pending_consumers = tuple(
                consumer
                for adapter_id in self._adapter_ids
                for consumer in pending_consumers_by_id[adapter_id]
            )
            references = tuple(
                dict.fromkeys(consumer.reference for consumer in pending_consumers)
            )
            if len(references) > SOURCE_HEALTH_TARGET_REFERENCE_LIMIT:
                raise ValueError("Source Health target references exceed their cap.")
            general_references = tuple(
                reference
                for reference in references
                if reference.target_kind != "character"
            )
            resolutions = (
                dict(self._resolver(context, general_references))
                if general_references
                else {}
            )
            local_targets = tuple(
                target
                for page in pages_by_id.values()
                for target in tuple(page.targets or ())
            )
            character_reference_groups: dict[
                object, list[SourceHealthReference]
            ] = {}
            for reference in references:
                if reference.target_kind == "character":
                    character_reference_groups.setdefault(
                        _character_reference_group_key(reference),
                        [],
                    ).append(reference)
            if len(character_reference_groups) > 50:
                raise ValueError("Source Health Character exact refs exceed their cap.")

            inventory_definition_file_count = 0
            inventory_definition_bytes = 0
            for page in pages_by_id.values():
                if (
                    type(page.definition_file_count) is not int
                    or page.definition_file_count < 0
                    or type(page.definition_bytes) is not int
                    or page.definition_bytes < 0
                ):
                    raise ValueError("Invalid Source Health definition measurements.")
                page_character_definitions = dict(page.character_definitions)
                if (
                    len(page_character_definitions) > page.definition_file_count
                    or any(
                        not isinstance(character_slug, str)
                        or not character_slug
                        or not isinstance(payload, Mapping)
                        for character_slug, payload in page_character_definitions.items()
                    )
                ):
                    raise ValueError("Invalid Source Health Character definitions.")
                inventory_definition_file_count += page.definition_file_count
                inventory_definition_bytes += page.definition_bytes
            if inventory_definition_file_count > 50:
                raise ValueError("Source Health definition reads exceed their cap.")
            if inventory_definition_bytes > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES:
                raise ValueError("Source Health definition bytes exceed their cap.")

            deferred_character_references: set[SourceHealthReference] = set()
            unresolved_character_groups: list[
                tuple[SourceHealthReference, tuple[SourceHealthReference, ...]]
            ] = []
            for grouped_references in character_reference_groups.values():
                reference = grouped_references[0]
                canonical_identity = _character_reference_canonical_identity(
                    context.campaign_slug,
                    reference,
                )
                matches = tuple(
                    target
                    for target in local_targets
                    if target.target_kind == "character"
                    and canonical_identity
                    and target.canonical_identity == canonical_identity
                )
                if matches:
                    resolution = SourceHealthResolution(
                        targets=matches,
                        contains_inaccessible=any(
                            not target.accessible for target in matches
                        ),
                    )
                    for grouped_reference in grouped_references:
                        resolutions[grouped_reference] = resolution
                else:
                    unresolved_character_groups.append(
                        (reference, tuple(grouped_references))
                    )

            remaining_definition_budget = (
                50 - inventory_definition_file_count
            )
            exact_groups = unresolved_character_groups[:remaining_definition_budget]
            exact_references = tuple(
                representative for representative, _group in exact_groups
            )
            exact_batch = (
                self._character_resolver(context, exact_references)
                if exact_references
                else SourceHealthResolutionBatch()
            )
            if not isinstance(exact_batch, SourceHealthResolutionBatch):
                raise ValueError("Invalid Character Source Health resolution batch.")
            if set(exact_batch.resolutions) != set(exact_references):
                raise ValueError("Incomplete Character Source Health resolution batch.")
            if (
                exact_batch.definition_file_count > len(exact_references)
                or exact_batch.definition_file_count > remaining_definition_budget
                or exact_batch.import_file_count > len(exact_references)
            ):
                raise ValueError("Character Source Health definition reads exceed their cap.")
            if (
                inventory_definition_bytes
                + exact_batch.definition_bytes
                + exact_batch.import_bytes
                > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
            ):
                raise ValueError("Character Source Health definition bytes exceed their cap.")
            for representative, grouped_references in exact_groups:
                resolution = exact_batch.resolutions[representative]
                for grouped_reference in grouped_references:
                    resolutions[grouped_reference] = resolution
            for _representative, grouped_references in unresolved_character_groups[
                remaining_definition_budget:
            ]:
                deferred_character_references.update(grouped_references)
            character_definitions: dict[str, Mapping[str, object]] = {}
            for page in pages_by_id.values():
                character_definitions.update(dict(page.character_definitions))
            character_definitions.update(dict(exact_batch.character_definitions))
            character_fingerprint_batch = SourceHealthResolutionBatch(
                resolutions=resolutions
            )
            if self._character_fingerprint_resolver is not None:
                fingerprint_character_references = tuple(
                    reference
                    for reference in references
                    if reference.target_kind == "character"
                    and reference not in deferred_character_references
                    and reference.version_scheme == _COMBAT_SEED_VERSION_SCHEME
                )
                character_fingerprint_batch = self._character_fingerprint_resolver(
                    context,
                    fingerprint_character_references,
                    dict(resolutions),
                    character_definitions,
                    inventory_definition_bytes + exact_batch.definition_bytes,
                )
                if not isinstance(
                    character_fingerprint_batch,
                    SourceHealthResolutionBatch,
                ):
                    raise ValueError("Invalid Character fingerprint resolution batch.")
                if (
                    character_fingerprint_batch.definition_file_count != 0
                    or character_fingerprint_batch.import_file_count
                    > len(fingerprint_character_references)
                    or inventory_definition_bytes
                    + exact_batch.definition_bytes
                    + character_fingerprint_batch.import_bytes
                    > SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
                ):
                    raise ValueError("Character fingerprint reads exceed their cap.")
                resolutions = dict(character_fingerprint_batch.resolutions)
            if self._fingerprint_resolver is not None:
                fingerprint_references = tuple(
                    reference
                    for reference in references
                    if reference not in deferred_character_references
                )
                overlaid = self._fingerprint_resolver(
                    context,
                    fingerprint_references,
                    dict(resolutions),
                )
                if not isinstance(overlaid, Mapping):
                    raise ValueError("Invalid Source Health fingerprint resolution batch.")
                resolutions = dict(overlaid)
            findings: list[SourceHealthFinding] = []
            ready_markers_by_id: dict[str, set[str]] = {
                adapter_id: set() for adapter_id in self._adapter_ids
            }
            deferred_adapter_ids: set[str] = set()
            saw_any_consumer = state.saw_any_consumer or bool(consumers)
            for adapter_id in self._adapter_ids:
                adapter_state = state_by_id[adapter_id]
                completed = set(adapter_state.completed)
                page_consumers = consumers_by_id.get(adapter_id, ())
                for consumer in page_consumers:
                    marker = _consumer_marker(consumer)
                    if marker in completed:
                        continue
                    if (
                        consumer.reference.target_kind == "character"
                        and consumer.reference in deferred_character_references
                    ):
                        deferred_adapter_ids.add(adapter_id)
                        continue
                    finding = classify_source_health(
                        consumer,
                        resolutions.get(consumer.reference, SourceHealthResolution()),
                    )
                    findings.append(finding)
                    ready_markers_by_id[adapter_id].add(marker)

            prior_held_ids = {
                adapter.adapter_id for adapter in state.adapters if adapter.held
            }
            held_ids = prior_held_ids | deferred_adapter_ids
            if len(held_ids) > 1:
                raise ValueError("Source Health pending work exceeded one owner page.")
            held_id = next(iter(held_ids), "")
            if held_id and len(consumers_by_id.get(held_id, ())) > 50:
                raise ValueError("Source Health pending owner page exceeds its cap.")

            findings.sort(
                key=lambda item: (
                    _CLASSIFICATION_ORDER[item.classification],
                    item.consumer.consumer_type,
                    item.consumer.consumer_key,
                )
            )
            window_digest = _finding_window_digest(findings)
            window_count = len(findings)
            report_offset = state.window.offset if state.window is not None else 0
            if state.window is not None and (
                state.window.digest != window_digest
                or state.window.count != window_count
            ):
                raise ValueError("Source Health finding window changed.")
            next_report_offset = report_offset + SOURCE_HEALTH_FINDING_LIMIT
            visible_findings = findings[report_offset:next_report_offset]
            window_remaining = next_report_offset < window_count
            saw_nonhealthy = state.saw_nonhealthy or any(
                finding.classification != "healthy" for finding in findings
            )

            transitioned_adapters: list[_CursorAdapterState] = []
            for adapter_id in self._adapter_ids:
                adapter_state = state_by_id[adapter_id]
                if adapter_state.exhausted:
                    transitioned_adapters.append(adapter_state)
                    continue
                page = pages_by_id[adapter_id]
                if adapter_id == held_id and adapter_id in deferred_adapter_ids:
                    completed = tuple(
                        sorted(
                            set(adapter_state.completed)
                            | ready_markers_by_id[adapter_id]
                        )
                    )
                    if len(completed) > 50:
                        raise ValueError("Source Health held completion state exceeded its cap.")
                    transitioned_adapters.append(
                        _CursorAdapterState(
                            adapter_id=adapter_id,
                            cursor=adapter_state.cursor,
                            held=True,
                            completed=completed,
                            page_digest=_inventory_page_digest(page),
                            page_count=len(page.consumers),
                        )
                    )
                    continue
                next_cursor = _text(page.continuation)
                transitioned_adapters.append(
                    _CursorAdapterState(
                        adapter_id=adapter_id,
                        cursor=next_cursor,
                        exhausted=not bool(next_cursor),
                    )
                )

            if window_remaining:
                next_state = replace(
                    state,
                    window=_CursorWindowState(
                        digest=window_digest,
                        count=window_count,
                        offset=next_report_offset,
                    ),
                    saw_any_consumer=saw_any_consumer,
                    saw_nonhealthy=saw_nonhealthy,
                )
            else:
                next_state = _CompositeCursorState(
                    campaign_slug=context.campaign_slug,
                    roster=self._adapter_ids,
                    adapters=tuple(transitioned_adapters),
                    saw_any_consumer=saw_any_consumer,
                    saw_nonhealthy=saw_nonhealthy,
                )
            complete = not window_remaining and all(
                adapter.exhausted for adapter in transitioned_adapters
            )
            continuations = (
                ()
                if complete
                else (self._cursor_codec.encode(next_state.to_payload()),)
            )
            if not complete:
                state = "partial"
                message = "More in-scope consumers remain. Refresh or continue before treating the campaign as healthy or empty."
            elif not saw_any_consumer:
                state = "empty"
                message = "No in-scope durable consumers were found."
            elif not saw_nonhealthy:
                state = "healthy"
                message = "Every in-scope durable reference in this complete report is healthy."
            else:
                state = "findings"
                message = "Source Health found durable references that need attention."
            return SourceHealthReport(
                campaign_slug=context.campaign_slug,
                state=state,
                findings=tuple(visible_findings),
                complete=complete,
                continuations=continuations,
                message=message,
                measurements=SourceHealthMeasurements(
                    definition_file_count=(
                        inventory_definition_file_count
                        + exact_batch.definition_file_count
                    ),
                    definition_bytes=(
                        inventory_definition_bytes
                        + exact_batch.definition_bytes
                    ),
                ),
            )
        except Exception:
            return self._error_report(context)


def mark_source_health_report_stale(report: SourceHealthReport) -> SourceHealthReport:
    return replace(
        report,
        state="report_stale",
        complete=False,
        message=SOURCE_HEALTH_STALE_MESSAGE,
    )


def serialize_source_health_report(report: SourceHealthReport) -> bytes:
    payload = json.dumps(
        report.to_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(payload) > SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES:
        raise ValueError("Source Health payload exceeds its frozen byte ceiling.")
    return payload
