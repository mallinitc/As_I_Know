export type EnvironmentId = "all" | "azure" | "aws" | "snowflake";
export type ProviderEnvironmentId = Exclude<EnvironmentId, "all">;
export type RiskLevel = "Critical" | "High" | "Medium" | "Low";
export type FindingStatus = "Open" | "In review" | "Resolved";

export interface Metric {
  label: string;
  value: string;
  change: string;
  trend: "up" | "down" | "neutral";
  detail: string;
}

export interface RiskSlice {
  name: RiskLevel;
  value: number;
  color: string;
}

export interface ActivityPoint {
  label: string;
  assessments: number;
  findings: number;
  dayOffset: number;
}

export interface EnvironmentHealth {
  id: ProviderEnvironmentId;
  name: string;
  status: "Healthy" | "Attention";
  score: number;
  coverage: string;
  lastEvidence: string;
}

export interface Finding {
  id: string;
  title: string;
  environment: ProviderEnvironmentId;
  severity: RiskLevel;
  status: FindingStatus;
  resource: string;
  owner: string;
  observedAt: string;
  dayOffset: number;
}

export interface DashboardSnapshot {
  environment: EnvironmentId;
  metrics: Metric[];
  risks: RiskSlice[];
  activity: ActivityPoint[];
}

export interface DemoDashboardData {
  label: string;
  generatedAt: string;
  snapshots: Record<EnvironmentId, DashboardSnapshot>;
  health: EnvironmentHealth[];
  findings: Finding[];
}
