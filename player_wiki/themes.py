from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THEME_KEY = "parchment"


@dataclass(frozen=True, slots=True)
class ThemePreset:
    key: str
    label: str
    description: str
    preview_colors: tuple[str, str, str]


THEME_PRESETS = (
    ThemePreset(
        key="parchment",
        label="Parchment",
        description="Warm parchment, copper accents, and the current default look.",
        preview_colors=("#efe2c5", "#fff9ef", "#8c4f31"),
    ),
    ThemePreset(
        key="moonlit",
        label="Moonlit Ledger",
        description="A dark brass-and-slate palette for late-night reading.",
        preview_colors=("#172331", "#243547", "#d4b16f"),
    ),
    ThemePreset(
        key="verdant",
        label="Verdant Archive",
        description="Soft greens and mossy neutrals with a brighter page surface.",
        preview_colors=("#dfe9db", "#fbfdf9", "#4a7e60"),
    ),
    ThemePreset(
        key="ember",
        label="Ember Court",
        description="Copper dusk tones with warmer highlights and bolder contrast.",
        preview_colors=("#f0d3bc", "#fff7f3", "#a34c31"),
    ),
)

THEME_PRESET_BY_KEY = {preset.key: preset for preset in THEME_PRESETS}


def list_theme_presets() -> list[ThemePreset]:
    return list(THEME_PRESETS)


def is_valid_theme_key(value: str) -> bool:
    return value.strip().lower() in THEME_PRESET_BY_KEY


def normalize_theme_key(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in THEME_PRESET_BY_KEY:
        return normalized
    return DEFAULT_THEME_KEY


def get_theme_preset(value: str | None) -> ThemePreset:
    return THEME_PRESET_BY_KEY[normalize_theme_key(value)]
