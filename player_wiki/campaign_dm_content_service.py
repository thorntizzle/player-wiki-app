from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .campaign_dm_content_store import CampaignDMContentStore
from .dm_content_models import (
    CampaignDMConditionDefinitionRecord,
    CampaignDMStatblockRecord,
)
from .repository import normalize_lookup, parse_frontmatter

ALLOWED_DM_CONTENT_MARKDOWN_EXTENSIONS = {".markdown", ".md"}
STATBLOCK_TITLE_HEADING_PATTERN = re.compile(r"^\s{0,3}#\s+(?P<title>.*?)\s*#*\s*$")
STATBLOCK_NAME_LINE_PATTERN = re.compile(r"(?im)^\s*Name\s*:\s*(?P<value>.+?)\s*$")
STATBLOCK_ARMOR_CLASS_PATTERN = re.compile(r"(?im)^\s*\*{0,2}Armor Class\*{0,2}\s*:?\s*(?P<value>\d+)\b")
STATBLOCK_HIT_POINTS_PATTERN = re.compile(r"(?im)^\s*\*{0,2}Hit Points\*{0,2}\s*:?\s*(?P<value>\d+)\b")
STATBLOCK_SPEED_PATTERN = re.compile(r"(?im)^\s*\*{0,2}Speed\*{0,2}\s*:?\s*(?P<value>.+?)\s*$")
STATBLOCK_DEX_MODIFIER_PATTERN = re.compile(r"(?im)\bDEX\s+\d+\s+\((?P<value>[+-]\d+)\)")
STATBLOCK_MOVEMENT_VALUE_PATTERN = re.compile(r"(?P<distance>\d+)")


class CampaignDMContentValidationError(ValueError):
    pass


@dataclass(slots=True)
class DMStatblockUpload:
    title: str
    body_markdown: str
    source_filename: str
    subsection: str
    armor_class: int | None
    max_hp: int
    speed_text: str
    movement_total: int
    initiative_bonus: int


def extract_statblock_title_heading(markdown_text: str) -> tuple[str, str]:
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    line_index = 0
    while line_index < len(lines) and not lines[line_index].strip():
        line_index += 1

    if line_index >= len(lines):
        return "", markdown_text.strip()

    match = STATBLOCK_TITLE_HEADING_PATTERN.match(lines[line_index])
    if match is None:
        return "", markdown_text.strip()

    title = match.group("title").strip()
    if not title:
        return "", markdown_text.strip()

    body_lines = lines[line_index + 1 :]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    return title, "\n".join(body_lines).strip()


def fallback_title_from_filename(filename: str) -> str:
    stem = Path(filename or "").stem.strip()
    if stem.lower().endswith(" statblock"):
        stem = stem[:-10].strip()
    return stem


def is_generic_statblock_heading(value: str) -> bool:
    return "statblock" in normalize_lookup(value)


