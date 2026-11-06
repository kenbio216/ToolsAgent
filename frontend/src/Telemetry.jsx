import {useEffect,useRef} from 'react';
import {request,visitId,newVisit} from './api';
export default function useTelemetry(person,stage,session){
 const tracker=useRef({at:performance.now(),stage:'entry',visible:!document.hidden,person:sessionStorage.getItem('shanye-visit-person')||''});
 const env=useRef({person,stage,session});env.current={person,stage,session};
 function flush(){
  const t=tracker.current,e=env.current,now=performance.now();
  if(e.person&&t.person&&e.person!==t.person){newVisit();t.at=now;}
  if(e.person){t.person=e.person;sessionStorage.setItem('shanye-visit-person',e.person);}
  const seq=Number(sessionStorage.getItem('shanye-visit-seq')||0)+1;sessionStorage.setItem('shanye-visit-seq',String(seq));
  const payload={visit:visitId(),seq,stage:e.stage,durationStage:t.stage,elapsedMs:t.visible?Math.min(30000,Math.max(0,Math.round(now-t.at))):0,visible:!document.hidden,width:innerWidth,height:innerHeight,dpr:devicePixelRatio};
  t.at=now;t.stage=e.stage;t.visible=!document.hidden;request('/telemetry',payload,e.session).catch(()=>{});
 }
 useEffect(()=>{flush();},[person,stage,session]);
 useEffect(()=>{const timer=setInterval(flush,15000);document.addEventListener('visibilitychange',flush);addEventListener('pagehide',flush);return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',flush);removeEventListener('pagehide',flush);};},[]);
}
