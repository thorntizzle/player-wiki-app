from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, render_template, request, url_for

from .auth import campaign_scope_access_required
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError
from .system_policy import CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION
from .xianxia_character_model import XIANXIA_ATTRIBUTE_KEYS, XIANXIA_EFFORT_KEYS


@dataclass(frozen=True)
class CharacterXianxiaCultivationRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    get_systems_service: Callable[..., object]
    list_visible_character_page_records: Callable[..., list[object]]
    parse_expected_revision: Callable[..., int]
    finalize_character_definition_for_write: Callable[..., object]
    can_manage_campaign_session: Callable[..., bool]
    character_advancement_lane: Callable[..., str]
    is_xianxia_system: Callable[..., bool]
    get_current_user: Callable[..., object]
    normalize_dm_player_wiki_int: Callable[..., int]
    update_xianxia_insight_definition: Callable[..., object]
    update_xianxia_gathering_insight_definition: Callable[..., object]
    spend_xianxia_cultivation_energy_definition: Callable[..., object]
    spend_xianxia_meditation_definition: Callable[..., object]
    spend_xianxia_conditioning_definition: Callable[..., object]
    spend_xianxia_training_definition: Callable[..., object]
    advance_xianxia_martial_art_rank_definition: Callable[..., object]
    learn_xianxia_generic_technique_definition: Callable[..., object]
    start_xianxia_realm_ascension_review_definition: Callable[..., object]
    reset_xianxia_realm_ascension_stats_definition: Callable[..., object]
    apply_xianxia_immortal_realm_rebuild_definition: Callable[..., object]
    apply_xianxia_divine_realm_rebuild_definition: Callable[..., object]
    confirm_xianxia_realm_ascension_definition: Callable[..., object]
    build_managed_character_import_metadata: Callable[..., object]
    merge_state_with_definition: Callable[..., dict[str, object]]
    load_campaign_character_config: Callable[..., object]
    write_yaml: Callable[..., None]
    present_character_detail: Callable[..., dict[str, object]]
    list_xianxia_generic_technique_learning_options: Callable[..., list[dict[str, object]]]
    build_character_entry_href: Callable[..., str | None]
    present_xianxia_cultivation_context: Callable[..., dict[str, object]]
    character_state_store: object


