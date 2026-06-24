import type { Dispatch, SetStateAction } from "react";

import type {
  CharacterAdvancedEditorContext,
  CharacterBuilderOption,
  CharacterEditorChoiceField,
  CharacterEditorField,
  CharacterRecord,
  CharacterLevelUpContext,
  CharacterProgressionRepairContext,
  CharacterRetrainingContext,
  CharacterXianxiaManualImportContext,
  CharacterXianxiaManualImportRow,
} from "./api/types";
import { asRecord, readString } from "./characterValueUtils";

export type CharacterAuthoringValues = Record<string, string | string[]>;

export function characterNameFromRecord(character: CharacterRecord | undefined): string {
  return readString(asRecord(character?.definition?.profile).name, readString(character?.definition?.name, "Character"));
}

export function classLevelTextFromRecord(character: CharacterRecord | undefined): string {
  return readString(asRecord(character?.definition?.profile).class_level_text);
}

export function optionValue(option: CharacterBuilderOption): string {
  return String(option.value || option.slug || option.entry_key || option.key || "");
}

export function optionLabel(option: CharacterBuilderOption): string {
  const value = optionValue(option);
  const label = option.label || option.title || option.name || value;
  return option.source_id ? `${label} (${option.source_id})` : label;
}

export function draftString(values: CharacterAuthoringValues, key: string, fallback = ""): string {
  const value = values[key];
  if (Array.isArray(value)) {
    return value[0] ?? fallback;
  }
  return value ?? fallback;
}

export function draftStringArray(values: CharacterAuthoringValues, key: string): string[] {
  const value = values[key];
  return Array.isArray(value) ? value : value ? [value] : [];
}

export function updateAuthoringValue(
  setValues: Dispatch<SetStateAction<CharacterAuthoringValues>>,
  key: string,
  value: string | string[],
) {
  setValues((current) => ({ ...current, [key]: value }));
}

export function selectOptions(options: CharacterBuilderOption[]) {
  return options.map((option) => {
    const value = optionValue(option);
    return (
      <option key={value || optionLabel(option)} value={value}>
        {optionLabel(option)}
      </option>
    );
  });
}

export function editorSelectOptions(options: CharacterBuilderOption[], emptyLabel?: string) {
  return (
    <>
      {emptyLabel ? <option value="">{emptyLabel}</option> : null}
      {selectOptions(options)}
    </>
  );
}

export function editorValuesFromContext(context: CharacterAdvancedEditorContext | null | undefined): Record<string, string> {
  const values: Record<string, string> = {};
  if (!context) {
    return values;
  }
  const copyField = (field: CharacterEditorField | CharacterEditorChoiceField) => {
    if (field.name) {
      values[field.name] = String(("options" in field ? field.selected : field.value) ?? "");
    }
  };
  context.proficiency_fields?.forEach(copyField);
  context.reference_fields?.forEach(copyField);
  context.stat_adjustment_fields?.forEach(copyField);
  context.recoverable_penalty_rows?.forEach((row) => {
    values[`recoverable_penalty_id_${row.index}`] = row.id ?? "";
    values[`recoverable_penalty_source_${row.index}`] = row.source ?? "";
    values[`recoverable_penalty_target_${row.index}`] = row.target ?? "";
    values[`recoverable_penalty_amount_${row.index}`] = row.amount ?? "";
    values[`recoverable_penalty_notes_${row.index}`] = row.notes ?? "";
  });
  context.feature_rows?.forEach((row) => {
    values[`custom_feature_id_${row.index}`] = row.id ?? "";
    values[`custom_feature_name_${row.index}`] = row.name ?? "";
    values[`custom_feature_page_ref_${row.index}`] = row.page_ref ?? "";
    values[`custom_feature_activation_type_${row.index}`] = row.activation_type ?? "";
    values[`custom_feature_description_${row.index}`] = row.description_markdown ?? "";
    values[`custom_feature_resource_max_${row.index}`] = row.resource_max ?? "";
    values[`custom_feature_resource_reset_on_${row.index}`] = row.resource_reset_on ?? "";
    row.choice_fields?.forEach(copyField);
  });
  context.equipment_rows?.forEach((row) => {
    values[`manual_item_id_${row.index}`] = row.id ?? "";
    values[`manual_item_name_${row.index}`] = row.name ?? "";
    values[`manual_item_page_ref_${row.index}`] = row.page_ref ?? "";
    values[`manual_item_quantity_${row.index}`] = row.quantity ?? "";
    values[`manual_item_weight_${row.index}`] = row.weight ?? "";
    values[`manual_item_notes_${row.index}`] = row.notes ?? "";
  });
  return values;
}

