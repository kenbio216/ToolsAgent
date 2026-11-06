import React,{useState} from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {History,RefreshCw,X,ArrowRight} from 'lucide-react';
import PersonalInventory from './PersonalInventory';

const date=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'时间未记录';
const statusLabels={pending:'等待同步',synced:'已同步飞书',local:'仅管理页保存',conflict:'同步待核对',error:'同步异常'};
const num=value=>value===null||value===undefined?'—':value;
function eventTags(event){
 const changes=event.changes||[],tags=[];
 if(changes.some(c=>c.before.borrowed!==c.after.borrowed))tags.push(['borrow','借出数量变更']);
 if(changes.some(c=>c.before.returned!==c.after.returned))tags.push(['return','归还数量变更']);
 if(changes.some(c=>c.before.owned!==c.after.owned))tags.push(['owned','自带数量变更']);
 if(!tags.length)tags.push(['other',({collective:'集体携带核对',feedback:'意见反馈',essentials:'必备装备说明'})[event.kind]||'个人装备核对']);
 return tags;
}
function RecordJournal({events,open,onClose}){
 const [filter,setFilter]=useState('all');
 const visible=events.filter(e=>filter==='all'||filter==='attention'&&['pending','conflict','error'].includes(e.state)||eventTags(e).some(([k])=>k===filter));
 return <Dialog.Root open={open} onOpenChange={value=>!value&&onClose()}><Dialog.Portal><Dialog.Overlay className="modal-overlay"/><Dialog.Content className="person-modal inventory-journal"><div className="modal-header"><div><Dialog.Title>装备登记流水</Dialog.Title><Dialog.Description>最近 {events.length} 条确认记录；保留修改前后数量，当前数量以最新确认结果为准。</Dialog.Description></div><Dialog.Close className="icon" aria-label="关闭登记流水"><X size={23}/></Dialog.Close></div><div className="journal-filters" aria-label="流水筛选">{[['all','全部'],['borrow','借出变更'],['return','归还变更'],['attention','待处理']].map(([id,label])=><button key={id} type="button" aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label}</button>)}</div><div className="journal-scroll">{visible.map(e=><article className={'journal-record journal-'+e.state} key={e.id}><div className="journal-heading"><strong>{e.name}</strong><time>{date(e.created)}</time><span className={'record-state record-'+e.state}>{statusLabels[e.state]||e.state}</span></div><div className="journal-tags">{e.actor==='owner'&&<span className="movement movement-owned">负责人修正</span>}{eventTags(e).map(([kind,label])=><span className={'movement movement-'+kind} key={kind}>{label}</span>)}</div><p>{e.description}</p>{e.changes?.length>0&&<details className="journal-changes"><summary>查看修改前后 · {e.changes.length} 类装备</summary>{e.changes.map((c,index)=><div key={index}><strong>{c.item}</strong>{[['owned','自带'],['borrowed','借出总数'],['returned','已归还']].map(([key,label])=><div className={'change-value change-'+key} key={key}><span>{label}</span><b>{c.before[key]}</b><ArrowRight size={14}/><b>{c.after[key]}</b></div>)}</div>)}</details>}</article>)}{!visible.length&&<div className="empty">这个分类暂时没有登记流水。</div>}</div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

function checkTone(text){return /待检查|异常/.test(text)?'issue':/^已核对|^已带齐/.test(text)?'solid':/数量待补|不足|待核对/.test(text)&&text.includes('\n')||/数量待补|不足/.test(text)?'pending':'empty';}

