import type { AskConversationContext, AskResponse } from "@/types/api";

export interface InvestigationContext {
  investigationId: string;
  provider: string;
  changeId?: string;
  selectedFinding?: string;
  evidenceReferences?: string[];
  sourceAgent: string;
  backendContext?: AskConversationContext;
}

export interface InvestigationTurn {
  investigationId: string;
  question: string;
  response: AskResponse;
}

export interface AskInvestigationState {
  context: InvestigationContext;
  turns: InvestigationTurn[];
  active: AskResponse | null;
  pendingRequestId: number | null;
  running: boolean;
  error: string;
}

export type InvestigationAction =
  | { type: "begin"; context: InvestigationContext }
  | { type: "request_started"; investigationId: string; requestId: number }
  | { type: "request_succeeded"; investigationId: string; requestId: number; question: string; response: AskResponse }
  | { type: "request_failed"; investigationId: string; requestId: number; error: string }
  | { type: "select_result"; investigationId: string; response: AskResponse };

export function directInvestigation(investigationId: string): InvestigationContext {
  return { investigationId, provider: "all", sourceAgent: "Direct" };
}

export function initialInvestigationState(context: InvestigationContext): AskInvestigationState {
  return { context, turns: [], active: null, pendingRequestId: null, running: false, error: "" };
}

export function investigationReducer(state: AskInvestigationState, action: InvestigationAction): AskInvestigationState {
  if (action.type === "begin") return initialInvestigationState(action.context);
  if (action.investigationId !== state.context.investigationId) return state;
  if (action.type === "request_started") return { ...state, pendingRequestId: action.requestId, running: true, active: null, error: "" };
  if (action.type === "request_succeeded") {
    if (state.pendingRequestId !== action.requestId) return state;
    return { ...state, context: { ...state.context, provider: action.response.conversation_context.provider || state.context.provider, backendContext: action.response.conversation_context }, pendingRequestId: null, running: false, error: "", active: action.response, turns: [...state.turns, { investigationId: action.investigationId, question: action.question, response: action.response }] };
  }
  if (action.type === "request_failed") {
    if (state.pendingRequestId !== action.requestId) return state;
    return { ...state, pendingRequestId: null, running: false, active: null, error: action.error };
  }
  return { ...state, active: action.response };
}

export function scopeFollowUp(question: string, context: InvestigationContext, isFollowUp: boolean): string {
  if (!isFollowUp && context.sourceAgent === "Direct") return question;
  const identifiers = [`provider ${context.provider}`];
  if (context.changeId) identifiers.push(`change ${context.changeId}`);
  if (context.selectedFinding) identifiers.push(`finding ${context.selectedFinding}`);
  if (context.backendContext?.selected_resource) identifiers.push(`resource ${context.backendContext.selected_resource}`);
  const kind = isFollowUp ? "Follow-up question" : "Contextual question";
  return `Use only the current investigation context for ${identifiers.join(", ")}. ${kind}: ${question}`;
}
