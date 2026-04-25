from __future__ import annotations

from types import SimpleNamespace

from player_wiki.system_policy import (
    CHARACTER_ADVANCEMENT_LANE_DND5E_LEVEL_UP,
    CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION,
    CHARACTER_ROUTE_LANE_DND5E,
    CHARACTER_ROUTE_LANE_SHARED,
    CHARACTER_ROUTE_LANE_XIANXIA,
    DND_5E_SYSTEM_CODE,
    XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
    XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE,
    XIANXIA_SYSTEM_CODE,
    character_advancement_lane,
    character_advancement_unsupported_message,
    character_controls_lane,
    character_read_lane,
    character_session_lane,
    default_systems_library_slug,
    is_dnd_5e_system,
    is_xianxia_system,
    native_character_create_lane,
    native_character_create_unsupported_message,
    normalize_system_code,
    supports_character_controls_routes,
    supports_character_read_routes,
    supports_character_session_routes,
    supports_native_character_advancement,
    supports_native_character_create,
    supports_combat_tracker,
    supports_dnd5e_character_pdf_import,
    supports_dnd5e_character_spellcasting_tools,
    supports_dnd5e_statblock_upload,
    supports_dnd5e_systems_import,
    supports_native_character_tools,
    system_policy_for_campaign,
    system_policy_for_code,
)


def test_system_policy_canonicalizes_dnd_5e_aliases() -> None:
    assert normalize_system_code("dnd 5e") == DND_5E_SYSTEM_CODE
    assert normalize_system_code("DND5E") == DND_5E_SYSTEM_CODE
    assert default_systems_library_slug("dnd-5e") == DND_5E_SYSTEM_CODE

    policy = system_policy_for_code("dnd5e")

    assert policy.code == DND_5E_SYSTEM_CODE
    assert is_dnd_5e_system("DND 5E")
    assert supports_combat_tracker("DND 5E")
    assert supports_dnd5e_statblock_upload("DND 5E")
    assert supports_native_character_tools("DND 5E")
    assert supports_native_character_create("DND 5E")
    assert supports_native_character_advancement("DND 5E")
    assert native_character_create_lane("DND 5E") == CHARACTER_ROUTE_LANE_DND5E
    assert character_read_lane("DND 5E") == CHARACTER_ROUTE_LANE_DND5E
    assert character_session_lane("DND 5E") == CHARACTER_ROUTE_LANE_DND5E
    assert character_controls_lane("DND 5E") == CHARACTER_ROUTE_LANE_SHARED
    assert character_advancement_lane("DND 5E") == CHARACTER_ADVANCEMENT_LANE_DND5E_LEVEL_UP
    assert supports_character_read_routes("DND 5E")
    assert supports_character_session_routes("DND 5E")
    assert supports_character_controls_routes("DND 5E")
    assert supports_dnd5e_character_pdf_import("DND 5E")
    assert supports_dnd5e_character_spellcasting_tools("DND 5E")
    assert supports_dnd5e_systems_import("DND 5E")


def test_system_policy_recognizes_xianxia_without_enabling_dnd_only_tools() -> None:
    campaign = SimpleNamespace(system="xianxia")
    policy = system_policy_for_campaign(campaign)

    assert normalize_system_code("xianxia") == XIANXIA_SYSTEM_CODE
    assert policy.code == XIANXIA_SYSTEM_CODE
    assert is_xianxia_system("xianxia")
    assert default_systems_library_slug("xianxia") == XIANXIA_SYSTEM_CODE
    assert not supports_combat_tracker("xianxia")
    assert not supports_dnd5e_statblock_upload("xianxia")
    assert not supports_native_character_tools("xianxia")
    assert not supports_native_character_create("xianxia")
    assert not supports_native_character_advancement("xianxia")
    assert native_character_create_lane("xianxia") == CHARACTER_ROUTE_LANE_XIANXIA
    assert character_read_lane("xianxia") == CHARACTER_ROUTE_LANE_XIANXIA
    assert character_session_lane("xianxia") == CHARACTER_ROUTE_LANE_XIANXIA
    assert character_controls_lane("xianxia") == CHARACTER_ROUTE_LANE_SHARED
    assert character_advancement_lane("xianxia") == CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION
    assert supports_character_read_routes("xianxia")
    assert supports_character_session_routes("xianxia")
    assert supports_character_controls_routes("xianxia")
    assert native_character_create_unsupported_message("xianxia") == XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE
    assert character_advancement_unsupported_message("xianxia") == XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE
    assert not supports_dnd5e_character_pdf_import("xianxia")
    assert not supports_dnd5e_character_spellcasting_tools("xianxia")
    assert not supports_dnd5e_systems_import("xianxia")


def test_unknown_systems_remain_unsupported_without_rewriting_the_code() -> None:
    policy = system_policy_for_code("Pathfinder 2E")

    assert policy.code == "Pathfinder 2E"
    assert policy.default_systems_library_slug == "Pathfinder 2E"
    assert not supports_combat_tracker("Pathfinder 2E")
    assert not supports_native_character_tools("Pathfinder 2E")
    assert not supports_native_character_create("Pathfinder 2E")
    assert not supports_native_character_advancement("Pathfinder 2E")
    assert native_character_create_lane("Pathfinder 2E") == ""
    assert character_read_lane("Pathfinder 2E") == CHARACTER_ROUTE_LANE_SHARED
    assert character_session_lane("Pathfinder 2E") == CHARACTER_ROUTE_LANE_SHARED
    assert character_controls_lane("Pathfinder 2E") == CHARACTER_ROUTE_LANE_SHARED
    assert supports_character_read_routes("Pathfinder 2E")
    assert supports_character_session_routes("Pathfinder 2E")
    assert supports_character_controls_routes("Pathfinder 2E")
    assert not supports_dnd5e_character_pdf_import("Pathfinder 2E")
    assert not supports_dnd5e_character_spellcasting_tools("Pathfinder 2E")
