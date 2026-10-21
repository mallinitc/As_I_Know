import fs from "node:fs/promises";
import path from "node:path";
import { gunzipSync } from "node:zlib";

const browserPort = Number(process.env.ARCA_CDP_PORT || 9222);
const baseUrl = process.env.ARCA_FRONTEND_URL || "http://127.0.0.1:3000";
const outputDir = path.resolve("docs/demo/screenshots");
const results = [];
const failures = [];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function record(name, passed, detail = "") {
  results.push({ name, status: passed ? "PASS" : "FAIL", detail });
  if (!passed) failures.push(`${name}: ${detail}`);
}

async function connect() {
  const target = await fetch(`http://127.0.0.1:${browserPort}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" }).then((response) => response.json());
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let sequence = 0;
  const pending = new Map();
  const listeners = new Map();
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (!message.id) {
      for (const listener of listeners.get(message.method) || []) {
        Promise.resolve(listener(message.params)).catch((error) => failures.push(`${message.method}: ${error.message}`));
      }
      return;
    }
    const item = pending.get(message.id);
    if (!item) return;
    pending.delete(message.id);
    if (message.error) item.reject(new Error(message.error.message)); else item.resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const on = (method, listener) => {
    const current = listeners.get(method) || [];
    current.push(listener);
    listeners.set(method, current);
  };
  const off = (method, listener) => listeners.set(method, (listeners.get(method) || []).filter((item) => item !== listener));
  return { socket, send, on, off };
}

const cdp = await connect();
await cdp.send("Page.enable");
await cdp.send("Runtime.enable");
await cdp.send("Network.enable");

async function evaluate(expression) {
  const response = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || "Browser evaluation failed");
  return response.result.value;
}

async function waitFor(expression, label, timeout = 12000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(expression)) return;
    await sleep(100);
  }
  const excerpt = await evaluate("document.body?.innerText?.slice(0,1200) || ''").catch(() => "");
  throw new Error(`Timed out waiting for ${label}\n${excerpt}`);
}

async function navigate(route) {
  await cdp.send("Page.navigate", { url: `${baseUrl}${route}` });
  await waitFor("document.readyState === 'complete'", `${route} document`);
  await sleep(450);
}

async function setViewport(width, height) {
  await cdp.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 600 });
}

async function screenshot(name) {
  const image = await cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(path.join(outputDir, name), Buffer.from(image.data, "base64"));
}

async function select(selector, value) {
  return evaluate(`(() => { const element=document.querySelector(${JSON.stringify(selector)}); if(!element)return false; element.value=${JSON.stringify(value)}; element.dispatchEvent(new Event('change',{bubbles:true})); return true; })()`);
}

async function selectOption(labelText, matcher = null) {
  return evaluate(`(() => { const label=[...document.querySelectorAll('label')].find(x=>x.innerText.includes(${JSON.stringify(labelText)})); const element=label?.querySelector('select'); if(!element)return false; const options=[...element.options]; const option=${matcher ? `options.find(x=>x.text.toLowerCase().includes(${JSON.stringify(matcher.toLowerCase())}))` : "options.find(x=>x.value)"}; if(!option)return false; element.value=option.value; element.dispatchEvent(new Event('change',{bubbles:true})); return {value:option.value,text:option.text,count:options.length}; })()`);
}

async function waitForOptions(labelText) {
  await waitFor(`[...document.querySelectorAll('label')].find(x=>x.innerText.includes(${JSON.stringify(labelText)}))?.querySelector('select')?.options.length > 1`, `${labelText} options`);
}

async function clickText(selector, text) {
  return evaluate(`(() => { const element=[...document.querySelectorAll(${JSON.stringify(selector)})].find(x=>x.innerText.includes(${JSON.stringify(text)})&&!x.disabled); if(!element)return false; element.click(); return true; })()`);
}

async function openWithEnvironment(route, provider) {
  await navigate("/");
  if (!(await select("#global-environment", provider))) throw new Error("Global environment selector not found");
  await sleep(100);
  await evaluate(`document.querySelector('a[href=${JSON.stringify(route)}]')?.click()`);
  await waitFor(`location.pathname === ${JSON.stringify(route)}`, route);
  await sleep(450);
}

async function assertPage(route, title, screenshotName, provider = "all") {
  if (route === "/") await navigate(route); else await openWithEnvironment(route, provider);
  const state = await evaluate(`({title:[...document.querySelectorAll('h1,h2')].some(x=>x.innerText.includes(${JSON.stringify(title)})), overflow:document.documentElement.scrollWidth>window.innerWidth+1, width:window.innerWidth})`);
  record(`${route} title`, state.title, title);
  record(`${route} desktop overflow`, !state.overflow, `viewport ${state.width}`);
  await screenshot(screenshotName);
}

function evidenceIds(value, output = []) {
  if (Array.isArray(value)) {
    for (const item of value) evidenceIds(item, output);
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (["evidence_id", "eventID", "event_data_id", "query_id"].includes(key) && typeof item === "string") output.push(item);
      else if (["event_ids", "query_ids", "evidence_ids"].includes(key) && Array.isArray(item)) output.push(...item.filter((entry) => typeof entry === "string"));
      else evidenceIds(item, output);
    }
  }
  return [...new Set(output)];
}

function completedAnalysis(agent, result) {
  const references = evidenceIds(result).slice(0, 4);
  return {
    execution_mode: "llm_assisted",
    llm_invoked: true,
    llm_status: "completed",
    model_identifier: "gpt-5-mini-2025-08-07",
    ai_summary: `${agent} fixture confirms the existing workspace renders a completed, separately labeled LLM advisory response.`,
    ai_observations: ["Deterministic findings remain visible and authoritative."],
    ai_recommendations: ["Review the cited deterministic evidence before acting."],
    evidence_references: references,
    limitations: ["Browser-only fixture; no model request was made for this UI check."],
    token_usage: { input_tokens: 10, output_tokens: 10, total_tokens: 20 },
  };
}

async function interceptJsonOnce(urlSuffix, fixture, action) {
  let intercepted = false;
  const listener = async ({ requestId, request }) => {
    if (!request.url.endsWith(urlSuffix) || request.method !== "POST") {
      await cdp.send("Fetch.continueRequest", { requestId });
      return;
    }
    intercepted = true;
    await cdp.send("Fetch.fulfillRequest", {
      requestId,
      responseCode: 200,
      responseHeaders: [
        { name: "Content-Type", value: "application/json" },
        { name: "Access-Control-Allow-Origin", value: "http://127.0.0.1:3000" },
        { name: "Vary", value: "Origin" },
      ],
      body: Buffer.from(JSON.stringify(fixture)).toString("base64"),
    });
  };
  cdp.on("Fetch.requestPaused", listener);
  await cdp.send("Fetch.enable", { patterns: [{ urlPattern: `*${urlSuffix}`, requestStage: "Request" }] });
  try {
    await action();
    try {
      await waitFor("/ai analysis|model-generated explanation/i.test(document.body.innerText) || (document.body.innerText.includes('Agent Execution') && document.body.innerText.includes('Evidence references'))", `rendered response for ${urlSuffix}`);
    } catch (error) {
      const diagnostic = await evaluate(`({alert:document.querySelector('[role=alert]')?.innerText||'',pressed:[...document.querySelectorAll('button')].find(x=>x.innerText==='LLM Assisted')?.getAttribute('aria-pressed')||'',body:document.body.innerText.slice(-800)})`);
      throw new Error(`${error.message}\nintercepted=${intercepted}\ndiagnostic=${JSON.stringify(diagnostic)}\nhandlerFailures=${JSON.stringify(failures)}`);
    }
  } finally {
    await cdp.send("Fetch.disable");
    cdp.off("Fetch.requestPaused", listener);
  }
  return intercepted;
}

async function postJson(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return response.json();
}

async function verifyAgentFixture({ name, route, provider, endpoint, body, button }) {
  const deterministic = await postJson(`http://127.0.0.1:8000${endpoint}`, body);
  const fixture = { ...deterministic, ai_analysis: completedAnalysis(name, deterministic) };
  await openWithEnvironment(route, provider);
  await waitForOptions("Verified Demo Example");
  await selectOption("Verified Demo Example");
  await sleep(150);
  await clickText("button", "LLM Assisted");
  await waitFor("[...document.querySelectorAll('button')].some(x=>x.innerText==='LLM Assisted'&&x.getAttribute('aria-pressed')==='true')", `${name} LLM Assisted selection`);
  const intercepted = await interceptJsonOnce(endpoint, fixture, async () => {
    if (!(await clickText("button", button))) throw new Error(`${name} submit button was unavailable`);
  });
  const ui = await evaluate(`({
    assisted:[...document.querySelectorAll('button')].some(x=>x.innerText==='LLM Assisted'&&x.getAttribute('aria-pressed')==='true'),
    completed:document.body.innerText.includes('completed'),
    model:document.body.innerText.includes('gpt-5-mini-2025-08-07'),
    analysis:/ai analysis/i.test(document.body.innerText)&&document.body.innerText.includes('Advisory interpretation'),
    deterministic:/findings|assessment/i.test(document.body.innerText),
    evidence:/evidence/i.test(document.body.innerText)
  })`);
  record(`${name} mocked LLM-assisted UI`, intercepted && Object.values(ui).every(Boolean), JSON.stringify(ui));
}

async function runFinalLlmVerification() {
  const encoded = process.env.ARCA_AGENT5_RESPONSE_GZIP_B64;
  if (!encoded) throw new Error("ARCA_AGENT5_RESPONSE_GZIP_B64 is required for final LLM verification");
  const agent5 = JSON.parse(gunzipSync(Buffer.from(encoded, "base64")).toString("utf8"));

  if (process.env.ARCA_AGENT5_ONLY !== "true") {
    await verifyAgentFixture({ name: "Agent 1", route: "/agents/change-quality", provider: "aws", endpoint: "/api/v1/aws/validate/change", body: { change_id: "CHG1003", execution_mode: "deterministic" }, button: "Run Change Validation" });
    await verifyAgentFixture({ name: "Agent 2", route: "/agents/access-intelligence", provider: "aws", endpoint: "/api/v1/aws/validate/access", body: { change_id: "CHG1007", execution_mode: "deterministic" }, button: "Run Access Validation" });
    await verifyAgentFixture({ name: "Agent 3", route: "/execution-assurance", provider: "aws", endpoint: "/api/v1/aws/execution-assurance/change", body: { change_id: "CHG1002", scenario_id: "AWS-EXEC-02", evaluation_timestamp: "2026-10-22T12:00:00Z", execution_mode: "deterministic" }, button: "Run Validation" });
    await verifyAgentFixture({ name: "Agent 4", route: "/risk-investigations", provider: "all", endpoint: "/api/v1/investigations/risk", body: { environment: "aws", window_days: 10, severity: "all", evaluation_timestamp: "2026-10-22T12:00:00Z", execution_mode: "deterministic" }, button: "Run Investigation" });
  }

  await openWithEnvironment("/ask-arca", "all");
  await waitForOptions("Verified Demo Example");
  await selectOption("Verified Demo Example", "unapproved snowflake role grant");
  await clickText("button", "LLM Assisted");
  const intercepted = await interceptJsonOnce("/api/v1/agents/ask-arca", agent5, async () => {
    if (!(await clickText("button", "Ask ARCA"))) throw new Error("Agent 5 submit button was unavailable");
  });
  const expectCompleted = process.env.ARCA_AGENT5_EXPECT_COMPLETED !== "false";
  const ui = await evaluate(`({
    assisted:[...document.querySelectorAll('button')].some(x=>x.innerText==='LLM Assisted'&&x.getAttribute('aria-pressed')==='true'),
    status:document.body.innerText.includes(${JSON.stringify(expectCompleted ? "LLM: Completed" : "LLM: Invalid Response")}),
    model:document.body.innerText.includes(${JSON.stringify(agent5.model_identifier)}),
    synthesis:${expectCompleted ? `/model-generated explanation/i.test(document.body.innerText)&&document.body.innerText.includes(${JSON.stringify(agent5.model_generated_explanation)})` : `!/model-generated explanation/i.test(document.body.innerText)&&document.body.innerText.includes('deterministic ARCA tools')`},
    deterministic:document.body.innerText.includes('Deterministic findings'),
    evidence:document.body.innerText.includes('Evidence references'),
    plannedTool:document.body.innerText.includes('Find Potentially Unapproved Activity'),
    evidenceTool:document.body.innerText.includes('Retrieve Supporting Evidence')
  })`);
  const responseSource = process.env.ARCA_AGENT5_RESPONSE_SOURCE || "live";
  const resultName = expectCompleted
    ? responseSource === "fixture" ? "Agent 5 accepted-response UI fixture" : "Agent 5 real LLM-assisted UI"
    : "Agent 5 rejected-synthesis fallback UI fixture";
  record(resultName, intercepted && Object.values(ui).every(Boolean), JSON.stringify(ui));
  await screenshot(responseSource === "fixture" ? "08-agent-5-ui-fixture.png" : "08-agent-5-live-llm.png");
}

if (process.env.ARCA_FINAL_LLM_VERIFY === "1") {
  await setViewport(1440, 900);
  await runFinalLlmVerification();
  await fs.writeFile(path.resolve("docs/demo/browser-llm-verification-results.json"), JSON.stringify({ generated_at: new Date().toISOString(), browser: "Installed Google Chrome via DevTools Protocol", results, failures }, null, 2));
  console.log(JSON.stringify({ passed: results.filter((item) => item.status === "PASS").length, failed: failures.length, failures }, null, 2));
  cdp.socket.close();
  process.exit(failures.length ? 1 : 0);
}

await setViewport(1440, 900);
await assertPage("/", "Assurance posture at a glance", "01-overview-desktop.png");
await assertPage("/agents/change-quality", "Change Quality", "02-agent-1-change-quality-desktop.png", "snowflake");
await assertPage("/agents/access-intelligence", "Access Intelligence", "02b-agent-2-access-intelligence-desktop.png", "snowflake");
await assertPage("/execution-assurance", "Post-Implementation Validation", "03-execution-assurance-desktop.png", "snowflake");
await assertPage("/risk-investigations", "Undocumented Changes", "04-risk-investigations-desktop.png");
await assertPage("/ask-arca", "Ask ARCA", "05-ask-arca-desktop.png");
await assertPage("/analytics", "Risk and control intelligence", "06-analytics-desktop.png");
await navigate("/");
record("Overview five-agent cards", await evaluate("[...document.querySelectorAll('a')].filter(x=>x.innerText.includes('Open Workspace')).length === 5"));
record("Sidebar five-agent navigation", await evaluate("[...document.querySelectorAll('nav[aria-label=\"Primary navigation\"] a')].filter(x=>/^A[1-5]/.test(x.innerText)).length === 5"));
await navigate("/change-assurance");
await waitFor("location.pathname === '/agents/change-quality'", "legacy Change Assurance redirect");
record("Legacy Change Assurance route", await evaluate("location.pathname === '/agents/change-quality'"));

for (const provider of ["aws", "azure", "snowflake"]) {
  await openWithEnvironment("/agents/change-quality", provider);
  await waitForOptions("Verified Demo Example");
  const chosen = await selectOption("Verified Demo Example");
  record(`Change Assurance ${provider} scenarios`, Boolean(chosen && chosen.count > 1), JSON.stringify(chosen));
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 450, downloadThroughput: -1, uploadThroughput: -1, connectionType: "wifi" });
  const action = await clickText("button", provider === "snowflake" ? "Run Validation" : "Run Change Validation");
  await sleep(40);
  const disabled = await evaluate(`[...document.querySelectorAll('button')].some(x=>x.innerText.includes('Run')&&x.disabled)`);
  record(`Change Assurance ${provider} processing state`, action && disabled, "button disabled after submit");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1, connectionType: "wifi" });
  const resultLabel = provider === "snowflake" ? "Change Quality result" : `${provider === "aws" ? "AWS" : "Azure"} assessment result`;
  await waitFor(`document.body.innerText.includes(${JSON.stringify(resultLabel)})`, `${provider} change result`);
  const content = await evaluate(`({result:document.body.innerText.includes(${JSON.stringify(resultLabel)}),evidence:/evidence/i.test(document.body.innerText),recommendation:/recommend/i.test(document.body.innerText)})`);
  record(`Change Assurance ${provider} result`, content.result && content.evidence && content.recommendation, JSON.stringify(content));
}

