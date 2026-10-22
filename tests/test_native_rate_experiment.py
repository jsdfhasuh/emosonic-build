"""Public synthetic gate fixtures; no private native source or captured logs."""
import copy
import contextlib
import io
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_rate_experiment as g


def report():
    def fill(shape):
        if shape=='boolean':return True
        if shape=='finite_number':return 0
        if shape=='finite_number_or_null':return None
        if set(shape)=={'literal'}:return shape['literal']
        if set(shape)=={'enum'}:return shape['enum'][0]
        if set(shape)=={'array'}:return []
        return {key:fill(value) for key,value in shape.items()}
    contract=g.schema();value=fill(contract['reportShape'])
    value.update(schemaVersion=1,hostLeadSupplied=False,trialCount=16,completedTrials=16,fullyMeasuredTrials=16)
    for index in range(16):
        row=fill(contract['reportShape']['trials']['array'])
        row.update(trialOrdinal=index+1,arm=contract['orders'][index//4][index%4],round=index//4+1,order=index%4+1,
            sampleCount=161,validSampleCount=161,transitionCount=2,windowCount=2,status='completed')
        for ordinal in (1,2):
            window=fill(contract['reportShape']['trials']['array']['windows']['array']);window['ordinal']=ordinal
            row['windows'].append(window);row['windowObservations'].append({'ordinal':ordinal,'status':'observed'})
        value['trials'].append(row)
    return value


class NativeRateExperimentTests(unittest.TestCase):
    def test_exact_schema_and_all_counterbalanced_trials(self):
        value=report();self.assertIs(g.validate_report(value),value);self.assertTrue(g.experiment_complete(value))
        self.assertEqual(hashlib.sha256(Path(g.__file__).with_name('native_rate_experiment_schema.json').read_bytes()).hexdigest(),g.SCHEMA_SHA)

    def test_any_deficit_sign_is_not_an_improvement_gate(self):
        for deficit in (-100000,0,100000):
            value=report()
            for row in value['trials']:
                for window in row['windows']:window['minimumDeficitMediaMs']=deficit
            self.assertTrue(g.experiment_complete(g.validate_report(value)))

    def test_failed_or_partially_measured_trial_remains_and_fails(self):
        value=report();value['trials'][3].update(status='load_not_ready',fullyMeasured=False)
        value.update(completedTrials=15,fullyMeasuredTrials=15)
        self.assertFalse(g.experiment_complete(g.validate_report(value)))
        self.assertEqual(len(value['trials']),16)

    def test_missing_duplicate_reordered_or_invented_trial_refused(self):
        for edit in (lambda x:x['trials'].pop(),lambda x:x['trials'][1].update(trialOrdinal=1),
                     lambda x:x['trials'].reverse(),lambda x:x.update(completedTrials=15)):
            value=report();edit(value)
            with self.assertRaises(g.request.p.GateError):g.validate_report(value)

    def test_private_strings_unknown_keys_nonfinite_bool_numbers_refused(self):
        for edit in (lambda x:x.update(private='SECRET'),lambda x:x['trials'][0].update(status='private-error'),
            lambda x:x['trials'][0].update(loadElapsedMs=float('nan')),lambda x:x.update(trialCount=True),
            lambda x:x.update(sandboxIdentityVerified=1),lambda x:x['trials'][0].update(sampleCount=182)):
            value=report();edit(value)
            with self.assertRaises(g.request.p.GateError):g.validate_report(value)

    def test_window_inventory_and_shape_fail_closed(self):
        for edit in (lambda x:x['trials'][0]['windows'].pop(),lambda x:x['trials'][0]['windowObservations'].reverse(),
                     lambda x:x['trials'][0]['windows'][0].update(ordinal=2),lambda x:x['trials'][0]['windows'][0].update(path='/private/token')):
            value=report();edit(value)
            with self.assertRaises(g.request.p.GateError):g.validate_report(value)

    def test_cleanup_and_sandbox_claims_are_required(self):
        for key in ('sandboxIdentityVerified','ownedMediaRemoved'):
            value=report();value[key]=False;self.assertFalse(g.experiment_complete(g.validate_report(value)))
        value=report();value['trials'][0]['cleanupStopped']=False;value['allCleanupStopped']=False
        self.assertFalse(g.experiment_complete(g.validate_report(value)))

    def test_bundle_identity_is_exact_run_attempt_not_arbitrary_path(self):
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'123456','GITHUB_RUN_ATTEMPT':'2'}):
            self.assertEqual(g.bundle_identity(),'com.emosonic.rateexperiment.run123456.attempt2')
        for text in ('0','../x','1;evil','1\n','9'*21):
            with patch.dict(os.environ,{'GITHUB_RUN_ID':text,'GITHUB_RUN_ATTEMPT':'1'}):
                with self.assertRaises(g.request.p.GateError):g.bundle_identity()

    def test_child_environment_strips_credentials_and_command_files(self):
        values={k:'PRIVATE' for k in ('SOURCE_READ_TOKEN','GITHUB_TOKEN','GITHUB_ENV','GITHUB_OUTPUT','GITHUB_PATH','GITHUB_STEP_SUMMARY')}
        with patch.dict(os.environ,values):out=g.environment(Path('/owned/tmp'))
        self.assertTrue(all(k not in out for k in values));self.assertEqual(out['TMPDIR'],'/owned/tmp')
        self.assertEqual(out['PYTHONDONTWRITEBYTECODE'],'1')

    def test_compile_diagnostic_only_finite_locations_categories(self):
        raw=b'/private/SECRET.m:0:9: error: use of undeclared identifier TOKEN\n'+b'/x:12:4: error: expected SECRET\n'*20
        value=g.compile_diagnostic(raw);text=json.dumps(value)
        self.assertEqual(value['errorCount'],21);self.assertEqual(len(value['errors']),12);self.assertTrue(value['truncated'])
        self.assertEqual(value['errors'][0],{'line':0,'column':9,'category':'unknown_identifier'})
        self.assertNotIn('SECRET',text);self.assertNotIn('TOKEN',text);self.assertNotIn('/private',text)

    def test_native_exit_codes_are_finite_without_stderr_or_payload(self):
        for exit_code in (4,5,6):
            with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()) as visible:
                root=Path(temp)
                code,_,_=g.bounded([sys.executable,'-c',f'import sys;print("PRIVATE");print("SECRET",file=sys.stderr);sys.exit({exit_code})'],root,'native',2,g.environment(root))
            self.assertEqual(code,exit_code)
            self.assertEqual(json.loads(visible.getvalue()),{'stage':'native-rate-experiment-command','status':'failed',
                'phase':'native','reason':'command_failed','exitCode':exit_code})

    def test_spawn_failure_emits_only_allowlisted_reason(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()) as visible:
            root=Path(temp)
            with patch.object(g.subprocess,'Popen',side_effect=FileNotFoundError('PRIVATE PATH')):
                with self.assertRaises(g.request.p.GateError):g.bounded(['missing'],root,'compile',2,g.environment(root))
        self.assertEqual(json.loads(visible.getvalue())['reason'],'spawn_failed')
        self.assertNotIn('PRIVATE',visible.getvalue())

    def test_bounded_process_is_reaped_on_timeout_and_outputs_private(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaises(g.request.p.GateError):
                g.bounded([sys.executable,'-c','import time;print("PRIVATE",flush=True);time.sleep(10)'],root,'native',.05,g.environment(root))
            self.assertFalse((root/'active.json').exists());self.assertIn('PRIVATE',(root/'native.stdout').read_text())

    def test_normal_process_exit_and_byte_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);code,out,_=g.bounded([sys.executable,'-c','print(123)'],root,'native',2,g.environment(root))
            self.assertEqual(code,0);self.assertEqual(out.read_text(),'123\n');self.assertFalse((root/'active.json').exists())
        with tempfile.TemporaryDirectory() as temp,patch.object(g,'MAX_BYTES',16):
            root=Path(temp)
            with self.assertRaises(g.request.p.GateError):g.bounded([sys.executable,'-c','print("x"*100)'],root,'native',2,g.environment(root))

    def test_cleanup_preserves_unclaimed_preexisting_container(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/g.WORK;work.mkdir();container=root/'container';container.mkdir();(container/'keep').write_text('owned elsewhere')
            (work/'ownership.json').write_text(json.dumps({'bundle':'fixture','containerInitiallyAbsent':True,'launchAttempted':False}))
            with patch.object(g.request.p,'ROOT',root),patch.object(g,'bundle_identity',return_value='fixture'),patch.object(g,'container_path',return_value=container):g.cleanup_owned()
            self.assertTrue((container/'keep').exists());self.assertFalse(work.exists())

    def test_cleanup_only_claimed_container_after_verified_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/g.WORK;work.mkdir();container=root/'container';container.mkdir()
            (work/'ownership.json').write_text(json.dumps({'bundle':'fixture','containerInitiallyAbsent':True,'launchAttempted':True}))
            (work/'active.json').write_text(json.dumps({'pid':123,'label':'native'}))
            context=(patch.object(g.request.p,'ROOT',root),patch.object(g,'bundle_identity',return_value='fixture'),patch.object(g,'container_path',return_value=container))
            with context[0],context[1],context[2],patch.object(g.os,'killpg'):
                with self.assertRaises(g.request.p.GateError):g.cleanup_owned()
            self.assertTrue(container.exists())
            with patch.object(g.request.p,'ROOT',root),patch.object(g,'bundle_identity',return_value='fixture'),patch.object(g,'container_path',return_value=container),patch.object(g.os,'killpg',side_effect=ProcessLookupError):g.cleanup_owned()
            self.assertFalse(container.exists());self.assertFalse(work.exists())

    def test_no_flutter_network_entitlement_upload_or_fallback(self):
        root=Path(__file__).resolve().parents[1];workflow=(root/'.github/workflows/native-rate-experiment.yml').read_text()
        self.assertEqual(g.ENTITLEMENTS,{'com.apple.security.app-sandbox':True})
        for forbidden in ('flutter-action','upload-artifact','RELEASE_WRITE_TOKEN','network.client','network.server'):self.assertNotIn(forbidden,workflow)
        self.assertIn('if: always()',workflow);self.assertIn('macos-26',workflow)
        source=Path(g.__file__).read_text();self.assertIn('bounded([str(binary)]',source)
        self.assertNotIn('sandbox-exec',source);self.assertNotIn('source_context(',source)

    def test_fixed_request_pins_and_no_publish_stage(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root/g.REQUEST_PATH).read_text()),g.REQUEST)
        self.assertEqual(g.SOURCE_SHA,'7e040ebbfcc08ea16a05ee0a359036c7f3e4d4fe')
        with patch.object(sys,'argv',['gate','publish']):self.assertEqual(g.main(),1)


if __name__=='__main__':unittest.main()
