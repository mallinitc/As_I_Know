import assert from "node:assert/strict";
import test from "node:test";
import { can, capabilityForPath, landingFor, PERSONA_PERMISSIONS } from "./persona.ts";

test("Analyst permissions expose only Agent 1 and Agent 5",()=>{
  assert.deepEqual(PERSONA_PERMISSIONS.arca_analyst,["stage1","agent5"]);
  assert.equal(can("arca_analyst","stage1"),true);assert.equal(can("arca_analyst","agent5"),true);
  for(const capability of ["stage2","stage3","agent4","executive_dashboard","analytics_dashboard"] as const)assert.equal(can("arca_analyst",capability),false);
  assert.equal(landingFor("arca_analyst"),"/agents/change-quality");
});

test("Manager permissions exclude Agent 1",()=>{
  assert.equal(can("arca_manager","stage1"),false);
  for(const capability of ["stage2","stage3","agent4","agent5","executive_dashboard","analytics_dashboard"] as const)assert.equal(can("arca_manager",capability),true);
  assert.equal(landingFor("arca_manager"),"/");
});

test("direct routes resolve to centralized capabilities",()=>{
  assert.equal(capabilityForPath("/agents/change-quality"),"stage1");
  assert.equal(capabilityForPath("/agents/access-intelligence"),"stage2");
  assert.equal(capabilityForPath("/execution-assurance"),"stage3");
  assert.equal(capabilityForPath("/risk-investigations"),"agent4");
  assert.equal(capabilityForPath("/ask-arca"),"agent5");
  assert.equal(capabilityForPath("/"),"executive_dashboard");
  assert.equal(capabilityForPath("/analytics"),"analytics_dashboard");
});