await openWithEnvironment("/agents/change-quality", "azure");
await waitForOptions("Verified Demo Example");
await selectOption("Verified Demo Example", "incomplete");
await clickText("button", "Run Change Validation");
await waitFor("document.body.innerText.includes('Missing-field guidance')", "missing-field guidance");
record("Agent 1 missing-field explanations", await evaluate("document.body.innerText.includes('Why it matters:') && document.body.innerText.includes('Ask ARCA About This')"));
const draftAction=await clickText("button", "Prepare Editable Draft");
if(!draftAction) throw new Error(`Draft action missing: ${JSON.stringify(await evaluate("[...document.querySelectorAll('button')].map(x=>x.innerText)"))}`);
await waitFor("document.body.innerText.includes('Copy Improved Draft') || Boolean(document.querySelector('[role=alert]'))", "editable improved draft", 20000);
const draftState=await evaluate("({action:"+JSON.stringify(draftAction)+",fields:document.querySelectorAll('input[placeholder^=\"[Required:\"],textarea[placeholder^=\"[Required:\"]').length,copy:document.body.innerText.includes('Copy Improved Draft'),error:[...document.querySelectorAll('[role=alert]')].map(x=>x.innerText).join(' | ')})");
record("Agent 1 improved draft", draftState.action && draftState.fields >= 5 && draftState.copy, JSON.stringify(draftState));
await evaluate("performance.clearResourceTimings()");
await clickText("button", "Ask ARCA About This");
await waitFor("location.pathname === '/ask-arca'", "contextual Ask ARCA navigation");
await waitFor("document.body.innerText.includes('Executive Summary') || Boolean(document.querySelector('[role=alert]'))", "contextual Ask ARCA autorun");
const contextualRequests=await evaluate("performance.getEntriesByType('resource').filter(x=>x.name.includes('/api/v1/agents/ask-arca')&&!x.name.includes('/scenarios')&&!x.name.includes('/capabilities')).length");
record("Contextual Ask ARCA autorun exactly once", contextualRequests===1, String(contextualRequests));

