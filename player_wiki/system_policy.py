from __future__ import annotations

from dataclasses import dataclass
import re

DND_5E_SYSTEM_CODE = "DND-5E"
XIANXIA_SYSTEM_CODE = "Xianxia"

NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE = (
    "This campaign can still use the character roster, read-mode sheets, session-mode sheets, "
    "and Controls. Native DND-5E builder, edit, level-up, repair, retraining, PDF-import, "
    "and spellcasting tools are not implemented for this campaign system."
)
XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE = (
    "Xianxia is recognized as its own character lane, but its native character builder is not "
    "implemented yet. Use the roster and existing read/session sheets for now."
)
XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE = (
    "Xianxia advancement and cultivation are recognized as their own character lane, but those "
    "routes are not implemented yet. Use the existing read/session sheet and Controls surfaces "
    "for now."
)
DND5E_CHARACTER_PDF_IMPORT_UNSUPPORTED_MESSAGE = (
    f"PDF character import is currently only supported for {DND_5E_SYSTEM_CODE} campaigns."
)
DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE = (
    "This character sheet remains available, but DND-5E spellcasting management is not "
    "implemented for this campaign system."
)

CHARACTER_ROUTE_LANE_SHARED = "shared"
CHARACTER_ROUTE_LANE_DND5E = "dnd5e"
CHARACTER_ROUTE_LANE_XIANXIA = "xianxia"
CHARACTER_ADVANCEMENT_LANE_DND5E_LEVEL_UP = "dnd5e-level-up"
CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION = "xianxia-cultivation"


@dataclass(frozen=True, slots=True)
class SystemCodePolicy:
    code: str
    label: str
    default_systems_library_slug: str
    default_campaign_visibility_by_scope: tuple[tuple[str, str], ...] = ()
    supports_combat_tracker: bool = False
    supports_dnd5e_statblock_upload: bool = False
    supports_native_character_tools: bool = False
    supports_native_character_create: bool = False
    supports_native_character_advancement: bool = False
    native_character_create_lane: str = ""
    character_read_lane: str = CHARACTER_ROUTE_LANE_SHARED
    character_session_lane: str = CHARACTER_ROUTE_LANE_SHARED
    character_controls_lane: str = CHARACTER_ROUTE_LANE_SHARED
    character_advancement_lane: str = ""
    native_character_create_unsupported_message: str = NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE
    character_advancement_unsupported_message: str = NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE
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
        supports_native_character_create=True,
        supports_native_character_advancement=True,
        native_character_create_lane=CHARACTER_ROUTE_LANE_DND5E,
        character_read_lane=CHARACTER_ROUTE_LANE_DND5E,
        character_session_lane=CHARACTER_ROUTE_LANE_DND5E,
        character_controls_lane=CHARACTER_ROUTE_LANE_SHARED,
        character_advancement_lane=CHARACTER_ADVANCEMENT_LANE_DND5E_LEVEL_UP,
        supports_dnd5e_character_pdf_import=True,
        supports_dnd5e_character_spellcasting_tools=True,
        supports_dnd5e_systems_import=True,
    ),
    XIANXIA_SYSTEM_CODE: SystemCodePolicy(
        code=XIANXIA_SYSTEM_CODE,
        label=XIANXIA_SYSTEM_CODE,
        default_systems_library_slug=XIANXIA_SYSTEM_CODE,
        default_campaign_visibility_by_scope=(("systems", "dm"),),
        supports_native_character_create=True,
        native_character_create_lane=CHARACTER_ROUTE_LANE_XIANXIA,
        character_read_lane=CHARACTER_ROUTE_LANE_XIANXIA,
        character_session_lane=CHARACTER_ROUTE_LANE_XIANXIA,
        character_controls_lane=CHARACTER_ROUTE_LANE_SHARED,
        character_advancement_lane=CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION,
        native_character_create_unsupported_message=XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE,
        character_advancement_unsupported_message=XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
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


def supports_native_character_create(value: object) -> bool:
    return system_policy_for_code(value).supports_native_character_create


def supports_native_character_advancement(value: object) -> bool:
    return system_policy_for_code(value).supports_native_character_advancement


def native_character_create_lane(value: object) -> str:
    return system_policy_for_code(value).native_character_create_lane


def character_read_lane(value: object) -> str:
    return system_policy_for_code(value).character_read_lane


def character_session_lane(value: object) -> str:
    return system_policy_for_code(value).character_session_lane


def character_controls_lane(value: object) -> str:
    return system_policy_for_code(value).character_controls_lane


def character_advancement_lane(value: object) -> str:
    return system_policy_for_code(value).character_advancement_lane


def supports_character_read_routes(value: object) -> bool:
    return bool(character_read_lane(value))


def supports_character_session_routes(value: object) -> bool:
    return bool(character_session_lane(value))


def supports_character_controls_routes(value: object) -> bool:
    return bool(character_controls_lane(value))


def native_character_create_unsupported_message(value: object) -> str:
    return system_policy_for_code(value).native_character_create_unsupported_message


def character_advancement_unsupported_message(value: object) -> str:
    return system_policy_for_code(value).character_advancement_unsupported_message


def supports_dnd5e_character_pdf_import(value: object) -> bool:
    return system_policy_for_code(value).supports_dnd5e_character_pdf_import


def supports_dnd5e_character_spellcasting_tools(value: object) -> bool:
    return system_policy_for_code(value).supports_dnd5e_character_spellcasting_tools


def supports_dnd5e_systems_import(library_slug: object) -> bool:
    return is_dnd_5e_systems_library(library_slug)
