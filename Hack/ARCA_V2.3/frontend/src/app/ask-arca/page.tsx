import { Suspense } from "react";
import { AgentWorkspaceHeader } from "@/components/agent-workspace-header";
import { AskArcaWorkspace } from "@/components/ask-arca-workspace";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page(){return <div className="space-y-6"><AgentWorkspaceHeader agent={5}/><Suspense fallback={<Skeleton className="h-[36rem]"/>}><AskArcaWorkspace/></Suspense></div>}
