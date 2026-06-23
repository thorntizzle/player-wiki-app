import type { CombatLiveStatePayload, CombatPayload } from "./api/types";

function isCombatUnchangedPayload(payload: CombatLiveStatePayload): payload is Extract<CombatLiveStatePayload, { changed: false }> {
  return payload.changed === false;
}

export function resolveCombatLivePayload(
  previous: CombatPayload | undefined,
  liveResponse: CombatLiveStatePayload,
): CombatPayload | null {
  if (isCombatUnchangedPayload(liveResponse)) {
    return previous ?? null;
  }
  if (previous) {
    return {
      ...liveResponse,
      available_character_choices: liveResponse.available_character_choices?.length
        ? liveResponse.available_character_choices
        : previous.available_character_choices,
      available_statblock_choices: liveResponse.available_statblock_choices?.length
        ? liveResponse.available_statblock_choices
        : previous.available_statblock_choices,
      combat_condition_options: liveResponse.combat_condition_options?.length
        ? liveResponse.combat_condition_options
        : previous.combat_condition_options,
    };
  }
  return liveResponse;
}