for (const provider of ["aws", "azure", "snowflake"]) {
  await openWithEnvironment("/agents/access-intelligence", provider);
  await waitForOptions("Verified Demo Example");
  const chosen = await selectOption("Verified Demo Example");
  record(`Access Intelligence ${provider} scenarios`, Boolean(chosen && chosen.count > 1), JSON.stringify(chosen));
  await clickText("button", provider === "snowflake" ? "Run Validation" : "Run Access Validation");
  const resultLabel = provider === "snowflake" ? "Access Intelligence result" : `${provider === "aws" ? "AWS" : "Azure"} assessment result`;
  await waitFor(`document.body.innerText.includes(${JSON.stringify(resultLabel)})`, `${provider} access result`);
  const content = await evaluate(`({result:document.body.innerText.includes(${JSON.stringify(resultLabel)}),evidence:/evidence/i.test(document.body.innerText),recommendation:/recommend/i.test(document.body.innerText)})`);
  record(`Access Intelligence ${provider} result`, content.result && content.evidence && content.recommendation, JSON.stringify(content));
}

await openWithEnvironment("/agents/change-quality", "aws");
await selectOption("Verified Demo Example");
await clickText("button", "Run Change Validation");
await waitFor("document.body.innerText.includes('AWS assessment result')", "AWS result before provider switch");
await select("#global-environment", "azure");
await waitFor("document.body.innerText.includes('Azure')", "Azure workspace after provider switch");
record("Provider switch clears stale Change Assurance result", !(await evaluate("document.body.innerText.includes('AWS assessment result')")));

