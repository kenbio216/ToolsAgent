const labels={borrow:'借出装备登记',return:'归还装备登记'};

export function shortcutGuide(mode,state){
 if(!labels[mode])return null;
 if(mode==='borrow')return {label:labels[mode],reply:'请说说这次已经实际从协会领到了哪些装备、各多少。例如“抓绒1件、攀岩鞋1双”。如果还没实际领取，也可以直接说明。'};
 const outstanding=(state.catalog||[]).filter(i=>Math.max(0,(state.items[i.id]?.borrowed||0)-(state.items[i.id]?.returned||0))>0).sort((a,b)=>Number(!!a.required)-Number(!!b.required));
 const examples=outstanding.slice(0,2).map(i=>`${i.name}${state.items[i.id].borrowed-state.items[i.id].returned}${i.unit||'件'}`).join('、');
 return {label:labels[mode],reply:'请说明这次已经实际归还的装备、数量、状态，以及交给了谁。'+(examples?'目前登记的未还装备包括：'+examples+'。':'目前没有登记的协会未还数量；若之前漏登记，请一并说明原借用情况。')+'尚未实际交还的，请先不要记为归还。'};
}

export function shortcutMessage(mode,message){
 return labels[mode]?labels[mode]+'：\n'+(message||'请帮我识别照片中的装备，并先核实实际借还情况。'):message;
}

// Keep local prompts at the point they were selected, ahead of later saved replies.
export function conversationWithGuides(messages,guides){
 const result=[],anchors=new Map(guides.map(g=>{let anchor=0;if(g.after)messages.forEach((m,i)=>{if(m.role===g.after.role&&m.content===g.after.content&&m.created===g.after.created)anchor=i+1;});return [g.id,anchor];}));
 for(let i=0;i<=messages.length;i++){
  for(const guide of guides.filter(g=>anchors.get(g.id)===i)){
   result.push({key:guide.id+'-user',role:'user',content:guide.label});
   result.push({key:guide.id+'-assistant',role:'assistant',content:guide.reply});
  }
  if(i<messages.length)result.push({...messages[i],key:'saved-'+i});
 }
 return result;
}
