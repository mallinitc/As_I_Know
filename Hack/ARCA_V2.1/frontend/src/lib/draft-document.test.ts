import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatCompleteChangeDescription, updateDraftField, UNKNOWN_DRAFT_VALUE } from "./draft-document.ts";
import type { ImprovedChangeDraft } from "@/types/api";

const draft: ImprovedChangeDraft = {
  change_title: "Rotate warehouse credentials", change_number: "CHG-SF-1007", business_justification: "Reduce credential risk",
  environment: "production", subscription: "", resource_group: "", resource_name_or_id: "ACME_DB.SECURITY.CREDENTIALS",
  implementer: "engineer@example.test", change_start: "2026-10-21T10:00:00Z", change_end: "2026-10-21T11:00:00Z",
  timezone: "UTC", required_role: "SECURITYADMIN", required_access_scope: "ACME_DB.SECURITY.CREDENTIALS",
  implementation_steps: ["Rotate the credential"], validation_plan: ["Confirm authentication"], rollback_plan: "Restore prior secret",
  expected_outcome: "Credential rotated", risk_and_impact: "Brief authentication interruption",
};

describe("complete change description", () => {
  it("uses explicit placeholders for unknown values", () => {
    const output = formatCompleteChangeDescription(draft);
    assert.ok(output.includes(`SUBSCRIPTION\n${UNKNOWN_DRAFT_VALUE}`));
  });
  it("includes corrected editable information", () => {
    const corrected = updateDraftField(draft, "subscription", "ACCOUNT-01");
    assert.ok(formatCompleteChangeDescription(corrected).includes("SUBSCRIPTION\nACCOUNT-01"));
  });
  it("preserves all unrelated edits and parses list fields", () => {
    const changed = updateDraftField(draft, "implementation_steps", "Step one\nStep two");
    assert.equal(changed.change_title, draft.change_title);
    assert.deepEqual(changed.implementation_steps, ["Step one", "Step two"]);
  });
});