await waitForOptions("Verified Demo Example");
await selectOption("Verified Demo Example");
await cdp.send("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
await clickText("button", "Run Change Validation");
await waitFor("Boolean(document.querySelector('[role=alert]'))", "offline validation error");
await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1, connectionType: "wifi" });
const errorState = await evaluate(`({alert:document.querySelector('[role=alert]')?.innerText||'',enabled:[...document.querySelectorAll('button')].some(x=>x.innerText.includes('Run Change Validation')&&!x.disabled),stale:document.body.innerText.includes('Azure assessment result')})`);
record("Failed request restores controls and clears stale result", Boolean(errorState.alert) && errorState.enabled && !errorState.stale, JSON.stringify(errorState));

for (const provider of ["aws", "azure", "snowflake"]) {
  await openWithEnvironment("/execution-assurance", provider);
  await waitForOptions("Verified Demo Example");
  const chosen = await selectOption("Verified Demo Example");
  record(`Execution Assurance ${provider} scenarios`, Boolean(chosen && chosen.count > 1), JSON.stringify(chosen));
  await clickText("button", provider === "aws" ? "Run Validation" : "Run Execution Validation");
  await waitFor("document.body.innerText.toLowerCase().includes('execution assurance result')", `${provider} execution result`);
  const content = await evaluate(`({findings:/findings/i.test(document.body.innerText),evidence:/timeline|evidence/i.test(document.body.innerText),recommendation:/recommend/i.test(document.body.innerText)})`);
  record(`Execution Assurance ${provider} result`, content.findings && content.evidence && content.recommendation, JSON.stringify(content));
}

