import type { Dispatch, SetStateAction } from "react";

import type { CharacterBuilderOption } from "./api/types";

export type CharacterAuthoringValues = Record<string, string | string[]>;

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
