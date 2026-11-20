import assert from "node:assert/strict";
import test from "node:test";

import { selectAskExecutionMode } from "./ask-arca-state.ts";

const unavailable = { enabled: false, available: false, provider: null, model_identifier: null, status: "disabled" };
const available = { enabled: true, available: true, provider: "azure_openai", model_identifier: "approved-deployment", status: "available" };

test("Ask ARCA mode switching rejects unavailable LLM mode", () => {
  assert.equal(selectAskExecutionMode("llm_assisted", unavailable), "deterministic");
  assert.equal(selectAskExecutionMode("deterministic", available), "deterministic");
});

test("Ask ARCA mode switching allows an available approved provider", () => {
  assert.equal(selectAskExecutionMode("llm_assisted", available), "llm_assisted");
});
