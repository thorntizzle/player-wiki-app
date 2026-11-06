"""One class/subclass progression and grant algorithm for both read adapters.

Ordinary service callers retain ordinary Python model semantics. The private
phase engine overrides only the explicit entry/tree access and output boundary.
"""
from __future__ import annotations
from collections import defaultdict
from html import escape
from .repository import normalize_lookup
from .systems_models import SystemsEntryRecord


class FeatureSemantics:
    @staticmethod
    def _feature_is_map(value):
        return isinstance(value, dict)

    @staticmethod
    def _feature_is_list(value):
        return isinstance(value, list)

    @staticmethod
    def _feature_is_entry(value):
        return isinstance(value, SystemsEntryRecord)

    @staticmethod
    def _feature_public_entry(value):
        return value

    def build_class_feature_progression_for_class_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *, include_embedded_cards: bool = True,
    ) -> list[dict[str, object]]:
        if entry.entry_type != "class":
            return []
        matching_entries = list(
            self._class_feature_entries_by_class_identity(
                campaign_slug, identity=(
                    str(entry.title or "").strip(),
                    str(entry.source_id or "").strip().upper(),
                ),
            )
        )

        progression_rows = entry.body.get("feature_progression")
        matching_entries.extend(
            self._campaign_progression_entries_for_class_entry(campaign_slug, entry)
        )
        return self._build_feature_progression_groups(
            campaign_slug,
            matching_entries=matching_entries,
            progression_rows=progression_rows,
            preferred_source_id=entry.source_id,
            include_embedded_cards=include_embedded_cards,
        )


    def build_subclass_feature_progression_for_subclass_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *, include_embedded_cards: bool = True,
    ) -> list[dict[str, object]]:
        if entry.entry_type != "subclass":
            return []
        class_name = str(entry.metadata.get("class_name", "") or "").strip()
        class_source = str(entry.metadata.get("class_source", "") or "").strip().upper()
        matching_entries = [
            candidate
            for candidate in self._subclass_feature_entries_by_class_and_source(
                campaign_slug, identity=(
                    class_name,
                    class_source,
                    str(entry.source_id or "").strip().upper(),
                ),
            )
            if self._subclass_entry_matches_feature(entry, candidate)
        ]

        progression_rows = entry.body.get("feature_progression")
        matching_entries.extend(
            self._campaign_progression_entries_for_subclass_entry(campaign_slug, entry)
        )
        return self._build_feature_progression_groups(
            campaign_slug,
            matching_entries=matching_entries,
            progression_rows=progression_rows,
            preferred_source_id=entry.source_id,
            include_embedded_cards=include_embedded_cards,
        )


    def _subclass_entry_matches_feature(
        self,
        subclass_entry: SystemsEntryRecord,
        subclass_feature_entry: SystemsEntryRecord,
    ) -> bool:
        subclass_title_variants = self._build_optionalfeature_title_variants(subclass_entry.title)
        feature_subclass_name = str(subclass_feature_entry.metadata.get("subclass_name", "") or "").strip()
        feature_title_variants = self._build_optionalfeature_title_variants(feature_subclass_name)
        return self._optionalfeature_titles_exactly_match(
            subclass_title_variants,
            feature_title_variants,
        ) or self._optionalfeature_titles_loosely_match(
            subclass_title_variants,
            feature_title_variants,
        )


    def _resolve_deterministic_feature_reference(
        self, campaign_slug: str, value: object, *, preferred_source_id: str,
        preferred_library_slug: str | None = None,
        owner_entry: SystemsEntryRecord | None = None,
    ) -> SystemsEntryRecord | None:
        """Resolve only full, same-source class/subclass references, uniquely."""
        if not self._feature_is_map(value):
            return None
        kind = str(value.get("type") or "").casefold()
        key = {"refclassfeature": "classFeature", "refsubclassfeature": "subclassFeature"}.get(kind)
        if not key or set(value) != {"type", key} or not isinstance(value.get(key), str):
            return None
        parts = [part.strip() for part in str(value[key]).split("|")]
        base_length = 4 if kind == "refclassfeature" else 6
        if len(parts) not in {base_length, base_length + 1}:
            return None
        # The pinned source reference format uses an empty class-source slot
        # for PHB. Admit that one default only within an exact PHB owner;
        # do not search other class/source versions for a missing identity.
        if (not parts[2] and owner_entry is not None
                and str(owner_entry.metadata.get("class_source") or "").upper() == "PHB"
                and str(owner_entry.metadata.get("class_name") or "").casefold() == parts[1].casefold()):
            parts[2] = "PHB"
        # The same pinned PHB UID convention omits the subclass-source slot.
        # Its default belongs to an exact owning subclass feature, never to
        # an inferred subclass/title or another class/source revision.
        if (kind == "refsubclassfeature" and not parts[4]
                and owner_entry is not None and owner_entry.entry_type == "subclassfeature"
                and owner_entry.source_id.upper() == "PHB"
                and str(preferred_source_id or "").upper() == "PHB"
                and parts[2].upper() == "PHB"
                and str(owner_entry.metadata.get("class_source") or "").upper() == "PHB"
                and str(owner_entry.metadata.get("class_name") or "").casefold() == parts[1].casefold()
                and str(owner_entry.metadata.get("subclass_source") or "").upper() == "PHB"
                and str(owner_entry.metadata.get("subclass_name") or "").casefold() == parts[3].casefold()
                and (preferred_library_slug is None or owner_entry.library_slug == preferred_library_slug)):
            parts[4] = "PHB"
        if not all(parts[:base_length]):
            return None
        source_id = parts[-1] if len(parts) > base_length and parts[-1] else parts[2 if base_length == 4 else 4]
        if source_id.casefold() != str(preferred_source_id or "").casefold():
            return None
        level = self._coerce_int(parts[base_length - 1], default=0)
        if not 1 <= level <= 20:
            return None
        if kind == "refclassfeature":
            candidates = self._class_feature_entries_by_class_identity(
                campaign_slug, identity=(parts[1], parts[2].upper()),
            )
        else:
            candidates = self._subclass_feature_entries_by_class_and_source(
                campaign_slug, identity=(parts[1], parts[2].upper(), parts[4].upper()),
            )
        matches = [
            candidate for candidate in candidates
            if candidate.title.casefold() == parts[0].casefold()
            and candidate.source_id.casefold() == source_id.casefold()
            and (preferred_library_slug is None or candidate.library_slug == preferred_library_slug)
            and self._coerce_int(candidate.metadata.get("level"), default=0) == level
            and (kind == "refclassfeature" or str(candidate.metadata.get("subclass_name") or "").casefold() == parts[3].casefold())
        ]
        return matches[0] if len(matches) == 1 else None


    def _deterministic_feature_bundle_entries(
        self, campaign_slug: str, value: object, *, preferred_source_id: str,
        preferred_library_slug: str | None = None,
        owner_entry: SystemsEntryRecord | None = None,
    ) -> list[SystemsEntryRecord] | None:
        # Count-less is necessary, not sufficient. Unknown selection controls,
        # prose/options, optionalfeature references and unresolved refs stay choices.
        if not self._feature_is_map(value) or set(value) not in (
            {"type", "entries"}, {"type", "entries", "style"},
        ):
            return None
        if "style" in value and value["style"] != "list-hang-notitle":
            return None
        if str(value.get("type") or "").casefold() != "options":
            return None
        entries = value.get("entries")
        if not self._feature_is_list(entries) or not 1 <= len(entries) <= 64:
            return None
        resolved = [self._resolve_deterministic_feature_reference(
            campaign_slug, item, preferred_source_id=preferred_source_id,
            preferred_library_slug=preferred_library_slug,
            owner_entry=owner_entry,
        ) for item in entries]
        if any(entry is None for entry in resolved):
            return None
        if owner_entry is not None and any(
            target.entry_type != owner_entry.entry_type or any(
                str(target.metadata.get(key) or "").casefold() != str(owner_entry.metadata.get(key) or "").casefold()
                for key in ("class_name", "class_source", "subclass_name", "subclass_source")
            ) for target in resolved
        ):
            return None
        return list(resolved)


    def _deterministic_feature_edges(
        self, campaign_slug: str, entry: SystemsEntryRecord,
        *, selected_feature_branches=None,
    ) -> tuple[list[SystemsEntryRecord], bool]:
        edges: list[SystemsEntryRecord] = []
        has_bundle = False
        body_entries = entry.body.get("entries")
        from .character_armor_models import MODEL, PATH, supported_rule, model_member_allowed
        if entry.entry_key == MODEL:
            # These are elective branches despite their plain entries shape.
            if (not supported_rule(self._feature_public_entry(entry))
                    or (selected_feature_branches or {}).get(MODEL) != list(PATH)):
                return [], False
            body_entries = entry.body["entries"][4]["entries"][0]
        pending: list[tuple[object, int]] = [(body_entries, 0)]
        visited = 0
        while pending:
            value, depth = pending.pop()
            visited += 1
            if visited > 512 or depth > 16:
                raise ValueError("Source feature grant structure exceeds the supported bounds.")
            if self._feature_is_list(value):
                pending.extend((item, depth + 1) for item in reversed(value))
                continue
            if not self._feature_is_map(value):
                continue
            kind = str(value.get("type") or "").casefold()
            if kind == "options":
                bundled = self._deterministic_feature_bundle_entries(
                    campaign_slug, value, preferred_source_id=entry.source_id,
                    preferred_library_slug=entry.library_slug,
                    owner_entry=entry,
                )
                if bundled is not None:
                    has_bundle = True
                    edges.extend(bundled)
                continue
            if kind in {"refclassfeature", "refsubclassfeature"}:
                target = self._resolve_deterministic_feature_reference(
                    campaign_slug, value, preferred_source_id=entry.source_id,
                    preferred_library_slug=entry.library_slug,
                    owner_entry=entry,
                )
                if target is not None:
                    edges.append(target)
                continue
            if kind in {"", "entries", "section", "list", "item"}:
                for key in ("entries", "entry", "items"):
                    if key in value:
                        pending.append((value[key], depth + 1))
        # A reference cannot escape the owner's exact class/subclass identity.
        identity_keys = ("class_name", "class_source", "subclass_name", "subclass_source")
        return [target for target in edges if model_member_allowed(target, selected_feature_branches)
            and target.entry_type == entry.entry_type and all(
            str(target.metadata.get(key) or "").casefold() == str(entry.metadata.get(key) or "").casefold()
            for key in identity_keys
        )], has_bundle


    def collect_attained_deterministic_feature_entries(
        self, campaign_slug: str, entry: SystemsEntryRecord, *, attained_level: int,
        selected_feature_branches=None,
    ) -> list[SystemsEntryRecord]:
        """Follow selected progression spines and unconditional same-source edges.

        Same-level catalogue siblings and historical empty choices are never
        evidence of a grant. Ambiguous roots/references are withheld.
        """
        if entry.entry_type not in {"class", "subclass"} or not 1 <= attained_level <= 20:
            return []
        current = self.get_entry_for_campaign(campaign_slug, entry.entry_key)
        if current != entry:
            return []
        groups = (self.build_class_feature_progression_for_class_entry(
                      campaign_slug, entry, include_embedded_cards=False)
                  if entry.entry_type == "class" else
                  self.build_subclass_feature_progression_for_subclass_entry(
                      campaign_slug, entry, include_embedded_cards=False))
        roots = [row.get("entry") for group in groups
                 if 1 <= int(group.get("level") or 0) <= attained_level
                 for row in list(group.get("feature_rows") or [])
                 if row.get("is_progression_spine") and row.get("deterministic_grant")]
        pending = list(reversed(roots))
        collected: list[SystemsEntryRecord] = []
        seen: set[str] = set()
        from .character_armor_models import model_member_allowed
        while pending:
            candidate = pending.pop()
            if not self._feature_is_entry(candidate) or candidate.entry_key in seen:
                continue
            if len(seen) >= 256:
                raise ValueError("Attained source feature grants exceed the supported bounds.")
            seen.add(candidate.entry_key)
            if not 1 <= self._coerce_int(candidate.metadata.get("level"), default=0) <= attained_level:
                continue
            if not model_member_allowed(candidate, selected_feature_branches):
                continue
            edges, _has_bundle = self._deterministic_feature_edges(campaign_slug, candidate,
                selected_feature_branches=selected_feature_branches)
            # Reachability proves the parent entitlement independently of any
            # choices offered inside it. Only unconditional edges are followed;
            # elective children still require their own authenticated selection.
            collected.append(candidate)
            pending.extend(reversed(edges))
        return collected


    def _build_feature_progression_groups(
        self,
        campaign_slug: str,
        *,
        matching_entries: list[SystemsEntryRecord],
        progression_rows: object,
        preferred_source_id: str = "",
        include_embedded_cards: bool = True,
    ) -> list[dict[str, object]]:
        if not matching_entries:
            return []
        if not self._feature_is_list(progression_rows):
            return []

        # Qualification consumes source identity and reachability, never cards.
        # Keep one selector for semantic and display callers so decoration
        # cannot alter which spine or unconditional children are admitted.
        optionalfeature_lookup = (self._build_optionalfeature_entry_lookup(campaign_slug)
                                  if include_embedded_cards else {})
        grouped_entries: dict[int, list[SystemsEntryRecord]] = defaultdict(list)
        for candidate in matching_entries:
            grouped_entries[self._coerce_int(candidate.metadata.get("level"), default=0)].append(candidate)

        rows: list[dict[str, object]] = []
        rendered_levels: set[int] = set()
        for group in progression_rows:
            if not self._feature_is_map(group):
                continue
            level_label = str(group.get("name", "") or "").strip()
            level = self._extract_level_from_progression_label(level_label)
            if level > 0:
                rendered_levels.add(level)
            entries_for_level = sorted(
                grouped_entries.get(level, []),
                key=lambda item: (
                    item.title.lower(),
                    item.source_id,
                    item.id,
                ),
            )
            unmatched_entries = list(entries_for_level)
            feature_rows: list[dict[str, object]] = []
            raw_labels = group.get("entries")
            if self._feature_is_list(raw_labels):
                for raw_label in raw_labels:
                    label = str(raw_label or "").strip()
                    if not label:
                        continue
                    matched_entry = self._pop_matching_class_feature_entry(unmatched_entries, label)
                    spine_matches = [candidate for candidate in entries_for_level
                                     if normalize_lookup(candidate.title) == self._normalize_class_feature_progression_label(label)
                                     and candidate.source_id.casefold() == preferred_source_id.casefold()]
                    feature_rows.append(
                        {
                            "label": label,
                            "entry": matched_entry,
                            "is_progression_spine": len(spine_matches) == 1 and matched_entry == spine_matches[0],
                            "embedded_card": self._build_embedded_feature_card(
                                campaign_slug,
                                self._feature_public_entry(matched_entry),
                                optionalfeature_lookup=optionalfeature_lookup,
                            )
                            if include_embedded_cards and matched_entry is not None
                            else None,
                        }
                    )
            for extra_entry in unmatched_entries:
                feature_rows.append(
                    {
                        "label": extra_entry.title,
                        "entry": extra_entry,
                        "embedded_card": self._build_embedded_feature_card(
                            campaign_slug,
                            self._feature_public_entry(extra_entry),
                            optionalfeature_lookup=optionalfeature_lookup,
                        ) if include_embedded_cards else None,
                    }
                )
            if not feature_rows:
                continue
            rows.append({"level": level, "level_label": level_label or f"Level {level}", "feature_rows": feature_rows})
        for level in sorted(level_key for level_key in grouped_entries if level_key > 0 and level_key not in rendered_levels):
            extra_entries = sorted(
                grouped_entries.get(level, []),
                key=lambda item: (
                    item.title.lower(),
                    item.source_id,
                    item.id,
                ),
            )
            if not extra_entries:
                continue
            rows.append(
                {
                    "level": level,
                    "level_label": f"Level {level}",
                    "feature_rows": [
                        {
                            "label": extra_entry.title,
                            "entry": extra_entry,
                            "embedded_card": self._build_embedded_feature_card(
                                campaign_slug,
                                self._feature_public_entry(extra_entry),
                                optionalfeature_lookup=optionalfeature_lookup,
                            ) if include_embedded_cards else None,
                        }
                        for extra_entry in extra_entries
                    ],
                }
            )
        # Catalogue siblings remain display rows. Only the selected, unambiguous
        # progression spine and its unconditional edges establish grant ownership.
        all_rows = [row for group in rows for row in list(group.get("feature_rows") or [])]
        pending = [row.get("entry") for row in all_rows if row.get("is_progression_spine")]
        reachable: set[str] = set()
        from .character_armor_models import model_member_allowed
        while pending:
            candidate = pending.pop()
            if not self._feature_is_entry(candidate) or candidate.entry_key in reachable:
                continue
            if not model_member_allowed(candidate):
                continue  # Display alternatives are not unconditional grants.
            if len(reachable) >= 256:
                raise ValueError("Source progression grants exceed the supported bounds.")
            reachable.add(candidate.entry_key)
            edges, _has_bundle = self._deterministic_feature_edges(campaign_slug, candidate)
            pending.extend(edges)
        for row in all_rows:
            candidate = row.get("entry")
            row["deterministic_grant"] = self._feature_is_entry(candidate) and candidate.entry_key in reachable
            row.setdefault("is_progression_spine", False)
            row["has_bundled_grants"] = (self._deterministic_feature_edges(campaign_slug, candidate)[1]
                                         if self._feature_is_entry(candidate) else False)
        return rows


    def _build_embedded_feature_card(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object]:
        campaign_option = dict(entry.metadata.get("campaign_option") or {})
        if not campaign_option:
            from .character_feature_composition import replacement_option
            campaign_option = replacement_option(entry.metadata) or {}
        base_rule_refs = self.build_base_rule_refs_for_campaign_option(campaign_slug, campaign_option)
        overlay_support = self.build_overlay_support_for_campaign_option(
            campaign_option,
            base_rule_refs=base_rule_refs,
        )
        base_rule_modification_summary = (
            dict(campaign_option.get("base_rule_modification_summary") or {})
            if isinstance(campaign_option.get("base_rule_modification_summary"), dict)
            else None
        )
        page_ref = str(entry.metadata.get("page_ref") or "").strip()
        if page_ref:
            return {
                "meta_badges": self._build_embedded_feature_badges(entry),
                "base_rule_refs": base_rule_refs,
                "overlay_support": overlay_support,
                "base_rule_modification_summary": base_rule_modification_summary,
                "body_html": self._build_campaign_page_body_html(campaign_slug, page_ref),
                "option_groups": [],
            }
        body_html, option_groups = self._render_embedded_content(
            campaign_slug,
            entry.body.get("entries"),
            heading_level=5,
            extract_option_groups=True,
            optionalfeature_lookup=optionalfeature_lookup,
            preferred_source_id=entry.source_id,
            grant_owner=entry,
        )
        return {
            "meta_badges": self._build_embedded_feature_badges(entry),
            "base_rule_refs": base_rule_refs,
            "overlay_support": overlay_support,
            "base_rule_modification_summary": base_rule_modification_summary,
            "body_html": body_html,
            "option_groups": option_groups,
        }


    def _build_embedded_optionalfeature_option(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object]:
        return {
            "label": entry.title,
            "slug": entry.slug,
            "meta_badges": self._build_embedded_feature_badges(entry),
            "body_html": self._render_embedded_content(
                campaign_slug,
                entry.body.get("entries"),
                heading_level=6,
                extract_option_groups=False,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=entry.source_id,
            )[0],
        }


    def _build_embedded_option_group(
        self,
        campaign_slug: str,
        value: dict[str, object],
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> dict[str, object]:
        count = self._coerce_int(value.get("count"), default=1)
        options: list[dict[str, object]] = []
        raw_entries = value.get("entries")
        if isinstance(raw_entries, list):
            for raw_option in raw_entries:
                resolved_entry = self._resolve_optionalfeature_entry(
                    raw_option,
                    optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                )
                label = self._format_feature_reference(raw_option)
                if resolved_entry is None:
                    if not label:
                        label = self._clean_embedded_text(str(raw_option or ""))
                    options.append(
                        {
                            "label": label,
                            "slug": None,
                            "meta_badges": [],
                            "body_html": "",
                        }
                    )
                    continue
                options.append(
                    self._build_embedded_optionalfeature_option(
                        campaign_slug,
                        resolved_entry,
                        optionalfeature_lookup=optionalfeature_lookup,
                    )
                )

        return {
            "summary_label": f"Choose {count} option{'s' if count != 1 else ''}",
            "options": options,
        }


    def _render_embedded_content(
        self,
        campaign_slug: str,
        value: object,
        *,
        heading_level: int,
        extract_option_groups: bool,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
        grant_owner: SystemsEntryRecord | None = None,
    ) -> tuple[str, list[dict[str, object]]]:
        if value is None:
            return "", []
        if isinstance(value, str):
            text = self._clean_embedded_text(value)
            return (f"<p>{escape(text)}</p>" if text else ""), []
        if isinstance(value, (int, float)):
            return f"<p>{escape(str(value))}</p>", []
        if isinstance(value, list):
            html_parts: list[str] = []
            option_groups: list[dict[str, object]] = []
            for item in value:
                rendered_html, nested_option_groups = self._render_embedded_content(
                    campaign_slug,
                    item,
                    heading_level=heading_level,
                    extract_option_groups=extract_option_groups,
                    optionalfeature_lookup=optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                    grant_owner=grant_owner,
                )
                if rendered_html:
                    html_parts.append(rendered_html)
                option_groups.extend(nested_option_groups)
            return "\n".join(html_parts), option_groups
        if isinstance(value, dict):
            value_type = str(value.get("type", "") or "").strip().lower()
            if self._looks_like_ability_block(value):
                return self._render_embedded_ability_scores(value), []
            if value_type == "list":
                items = value.get("items")
                if not isinstance(items, list):
                    return "", []
                list_items: list[str] = []
                option_groups: list[dict[str, object]] = []
                for item in items:
                    rendered_item, nested_option_groups = self._render_embedded_list_item(
                        campaign_slug,
                        item,
                        heading_level=heading_level,
                        extract_option_groups=extract_option_groups,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                        grant_owner=grant_owner,
                    )
                    if rendered_item:
                        list_items.append(rendered_item)
                    option_groups.extend(nested_option_groups)
                if not list_items:
                    return "", option_groups
                return "<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>", option_groups
            if value_type == "options":
                if self._deterministic_feature_bundle_entries(
                    campaign_slug, value, preferred_source_id=preferred_source_id,
                    preferred_library_slug=grant_owner.library_slug if grant_owner is not None else None,
                    owner_entry=grant_owner,
                ) is not None:
                    return self._render_embedded_option_list(
                        campaign_slug, value, heading_level=heading_level,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    )
                if extract_option_groups:
                    option_group = self._build_embedded_option_group(
                        campaign_slug,
                        value,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    )
                    return "", ([option_group] if option_group["options"] else [])
                return self._render_embedded_option_list(
                    campaign_slug,
                    value,
                    heading_level=heading_level,
                    optionalfeature_lookup=optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                )
            if value_type == "table":
                return self._render_embedded_table(value), []
            if value_type in {"abilitydc", "abilityattackmod"}:
                return self._render_embedded_ability_formula(value), []
            if value_type in {"refclassfeature", "refoptionalfeature", "refsubclassfeature"}:
                return (
                    self._render_embedded_reference(
                        campaign_slug,
                        value,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    ),
                    [],
                )

            name = self._clean_embedded_text(str(value.get("name", "") or ""))
            entries = value.get("entries")
            entry_value = entries if entries is not None else value.get("entry")
            rendered_entries, option_groups = self._render_embedded_content(
                campaign_slug,
                entry_value,
                heading_level=min(heading_level + 1, 6),
                extract_option_groups=extract_option_groups,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
                grant_owner=grant_owner,
            )
            if name and rendered_entries:
                heading_tag = f"h{heading_level}"
                return f"<section><{heading_tag}>{escape(name)}</{heading_tag}>{rendered_entries}</section>", option_groups
            if name:
                return f"<p><strong>{escape(name)}.</strong></p>", option_groups
            return rendered_entries, option_groups
        text = self._clean_embedded_text(str(value or ""))
        return (f"<p>{escape(text)}</p>" if text else ""), []


    def _render_embedded_list_item(
        self,
        campaign_slug: str,
        item: object,
        *,
        heading_level: int,
        extract_option_groups: bool,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
        grant_owner: SystemsEntryRecord | None = None,
    ) -> tuple[str, list[dict[str, object]]]:
        if isinstance(item, dict) and str(item.get("type", "") or "").strip().lower() == "item":
            name = self._clean_embedded_text(str(item.get("name", "") or ""))
            entry_value = item.get("entry", item.get("entries"))
            entry_text, option_groups = self._render_embedded_content(
                campaign_slug,
                entry_value,
                heading_level=heading_level,
                extract_option_groups=extract_option_groups,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
                grant_owner=grant_owner,
            )
            stripped_entry_text = self._strip_outer_paragraph(entry_text)
            if name and stripped_entry_text:
                return f"<strong>{escape(name)}</strong> {stripped_entry_text}", option_groups
            if name:
                return f"<strong>{escape(name)}</strong>", option_groups
            return stripped_entry_text, option_groups
        rendered_html, option_groups = self._render_embedded_content(
            campaign_slug,
            item,
            heading_level=heading_level,
            extract_option_groups=extract_option_groups,
            optionalfeature_lookup=optionalfeature_lookup,
            preferred_source_id=preferred_source_id,
            grant_owner=grant_owner,
        )
        return self._strip_outer_paragraph(rendered_html), option_groups


    def _render_embedded_option_list(
        self,
        campaign_slug: str,
        value: dict[str, object],
        *,
        heading_level: int,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> tuple[str, list[dict[str, object]]]:
        parts: list[str] = []
        count = value.get("count")
        if count not in (None, ""):
            count_text = str(count).strip()
            if count_text:
                parts.append(f"<p>Choose {escape(count_text)} option{'s' if count_text != '1' else ''}:</p>")
        option_entries = value.get("entries")
        if not isinstance(option_entries, list):
            return "".join(parts), []
        list_items: list[str] = []
        for item in option_entries:
            rendered_item, _ = self._render_embedded_list_item(
                campaign_slug,
                item,
                heading_level=heading_level,
                extract_option_groups=False,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            if rendered_item:
                list_items.append(rendered_item)
        if list_items:
            parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
        return "".join(parts), []


