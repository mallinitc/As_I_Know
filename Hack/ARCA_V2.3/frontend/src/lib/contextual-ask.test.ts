import assert from "node:assert/strict";
import test from "node:test";
import { consumeAskArcaContext, saveAskArcaContext } from "./contextual-ask.ts";

test("contextual Ask ARCA navigation is consumed exactly once", () => {
  const values = new Map<string,string>();
  Object.defineProperty(globalThis,"window",{value:{},configurable:true});
  Object.defineProperty(globalThis,"sessionStorage",{value:{setItem:(key:string,value:string)=>values.set(key,value),getItem:(key:string)=>values.get(key)??null,removeItem:(key:string)=>values.delete(key)},configurable:true});
  const nonce=saveAskArcaContext({sourceAgent:"A1",provider:"azure",changeId:"CHG-AZ-2001",selectedFinding:"rollback_plan",evidenceReferences:["EV-1"],suggestedQuestion:"Clarify rollback plan",autorun:true});
  assert.ok(nonce);
  assert.equal(consumeAskArcaContext("wrong-nonce"),null);
  const first=consumeAskArcaContext(nonce);
  assert.equal(first?.suggestedQuestion,"Clarify rollback plan");
  assert.equal(first?.autorun,true);
  assert.deepEqual(first?.evidenceReferences,["EV-1"]);
  assert.equal(consumeAskArcaContext(nonce),null);
});
