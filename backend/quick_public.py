"""Maintain the temporary member API and publish its current address to Pages.

No Hub or Tailscale routing is changed. Requires the user's existing gh login.
"""
import base64,json,os,re,subprocess,tempfile,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=os.environ.get('EQUIPMENT_GITHUB_REPO','kenbio216/ToolsAgent')
REMOTE='frontend/public/api-config.json'
def publish(url):
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
    state=ROOT/'state/public-api.json';state.parent.mkdir(exist_ok=True);state.write_text(json.dumps({'url':url,'temporary':True}));state.chmod(0o600)
    print('Member API verified; Pages connection configured',flush=True)
def main():
    connector=str(Path.home()/'.local/bin/cloudflared-equipment')
    while True:
        proc=subprocess.Popen([connector,'tunnel','--no-autoupdate','--no-prechecks','--edge-ip-version','4','--protocol','http2','--url','http://127.0.0.1:18953'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        url=None;published=False
        try:
            for line in proc.stdout:
                match=re.search(r'https://[-a-z0-9]+\.trycloudflare\.com',line)
                if match:url=match[0]
                if url and not published and 'Registered tunnel connection' in line:
                    print('Checking member endpoint '+url,flush=True)
                    while proc.poll() is None:
                        try:
                            with urllib.request.urlopen(url+'/health',timeout=12) as r:assert json.load(r).get('ok')
                            publish(url);published=True;break
                        except Exception as e:print('Endpoint check: '+str(e)[:160],flush=True);time.sleep(5)
                    if not published:raise ValueError('Temporary API or Pages update not ready')
            proc.wait()
        except Exception as e:print(type(e).__name__+': '+str(e)[:140]+'; reconnecting member API',flush=True)
        finally:
            if proc.poll() is None:proc.terminate()
            try:proc.wait(timeout=12)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        time.sleep(5)
if __name__=='__main__':main()
