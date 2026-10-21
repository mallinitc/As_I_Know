import assert from "node:assert/strict";
import test from "node:test";
import { consumeAskArcaContext, saveAskArcaContext } from "./contextual-ask.ts";

test("contextual Ask ARCA navigation is consumed exactly once", () => {
  const values = new Map<string,string>();
  Object.defineProperty(globalThis,"window",{value:{},configurable:true});
  Object.defineProperty(globalThis,"sessionStorage",{value:{setItem:(key:string,value:string)=>values.set(key,value),getItem:(key:string)=>values.get(key)??null,removeItem:(key:string)=>values.delete(key)},configurable:true});
  saveAskArcaContext({sourceAgent:"A1",provider:"azure",changeId:"CHG-AZ-2001",selectedFinding:"rollback_plan",evidenceReferences:[],suggestedQuestion:"Clarify rollback plan",autorun:true});
  const first=consumeAskArcaContext();
  assert.equal(first?.suggestedQuestion,"Clarify rollback plan");
  assert.equal(first?.autorun,true);
  assert.equal(consumeAskArcaContext(),null);
});
