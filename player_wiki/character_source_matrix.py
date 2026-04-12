from __future__ import annotations

from dataclasses import dataclass

from .repository import normalize_lookup

PHB_SOURCE_ID = "PHB"


def _normalize_source_id(value: str) -> str:
    return str(value or "").strip().upper()


def _normalize_base_class_key(source_id: str, class_name: str) -> tuple[str, str] | None:
    normalized_source_id = _normalize_source_id(source_id)
    normalized_class_name = normalize_lookup(str(class_name or "").strip())
    if not normalized_source_id or not normalized_class_name:
        return None
    return normalized_source_id, normalized_class_name


@dataclass(frozen=True)
class NativeSourceMatrixPolicy:
    supported_non_phb_base_class_keys: frozenset[tuple[str, str]]
    supported_subordinate_source_ids: frozenset[str]
    phb_source_id: str = PHB_SOURCE_ID

    def __post_init__(self) -> None:
        normalized_phb_source_id = _normalize_source_id(self.phb_source_id) or PHB_SOURCE_ID
        normalized_base_class_keys = frozenset(
            key
            for key in (
                _normalize_base_class_key(source_id, class_name)
                for source_id, class_name in self.supported_non_phb_base_class_keys
            )
            if key is not None and key[0] != normalized_phb_source_id
        )
        normalized_subordinate_source_ids = frozenset(
            source_id
            for source_id in (_normalize_source_id(source_id) for source_id in self.supported_subordinate_source_ids)
            if source_id and source_id != normalized_phb_source_id
        )
        object.__setattr__(self, "phb_source_id", normalized_phb_source_id)
        object.__setattr__(self, "supported_non_phb_base_class_keys", normalized_base_class_keys)
        object.__setattr__(self, "supported_subordinate_source_ids", normalized_subordinate_source_ids)

    @property
    def supported_non_phb_source_ids(self) -> frozenset[str]:
        return frozenset(
            self.supported_subordinate_source_ids
            | {source_id for source_id, _ in self.supported_non_phb_base_class_keys}
        )

    def source_label(self, source_id: str) -> str:
        normalized_source_id = _normalize_source_id(source_id)
        return normalized_source_id or "non-PHB"

    def supports_base_class_identity(
        self,
        *,
        class_name: str,
        class_source: str,
    ) -> bool:
        normalized_class_source = _normalize_source_id(class_source)
        if not normalized_class_source:
            return False
        if normalized_class_source == self.phb_source_id:
            return True
        normalized_key = _normalize_base_class_key(normalized_class_source, class_name)
        return normalized_key in self.supported_non_phb_base_class_keys

    def supports_subclass_source(self, source_id: str) -> bool:
        normalized_source_id = _normalize_source_id(source_id)
        if not normalized_source_id:
            return False
        return normalized_source_id == self.phb_source_id or normalized_source_id in self.supported_non_phb_source_ids

    def should_prefix_profile_link_source(self, source_id: str) -> bool:
        return _normalize_source_id(source_id) in self.supported_non_phb_source_ids


# Keep the current accepted source boundary explicit in one place so future source
# additions can land as a policy update instead of a scattered builder refactor.
DEFAULT_NATIVE_SOURCE_MATRIX_POLICY = NativeSourceMatrixPolicy(
    supported_non_phb_base_class_keys=frozenset({("TCE", "Artificer")}),
    supported_subordinate_source_ids=frozenset({"TCE", "SCAG", "XGE", "EGW", "DMG"}),
)