await openWithEnvironment("/execution-assurance", "aws");
await clickText("button", "By IAM Principal / User");
await sleep(100);
await waitForOptions("Verified Demo Example");
await selectOption("Verified Demo Example");
await clickText("button", "Run Validation");
await waitFor("document.body.innerText.includes('AWS execution assurance result')", "principal execution result");
record("User/principal investigation", await evaluate("document.body.innerText.includes('AWS execution assurance result')"));

await openWithEnvironment("/risk-investigations", "all");
await waitForOptions("Verified Demo Example");
let chosen = await selectOption("Verified Demo Example");
record("Risk single-provider scenario selectable", Boolean(chosen));
await clickText("button", "Run Investigation");
await waitFor("document.body.innerText.includes('Investigation summary')", "risk result");
record("Risk result and evidence", await evaluate("/evidence/i.test(document.body.innerText) && /finding/i.test(document.body.innerText)"));
chosen = await selectOption("Verified Demo Example", "multi-environment");
record("Risk cross-environment scenario selectable", Boolean(chosen), JSON.stringify(chosen));
const severityChanged = await selectOption("Severity", "high");
record("Risk severity filter", Boolean(severityChanged));

await openWithEnvironment("/ask-arca", "all");
await waitForOptions("Verified Demo Example");
record("Ask ARCA deterministic default", await evaluate("[...document.querySelectorAll('button')].some(x=>x.innerText==='Deterministic'&&x.getAttribute('aria-pressed')==='true')"));
record("Ask ARCA LLM capability state", await evaluate("[...document.querySelectorAll('button')].some(x=>x.innerText==='LLM Assisted'&&(!x.disabled?document.body.innerText.includes('openai available'):document.body.innerText.includes('LLM Assisted mode is')))"));
for (const matcher of ["change", "user", "cross", "ambiguous"]) {
  const askChoice = await selectOption("Verified Demo Example", matcher);
  record(`Ask ARCA ${matcher} scenario`, Boolean(askChoice), JSON.stringify(askChoice));
  if (!askChoice) continue;
  await clickText("button", "Ask ARCA");
  await waitFor("document.body.innerText.includes('Executive Summary') && document.body.innerText.includes('Technical Evidence')", `Ask ARCA ${matcher} result`);
}
record("Ask ARCA tool trace and evidence", await evaluate("document.body.innerText.includes('Technical Evidence') && Boolean(document.querySelector('details'))"));
record("Ask ARCA response mode disclosure", await evaluate("document.body.innerText.includes('LLM: Not Invoked') && document.body.innerText.includes('What Was Found')"));

