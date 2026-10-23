import assert from "node:assert/strict";
import test from "node:test";
import { ArcaApiError, createArcaApiClient } from "./arca-api.ts";

const metadata = { synthetic: true, dataset_label: "Synthetic Demo Dataset", reference_timestamp: "2026-11-23T10:00:00Z", provider: "all", days: null, severity: "all", metric_definitions: {}, limitations: [] };
const summary = { compliant: 1, noncompliant: 2, review_or_unknown: 1, denominator: 3 };
const overview = { metadata, total_unique_changes: 4, approved_changes: 3, successfully_verified_changes: 1, noncompliant_changes: 2, changes_requiring_review: 1, compliance_rate: 33.3, compliance_denominator: 3, high_risk_findings: 2, execution_deviations: 1, potentially_unapproved_activities: 1, potentially_undocumented_changes: 1, access_risk_findings: 1, provider_risk_counts: [{ name: "aws", value: 2 }], findings_by_severity: [{ name: "high", value: 2 }], findings_over_time: [], change_assurance: summary, execution_assurance: summary, execution_risk_categories: [], access_risk_categories: [], undocumented_activity: [], recent_significant_findings: [] };
const risks = { metadata, total_findings: 2, unique_high_risk_findings: 2, findings_by_severity: [], findings_by_provider: [], findings_by_category: [], findings_over_time: [], findings: [] };
const execution = { metadata, summary, deviations: 1, potentially_unapproved_activities: 1, categories: [], evidence_coverage: { covered: 2, eligible: 3, percentage: 66.7, unavailable_reason: null } };
const access = { metadata, access_risk_findings: 1, categories: [], provider_counts: [], unavailable_metrics: {} };
const response = (value: unknown) => new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });

test("analytics client applies provider, period, and severity to all endpoints", async () => {
  const calls: string[] = [];
  const fetchImpl = (async (input: string | URL | Request) => { const url = String(input); calls.push(url); if (url.includes("/overview")) return response(overview); if (url.includes("/risks")) return response(risks); if (url.includes("/execution")) return response(execution); return response(access); }) as typeof fetch;
  const client = createArcaApiClient({ baseUrl: "http://arca.test", fetchImpl });
  const filters = { provider: "azure" as const, days: 15 as const, severity: "high" as const };
  assert.equal((await client.getAnalyticsOverview(filters)).total_unique_changes, 4);
  assert.equal((await client.getAnalyticsRisks(filters)).total_findings, 2);
  assert.equal((await client.getAnalyticsExecution(filters)).evidence_coverage.percentage, 66.7);
  assert.equal((await client.getAnalyticsAccess(filters)).access_risk_findings, 1);
  for (const call of calls) { const url = new URL(call); assert.equal(url.searchParams.get("provider"), "azure"); assert.equal(url.searchParams.get("days"), "15"); assert.equal(url.searchParams.get("severity"), "high"); }
});

test("analytics client rejects malformed responses instead of showing placeholders", async () => {
  const client = createArcaApiClient({ fetchImpl: (async () => response({ synthetic: true })) as typeof fetch });
  await assert.rejects(client.getAnalyticsOverview({ provider: "all", days: null, severity: "all" }), (error: unknown) => error instanceof ArcaApiError && error.kind === "schema");
});
