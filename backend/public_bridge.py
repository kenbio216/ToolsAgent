"""Public member-only bridge. Bind to loopback behind the dedicated tunnel."""
import collections,http.client,ipaddress,json,os,re,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit

ORIGIN='https://kenbio216.github.io'
PREFIX='/api/gateway/equipment-agent'
PUBLIC=re.compile(r'/(?:hello|enter|telemetry|feedback|guided-state|confirm-personal|confirm-collective|chat|commit|dismiss|transcribe|job/[a-f0-9]{32}|voice-job/[a-f0-9]{32})$')
class Limits:
 def __init__(self):self.lock=threading.Lock();self.events={}
 def allow(self,ip,path):
  now=time.monotonic();rules=[('all',60,600)]
  if path=='/enter':rules.append(('enter',3600,60))
  if path=='/chat':rules.append(('chat',3600,240))
  if path=='/transcribe':rules.append(('voice',3600,120))
  with self.lock:
   if len(self.events)>10000:self.events={k:q for k,q in self.events.items() if q and q[-1]>now-3600}
   for kind,seconds,cap in rules:
    q=self.events.setdefault((ip,kind),collections.deque())
    while q and q[0]<now-seconds:q.popleft()
    if len(q)>=cap:return False
   for kind,_,_ in rules:self.events[(ip,kind)].append(now)
  return True

class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass
 def reply(self,status,data):
  b=json.dumps(data,ensure_ascii=False).encode();self.send_response(status)
  for k,v in {'Content-Type':'application/json; charset=utf-8','Content-Length':str(len(b)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Connection':'close','Vary':'Origin'}.items():self.send_header(k,v)
  if self.headers.get('Origin')==ORIGIN:
   self.send_header('Access-Control-Allow-Origin',ORIGIN);self.send_header('Access-Control-Allow-Methods','POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type, X-Equipment-Member, X-Equipment-Visit')
  self.end_headers();self.close_connection=True
  if self.command!='HEAD':self.wfile.write(b)
 def dispatch(self):
  parsed=urlsplit(self.path)
  if parsed.scheme or parsed.netloc or parsed.query:return self.reply(404,{'error':'未找到接口'})
  path=parsed.path.removeprefix(PREFIX)
  if self.command in ('GET','HEAD') and parsed.path=='/health':return self.reply(200,{'ok':True,'service':'equipment-member-api'})
  if not parsed.path.startswith(PREFIX) or not PUBLIC.fullmatch(path):return self.reply(404,{'error':'未找到接口'})
  if self.headers.get('Origin')!=ORIGIN:return self.reply(403,{'error':'请从装备助手页面打开'})
  if self.command=='OPTIONS':return self.reply(200,{'ok':True})
  if self.command!='POST':return self.reply(405,{'error':'请求方式不支持'})
  try:
   # Only the dedicated loopback tunnel supplies these headers. Owner headers are never forwarded.
   ip=str(ipaddress.ip_address(self.headers.get('CF-Connecting-IP','')))
   if not re.fullmatch(r'[a-fA-F0-9]+-[A-Za-z0-9]+',self.headers.get('CF-Ray','')):raise ValueError('未通过入口校验')
   if not self.server.limits.allow(ip,path):return self.reply(429,{'error':'请求较多，请稍后再试'})
   if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:raise ValueError('请求格式无效')
   n=int(self.headers['Content-Length']);maximum=4*1024*1024 if path in ('/chat','/transcribe') else 16384
   if not 0<n<=maximum:raise ValueError('请求过大')
   if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('请求格式无效')
   token=self.headers.get('X-Equipment-Member','')
   if token and not re.fullmatch(r'[A-Za-z0-9_-]{20,100}',token):raise ValueError('会话凭证无效')
   if not token and path not in ('/hello','/enter','/telemetry','/feedback'):return self.reply(401,{'error':'请先填写姓名'})
   self.connection.settimeout(15);value=json.loads(self.rfile.read(n))
   if not isinstance(value,dict):raise ValueError('请求格式无效')
   headers={'Content-Type':'application/json','X-Asset-File-Token':self.server.token,'X-Equipment-Owner':'0','X-Equipment-Member':token,'X-Equipment-Client-IP':ip,'X-Equipment-User-Agent':self.headers.get('User-Agent','')[:512],'X-Equipment-Visit':self.headers.get('X-Equipment-Visit','')[:80]}
   connection=http.client.HTTPConnection('127.0.0.1',self.server.backend_port,timeout=35)
   try:
    connection.request('POST','/agent'+path,json.dumps(value).encode(),headers);r=connection.getresponse();body=r.read(2*1024*1024+1)
    if len(body)>2*1024*1024:raise ValueError('响应过大')
    result=json.loads(body);return self.reply(r.status,result)
   finally:connection.close()
  except (ValueError,KeyError):return self.reply(400,{'error':'请求未完整，请检查后重试'})
  except (OSError,http.client.HTTPException):return self.reply(503,{'error':'登记服务暂未连通，草稿保留，请稍后再试'})
 do_GET=dispatch;do_HEAD=dispatch;do_POST=dispatch;do_OPTIONS=dispatch

def make_server(port=18953,token=None,backend_port=18937):
 token=token or os.environ.get('ASSET_FILE_TOKEN','')
 if len(token)<32:raise ValueError('Missing private service credential')
 s=ThreadingHTTPServer(('127.0.0.1',port),Handler);s.daemon_threads=True;s.limits=Limits();s.token=token;s.backend_port=backend_port;return s
if __name__=='__main__':make_server().serve_forever()
