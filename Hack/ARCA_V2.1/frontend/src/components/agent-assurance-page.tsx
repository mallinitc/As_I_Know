"use client";

import { AgentWorkspaceHeader } from "@/components/agent-workspace-header";
import { ChangeAssuranceWorkspace } from "@/components/change-assurance-workspace";

export function AgentAssurancePage({ agent }: { agent: 1 | 2 }) {
  return (
    <div className="space-y-6">
      <AgentWorkspaceHeader agent={agent} />
      <ChangeAssuranceWorkspace agent={agent} />
    </div>
  );
}
