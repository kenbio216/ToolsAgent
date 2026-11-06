"""Owner-only usage analytics and private feedback for the equipment application."""
import datetime,ipaddress,json,re,time,uuid
from agent_guided import GuidedAgentService,declared_group_items,group_owners
from agent_service import stamp,text
from agent_catalog import BY_PERSON,PEOPLE,ACTIVE_IDS,CORE,BY_ITEM
from agent_collective import GROUP_BY_ID
from agent_geo import locate

STAGES={'entry':'姓名入口','personal':'个人装备','collective':'集体携带','borrow':'借还对话'}
VISIT=re.compile(r'[A-Za-z0-9_-]{16,80}')

def meta(h):
    ip=h.headers.get('X-Equipment-Client-IP','')[:80]
    try:ip=str(ipaddress.ip_address(ip))
    except ValueError:ip='未提供'
    return ip,h.headers.get('X-Equipment-User-Agent','')[:512]

def device(ua):
    system=next((label for word,label in [('iPhone','iPhone / iOS'),('iPad','iPad / iPadOS'),('Android','Android'),('Windows','Windows'),('Macintosh','Mac'),('Linux','Linux')] if word in ua),'未知设备')
    browser=next((label for word,label in [('MicroMessenger','微信内置浏览器'),('Edg/','Edge'),('CriOS/','Chrome'),('Chrome/','Chrome'),('Firefox/','Firefox'),('Safari/','Safari')] if word in ua),'未知浏览器')
    return system+' · '+browser