class CampaignDMContentService:
    def __init__(self, store: CampaignDMContentStore) -> None:
        self.store = store

    def list_statblocks(self, campaign_slug: str) -> list[CampaignDMStatblockRecord]:
        return self.store.list_statblocks(campaign_slug)

    def get_statblock(self, campaign_slug: str, statblock_id: int) -> CampaignDMStatblockRecord | None:
        return self.store.get_statblock(campaign_slug, statblock_id)

    def create_statblock(
        self,
        campaign_slug: str,
        *,
        filename: str,
        data_blob: bytes,
        subsection: str = "",
        created_by_user_id: int | None = None,
    ) -> CampaignDMStatblockRecord:
        upload = self.parse_statblock_markdown_upload(
            filename=filename,
            data_blob=data_blob,
            subsection_hint=subsection,
        )
        return self.store.create_statblock(
            campaign_slug,
            title=upload.title,
            body_markdown=upload.body_markdown,
            source_filename=upload.source_filename,
            subsection=upload.subsection,
            armor_class=upload.armor_class,
            max_hp=upload.max_hp,
            speed_text=upload.speed_text,
            movement_total=upload.movement_total,
            initiative_bonus=upload.initiative_bonus,
            created_by_user_id=created_by_user_id,
        )

    def delete_statblock(self, campaign_slug: str, statblock_id: int) -> CampaignDMStatblockRecord:
        statblock = self.store.delete_statblock(campaign_slug, statblock_id)
        if statblock is None:
            raise CampaignDMContentValidationError("That statblock could not be found.")
        return statblock

    def list_condition_definitions(self, campaign_slug: str) -> list[CampaignDMConditionDefinitionRecord]:
        return self.store.list_condition_definitions(campaign_slug)

    def create_condition_definition(
        self,
        campaign_slug: str,
        *,
        name: str,
        description_markdown: str = "",
        created_by_user_id: int | None = None,
    ) -> CampaignDMConditionDefinitionRecord:
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise CampaignDMContentValidationError("Condition name is required.")
        if len(normalized_name) > 80:
            raise CampaignDMContentValidationError("Condition names must stay under 80 characters.")

        normalized_description = (description_markdown or "").strip()
        if len(normalized_description) > 4_000:
            raise CampaignDMContentValidationError("Condition descriptions must stay under 4,000 characters.")

        normalized_name_lookup = normalize_lookup(normalized_name)
        existing_names = {
            normalize_lookup(condition.name)
            for condition in self.store.list_condition_definitions(campaign_slug)
        }
        if normalized_name_lookup in existing_names:
            raise CampaignDMContentValidationError("A custom condition with that name already exists.")

        return self.store.create_condition_definition(
            campaign_slug,
            name=normalized_name,
            description_markdown=normalized_description,
            created_by_user_id=created_by_user_id,
        )

    def delete_condition_definition(
        self,
        campaign_slug: str,
        condition_definition_id: int,
    ) -> CampaignDMConditionDefinitionRecord:
        condition_definition = self.store.delete_condition_definition(campaign_slug, condition_definition_id)
        if condition_definition is None:
            raise CampaignDMContentValidationError("That custom condition could not be found.")
        return condition_definition

    def parse_statblock_markdown_upload(
        self,
        *,
        filename: str,
        data_blob: bytes,
        subsection_hint: str = "",
    ) -> DMStatblockUpload:
        normalized_filename = Path(filename or "").name.strip()
        if not normalized_filename:
            raise CampaignDMContentValidationError("Choose a markdown statblock file before uploading.")

        extension = Path(normalized_filename).suffix.lower()
        if extension not in ALLOWED_DM_CONTENT_MARKDOWN_EXTENSIONS:
            raise CampaignDMContentValidationError(
                "DM Content statblock uploads must use .md or .markdown files."
            )

        if not data_blob:
            raise CampaignDMContentValidationError("Uploaded statblock files cannot be empty.")

        try:
            raw_text = data_blob.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CampaignDMContentValidationError("Uploaded statblock files must be valid UTF-8 text.") from exc

        try:
            metadata, body_markdown = parse_frontmatter(raw_text)
        except yaml.YAMLError as exc:
            raise CampaignDMContentValidationError("Uploaded statblock frontmatter must be valid YAML.") from exc

        if not isinstance(metadata, dict):
            raise CampaignDMContentValidationError("Uploaded statblock frontmatter must be a YAML object.")

        normalized_body = body_markdown.strip()
        metadata_title = str(metadata.get("title") or metadata.get("name") or "").strip()
        heading_title, body_without_heading = extract_statblock_title_heading(normalized_body)
        if heading_title and is_generic_statblock_heading(heading_title):
            heading_title = ""
        elif heading_title:
            normalized_body = body_without_heading

        name_line_match = STATBLOCK_NAME_LINE_PATTERN.search(normalized_body)
        name_line_title = str(name_line_match.group("value")).strip() if name_line_match is not None else ""
        fallback_title = fallback_title_from_filename(normalized_filename)
        normalized_title = metadata_title or heading_title or name_line_title or fallback_title
        if not normalized_title:
            raise CampaignDMContentValidationError("The uploaded statblock needs a name or title.")

        normalized_subsection = self._normalize_statblock_subsection(
            subsection_hint
            or metadata.get("subsection")
            or metadata.get("group")
            or metadata.get("section")
        )

        armor_class = self._parse_optional_int(metadata.get("armor_class") or metadata.get("ac"))
        if armor_class is None:
            armor_class = self._search_int(STATBLOCK_ARMOR_CLASS_PATTERN, normalized_body)

        max_hp = self._parse_optional_int(metadata.get("max_hp") or metadata.get("hp"))
        if max_hp is None:
            max_hp = self._search_int(STATBLOCK_HIT_POINTS_PATTERN, normalized_body)
        if max_hp is None:
            raise CampaignDMContentValidationError("The uploaded statblock needs a Hit Points value.")

        speed_text = str(metadata.get("speed") or "").strip()
        if not speed_text:
            speed_match = STATBLOCK_SPEED_PATTERN.search(normalized_body)
            speed_text = str(speed_match.group("value")).strip() if speed_match is not None else ""
        if not speed_text:
            raise CampaignDMContentValidationError("The uploaded statblock needs a Speed value.")

        movement_total = self._parse_movement_total(speed_text)
        if movement_total < 0:
            raise CampaignDMContentValidationError("The uploaded statblock has an invalid Speed value.")

        initiative_bonus = self._parse_optional_int(metadata.get("initiative_bonus") or metadata.get("initiative"))
        if initiative_bonus is None:
            dex_match = STATBLOCK_DEX_MODIFIER_PATTERN.search(normalized_body)
            initiative_bonus = int(dex_match.group("value")) if dex_match is not None else 0

        return DMStatblockUpload(
            title=normalized_title,
            body_markdown=normalized_body,
            source_filename=normalized_filename,
            subsection=normalized_subsection,
            armor_class=armor_class,
            max_hp=max_hp,
            speed_text=speed_text,
            movement_total=movement_total,
            initiative_bonus=initiative_bonus,
        )

    def _search_int(self, pattern: re.Pattern[str], value: str) -> int | None:
        match = pattern.search(value or "")
        if match is None:
            return None
        return int(match.group("value"))

    def _parse_optional_int(self, value) -> int | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        match = re.search(r"-?\d+", normalized)
        if match is None:
            return None
        return int(match.group(0))

    def _parse_movement_total(self, value: str) -> int:
        distances = [int(match.group("distance")) for match in STATBLOCK_MOVEMENT_VALUE_PATTERN.finditer(value or "")]
        if not distances:
            return 0
        return max(distances)

    def _normalize_statblock_subsection(self, value: object) -> str:
        normalized = str(value or "").strip()
        if len(normalized) > 80:
            raise CampaignDMContentValidationError(
                "Statblock subsection labels must stay under 80 characters."
            )
        return normalized
