import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import follow_ingress_green as g
import fixed_flutter_green as f

class StorageValidationTest(unittest.TestCase):
    def test_three_private_literals_are_hash_pinned(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/g.STORAGE_PATH;p.parent.mkdir(parents=True)
            raw=b"testWidgets('private a', () {});testWidgets('private b', () {});testWidgets('private c', () {});"
            p.write_bytes(raw)
            with patch.object(g,'STORAGE_SHA256',hashlib.sha256(raw).hexdigest()):
                self.assertEqual(len(g.storage_inventory(root)['names']),3)
                p.write_bytes(raw+b' ')
                with self.assertRaises(g.recovery.request.p.GateError):g.storage_inventory(root)

    def test_storage_does_not_emit_ingress_observations(self):
        with patch.object(g,'ORIGINAL_OBSERVER',return_value={}),patch.object(g.ingress,'phase_observation') as obs:
            g.focused_observation('',0,expected_names=['a','b','c'],fixture_basename=Path(g.STORAGE_PATH).name)
            obs.assert_not_called()

    def test_hidden_error_and_finite_runner_categories(self):
        for message,category in [('FlutterError: private','FlutterError'),('A Timer is still pending private','pending-timer'),('Shell subprocess crashed private','shell-crash'),('Test timed out after private','test-timeout'),('Failed to load private','test-load-failed')]:
            for hidden in (False,True):
                events=[dict(type='testStart',test=dict(id=1,name='private')),dict(type='error',testID=1,isFailure=False,error=message),dict(type='testDone',testID=1,hidden=hidden,result='error',skipped=False)]
                report=f.observe_green('\n'.join(map(json.dumps,events)),1,expected_names=['private'],fixture_basename='fixture_test.dart')
                self.assertEqual(report['errors'][0]['category'],category)
                self.assertEqual(report['errors'][0]['hidden'],hidden)
                self.assertEqual(report['errors'][0]['result'],'error')
                self.assertNotIn('private',json.dumps(report))

    def test_full_observer_preserves_hidden_error(self):
        events=[dict(type='suite',suite=dict(id=7,path='/owned/test/ui/x_test.dart')),dict(type='testStart',test=dict(id=1,name='private',suiteID=7)),dict(type='error',testID=1,isFailure=False,error='SocketException: secret'),dict(type='testDone',testID=1,hidden=True,result='error',skipped=False)]
        report=g.recovery.full_test_observation('\n'.join(map(json.dumps,events)),'',['test/ui/x_test.dart'],Path('/owned'),[],1)
        self.assertEqual(report['errors'][0]['hidden'],True)
        self.assertEqual(report['errors'][0]['category'],'SocketException')
        self.assertNotIn('secret',json.dumps(report))

    def test_malformed_error_ids_never_alias_or_crash(self):
        for tid in ([], {}, True, None, '1'):
            events=[dict(type='testDone',testID=1,hidden=True,result='error',skipped=False),dict(type='error',testID=tid,isFailure=False,error='secret')]
            report=f.observe_green('\n'.join(map(json.dumps,events)),1,expected_names=['private'],fixture_basename='fixture_test.dart')
            self.assertNotIn('hidden',report['errors'][0])
            self.assertNotIn('result',report['errors'][0])
