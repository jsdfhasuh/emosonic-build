import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_seek_latency_proof as c

class FollowSeekProofTests(unittest.TestCase):
    def report(self):
        events = [
            {'type':'start'},
            {'type':'testStart','test':{'id':1,'name':'loading'}},
            {'type':'testDone','testID':1,'hidden':True,'skipped':False,'result':'success'},
            {'type':'testStart','test':{'id':2,'name':c.TEST_NAME}},
            {'type':'error','testID':2,'isFailure':True,'error':c.ASSERTION_MARKER},
            {'type':'testDone','testID':2,'hidden':False,'skipped':False,'result':'failure'},
            {'type':'done','success':False}]
        for tid in range(3,15):
            events[-1:-1]=[{'type':'testStart','test':{'id':tid,'name':'control'+str(tid)}},{'type':'testDone','testID':tid,'hidden':False,'skipped':False,'result':'success'}]
        samples = [dict(cycle=i,rate=1.5,holdMs=200,decision='[[EMO_FOLLOW_SYNC]] action=softCorrectDrift private ignored suffix',
                        requestedPositionMs=10000+i*1500,serverNowMs=100200+i*1000,
                        residualMs=-290,nativeResidualMs=-300,realProjectionUpperMs=10,
                        nativeAnchorAdopted=True) for i in range(5)]
        events.insert(-1, {'type':'print','testID':2,
                          'message':'FOLLOW_SEEK_LATENCY_SAMPLES '+json.dumps(samples)})
        return events

    def parse(self, events):
        with patch.multiple(c.regression, TEST_NAME=c.TEST_NAME, ASSERTION_MARKER=c.ASSERTION_MARKER):
            return c.exact_red('\n'.join(json.dumps(e) for e in events))

    def test_exact_causal_failure(self):
        self.assertEqual(self.parse(self.report())['passedControls'], 12)
        self.assertEqual(len(self.parse(self.report())['syntheticSamples']), 5)
        self.assertNotIn('private', json.dumps(self.parse(self.report())))

    def test_marker_substrings_cannot_prove_failure(self):
        for message in ('prefix '+c.ASSERTION_MARKER, c.ASSERTION_MARKER+' suffix', 'wrong', ''):
            events=self.report();events[4]['error']=message
            with self.subTest(message=message), self.assertRaises(c.request.p.GateError): self.parse(events)

    def test_wrong_test_compile_skip_and_duplicate_rejected(self):
        for index,key,value in [(4,'isFailure',False),(4,'testID',1),(5,'skipped',True),(-1,'success',True)]:
            events=self.report();events[index][key]=value
            with self.subTest(key=key), self.assertRaises(c.request.p.GateError):self.parse(events)
        events=self.report();events.insert(5,events[4].copy())
        with self.assertRaises(c.request.p.GateError):self.parse(events)

    def test_missing_or_failed_control_rejected(self):
        events=self.report();events[7]['result']='failure'
        with self.assertRaises(c.request.p.GateError):self.parse(events)
        events=self.report();del events[6:8]
        with self.assertRaises(c.request.p.GateError):self.parse(events)

    def test_private_or_unbounded_diagnostic_rejected(self):
        for key,value in [('decision','private text'),('rate',float('nan')),('holdMs',True),('extra','private')]:
            events=self.report(); report=events[-2]; samples=json.loads(report['message'].split(' ',1)[1]); samples[0][key]=value
            report['message']='FOLLOW_SEEK_LATENCY_SAMPLES '+json.dumps(samples)
            with self.subTest(key=key),self.assertRaises(c.request.p.GateError):self.parse(events)

    def test_plugin_details_are_known_enums_only(self):
        raw=json.dumps({'type':'error','testID':3,'error':'MissingPluginException(No implementation found for method getApplicationSupportDirectory on channel plugins.flutter.io/path_provider)','stackTrace':'private/emo_follow_sync_controller_test.dart 123:4 private'})
        report=c.finite_report(raw,'',1)['errors'][0]
        self.assertEqual(report['knownPluginChannels'],['plugins.flutter.io/path_provider'])
        self.assertEqual(report['knownPluginMethods'],['getApplicationSupportDirectory'])
        self.assertEqual(report['fixtureLines'],[123])
        self.assertNotIn('private',json.dumps(report))
        raw=json.dumps({'type':'error','error':'MissingPluginException(No implementation found for method privateMethod on channel privateChannel)'})
        report=c.finite_report(raw,'',1)['errors'][0]
        self.assertEqual(report['knownPluginChannels'],[]);self.assertEqual(report['knownPluginMethods'],[])

    def test_failure_stages_are_precise(self):
        cases=[]
        e=self.report();e[4]['error']='other';cases.append((e,'exact-error'))
        e=self.report();e[7]['result']='failure';cases.append((e,'all-control-results'))
        e=self.report();e[-2]['message']='missing';cases.append((e,'finite-synthetic-samples'))
        e=self.report();e[3]['test']['name']='wrong';cases.append((e,'target-and-terminal'))
        for events,stage in cases:
            with self.subTest(stage=stage), self.assertRaises(c.request.p.GateError):self.parse(events)
            self.assertEqual(c.PROOF_STAGE,stage)

    def test_finite_failure_report_never_exports_private_messages(self):
        events=self.report(); events[-3]['error']='private secret TimeoutException'; events[-3]['stackTrace']='private-path/emo_follow_sync_controller_test.dart:123:4 private'
        raw='private raw stderr line\n'+'\n'.join(json.dumps(e) for e in events)
        report=c.finite_report(raw,'private compiler text test/services/emo_follow_sync_controller_test.dart:90:12: Error: private',1)
        self.assertEqual(report['nonJsonLines'],1)
        self.assertEqual(report['compileLocations'],[(90,12)])
        self.assertNotIn('private',json.dumps(report)); self.assertNotIn('secret',json.dumps(report))

    def test_no_package_native_or_full_validation_stage(self):
        for category,stage in [('source','build'),('source','publish'),('source','validate_source'),('native','build')]:
            with patch.object(sys,'argv',['wrapper',category,stage]), patch.object(c.request,'main') as run:
                self.assertEqual(c.main(),1);run.assert_not_called()

    def test_bounded_workflow(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH):self.assertIn(value,text)
        for value in ('macos-26','upload-artifact','validate-source:','RELEASE_WRITE_TOKEN','DEFAULT_SERVER_URL'):
            self.assertNotIn(value,text)
        self.assertIn('if: always()',text)

if __name__=='__main__':unittest.main()
