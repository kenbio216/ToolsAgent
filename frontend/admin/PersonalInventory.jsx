import React,{useState} from 'react';

const categories=[['all','全部必带'],['technical','个人技术装备'],['borrowable','其他可借必带'],['self','仅自备物品']];
const amount=(value,unit='')=>value===null||value===undefined?'未登记':`${value}${unit}`;

function Person({person,unit}){
 return <div className={'personal-person personal-person-'+person.tone} data-person={person.id}>
  <div className="personal-person-heading"><strong>{person.name}</strong><span>{person.status}</span></div>
  <div className="personal-person-values"><span>自带 <b>{Number.isFinite(person.owned)?amount(person.owned,unit):'未说明'}</b></span><span>协会未还 <b>{Number.isFinite(person.borrowedOpen)?amount(person.borrowedOpen,unit):'未说明'}</b></span><span>持有合计 <b>{Number.isFinite(person.held)?amount(person.held,unit):'未说明'}</b></span></div>
  {person.carrying>0&&<small>第二步已确认携带 {person.carrying}{unit}，合计不重复计数</small>}
  {person.detail&&<small>{person.detail}</small>}
 </div>;
}

export default function PersonalInventory({items=[]}){
 const [category,setCategory]=useState('all');
 const shown=category==='all'?items:items.filter(i=>i.category===category);
 return <section className="personal-section" aria-labelledby="personal-overview-title">
  <h2 id="personal-overview-title">个人必带装备总览</h2>
  <p className="hint">按个人装备计划逐项汇总，自带与协会借用分开。这里显示已确认的登记情况；数量足额不代表已现场检查或装包。选带物品不计入必带总览。</p>
  <div className="personal-categories" aria-label="必带装备分类">{categories.map(([key,label])=><button type="button" key={key} aria-pressed={category===key} data-category={key} onClick={()=>setCategory(key)}>{label}<span>{key==='all'?items.length:items.filter(i=>i.category===key).length}</span></button>)}</div>
  <div className="carry-legend personal-legend"><span><i className="solid"/>有足额登记</span><span><i className="pending"/>不足 / 待核对 / 未准备</span><span><i className="outline"/>未登记 / 待说明</span><span><i className="issue"/>状态待检查</span></div>
  <div className="carry-grid personal-grid">{shown.map(item=>{
   const people=item.people||[],totalPeople=people.length,allReady=totalPeople>0&&item.readyPeople===totalPeople;
   const issue=people.some(p=>p.tone==='issue');
   const hasQuantity=Number.isFinite(item.registered)&&people.some(p=>Number.isFinite(p.held)),hasOwned=people.some(p=>Number.isFinite(p.owned)),hasBorrowed=people.some(p=>Number.isFinite(p.borrowedOpen));
   const state=issue?'issue':allReady?'complete':item.attentionPeople?'pending':item.registered>0?'partial':'empty';
   const progressLabel=item.category==='technical'?'足额并已核对':'已有足额登记';
   return <article key={item.id} data-personal-item={item.id} className={'carry-card personal-card personal-'+state}>
    <div className="carry-title"><div><h3>{item.name}</h3><p className="personal-category-label">{item.categoryLabel}</p></div><span className={'carry-state personal-state-'+state}>{issue?'状态待检查':!item.tracked?'待本人说明':allReady?(item.category==='technical'?'全员已核对':'全员有足额登记'):item.attentionPeople?'有待核实':item.registered>0?'已登记部分':'尚未登记'}</span></div>
    <div className="carry-totals personal-totals"><div><span>全队计划</span><strong>{item.requiredTotal??'未定量'}<small>{item.requiredTotal!==null?item.unit:''}</small></strong><small>{item.requiredEach===null?'按个人需求核实':`每人 ${item.requiredEach}${item.unit}`}</small></div><div><span>已登记持有</span><strong className={item.registered>0?'green':''}>{hasQuantity?item.registered:'未登记'}<small>{hasQuantity?item.unit:''}</small></strong></div></div>
    <div className="personal-source-totals"><span>自带 <strong>{hasOwned?amount(item.ownedTotal,item.unit):'未登记'}</strong></span><span>协会未还 <strong>{hasBorrowed?amount(item.borrowedOpenTotal,item.unit):'未登记'}</strong></span>{item.collectiveOnlyTotal>0&&<span>另有携带记录 <strong>{item.collectiveOnlyTotal}{item.unit}</strong></span>}</div>
    {item.tracked?<><div className="carry-progress personal-progress" role="img" aria-label={`${progressLabel} ${item.readyPeople} / ${totalPeople} 人`}><i style={{width:(totalPeople?item.readyPeople/totalPeople*100:0)+'%'}}/></div><div className="personal-readiness"><span>{progressLabel}</span><strong>{item.readyPeople} / {totalPeople} 人</strong></div><div className="carry-gaps personal-gaps">{item.remaining!==null&&item.remaining>0&&<span>按逐人需求，尚待登记或补足 {item.remaining}{item.unit}</span>}{item.unregisteredPeople>0&&<span>{item.unregisteredPeople} 人尚未登记数量</span>}{item.attentionPeople>0&&<span className="carry-pending-note">{item.attentionPeople} 人需核实数量或状态</span>}{item.quantityReadyPeople>item.readyPeople&&<span>其中 {item.quantityReadyPeople-item.readyPeople} 人数量足额，核对或状态仍待确认</span>}</div></>:<p className="personal-plan-note">计划要求自备，当前尚无逐人数量登记；不会按计划自动算作持有。</p>}
    <details className="carry-members personal-members"><summary>逐人查看 · {totalPeople} 人</summary><div>{people.map(person=><Person key={person.id} person={person} unit={item.unit}/>)}</div></details>
   </article>;
  })}</div>
  {!shown.length&&<p className="empty">这个分类暂无必带装备计划。</p>}
 </section>;
}
