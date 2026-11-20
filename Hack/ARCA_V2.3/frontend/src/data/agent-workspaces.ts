import {
  Activity,
  Bot,
  ClipboardCheck,
  KeyRound,
  SearchCheck,
  type LucideIcon,
} from "lucide-react";

import type { EnvironmentId } from "@/types/dashboard";

export type AgentNumber = 1 | 2 | 3 | 4 | 5;

export interface AgentWorkspaceDefinition {
  number: AgentNumber;
  name: string;
  responsibility: string;
  detail: string;
  href: string;
  supportedProviders: string[];
  executionMode: string;
  icon: LucideIcon;
}

export const agentWorkspaces: AgentWorkspaceDefinition[] = [
  {
    number: 1,
    name: "Change Quality",
    responsibility: "Validate change quality before implementation.",
    detail: "Pre-change request quality, completeness, ambiguity, and consistency validation",
    href: "/agents/change-quality",
    supportedProviders: ["AWS", "Azure", "Snowflake"],
    executionMode: "Deterministic Validation",
    icon: ClipboardCheck,
  },
  {
    number: 2,
    name: "Access Intelligence",
    responsibility: "Validate least-privilege access before execution.",
    detail: "Pre-execution IAM, PIM/RBAC, and Snowflake role assessment; audit logs are not required",
    href: "/agents/access-intelligence",
    supportedProviders: ["AWS", "Azure", "Snowflake"],
    executionMode: "Deterministic Validation",
    icon: KeyRound,
  },
  {
    number: 3,
    name: "Execution Assurance",
    responsibility: "Verify observed changes against approved activity.",
    detail: "Post-implementation evidence correlation",
    href: "/execution-assurance",
    supportedProviders: ["AWS", "Azure"],
    executionMode: "Deterministic Validation",
    icon: Activity,
  },
  {
    number: 4,
    name: "Undocumented Changes",
    responsibility: "Discover potentially undocumented or suspicious activity.",
    detail: "Cross-environment risk and evidence investigation",
    href: "/risk-investigations",
    supportedProviders: ["AWS", "Azure"],
    executionMode: "Deterministic Evidence Correlation",
    icon: SearchCheck,
  },
  {
    number: 5,
    name: "Ask ARCA",
    responsibility: "Investigate natural-language questions through existing tools.",
    detail: "Evidence-grounded conversational investigation",
    href: "/ask-arca",
    supportedProviders: ["AWS", "Azure", "Snowflake"],
    executionMode: "Deterministic / LLM Assisted",
    icon: Bot,
  },
];

const providerLabels: Record<EnvironmentId, string | null> = { all: null, aws: "AWS", azure: "Azure", snowflake: "Snowflake" };

/** Whether an agent workspace path is offered for the selected environment; non-agent paths always are. */
export function isWorkspaceAvailable(href: string, environment: EnvironmentId): boolean {
  const workspace = agentWorkspaces.find((item) => item.href === href);
  const provider = providerLabels[environment];
  return !workspace || !provider || workspace.supportedProviders.includes(provider);
}

export function getAgentWorkspace(number: AgentNumber): AgentWorkspaceDefinition {
  const workspace = agentWorkspaces.find((item) => item.number === number);
  if (!workspace) throw new Error(`Unknown ARCA agent: ${number}`);
  return workspace;
}