export function characterLevelUpValuesFromContext(context: CharacterLevelUpContext | null | undefined): CharacterAuthoringValues {
  const values: CharacterAuthoringValues = { ...(context?.values ?? {}) };
  if (!context) {
    return values;
  }
  values.advancement_mode = draftString(values, "advancement_mode", context.advancement_mode || "advance_existing");
  values.target_class_row_id = draftString(values, "target_class_row_id", context.target_class_row_id || "");
  values.new_class_slug = draftString(values, "new_class_slug");
  values.new_subclass_slug = draftString(values, "new_subclass_slug");
  values.subclass_slug = draftString(values, "subclass_slug");
  values.hp_gain = draftString(values, "hp_gain");
  context.choice_sections?.forEach((section) => {
    section.fields?.forEach((field) => {
      if (field.name && values[field.name] === undefined) {
        values[field.name] = field.selected ?? "";
      }
    });
  });
  return values;
}

export function characterAuthoringStringValues(values: CharacterAuthoringValues): Record<string, string> {
  const payload: Record<string, string> = {};
  Object.entries(values).forEach(([key, value]) => {
    payload[key] = Array.isArray(value) ? String(value[0] ?? "") : String(value ?? "");
  });
  return payload;
}

export function characterProgressionRepairValuesFromContext(
  context: CharacterProgressionRepairContext | null | undefined,
): CharacterAuthoringValues {
  const values: CharacterAuthoringValues = { ...(context?.values ?? {}) };
  context?.class_rows?.forEach((row) => {
    if (row.class_field_name && values[row.class_field_name] === undefined) {
      values[row.class_field_name] = row.class_selected ?? "";
    }
    if (row.subclass_field_name && values[row.subclass_field_name] === undefined) {
      values[row.subclass_field_name] = row.subclass_selected ?? "";
    }
  });
  context?.feat_rows?.forEach((row) => {
    if (row.name && values[row.name] === undefined) {
      values[row.name] = row.selected ?? "";
    }
  });
  context?.optionalfeature_rows?.forEach((row) => {
    if (row.name && values[row.name] === undefined) {
      values[row.name] = row.selected ?? "";
    }
  });
  context?.spell_rows?.forEach((row) => {
    if (row.class_row_field_name && values[row.class_row_field_name] === undefined) {
      values[row.class_row_field_name] = row.class_row_selected ?? "";
    }
    if (row.field_name && values[row.field_name] === undefined) {
      values[row.field_name] = row.selected ?? "";
    }
  });
  return values;
}

export function characterRetrainingValuesFromContext(context: CharacterRetrainingContext | null | undefined): CharacterAuthoringValues {
  const values: CharacterAuthoringValues = { ...(context?.values ?? {}) };
  context?.feature_rows?.forEach((row) => {
    row.choice_fields?.forEach((field) => {
      if (field.name && values[field.name] === undefined) {
        values[field.name] = field.selected ?? "";
      }
    });
  });
  return values;
}

export function manualImportRows(
  context: CharacterXianxiaManualImportContext | undefined,
  rowCount: number,
  values: CharacterAuthoringValues,
): CharacterXianxiaManualImportRow[] {
  const baseRows = context?.martial_art_rows ?? [];
  const maxRows = Math.max(rowCount, baseRows.length, 3);
  return Array.from({ length: maxRows }, (_, offset) => {
    const index = offset + 1;
    const existing = baseRows.find((row) => row.index === index);
    return {
      index,
      slug_input_name: `martial_art_${index}_slug`,
      name_input_name: `martial_art_${index}_name`,
      rank_input_name: `martial_art_${index}_rank`,
      teacher_input_name: `martial_art_${index}_teacher`,
      breakthrough_input_name: `martial_art_${index}_breakthrough`,
      notes_input_name: `martial_art_${index}_notes`,
      selected_slug: draftString(values, `martial_art_${index}_slug`, existing?.selected_slug || ""),
      name: draftString(values, `martial_art_${index}_name`, existing?.name || ""),
      rank: draftString(values, `martial_art_${index}_rank`, existing?.rank || ""),
      teacher: draftString(values, `martial_art_${index}_teacher`, existing?.teacher || ""),
      breakthrough: draftString(values, `martial_art_${index}_breakthrough`, existing?.breakthrough || ""),
      notes: draftString(values, `martial_art_${index}_notes`, existing?.notes || ""),
    };
  });
}
