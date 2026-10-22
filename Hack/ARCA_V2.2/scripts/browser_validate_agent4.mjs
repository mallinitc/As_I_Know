const cdpPort = Number(process.env.ARCA_CDP_PORT || 9222);
const baseUrl = process.env.ARCA_FRONTEND_URL || "http://127.0.0.1:3000";
const results = [];
const failures = [];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function record(name, passed, detail = "") { results.push({ name, passed, detail }); if (!passed) failures.push(`${name}: ${detail}`); }

const target = await fetch(`http://127.0.0.1:${cdpPort}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" }).then((response) => response.json());
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
let sequence = 0;
const pending = new Map();
socket.onmessage = (event) => { const message = JSON.parse(event.data); if (!message.id) return; const item = pending.get(message.id); if (!item) return; pending.delete(message.id); message.error ? item.reject(new Error(message.error.message)) : item.resolve(message.result); };
const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
await send("Page.enable"); await send("Runtime.enable");

async function evaluate(expression) { const response = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }); if (response.exceptionDetails) throw new Error(response.exceptionDetails.text); return response.result.value; }
async function waitFor(expression, label, timeout = 12000) { const start = Date.now(); while (Date.now() - start < timeout) { if (await evaluate(expression)) return; await sleep(100); } throw new Error(`Timed out waiting for ${label}`); }
async function setViewport(width, height) { await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 600 }); }

await setViewport(1366, 768);
await send("Page.navigate", { url: `${baseUrl}/risk-investigations` });
await waitFor("document.readyState==='complete'", "page load");
await waitFor("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select')?.options.length===20", "19 scenarios");

const options = await evaluate(`(() => { const select=[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example')).querySelector('select'); return [...select.options].map(x=>x.text); })()`);
record("V1 Azure demo availability", ["Azure unmatched activity — 24 hours", "Azure unmatched activity — 2 days", "Azure unmatched activity — 7 days", "Azure unmatched activity — 15 days"].every((name) => options.includes(name)), JSON.stringify(options.slice(-4)));

await evaluate(`(() => { const select=[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example')).querySelector('select'); select.value='UD-AZ-24H'; select.dispatchEvent(new Event('change',{bubbles:true})); })()`);
await sleep(100);
const populated = await evaluate(`(() => { const labels=[...document.querySelectorAll('label')]; const value=(name)=>labels.find(x=>x.innerText.trim().startsWith(name)&&x.querySelector('select,input'))?.querySelector('select,input')?.value; return {environment:value('Environment'),time:value('Time Range'),stale:document.body.innerText.includes('Investigation summary')}; })()`);
record("Scenario auto-population", populated.environment === "azure" && populated.time === "1" && !populated.stale, JSON.stringify(populated));

await evaluate(`[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Run Investigation')).click()`);
await waitFor("document.body.innerText.includes('Investigation summary')", "Agent 4 result");
const rendered = await evaluate(`({
  classification:document.body.innerText.toLowerCase().includes('unmatched in available records'),
  evidence:document.body.innerText.includes('Supporting Activity Log evidence')&&document.body.innerText.includes('10'),
  warning:document.body.innerText.includes('does not establish that the action was unauthorized'),
  azureOnly:document.body.innerText.includes('AZURE: 10')&&!document.body.innerText.includes('AWS:'),
  period:document.body.innerText.includes('2026-10-25T08:20:00Z')&&document.body.innerText.includes('2026-10-26T08:20:00Z'),
  noLlm:/deterministic|not invoked/i.test(document.body.innerText)
})`);
record("Result and evidence rendering", Object.values(rendered).every(Boolean), JSON.stringify(rendered));

await evaluate(`(() => { const select=[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example')).querySelector('select'); select.value='UD-AZ-2D'; select.dispatchEvent(new Event('change',{bubbles:true})); })()`);
await sleep(100);
record("Scenario switch clears stale output", await evaluate("!document.body.innerText.includes('Investigation summary')"));

await evaluate(`(() => { const select=[...document.querySelectorAll('label')].find(x=>x.innerText.trim().startsWith('Environment')&&x.querySelector('select'))?.querySelector('select'); if(!select)throw new Error('Environment control unavailable'); select.value='aws'; select.dispatchEvent(new Event('change',{bubbles:true})); })()`);
await sleep(100);
const switched = await evaluate(`(() => { const labels=[...document.querySelectorAll('label')]; return {scenario:labels.find(x=>x.innerText.includes('Verified Demo Example')).querySelector('select').value,result:document.body.innerText.includes('Investigation summary')}; })()`);
record("Provider switch clears incompatible state", switched.scenario === "" && !switched.result, JSON.stringify(switched));

for (const viewport of [{ width: 1366, height: 768 }, { width: 768, height: 1024 }]) {
  await setViewport(viewport.width, viewport.height); await sleep(100);
  const overflow = await evaluate("document.documentElement.scrollWidth>window.innerWidth+1");
  record(`${viewport.width}px responsive layout`, !overflow, String(overflow));
}

console.log(JSON.stringify({ passed: results.filter((item) => item.passed).length, failed: failures.length, results, failures }, null, 2));
socket.close();
if (failures.length) process.exitCode = 1;
