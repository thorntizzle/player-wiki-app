import React from "react";

import type { CharacterDndChoiceField } from "../api/types";
import { draftString, selectOptions, type CharacterAuthoringValues } from "../characterAuthoringUtils";

export function CharacterDndChoiceSelect({
  field,
  draftValues,
  setDraftValues,
  refreshContext,
}: {
  field: CharacterDndChoiceField;
  draftValues: CharacterAuthoringValues;
  setDraftValues: React.Dispatch<React.SetStateAction<CharacterAuthoringValues>>;
  refreshContext: (values?: CharacterAuthoringValues) => void;
}) {
  const value = draftString(draftValues, field.name, field.selected || "");
  return (
    <label className="field">
      <span>{field.label}</span>
      <select
        name={field.name}
        value={value}
        onChange={(event) => {
          const nextValues = { ...draftValues, [field.name]: event.currentTarget.value };
          setDraftValues(nextValues);
          refreshContext(nextValues);
        }}
      >
        <option value="">Choose an option</option>
        {selectOptions(field.options ?? [])}
      </select>
      {field.help_text ? <small>{field.help_text}</small> : null}
    </label>
  );
}
