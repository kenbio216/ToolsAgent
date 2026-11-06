"""Explicit personal equipment sources; human summary without operational logs."""
from agent_catalog import CORE

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
