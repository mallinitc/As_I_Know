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

const KEY_PREFIX = "arca:ask-context:";
const LEGACY_KEY = "arca:ask-context";
const SAFE_NONCE = /^[a-zA-Z0-9-]{8,80}$/;

export function saveAskArcaContext(context: Omit<AskArcaContext, "nonce">): string | null {
  if (typeof window === "undefined") return null;
  const nonce = crypto.randomUUID();
  sessionStorage.removeItem(LEGACY_KEY);
  sessionStorage.setItem(`${KEY_PREFIX}${nonce}`, JSON.stringify({ ...context, nonce }));
  return nonce;
}

export function consumeAskArcaContext(nonce: string | null): AskArcaContext | null {
  if (typeof window === "undefined" || !nonce || !SAFE_NONCE.test(nonce)) return null;
  const key = `${KEY_PREFIX}${nonce}`;
  const raw = sessionStorage.getItem(key);
  if (!raw) return null;
  sessionStorage.removeItem(key);
  try {
    const value = JSON.parse(raw) as AskArcaContext;
    return value?.suggestedQuestion && value?.nonce === nonce ? value : null;
  } catch {
    return null;
  }
}
