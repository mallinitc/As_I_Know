"""Checkpointed LangGraph workflow for read-only Azure investigations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import operator
import re
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .models import classify_conversation, get_model_adapter
from .tools import InvestigationTools, _at
from arca.observability import performance_span
from arca.snowflake_post_implementation import investigate_user


class ConversationState(TypedDict, total=False):
    messages: Annotated[list[dict], operator.add]
    query: str
    intent: str
    parameters: dict
    context: dict
    tool_results: dict
    response: str
    evidence_refs: list[str]
    status: str
    direct_response: str
    planner_error: str


class InvestigationAgent:
    """Natural-language facade over deterministic read-only evidence tools."""

    def __init__(self, tools=None, model_mode=None):
        self.tools = tools or InvestigationTools()
        self.model = get_model_adapter(model_mode)
        self.checkpointer = MemorySaver()
        graph = StateGraph(ConversationState)
        graph.add_node("plan", self._plan)
        graph.add_node("investigate", self._investigate)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "investigate")
        graph.add_edge("investigate", END)
        self.graph = graph.compile(checkpointer=self.checkpointer)

    @property
    def mode_label(self): return self.model.label

    def _tool(self, name, method, *args, **kwargs):
        with performance_span(name, stage="Ask ARCA", agent="InvestigationTools"):
            return method(*args, **kwargs)

    def ask(self, query: str, thread_id: str = "default", context: dict | None = None) -> dict:
        payload = {"query": query, "messages": [{"role": "user", "content": query}]}
        if context: payload["context"] = context
        return self.graph.invoke(payload,
                                 config={"configurable": {"thread_id": thread_id}})

    def reset(self, thread_id: str = "default"):
        # A new thread identifier is the supported immutable-checkpoint reset mechanism.
        return f"{thread_id}-reset"

    def _plan(self, state):
        context = dict(state.get("context") or {})
        direct = classify_conversation(state.get("query", ""))
        if direct:
            return {"intent": direct["intent"], "parameters": {}, "context": context,
                    "direct_response": direct.get("response", ""), "status": "routed"}
        if getattr(self.tools, "provider", "") == "snowflake":
            plan = self._plan_snowflake(state.get("query", ""), context)
        else:
            plan = self.model.plan(state.get("query", ""), context, self.tools.evidence_as_of)
        return {"intent": plan["intent"], "parameters": plan.get("parameters", {}),
                "context": context, "planner_error": plan.get("error", ""), "status": "planned"}

    def _resource_from_query(self, query, context):
        lower = query.lower()
        resources = self.tools.bundle["resources"]
        named = [resource for resource in resources if resource["name"].lower() in lower or resource["resource_id"].lower() in lower]
        if len(named) == 1: return named[0], None
        if len(named) > 1: return None, named
        if re.search(r"\b(this|that|selected) resource\b", lower) and context.get("selected_resource"):
            result = self._tool("Resource details retrieval", self.tools.get_resource_details, context["selected_resource"])
            return (result["items"][0], None) if result["count"] else (None, [])
        type_hint = None
        for token in ("storage", "virtual machine", "web", "key vault", "sql", "network security"):
            if token in lower: type_hint = token; break
        if type_hint:
            matches = self._tool("Resource search", self.tools.find_resources, resource_type=type_hint.split()[0])
            return (matches["items"][0], None) if matches["count"] == 1 else (None, matches["items"])
        if context.get("selected_resource"):
            result = self._tool("Resource details retrieval", self.tools.get_resource_details, context["selected_resource"])
            return (result["items"][0], None) if result["count"] else (None, [])
        return None, []

    @staticmethod
    def _refs(results):
        refs = []
        for result in results.values():
            for item in result.get("items", []):
                for key in ("query_id", "event_data_id", "event_id", "pim_request_id", "assignment_id", "change_id", "resource_id"):
                    if item.get(key) and item[key] not in refs: refs.append(item[key])
                    if key in item: break
        return refs

    def _plan_snowflake(self, query, context):
        text, lower = (query or "").strip(), (query or "").lower()
        if not text or len(text) > 2000:
            return {"intent": "malformed", "parameters": {}, "error": "Enter a non-empty investigation question under 2,000 characters."}
        change = re.search(r"\bCHG-SF-\d{4}\b", text, re.I)
        email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
        user_id = re.search(r"\bSF-USER-\d{3}\b", text, re.I)
        user_name = re.search(r"\bSF(?:ENGINEER|SECURITY|ROGUE)\d{2}\b", text, re.I)
        days_match = re.search(r"(?:last|past)\s+(\d+)\s+days?", lower)
        days = int(days_match.group(1)) if days_match else 10
        params = {"days": days, "evaluation_time": context.get("evaluation_time") or self.tools.evidence_as_of}
        identity = email or user_id or user_name
        if identity: params["identity"] = identity.group(0)
        if change: params["change_id"] = change.group(0).upper()
        if "accountadmin" in lower: params["role"] = "ACCOUNTADMIN"
        if "grant role" in lower or "role grant" in lower: params["operation"] = "GRANT ROLE"
        if "revoke role" in lower or "role revocation" in lower: params["operation"] = "REVOKE ROLE"
        if change: return {"intent": "snowflake_change", "parameters": params}
        if identity: return {"intent": "snowflake_user", "parameters": params}
        if any(term in lower for term in ("unapproved", "without approved", "unexpected", "privilege escalation", "failed administrative", "database modifications", "role grant", "role revocation", "accountadmin")):
            return {"intent": "snowflake_unapproved", "parameters": params}
        return {"intent": "unsupported", "parameters": params}

    def _clarify_resource(self, matches):
        if matches:
            choices = ", ".join(f"{x['name']} ({x['resource_group']})" for x in matches[:8])
            return f"I found multiple matching synthetic resources: {choices}. Which resource should I investigate? Provide the exact name, subscription/resource group, or full resource ID."
        return "I could not uniquely identify a resource in the synthetic Azure dataset. Provide its exact resource name, subscription/resource group, or full resource ID."

    def _investigate(self, state):
        intent, params = state["intent"], state.get("parameters", {})
        context = dict(state.get("context") or {})
        query = state.get("query", "")
        if getattr(self.tools, "provider", "") == "snowflake" and intent.startswith("snowflake_"):
            return self._investigate_snowflake(intent, params, query, context)
        if intent in {"greeting", "capabilities", "known_cloud", "unrelated"}:
            context.update({"last_intent": intent, "pending_clarification": None})
            return self._finish(state.get("direct_response", ""), {}, context,
                                "unsupported" if intent == "unrelated" else "complete")
        if intent == "general_cloud":
            if hasattr(self.model, "answer_general"):
                try:
                    response = self.model.answer_general(query)
                    return self._finish(response, {}, context, "complete")
                except Exception as exc:
                    return self._finish(f"A general cloud explanation is temporarily unavailable ({type(exc).__name__}). No environment-specific evidence was inspected.", {}, context, "unavailable")
            return self._finish("The configured offline mode cannot answer this broader general-knowledge question. I can still investigate the local cloud evidence or explain ARCA capabilities.", {}, context, "unavailable")
        if intent in {"malformed", "unavailable"}:
            response = state.get("planner_error") or "The configured investigation planner is unavailable. No evidence tools were executed."
            return self._finish(response, {}, context, "unavailable")
        if intent == "unsupported":
            return self._finish("I can investigate access loss, resource modifications, undocumented changes, approval evidence, and Azure PIM requests. Try one of the suggested questions.", {}, context, "unsupported")
        if intent == "undocumented_changes":
            result = self._tool("Activity log correlation", self.tools.find_undocumented_changes, start=params.get("start"), end=params.get("end"), environment=params.get("environment") or "production")
            response = (f"MOCK MODE: Found {result['count']} successful modification event(s) without an exact matching approved change in the available synthetic evidence. "
                        "These are unmatched records, not confirmed unauthorized changes.")
            context.update({"investigation_window": {"start": params.get("start"), "end": params.get("end")}, "previous_findings": result["items"], "last_intent": intent, "pending_clarification": None})
            return self._finish(response, {"undocumented": result}, context)
        if intent == "pim_requests":
            result = self._tool("PIM evidence retrieval", self.tools.get_pim_requests, role=params.get("role"), scope=params.get("scope"), start=params.get("start"), end=params.get("end"))
            response = f"MOCK MODE: Found {result['count']} matching synthetic PIM request(s). Results reflect request records, not independently calculated effective access."
            context.update({"investigation_window": {"start": params.get("start"), "end": params.get("end")}, "previous_findings": result["items"], "last_intent": intent, "pending_clarification": None})
            return self._finish(response, {"pim_requests": result}, context)
        if intent in {"actors_followup", "approval_followup"}:
            return self._followup(intent, context)

        resource, matches = self._resource_from_query(query, context)
        if not resource:
            context["pending_clarification"] = "resource"
            context["pending_intent"] = intent
            return self._finish(self._clarify_resource(matches), {}, context, "clarification")
        context.update({"selected_resource": resource["resource_id"], "subscription": resource["subscription_id"],
                        "resource_group": resource["resource_group"]})
        if intent == "access_troubleshooting" and not params.get("identity"):
            context["pending_clarification"] = "identity"
            return self._finish(f"I identified {resource['name']} in {resource['resource_group']}. Which user or service-principal name/object ID is experiencing the access failure?", {"resource": self._tool("Resource details retrieval", self.tools.get_resource_details, resource["resource_id"])}, context, "clarification")

        start, end = params.get("start"), params.get("end")
        activity = self._tool("Activity log retrieval", self.tools.get_activity_logs, resource_id=resource["resource_id"], start=start, end=end, modifications_only=True)
        changes = self._tool("Change evidence retrieval", self.tools.get_change_records, resource_id=resource["resource_id"], start=start, end=end)
        results = {"resource": self._tool("Resource details retrieval", self.tools.get_resource_details, resource["resource_id"]), "activity_logs": activity, "change_records": changes}
        if intent == "access_troubleshooting":
            identity = params["identity"]
            results["role_assignments"] = self._tool("Role assignment retrieval", self.tools.get_role_assignments, resource_id=resource["resource_id"], identity=identity)
            results["pim_requests"] = self._tool("PIM evidence retrieval", self.tools.get_pim_requests, resource_id=resource["resource_id"], identity=identity, start=start, end=end)
            signals = []
            for event in activity["items"]:
                signal = azure_signal(event)
                if signal: signals.append(signal)
            if signals:
                cause = " Relevant evidence includes " + "; ".join(sorted(set(signals))) + "."
            else:
                cause = " The available evidence does not establish a root cause for this identity's access failure."
            response = (f"MOCK MODE: Reviewed {activity['count']} modification event(s), {results['role_assignments']['count']} role assignment(s), "
                        f"{results['pim_requests']['count']} PIM request(s), and {changes['count']} approved change record(s) for {resource['name']}.{cause} "
                        "Potential causes are not confirmed root causes without resource-state and sign-in evidence.")
            context["selected_identity"] = identity
        else:
            actors = sorted({x["caller"] for x in activity["items"]})
            response = f"MOCK MODE: Found {activity['count']} successful modification event(s) for {resource['name']} in the selected window. Actors in the evidence: {', '.join(actors) if actors else 'none'}."
        context.update({"investigation_window": {"start": start, "end": end}, "previous_findings": activity["items"], "last_intent": intent, "pending_clarification": None, "pending_intent": None})
        return self._finish(response, results, context)

    def _investigate_snowflake(self, intent, params, query, context):
        trace, results = [], {}
        def run(label, key, method, *args, **kwargs):
            trace.append(label)
            value = self._tool(label, method, *args, **kwargs)
            results[key] = value
            return value
        if intent == "snowflake_change":
            change_id = params["change_id"]
            details = run("Get Change Details", "change_details", self.tools.get_change_details, change_id)
            if not details["count"]:
                return self._finish(f"No synthetic Snowflake change record was found for {change_id}.", results, context, "insufficient_evidence")
            activity = run("Get Change Activity", "change_activity", self.tools.get_change_activity,
                           change_id, params.get("evaluation_time"))
            query_ids = [row["query_id"] for row in activity["items"]]
            run("Get Access History", "access_history", self.tools.get_access_history, query_ids=query_ids)
            deviations = run("Detect Change Deviations", "deviations", self.tools.detect_change_deviations,
                             change_id, params.get("evaluation_time"))
            assessment = deviations["query"]["assessment"]
        elif intent == "snowflake_user":
            identity, days = params["identity"], params.get("days", 10)
            resolved = run("Resolve Snowflake User", "identity", self.tools.resolve_snowflake_user, identity)
            identity_status = resolved["query"].get("status")
            if identity_status != "RESOLVED":
                message = ("Multiple exact Snowflake identities use that email; provide a user name or user ID."
                           if identity_status == "AMBIGUOUS" else "The user could not be resolved in the synthetic Snowflake directory.")
                return self._finish(message, results, context, "clarification")
            start, end = self.tools.user_window(days, params.get("evaluation_time"))
            activity = run("Get User Activity", "user_activity", self.tools.get_user_activity, identity, start, end)
            query_ids = [row["query_id"] for row in activity["items"]]
            run("Get Access History", "access_history", self.tools.get_access_history, query_ids=query_ids)
            assessment = investigate_user(identity, self.tools.bundle, days=days, evaluation_time=params.get("evaluation_time"))
            structured = self.tools.structured_findings(assessment)
            results["deviations"] = {"tool": "detect_change_deviations", "count": len(structured),
                                     "items": structured, "query": {"assessment": assessment}}
            trace.append("Detect Change Deviations")
        else:
            end = params.get("evaluation_time") or self.tools.evidence_as_of
            start, end = self.tools.user_window(params.get("days", 10), end)
            unmatched = run("Get Unapproved Activity", "unapproved_activity", self.tools.get_unapproved_activity,
                            start=start, end=end, role=params.get("role"), operation=params.get("operation"))
            assessment = {"mode": "unapproved_activity", "status": "REVIEW_REQUIRED" if unmatched["count"] else "NO_GOVERNED_ACTIVITY",
                          "investigation_window": {"start": start, "end": end},
                          "summary": {"finding_categories": ["POSSIBLE_UNAPPROVED_ACTIVITY"] if unmatched["count"] else []},
                          "findings": [{"category": "POSSIBLE_UNAPPROVED_ACTIVITY", "recommended_action": "Review unmatched governed activity."}] if unmatched["count"] else [],
                          "timeline": unmatched["items"], "limitations": ["Unmatched activity is not proof of malicious behavior."]}
        timeline = run("Build Investigation Timeline", "timeline", self.tools.build_investigation_timeline, assessment.get("timeline", []))
        summary = run("Summarize Investigation", "summary", self.tools.summarize_investigation, assessment, query)
        results["tool_trace"] = {"tool": "tool_execution_trace", "count": len(trace), "items": [{"step": i + 1, "tool": name} for i, name in enumerate(trace)], "query": {}}
        categories = assessment.get("summary", {}).get("finding_categories", [])
        response = (f"MOCK MODE: Snowflake investigation completed with {len(assessment.get('timeline', []))} activity event(s). "
                    f"Findings: {', '.join(categories) if categories else 'no governed deviations identified'}. "
                    "Conclusions use deterministic synthetic audit correlation; successful SQL does not verify final object configuration.")
        context.update({"investigation_window": assessment.get("investigation_window"), "previous_findings": assessment.get("timeline", []),
                        "last_intent": intent, "selected_identity": params.get("identity"), "selected_change": params.get("change_id"),
                        "tool_trace": trace, "pending_clarification": None})
        return self._finish(response, results, context)

    def _followup(self, intent, context):
        findings = context.get("previous_findings") or []
        if not findings:
            return self._finish("I do not have prior modification evidence in this conversation. Select a resource and investigation window first.", {}, context, "insufficient_evidence")
        if intent == "actors_followup":
            actors = sorted({item.get("caller") for item in findings if item.get("caller")})
            response = "MOCK MODE: Actors recorded on the previous evidence: " + (", ".join(actors) if actors else "none available in the evidence.")
            return self._finish(response, {"previous_activity": {"tool": "conversation_context", "count": len(findings), "items": findings, "query": {}}}, context)
        approved, unmatched = [], []
        for event in findings:
            event_id = event.get("event_data_id") or event.get("event_id")
            matches = []
            for change in self.tools.bundle["changes"]:
                implementer = change.get("implementer", {})
                if change.get("start") <= event.get("event_timestamp", event.get("timestamp", "")) <= change.get("end") \
                   and implementer.get("principal_id") == event.get("caller_principal_id") \
                   and any(x["operation"].lower() == event.get("operation_name", {}).get("value", event.get("operation", "")).lower()
                           and x["resource_id"].lower() == event.get("resource_id", "").lower() for x in change.get("expected", [])):
                    matches.append(change["change_id"])
            (approved if matches else unmatched).append({"event_id": event_id, "change_ids": matches})
        response = f"MOCK MODE: {len(approved)} prior event(s) have an exact matching approved synthetic change; {len(unmatched)} do not. Unmatched does not mean unauthorized."
        result = {"tool": "approval_correlation", "count": len(approved) + len(unmatched), "query": {}, "items": approved + unmatched}
        context["previous_findings"] = result["items"]
        return self._finish(response, {"approval_correlation": result}, context)

    def _finish(self, response, results, context, status="complete"):
        if status == "complete" and results and hasattr(self.model, "respond"):
            try:
                response = self.model.respond(response, results, context)
            except Exception as exc:
                response = f"{response} Model-generated narration was unavailable ({type(exc).__name__}); the displayed result uses deterministic tool output."
        refs = self._refs(results)
        return {"response": response, "tool_results": results, "context": context, "evidence_refs": refs,
                "status": status, "messages": [{"role": "assistant", "content": response}]}


def azure_signal(event):
    operation = event.get("operation_name", {}).get("value", "").lower()
    properties = event.get("properties", {})
    if operation == "microsoft.authorization/roleassignments/delete":
        return "a role-assignment removal possibly related to storage access"
    if operation == "microsoft.storage/storageaccounts/write" and "networkAcls" in properties.get("changed_settings", []):
        return "a storage firewall/network ACL modification possibly related to access"
    return None
