import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import negative_nominal_observation as c
import authority_rate_feedback_green as green

class NegativeNominalObservationTests(unittest.TestCase):
    def value(self):
        return dict(schemaVersion=1,exactAckFloorObserved=False,ackBeforeUs=100,ackAfterUs=200,rateWriteCount=2,
            rateWrites=[dict(atMs=200,rate=1.44),dict(atMs=3400,rate=1.5)],
            snapshots=[dict(phase=p,nowMs=3400+i*100,nativeResidualMs=49,runtimeDriftMs=49,currentRate=1.5,nativeRate=1.5,requestedRate=1.5,settledCount=0 if i<2 else 1,activeTimerCount=2,rateWriteCount=2,anchorSequence=i+1,anchorPositionUs=1000000+i*150000,anchorSampleOffsetUs=201+i*100,ageBeforeUs=10,ageAfterUs=20) for i,p in enumerate(c.PHASES)])
    def suites(self):
        return [dict(path=c.TEST_PATH,sha256=c.FIXTURE_SHA256,names=['private one','private two','private target'])]
    def events(self,value=None):
        return [dict(type='suite',suite=dict(id=2,path=c.TEST_PATH)),dict(type='testStart',test=dict(id=5,suiteID=2,name='private target')),dict(type='print',testID=5,message=c.PREFIX+json.dumps(value or self.value())),dict(type='testDone',testID=5,result='failure',hidden=False,skipped=False),dict(type='done',success=False)]
    def observe(self,events=None,suites=None):
        return c.observe_negative_nominal('\n'.join(json.dumps(e) for e in (events or self.events())),Path('/private'),suites or self.suites(),'full')
    def test_finite_record_retained_even_when_actual_test_failed(self):
        r=self.observe();self.assertEqual(r['status'],'observed');self.assertEqual(r['diagnostic'],self.value());self.assertNotIn('private',json.dumps(r));self.assertFalse(r['diagnostic']['exactAckFloorObserved'])
    def test_null_anchor_is_honest_not_an_invented_receipt(self):
        v=self.value()
        for k in ('anchorSequence','anchorPositionUs','anchorSampleOffsetUs','ageBeforeUs','ageAfterUs'):v['snapshots'][0][k]=None
        self.assertEqual(c.project(v),v)
    def test_wrong_manifest_and_case_cannot_export(self):
        s=self.suites();s[0]['sha256']='a'*64;self.assertEqual(self.observe(suites=s)['status'],'fixture-mismatch')
        e=self.events();e[1]['test']['name']='private one';self.assertEqual(self.observe(e)['status'],'missing-target')
        e=self.events();e[2]['testID']=99;self.assertEqual(self.observe(e)['status'],'wrong-test-id')
    def test_ambiguous_suite_target_and_boolean_ids_fail_closed(self):
        for field in ('suite','target','bool'):
            e=self.events()
            if field=='suite':e.insert(1,copy.deepcopy(e[0]))
            elif field=='target':e.insert(2,copy.deepcopy(e[1]))
            else:e[2]['testID']=True
            self.assertNotEqual(self.observe(e)['status'],'observed')
    def test_extra_private_keys_nonfinite_bools_and_bounds_rejected(self):
        for mutate in (lambda v:v.update(secret='private'),lambda v:v.update(schemaVersion=True),lambda v:v.update(exactAckFloorObserved=True),lambda v:v.update(ackAfterUs=1),lambda v:v['snapshots'][0].update(nativeResidualMs=float('nan')),lambda v:v['snapshots'][0].update(currentRate=True),lambda v:v['snapshots'][0].update(anchorSequence=None),lambda v:v['snapshots'][0].update(ageAfterUs=0),lambda v:v['rateWrites'][0].update(rate=3),lambda v:v['snapshots'].reverse(),lambda v:v.update(rateWriteCount=4)):
            v=self.value();mutate(v);self.assertEqual(self.observe(self.events(v))['status'],'malformed-samples')
    def test_duplicate_json_keys_and_repeated_reports_rejected(self):
        e=self.events();e[2]['message']=c.PREFIX+'{"schemaVersion":1,"schemaVersion":1}';self.assertEqual(self.observe(e)['status'],'malformed-samples')
        e=self.events();e.insert(3,copy.deepcopy(e[2]));self.assertEqual(self.observe(e)['status'],'malformed-samples')
    def test_output_and_event_bounds(self):
        with patch.object(c,'MAX_BYTES',1):self.assertEqual(self.observe()['status'],'output-limit')
        with patch.object(c,'MAX_EVENTS',1):self.assertEqual(self.observe()['status'],'event-limit')
    def test_both_calls_are_before_unchanged_verdict(self):
        text=(Path(__file__).resolve().parents[1]/'scripts/follow_recovery_check.py').read_text()
        self.assertIn("observe_negative_nominal(result.stdout,source,[suite],'focused')",text)
        self.assertIn("observe_negative_nominal(raw,source,suites,'full')",text)
        self.assertLess(text.index('diagnostic=observe_negative_nominal'),text.index('report=verify_green'))
    def test_manifest_override_scoped_and_restored(self):
        old=green.directional.INVENTORY_SHA256
        def inside():
            self.assertEqual(green.directional.INVENTORY_SHA256,green.DIRECTIONAL_INVENTORY_SHA256);raise RuntimeError('synthetic')
        with patch.object(green.previous,'main',side_effect=inside),self.assertRaises(RuntimeError):green.main()
        self.assertEqual(green.directional.INVENTORY_SHA256,old)

if __name__=='__main__':unittest.main()
