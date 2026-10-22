const port=Number(process.env.ARCA_CDP_PORT||9222);
const base=process.env.ARCA_FRONTEND_URL||"http://127.0.0.1:3000";
const target=await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`,{method:"PUT"}).then(r=>r.json());
const socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
let id=0;const pending=new Map();socket.onmessage=event=>{const value=JSON.parse(event.data);if(!value.id)return;const item=pending.get(value.id);pending.delete(value.id);value.error?item.reject(new Error(value.error.message)):item.resolve(value.result)};
const send=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params}))});
await send("Page.enable");await send("Runtime.enable");
async function evaluate(expression){const result=await send("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.text);return result.result.value}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(expression,label){for(let i=0;i<150;i++){if(await evaluate(`Boolean(${expression})`))return;await sleep(100)}const body=await evaluate("document.body.innerText.slice(-1600)");throw new Error(`Timed out: ${label}\n${body}`)}
async function selectScenario(index=1){const info=await evaluate(`(()=>{const select=[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select');if(!select)return null;const option=select.options[${index}];return option?.value?{count:select.options.length,text:option.text,value:option.value}:null})()`);if(!info)return null;for(let i=0;i<index;i++){await evaluate(`(()=>{const select=[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select');select?.focus();return Boolean(select)})()`);await send("Input.dispatchKeyEvent",{type:"keyDown",key:"ArrowDown",code:"ArrowDown",windowsVirtualKeyCode:40,nativeVirtualKeyCode:40});await send("Input.dispatchKeyEvent",{type:"keyUp",key:"ArrowDown",code:"ArrowDown",windowsVirtualKeyCode:40,nativeVirtualKeyCode:40});await sleep(250)}return info}
async function click(text){return evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find(x=>x.innerText.includes(${JSON.stringify(text)})&&!x.disabled);if(!button)return false;button.click();return true})()`)}
async function input(label){return evaluate(`(()=>[...document.querySelectorAll('label')].find(x=>x.innerText.includes(${JSON.stringify(label)}))?.querySelector('input,textarea')?.value||'')()`)}
await send("Page.navigate",{url:`${base}/`});await wait("document.readyState==='complete'","home");
await wait("document.querySelector('#global-environment')","environment selector");
await evaluate(`(()=>{const x=document.querySelector('#global-environment');x.value='azure';x.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('a[href="/agents/access-intelligence"]')?.click();return true})()`);
await wait("location.pathname==='/agents/access-intelligence'","Agent 2 route");
await wait("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select')?.options.length===6","five change scenarios plus manual");
const change=await selectScenario();await wait("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Change number'))?.querySelector('input')?.value==='CHG-AZ-2021'","change population");
await click("Validate All PIM Requests");await wait("document.body.innerText.toUpperCase().includes('STAGE 2 COMPLETE')","change result");
const changeOutcome=await evaluate("document.body.innerText.toUpperCase().includes('APPROVE RECOMMENDED')");
await click("Search by Change Number");await wait("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select')?.value===''","change reset");
const insufficient=await selectScenario(3);await wait("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Change number'))?.querySelector('input')?.value==='CHG-AZ-2023'","insufficient change population");
await click("Validate All PIM Requests");await wait("document.body.innerText.toUpperCase().includes('STAGE 2 COMPLETE')","insufficient change result");
const insufficientOutcome=await evaluate("document.body.innerText.toUpperCase().includes('INSUFFICIENT ACCESS')");
await click("Search by User ID");await wait("[...document.querySelectorAll('label')].some(x=>x.innerText.includes('Azure UPN'))","user mode");await wait("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select')?.options.length===6","five user scenarios plus manual");
const user=await selectScenario(2);await wait("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Azure UPN'))?.querySelector('input')?.value==='engineer05@example.invalid'","user population");
await click("Validate All PIM Requests");await wait("document.body.innerText.toUpperCase().includes('STAGE 2 COMPLETE')","user result");
const userOutcome=await evaluate("document.body.innerText.toUpperCase().includes('OVERPRIVILEGED')");
await click("Paste PIM Records");await wait("document.querySelector('textarea')","paste mode");await wait("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select')?.options.length===6","five paste scenarios plus manual");
const paste={count:await evaluate("[...document.querySelectorAll('label')].find(x=>x.innerText.includes('Verified Demo Example'))?.querySelector('select')?.options.length")};
const pasteRecords=await fetch("http://127.0.0.1:8000/api/v1/agents/access-intelligence/stage2/scenario-records?request_ids=pim-az-0021,pim-az-0022,pim-az-0023").then(r=>r.json());
await evaluate("document.querySelector('textarea')?.focus()");await send("Input.insertText",{text:pasteRecords.records_text});await wait("document.querySelector('textarea')?.value.includes('pim-az-0021')","pasted record entry");
await click("Validate All PIM Requests");await wait("document.body.innerText.toUpperCase().includes('STAGE 2 COMPLETE')","paste result");
const pasteOutcome=await evaluate("document.body.innerText.toUpperCase().includes('APPROVE RECOMMENDED')");
const report={changeOptions:change.count,userOptions:user.count,pasteOptions:paste.count,totalScenarios:change.count+user.count+paste.count-3,selectedScenarios:[change.text,insufficient.text,user.text],changeOutcome,insufficientOutcome,userOutcome,pasteOutcome,snowflakeLeak:await evaluate("document.body.innerText.includes('selected Snowflake change')"),status:changeOutcome&&insufficientOutcome&&userOutcome&&pasteOutcome?"PASS":"FAIL"};
console.log(JSON.stringify(report));socket.close();
