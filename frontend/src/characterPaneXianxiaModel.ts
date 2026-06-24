import type { CharacterPresentedXianxia } from "./api/types";
import { asRecord, asRecordArray, asStringArray, readString } from "./characterValueUtils";
import { joinDisplay } from "./characterPaneUtils";

export function buildCharacterPaneXianxiaModel(presentedXianxia: CharacterPresentedXianxia) {
  const skillUseGuardrails = asRecord(presentedXianxia.quick_reference?.skill_use_guardrails);
  const skillUseGuardrailRuleHref = readString(skillUseGuardrails.rule_href);
  const skillUseGuardrailRuleTitle = readString(skillUseGuardrails.rule_title, "Skills");
  const skillUseGuardrailReferenceLines = asStringArray(skillUseGuardrails.reference_lines);
  const hasSkillUseGuardrail = Boolean(skillUseGuardrailRuleHref) || skillUseGuardrailReferenceLines.length > 0;

  const honorInteractions = asRecord(presentedXianxia.quick_reference?.honor_interactions);
  const honorContexts = asRecordArray(honorInteractions.contexts);
  const honorReferenceLines = asStringArray(honorInteractions.reference_lines);
  const hasHonorInteractions = Boolean(
    honorContexts.length ||
      honorReferenceLines.length ||
      readString(honorInteractions.summary) ||
      readString(honorInteractions.rule_href) ||
      readString(honorInteractions.status_label) ||
      readString(honorInteractions.status) ||
      readString(honorInteractions.support) ||
      readString(honorInteractions.support_label),
  );

  const stanceBreak = asRecord(presentedXianxia.quick_reference?.stance_break);
  const stanceBreakReferenceLines = asStringArray(stanceBreak.reference_lines);
  const stanceBreakRecoveryLines = asStringArray(stanceBreak.recovery_lines);
  const hasStanceBreak = Boolean(
    stanceBreakReferenceLines.length ||
      stanceBreakRecoveryLines.length ||
      readString(stanceBreak.status_label) ||
      readString(stanceBreak.status) ||
      readString(stanceBreak.rule_href),
  );

  return {
    activeStateStatus: joinDisplay([
      readString(presentedXianxia.active_state?.stance?.status_label),
      readString(presentedXianxia.active_state?.aura?.status_label),
    ]),
    actionReference: asRecord(presentedXianxia.quick_reference?.actions),
    currency: presentedXianxia.inventory?.currency ?? [],
    dao: presentedXianxia.resources?.dao,
    defenseReference: asRecord(presentedXianxia.quick_reference?.defense),
    durability: presentedXianxia.resources?.durability ?? [],
    energies: presentedXianxia.resources?.energies ?? [],
    hasHonorInteractions,
    hasSkillUseGuardrail,
    hasStanceBreak,
    honorContexts,
    honorInteractions,
    honorReferenceLines,
    insight: presentedXianxia.resources?.insight,
    inventory: presentedXianxia.inventory?.quantities ?? [],
    ruleTextReferences: asRecordArray(presentedXianxia.quick_reference?.rule_text_references),
    skillUseGuardrailReferenceLines,
    skillUseGuardrailRuleHref,
    skillUseGuardrailRuleTitle,
    stanceBreak,
    stanceBreakRecoveryLines,
    stanceBreakReferenceLines,
    yinYang: presentedXianxia.resources?.yin_yang ?? [],
  };
}
