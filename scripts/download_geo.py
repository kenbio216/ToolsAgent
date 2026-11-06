import json,urllib.request,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'backend';meta=json.loads((root/'geo-data/source.json').read_text())
for item in meta['files']:
 if not item['path'].endswith('.xdb'):continue
 path=root/item['path'];url='https://raw.githubusercontent.com/lionsoul2014/ip2region/'+meta['commit']+'/data/'+path.name
 with urllib.request.urlopen(url,timeout=90) as r:data=r.read()
 assert hashlib.sha256(data).hexdigest()==item['sha256']
 path.parent.mkdir(exist_ok=True);path.write_bytes(data);print(path.name)
