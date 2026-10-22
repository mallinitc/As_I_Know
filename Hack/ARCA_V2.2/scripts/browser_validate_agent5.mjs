const port = Number(process.env.ARCA_CDP_PORT || 9222);
const baseUrl = process.env.ARCA_FRONTEND_URL || "http://127.0.0.1:3000";
const results = [];
const failures = [];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const record = (name, passed, detail = "") => {
  results.push({ name, status: passed ? "PASS" : "FAIL", detail });
  if (!passed) failures.push(`${name}: ${detail}`);
};

const target = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" }).then((response) => response.json());
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
let sequence = 0;
const pending = new Map();
socket.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (!message.id) return;
  const item = pending.get(message.id);
  if (!item) return;
  pending.delete(message.id);
  message.error ? item.reject(new Error(message.error.message)) : item.resolve(message.result);
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence;
  pending.set(id, { resolve, reject });
  socket.send(JSON.stringify({ id, method, params }));
});
const evaluate = async (expression) => {
  const response = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || "Browser evaluation failed");
  return response.result.value;
};
const waitFor = async (expression, label, timeout = 15000) => {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await evaluate(expression)) return;
    await sleep(100);
  }
  const excerpt = await evaluate("document.body.innerText.slice(-2500)").catch(() => "");
  throw new Error(`Timed out waiting for ${label}\n${excerpt}`);
};
await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: `${baseUrl}/ask-arca` });
await waitFor("document.readyState==='complete'", "Ask ARCA page");
await waitFor("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select')?.options.length===22", "21 scenarios");

const labels = await evaluate(`(() => [...[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example')).querySelector('select').options].map(x=>x.text))()`);
const v1 = ["Find recent undocumented changes", "Review subscription Contributor requests", "Investigate a uniquely named resource", "Troubleshoot storage access loss", "Ambiguous Storage Account reference", "Unsupported question guardrail"];
record("all V1 scenarios", v1.every((name) => labels.includes(name)), JSON.stringify(labels.slice(-6)));

await evaluate(`(() => { const s=[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example')).querySelector('select'); s.value='ASK-ACCESS'; s.dispatchEvent(new Event('change',{bubbles:true})); })()`);
await sleep(150);
record("scenario populates exact question", await evaluate(`[...document.querySelectorAll('textarea')].some(x=>x.value==='I could access starchprod04 two days ago, but now I cannot. What changed?')`));
await evaluate(`[...document.querySelectorAll('button')].find(x=>x.innerText.trim()==='Ask ARCA').click()`);
await waitFor("document.body.innerText.includes('Which user or service-principal')", "identity clarification");
record("access clarification", await evaluate("document.body.innerText.includes('starchprod04') && document.body.innerText.includes('Which user or service-principal')"));

await evaluate(`(() => { const t=document.querySelector('textarea'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(t,'engineer12@example.invalid'); t.dispatchEvent(new Event('input',{bubbles:true})); })()`);
await sleep(100);
await evaluate(`[...document.querySelectorAll('button')].filter(x=>x.innerText.trim()==='Ask Follow-Up').at(-1).click()`);
await waitFor("document.body.innerText.includes('firewall/network ACL modification')", "access evidence", 20000);
await evaluate(`[...document.querySelectorAll('summary')].find(x=>x.innerText.includes('Technical Evidence')).click()`);
await waitFor("document.body.innerText.includes('az-event-0012')", "expanded technical evidence");
const access = await evaluate(`({identity:document.body.innerText.includes('engineer12@example.invalid'),resource:document.body.innerText.includes('starchprod04'),event:document.body.innerText.includes('az-event-0012'),technical:document.body.innerText.includes('Technical Evidence'),trace:document.body.innerText.includes('Execution trace')})`);
record("access follow-up evidence", Object.values(access).every(Boolean), JSON.stringify(access));

await evaluate(`[...document.querySelectorAll('button')].find(x=>x.innerText.trim()==='New Investigation').click()`);
await sleep(200);
record("new investigation isolation", await evaluate("!document.body.innerText.includes('az-event-0012') && !document.body.innerText.includes('firewall/network ACL modification')"));

await evaluate(`(() => { const s=[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example')).querySelector('select'); s.value='ASK-AMBIGUOUS'; s.dispatchEvent(new Event('change',{bubbles:true})); })()`);
await evaluate(`[...document.querySelectorAll('button')].find(x=>x.innerText.trim()==='Ask ARCA').click()`);
await waitFor("document.body.innerText.includes('multiple matching synthetic resources')", "resource clarification");
record("ambiguous resource clarification", await evaluate("document.body.innerText.includes('Provide the exact name, resource group, or full resource ID')"));

for (const width of [1366, 768]) {
  await send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: false });
  await sleep(100);
  record(`${width}px layout`, !(await evaluate("document.documentElement.scrollWidth>window.innerWidth+1")));
}

console.log(JSON.stringify(results, null, 2));
socket.close();
if (failures.length) throw new Error(failures.join("\n"));