await openWithEnvironment("/analytics", "all");
await cdp.send("Performance.enable").catch(() => undefined);
await evaluate("performance.clearResourceTimings()");
await selectOption("Time period", "15");
await selectOption("Severity", "high");
await sleep(600);
const analyticsState = await evaluate(`({label:document.body.innerText.includes('Synthetic Demo Dataset'),charts:document.querySelectorAll('.recharts-wrapper').length,requests:performance.getEntriesByType('resource').map(x=>x.name).filter(x=>x.includes('/api/v1/analytics/')).length,kpis:document.body.innerText.includes('Risk and control intelligence')})`);
record("Analytics filters and API refresh", analyticsState.label && analyticsState.charts >= 5 && analyticsState.requests >= 3 && analyticsState.kpis, JSON.stringify(analyticsState));
const chartPoint = await evaluate(`(() => { const node=document.querySelector('.recharts-surface'); if(!node)return null; const r=node.getBoundingClientRect(); return {x:r.left+r.width*.72,y:r.top+r.height*.5}; })()`);
if (chartPoint) {
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: chartPoint.x, y: chartPoint.y });
  await sleep(150);
}
record("Analytics chart tooltip", await evaluate("Boolean(document.querySelector('.recharts-tooltip-wrapper')?.innerText.trim())"));
const findingLink = await evaluate("document.querySelector('a[href=\"/risk-investigations\"],a[href=\"/agents/change-quality\"],a[href=\"/execution-assurance\"]')?.getAttribute('href') || null");
record("Overview finding navigation target", Boolean(findingLink), String(findingLink));

