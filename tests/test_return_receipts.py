import unittest
from agent_returns import collective_return_view
class ReturnReceiptTests(unittest.TestCase):
 def view(self,n,old=None):
  p={'id':'a','checked':True,'quantity':n,'status':'已登记'}
  return collective_return_view([{'id':'rope','people':[p]}],{} if old is None else {('a','rope'):old})[0]
 def test_known_return_keeps_carrying_history(self):
  v=self.view(2,{'quantity':2,'original_quantity':2,'complete':1});self.assertEqual(v['people'][0]['quantity'],2);self.assertEqual(v['returnedRegistered'],2);self.assertEqual(v['outstandingRegistered'],0);self.assertTrue(v['people'][0]['returnConfirmed'])
 def test_unknown_quantity_return_does_not_invent_zero(self):
  v=self.view(None,{'quantity':None,'original_quantity':None,'complete':1});p=v['people'][0];self.assertIsNone(p['returned']);self.assertIsNone(p['outstanding']);self.assertTrue(p['returnConfirmed']);self.assertEqual(v['returnQuantityUnknownPeople'],1)
 def test_later_quantity_change_needs_new_review(self):
  p=self.view(3,{'quantity':2,'original_quantity':2,'complete':1})['people'][0];self.assertFalse(p['returnConfirmed']);self.assertIsNone(p['returned']);self.assertEqual(p['returnStatus'],'归还数量待核实')
 def test_unrecorded_return_is_not_completed(self):self.assertFalse(self.view(1)['people'][0]['returnConfirmed'])
