from __future__ import annotations

from pathlib import Path

import pytest

import player_wiki.character_path_safety as path_safety
from player_wiki.character_path_safety import CharacterPathSafetyError


def test_definition_import_pair_resolves_root_and_each_fixed_child_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "characters"
    character_dir = root / "hero"
    character_dir.mkdir(parents=True)
    definition = character_dir / "definition.yaml"
    import_file = character_dir / "import.yaml"
    definition.write_text("name: Hero\n", encoding="utf-8")
    import_file.write_text("source: test\n", encoding="utf-8")
    calls: list[Path] = []
    real_resolve = Path.resolve

    def tracked_resolve(path: Path, *args, **kwargs) -> Path:
        calls.append(path)
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", tracked_resolve)

    actual_definition, actual_import = (
        path_safety.resolve_character_definition_import_paths(root, "hero")
    )

    assert (actual_definition, actual_import) == (definition, import_file)
    assert calls == [root, definition, import_file]


@pytest.mark.parametrize("child_name", ("definition.yaml", "import.yaml"))
def test_definition_import_pair_rejects_child_symlink_escape(
    tmp_path: Path,
    child_name: str,
) -> None:
    root = tmp_path / "characters"
    character_dir = root / "hero"
    character_dir.mkdir(parents=True)
    outside = tmp_path / f"outside-{child_name}"
    outside.write_text("unsafe\n", encoding="utf-8")
    try:
        (character_dir / child_name).symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this Windows host: {exc}")
    other_name = "import.yaml" if child_name == "definition.yaml" else "definition.yaml"
    (character_dir / other_name).write_text("safe\n", encoding="utf-8")

    with pytest.raises(CharacterPathSafetyError):
        path_safety.resolve_character_definition_import_paths(root, "hero")


def test_definition_import_pair_rejects_character_directory_symlink_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "characters"
    root.mkdir()
    outside = tmp_path / "outside-character"
    outside.mkdir()
    (outside / "definition.yaml").write_text("unsafe\n", encoding="utf-8")
    (outside / "import.yaml").write_text("unsafe\n", encoding="utf-8")
    try:
        (root / "hero").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this Windows host: {exc}")

    with pytest.raises(CharacterPathSafetyError):
        path_safety.resolve_character_definition_import_paths(root, "hero")


def test_definition_import_pair_rejects_in_root_character_alias(
    tmp_path: Path,
) -> None:
    root = tmp_path / "characters"
    actual = root / "actual"
    actual.mkdir(parents=True)
    (actual / "definition.yaml").write_text("name: Actual\n", encoding="utf-8")
    (actual / "import.yaml").write_text("source: test\n", encoding="utf-8")
    try:
        (root / "hero").symlink_to(actual, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this Windows host: {exc}")

    with pytest.raises(CharacterPathSafetyError):
        path_safety.resolve_character_definition_import_paths(root, "hero")


@pytest.mark.parametrize("slug", ("../hero", "CON", "hero/other", ""))
def test_definition_import_pair_reuses_exact_slug_validation(
    tmp_path: Path,
    slug: str,
) -> None:
    with pytest.raises(CharacterPathSafetyError):
        path_safety.resolve_character_definition_import_paths(
            tmp_path / "characters",
            slug,
        )
