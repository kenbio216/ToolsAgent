"""A return receipt preserves the original collective carrying record."""
def collective_return_view(items,receipts):
    result=[]
    for item in items:
        people=[]
        for person in item['people']:
            p=dict(person);receipt=receipts.get((p['id'],item['id']))
            same=bool(receipt and p['checked'] and receipt['original_quantity']==p['quantity'])
            complete=bool(same and receipt['complete'])
            returned=receipt['quantity'] if same else None
            outstanding=None if not p['checked'] or p['quantity'] is None else max(0,p['quantity']-(returned or 0))
            status=('已归还（原数量未填）' if p['quantity'] is None else '已归还') if complete else ('归还数量待核实' if receipt and not same else '归还未登记')
            if not p['checked']:status=p['status'];returned=None
            p.update(returned=returned,outstanding=outstanding,returnConfirmed=complete,returnStatus=status)
            people.append(p)
        result.append({**item,'people':people,'returnedRegistered':sum(p['returned'] or 0 for p in people if p['checked']),
                       'outstandingRegistered':sum(p['outstanding'] or 0 for p in people),'returnedPeople':sum(p['returnConfirmed'] for p in people),
                       'returnQuantityUnknownPeople':sum(p['returnConfirmed'] and p['quantity'] is None for p in people)})
    return result
