"""Name entry and a single conversation with an independently confirmed checklist.

Each browser registration keeps its own conversation. Names are self-declared;
only exact normalized roster matches are eligible for the fixed Feishu workbook.
"""
import json,re,secrets,threading,time,unicodedata,uuid
from agent_service import AgentService,Conflict,digest,stamp,text
from agent_catalog import PEOPLE,ACTIVE_IDS,BY_PERSON,CORE,CATALOG,BY_ITEM


def normalized_name(value):
    value=unicodedata.normalize('NFKC',value)
    return ''.join(c for c in value if not c.isspace() and unicodedata.category(c)!='Cf').casefold()


class SimpleAgentService(AgentService):
    def __init__(self,*args,**kwargs):
        start=kwargs.pop('start',True)
        super().__init__(*args,start=False,**kwargs)
        with self.db() as d:
            d.execute('CREATE TABLE IF NOT EXISTS registrations(id TEXT PRIMARY KEY,name TEXT NOT NULL,normalized TEXT NOT NULL,roster TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,request TEXT UNIQUE NOT NULL)')
            d.execute('CREATE TABLE IF NOT EXISTS name_states(normalized TEXT PRIMARY KEY,person TEXT NOT NULL)')
            # Keep old browser conversations; choose their latest confirmed state once.
            for r in d.execute('SELECT r.* FROM registrations r ORDER BY COALESCE((SELECT MAX(rowid) FROM events e WHERE e.person=r.id),0) DESC,r.created DESC').fetchall():
                d.execute('INSERT OR IGNORE INTO name_states VALUES(?,?)',(r['normalized'],r['id']))
            rows=d.execute('SELECT * FROM registrations').fetchall()
        for r in rows:self.register_identity(r['id'],r['name'],r['roster'])
        if start:threading.Thread(target=self.sync_loop,daemon=True,name='equipment-sync').start()

    @staticmethod
    def register_identity(ident,name,roster):
        target=next((p for p in PEOPLE if p['id']==roster),None)
        BY_PERSON[ident]={'id':ident,'name':target['name'] if target else name,
            'group':target['group'] if target else '未关联十险名单','role':target['role'] if target else '登记人'}

    def enter(self,value):
        name=text(value.get('name',''),30)
        if not name or any(ord(c)<32 for c in name):raise ValueError('请填写你的姓名')
        request=text(value.get('requestId',''),100)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{12,100}',request):raise ValueError('请重新提交姓名')
        normalized=normalized_name(name)
        target=next((p['id'] for p in PEOPLE if normalized_name(p['name'])==normalized),None)
        with self.db() as d:
            d.execute('BEGIN IMMEDIATE')
            prior=d.execute('SELECT * FROM registrations WHERE request=?',(request,)).fetchone()
            if prior:
                if prior['normalized']!=normalized:raise ValueError('姓名已变更，请重新提交')
                ident=prior['id'];target=prior['roster'] if prior['roster'] in ACTIVE_IDS else None;name=prior['name']
            else:
                ident='entry_'+uuid.uuid4().hex;now=stamp()
                shared=d.execute('SELECT person FROM name_states WHERE normalized=?',(normalized,)).fetchone()
                source=target or (shared['person'] if shared else None)
                d.execute('INSERT INTO registrations VALUES(?,?,?,?,?,?,?)',(ident,name,normalized,target,now,now,request))
                d.execute('INSERT INTO members(person) VALUES(?)',(ident,))
                d.execute('INSERT OR IGNORE INTO name_states VALUES(?,?)',(normalized,ident))
                for item in CATALOG:
                    baseline=d.execute('SELECT * FROM items WHERE person=? AND item=?',(source,item['id'])).fetchone() if source else None
                    d.execute('INSERT INTO items(person,item,owned,borrowed,returned,packed,condition,verified) VALUES(?,?,?,?,?,?,?,?)',
                        (ident,item['id'],baseline['owned'] if baseline else 0,baseline['borrowed'] if baseline else 0,
                        baseline['returned'] if baseline else 0,baseline['packed'] if baseline else 0,baseline['condition'] if baseline else '正常',
                        int(bool(baseline['verified'])) if baseline and baseline['verified'] is not None else 0))
        self.register_identity(ident,name,target)
        code=self.invite(ident)['code']
        return {'session':code,'person':BY_PERSON[ident],'matched':bool(target),'matchedName':BY_PERSON[target]['name'] if target else None}

    def target_for(self,person):
        with self.db() as d:r=d.execute('SELECT roster FROM registrations WHERE id=?',(person,)).fetchone()
        target=r['roster'] if r else person
        return target if target in ACTIVE_IDS else None

    def record_source(self,d,person):
        r=d.execute('SELECT normalized,roster FROM registrations WHERE id=?',(person,)).fetchone()
        if not r:return person
        if r['roster'] in ACTIVE_IDS:return r['roster']
        shared=d.execute('SELECT person FROM name_states WHERE normalized=?',(r['normalized'],)).fetchone()
        return shared['person'] if shared else person

    def profile(self,person):
        result=super().profile(person)
        with self.db() as d:
            source=self.record_source(d,person)
            if source!=person:result['items']={r['item']:dict(r) for r in d.execute('SELECT * FROM items WHERE person=?',(source,))}
        checks,todo=self.feishu.check_cells(person,result['items'])
        result.update(completed=sum(c in ('已带齐','已核对') for c in checks),todo=todo)
        return result

    def session_person(self,token):
        person=self.authorize(False,token)
        with self.db() as d:r=d.execute('SELECT id FROM registrations WHERE id=?',(person,)).fetchone()
        if not r:raise PermissionError('请先填写姓名开始登记')
        return person

    def simple_state(self,person,owner):
        result=self.state(person,False)
        target=self.target_for(person)
        result.update(owner=bool(owner),matched=bool(target),matchedName=BY_PERSON[target]['name'] if target else None)
        return result

    def check_item(self,person,value):
        item=value.get('item');checked=value.get('checked')
        if item not in {i['id'] for i in CORE} or not isinstance(checked,bool):raise ValueError('请选择清单中的装备')
        record={'requestId':value.get('requestId'),'revision':self.profile(person)['revision'],
            'entries':[{'item':item,'action':'check','quantity':BY_ITEM[item]['required'] if checked else 0,
                'condition':'正常','receiver':'','detail':'确认有该项装备' if checked else '取消本次核对'}]}
        try:return self.record(person,record)
        except Conflict:
            # A checkbox is an absolute assertion; retry its unchanged intention once
            # against the latest revision, never overwrite borrowed/returned counts.
            record['revision']=self.profile(person)['revision'];return self.record(person,record)

    def extra_prompt(self,person):
        if not person.startswith('entry_'):return ''
        target=self.target_for(person)
        return '''
本次界面为简洁对话＋右侧可勾选清单，下列核对规则优先于前面的旧版装包规则：
清单勾选的唯一含义是“本人核对确认有该项装备”，不是自有、借用或装包。items.verified=1就是已核对，0表示未核对，不能因为0就断言实际没有。
当用户明确说已确认具有某项，可提出action=check，quantity为该项所需数量；取消核对为0。check不需要追问来源，不要求先登记self/borrow/pack。不要要求做来源表单、切换其他页或填写协会编号。
借用和归还仍用borrow/return，并区分意向与真实领取、真实归还；需要时简短追问数量、状态和接收人。只给最多两个相关问题。不要反复解释系统或输出大段操作指南。
当前登记名'''+('已匹配本次十险名单，确认后的记录由程序自动同步飞书。' if target else '未匹配本次十险名单。对话、核对和借还记录照常保存在管理员后台，暂不同步飞书；不要自称已经同步。')

    def after_sync(self,event):
        if event.get('sharedSource'):return # updated atomically on confirmation, never roll back a newer submission
        target=event.get('target')
        if not target or target==event['person']:return
        with self.db() as d:
            for item,a in event['after'].items():
                d.execute('UPDATE items SET owned=?,borrowed=?,returned=?,packed=?,condition=?,verified=? WHERE person=? AND item=?',
                    (a['owned'],a['borrowed'],a['returned'],a['packed'],a['condition'],a.get('verified'),target,item))

    def admin_entries(self):
        with self.db() as d:
            rows=d.execute('''SELECT r.*,m.revision,
                (SELECT COUNT(*) FROM messages x WHERE x.person=r.id) AS message_count,
                (SELECT COUNT(*) FROM events x WHERE x.person=r.id) AS record_count,
                (SELECT COUNT(*) FROM events x WHERE x.person=r.id AND x.state IN ('pending','conflict')) AS pending_count
                FROM registrations r JOIN members m ON m.person=r.id ORDER BY r.created DESC,r.rowid DESC LIMIT 500''').fetchall()
            legacy=[p['id'] for p in PEOPLE if d.execute('SELECT 1 FROM messages WHERE person=? LIMIT 1',(p['id'],)).fetchone()]
        return {'registrations':[{'id':r['id'],'name':r['name'],'matched':r['roster'] in ACTIVE_IDS,
            'matchedName':BY_PERSON[r['roster']]['name'] if r['roster'] in ACTIVE_IDS else None,'created':r['created'],
            'messages':r['message_count'],'records':r['record_count'],'pending':r['pending_count'],
            'completed':self.profile(r['id'])['completed']} for r in rows],
            'legacy':[BY_PERSON[p] for p in legacy]}

    def dispatch(self,h,path,value):
        owner=h.headers.get('X-Equipment-Owner')=='1';value=value or {};token=h.headers.get('X-Equipment-Member','')
        if path=='/hello':return {'owner':owner,'nameEntry':True}
        if path=='/enter':return self.enter(value)
        if path=='/chat-state':return self.simple_state(self.session_person(token),owner)
        if path=='/check':return self.check_item(self.session_person(token),value)
        if path=='/admin/entries':
            if not owner:raise PermissionError('仅装备负责人可查看后台记录')
            return self.admin_entries()
        if path=='/admin/detail':
            if not owner:raise PermissionError('仅装备负责人可查看后台记录')
            person=value.get('entry','')
            if person not in BY_PERSON:raise KeyError('登记不存在')
            return self.simple_state(person,True)
        return super().dispatch(h,path,value)
