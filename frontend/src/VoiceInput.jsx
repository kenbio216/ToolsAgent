import React,{useEffect,useRef,useState} from 'react';
import {Mic,LoaderCircle,Keyboard,X} from 'lucide-react';
import {uuid} from './api';

export default function VoiceInput({api,onText,onError,onBusy,disabled,onKeyboard}){
 const [status,setStatus]=useState('idle'),[cancel,setCancel]=useState(false),[seconds,setSeconds]=useState(0),[hint,setHint]=useState('');
 const ref=useRef({held:false,recorder:null,stream:null,timer:null,stopTimer:null,cancel:false,start:0}),alive=useRef(true);
 useEffect(()=>()=>{alive.current=false;const g=ref.current;g.cancel=true;g.held=false;clearInterval(g.timer);clearTimeout(g.stopTimer);if(g.recorder?.state==='recording')g.recorder.stop();g.stream?.getTracks().forEach(t=>t.stop());},[]);
 function update(s){if(alive.current){setStatus(s);onBusy(!['idle','error'].includes(s));}}
 async function transcribe(blob){
  update('transcribing');
  try{
   const audio=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(blob);});
   const result=await api('/transcribe',{audio,mime:blob.type.split(';')[0],requestId:uuid()});
   for(let i=0;i<110&&alive.current;i++){
    const job=await api('/voice-job/'+result.job);
    if(job.state==='done'){onText(job.text);update('idle');return;}
    if(job.state==='error')throw new Error(job.error);
    await new Promise(r=>setTimeout(r,1000));
   }
   throw new Error('识别用时较长，请重试或键盘输入');
  }catch(e){if(alive.current){onError(e.message);update('idle');}}
 }
 function finish(forceCancel=false){
  const g=ref.current;g.held=false;if(forceCancel)g.cancel=true;
  if(g.recorder?.state==='recording')g.recorder.stop();
 }
 async function begin(event){
  event.preventDefault();if(disabled||status!=='idle')return;
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){onError('当前浏览器无法录音，请使用手机浏览器的HTTPS页面，或键盘输入');return;}
  const g=ref.current;g.held=true;g.cancel=false;g.y=event.clientY||0;setCancel(false);setHint('');setSeconds(0);
  try{event.currentTarget.setPointerCapture?.(event.pointerId);}catch{}
  update('permission');
  try{
   g.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   if(!g.held||!alive.current){g.stream.getTracks().forEach(t=>t.stop());update('idle');setHint('麦克风已就绪，请再次按住说话');return;}
   const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(t=>MediaRecorder.isTypeSupported(t));
   const rec=new MediaRecorder(g.stream,mime?{mimeType:mime,audioBitsPerSecond:48000}:{}),chunks=[];g.recorder=rec;g.start=performance.now();
   rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
   rec.onstop=()=>{
    clearInterval(g.timer);clearTimeout(g.stopTimer);g.stream?.getTracks().forEach(t=>t.stop());
    if(!alive.current)return;
    if(g.cancel){update('idle');setCancel(false);setHint('已取消录音');return;}
    if(performance.now()-g.start<400||!chunks.length){update('idle');setHint('按住说完再松开');return;}
    transcribe(new Blob(chunks,{type:rec.mimeType||mime||'audio/webm'}));
   };
   rec.onerror=()=>{g.cancel=true;finish(true);onError('录音中断，请重新按住说话');update('idle');};
   rec.start(200);update('recording');g.timer=setInterval(()=>alive.current&&setSeconds(Math.floor((performance.now()-g.start)/1000)),200);g.stopTimer=setTimeout(()=>finish(),60000);
  }catch(e){g.stream?.getTracks().forEach(t=>t.stop());update('idle');onError(e.name==='NotAllowedError'?'麦克风未获允许，请在浏览器设置中允许后重试':'麦克风暂不可用，请检查权限或键盘输入');}
 }
 return <div className="voice-input"><div className="voice-controls"><button type="button" className="icon-button" onClick={onKeyboard} aria-label="切换键盘输入" disabled={status!=='idle'}><Keyboard size={23}/></button><button type="button" className={'hold-button '+(status==='recording'?(cancel?'record-cancel':'record-active'):'')} disabled={disabled||status==='transcribing'} aria-label="按住说话，松开转文字，上滑取消" onContextMenu={e=>e.preventDefault()} onPointerDown={begin} onPointerMove={e=>{if(ref.current.held&&status==='recording'){const c=ref.current.y-e.clientY>65;ref.current.cancel=c;setCancel(c);}}} onPointerUp={()=>finish()} onPointerCancel={()=>finish(true)} onLostPointerCapture={()=>finish()} onKeyDown={e=>{if((e.key===' '||e.key==='Enter')&&!e.repeat)begin(e);}} onKeyUp={e=>{if(e.key===' '||e.key==='Enter')finish();}}>{status==='transcribing'?<><LoaderCircle size={20} className="spin"/>正在转成文字…</>:status==='permission'?'请允许麦克风':status==='recording'?<>{cancel?<X size={20}/>:<Mic size={21}/>} {cancel?'松开取消':`松开转文字 · ${seconds}s`}</>:<><Mic size={21}/>按住说话</>}</button></div><p className="voice-hint" role="status">{status==='recording'?(cancel?'本段录音将取消':'正在录音 · 上滑取消 · 最长60秒'):status==='transcribing'?'本机识别中，文字出现后可修改再发送':hint||'松开后转成文字，可修改再发送'}</p></div>;
}
