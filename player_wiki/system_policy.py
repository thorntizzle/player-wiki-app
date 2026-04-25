from __future__ import annotations

from dataclasses import dataclass
import re

DND_5E_SYSTEM_CODE = "DND-5E"
XIANXIA_SYSTEM_CODE = "Xianxia"

NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE = (
    f"Native character tools are currently only supported for {DND_5E_SYSTEM_CODE} campaigns."
)
DND5E_CHARACTER_PDF_IMPORT_UNSUPPORTED_MESSAGE = (
    f"PDF character import is currently only supported for {DND_5E_SYSTEM_CODE} campaigns."
)
DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE = (
    f"Spellcasting management is currently only supported for {DND_5E_SYSTEM_CODE} campaigns."
)


@dataclass(frozen=True, slots=True)
class SystemCodePolicy:
    code: str
    label: str
    default_systems_library_slug: str
    supports_combat_tracker: bool = False
    supports_dnd5e_statblock_upload: bool = False
    supports_native_character_tools: bool = False
    supports_dnd5e_character_pdf_import: bool = False
    supports_dnd5e_character_spellcasting_tools: bool = False
    supports_dnd5e_systems_import: bool = False


def _normalize_system_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


_SYSTEM_CODE_BY_KEY = {
    _normalize_system_key(DND_5E_SYSTEM_CODE): DND_5E_SYSTEM_CODE,
    _normalize_system_key("DND 5E"): DND_5E_SYSTEM_CODE,
    _normalize_system_key("DND5E"): DND_5E_SYSTEM_CODE,
    _normalize_system_key(XIANXIA_SYSTEM_CODE): XIANXIA_SYSTEM_CODE,
}

_SYSTEM_POLICIES = {
    DND_5E_SYSTEM_CODE: SystemCodePolicy(
        code=DND_5E_SYSTEM_CODE,
        label=DND_5E_SYSTEM_CODE,
        default_systems_library_slug=DND_5E_SYSTEM_CODE,
        supports_combat_tracker=True,
        supports_dnd5e_statblock_upload=True,
        supports_native_character_tools=True,
        supports_dnd5e_character_pdf_import=True,
        supports_dnd5e_character_spellcasting_tools=True,
        supports_dnd5e_systems_import=True,
    ),
    XIANXIA_SYSTEM_CODE: SystemCodePolicy(
        code=XIANXIA_SYSTEM_CODE,
        label=XIANXIA_SYSTEM_CODE,
        default_systems_library_slug=XIANXIA_SYSTEM_CODE,
    ),
}

KNOWN_SYSTEM_CODES = tuple(_SYSTEM_POLICIES.keys())


def normalize_system_code(value: object) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    return _SYSTEM_CODE_BY_KEY.get(_normalize_system_key(raw_value), raw_value)


def system_policy_for_code(value: object) -> SystemCodePolicy:
    code = normalize_system_code(value)
    policy = _SYSTEM_POLICIES.get(code)
    if policy is not None:
        return policy
    return SystemCodePolicy(
        code=code,
        label=code or "Unspecified",
        default_systems_library_slug=code,
    )


def system_policy_for_campaign(campaign: object) -> SystemCodePolicy:
    return system_policy_for_code(getattr(campaign, "system", ""))


def system_label(value: object) -> str:
    return system_policy_for_code(value).label


def default_systems_library_slug(value: object) -> str:
    return system_policy_for_code(value).default_systems_library_slug


def is_dnd_5e_system(value: object) -> bool:
    return system_policy_for_code(value).code == DND_5E_SYSTEM_CODE


def is_xianxia_system(value: object) -> bool:
    return system_policy_for_code(value).code == XIANXIA_SYSTEM_CODE


def is_dnd_5e_systems_library(library_slug: object) -> bool:
    return normalize_system_code(library_slug) == DND_5E_SYSTEM_CODE


def supports_combat_tracker(value: object) -> bool:
    return system_policy_for_code(value).supports_combat_tracker


def supports_dnd5e_statblock_upload(value: object) -> bool:
    return system_policy_for_code(value).supports_dnd5e_statblock_upload


def supports_native_character_tools(value: object) -> bool:
    return system_policy_for_code(value).supports_native_character_tools


def supports_dnd5e_character_pdf_import(value: object) -> bool:
    return system_policy_for_code(value).supports_dnd5e_character_pdf_import


def supports_dnd5e_character_spellcasting_tools(value: object) -> bool:
    return system_policy_for_code(value).supports_dnd5e_character_spellcasting_tools


def supports_dnd5e_systems_import(library_slug: object) -> bool:
    return is_dnd_5e_systems_library(library_slug)
