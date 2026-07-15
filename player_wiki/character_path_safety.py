from __future__ import annotations

from pathlib import Path, PureWindowsPath


class CharacterPathSafetyError(ValueError):
    pass


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "CONIN$",
    "CONOUT$",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
    "COM\u00b9",
    "COM\u00b2",
    "COM\u00b3",
    "LPT\u00b9",
    "LPT\u00b2",
    "LPT\u00b3",
}
_WINDOWS_ILLEGAL_CHARACTERS = frozenset('<>:"|?*')


def validate_character_slug(character_slug: str) -> str:
    """Return an exact, cross-platform-safe Character directory name."""

    if not isinstance(character_slug, str) or not character_slug:
        raise CharacterPathSafetyError("A Character slug is required.")
    if character_slug in {".", ".."}:
        raise CharacterPathSafetyError("Character slugs cannot be dot-path segments.")
    if "/" in character_slug or "\\" in character_slug:
        raise CharacterPathSafetyError("Character slugs cannot contain path separators.")
    if any(ord(character) < 32 or ord(character) == 127 for character in character_slug):
        raise CharacterPathSafetyError("Character slugs cannot contain control characters.")
    if any(character in _WINDOWS_ILLEGAL_CHARACTERS for character in character_slug):
        raise CharacterPathSafetyError("Character slugs contain an unsupported filesystem character.")
    if character_slug.endswith((".", " ")):
        raise CharacterPathSafetyError("Character slugs cannot end with a dot or space.")

    windows_path = PureWindowsPath(character_slug)
    if windows_path.is_absolute() or windows_path.drive or windows_path.root:
        raise CharacterPathSafetyError("Character slugs must be relative directory names.")
    reserved_stem = character_slug.split(".", 1)[0].upper()
    if reserved_stem in _WINDOWS_RESERVED_NAMES:
        raise CharacterPathSafetyError("Character slugs cannot use reserved filesystem names.")
    return character_slug


def resolve_character_path(
    root_dir: Path,
    character_slug: str,
    *child_parts: str,
) -> Path:
    """Resolve a Character path and prove it remains beneath ``root_dir``."""

    validate_character_slug(character_slug)
    root = Path(root_dir).resolve()
    candidate = root / character_slug
    for child_part in child_parts:
        candidate /= child_part
    resolved = candidate.resolve()
    if root not in resolved.parents or resolved != candidate:
        raise CharacterPathSafetyError("Resolved Character path escapes its configured root.")
    return resolved
