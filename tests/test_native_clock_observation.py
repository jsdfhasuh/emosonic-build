"""Synthetic finite-clock fixtures only; no private repository code or logs."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('clock_observer',ROOT/'scripts/native_seek_anchor_observation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def rates(at=1000, owner=1, effective=1.5):
    return dict(wallBeforeMs=1000000+at,wallAfterMs=1000000+at+0.1,monoBeforeMs=at,monoAfterMs=at+0.1,
        requestedRate=1.5,nativeRate=1.5,effectiveRate=effective,effectiveAvailable=True,identityMatches=owner>0,
        owner=owner,playingIntent=True,seeking=False,processingState=3,timeControl=2,effectiveReadCount=1)


def point(seq=1, at=1020, owner=1):
    return dict(sequence=seq,owner=owner,rateSequence=1,seekSequence=1,positionValid=owner>0,positionMs=20000+at,
        wallBeforeMs=1000000+at,wallAfterMs=1000000+at+0.2,monoBeforeMs=at,monoAfterMs=at+0.2,rates=rates(at+.2,owner))


def raw_clock(count=1):
    seq=m.retained_sequences(count)
    rows=[]
    for i in seq:
        at=1000+i*.1
        rows.append(dict(sequence=i,owner=1,requested=1.56,invocation=rates(at,effective=0),returned=rates(at+2,effective=0),
            returnedSeen=True,replyBegan=True,replyReturned=True,replyBeginMonoMs=at+3,replyBeginWallMs=1000000+at+3,
            replyEndMonoMs=at+4,replyEndWallMs=1000000+at+4,priorAnchor=point(at=at-10),
            firstAnchorSeen=True,firstAnchor=dict(point(at=at+50),rateSequence=i),firstNativeSeen=True,firstNative=dict(point(at=at+20),rateSequence=i)))
    return dict(rateCount=count,nativeCount=count,anchorCount=count,ownerCount=1,unmatchedReplies=0,
        rates=rows,native=[point(i,1000+i*.1) for i in seq],anchors=[point(i,1010+i*.1) for i in seq])


class NativeClockObservationTests(unittest.TestCase):
    def test_setter_return_reply_dispatch_and_real_progress_remain_distinct(self):
        value=m.clock_observation(raw_clock());row=value['rateRecords'][0]
        self.assertEqual(row['status'],'setter_returned')
        self.assertEqual(row['nativeReplyMeaning'],'dispatch_not_dart_ack')
        self.assertEqual(row['returned']['effectiveRate'],0)
        self.assertTrue(row['returned']['positiveNominalRateWithHeldClock'])
        self.assertLess(row['returnAfterInvocationMs'],row['replyDispatchAfterInvocationMs'])
        self.assertLess(row['replyDispatchAfterInvocationMs'],row['firstNativeObservation']['offsetMs'])
        self.assertEqual(value['dartAckReceipt'],'unavailable')
        self.assertEqual(value['intervalAttribution'],'unknown')
        self.assertEqual(value['recoveryArmAge'],'unavailable')

    def test_item_and_source_domains_and_uncertainty_are_explicit(self):
        value=m.clock_observation(raw_clock());row=value['rateRecords'][0]
        self.assertEqual(row['firstNativeObservation']['basis'],'item_current_time')
        self.assertEqual(row['firstAdmittedAnchor']['basis'],'source_relative_sampler')
        self.assertGreater(row['firstNativeObservation']['sampleUncertaintyMs'],1)
        self.assertNotIn('holdDurationMs',json.dumps(value))

    def test_first_and_tail_retention_is_fixed_and_discloses_loss(self):
        for n in (0,1,2,8,9,100,65535):
            value=m.clock_observation(raw_clock(n))
            self.assertEqual(len(value['nativeObservations']),min(8,n))
            self.assertEqual(value['nativeDropped'],max(0,n-8))
            self.assertEqual([v['ordinal'] for v in value['rateRecords']],m.retained_sequences(n))
            self.assertEqual(value['counterCapReached'],n==65535)

    def test_unknown_identity_omits_position_and_rates(self):
        value=point(owner=0);out=m.clock_point(value,1000,1001000,'item_current_time')
        self.assertFalse(out['samePlaybackIdentity']);self.assertNotIn('positionMs',out)
        self.assertEqual(out['rateCapture']['effectiveRateStatus'],'unavailable_identity_changed')
        self.assertNotIn('effectiveRate',out['rateCapture'])

    def test_preload_replacement_and_wrong_operation_cannot_gain_progress_link(self):
        for key,value in (('owner',2),('rateSequence',99)):
            raw=raw_clock();raw['rates'][0]['firstNative'][key]=value
            row=m.clock_observation(raw)['rateRecords'][0]
            self.assertNotIn('firstNativeObservation',row)
            self.assertEqual(row['firstNativeObservationStatus'],'invalid_record')

    def test_clock_step_backwards_and_nonfinite_records_do_not_look_valid(self):
        for key,value in (('wallAfterMs',1009999),('monoAfterMs',0),('monoBeforeMs',float('nan'))):
            raw=point();raw[key]=value
            self.assertIsNone(m.clock_point(raw,1000,1001000,'item_current_time'))
        raw=raw_clock();raw['rates'][0]['replyBeginWallMs']+=100
        self.assertNotIn('replyDispatchAfterInvocationMs',m.clock_observation(raw)['rateRecords'][0])

    def test_malformed_ordinals_counts_and_missing_retained_records_fail_closed(self):
        for edit in (lambda x:x.update(rateCount=True),lambda x:x['rates'].pop(),
                     lambda x:x['native'][0].update(sequence=True),lambda x:x.update(nativeCount=65536)):
            raw=raw_clock();edit(raw);self.assertEqual(m.clock_observation(raw),{'status':'malformed'})

    def test_unavailable_anchor_is_not_a_continuous_hold_claim(self):
        raw=raw_clock();row=raw['rates'][0];row.update(firstAnchorSeen=False,firstNativeSeen=False)
        out=m.clock_observation(raw)['rateRecords'][0]
        self.assertNotIn('firstAdmittedAnchor',out);self.assertNotIn('firstNativeObservation',out)
        self.assertNotIn('heldDurationMs',out)

    def test_existing_state_clock_evolution_is_paired_and_budget_is_only_readiness(self):
        prior=None
        for i in range(12):
            native={'sampledAtMs':1000000+i*200,'positionMs':30000+i*300,'playbackRate':1.5,'requestedRate':1.5,
                'sampleUncertaintyMs':2,'playingIntent':True,'seekInProgress':False,'playbackState':3}
            state={'serverClockOffsetMs':20-i,'latencySampleCount':i,'dartPositionSampledAtMs':native['sampledAtMs']+7,
                'dartPositionSampleUncertaintyMs':3}
            pair={'nativePlayers':[dict(native,sampledAtMs=native['sampledAtMs']+12)]}
            result=m.clock_history(prior,state,native,i*500,pair);prior={'clockHistory':result}
        self.assertEqual(result['count'],12);self.assertEqual(result['dropped'],4)
        self.assertEqual([v['ordinal'] for v in result['records']],[1,2,7,8,9,10,11,12])
        self.assertEqual(result['records'][-1]['remainingReadinessBudgetMs'],0)
        self.assertEqual(result['records'][-1]['dartMinusNativeSampleMs'],7)
        self.assertEqual(result['records'][-1]['pairedNativeSampleDeltaMs'],-12)
        self.assertEqual(result['recoveryArmAge'],'unavailable')

    def test_private_text_and_absolute_timestamps_never_leave_reducer(self):
        raw=raw_clock();raw['private']='SECRET';raw['rates'][0]['error']='TOKEN'
        value=json.dumps(m.clock_observation(raw))
        for secret in ('SECRET','TOKEN','wallBeforeMs','monoBeforeMs','replyBeginWallMs','1001100'):
            self.assertNotIn(secret,value)
        prior={'clockHistory':{'count':1,'records':[{'ordinal':1,'token':'SECRET','nativePositionMs':float('nan')}]}}
        value=m.clock_history(prior,{}, {},10,None)
        self.assertEqual(value['records'][0],{'ordinal':1})

    def test_actual_native_fixed_state_helpers_compile_and_bound_every_counter(self):
        code=m.payload('lab_timing_state.h')+r'''
#include <assert.h>
int main(void) {
  LabTimingState old={0}; LabTimingRates r={0}; unsigned seq=LabTimingBegin(&old,10,r);
  LabTimingCallback(&old,seq,1,1); LabTimingComplete(&old,seq,true,r);
  LabClockPoint p={.owner=1,.positionValid=true,.positionMs=200,.rates={.owner=1,.identityMatches=true}};
  assert(LabClockPointUsable(p)); p.positionValid=false; assert(!LabClockPointUsable(p));
  p.positionValid=true; p.positionMs=NAN; assert(!LabClockPointUsable(p));
  p.positionMs=200; p.rates.owner=2; assert(!LabClockPointUsable(p));
  LabClockState s={0};
  for (unsigned i=1;i<=65535;++i) s.rate[LabClockSlot(i)]=(LabClockRate){.sequence=i};
  for (unsigned i=0;i<8;++i) { unsigned n=LabClockRetainedSequence(65535,i); assert(n); assert(LabClockFindRate(&s,n)); }
  assert(!LabClockRetainedSequence(1,1)); assert(!LabClockFindRate(&s,0)); assert(!LabClockFindRate(&s,100));
  assert(LabClockRetainedSequence(9,0)==1 && LabClockRetainedSequence(9,1)==2 && LabClockRetainedSequence(9,2)==4);
  assert(sizeof(s)+sizeof(old)<65536);
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'probe.c';out=Path(tmp)/'probe';src.write_text(code)
            built=subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(src),'-o',str(out)],capture_output=True)
            self.assertEqual(built.returncode,0,'Synthetic fixed-state compilation failed')
            self.assertEqual(subprocess.run([str(out)],capture_output=True).returncode,0)

    def test_payload_retains_only_existing_position_reads_and_no_new_scheduler(self):
        body=m.payload('lab_timing_getters.inc')+m.payload('lab_timing_native.inc')
        for token in ('currentTime','indexedSource.position','broadcastPlaybackEvent','dispatch_after','NSTimer','setRate:'):
            self.assertNotIn(token,body)
        self.assertIn('seek->sequence == point.seekSequence',body)
        self.assertIn('point.rates.requestedRate == rate->requested',body)
        self.assertEqual(body.count('CMTimebaseGetEffectiveRate('),1)

    def test_full_saturated_record_survives_real_public_sanitizer(self):
        # Existing output is schema-bounded, not truncated by a byte/line cap.
        sys.path.insert(0,str(ROOT/'scripts'))
        import current_native_check as public
        from unittest.mock import patch
        def fill(schema):
            if schema is bool:return True
            if type(schema) is frozenset:return max(schema,key=len)
            if type(schema) is dict:return {k:fill(v) for k,v in schema.items()}
            if schema[0]=='list':return [fill(schema[1]) for _ in range(schema[2])]
            return schema[2] if schema[0]=='integer' else float(schema[2])
        value=fill(m.SCHEMA)
        actual=m.clock_observation(raw_clock(65535))
        value['clockObservation']=actual
        data={'stage':'native-follow-rate','rateMeasurement':{'nativeTiming':{'authority':value,'follower':copy.deepcopy(value)}}}
        with patch.dict(public.RATE_SCHEMA,{'nativeTiming':{'authority':m.SCHEMA,'follower':m.SCHEMA}}):
            exported=public.report_line(json.dumps(data))
        self.assertEqual(exported['rateMeasurement'],data['rateMeasurement'])
        self.assertLess(len(json.dumps(data)),256000)
        self.assertEqual(len(exported['rateMeasurement']['nativeTiming']['follower']['seekRecords']),16)
        self.assertEqual(len(exported['rateMeasurement']['nativeTiming']['follower']['clockObservation']['rateRecords']),8)

    def test_maximum_finite_output_is_bounded_and_closed(self):
        value=m.clock_observation(raw_clock(65535))
        self.assertLess(len(json.dumps(value)),64000)
        def check(obj,schema):
            self.assertEqual(set(obj)-set(schema),set())
            for k,v in obj.items():
                t=schema[k]
                if t is bool:self.assertIs(type(v),bool)
                elif type(t) is dict:check(v,t)
                elif type(t) is frozenset:self.assertIn(v,t)
                elif t[0]=='list':
                    self.assertLessEqual(len(v),t[2])
                    for row in v:check(row,t[1])
                else:
                    self.assertTrue(m.number(v,t[1],t[2]))
                    if t[0]=='integer':self.assertIs(type(v),int)
        check(value,m.SCHEMA['clockObservation'])


if __name__=='__main__':unittest.main()
