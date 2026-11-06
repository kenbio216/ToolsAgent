import React,{useEffect,useRef,useState} from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {Bot,MessageCircle,Mic,ArrowUp,Minus,X,Check,LoaderCircle,ArrowRight,RefreshCw} from 'lucide-react';
import VoiceInput from '../src/VoiceInput';
import {uuid} from '../src/api';

const emptyState={messages:[],drafts:[],activeJobs:[]};
const timestamp=value=>value?new Date(value).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}):'';

export default function OwnerAssistant({api,onChanged}){
 const [open,setOpen]=useState(false),[mobile,setMobile]=useState(()=>innerWidth<700),[viewport,setViewport]=useState(()=>({height:window.visualViewport?.height||innerHeight,top:window.visualViewport?.offsetTop||0}));
 const [data,setData]=useState(emptyState),[input,setInput]=useState(()=>sessionStorage.getItem('equipment-owner-ai-draft')||''),[loading,setLoading]=useState(false),[sending,setSending]=useState(false),[thinking,setThinking]=useState(false),[saving,setSaving]=useState(''),[voice,setVoice]=useState(false),[voiceBusy,setVoiceBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const apiRef=useRef(api),changedRef=useRef(onChanged),alive=useRef(true),polls=useRef(new Set()),commitRequests=useRef(new Map()),bottom=useRef(null),text=useRef(null);
 apiRef.current=api;changedRef.current=onChanged;
 const request=(path,value={})=>apiRef.current('/admin/ai'+path,value);
 useEffect(()=>()=>{alive.current=false;},[]);
 useEffect(()=>{const query=matchMedia('(max-width:699px)'),resize=()=>{setMobile(query.matches);setViewport({height:window.visualViewport?.height||innerHeight,top:window.visualViewport?.offsetTop||0});};query.addEventListener('change',resize);window.visualViewport?.addEventListener('resize',resize);window.visualViewport?.addEventListener('scroll',resize);addEventListener('resize',resize);return()=>{query.removeEventListener('change',resize);window.visualViewport?.removeEventListener('resize',resize);window.visualViewport?.removeEventListener('scroll',resize);removeEventListener('resize',resize);};},[]);
 useEffect(()=>{sessionStorage.setItem('equipment-owner-ai-draft',input);},[input]);
 useEffect(()=>{if(open)load(true);},[open]);
 useEffect(()=>{if(open)bottom.current?.scrollIntoView({block:'nearest',behavior:'smooth'});},[open,data.messages?.length,data.drafts?.length,thinking]);
 useEffect(()=>{if(!text.current)return;text.current.style.height='auto';text.current.style.height=Math.min(text.current.scrollHeight,100)+'px';},[input,open,voice]);
 async function load(showLoading=false){
  if(showLoading)setLoading(true);
  try{const next=await request('/state');if(!alive.current)return;setData({...emptyState,...next});setError('');for(const job of next.activeJobs||[])poll(job.id);}
  catch(e){if(alive.current)setError(e.status===401?'本人登录已过期，请重新打开管理页登录。':e.message);}
  finally{if(alive.current)setLoading(false);}
 }
 async function poll(id){
  if(polls.current.has(id))return;polls.current.add(id);setThinking(true);
  try{for(let i=0;i<180&&alive.current;i++){const job=await request('/job/'+id);if(job.state==='done'||['discarded','superseded'].includes(job.state)){await load();return;}if(job.state==='error'){await load();throw new Error(job.error||'本次整理未完成，请补充说明后再试。');}await new Promise(resolve=>setTimeout(resolve,1000));}if(alive.current)throw new Error('整理仍在进行，可稍后刷新对话查看。');}
  catch(e){if(alive.current)setError(e.message);}
  finally{polls.current.delete(id);if(alive.current)setThinking(polls.current.size>0);}
 }
 const busy=sending||thinking||!!saving||voiceBusy;
 async function send(event){
  event?.preventDefault();const message=input.trim();if(!message||busy)return;
  setSending(true);setError('');setNotice('');
  try{const result=await request('/chat',{message,requestId:uuid()});if(!alive.current)return;setInput('');await load();poll(result.job);}
  catch(e){if(alive.current)setError(e.message);}
  finally{if(alive.current)setSending(false);}
 }
 async function confirm(job){
  if(busy)return;setSaving(job.id);setError('');setNotice('');
  if(!commitRequests.current.has(job.id))commitRequests.current.set(job.id,uuid());
  try{const result=await request('/commit',{job:job.id,requestId:commitRequests.current.get(job.id)});if(!alive.current)return;setNotice(result.summary||'修改已确认，管理页数据已刷新。');await load();changedRef.current?.();}
  catch(e){if(alive.current)setError(e.message);}
  finally{if(alive.current)setSaving('');}
 }
 async function dismiss(job){
  if(busy)return;setSaving(job.id);setError('');try{await request('/dismiss',{job:job.id});if(alive.current){await load();setNotice('已取消这份修改草稿。');}}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setSaving('');}
 }
 function close(){if(voiceBusy){setError('请先结束录音，或等待转文字完成。');return;}setOpen(false);}
 const panel=<><div className="owner-ai-heading"><div><Bot size={23}/><div><h2 id="owner-ai-title">装备管理助手</h2><p id="owner-ai-description">先核对修改内容，确认后才保存。</p></div></div><button type="button" className="owner-ai-icon" disabled={voiceBusy} onClick={close} aria-label={mobile?'关闭管理助手':'收起管理助手'}>{mobile?<X size={21}/>:<Minus size={21}/>}</button></div>
 <div className="owner-ai-messages" aria-live="polite">{loading&&!data.messages.length?<div className="owner-ai-empty"><LoaderCircle className="spin" size={23}/><p>正在读取对话…</p></div>:!data.messages.length?<div className="owner-ai-empty"><MessageCircle size={30}/><p>告诉我谁的哪项记录需要修改。</p><small>例如把误填的动力绳改为静力绳，或补登记实际领取的装备。</small></div>:data.messages.map((message,index)=><article className={'owner-ai-message owner-ai-'+message.role} key={message.id||index}><div><strong>{message.role==='user'?'我':'管理助手'}</strong><time>{timestamp(message.created)}</time></div><p>{message.content}</p></article>)}
 {thinking&&<div className="owner-ai-thinking" role="status"><LoaderCircle size={17} className="spin"/>正在整理修改草稿…</div>}
 {(data.drafts||[]).map(job=><div className="owner-ai-draft" data-owner-draft={job.id} key={job.id}><div className="owner-ai-draft-heading"><strong>待确认修改</strong><span>{job.preview?.person?.name||'请核对修改对象'}</span></div>{!job.preview?.lines?.length?<p className="owner-ai-empty-preview">修改明细尚未完整，请取消草稿并补充说明。</p>:<div className="owner-ai-change-list">{job.preview.lines.map((line,index)=><div className="owner-ai-change" key={index}><strong>{line.label}</strong><div><span>{line.before??'未登记'}</span><ArrowRight size={15}/><b>{line.after??'未登记'}</b></div></div>)}</div>}<div className="owner-ai-draft-actions"><button type="button" className="button primary" disabled={busy||!job.preview?.lines?.length||!job.preview?.person?.id} onClick={()=>confirm(job)}>{saving===job.id?<LoaderCircle size={16} className="spin"/>:<Check size={16}/>}确认修改</button><button type="button" className="button" disabled={busy} onClick={()=>dismiss(job)}>取消</button></div></div>)}
 <div ref={bottom}/></div>
 <div className="owner-ai-composer">{error&&<div className="owner-ai-error" role="alert"><p>{error}</p><button type="button" className="owner-ai-icon" aria-label="关闭助手提示" onClick={()=>setError('')}><X size={17}/></button></div>}{notice&&<p className="owner-ai-notice" role="status">{notice}</p>}
 {voice?<VoiceInput api={request} disabled={sending||thinking||!!saving} onText={value=>{setInput(old=>old?old+'\n'+value:value);setVoice(false);setTimeout(()=>text.current?.focus(),30);}} onError={setError} onBusy={setVoiceBusy} onKeyboard={()=>setVoice(false)}/>:<form onSubmit={send}><textarea ref={text} rows={2} maxLength={3000} aria-label="向管理助手说明修改" placeholder="说说需要修改谁的装备记录…" value={input} onChange={event=>setInput(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();send();}}}/><div className="owner-ai-controls"><button type="button" className="owner-ai-icon" aria-label="管理助手语音输入" disabled={busy} onClick={()=>setVoice(true)}><Mic size={22}/></button><button type="button" className="owner-ai-icon" aria-label="刷新管理助手对话" disabled={busy||loading} onClick={()=>load(true)}><RefreshCw size={18}/></button><span>修改后保留流水</span><button type="submit" className="owner-ai-send" aria-label="发送管理助手消息" disabled={busy||!input.trim()}>{sending?<LoaderCircle size={19} className="spin"/>:<ArrowUp size={22}/>}</button></div></form>}
 </div></>;
 const viewStyle={'--owner-viewport-height':viewport.height+'px','--owner-viewport-top':viewport.top+'px'};
 return <><button type="button" className={'owner-ai-launcher '+(open?'owner-ai-launcher-hidden':'')} onClick={()=>setOpen(true)} aria-label="打开管理AI助手" aria-expanded={open} aria-controls="owner-ai-panel"><Bot size={23}/><span>管理助手</span>{data.drafts?.length>0&&<b>{data.drafts.length}</b>}</button>{!mobile&&open&&<aside id="owner-ai-panel" className="owner-ai-panel" role="region" aria-labelledby="owner-ai-title" style={viewStyle}>{panel}</aside>}{mobile&&<Dialog.Root open={open} onOpenChange={value=>value?setOpen(true):close()}><Dialog.Portal><Dialog.Overlay className="owner-ai-overlay"/><Dialog.Content id="owner-ai-panel" className="owner-ai-panel owner-ai-mobile" style={viewStyle} aria-labelledby="owner-ai-title" aria-describedby="owner-ai-description" onOpenAutoFocus={event=>event.preventDefault()} onEscapeKeyDown={event=>{if(voiceBusy)event.preventDefault();}}><Dialog.Title className="owner-ai-sr">装备管理助手</Dialog.Title><Dialog.Description className="owner-ai-sr">核对AI整理的修改草稿，确认后保存。</Dialog.Description>{panel}</Dialog.Content></Dialog.Portal></Dialog.Root>}</>;
}
