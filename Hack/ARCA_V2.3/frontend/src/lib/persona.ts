"use client";

import { useSyncExternalStore } from "react";

export type PersonaRole="arca_analyst"|"arca_manager";
export type Capability="stage1"|"stage2"|"stage3"|"agent4"|"agent5"|"executive_dashboard"|"analytics_dashboard";

export const PERSONA_PERMISSIONS:Record<PersonaRole,readonly Capability[]>={
  arca_analyst:["stage1","agent5"],
  arca_manager:["stage2","stage3","agent4","agent5","executive_dashboard","analytics_dashboard"],
};
const KEY="arca_demo_persona";const EVENT="arca-persona-change";

function snapshot():PersonaRole{if(typeof window==="undefined")return "arca_manager";const value=localStorage.getItem(KEY);return value==="arca_analyst"||value==="arca_manager"?value:"arca_manager"}
function subscribe(callback:()=>void){window.addEventListener("storage",callback);window.addEventListener(EVENT,callback);return()=>{window.removeEventListener("storage",callback);window.removeEventListener(EVENT,callback)}}
export function usePersona(){return useSyncExternalStore(subscribe,snapshot,()=>"arca_manager" as PersonaRole)}
export function currentPersona():PersonaRole{return snapshot()}
export function setPersona(role:PersonaRole){localStorage.setItem(KEY,role);window.dispatchEvent(new Event(EVENT))}
export function can(role:PersonaRole,capability:Capability){return PERSONA_PERMISSIONS[role].includes(capability)}
export function capabilityForPath(path:string):Capability|undefined{
  if(path==="/")return "executive_dashboard";if(path.startsWith("/analytics"))return "analytics_dashboard";
  if(path.startsWith("/agents/change-quality")||path.startsWith("/change-assurance"))return "stage1";
  if(path.startsWith("/agents/access-intelligence"))return "stage2";if(path.startsWith("/execution-assurance"))return "stage3";
  if(path.startsWith("/risk-investigations"))return "agent4";if(path.startsWith("/ask-arca"))return "agent5";
}
export function landingFor(role:PersonaRole){return role==="arca_analyst"?"/agents/change-quality":"/"}
export function apiCapability(path:string):Capability|undefined{
  if(path.includes("/agents/change-quality"))return "stage1";if(path.includes("/agents/access-intelligence"))return "stage2";
  if(path.includes("/investigations/risk"))return "agent4";if(path.includes("/agents/ask-arca"))return "agent5";
  if(path.includes("/analytics/observability"))return "analytics_dashboard";if(path.includes("/analytics/"))return "executive_dashboard";
  if(path.includes("/execution-assurance")||path.includes("/execution-scenarios"))return "stage3";
  if(path.includes("/validate/access"))return "stage2";if(path.includes("/validate/change"))return "stage1";
  if(path.includes("/snowflake/validate")||path.endsWith("/changes")||path.endsWith("/demo-scenarios"))return typeof window!=="undefined"?capabilityForPath(window.location.pathname):"stage1";
}
