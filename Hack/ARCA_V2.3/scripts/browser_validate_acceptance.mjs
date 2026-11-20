const port=Number(process.env.ARCA_CDP_PORT||9222),base=process.env.ARCA_FRONTEND_URL||"http://127.0.0.1:3000",checks=[];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const target=await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`,{method:"PUT"}).then(r=>r.json());
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});let seq=0;const pending=new Map();
ws.onmessage=e=>{const m=JSON.parse(e.data);if(!m.id)return;const p=pending.get(m.id);if(!p)return;pending.delete(m.id);m.error?p.reject(new Error(m.error.message)):p.resolve(m.result)};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
await send("Page.enable");await send("Runtime.enable");
async function evaljs(expression){const r=await send("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value}
async function wait(expression,label,timeout=15000){const start=Date.now();while(Date.now()-start<timeout){if(await evaljs(expression))return;await sleep(100)}throw new Error(`Timed out: ${label}`)}
async function nav(path){await send("Page.navigate",{url:`${base}${path}`});await wait("document.readyState==='complete'",path);await sleep(350)}
function ok(name,passed,detail=""){checks.push({name,passed,detail});if(!passed)throw new Error(`${name}: ${detail}`)}
await send("Emulation.setDeviceMetricsOverride",{width:1366,height:768,deviceScaleFactor:1,mobile:false});
await nav("/");let body=await evaljs("document.body.innerText");
ok("executive dashboard focus",body.includes("Infrastructure Change Overview")&&body.includes("Potentially Undocumented")&&!body.includes("Input tokens"));
ok("executive provenance",body.includes("Synthetic Demo Dataset")&&body.includes("Snapshot reference")&&body.includes("not live cloud telemetry"));
await evaljs(`(()=>{const s=document.querySelector('#global-environment');s.value='azure';s.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);await sleep(500);
ok("provider filter",(await evaljs("document.querySelector('#global-environment')?.value"))==="azure");
await nav("/risk-investigations");await wait("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select')?.options.length>1","Agent 4 scenarios");
await evaljs(`(()=>{const s=[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example')).querySelector('select');s.value='UD-AZ-24H';s.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);
await evaljs(`[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Run Investigation')).click()`);await wait("document.body.innerText.includes('Assessment feedback')","feedback controls",30000);
await evaljs(`[...document.querySelectorAll('button')].find(x=>x.innerText.trim()==='Correct').click()`);await evaljs(`[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Submit Feedback')).click()`);await wait("document.body.innerText.includes('Latest response: Correct')","saved feedback");
ok("stage feedback persistence",true);
await nav("/analytics");await wait("document.body.innerText.includes('Tool Usage, Performance & AI Metrics')","analytics dashboard");body=await evaljs("document.body.innerText");
ok("analytics focus",body.includes("LLM Usage & Cost")&&body.includes("Performance & Reliability")&&body.includes("Human Feedback"));
ok("analytics filters",["Time","Environment","Stage / Feature","Status","Advanced Filters"].every(x=>body.includes(x)));
ok("feedback aggregation",body.includes("Correct")&&body.includes("Latest feedback distribution"));
ok("cost safety",body.includes("Cost unavailable")||body.includes("Estimated LLM cost"));
await send("Emulation.setDeviceMetricsOverride",{width:768,height:1024,deviceScaleFactor:1,mobile:false});await sleep(200);
ok("responsive analytics",!(await evaljs("document.documentElement.scrollWidth>window.innerWidth+1")));
console.log(JSON.stringify({passed:checks.length,failed:0,checks},null,2));ws.close();
