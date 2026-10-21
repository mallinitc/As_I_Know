"use client";

import { useRouter } from "next/navigation";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { saveAskArcaContext } from "@/lib/contextual-ask";

export function AskArcaAction({ sourceAgent, provider, changeId, finding, evidenceReferences = [], question, autorun = true, label = "Ask ARCA About This" }: {
  sourceAgent:string; provider:string; changeId?:string; finding?:string; evidenceReferences?:string[]; question:string; autorun?:boolean; label?:string;
}) {
  const router = useRouter();
  return <Button variant="outline" onClick={() => {
    saveAskArcaContext({ sourceAgent, provider, changeId, selectedFinding:finding, evidenceReferences, suggestedQuestion:question, autorun });
    router.push("/ask-arca");
  }}><Bot className="size-4" />{label}</Button>;
}
