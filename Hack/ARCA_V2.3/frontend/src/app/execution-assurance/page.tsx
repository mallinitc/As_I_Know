import { AgentWorkspaceHeader } from "@/components/agent-workspace-header";
import { ExecutionAssuranceWorkspace } from "@/components/execution-assurance-workspace";

export default function Page() {
  return <div className="space-y-6"><AgentWorkspaceHeader agent={3} /><ExecutionAssuranceWorkspace /></div>;
}
