from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_slug": self.campaign_slug,
            "character_slug": self.character_slug,
            "name": self.name,
            "status": self.status,
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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CharacterDefinition":
        required_fields = ("campaign_slug", "character_slug", "name", "status")
        missing = [field for field in required_fields if not payload.get(field)]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Character definition is missing required fields: {joined}")

        return cls(
            campaign_slug=str(payload["campaign_slug"]),
            character_slug=str(payload["character_slug"]),
            name=str(payload["name"]),
            status=str(payload["status"]),
            profile=dict(payload.get("profile") or {}),
            stats=dict(payload.get("stats") or {}),
            skills=list(payload.get("skills") or []),
            proficiencies={
                "armor": list((payload.get("proficiencies") or {}).get("armor") or []),
                "weapons": list((payload.get("proficiencies") or {}).get("weapons") or []),
                "tools": list((payload.get("proficiencies") or {}).get("tools") or []),
                "languages": list((payload.get("proficiencies") or {}).get("languages") or []),
            },
            attacks=list(payload.get("attacks") or []),
            features=list(payload.get("features") or []),
            spellcasting=dict(payload.get("spellcasting") or {}),
            equipment_catalog=list(payload.get("equipment_catalog") or []),
            reference_notes=dict(payload.get("reference_notes") or {}),
            resource_templates=list(payload.get("resource_templates") or []),
            source=dict(payload.get("source") or {}),
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
