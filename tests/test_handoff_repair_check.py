import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import handoff_repair_check as r

class RedGateTests(unittest.TestCase):
    def report(self):
        return [
            {'type':'start'},
            {'type':'testStart','test':{'id':1,'name':'loading'}},
            {'type':'testDone','testID':1,'hidden':True,'skipped':False,'result':'success'},
            {'type':'testStart','test':{'id':2,'name':r.TEST_NAME}},
            {'type':'error','testID':2,'isFailure':True,'error':r.ASSERTION_MARKER},
            {'type':'testDone','testID':2,'hidden':False,'skipped':False,'result':'failure'},
            {'type':'done','success':False}]
    def parse(self, events):
        return r.intentional_red('\n'.join(json.dumps(e) for e in events))
    def test_reviewed_red(self):
        self.assertEqual(self.parse(self.report()),{'expectedFailures':1,'unexpectedFailures':0})
    def test_wrong_failure_or_compile_error(self):
        for index,field,value in [(4,'error','unrelated error'),(4,'isFailure',False),(4,'testID',1),(5,'hidden',True),(5,'skipped',True),(6,'success',True)]:
            e=self.report();e[index][field]=value
            with self.subTest(field=field),self.assertRaises(r.request.p.GateError):self.parse(e)
    def test_wrong_test_and_duplicate_errors(self):
        e=self.report();e[3]['test']['name']='different'
        with self.assertRaises(r.request.p.GateError):self.parse(e)
        e=self.report();e.insert(5,e[4].copy())
        with self.assertRaises(r.request.p.GateError):self.parse(e)
    def test_incomplete_and_trailing_event(self):
        for e in (self.report()[:-1],self.report()+[{'type':'print'}]):
            with self.assertRaises(r.request.p.GateError):self.parse(e)
    def test_packages_denied(self):
        with patch.object(sys,'argv',['repair','source','build']):self.assertEqual(r.main(),1)