function TechnicalInventory({data}){
 return <section className="technical-section"><div className="section-heading"><div><h2>个人技术装备数量核查</h2><p className="hint">自带与协会未还分开统计；逐人核实，某人多带不能抵消他人的缺项。</p></div><span className="inventory-count">{data.core.length} 类技术装备</span></div><div className="table-scroll"><table className="technical-table"><thead><tr><th>装备</th><th>全队需求</th><th>自带</th><th>协会未还</th><th>已登记合计</th><th>尚待登记或补足</th></tr></thead><tbody>{data.summary.map(i=>{
 const overview=data.personalOverview?.find(x=>x.id===i.id),remaining=overview?.remaining??Math.max(0,i.requiredTotal-i.registered);
 return <tr key={i.id}><td><strong>{i.name}</strong></td><td>{i.requiredTotal}<small className="inline-unit">{i.unit}</small></td><td><span className="inventory-number number-owned">{i.owned}</span></td><td><span className="inventory-number number-borrowed">{i.borrowedOpen}</span></td><td><strong className={i.registered?'quantity-known':'quantity-none'}>{i.registered}</strong></td><td><span className={'quantity-badge '+(remaining?'quantity-waiting':'quantity-enough')}>{remaining?`${remaining}${i.unit} 待登记或补足`:'已登记数量达到需求'}</span></td></tr>;
 })}</tbody></table></div><h3>逐人核对</h3><p className="hint">实色表示足额且已核对；黄色需要补数或复核，虚线表示尚未核对，红色表示装备状态待检查。</p><div className="table-scroll"><table className="people-table personal-check-table"><thead><tr><th>队员</th>{data.core.map(i=><th key={i.id}>{i.name}</th>)}</tr></thead><tbody>{data.people.map(p=><tr key={p.id}><td><strong>{p.name}</strong></td>{data.core.map(i=>{const text=p.checks[i.id]||'待核对',parts=text.split('\n');return <td key={i.id}><div className={'check-status check-'+checkTone(text)}><strong>{parts[0]}</strong>{parts.slice(1).map((line,index)=><small key={index}>{line}</small>)}</div></td>;})}</tr>)}</tbody></table></div></section>;
}

function RentalInventory({items=[]}){
 const [filter,setFilter]=useState('all');
 const visible=items.filter(i=>filter==='all'||filter==='outstanding'&&i.outstandingTotal>0||filter==='unknown'&&i.unknownPeople>0);
 return <div className="warehouse-personal"><h3 className="warehouse-subheading">个人领用装备</h3><p className="hint">借出总数、已归还和当前未还分别呈现，包含可选借用装备。只汇总已有登记；“—”表示尚未填写，不代表 0。</p><div className="rental-filters" aria-label="租借装备筛选">{[['all','全部装备'],['outstanding','有未还'],['unknown','有人未登记']].map(([key,label])=><button key={key} type="button" aria-pressed={filter===key} onClick={()=>setFilter(key)}>{label}</button>)}</div><div className="carry-grid rental-grid">{visible.map(item=>{
 const recorded=item.recordedPeople>0;
 return <article className={'rental-card '+(item.outstandingTotal>0?'rental-outstanding':recorded?'rental-recorded':'rental-unknown')} key={item.id} data-rental-item={item.id}><div className="carry-title"><h3>{item.name}</h3><span className={'rental-label '+(item.outstandingTotal>0?'label-outstanding':recorded?'label-returned':'label-unknown')}>{item.outstandingTotal>0?'仍有未还':recorded?(item.borrowedTotal===0&&item.returnedTotal===0?(item.unknownPeople?'已登记部分未借':'明确未借'):'已登记，无未还'):'尚未登记'}</span></div><div className="rental-totals">{[['borrowedTotal','借出总数','borrow'],['returnedTotal','已归还','return'],['outstandingTotal','当前未还','outstanding']].map(([key,label,color])=><div key={key}><span>{label}</span><strong className={'rental-'+color}>{recorded?item[key]:'—'}<small>{recorded?item.unit:''}</small></strong></div>)}</div><div className="rental-coverage"><span>{item.recordedPeople} 人已有借还登记</span>{item.unknownPeople>0&&<span>{item.unknownPeople} 人尚未填写</span>}</div><details className="carry-members rental-members"><summary>逐人查看借还</summary><div>{item.people.map(p=><div className={'rental-person '+(p.condition&&p.condition!=='正常'&&p.recorded?'rental-person-issue':p.outstanding>0?'rental-person-outstanding':p.recorded?'rental-person-recorded':'rental-person-unknown')} key={p.id}><div className="rental-person-heading"><strong>{p.name}</strong><span>{!p.active?'未关联 / 历史登记':p.group}</span></div><div className="rental-person-values"><span>借出 <b className="rental-borrow">{num(p.borrowed)}</b></span><span>已还 <b className="rental-return">{num(p.returned)}</b></span><span>未还 <b className="rental-outstanding">{num(p.outstanding)}</b></span></div><small>{!p.recorded?'尚未填写借还数量':p.condition&&p.condition!=='正常'?'状态待检查：'+p.condition:p.outstanding>0?'仍需登记归还':p.borrowed===0&&p.returned===0?'明确未借':'已登记，无未还'}</small></div>)}</div></details></article>;
 })}</div>{!visible.length&&<div className="empty">这个分类暂时没有装备。</div>}</div>;
}


