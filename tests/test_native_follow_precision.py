"""Public synthetic contracts only; actual private methods run in hosted proof."""
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_follow_readiness as r
import native_follow_lifecycle as lifecycle
import native_seek_anchor_observation as timing
import current_native_check as public

class StrictPrecisionPublicTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('public_precision_fixture',r.ROOT/'native_follow_readiness_payload/precision_contract.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

    def test_exact_35_final_method_cases_and_distinct_prior_provenance(self):
        m=self.load();self.assertEqual(len(m.TEST_NAMES),35);self.assertEqual(len(set(m.TEST_NAMES)),35)
        self.assertEqual(r.PRECISION_CHECKS,35)
        self.assertNotEqual(r.PRECISION_PRIOR_SHA256,r.AFTER[r.LAB])
        self.assertEqual(r.expected_proof()['precision']['checks'],35)
        self.assertEqual(r.expected_proof()['priorAcceptanceHarness'],r.PRECISION_PRIOR_SHA256)

    def test_exact_payload_and_chain_pins(self):
        for name in r.PAYLOAD_HASHES:r.payload(name)
        self.assertEqual(lifecycle.BEFORE_SHA256,r.AFTER[r.LAB])
        self.assertEqual(timing.HARNESS_SHA,lifecycle.AFTER_HARNESS_SHA256)
        self.assertTrue(r.expected_manifest()['strictSampledFollowAcceptance'])
        self.assertEqual(r.expected_manifest()['strictFollowDriftBoundMs'],50)

    def test_no_added_poll_sleep_media_or_control_call_in_predicate(self):
        tree=ast.parse(r.payload('follow_precision_helpers.py'))
        calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        for forbidden in ('matrix.states','matrix.wait','time.sleep','matrix.clients','open'):
            self.assertNotIn(forbidden,calls)
        self.assertNotIn('command',calls)

    def test_all_prior_assertions_are_retained_by_transform_guard(self):
        tree=ast.parse(Path(r.__file__).read_text())
        f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='strengthen_follow_precision')
        text=ast.unparse(f)
        self.assertIn('restore_follow_precision(result) != original',text)
        self.assertIn('new_asserts.count(item) < old_asserts.count(item)',text)

    def test_nominal_is_distinct_from_existing_correction_cap(self):
        m=self.load();ns={'math':math,'decoded':lambda s:s['nativePlayers'][0],
            'native_requested_rate':lambda s:s['nativePlayers'][0]['requestedRate'],
            'native_rate_matches':lambda s,e,follower=False: abs(s['nativePlayers'][0]['playbackRate']-e)<(.06001 if follower else .0001),
            'follow_native_rate_bounds':lambda s,e:(e*.96,e*1.04)}
        exec(r.payload('follow_precision_helpers.py'),ns)
        s=m.pair(0);self.assertTrue(ns['follow_nominal_precision_ready'](s[0],s[2],1.5))
        s[2]['nativePlayers'][0].update(playbackRate=1.56,requestedRate=1.56)
        self.assertFalse(ns['follow_nominal_precision_ready'](s[0],s[2],1.5))

    def test_fixed_zero_lead_and_fifty_policy(self):
        m=self.load();ns={'math':math,'decoded':lambda s:s['nativePlayers'][0],
            'native_requested_rate':lambda s:s['nativePlayers'][0]['requestedRate'],
            'native_rate_matches':lambda *a,**kw:True,'follow_native_rate_bounds':lambda s,e:(e*.96,e*1.04)}
        exec(r.payload('follow_precision_helpers.py'),ns)
        for key,value in (('followSyncToleranceMs',51),('followSyncToleranceMs',True),('followLeadCompensationMs',1),('followLeadCompensationMs',False)):
            s=m.pair(0);s[2][key]=value
            with self.assertRaises(AssertionError):ns['follow_nominal_precision_ready'](s[0],s[2],1.5)

    def test_finite_precision_export_preserves_failure_evidence(self):
        sample={'stage':'follower-avplayer-rate-1.5','status':'failed','rateMeasurement':{
            'precisionSamples':16,'precisionDriftMs':-49,'precisionUncertaintyMs':4,
            'precisionWorstCaseMs':53,'precisionMaxWorstCaseMs':53,
            'precisionSourceNative':{'positionMs':10000},'precisionFollowerNative':{'positionMs':9951},
            'initialFollowAcquisitionMs':450,'initialFollowCommandToMeasurementEndMs':6400}}
        self.assertEqual(public.report_line(json.dumps(sample)),sample)
        sample['rateMeasurement'].update(privateIdentity='do-not-export',precisionDriftMs=float('nan'))
        value=public.report_line(json.dumps(sample))
        self.assertNotIn('privateIdentity',value['rateMeasurement']);self.assertNotIn('precisionDriftMs',value['rateMeasurement'])

    def test_exact_proof_count_ordinal_bounds_and_steady_failure_enum(self):
        good={'stage':'native-follow-precision-proof','status':'failed','checks':35,'failedTestOrdinals':[1,35],'errorCategory':'assertion'}
        self.assertEqual(public.report_line(json.dumps(good)),good)
        bad=dict(good,checks=36,failedTestOrdinals=[0,36])
        parsed=public.report_line(json.dumps(bad));self.assertNotIn('checks',parsed);self.assertEqual(parsed.get('failedTestOrdinals',[]),[])
        self.assertIn('steady_sample_precision',public.FOLLOW_CONDITIONS)

if __name__=='__main__':unittest.main()
