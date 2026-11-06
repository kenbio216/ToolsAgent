"""Private loopback engine; expose only through the member bridge or a trusted owner gateway."""
import json,os,secrets
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from agent_management import ManagementAgentService
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  if not secrets.compare_digest(self.headers.get('X-Asset-File-Token',''),self.server.token):return self.reply(401,{'error':'Unauthorized'})
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=4*1024*1024:raise ValueError('Request size invalid')
   value=json.loads(self.rfile.read(n));result=self.server.agent.dispatch(self,self.path.removeprefix('/agent'),value);self.reply(200,result)
  except PermissionError:self.reply(401,{'error':'Unauthorized'})
  except (ValueError,KeyError) as e:self.reply(400,{'error':str(e)[:200]})
 def reply(self,status,value):
  data=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*args):pass
if __name__=='__main__':
 token=os.environ.get('ASSET_FILE_TOKEN','')
 if len(token)<32:raise SystemExit('Configure a private ASSET_FILE_TOKEN of at least 32 characters')
 server=ThreadingHTTPServer(('127.0.0.1',18937),Handler);server.token=token;server.agent=ManagementAgentService(Path('state'));server.serve_forever()
