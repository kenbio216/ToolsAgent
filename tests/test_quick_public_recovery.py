import sys,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from quick_public import connector_revoked
class ConnectorRecoveryTests(unittest.TestCase):
 def test_only_repeated_explicit_recent_revocation_replaces_live_connector(self):
  unit='kenbio-equipment-tunnel-'+'a'*32+'.service';terminal='Register tunnel error from server side error="Unauthorized: Tunnel not found"\n'
  with patch('quick_public.subprocess.run') as run:
   run.return_value=subprocess.CompletedProcess([],0,terminal*3,'');self.assertTrue(connector_revoked(unit));self.assertIn('--since=-2min',run.call_args.args[0])
   for log in [terminal*2,'TLS handshake failed\n'*10,'origin service connection refused\n'*10]:
    run.return_value=subprocess.CompletedProcess([],0,log,'');self.assertFalse(connector_revoked(unit))
 def test_external_service_cannot_be_inspected_or_replaced(self):
  with patch('quick_public.subprocess.run') as run:
   self.assertFalse(connector_revoked('some-unrelated.service'));run.assert_not_called()
