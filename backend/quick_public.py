"""Maintain the temporary member API and publish its current address to Pages.

No Hub or Tailscale routing is changed. Requires the user's existing gh login.
"""
import base64,ipaddress,json,os,re,subprocess,tempfile,time,urllib.parse,urllib.request,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=os.environ.get('EQUIPMENT_GITHUB_REPO','kenbio216/ToolsAgent')
REMOTE='frontend/public/api-config.json'
ORIGIN=os.environ.get('EQUIPMENT_PAGES_ORIGIN','https://kenbio216.github.io')
def write_state(name,value):
    directory=ROOT/'state';directory.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=directory,delete=False) as file:
        json.dump(value,file);temp=Path(file.name)
    temp.chmod(0o600);os.replace(temp,directory/name)
def public_dns_ready(url):
    # A fresh Quick Tunnel can be registered before its DNS is provisioned.
    # Do not seed the machine/proxy resolver with an immediate negative lookup.
    host=urllib.parse.urlsplit(url).hostname
    if not host or not re.fullmatch(r'[-a-z0-9]+\.trycloudflare\.com',host):return False
    query=urllib.parse.urlencode({'name':host,'type':'A'})
    request=urllib.request.Request('https://cloudflare-dns.com/dns-query?'+query,headers={'Accept':'application/dns-json'})
    with urllib.request.urlopen(request,timeout=12) as r:record=json.load(r)
    answers=[a.get('data','') for a in record.get('Answer',[]) if a.get('type')==1]
    return record.get('Status')==0 and bool(answers) and all(ipaddress.ip_address(a).is_global for a in answers)
def verify_member_endpoint(url):
    # Keep normal certificate/hostname validation. Never publish merely because
    # cloudflared has connected to an edge or an arbitrary health page replies.
    with urllib.request.urlopen(url+'/health',timeout=12) as r:health=json.load(r)
    if health!={'ok':True,'service':'equipment-member-api'}:raise ValueError('Unexpected member health response')
    request=urllib.request.Request(url+'/api/gateway/equipment-agent/hello',data=b'{}',headers={'Content-Type':'application/json','Origin':ORIGIN})
    with urllib.request.urlopen(request,timeout=12) as r:
        allow=r.headers.get('Access-Control-Allow-Origin');hello=json.load(r)
    if allow!=ORIGIN or hello.get('owner') is not False or hello.get('nameEntry') is not True:raise ValueError('Member API or browser origin validation failed')
def publish(url,unit=None):
    endpoint=f'repos/{REPO}/contents/{REMOTE}'
    p=subprocess.run(['gh','api',endpoint],capture_output=True,text=True,timeout=30)
    if p.returncode:raise ValueError('Unable to read Pages backend configuration')
    old=json.loads(p.stdout);config=json.loads(base64.b64decode(old['content']))
    if config.get('mode')!='temporary-local':raise ValueError('Fixed backend configured; automatic temporary routing disabled')
    desired={**config,'apiBase':url+'/api/gateway/equipment-agent'}
    if desired!=config:
        body={'message':'Update member API connection','sha':old['sha'],'content':base64.b64encode((json.dumps(desired,indent=2)+'\n').encode()).decode()}
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'request.json';file.write_text(json.dumps(body));file.chmod(0o600)
            result=subprocess.run(['gh','api','--method','PUT',endpoint,'--input',str(file)],capture_output=True,text=True,timeout=40)
        if result.returncode:raise ValueError('Unable to publish member API address')
    write_state('public-api.json',{'url':url,'temporary':True,**({'unit':unit} if unit else {})})
    print('Member API verified; Pages connection configured',flush=True)
def read_state(name):
    try:
        value=json.loads((ROOT/'state'/name).read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}
def managed_unit(unit):
    return isinstance(unit,str) and bool(re.fullmatch(r'kenbio-equipment-tunnel-[a-f0-9]{32}\.service',unit))
def unit_alive(unit):
    if not managed_unit(unit):return False
    p=subprocess.run(['systemctl','--user','show',unit,'--property=ActiveState','--value'],capture_output=True,text=True,timeout=10)
    return p.returncode==0 and p.stdout.strip() in ('active','activating','reloading')
def reusable_active(active):
    if not active.get('url'):return False
    # A running independent connector owns the published hostname. Keep it even
    # during temporary resolver/backend trouble; rotating cannot repair that.
    if managed_unit(active.get('unit')):return unit_alive(active['unit'])
    # Legacy/external connections can be adopted without assuming ownership.
    try:verify_member_endpoint(active['url']);return True
    except Exception:return False
