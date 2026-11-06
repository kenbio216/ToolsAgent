"""Confirmed essential-gear facts and a deterministic post-registration question."""
from agent_catalog import BY_ITEM

ESSENTIALS = ('headlamp', 'blanket', 'raincoat', 'radio')
RESPONSE_LABELS = {'deferred': '暂不补充登记（未确认持有）', 'unprepared': '尚未准备'}


def responses(raw):
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > len(ESSENTIALS):
        raise ValueError('请逐项说明必备装备的情况')
    result, seen = [], set()
    for value in raw:
        if not isinstance(value, dict) or value.get('item') not in ESSENTIALS or value.get('status') not in RESPONSE_LABELS or value['item'] in seen:
            raise ValueError('必备装备说明无效或重复')
        detail = value.get('detail', '')
        if not isinstance(detail, str) or len(detail) > 160:
            raise ValueError('请简短说明必备装备的情况')
        result.append({'item': value['item'], 'status': value['status'], 'detail': detail.strip()})
        seen.add(value['item'])
    return result


def readiness(d, source, items):
    declared = {r['item']: dict(r) for r in d.execute('SELECT item,status,detail FROM essential_responses WHERE person=?', (source,))}
    # Only an actual positive carrying record counts, never a plan or a checkbox
    # with unknown quantity. This is carrying evidence, not proof of ownership.
    radio = d.execute("SELECT checked,quantity FROM group_items WHERE person=? AND item='radio_spare'", (source,)).fetchone()
    result = []
    for item in ESSENTIALS:
        value = items[item]
        owned = value['owned']
        borrowed = max(0, value['borrowed'] - value['returned'])
        carrying = item == 'radio' and radio is not None and radio['checked'] and (radio['quantity'] or 0) > 0
        response = declared.get(item, {})
        result.append({'item': item, 'name': BY_ITEM[item]['name'], 'owned': owned, 'borrowedOpen': borrowed,
                       'status': 'recorded' if owned + borrowed > 0 or carrying else response.get('status', 'unknown'),
                       'detail': '已确认实际携带对讲机' if carrying else response.get('detail', '')})
    return result


def followup(state):
    missing = {i['item'] for i in state if i['status'] == 'unknown'}
    if not missing:
        return ''
    names = []
    trio = {'headlamp', 'blanket', 'raincoat'}
    if trio <= missing:
        names.append('救生三件套（头灯、救生毯、雨衣）')
        missing -= trio
    names.extend(BY_ITEM[i]['name'] for i in ESSENTIALS if i in missing)
    return '另外，还没有记录' + '、'.join(names) + '的持有情况。您是自备了这些装备，还是需要补充登记？尚未准备也可以直接说明。'
