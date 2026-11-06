"""The live-read collective plan and writes confined to a new carrying sheet."""
import json
from pathlib import Path
from agent_catalog import PEOPLE,BY_PERSON
from agent_service import Conflict,stamp

GROUP=json.loads(Path(__file__).with_name('group_plan.json').read_text())['items']
GROUP_BY_ID={i['id']:i for i in GROUP}
GROUP_SHEET='集体装备携带核对'

def prepare_collective(s):
    with s.lock:
        names={r['sheet_name'] for r in s.cli(['+workbook-info'])['sheets']}
        if GROUP_SHEET not in names:
            rows=[[p['name'],i['name'],'','待核对','','新增',''] for p in PEOPLE for i in GROUP]
            s.new_sheet(GROUP_SHEET,['姓名','集体装备','实际携带数量','核对状态','更新时间','变更标记','登记编号'],rows)
            return True
        return False

def sync_collective(s,event):
    target=event.get('target')
    if target not in {p['id'] for p in PEOPLE}:raise Conflict('姓名尚未匹配十险名单')
    with s.lock:
        prepare_collective(s)
        rows=s.values(GROUP_SHEET)
        lookup={}
        for r,row in enumerate(rows[1:],2):
            if len(row)>=2:
                key=(row[0],row[1])
                if key in lookup:raise Conflict('集体携带表出现重复人员装备行，请先核对')
                lookup[key]=r
        writes=[]
        for ident,value in event['collective_after'].items():
            item=GROUP_BY_ID[ident];key=(BY_PERSON[target]['name'],item['name'])
            if key not in lookup:raise Conflict('集体携带表的人员或装备名称已变动，未覆盖其他行')
            n=value.get('quantity');cells=[n if n is not None and value['checked'] else '',
                '已核对携带' if value['checked'] else '本次未携带',event['created'],'此行被修改，待查看',event['id']]
            writes.append({'sheet_name':GROUP_SHEET,'range':f'C{lookup[key]}:G{lookup[key]}','cells':[[{'value':v} for v in cells]]})
        if writes:s.write(writes)
        after=s.values(GROUP_SHEET)
        for ident,value in event['collective_after'].items():
            r=lookup[(BY_PERSON[target]['name'],GROUP_BY_ID[ident]['name'])]
            if len(after[r-1])<7 or after[r-1][6]!=event['id']:raise Conflict('集体装备核对回读未匹配，记录已保留待重试')
