export let API=import.meta.env.VITE_EQUIPMENT_API_BASE||'/api/gateway/equipment-agent';
let apiSetup,apiCheckedAt=0;
async function setupApi(){if(!import.meta.env.VITE_EQUIPMENT_REMOTE)return;if(!apiSetup||Date.now()-apiCheckedAt>30000)apiSetup=(async()=>{apiCheckedAt=Date.now();const stop=new AbortController(),timer=setTimeout(()=>stop.abort(),10000);let r;try{r=await fetch(import.meta.env.BASE_URL+'api-config.json?t='+Math.floor(Date.now()/30000),{cache:'no-store',signal:stop.signal});}finally{clearTimeout(timer);}if(!r.ok)throw new Error('登记服务暂未配置，请稍后重试');const c=await r.json();const u=new URL(c.apiBase);if(u.protocol!=='https:'||u.username||u.password)throw new Error('登记服务配置无效');API=u.href.replace(/\/$/,'');})();try{await apiSetup;}catch(e){apiSetup=null;throw e;}}
export const STORE='shanye-chat-session-v2';
export const uuid=()=>typeof crypto.randomUUID==='function'?crypto.randomUUID().replaceAll('-','_'):Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
export function visitId(){let id=sessionStorage.getItem('shanye-visit-v1');if(!id){id=uuid();sessionStorage.setItem('shanye-visit-v1',id);}return id;}
export function newVisit(){const id=uuid();sessionStorage.setItem('shanye-visit-v1',id);sessionStorage.setItem('shanye-visit-seq','0');return id;}
export const normalizedName=name=>name.normalize('NFKC').replace(/[\s\p{Cf}]/gu,'').toLocaleLowerCase();
export async function request(path,data={},session=''){
 const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),35000);
 try{
  await setupApi();
  const response=await fetch(API+path,{method:'POST',credentials:'same-origin',signal:abort.signal,keepalive:path==='/telemetry',headers:{'Content-Type':'application/json','X-Equipment-Visit':visitId(),...(session?{'X-Equipment-Member':session}:{})},body:JSON.stringify(data)});
  const result=await response.json();if(!response.ok){const e=new Error(result.error||'暂时没能保存，请重试');e.status=response.status;throw e;}return result;
 }catch(e){if(e.name==='AbortError')throw new Error('连接暂未完成，请保留草稿并重试');if(e instanceof TypeError)throw new Error('网络未连接，草稿已保留');throw e;}finally{clearTimeout(timer);}
}
