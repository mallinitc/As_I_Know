import type { ImprovedChangeDraft } from "@/types/api";

const UNKNOWN = "[Not provided - enter a verified value]";

const sections: { key: keyof ImprovedChangeDraft; label: string }[] = [
  { key: "change_title", label: "Change Title" },
  { key: "change_number", label: "Change Number" },
  { key: "business_justification", label: "Business Justification" },
  { key: "environment", label: "Environment" },
  { key: "subscription", label: "Subscription" },
  { key: "resource_group", label: "Resource Group" },
  { key: "resource_name_or_id", label: "Resource Name / ID" },
  { key: "implementer", label: "Implementer" },
  { key: "change_start", label: "Change Start" },
  { key: "change_end", label: "Change End" },
  { key: "timezone", label: "Timezone" },
  { key: "required_role", label: "Required Role" },
  { key: "required_access_scope", label: "Required Access Scope" },
  { key: "implementation_steps", label: "Implementation Steps" },
  { key: "validation_plan", label: "Validation Plan" },
  { key: "rollback_plan", label: "Rollback Plan" },
  { key: "expected_outcome", label: "Expected Outcome" },
  { key: "risk_and_impact", label: "Risk and Impact" },
];

export function formatCompleteChangeDescription(draft: ImprovedChangeDraft): string {
  return sections.map(({ key, label }) => {
    const value = draft[key];
    const rendered = Array.isArray(value)
      ? (value.length ? value.map((item, index) => `${index + 1}. ${item}`).join("\n") : UNKNOWN)
      : (value.trim() || UNKNOWN);
    return `${label.toUpperCase()}\n${rendered}`;
  }).join("\n\n");
}

export function updateDraftField(draft: ImprovedChangeDraft, key: keyof ImprovedChangeDraft, value: string): ImprovedChangeDraft {
  return {
    ...draft,
    [key]: Array.isArray(draft[key])
      ? value.split("\n").map((item) => item.trim()).filter(Boolean)
      : value,
  };
}

export { UNKNOWN as UNKNOWN_DRAFT_VALUE };
