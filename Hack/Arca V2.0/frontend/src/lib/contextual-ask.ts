export interface AskArcaContext {
  sourceAgent: string;
  provider: string;
  changeId?: string;
  selectedFinding?: string;
  evidenceReferences?: string[];
  suggestedQuestion: string;
  autorun: boolean;
  nonce: string;
}

const KEY = "arca:ask-context";

export function saveAskArcaContext(context: Omit<AskArcaContext, "nonce">): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(KEY, JSON.stringify({ ...context, nonce: crypto.randomUUID() }));
}

export function consumeAskArcaContext(): AskArcaContext | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(KEY);
  if (!raw) return null;
  sessionStorage.removeItem(KEY);
  try {
    const value = JSON.parse(raw) as AskArcaContext;
    return value?.suggestedQuestion && value?.nonce ? value : null;
  } catch {
    return null;
  }
}
