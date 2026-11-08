"""Scoped equipment conversations, independent memory and a durable Feishu outbox.

The existing Remarks columns are never written. Confirmed sheet writes contain
loan counts and the concise personal checklist only.
"""
from __future__ import annotations
import base64,concurrent.futures,contextlib,copy,datetime,hashlib,io,csv,json,os,re,secrets,sqlite3,subprocess,threading,time,uuid
from pathlib import Path
from agent_catalog import PEOPLE,INACTIVE_PEOPLE,BY_PERSON,CATALOG,BY_ITEM,CORE,SHEET_TOKEN,SHEET_URL,CHECK_SHEET,LOG_SHEET,SYSTEM


def stamp():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def qty(n):
    if isinstance(n,bool) or not isinstance(n,int) or not 0<=n<=100:raise ValueError('数量须为0至100的整数')
    return n
def text(s,limit=200):
    if not isinstance(s,str) or len(s)>limit:raise ValueError('内容为空或过长，请缩短后重试')
    return s.strip()
def col(n):
    s=''
    while n:n,a=divmod(n-1,26);s=chr(65+a)+s
    return s
class Conflict(ValueError):pass


class Feishu:
    def __init__(self,root,lock=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.lock=lock or threading.RLock()
    def cli(self,args):
        env=dict(os.environ,HERMES_HOME=str(Path.home()/'.hermes'),LARKSUITE_CLI_NO_UPDATE_NOTIFIER='1',LARKSUITE_CLI_NO_SKILLS_NOTIFIER='1')
        cli=Path.home()/'.local/lib/node_modules/@larksuite/cli/bin/lark-cli'
        p=subprocess.run([str(cli),'sheets',*args,'--spreadsheet-token',SHEET_TOKEN,'--as','user'],env=env,cwd=self.root,capture_output=True,text=True,timeout=75)
        try:d=json.loads(p.stdout or p.stderr)
        except ValueError:raise ValueError('飞书响应未确认，记录已保留，待重试') from None
        if p.returncode or not d.get('ok'):
            typ=d.get('error',{}).get('subtype','')
            raise ValueError('飞书访问频率受限，记录已保存待重试' if typ=='rate_limit' else '飞书连接未完成，记录已保留待同步')
        return d['data']
    def values(self,name,rng=None):
        a=self.cli(['+csv-get','--sheet-name',name]+(['--range',rng] if rng else []))
        if a.get('has_more'):raise ValueError('飞书数据读取不完整，未覆盖写入')
        return list(csv.reader(io.StringIO(re.sub(r'(?m)^\[row=\d+\] ','',a['annotated_csv']))))
    def write(self,writes):
        filename='write-'+uuid.uuid4().hex+'.json';p=self.root/filename
        p.write_text(json.dumps(writes,ensure_ascii=False));p.chmod(0o600)
        try:return self.cli(['+cells-set','--writes','@./'+filename])
        finally:p.unlink(missing_ok=True)
    def prepare(self,snapshot):
        with self.lock:
            names={s['sheet_name'] for s in self.cli(['+workbook-info'])['sheets']}
            created=[]
            if CHECK_SHEET not in names:
                columns=['姓名','绳组','主锁（5把）','ATC（1个）','上升器（1个）','抓结（1个）','120cm扁带（1条）','副保快挂（1副）','足额核对','待办','更新时间']
                rows=[[p['name'],p['group']+'·'+p['role']]+['待核对']*6+['0/6项','五把锁＋五件装备待核对',stamp()] for p in PEOPLE]
                self.new_sheet(CHECK_SHEET,columns,rows)
                self.upgrade_check_formulas()
                checked=self.cli(['+formula-verify','--sheet-name',CHECK_SHEET,'--range',f'I2:I{len(PEOPLE)+1}','--exit-on-error'])
                if checked.get('status')!='success' or checked.get('has_more'):raise ValueError('核对表公式尚未通过校验')
                created.append(CHECK_SHEET)
            # Read identity columns before ever writing per-member cells.
            self.check_rows()
            return {'created':created,'url':SHEET_URL}
    def check_rows(self):
        rows=self.values(CHECK_SHEET,f'A1:B{len(PEOPLE)+len(INACTIVE_PEOPLE)+1}')
        active={p['name']:p['id'] for p in PEOPLE};inactive={p['name'] for p in INACTIVE_PEOPLE}
        present=[r[0] for r in rows[1:] if r and r[0] and r[0] not in inactive]
        if present!=list(active):raise Conflict('个人装备核对表的人员行或顺序已变化，请管理员核对后再同步')
        return {active[r[0]]:n for n,r in enumerate(rows[1:],2) if r and r[0] in active}
    def upgrade_check_formulas(self):
        # Only the assistant-owned completion column.
        rows=list(self.check_rows().values())
        self.write([{'sheet_name':CHECK_SHEET,'range':f'I{r}',
            'cells':[[{'formula':f'=(COUNTIF(C{r}:H{r},"已核对*")+COUNTIF(C{r}:H{r},"已带齐*"))&"/6项"'}]]} for r in rows])
    def new_sheet(self,name,columns,rows):
        end=col(len(columns));n=max(2,len(rows)+1)
        body={'sheets':[{'name':name,'columns':columns,'data':rows,'dtypes':{c:'object' for c in columns}}]}
        styles={'styles':[{'name':name,'cell_styles':[
            {'range':f'A1:{end}1','font_size':11,'font_weight':'bold','background_color':'#F9E5CE','font_color':'#172B2A','word_wrap':'auto-wrap'},
            {'range':f'A2:{end}{n}','font_size':11,'background_color':'#FFFFFF','font_color':'#172B2A','word_wrap':'auto-wrap','border_styles':{'all':{'style':'solid','weight':'thin','color':'#D7DEDA'}}}],
            'row_sizes':[{'range':f'1:{n}','size':48}],
            'col_sizes':[{'range':f'A:{end}','size':120},{'range':f'{"J" if len(columns)>9 else "D"}:{end}','size':200}]}]}
        p=self.root/'create.json';s=self.root/'styles.json';p.write_text(json.dumps(body,ensure_ascii=False));s.write_text(json.dumps(styles,ensure_ascii=False))
        self.cli(['+table-put','--sheets','@./create.json','--styles','@./styles.json'])
        self.cli(['+dim-freeze','--sheet-name',name,'--rows','1','--cols','2'])
    def loan_map(self):
        rows=self.values('装备借用记录');head=rows[1]
        names={p['id']:next((j for j,v in enumerate(head) if v==p['name']+'·借'),None) for p in PEOPLE}
        if any(v is None for v in names.values()):raise Conflict('借还表的队员表头已变化，请管理员核对')
        mapping={i['id']:next((r for r,row in enumerate(rows,1) if row and row[0]==i['sheet']),None) for i in CATALOG}
        if any(v is None for v in mapping.values()):raise Conflict('借还表的装备名称已变化，请管理员核对')
        return rows,names,mapping
    def import_counts(self):
        with self.lock:
            rows,names,mapping=self.loan_map();result=[]
            for p,j in names.items():
                for item,r in mapping.items():
                    pair=rows[r-1][j:j+2];pair+=['']*(2-len(pair))
                    if any(v and not re.fullmatch(r'\d+',v) for v in pair):raise Conflict('借还数量含非整数，未自动改写，请管理员核对')
                    b,t=[int(v or 0) for v in pair]
                    if t>b:raise Conflict('飞书归还数超过借出数，请管理员先核对')
                    result.append((p,item,b,t))
            return result
    @staticmethod
    def check_cells(person,items):
        cells=[];todos=[]
        for core in CORE:
            a=items[core['id']];need=core['required'];held=a['owned']+a['borrowed']-a['returned']
            explicit=a.get('verified') is not None
            done=(bool(a.get('verified')) if explicit else a['packed']>=need and held>=need) and a['condition']=='正常'
            value=('已核对' if explicit else '已带齐') if done else ('待检查' if a['condition']!='正常' else ('待核对' if explicit else (f"已装{a['packed']}/{need}" if a['packed'] else '待核对')))
            cells.append(value)
            if not done:todos.append(core['name'])
        return cells,('全部已核对' if not todos else '待核对：'+'、'.join(todos))
    def sync(self,event,profile):
        if event.get('kind')=='collective':return self.sync_collective(event)
        with self.lock:
            self.prepare(profile)
            target=event.get('target',event['person'])
            if target not in {p['id'] for p in PEOPLE}:raise Conflict('姓名尚未匹配本次十险名单，记录保留在后台')
            rows,names,mapping=self.loan_map();j=names[target];writes=[]
            explicit={e['item'] for e in event.get('entries',[]) if e['action']=='loan_set'}
            # Strict read-before-write: never overwrite a newly edited human count.
            for item,expected in event['before'].items():
                current=rows[mapping[item]-1];pair=current[j:j+2]+['']*2
                actual=[int(v or 0) if re.fullmatch(r'\d*',v) else -1 for v in pair[:2]]
                old=[expected['borrowed'],expected['returned']];new=event['after'][item]
                desired=[new['borrowed'],new['returned']]
                if actual!=old and actual!=desired:raise Conflict('飞书中这项借还数量已被人工修改；已暂停覆盖，待管理员核对')
                if desired!=old or item in explicit:
                    writes.append({'sheet_name':'装备借用记录','range':f'{col(j+1)}{mapping[item]}:{col(j+2)}{mapping[item]}',
                        'cells':[[{'value':v,'cell_styles':{'number_format':'0'}} for v in desired]]})
            r=self.check_rows()[target]
            identity=self.values(CHECK_SHEET,f'A{r}:B{r}')[0]
            if identity[0]!=BY_PERSON[target]['name']:raise Conflict('核对表人员行已移动，未写入其他人的行')
            from agent_inventory import human_checks
            checks,todo=human_checks(profile['items'])
            if target!=event['person']:
                # A new name session must not clear checks entered on another
                # device. Only the equipment mentioned in this event changes.
                current=self.values(CHECK_SHEET,f'C{r}:H{r}')[0]
                current=(current+['待核对']*6)[:6]
                checks=[checks[k] if i['id'] in event['after'] else current[k] for k,i in enumerate(CORE)]
                missing=[i['name'] for k,i in enumerate(CORE) if not checks[k].startswith(('已核对','已带齐'))]
                todo='待核对：'+'、'.join(missing) if missing else '全部已核对'
            writes.append({'sheet_name':CHECK_SHEET,'range':f'C{r}:H{r}','cells':[[{'value':v} for v in checks]]})
            writes.append({'sheet_name':CHECK_SHEET,'range':f'J{r}:K{r}','cells':[[{'value':v} for v in [todo,stamp()]]]})
            self.write(writes)
            # Verify the exact values written, including person and item coordinates.
            for item in event['before']:
                new=event['after'][item]
                if item in explicit or [new['borrowed'],new['returned']] != [event['before'][item]['borrowed'],event['before'][item]['returned']]:
                    actual=self.values('装备借用记录',f'{col(j+1)}{mapping[item]}:{col(j+2)}{mapping[item]}')[0]
                    if actual!=[str(new['borrowed']),str(new['returned'])]:raise Conflict('飞书回读数量未匹配，记录仍待核对')
            actual=self.values(CHECK_SHEET,f'C{r}:H{r}')[0]
            if actual!=checks:raise Conflict('个人核对表回读未匹配，记录仍待核对')
    def sync_collective(self,event):
        # Detailed carrying history belongs to the private management database.
        return {'storedInManagement':True}



class AgentService:
    def __init__(self,root,cli_lock=None,model=None,sync=None,start=True):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.root.chmod(0o700)
        self.path=self.root/'equipment-agent.sqlite3';self.feishu=sync or Feishu(self.root/'sync',cli_lock)
        self.model=model or self.call_model;self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=3,thread_name_prefix='equipment-agent')
        self.wake=threading.Event();self.stopping=threading.Event()
        with self.db() as d:
            d.executescript('''
            CREATE TABLE IF NOT EXISTS members(person TEXT PRIMARY KEY,revision INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS items(person TEXT,item TEXT,owned INTEGER DEFAULT 0,borrowed INTEGER DEFAULT 0,returned INTEGER DEFAULT 0,packed INTEGER DEFAULT 0,condition TEXT DEFAULT '正常',PRIMARY KEY(person,item));
            CREATE TABLE IF NOT EXISTS invites(hash TEXT PRIMARY KEY,person TEXT,created TEXT,expires REAL,revoked INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,person TEXT,role TEXT,content TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,request TEXT UNIQUE,person TEXT,state TEXT,answer TEXT,receipt TEXT,error TEXT,created TEXT,confirmed TEXT);
            CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,person TEXT,content TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,request TEXT UNIQUE,person TEXT,data TEXT,state TEXT,attempts INTEGER DEFAULT 0,error TEXT,next REAL DEFAULT 0,created TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            ''')
            if 'verified' not in {r[1] for r in d.execute('PRAGMA table_info(items)')}:
                d.execute('ALTER TABLE items ADD COLUMN verified INTEGER DEFAULT NULL')
            for p in PEOPLE:
                d.execute('INSERT OR IGNORE INTO members(person) VALUES(?)',(p['id'],))
            for member in d.execute('SELECT person FROM members').fetchall():
                for item in CATALOG:d.execute('INSERT OR IGNORE INTO items(person,item) VALUES(?,?)',(member['person'],item['id']))
            d.execute("UPDATE jobs SET state='error',error='服务重启中断了识别，消息已保留，请重试' WHERE state='running'")
        self.path.chmod(0o600)
        if start:threading.Thread(target=self.sync_loop,daemon=True,name='equipment-sync').start()
    @contextlib.contextmanager
    def db(self):
        d=sqlite3.connect(self.path,timeout=15);d.row_factory=sqlite3.Row
        try:
            with d:yield d
        finally:d.close()
    def authorize(self,owner,token,person=None):
        if owner:
            if person is None:person=os.environ.get('EQUIPMENT_OWNER_PERSON','member_1')
            if person not in BY_PERSON:raise ValueError('请选择当前队员')
            return person
        if not token or len(token)>100:raise PermissionError('请使用自己的队员登记链接，或先登录管理员账号')
        with self.db() as d:r=d.execute('SELECT * FROM invites WHERE hash=? AND revoked=0 AND expires>?',(digest(token),time.time())).fetchone()
        if not r:raise PermissionError('登记链接已失效，请联系装备负责人获取新链接')
        return r['person']
    def invite(self,person):
        if person not in BY_PERSON:raise ValueError('队员不存在')
        token=secrets.token_urlsafe(32)
        with self.db() as d:
            d.execute('UPDATE invites SET revoked=1 WHERE person=?',(person,))
            d.execute('INSERT INTO invites VALUES(?,?,?,?,0)',(digest(token),person,stamp(),time.time()+14*86400))
        return {'person':person,'code':token,'expiresDays':14}
    def profile(self,person):
        with self.db() as d:
            rows=d.execute('SELECT * FROM items WHERE person=?',(person,)).fetchall()
            revision=d.execute('SELECT revision FROM members WHERE person=?',(person,)).fetchone()[0]
        items={r['item']:dict(r) for r in rows}
        checks,todo=self.feishu.check_cells(person,items)
        return {'person':BY_PERSON[person],'revision':revision,'items':items,'completed':sum(c in ('已带齐','已核对') for c in checks),'todo':todo}
    def state(self,person,owner):
        profile=self.profile(person)
        with self.db() as d:
            messages=[dict(r) for r in d.execute('SELECT role,content,created FROM messages WHERE person=? ORDER BY id DESC LIMIT 40',(person,))][::-1]
            notes=[dict(r) for r in d.execute('SELECT id,content,created FROM notes WHERE person=? ORDER BY created DESC LIMIT 20',(person,))]
            events=[{'id':r['id'],'person':r['person'],'state':r['state'],'error':r['error'],'created':r['created'],'entries':json.loads(r['data'])['entries']} for r in d.execute('SELECT * FROM events '+('' if owner else 'WHERE person=? ')+'ORDER BY created DESC LIMIT 40',() if owner else (person,))]
            active=[dict(r) for r in d.execute("SELECT id,state,created FROM jobs WHERE person=? AND state='running'",(person,))]
            drafts=[{'id':r['id'],'answer':json.loads(r['answer']),'created':r['created']} for r in d.execute("SELECT * FROM jobs WHERE person=? AND state='done' AND confirmed='' ORDER BY created DESC LIMIT 3",(person,)) if any(json.loads(r['answer']).get(k) for k in ('proposals','memory','feedback','collectiveProposals','essentialResponses'))]
            ready=d.execute("SELECT value FROM settings WHERE key='ready'").fetchone()
        return {**profile,'owner':bool(owner),'people':PEOPLE if owner else [BY_PERSON[person]],'catalog':CATALOG,'core':CORE,'messages':messages,'notes':notes,'events':events,'drafts':drafts,'activeJobs':active,'sheetUrl':SHEET_URL,'sheetsReady':bool(ready),'model':'glm-5.3-flash','reasoning':'max','team': [self.profile(p['id']) for p in PEOPLE] if owner else []}
    def prepare(self):
        # Provision only new worksheets; existing remarks are outside this writer.
        self.feishu.prepare(None);counts=self.feishu.import_counts()
        with self.db() as d:
            for p,item,b,r in counts:
                pending=d.execute("SELECT 1 FROM events WHERE (person=? OR json_extract(data,'$.target')=?) AND state IN ('pending','conflict')",(p,p)).fetchone()
                if not pending:d.execute('UPDATE items SET borrowed=?,returned=?,packed=MIN(packed,owned+?-?) WHERE person=? AND item=?',(b,r,b,r,p,item))
            d.execute("INSERT OR REPLACE INTO settings VALUES('ready',?)",(stamp(),))
        self.wake.set();return {'ok':True,'url':SHEET_URL}
    @staticmethod
    def entries(raw):
        if not isinstance(raw,list):raise ValueError('登记草稿格式无效，请重新整理')
        if not 1<=len(raw)<=40:raise ValueError('请一次登记1至40项')
        result=[]
        for e in raw:
            if not isinstance(e,dict) or e.get('item') not in BY_ITEM or e.get('action') not in ('borrow','return','loan_set','self','pack','issue','check'):raise ValueError('装备或操作类型无效')
            q=qty(e.get('quantity'));action=e['action']
            if action=='check' and (e['item'] not in {i['id'] for i in CORE} or q not in (0,BY_ITEM[e['item']]['required'])):raise ValueError('请按清单指定数量核对装备')
            if action in ('borrow','return','issue') and q==0:raise ValueError('本次借还数量须大于0')
            condition=e.get('condition','正常')
            if condition not in ('正常','待检查','异常'):raise ValueError('请确认装备状态')
            receiver=text(e.get('receiver',''),40)
            if action=='return' and not receiver:raise ValueError('请说明归还给谁，再确认登记')
            result.append({'item':e['item'],'action':action,'quantity':q,'condition':condition,'receiver':receiver,'detail':text(e.get('detail',''),160)})
            if action=='loan_set' and 'returned' in e:
                result[-1]['returned']=qty(e['returned'])
                if result[-1]['returned']>q:raise ValueError('归还数量不能超过借出数量')
        return result
    def record_source(self,d,person):return person
    def before_record(self,d,person,source,value,job,owner_job=None):pass
    def running_model_jobs(self,d):return d.execute("SELECT count(*) FROM jobs WHERE state='running'").fetchone()[0]
    def record(self,person,value,job=None,*,owner_job=None):
        request=text(value.get('requestId',''),100)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{12,100}',request):raise ValueError('登记编号无效，请刷新后重试')
        memory=text(value.get('memory',''),500)
        feedback=value.get('feedback')
        collective=value.get('collectiveProposals')
        entries=[] if not value.get('entries') and (memory or feedback or collective or value.get('essentialResponses')) else self.entries(value.get('entries',[]))
        with self.db() as d:
            d.execute('BEGIN IMMEDIATE')
            prior=d.execute('SELECT id,person FROM events WHERE request=?',(request,)).fetchone()
            if prior:
                if prior['person']!=person:raise PermissionError('登记编号已使用，请刷新重试')
                return {'event':prior[0],'duplicate':True}
            if job:
                prior=d.execute('SELECT confirmed,state FROM jobs WHERE id=? AND person=?',(job,person)).fetchone()
                if prior and prior[0]:return {'event':prior[0],'duplicate':True}
                if not prior or prior['state']!='done':raise Conflict('这份旧草稿已失效，请核对最新草稿后再登记')
            revision=d.execute('SELECT revision FROM members WHERE person=?',(person,)).fetchone()[0]
            if value.get('revision')!=revision:raise Conflict('记录已在另一处更新，请刷新核对后再确认；本次草稿仍保留')
            source=self.record_source(d,person)
            self.before_record(d,person,source,value,job,owner_job)
            before={};after={}
            for e in entries:
                i=e['item']
                if i not in before:
                    before[i]=dict(d.execute('SELECT * FROM items WHERE person=? AND item=?',(source,i)).fetchone());after[i]=copy.deepcopy(before[i])
                a=after[i];q=e['quantity'];action=e['action']
                if action=='borrow':a['borrowed']+=q
                elif action=='loan_set':
                    returned=e.get('returned',a['returned'])
                    if returned>q:raise ValueError('修正借出总数不能少于已归还数，请说明是否也要修正归还记录')
                    a['borrowed']=q;a['returned']=returned;a['packed']=min(a['packed'],a['owned']+q-returned)
                    if a.get('verified') and a['owned']+q-returned<BY_ITEM[i]['required']:a['verified']=0
                elif action=='return':
                    if q>a['borrowed']-a['returned']:raise ValueError(f"{BY_ITEM[i]['name']}本次归还数超过未还数量，请核对")
                    a['returned']+=q;a['packed']=min(a['packed'],a['owned']+a['borrowed']-a['returned'])
                    if a.get('verified') is not None:a['verified']=0
                elif action=='self':
                    a['owned']=q;a['packed']=min(a['packed'],a['owned']+a['borrowed']-a['returned'])
                elif action=='pack':
                    if q>a['owned']+a['borrowed']-a['returned']:raise ValueError(f"请先登记{BY_ITEM[i]['name']}的自有或实际借用数量，再核对装包")
                    a['packed']=q
                elif action=='check':a['verified']=int(q>0)
                if action=='issue' or e['condition']!='正常':
                    a['condition']=e['condition'] if e['condition']!='正常' else '待检查'
                    if a.get('verified') is not None:a['verified']=0
                elif a['condition']!='正常' and not(action=='check' and q==0):raise ValueError('异常装备需要管理员核实，不能直接标记已核对')
            for i,a in after.items():
                d.execute('UPDATE items SET owned=?,borrowed=?,returned=?,packed=?,condition=?,verified=? WHERE person=? AND item=?',(a['owned'],a['borrowed'],a['returned'],a['packed'],a['condition'],a.get('verified'),person,i))
                if source!=person:d.execute('UPDATE items SET owned=?,borrowed=?,returned=?,packed=?,condition=?,verified=? WHERE person=? AND item=?',(a['owned'],a['borrowed'],a['returned'],a['packed'],a['condition'],a.get('verified'),source,i))
            target=self.target_for(person)
            if not entries:target=None
            event={'id':uuid.uuid4().hex,'person':person,'target':target,'sharedSource':source,'before':before,'after':after,'entries':entries,'created':stamp()}
            if owner_job:event['ownerJob']=owner_job
            if feedback:
                event['feedback']=feedback
                if not entries:event['kind']='feedback'
            if value.get('noBorrow'):event['noBorrow']=True
            status='pending' if target else 'local'
            self.on_record_confirmed(d,event,value,job)
            d.execute('INSERT INTO events(id,request,person,data,state,error,created) VALUES(?,?,?,?,?,?,?)',(event['id'],request,person,json.dumps(event,ensure_ascii=False),status,'',event['created']))
            d.execute('UPDATE members SET revision=revision+1 WHERE person=?',(person,))
            if memory:d.execute('INSERT INTO notes VALUES(?,?,?,?)',(uuid.uuid4().hex,person,memory,stamp()))
            if job:d.execute('UPDATE jobs SET confirmed=? WHERE id=?',(event['id'],job))
            summary=('已记录：'+'；'.join(f"{BY_ITEM[e['item']]['name']} {e['quantity']} { {'borrow':'借用','loan_set':'本次借出总数','return':'归还','self':'自有','pack':'已装包','issue':'异常','check':'已核对'}[e['action']]}" for e in entries)+('。正在同步飞书。' if target else '。记录已保存在后台。')) if entries else '已记住这条装备信息。'
            if value.get('noBorrow'):summary='已确认本次未借装备，借出0、归还0。'+('正在同步飞书。' if target else '已保存在后台。')+('集体携带补报也已保存。' if collective else '')
            if feedback and not entries:summary='已提交意见，装备负责人可在后台查看；未修改装备借还数量。'
            if collective and not entries:summary='已补充集体装备携带，第二步及负责人管理页已更新。'+('意见也已提交。' if feedback else '')
            if value.get('essentialResponses'):
                from agent_essentials import RESPONSE_LABELS
                note='；'.join(BY_ITEM[e['item']]['name']+'：'+RESPONSE_LABELS[e['status']] for e in value['essentialResponses'])
                summary=(summary+'\n' if entries or collective or feedback else '')+'已保存装备说明：'+note+'。'
            if not entries or not all(e['action']=='check' for e in entries):
                cursor=d.execute('INSERT INTO messages(person,role,content,created) VALUES(?,?,?,?)',(person,'assistant',summary,stamp()))
                self.on_record_message(d,job,cursor.lastrowid)
        self.wake.set();return {'event':event['id'],'state':status,'revision':revision+1}
    def target_for(self,person):return person
    def after_sync(self,event):pass
    def chat(self,person,value):
        message=text(value.get('message',''),3000);images=value.get('images',[])
        if not message and not images:raise ValueError('请说说要登记什么，或选择装备照片')
        if not isinstance(images,list) or len(images)>2:raise ValueError('每次最多发送2张照片')
        for im in images:
            if not isinstance(im,str) or len(im)>1800000 or not re.match(r'^data:image/(jpeg|png|webp);base64,',im):raise ValueError('照片须为JPEG、PNG或WebP，请重新选择')
            try:b=base64.b64decode(im.split(',',1)[1],validate=True)
            except ValueError:raise ValueError('照片内容无效') from None
            if not (b.startswith(b'\xff\xd8\xff') or b.startswith(b'\x89PNG\r\n\x1a\n') or (b.startswith(b'RIFF') and b[8:12]==b'WEBP')):raise ValueError('照片格式与内容不匹配')
        request=text(value.get('requestId',''),100)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{12,100}',request):raise ValueError('消息编号无效，请刷新重试')
        with self.db() as d:
            d.execute('BEGIN IMMEDIATE')
            prior=d.execute('SELECT id,person FROM jobs WHERE request=?',(request,)).fetchone()
            if prior:
                if prior['person']!=person:raise PermissionError('无法读取这条消息')
                return {'job':prior['id']}
            running=self.running_model_jobs(d)
            if running>=3 or d.execute("SELECT 1 FROM jobs WHERE person=? AND state='running'",(person,)).fetchone():raise Conflict('已有消息正在处理，完成后可继续登记')
            recent=d.execute('SELECT count(*) FROM jobs WHERE person=? AND created>?',(person,(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))-datetime.timedelta(minutes=10)).isoformat(timespec='seconds'))).fetchone()[0]
            if recent>=20:raise ValueError('这段时间消息较多，请稍后再试；可先使用个人核对清单')
            d.execute("UPDATE jobs SET state='superseded' WHERE person=? AND state='done' AND confirmed=''",(person,))
            job=uuid.uuid4().hex
            d.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(job,request,person,'running','{}','{}','',stamp(),''))
            cursor=d.execute('INSERT INTO messages(person,role,content,created) VALUES(?,?,?,?)',(person,'user',message+('【附装备照片】' if images else ''),stamp()))
            self.on_chat_created(d,job,person,value,cursor.lastrowid)
        self.pool.submit(self.chat_worker,job,person,message,images);return {'job':job}
    def chat_worker(self,job,person,message,images):
        result=None
        try:
            state=self.state(person,False)
            prompt,history=self.model_input(job,person,state)
            content=[{'type':'text','text':message or '请识别照片中的装备，逐项核对种类和可见数量；不清楚的地方先问我。'}]+[{'type':'image_url','image_url':{'url':im}} for im in images]
            result=self.model({'messages':[{'role':'system','content':prompt}]+history+[{'role':'user','content':content if images else message}]})
            answer=result['answer'];answer['reply']=text(answer.get('reply',''),2000)
            proposals=answer.get('proposals',[])
            if proposals:answer['proposals']=self.entries(proposals)
            else:answer['proposals']=[]
            answer['memory']=text(answer.get('memory',''),500)
            self.validate_answer(job,person,answer)
            with self.db() as d:
                d.execute("UPDATE jobs SET state='done',answer=?,receipt=? WHERE id=?",(json.dumps(answer,ensure_ascii=False),json.dumps(result.get('receipt',{}),ensure_ascii=False),job))
                cursor=d.execute('INSERT INTO messages(person,role,content,created) VALUES(?,?,?,?)',(person,'assistant',answer['reply'],stamp()))
                self.on_chat_replied(d,job,person,cursor.lastrowid)
        except Exception as e:
            error=str(e) if isinstance(e,ValueError) else '识别暂时未完成，请重试；未登记任何借还记录'
            answer=result.get('answer',{}) if isinstance(result,dict) else {}
            receipt=result.get('receipt',{}) if isinstance(result,dict) else {}
            with self.db() as d:d.execute("UPDATE jobs SET state='error',error=?,answer=?,receipt=? WHERE id=?",(error[:250],json.dumps(answer,ensure_ascii=False),json.dumps(receipt,ensure_ascii=False),job))
    def on_chat_created(self,d,job,person,value,message_id):pass
    def on_chat_replied(self,d,job,person,message_id):pass
    def on_record_message(self,d,job,message_id):pass
    def on_record_confirmed(self,d,event,value,job):pass
    def validate_answer(self,job,person,answer):pass
    def model_input(self,job,person,state):
        prompt=SYSTEM+self.extra_prompt(person)+'\n当前登记人与已确认记录（仅此人为登记对象）：'+json.dumps({k:state[k] for k in ['person','items','todo','catalog','notes']},ensure_ascii=False)
        return prompt,[{'role':m['role'],'content':m['content']} for m in state['messages'][-12:-1]]
    def call_model(self,payload):
        p=subprocess.run(['python3',str(Path(__file__).with_name('agent_model.py'))],input=json.dumps(payload,ensure_ascii=False),capture_output=True,text=True,timeout=165)
        try:d=json.loads(p.stdout)
        except ValueError:raise ValueError('模型响应未确认，请稍后重试') from None
        if p.returncode or d.get('error'):raise ValueError(d.get('error','模型服务暂时不可用'))
        return d
    def extra_prompt(self,person):return ''
    def job(self,person,jid):
        with self.db() as d:r=d.execute('SELECT * FROM jobs WHERE id=? AND person=?',(jid,person)).fetchone()
        if not r:raise KeyError('消息不存在')
        return {'id':r['id'],'state':r['state'],'answer':json.loads(r['answer']),'error':r['error'],'receipt':json.loads(r['receipt']),'confirmed':r['confirmed']}
    def commit(self,person,value):
        job=self.job(person,value.get('job',''))
        if job['confirmed']:return {'event':job['confirmed'],'duplicate':True}
        if job['state'] in ('superseded','discarded'):raise Conflict('这份旧草稿已失效，请核对最新草稿后再登记')
        if job['state']!='done':raise ValueError('请等待识别完成再核对登记')
        return self.record(person,{**value,'entries':job['answer'].get('proposals',[]),'memory':job['answer'].get('memory',''),'feedback':job['answer'].get('feedback'),'noBorrow':job['answer'].get('noBorrow',False),'collectiveProposals':job['answer'].get('collectiveProposals',[]),'essentialResponses':job['answer'].get('essentialResponses',[])},job['id'])
    def sync_loop(self):
        while not self.stopping.is_set():
            self.wake.wait(3);self.wake.clear()
            with self.db() as d:
                ready=d.execute("SELECT 1 FROM settings WHERE key='ready'").fetchone()
                pending=d.execute("SELECT e.* FROM events e WHERE e.state='pending' AND e.next<=? AND e.rowid=(SELECT MIN(p.rowid) FROM events p WHERE COALESCE(json_extract(p.data,'$.target'),p.person)=COALESCE(json_extract(e.data,'$.target'),e.person) AND p.state IN ('pending','conflict')) ORDER BY e.rowid LIMIT 1",(time.time(),)).fetchone()
            if not ready or not pending:continue
            self.sync_one(pending)
    def sync_one(self,row):
        event=json.loads(row['data'])
        try:
            profile=self.profile(event['person']);profile['items'].update(event.get('after',{}))
            self.feishu.sync(event,profile)
            self.after_sync(event)
            with self.db() as d:d.execute("UPDATE events SET state='synced',error='' WHERE id=?",(row['id'],))
        except Exception as e:
            conflict=isinstance(e,Conflict);error=str(e) if isinstance(e,ValueError) else '飞书连接暂时中断，记录已保存待同步'
            with self.db() as d:d.execute('UPDATE events SET state=?,attempts=attempts+1,error=?,next=? WHERE id=?',('conflict' if conflict else 'pending',error[:250],time.time()+min(300,10*(row['attempts']+1)),row['id']))
    def dispatch(self,h,path,value):
        owner=h.headers.get('X-Equipment-Owner')=='1';token=h.headers.get('X-Equipment-Member','')
        person=self.authorize(owner,token,(value or {}).get('person'))
        if path=='/state':return self.state(person,owner)
        if path.startswith('/job/') and re.fullmatch(r'/job/[a-f0-9]{32}',path):return self.job(person,path.rsplit('/',1)[1])
        if h.command!='POST':raise KeyError('接口不存在')
        if path=='/chat':return self.chat(person,value)
        if path=='/record':return self.record(person,value)
        if path=='/commit':return self.commit(person,value)
        if path=='/dismiss':
            self.job(person,value.get('job',''))
            with self.db() as d:d.execute("UPDATE jobs SET state='discarded' WHERE id=? AND person=? AND confirmed=''",(value['job'],person))
            return {'ok':True}
        if path in ('/prepare','/refresh'):
            if not owner:raise PermissionError('仅装备负责人可刷新全队飞书记录')
            return self.prepare()
        if path=='/invite':
            if not owner:raise PermissionError('仅装备负责人可生成登记链接')
            return self.invite(value.get('target',''))
        if path=='/retry':
            if not owner:raise PermissionError('仅装备负责人可重试冲突记录')
            with self.db() as d:d.execute("UPDATE events SET state='pending',next=0 WHERE id=? AND state IN ('pending','conflict')",(text(value.get('event',''),40),))
            self.wake.set();return {'ok':True}
        raise KeyError('接口不存在')