class ManagementAgentService(GuidedAgentService):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        with self.db() as d:
            d.executescript('''
            CREATE TABLE IF NOT EXISTS sheet_archives(name TEXT PRIMARY KEY,rows TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS visits(id TEXT PRIMARY KEY,person TEXT DEFAULT '',created REAL,last REAL,stage TEXT,visible INTEGER,ip TEXT,ua TEXT,width INTEGER,height INTEGER,dpr REAL,seq INTEGER DEFAULT -1);
            CREATE TABLE IF NOT EXISTS dwell(visit TEXT,stage TEXT,ms INTEGER DEFAULT 0,PRIMARY KEY(visit,stage));
            CREATE TABLE IF NOT EXISTS visit_events(id INTEGER PRIMARY KEY,visit TEXT,at REAL,stage TEXT,visible INTEGER);
            CREATE TABLE IF NOT EXISTS request_log(id INTEGER PRIMARY KEY,at REAL,person TEXT,visit TEXT,ip TEXT,ua TEXT,path TEXT,status INTEGER,ms REAL,owner INTEGER);
            CREATE INDEX IF NOT EXISTS request_time ON request_log(at);
            CREATE INDEX IF NOT EXISTS request_person ON request_log(person,at);
            CREATE INDEX IF NOT EXISTS request_visit ON request_log(visit,at);
            CREATE INDEX IF NOT EXISTS visit_person ON visits(person,last);
            CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,request TEXT UNIQUE,person TEXT,visit TEXT,content TEXT,category TEXT,contact TEXT,state TEXT,created TEXT,ip TEXT,ua TEXT,stage TEXT);
            ''')
            d.execute("INSERT OR IGNORE INTO settings VALUES('analytics_started',?)",(stamp(),))
        self._last_cleanup=0

    def optional_person(self,token):return self.session_person(token) if token else ''
    def telemetry(self,h,value,token):
        visit=value.get('visit','');stage=value.get('stage');seq=value.get('seq');elapsed=value.get('elapsedMs',0)
        if not isinstance(visit,str) or not VISIT.fullmatch(visit) or stage not in STAGES:raise ValueError('访问记录格式无效')
        if isinstance(seq,bool) or not isinstance(seq,int) or not 0<=seq<10**10:raise ValueError('访问序号无效')
        if isinstance(elapsed,bool) or not isinstance(elapsed,(int,float)):raise ValueError('时长格式无效')
        elapsed=max(0,min(30000,int(elapsed)));visible=bool(value.get('visible'));person=self.optional_person(token);ip,ua=meta(h);now=time.time()
        def number(key,lo,hi,default):
            x=value.get(key,default)
            return max(lo,min(hi,float(x))) if isinstance(x,(int,float)) and not isinstance(x,bool) else default
        width=int(number('width',0,20000,0));height=int(number('height',0,20000,0));dpr=number('dpr',.1,10,1)
        with self.db() as d:
            d.execute('BEGIN IMMEDIATE');prior=d.execute('SELECT * FROM visits WHERE id=?',(visit,)).fetchone()
            if prior and seq<=prior['seq']:return {'ok':True,'duplicate':True}
            if prior and prior['person'] and person and prior['person']!=person:raise ValueError('姓名切换后请重新记录本次访问')
            owner_person=person or (prior['person'] if prior else '')
            if prior:
                elapsed=min(elapsed,max(0,int((now-prior['last'])*1000)+1500))
                d.execute('UPDATE visits SET person=?,last=?,stage=?,visible=?,ip=?,ua=?,width=?,height=?,dpr=?,seq=? WHERE id=?',(owner_person,now,stage,int(visible),ip,ua,width,height,dpr,seq,visit))
            else:
                elapsed=0;d.execute('INSERT INTO visits VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(visit,person,now,now,stage,int(visible),ip,ua,width,height,dpr,seq))
            if elapsed:
                duration_stage=value.get('durationStage',prior['stage'] if prior else stage)
                if duration_stage not in STAGES:duration_stage=stage
                d.execute('INSERT INTO dwell VALUES(?,?,?) ON CONFLICT(visit,stage) DO UPDATE SET ms=ms+excluded.ms',(visit,duration_stage,elapsed))
            if not prior or prior['stage']!=stage or prior['visible']!=int(visible):d.execute('INSERT INTO visit_events(visit,at,stage,visible) VALUES(?,?,?,?)',(visit,now,stage,int(visible)))
        return {'ok':True}

    def track_request(self,h,status,elapsed_ms):
        ip,ua=meta(h);token=h.headers.get('X-Equipment-Member','');visit=h.headers.get('X-Equipment-Visit','')
        if not VISIT.fullmatch(visit):visit=''
        try:person=self.optional_person(token)
        except (PermissionError,ValueError):person=''
        path=h.path.split('?',1)[0].removeprefix('/agent');owner=h.headers.get('X-Equipment-Owner')=='1';now=time.time()
        with self.db() as d:
            d.execute('INSERT INTO request_log(at,person,visit,ip,ua,path,status,ms,owner) VALUES(?,?,?,?,?,?,?,?,?)',(now,person,visit,ip,ua,path,status,round(elapsed_ms,2),int(owner)))
            if now-self._last_cleanup>3600:
                d.execute('DELETE FROM request_log WHERE at<?',(now-30*86400,));self._last_cleanup=now

    def feedback_submit(self,h,value,token):
        content=text(value.get('content',''),2000);category=value.get('category','suggestion');contact=text(value.get('contact',''),100);req=text(value.get('requestId',''),100)
        if len(content)<2 or category not in ['bug','catalog','suggestion','other'] or not VISIT.fullmatch(req):raise ValueError('请填写反馈内容后提交')
        person=self.optional_person(token);ip,ua=meta(h);visit=value.get('visit','');stage=value.get('stage','entry')
        if not isinstance(visit,str) or not VISIT.fullmatch(visit):visit=''
        if stage not in STAGES:stage='entry'
        with self.db() as d:
            d.execute('BEGIN IMMEDIATE');old=d.execute('SELECT id,person FROM feedback WHERE request=?',(req,)).fetchone()
            if old:
                if old['person']!=person:raise PermissionError('反馈编号已使用')
                return {'id':old['id'],'duplicate':True}
            recent=d.execute('SELECT COUNT(*) FROM feedback WHERE ip=? AND created>?',(ip,(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))-datetime.timedelta(hours=1)).isoformat(timespec='seconds'))).fetchone()[0]
            if recent>=30:raise ValueError('本小时反馈较多，请稍后再提交')
            ident=uuid.uuid4().hex;d.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ident,req,person,visit,content,category,contact,'new',stamp(),ip,ua,stage))
        return {'id':ident}

    def guided_state(self,p,owner):
        result=super().guided_state(p,owner)
        with self.db() as d:updated=d.execute("SELECT 1 FROM jobs WHERE person=? AND error='catalog_updated_raincoat_shell_pants' LIMIT 1",(p,)).fetchone()
        result['catalogNotice']=bool(updated);return result

    def on_record_confirmed(self,d,event,value,job):
        super().on_record_confirmed(d,event,value,job)
        f=value.get('feedback')
        if not f:return
        if not isinstance(f,dict) or f.get('category') not in ('bug','catalog','suggestion','other'):raise ValueError('请选择有效的意见类型')
        content=text(f.get('content',''),2000)
        if len(content)<2:raise ValueError('请说明要反馈的内容')
        visit=d.execute('SELECT id,ip,ua FROM visits WHERE person=? ORDER BY last DESC LIMIT 1',(event['person'],)).fetchone()
        d.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,value['requestId'],event['person'],visit['id'] if visit else '',content,f['category'],'','new',event['created'],visit['ip'] if visit else '',visit['ua'] if visit else '','borrow'))

    @staticmethod
    def visit_data(row,durations):
        r=dict(row);r['device']=device(r['ua']);r['online']=r['last']>time.time()-45 and bool(r['visible']);r['durations']=durations;r['visibleMs']=sum(durations.values());r['location']=locate(r['ip']);return r

    def overview(self,value):
        now=time.time();days=value.get('days',7)
        if isinstance(days,bool) or not isinstance(days,int) or days not in (1,7,30):days=7
        since=now-days*86400
        with self.db() as d:
            started=d.execute("SELECT value FROM settings WHERE key='analytics_started'").fetchone()[0]
            regs=[dict(r) for r in d.execute('''SELECT r.*,(SELECT COUNT(*) FROM messages m WHERE m.person=r.id AND m.role='user') messages,
                (SELECT COUNT(*) FROM events e WHERE e.person=r.id) records FROM registrations r ORDER BY r.created DESC''')]
            visits=[dict(r) for r in d.execute('SELECT * FROM visits WHERE last>=? ORDER BY last DESC LIMIT 500',(since,))]
            dwell_rows=d.execute('SELECT * FROM dwell').fetchall();durations={}
            for r in dwell_rows:durations.setdefault(r['visit'],{})[r['stage']]=r['ms']
            totals={k:d.execute(sql,params).fetchone()[0] for k,sql,params in [
                ('registrations','SELECT COUNT(*) FROM registrations',()),('visits','SELECT COUNT(*) FROM visits WHERE last>=?',(since,)),
                ('active','SELECT COUNT(*) FROM visits WHERE last>? AND visible=1',(now-45,)),
                ('requests60','SELECT COUNT(*) FROM request_log WHERE at>? AND path NOT LIKE \'/admin/%\'',(now-60,)),
                ('requestsHour','SELECT COUNT(*) FROM request_log WHERE at>? AND path NOT LIKE \'/admin/%\'',(now-3600,)),
                ('errorsHour','SELECT COUNT(*) FROM request_log WHERE at>? AND status>=400 AND path NOT LIKE \'/admin/%\'',(now-3600,)),
                ('newFeedback',"SELECT COUNT(*) FROM feedback WHERE state='new'",())]}
            ips=[dict(r) for r in d.execute("SELECT ip,COUNT(*) requests,SUM(CASE WHEN at>? THEN 1 ELSE 0 END) perMinute,MAX(at) last FROM request_log WHERE at>? AND path NOT LIKE '/admin/%' GROUP BY ip ORDER BY requests DESC",(now-60,now-3600))]
            rates=[dict(r) for r in d.execute("SELECT CAST(at/60 AS INTEGER)*60 bucket,COUNT(*) count FROM request_log WHERE at>? AND path NOT LIKE '/admin/%' GROUP BY bucket ORDER BY bucket",(now-3600,))]
            feedback=[dict(r) for r in d.execute('SELECT * FROM feedback ORDER BY created DESC LIMIT 500')]
            by_person={}
            for r in d.execute('SELECT person,COUNT(*) requests,SUM(CASE WHEN status>=400 THEN 1 ELSE 0 END) errors FROM request_log WHERE at>? GROUP BY person',(now-3600,)):by_person[r['person']]=dict(r)
        visits=[self.visit_data(v,durations.get(v['id'],{})) for v in visits]
        for row in ips:row['location']=locate(row['ip'])
        for r in regs:
            own=[v for v in visits if v['person']==r['id']];r.update(matched=r['roster'] in ACTIVE_IDS,profileName=BY_PERSON.get(r['id'],{}).get('name',r['name']),visits=own,requestsHour=by_person.get(r['id'],{}).get('requests',0),errorsHour=by_person.get(r['id'],{}).get('errors',0))
        for f in feedback:f['name']=BY_PERSON.get(f['person'],{}).get('name','未填写姓名')
        return {'started':started,'days':days,'totals':totals,'people':regs,'visits':visits,'durations':STAGES,'rates':rates,'ips':ips,'feedback':feedback,'limits':{'visits':500,'feedback':500,'requestRetentionDays':30},'at':stamp()}

    def person_detail(self,p):
        with self.db() as d:
            if not d.execute('SELECT 1 FROM members WHERE person=?',(p,)).fetchone():raise KeyError('登记不存在')
            messages=[dict(r) for r in d.execute("SELECT m.id,m.role,m.content,m.created,COALESCE(s.stage,'legacy') stage FROM messages m LEFT JOIN message_scopes s ON s.id=m.id WHERE m.person=? ORDER BY m.id DESC LIMIT 1000",(p,))][::-1]
            jobs=[]
            for row in d.execute("SELECT j.id,j.state,j.created,j.error,j.confirmed,j.receipt,j.answer,COALESCE(s.stage,'legacy') stage FROM jobs j LEFT JOIN job_scopes s ON s.job=j.id WHERE j.person=? ORDER BY j.rowid DESC LIMIT 200",(p,)):
                r=dict(row);r['receipt']=json.loads(r['receipt']);r['answer']=json.loads(r['answer']);jobs.append(r)
            visits=[dict(r) for r in d.execute('SELECT * FROM visits WHERE person=? ORDER BY last DESC',(p,))]
            durations={}
            for v in visits:durations[v['id']]={r['stage']:r['ms'] for r in d.execute('SELECT * FROM dwell WHERE visit=?',(v['id'],))}
            feedback=[dict(r) for r in d.execute('SELECT * FROM feedback WHERE person=? ORDER BY created DESC',(p,))]
        state=self.guided_state(p,True)
        with self.db() as d:
            events=[]
            for row in d.execute('SELECT id,state,error,created,data FROM events WHERE person=? ORDER BY rowid DESC LIMIT 200',(p,)):
                r=dict(row);raw=json.loads(r.pop('data'));r['kind']=raw.get('kind','equipment');r['entries']=raw.get('entries',[]);r['feedback']=raw.get('feedback');r['noBorrow']=bool(raw.get('noBorrow'));r['collective']=[{'name':GROUP_BY_ID.get(k,{}).get('name',k),**v} for k,v in raw.get('collective_after',{}).items()];events.append(r)
        state['events']=events
        state.update(messages=messages,jobs=jobs,visits=[self.visit_data(v,durations[v['id']]) for v in visits],feedback=feedback);return state

    def inventory(self):
        from agent_inventory import human_checks
        team={p['id']:self.profile(p['id']) for p in PEOPLE}
        with self.db() as d:
            event_rows=d.execute('SELECT * FROM events ORDER BY rowid').fetchall()
            for row in event_rows:
                raw=json.loads(row['data']);target=raw.get('target',row['person'])
                if target in team and row['state'] in ('pending','conflict'):
                    for item,value in raw.get('after',{}).items():
                        if item in team[target]['items']:team[target]['items'][item]=value
            carrying=[];group_rows={}
            for row in d.execute('SELECT * FROM group_items WHERE checked=1'):
                if row['person'] in team:
                    group_rows[(row['person'],row['item'])]=dict(row)
                    carrying.append({'name':BY_PERSON[row['person']]['name'],'item':GROUP_BY_ID.get(row['item'],{}).get('name',row['item']),'quantity':row['quantity']})
            archives=[{'name':r['name'],'rows':json.loads(r['rows']),'created':r['created']} for r in d.execute('SELECT * FROM sheet_archives')]
        collective_confirmed={p:set() for p in team}
        for row in event_rows:
            raw=json.loads(row['data'])
            target=raw.get('target') or raw.get('sharedSource') or row['person']
            if target in team:collective_confirmed[target].update(declared_group_items(raw))
        collective=[]
        for item in GROUP_BY_ID.values():
            members=[]
            for p in PEOPLE:
                row=group_rows.get((p['id'],item['id']));checked=bool(row);n=row['quantity'] if row else None
                status=('已登记' if n is not None else '数量待填') if checked else ('未携带' if item['id'] in collective_confirmed[p['id']] else '未登记')
                members.append({**p,'checked':checked,'quantity':n,'status':status,'assigned':p['name'] in group_owners(item)})
            known=sum(p['quantity'] for p in members if p['checked'] and p['quantity'] is not None)
            pending=sum(p['status']=='数量待填' for p in members)
            planned=int(item['total']) if str(item['total']).isdigit() else None
            collective.append({**item,'planned':planned,'registered':known,'pendingPeople':pending,'checkedPeople':sum(p['checked'] for p in members),'unregisteredPeople':sum(p['status']=='未登记' for p in members),'remaining':max(0,planned-known) if planned is not None else None,'people':members})
        summaries=[]
        for i in CORE:
            own=sum(p['items'][i['id']]['owned'] for p in team.values());borrowed=sum(max(0,p['items'][i['id']]['borrowed']-p['items'][i['id']]['returned']) for p in team.values())
            summaries.append({**i,'requiredTotal':i['required']*len(PEOPLE),'owned':own,'borrowedOpen':borrowed,'registered':own+borrowed})
        people=[]
        for p in PEOPLE:
            profile=team[p['id']];cells,_=human_checks(profile['items']);people.append({'id':p['id'],'name':p['name'],'checks':dict(zip([i['id'] for i in CORE],cells))})
        events=[]
        for row in event_rows[-100:][::-1]:
            raw=json.loads(row['data']);lines=[];changes=[]
            if raw.get('collectiveProposals'):lines=[GROUP_BY_ID[e['item']]['name']+' '+('补报携带 '+str(e['quantity'] if e['quantity'] is not None else '数量待填') if e['checked'] else '取消携带') for e in raw['collectiveProposals']]
            elif raw.get('kind')=='collective':lines=[GROUP_BY_ID.get(k,{}).get('name',k)+' '+str(v.get('quantity') if v.get('quantity') is not None else '数量未填') for k,v in raw.get('collective_after',{}).items() if v.get('checked')]
            else:lines=[BY_ITEM.get(e['item'],{}).get('name',e['item'])+' '+{'self':'自带','borrow':'追加借用','loan_set':'本次借出总数','return':'归还','check':'核对','issue':'异常','pack':'装包'}.get(e['action'],e['action'])+' '+str(e['quantity']) for e in raw.get('entries',[])]
            for key,a in raw.get('after',{}).items():
                b=raw.get('before',{}).get(key,{})
                changes.append({'item':BY_ITEM.get(key,{}).get('name',key),'before':{k:b.get(k,0) for k in ('owned','borrowed','returned')},'after':{k:a.get(k,0) for k in ('owned','borrowed','returned')}})
            if raw.get('noBorrow'):lines=['本次未向协会借装备；所有装备借出、归还均设为0，原流水保留']+(lines if raw.get('collectiveProposals') else [])
            if raw.get('feedback'):lines.append('意见：'+raw['feedback']['content'])
            events.append({'id':row['id'],'name':BY_PERSON.get(row['person'],{}).get('name','未知登记'),'created':row['created'],'state':row['state'],'kind':raw.get('kind','equipment'),'changes':changes,'description':'；'.join(lines) or ('确认本次不携带集体装备' if raw.get('kind')=='collective' else '装备记忆')})
        return {'core':CORE,'summary':summaries,'people':people,'carrying':carrying,'collective':collective,'events':events,'archives':archives}

    def requests(self,value):
        person=value.get('person');visit=value.get('visit');offset=value.get('offset',0);minutes=value.get('minutes',60)
        if not isinstance(offset,int) or isinstance(offset,bool) or not 0<=offset<=100000:offset=0
        if minutes not in (60,1440,43200):minutes=60
        clauses=['at>=?'];params=[time.time()-minutes*60]
        if person:clauses.append('person=?');params.append(text(person,80))
        if visit:clauses.append('visit=?');params.append(text(visit,80))
        if not value.get('includeAdmin'):clauses.append("path NOT LIKE '/admin/%'")
        with self.db() as d:
            rows=[dict(r) for r in d.execute('SELECT * FROM request_log WHERE '+' AND '.join(clauses)+' ORDER BY id DESC LIMIT 101 OFFSET ?',(*params,offset))]
        for r in rows:r['name']=BY_PERSON.get(r['person'],{}).get('name','未填写姓名');r['device']=device(r['ua']);r['location']=locate(r['ip'])
        return {'rows':rows[:100],'hasMore':len(rows)>100,'nextOffset':offset+100}

    def dispatch(self,h,path,value):
        value=value or {};token=h.headers.get('X-Equipment-Member','');owner=h.headers.get('X-Equipment-Owner')=='1'
        if path=='/telemetry':return self.telemetry(h,value,token)
        if path=='/feedback':return self.feedback_submit(h,value,token)
        if path.startswith('/admin/'):
            if not owner:raise PermissionError('仅本人尾网认证后可访问管理数据')
            if path=='/admin/overview':return self.overview(value)
            if path=='/admin/person':return self.person_detail(text(value.get('person',''),80))
            if path=='/admin/requests':return self.requests(value)
            if path=='/admin/inventory':return self.inventory()
            if path=='/admin/feedback-update':
                ident=value.get('id');state=value.get('state')
                if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident) or state not in ['new','processing','done']:raise ValueError('反馈状态无效')
                with self.db() as d:d.execute('UPDATE feedback SET state=? WHERE id=?',(state,ident))
                return {'ok':True}
        return super().dispatch(h,path,value)