def start_connector():
    unit='kenbio-equipment-tunnel-'+uuid.uuid4().hex+'.service'
    connector=str(Path.home()/'.local/bin/cloudflared-equipment')
    command=['systemd-run','--user','--quiet','--collect','--unit='+unit,
        '--property=NoNewPrivileges=yes','--property=UMask=0077',
        '--property=Restart=no','--property=KillMode=control-group',
        '--property=WorkingDirectory='+str(ROOT),
        '--property=EnvironmentFile='+str(ROOT/'state/internet.env'),
        connector,'tunnel','--no-autoupdate','--no-prechecks','--edge-ip-version','4',
        '--protocol','http2','--url','http://127.0.0.1:18953']
    # No PartOf/BindsTo/Requires relationship to the manager: manager stop or
    # restart must not signal a connector already being used by members.
    p=subprocess.run(command,capture_output=True,text=True,timeout=20)
    if p.returncode:raise ValueError('Unable to start independent member connector')
    value={'unit':unit,'ready':False,'registered':False}
    write_state('public-api-candidate.json',value)
    return value
def connector_status(candidate):
    # Read bounded existing journal records instead of attaching a child to the
    # connector. A restarted manager can recover a candidate's URL immediately.
    p=subprocess.run(['journalctl','--user','--unit='+candidate['unit'],'--no-pager','--output=cat','-n','120'],capture_output=True,text=True,timeout=15)
    if p.returncode:raise ValueError('Unable to inspect member connector journal')
    match=re.search(r'https://[-a-z0-9]+\.trycloudflare\.com',p.stdout)
    if match:candidate={**candidate,'url':match[0]}
    if 'Registered tunnel connection' in p.stdout:candidate={**candidate,'registered':True}
    return candidate
def safe_reason(error):
    return re.sub(r'(https?://)[^/@\s]+@',r'\1[redacted]@',str(error))[:160]
def finish_replacement(previous,candidate):
    # Remote update and durable active state must succeed before retiring a
    # connector. Never stop external/legacy units or any unrelated service.
    publish(candidate['url'],candidate['unit'])
    write_state('public-api-candidate.json',{**candidate,'ready':True,'lastChecked':time.time()})
    old=previous.get('unit')
    if managed_unit(old) and old!=candidate['unit']:
        p=subprocess.run(['systemctl','--user','stop',old],capture_output=True,text=True,timeout=20)
        if p.returncode:print('Previous member connector retained; automatic cleanup failed',flush=True)
def prepare_candidate(candidate,previous):
    dns_ready_count=0;last_error_log=0
    while unit_alive(candidate['unit']):
        try:
            if not candidate.get('url') or not candidate.get('registered'):
                candidate=connector_status(candidate)
                if not candidate.get('url') or not candidate.get('registered'):raise ValueError('Waiting for member connector registration')
            if dns_ready_count<2:
                try:dns_ready=public_dns_ready(candidate['url'])
                except Exception:
                    dns_ready_count=0
                    raise
                dns_ready_count=dns_ready_count+1 if dns_ready else 0
                if dns_ready_count<2:raise ValueError('Public endpoint DNS is not yet provisioned')
            verify_member_endpoint(candidate['url'])
            finish_replacement(previous,candidate)
            return
        except Exception as error:
            reason=safe_reason(error)
            write_state('public-api-candidate.json',{**candidate,'ready':False,'lastChecked':time.time(),'error':type(error).__name__+': '+reason})
            if time.monotonic()-last_error_log>=60:
                print('Endpoint check '+candidate.get('url',candidate['unit'])+': '+reason,flush=True);last_error_log=time.monotonic()
            time.sleep(5)
    raise ValueError('Independent member connector stopped')
def main():
    last_active_log=0
    while True:
        try:
            active=read_state('public-api.json')
            candidate=read_state('public-api-candidate.json')
            # Resume an intentional pending replacement before adopting the
            # active route, leaving that route alive until publication succeeds.
            if candidate.get('unit')!=active.get('unit') and unit_alive(candidate.get('unit')):
                prepare_candidate(candidate,active)
                continue
            if reusable_active(active):
                try:verify_member_endpoint(active['url'])
                except Exception as error:
                    if time.monotonic()-last_active_log>=60:
                        print('Published member connector retained: '+safe_reason(error),flush=True);last_active_log=time.monotonic()
                time.sleep(30)
                continue
            candidate=read_state('public-api-candidate.json')
            if not unit_alive(candidate.get('unit')):candidate=start_connector()
            prepare_candidate(candidate,active)
        except Exception as error:
            print(type(error).__name__+': '+safe_reason(error)+'; retrying member manager',flush=True)
            time.sleep(5)
if __name__=='__main__':main()