def register_character_xianxia_cultivation_route(
    app: Any,
    *,
    dependencies: CharacterXianxiaCultivationRouteDependencies,
) -> None:
    def character_xianxia_cultivation_view(
        campaign_slug: str, character_slug: str
    ):
        if not dependencies.can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if (
            dependencies.character_advancement_lane(
                getattr(campaign, "system", "")
            )
            != CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION
            or not dependencies.is_xianxia_system(
                getattr(record.definition, "system", "")
            )
        ):
            flash(
                "Cultivation is only available for Xianxia character sheets.",
                "error",
            )
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )

        if request.method == "POST":
            user = dependencies.get_current_user()
            if user is None:
                abort(403)

            redirect_anchor = "xianxia-cultivation-insight"
            try:
                expected_revision = dependencies.parse_expected_revision()
                cultivation_action = str(
                    request.form.get("cultivation_action") or "save_insight"
                ).strip()
                if cultivation_action == "save_insight":
                    insight_available = dependencies.normalize_dm_player_wiki_int(
                        request.form.get("insight_available", ""),
                        field_label="Insight available",
                    )
                    insight_spent = dependencies.normalize_dm_player_wiki_int(
                        request.form.get("insight_spent", ""),
                        field_label="Insight spent",
                    )
                    definition = dependencies.update_xianxia_insight_definition(
                        record.definition,
                        available=insight_available,
                        spent=insight_spent,
                    )
                    success_message = "Insight counters saved."
                elif cultivation_action == "record_gathering_insight":
                    redirect_anchor = "xianxia-cultivation-gathering-insight"
                    insight_gain = dependencies.normalize_dm_player_wiki_int(
                        request.form.get("insight_gain_amount", ""),
                        field_label="Gathered Insight",
                    )
                    definition = (
                        dependencies.update_xianxia_gathering_insight_definition(
                            record.definition,
                            amount=insight_gain,
                            downtime=request.form.get(
                                "gathering_insight_downtime", ""
                            ),
                            notes=request.form.get("gathering_insight_notes", ""),
                        )
                    )
                    success_message = "Gathering Insight recorded."
                elif cultivation_action == "spend_cultivation_energy":
                    redirect_anchor = "xianxia-cultivation-energy"
                    energy_result = (
                        dependencies.spend_xianxia_cultivation_energy_definition(
                            record.definition,
                            energy_key=request.form.get("energy_key", ""),
                            notes=request.form.get(
                                "cultivation_energy_notes", ""
                            ),
                        )
                    )
                    definition = energy_result.definition
                    success_message = (
                        f"Spent {energy_result.insight_cost} Insight on Cultivation "
                        f"to increase {energy_result.energy_name}."
                    )
                elif cultivation_action == "spend_meditation_yin_yang":
                    redirect_anchor = "xianxia-cultivation-meditation"
                    meditation_result = (
                        dependencies.spend_xianxia_meditation_definition(
                            record.definition,
                            yin_yang_key=request.form.get("yin_yang_key", ""),
                            notes=request.form.get("meditation_notes", ""),
                        )
                    )
                    definition = meditation_result.definition
                    success_message = (
                        f"Spent {meditation_result.insight_cost} Insight on Meditation "
                        f"to increase {meditation_result.yin_yang_name}."
                    )
                elif cultivation_action == "spend_conditioning":
                    redirect_anchor = "xianxia-cultivation-conditioning"
                    conditioning_result = (
                        dependencies.spend_xianxia_conditioning_definition(
                            record.definition,
                            conditioning_target=request.form.get(
                                "conditioning_target", ""
                            ),
                            effort_key=request.form.get("effort_key", ""),
                            notes=request.form.get("conditioning_notes", ""),
                        )
                    )
                    definition = conditioning_result.definition
                    success_message = (
                        f"Spent {conditioning_result.insight_cost} Insight on Conditioning "
                        f"to increase {conditioning_result.target_name}."
                    )
                elif cultivation_action == "spend_training":
                    redirect_anchor = "xianxia-cultivation-training"
                    training_result = dependencies.spend_xianxia_training_definition(
                        record.definition,
                        training_target=request.form.get("training_target", ""),
                        attribute_key=request.form.get("attribute_key", ""),
                        notes=request.form.get("training_notes", ""),
                    )
                    definition = training_result.definition
                    success_message = (
                        f"Spent {training_result.insight_cost} Insight on Training "
                        f"to increase {training_result.target_name}."
                    )
                elif cultivation_action == "advance_martial_art_rank":
                    redirect_anchor = "xianxia-cultivation-martial-arts"
                    raw_martial_art_index = request.form.get(
                        "martial_art_index", ""
                    )
                    if not str(raw_martial_art_index or "").strip():
                        raise ValueError("Martial Art selection is required.")
                    martial_art_index = dependencies.normalize_dm_player_wiki_int(
                        raw_martial_art_index,
                        field_label="Martial Art selection",
                    )
                    rank_result = (
                        dependencies.advance_xianxia_martial_art_rank_definition(
                            record.definition,
                            campaign_slug=campaign_slug,
                            systems_service=dependencies.get_systems_service(),
                            martial_art_index=martial_art_index,
                            target_rank_key=request.form.get(
                                "target_rank_key", ""
                            ),
                            legendary_quest_note=request.form.get(
                                "legendary_quest_note",
                                "",
                            ),
                        )
                    )
                    definition = rank_result.definition
                    success_message = (
                        f"Spent {rank_result.insight_cost} Insight to advance "
                        f"{rank_result.martial_art_name} to {rank_result.rank_name}."
                    )
                elif cultivation_action == "learn_generic_technique":
                    redirect_anchor = "xianxia-cultivation-techniques"
                    technique_result = (
                        dependencies.learn_xianxia_generic_technique_definition(
                            record.definition,
                            campaign_slug=campaign_slug,
                            systems_service=dependencies.get_systems_service(),
                            generic_technique_entry_key=request.form.get(
                                "generic_technique_entry_key",
                                "",
                            ),
                            notes=request.form.get(
                                "generic_technique_notes", ""
                            ),
                        )
                    )
                    definition = technique_result.definition
                    success_message = (
                        f"Spent {technique_result.insight_cost} Insight to learn "
                        f"{technique_result.technique_name}."
                    )
                elif cultivation_action == "start_realm_ascension_review":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    realm_result = (
                        dependencies.start_xianxia_realm_ascension_review_definition(
                            record.definition,
                            target_realm=request.form.get("target_realm", ""),
                            gm_review_note=request.form.get(
                                "realm_ascension_gm_review_note", ""
                            ),
                            seclusion_notes=request.form.get(
                                "realm_ascension_seclusion_notes", ""
                            ),
                            hp_stance_trade_notes=request.form.get(
                                "realm_ascension_hp_stance_trade_notes",
                                "",
                            ),
                        )
                    )
                    definition = realm_result.definition
                    success_message = (
                        f"Started Realm ascension review from {realm_result.current_realm} "
                        f"to {realm_result.target_realm}."
                    )
                elif cultivation_action == "reset_realm_ascension_stats":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    reset_result = (
                        dependencies.reset_xianxia_realm_ascension_stats_definition(
                            record.definition,
                            target_realm=request.form.get("target_realm", ""),
                            notes=request.form.get(
                                "realm_ascension_reset_notes", ""
                            ),
                        )
                    )
                    definition = reset_result.definition
                    success_message = (
                        f"Reset Attributes and Efforts for {reset_result.current_realm} "
                        f"to {reset_result.target_realm} Realm ascension."
                    )
                elif cultivation_action == "apply_immortal_realm_rebuild":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    rebuild_result = (
                        dependencies.apply_xianxia_immortal_realm_rebuild_definition(
                            record.definition,
                            target_realm=request.form.get("target_realm", ""),
                            attribute_scores={
                                key: request.form.get(
                                    f"realm_rebuild_attribute_{key}", ""
                                )
                                for key in XIANXIA_ATTRIBUTE_KEYS
                            },
                            effort_scores={
                                key: request.form.get(
                                    f"realm_rebuild_effort_{key}", ""
                                )
                                for key in XIANXIA_EFFORT_KEYS
                            },
                            hp_maximum_trade=request.form.get(
                                "realm_ascension_trade_hp", ""
                            ),
                            stance_maximum_trade=request.form.get(
                                "realm_ascension_trade_stance",
                                "",
                            ),
                            notes=request.form.get(
                                "realm_ascension_rebuild_notes", ""
                            ),
                        )
                    )
                    definition = rebuild_result.definition
                    success_message = (
                        f"Applied the Immortal rebuild budget for "
                        f"{rebuild_result.total_rebuild_points} points and "
                        f"{rebuild_result.actions_per_turn} actions."
                    )
                elif cultivation_action == "apply_divine_realm_rebuild":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    rebuild_result = (
                        dependencies.apply_xianxia_divine_realm_rebuild_definition(
                            record.definition,
                            target_realm=request.form.get("target_realm", ""),
                            attribute_scores={
                                key: request.form.get(
                                    f"realm_rebuild_attribute_{key}", ""
                                )
                                for key in XIANXIA_ATTRIBUTE_KEYS
                            },
                            effort_scores={
                                key: request.form.get(
                                    f"realm_rebuild_effort_{key}", ""
                                )
                                for key in XIANXIA_EFFORT_KEYS
                            },
                            hp_maximum_trade=request.form.get(
                                "realm_ascension_trade_hp", ""
                            ),
                            stance_maximum_trade=request.form.get(
                                "realm_ascension_trade_stance",
                                "",
                            ),
                            notes=request.form.get(
                                "realm_ascension_rebuild_notes", ""
                            ),
                        )
                    )
                    definition = rebuild_result.definition
                    success_message = (
                        f"Applied the Divine rebuild budget for "
                        f"{rebuild_result.total_rebuild_points} points and "
                        f"{rebuild_result.actions_per_turn} actions."
                    )
                elif cultivation_action == "confirm_realm_ascension":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    confirmation_result = (
                        dependencies.confirm_xianxia_realm_ascension_definition(
                            record.definition,
                            target_realm=request.form.get("target_realm", ""),
                            gm_confirmation_note=request.form.get(
                                "realm_ascension_gm_confirmation_note",
                                "",
                            ),
                        )
                    )
                    definition = confirmation_result.definition
                    success_message = (
                        f"Recorded GM confirmation for the "
                        f"{confirmation_result.target_realm} Realm ascension."
                    )
                else:
                    raise ValueError(
                        "Unsupported cultivation action. Refresh the page and try again."
                    )
                definition = (
                    dependencies.finalize_character_definition_for_write(
                        campaign_slug,
                        definition,
                        campaign=campaign,
                    )
                )
                import_metadata = (
                    dependencies.build_managed_character_import_metadata(
                        campaign_slug,
                        record.definition.character_slug,
                        record.import_metadata,
                    )
                )
                merged_state = dependencies.merge_state_with_definition(
                    definition,
                    record.state_record.state,
                )
                dependencies.character_state_store.replace_state(
                    definition,
                    merged_state,
                    expected_revision=expected_revision,
                    updated_by_user_id=user.id,
                )
                config = dependencies.load_campaign_character_config(
                    current_app.config["CAMPAIGNS_DIR"], campaign_slug
                )
                character_dir = config.characters_dir / character_slug
                dependencies.write_yaml(
                    character_dir / "definition.yaml", definition.to_dict()
                )
                dependencies.write_yaml(
                    character_dir / "import.yaml", import_metadata.to_dict()
                )
            except CharacterStateConflictError:
                flash(
                    "This sheet changed in another session. Refresh the page and try again.",
                    "error",
                )
            except (CharacterStateValidationError, ValueError) as exc:
                flash(str(exc), "error")
            else:
                flash(success_message, "success")

            return redirect(
                url_for(
                    "character_xianxia_cultivation_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                    _anchor=redirect_anchor,
                )
            )

        character = dependencies.present_character_detail(
            campaign,
            record,
            include_player_notes_section=True,
            systems_service=dependencies.get_systems_service(),
            campaign_page_records=(
                dependencies.list_visible_character_page_records(
                    campaign_slug, campaign
                )
            ),
        )
        xianxia_read = character.get("xianxia_read")
        if not isinstance(xianxia_read, dict):
            abort(404)
        generic_technique_options = []
        for option in dependencies.list_xianxia_generic_technique_learning_options(
            record.definition,
            campaign_slug=campaign_slug,
            systems_service=dependencies.get_systems_service(),
        ):
            systems_ref = dict(option.get("systems_ref") or {})
            generic_technique_options.append(
                {
                    **option,
                    "href": dependencies.build_character_entry_href(
                        campaign_slug,
                        systems_ref=systems_ref,
                    ),
                }
            )

        return render_template(
            "character_cultivation_xianxia.html",
            campaign=campaign,
            character=character,
            cultivation=dependencies.present_xianxia_cultivation_context(
                character,
                record.definition.xianxia,
                generic_technique_learning_options=generic_technique_options,
            ),
            active_nav="characters",
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/cultivation",
        endpoint="character_xianxia_cultivation_view",
        view_func=campaign_scope_access_required("characters")(
            character_xianxia_cultivation_view
        ),
        methods=("GET", "POST"),
    )