for (const viewport of [{ name: "laptop", width: 1366, height: 768 }, { name: "tablet", width: 768, height: 1024 }, { name: "mobile", width: 390, height: 844 }]) {
  await setViewport(viewport.width, viewport.height);
  for (const route of ["/", "/agents/change-quality", "/agents/access-intelligence", "/execution-assurance", "/risk-investigations", "/ask-arca", "/analytics"]) {
    await navigate(route);
    const layout = await evaluate(`({overflow:document.documentElement.scrollWidth>window.innerWidth+1,main:!!document.querySelector('main'),menu:${viewport.width < 1024}?!!document.querySelector('button[aria-label="Open navigation"]'):true})`);
    record(`${viewport.name} ${route} layout`, !layout.overflow && layout.main && layout.menu, JSON.stringify(layout));
  }
  if (viewport.name === "mobile") {
    await navigate("/");
    await evaluate("document.querySelector('button[aria-label=\"Open navigation\"]')?.click()");
    await sleep(100);
    record("Mobile sidebar navigation", await evaluate("Boolean(document.querySelector('a[href=\"/analytics\"]')) && document.body.innerText.includes('Analytics')"));
    await screenshot("07-overview-mobile.png");
  }
}

await fs.writeFile(path.resolve("docs/demo/browser-validation-results.json"), JSON.stringify({ generated_at: new Date().toISOString(), browser: "Installed Google Chrome via DevTools Protocol", results, failures }, null, 2));
console.log(JSON.stringify({ passed: results.filter((item) => item.status === "PASS").length, failed: failures.length, failures }, null, 2));
cdp.socket.close();
if (failures.length) process.exitCode = 1;
