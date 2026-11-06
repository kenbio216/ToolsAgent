"""Explicit personal equipment sources; human summary without operational logs."""
import json
from agent_catalog import CORE,BY_ITEM,CATALOG


def recorded_actions(event_rows,team):
    recorded={}
    for row in event_rows:
        event=row if isinstance(row,dict) and 'data' not in row else json.loads(row['data'])
        source=event.get('sharedSource') or event.get('target') or event.get('person')
        if source not in team:continue
        for entry in event.get('entries',[]):recorded.setdefault((source,entry['item']),set()).add(entry['action'])
    return recorded


def personal_requirements(plan):
    """Core requirements override plan aliases; optional equipment stays out."""
    result=[{**i,'requiredEach':i['required'],'category':'technical','categoryLabel':'个人技术装备','tracked':True} for i in CORE]
    seen={i['id'] for i in CORE}
    for item in plan:
        if not item.get('required') or item['id'] in seen:continue
        seen.add(item['id'])
        catalog=BY_ITEM.get(item['id'])
        category='borrowable' if catalog else 'self'
        result.append({**item,'name':catalog['name'] if catalog else item['name'],
                       'unit':item.get('unit') or (catalog['unit'] if catalog else ''),
                       'requiredEach':item.get('quantity'),'category':category,
                       'categoryLabel':('其他可借必带 · 救生三件套' if item['id'] in ('headlamp','raincoat','blanket') else '其他可借必带') if catalog else '其他自备必带','tracked':bool(catalog)})
    return result


def personal_overview(team,plan,event_rows,declarations,group_rows):
    """Summarize canonical people once, preserving unknown quantities as null."""
    recorded=recorded_actions(event_rows,team)
    output=[]
    for item in personal_requirements(plan):
        people=[];required=item['requiredEach']
        for ident,profile in team.items():
            person=profile['person'];value=profile['items'].get(item['id']) if item['tracked'] else None
            owned=borrowed=held=carrying=None;verified=False;detail=[];quantity_ready=False;ready=False
            declaration=declarations.get((ident,item['id']),{})
            if value is None:
                status='待本人说明';tone='empty';detail.append('计划要求自备；当前未采集这项的实际数量')
            else:
                actions=recorded.get((ident,item['id']),set())
                owned=value['owned'] if value['owned']>0 or 'self' in actions else None
                borrowed=max(0,value['borrowed']-value['returned']) if value['borrowed']>0 or value['returned']>0 or actions & {'borrow','return','loan_set'} else None
                subtotal=(owned or 0)+(borrowed or 0)
                held=subtotal if subtotal>0 or owned is not None and borrowed is not None else None
                verified=bool(value.get('verified')) if value.get('verified') is not None else item['category']=='technical' and required is not None and value.get('packed',0)>=required
                radio=group_rows.get((ident,'radio_spare')) if item['id']=='radio' else None
                if radio and radio.get('checked') and radio.get('quantity') is not None and radio['quantity']>0:
                    carrying=radio['quantity'];held=max(held or 0,carrying)
                    detail.append('另有第二步实际携带记录；与个人数量取较大值，避免重复计数')
                if owned is None:detail.append('自带数量待说明')
                if borrowed is None:detail.append('协会未还数量待说明')
                if declaration.get('detail'):detail.append(declaration['detail'])
                quantity_ready=held is not None and required is not None and held>=required
                if value['condition']!='正常':status='状态待检查';tone='issue'
                elif declaration.get('status')=='unprepared':status='尚未准备';tone='pending'
                elif held is None:
                    if declaration.get('status')=='deferred':status='暂不补登记';tone='pending'
                    elif verified:status='数量待填';tone='pending'
                    elif owned is not None or borrowed is not None:status='待补持有说明';tone='pending'
                    else:status='未登记';tone='empty'
                elif required is None:status='数量待定';tone='pending'
                elif not quantity_ready:status='数量不足';tone='pending'
                elif item['category']=='technical' and not verified:status='待核对';tone='pending'
                else:status='已核对' if item['category']=='technical' else '已登记';tone='solid';ready=True
            people.append({'id':ident,'name':person['name'],'owned':owned,'borrowedOpen':borrowed,'carrying':carrying,
                           'held':held,'verified':verified,'confirmed':held is not None,'required':required,
                           'status':status,'tone':tone,'detail':'；'.join(detail),'ready':ready,'quantityReady':quantity_ready})
        tracked=item['tracked']
        output.append({**item,'requiredTotal':required*len(people) if required is not None else None,
                       'ownedTotal':sum(p['owned'] or 0 for p in people) if tracked else None,
                       'borrowedOpenTotal':sum(p['borrowedOpen'] or 0 for p in people) if tracked else None,
                       'collectiveOnlyTotal':sum(max(0,(p['carrying'] or 0)-(p['owned'] or 0)-(p['borrowedOpen'] or 0)) for p in people),
                       'registered':sum(p['held'] or 0 for p in people) if tracked else None,
                       # Surplus for one person cannot fill another's checklist.
                       'remaining':sum(max(0,required-(p['held'] or 0)) for p in people) if tracked and required is not None else None,
                       'readyPeople':sum(p['ready'] for p in people),'quantityReadyPeople':sum(p['quantityReady'] for p in people),
                       'unregisteredPeople':sum(p['held'] is None for p in people),'attentionPeople':sum(not p['ready'] for p in people),'people':people})
    return output


def rental_overview(team,event_rows):
    """Confirmed association borrowing, including explicit zero declarations."""
    recorded=recorded_actions(event_rows,team);output=[]
    for item in CATALOG:
        people=[]
        for ident,profile in team.items():
            value=profile['items'][item['id']];person=profile['person']
            known=bool(value['borrowed'] or value['returned'] or recorded.get((ident,item['id']),set()) & {'borrow','return','loan_set'})
            people.append({'id':ident,'name':person['name'],'group':person.get('group','未关联名单'),
                           'active':person.get('active',True),'recorded':known,'condition':value['condition'],
                           'borrowed':value['borrowed'] if known else None,'returned':value['returned'] if known else None,
                           'outstanding':max(0,value['borrowed']-value['returned']) if known else None})
        output.append({**item,'borrowedTotal':sum(p['borrowed'] or 0 for p in people),
                       'returnedTotal':sum(p['returned'] or 0 for p in people),'outstandingTotal':sum(p['outstanding'] or 0 for p in people),
                       'recordedPeople':sum(p['recorded'] for p in people),'unknownPeople':sum(not p['recorded'] for p in people),'people':people})
    return output

def human_checks(items):
    cells=[];missing=[]
    for i in CORE:
        a=items[i['id']];owned=a['owned'];borrowed=max(0,a['borrowed']-a['returned']);held=owned+borrowed
        verified=bool(a.get('verified')) if a.get('verified') is not None else a['packed']>=i['required']
        if a['condition']!='正常':status='待检查'
        elif verified and held>=i['required']:status=f'已核对\n自带{owned} · 借用{borrowed}'
        elif verified:status='数量待补'
        elif held:status=f'待核对\n自带{owned} · 借用{borrowed}'
        else:status='待核对'
        cells.append(status)
        if not status.startswith('已核对'):missing.append(i['name'])
    return cells,('全部足额核对' if not missing else '待核对：'+'、'.join(missing))
