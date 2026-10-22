import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_native_check as n

class NativeOutputTests(unittest.TestCase):
    def test_drops_raw_lines(self):
        self.assertIsNone(n.report_line('Authorization: private-token'))
        self.assertIsNone(n.report_line('Traceback (most recent call last)'))

    def test_only_static_classifications_and_numeric_metrics(self):
        value = {'stage':'handoff-continuity', 'status':'passed', 'positionMs':1234,
                 'password':'secret-value', 'url':'http://secret.example',
                 'compilerDiagnostics':[{'message':'private source', 'line':3}],
                 'nested':{'account':'private-user', 'driftMs':1.2},
                 'array':['private-id', 2, False]}
        out=n.report_line(json.dumps(value))
        encoded=json.dumps(out)
        for secret in ['secret-value','secret.example','private source','private-user','private-id']:
            self.assertNotIn(secret,encoded)
        self.assertEqual(out['positionMs'],1234)
        self.assertNotIn('nested',out)
        self.assertNotIn('compilerDiagnostics',out)
        self.assertEqual(out['status'],'passed')

    def test_rejects_arbitrary_text_classifications(self):
        out=n.report_line(json.dumps({'stage':'http://secret', 'status':'secret value', 'errorType':'some secret'}))
        self.assertFalse(out)

    def test_regex_compatible_secrets_and_arbitrary_keys_rejected(self):
        self.assertIsNone(n.report_line(json.dumps({'stage':'private_token_ABC',
            'status':'private_token_ABC', 'errorType':'PrivateAccount', 'PrivateAccount123':123})))
        self.assertEqual(n.report_line(json.dumps({'stage':'build-authority','status':'passed',
            'count':3, 'positionMs':float('nan')})), {'stage':'build-authority','status':'passed','count':3})

    def test_command_files_removed(self):
        with patch.object(n.p, 'build_env', return_value={'GITHUB_ENV':'x','GITHUB_OUTPUT':'x',
                'GITHUB_PATH':'x','GITHUB_STEP_SUMMARY':'x','PATH':'safe'}):
            self.assertEqual(n.native_env(), {'PATH':'safe'})

    def test_cleanup_is_constrained_and_never_signals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'repo'; root.mkdir()
            temp=Path(temporary)/'temp'; temp.mkdir()
            env={'RUNNER_TEMP':str(temp),'GITHUB_RUN_ID':'1','GITHUB_RUN_ATTEMPT':'1'}
            with patch.dict(os.environ,env), patch.object(n.p,'ROOT',root):
                output=n.output_path(); output.mkdir()
                server=root/'.native-server'; server.mkdir()
                unrelated=temp/'unrelated'; unrelated.mkdir()
                source=root/'source'; source.mkdir()
                with patch.object(n.subprocess,'run',return_value=SimpleNamespace(returncode=0,
                        stdout='123 /usr/bin/safe-process\n')) as run:
                    n.cleanup()
                    run.assert_called_once()
                    self.assertEqual(run.call_args.args[0], ['ps','-ww','-axo','pid=,command='])
                self.assertFalse(output.exists()); self.assertFalse(server.exists())
                self.assertTrue(source.exists()); self.assertTrue(unrelated.exists())

    def test_cleanup_refuses_active_or_unverifiable_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'repo'; root.mkdir()
            env={'RUNNER_TEMP':temporary,'GITHUB_RUN_ID':'1','GITHUB_RUN_ATTEMPT':'1'}
            with patch.dict(os.environ,env), patch.object(n.p,'ROOT',root):
                output=n.output_path(); output.mkdir()
                for result in (SimpleNamespace(returncode=1,stdout=''),
                               SimpleNamespace(returncode=0,stdout='123 '+str(output)+'/EmoSonic.app\n'),
                               SimpleNamespace(returncode=0,stdout='unparseable')):
                    with patch.object(n.subprocess,'run',return_value=result):
                        with self.assertRaises(n.p.GateError): n.cleanup()
                    self.assertTrue(output.exists())

    def test_cleanup_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'repo'; root.mkdir()
            env={'RUNNER_TEMP':temporary,'GITHUB_RUN_ID':'1','GITHUB_RUN_ATTEMPT':'1'}
            with patch.dict(os.environ,env), patch.object(n.p,'ROOT',root):
                output=n.output_path(); output.symlink_to(root, target_is_directory=True)
                with self.assertRaises(n.p.GateError): n.cleanup()

    def test_terminal_handoff_diagnostics_preserve_only_reviewed_fields(self):
        record={'role':'target','status':'failed','errorCode':'prepare_failed',
            'knownFailureReason':'source_sample_stale','contextMatches':True,
            'controlVersion':27,'errorMessage':'PRIVATE_TOKEN','contextId':'PRIVATE_ID'}
        value={'stage':'handoff-native-completion','status':'failed','errorType':'AssertionError',
            'handoffDiagnostics':[{'role':'target','nativeEvidenceValid':True,
                'handoff':record,'handoffHistory':[record]*12,'clientId':'PRIVATE_ID'}]*5}
        out=n.report_line(json.dumps(value))
        self.assertEqual(len(out['handoffDiagnostics']),3)
        self.assertEqual(len(out['handoffDiagnostics'][0]['handoffHistory']),8)
        handoff=out['handoffDiagnostics'][0]['handoff']
        self.assertEqual(handoff['knownFailureReason'],'source_sample_stale')
        self.assertEqual(handoff['status'],'failed')
        self.assertNotIn('PRIVATE',json.dumps(out))

    def test_native_failure_and_readiness_are_distinguishable(self):
        value={'nativeErrors':[{'role':'target','nativeErrorDomain':'AVFoundationErrorDomain',
                'nativeErrorCode':-11800,'message':'PRIVATE'}],
            'nativePlayback':[{'clientOrdinal':1,'trackMatchesFirstClient':False,
                'native':[{'avPlayerStatus':2,'avItemStatus':2,'playbackState':4,
                    'avTimeControlStatus':0,'playbackRate':0,'positionMs':1200,
                    'id':'PRIVATE','sampledAtMs':1234567}]}]}
        out=n.report_line(json.dumps(value))
        self.assertEqual(out['nativeErrors'][0]['nativeErrorCode'],-11800)
        self.assertEqual(out['nativePlayback'][0]['native'][0]['avItemStatus'],2)
        self.assertNotIn('sampledAtMs',json.dumps(out)); self.assertNotIn('PRIVATE',json.dumps(out))

    def test_diagnostic_rejects_wrong_types_out_of_range_and_unknown_enums(self):
        value={'handoffDiagnostics':[{'role':'private_token','nativePlaying':1,
            'controlVersion':True,'handoff':{'status':'PRIVATE','knownFailureReason':'SECRET'},
            'native':[{'positionMs':1e99,'playbackRate':float('inf'),'avItemStatus':99}]}],
            'nativeErrors':[{'role':'target','nativeErrorDomain':'private_token','nativeErrorCode':2**64}],
            'nativePlayback':[{'clientOrdinal':3}], 'positionMs':float('inf')}
        out=n.report_line(json.dumps(value))
        self.assertEqual(out['nativeErrors'],[{'role':'target'}])
        self.assertEqual(out['nativePlayback'],[])
        self.assertNotIn('PRIVATE',json.dumps(out)); self.assertNotIn('private_token',json.dumps(out))
        self.assertNotIn('positionMs',json.dumps(out)); self.assertNotIn('controlVersion',json.dumps(out))
        self.assertNotIn('nativePlaying',json.dumps(out))

    def test_server_canonical_schema_omits_ids_and_payloads(self):
        canonical={'state':'playing','authorityIsTarget':True,'controlVersion':28,
            'queueMatchesBaseline':True,'trackId':'PRIVATE','queueSongIds':['PRIVATE']}
        value={'serverCanonicalObservation':{'status':'read_only_snapshot',
            'currentCanonical':canonical,'cachedCanonicalPayload':canonical,
            'devices':[{'role':'target','present':True,'generationMatches':True,
                'appliedControlVersion':28,'deviceSessionId':'PRIVATE'}],
            'handoff':{'status':'completed','completionCanonicalPresent':True,
                'completionCanonical':canonical,'provisionalControlVersion':28,
                'completionProof':{'trackMatchesBaseline':True,'queueIndex':0,
                    'appliedControlVersion':28,'trackId':'PRIVATE'}}}}
        out=n.report_line(json.dumps(value))['serverCanonicalObservation']
        self.assertEqual(out['currentCanonical']['controlVersion'],28)
        self.assertEqual(out['handoff']['completionProof']['appliedControlVersion'],28)
        self.assertNotIn('PRIVATE',json.dumps(out))
        self.assertEqual(n.report_line(json.dumps({'serverCanonicalObservation':{
            'status':'observation_unavailable','errorType':'OperationalError','error':'PRIVATE'}})),
            {'serverCanonicalObservation':{'status':'observation_unavailable','errorType':'OperationalError'}})

    def test_diagnostic_schemas_are_path_specific(self):
        value={'status':'completed', 'knownFailureReason':'source_sample_stale',
            'nativeErrors':[{'status':'failed','knownFailureReason':'source_sample_stale'}],
            'serverCanonicalObservation':{'errorType':'AssertionError','status':'failed'}}
        self.assertEqual(n.report_line(json.dumps(value)),{'nativeErrors':[]})

    def test_workflow_uses_exact_approved_native_boundary(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/current-source-check.yml').read_text()
        self.assertIn('EMOSONIC_MAC_LAB_NETWORK_APPROVED',text)
        self.assertIn('ref: '+n.request.SERVER_SHA,text)
        section=text[text.index('  native-macos-server:'):]
        self.assertNotIn('upload-artifact', section)
        self.assertNotIn('ANDROID_KEYSTORE', section)
        self.assertLess(section.index('current_native_check.py preflight'),section.index('subosito/flutter-action'))

if __name__=='__main__':
    unittest.main()
