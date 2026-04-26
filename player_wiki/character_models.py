from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .system_policy import DND_5E_SYSTEM_CODE, is_xianxia_system, normalize_system_code
from .xianxia_character_model import normalize_xianxia_definition_payload


def _normalize_proficiency_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe_proficiency_values(values: Any) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in list(values or []):
        cleaned = _normalize_proficiency_text(value)
        normalized = cleaned.casefold()
        if not cleaned or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(cleaned)
    return deduped


@dataclass(slots=True)
class CharacterDefinition:
    campaign_slug: str
    character_slug: str
    name: str
    status: str
    profile: dict[str, Any]
    stats: dict[str, Any]
    skills: list[dict[str, Any]]
    proficiencies: dict[str, list[str]]
    attacks: list[dict[str, Any]]
    features: list[dict[str, Any]]
    spellcasting: dict[str, Any]
    equipment_catalog: list[dict[str, Any]]
    reference_notes: dict[str, Any]
    resource_templates: list[dict[str, Any]]
    source: dict[str, Any]
    system: str = DND_5E_SYSTEM_CODE
    xianxia: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        normalized_system = normalize_system_code(self.system) or DND_5E_SYSTEM_CODE
        payload = {
            "campaign_slug": self.campaign_slug,
            "character_slug": self.character_slug,
            "name": self.name,
            "status": self.status,
            "system": normalized_system,
            "profile": self.profile,
            "stats": self.stats,
            "skills": self.skills,
            "proficiencies": self.proficiencies,
            "attacks": self.attacks,
            "features": self.features,
            "spellcasting": self.spellcasting,
            "equipment_catalog": self.equipment_catalog,
            "reference_notes": self.reference_notes,
            "resource_templates": self.resource_templates,
            "source": self.source,
        }
        if is_xianxia_system(normalized_system):
            payload["xianxia"] = normalize_xianxia_definition_payload(
                {**payload, "xianxia": self.xianxia}
            )["xianxia"]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CharacterDefinition":
        normalized_system = (
            normalize_system_code(payload.get("system") or payload.get("system_code") or DND_5E_SYSTEM_CODE)
            or DND_5E_SYSTEM_CODE
        )
        normalized_payload = dict(payload)
        normalized_payload["system"] = normalized_system
        if is_xianxia_system(normalized_system):
            normalized_payload = normalize_xianxia_definition_payload(normalized_payload)

        required_fields = ("campaign_slug", "character_slug", "name", "status")
        missing = [field for field in required_fields if not normalized_payload.get(field)]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Character definition is missing required fields: {joined}")
        raw_proficiencies = dict(normalized_payload.get("proficiencies") or {})
        tool_expertise = _dedupe_proficiency_values(raw_proficiencies.get("tool_expertise") or [])
        tools = _dedupe_proficiency_values(list(raw_proficiencies.get("tools") or []) + tool_expertise)

        return cls(
            campaign_slug=str(normalized_payload["campaign_slug"]),
            character_slug=str(normalized_payload["character_slug"]),
            name=str(normalized_payload["name"]),
            status=str(normalized_payload["status"]),
            profile=dict(normalized_payload.get("profile") or {}),
            stats=dict(normalized_payload.get("stats") or {}),
            skills=list(normalized_payload.get("skills") or []),
            proficiencies={
                "armor": _dedupe_proficiency_values(raw_proficiencies.get("armor") or []),
                "weapons": _dedupe_proficiency_values(raw_proficiencies.get("weapons") or []),
                "tools": tools,
                "languages": _dedupe_proficiency_values(raw_proficiencies.get("languages") or []),
                "tool_expertise": tool_expertise,
            },
            attacks=list(normalized_payload.get("attacks") or []),
            features=list(normalized_payload.get("features") or []),
            spellcasting=dict(normalized_payload.get("spellcasting") or {}),
            equipment_catalog=list(normalized_payload.get("equipment_catalog") or []),
            reference_notes=dict(normalized_payload.get("reference_notes") or {}),
            resource_templates=list(normalized_payload.get("resource_templates") or []),
            source=dict(normalized_payload.get("source") or {}),
            system=normalized_system,
            xianxia=dict(normalized_payload.get("xianxia") or {}) if is_xianxia_system(normalized_system) else {},
        )


@dataclass(slots=True)
class CharacterImportMetadata:
    campaign_slug: str
    character_slug: str
    source_path: str
    imported_at_utc: str
    parser_version: str
    import_status: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_slug": self.campaign_slug,
            "character_slug": self.character_slug,
            "source_path": self.source_path,
            "imported_at_utc": self.imported_at_utc,
            "parser_version": self.parser_version,
            "import_status": self.import_status,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CharacterImportMetadata":
        return cls(
            campaign_slug=str(payload.get("campaign_slug", "")),
            character_slug=str(payload.get("character_slug", "")),
            source_path=str(payload.get("source_path", "")),
            imported_at_utc=str(payload.get("imported_at_utc", "")),
            parser_version=str(payload.get("parser_version", "")),
            import_status=str(payload.get("import_status", "")),
            warnings=list(payload.get("warnings") or []),
        )


@dataclass(slots=True)
class CharacterStateRecord:
    campaign_slug: str
    character_slug: str
    revision: int
    state: dict[str, Any]
    updated_at: datetime
    updated_by_user_id: int | None


@dataclass(slots=True)
class CharacterRecord:
    definition: CharacterDefinition
    import_metadata: CharacterImportMetadata
    state_record: CharacterStateRecord