function CollectiveWarehouse({items=[]}){
 return <div className="warehouse-collective"><h3 className="warehouse-subheading">公共装备</h3><p className="hint">以下依据已确认的实际携带记录。计划仅供参考；未登记的出库来源、归还情况仍待核实，不按计划自动填数。</p><div className="warehouse-collective-list">{items.map(item=>{
  const people=item.people||[],hasQuantity=people.some(p=>p.checked&&Number.isFinite(p.quantity)),allDeclined=people.length>0&&!item.unregisteredPeople&&!item.pendingPeople&&!people.some(p=>p.checked);
  return <details key={item.id} className={'warehouse-collective-row '+(hasQuantity?'warehouse-known':'warehouse-unknown')} data-warehouse-collective={item.id}><summary><span className="warehouse-kind">公共</span><strong>{item.name}</strong><span className="warehouse-actual">实际携带 <b>{hasQuantity||allDeclined?item.registered:'—'}</b>{hasQuantity||allDeclined?item.unit:''}</span><span className="warehouse-plan">计划 {item.planned??'未定量'}{item.planned!==null?item.unit:''}</span></summary><div className="warehouse-carry-note">{item.pendingPeople>0&&<span>{item.pendingPeople}人已确认携带，数量待填</span>}{item.unregisteredPeople>0&&<span>{item.unregisteredPeople}人尚未登记</span>}{allDeclined&&<span>已确认本次无携带记录</span>}<span>这里只展示携带登记，未将其写成个人借出或归还。</span></div><div className="warehouse-collective-people">{people.map(p=><div key={p.id} className={'warehouse-carrier '+(p.checked&&Number.isFinite(p.quantity)?'warehouse-carrier-known':'warehouse-carrier-unknown')}><strong>{p.name}</strong><span>{p.checked?(p.quantity===null?'确认携带，数量待填':p.quantity+item.unit):p.status||'未登记'}</span></div>)}</div></details>;
 })}</div>{!items.length&&<p className="empty">暂无公共装备登记。</p>}</div>;
}
function WarehouseInventory({data}){
 const [scope,setScope]=useState('all');
 const warehouse=data.warehouse||{personal:data.rentals||[],collective:data.collective||[]};
 return <section className="warehouse-section"><h2>所有从仓库带出装备总览</h2><p className="hint">个人领用与公共装备分别列示，自备装备不计入这里。个人借还以已确认数量为准，公共装备按实际携带记录查看。</p><div className="warehouse-tabs" aria-label="仓库装备范围">{[['all','全部'],['personal','个人领用'],['collective','公共装备']].map(([key,label])=><button type="button" key={key} aria-pressed={scope===key} data-warehouse-scope={key} onClick={()=>setScope(key)}>{label}<small>{key==='personal'?warehouse.personal.length:key==='collective'?warehouse.collective.length:warehouse.personal.length+warehouse.collective.length}类</small></button>)}</div>{scope!=='collective'&&<RentalInventory items={warehouse.personal}/>}{scope!=='personal'&&<CollectiveWarehouse items={warehouse.collective}/>}</section>;
}

export default function InventoryPanel({data,error,onRefresh,children}){
 const [journal,setJournal]=useState(false);
 return <><div className="inventory-topbar"><div><h2>装备明细</h2><p>个人核对、仓库带出与实际携带，分别查看最新确认结果。</p></div><div className="inventory-actions"><button className="button journal-open" type="button" onClick={()=>setJournal(true)}><History size={19}/>查看登记流水<span>{data.events.length}</span></button><button className="button" type="button" onClick={onRefresh}><RefreshCw size={17}/>刷新明细</button></div></div>{error&&<p className="error-banner">{error}</p>}<TechnicalInventory data={data}/><WarehouseInventory data={data}/>{children}<PersonalInventory items={data.personalOverview||[]}/>{data.archives.length>0&&<section><h2>旧辅助表迁移存档</h2><p className="hint">迁移时的只读快照，供追溯，不作为实时统计。飞书中的原表已收起。</p>{data.archives.map(a=><details key={a.name}><summary>{a.name} · {date(a.created)}</summary><div className="table-scroll"><table><tbody>{a.rows.filter(r=>r.some(Boolean)).map((r,index)=><tr key={index}>{r.map((c,j)=><td key={j}>{c}</td>)}</tr>)}</tbody></table></div></details>)}</section>}<RecordJournal events={data.events} open={journal} onClose={()=>setJournal(false)}/></>;
}
