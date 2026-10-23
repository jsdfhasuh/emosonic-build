"""Synthetic fixed-literal counters; no private source, IDs, or raw log export."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'scripts/native_follow_lifecycle_payload')]
import follow_lifecycle_observation as o
import native_follow_lifecycle as lifecycle
import native_follow_lifecycle_schema as schema
import current_native_check as public


def line(body, logger='EmoRealtimeClient'):
    return '[2026-10-23T12:00:00.000] [DEBUG] ['+logger+'] '+body+'\n'


def observe(text, offset=0, data=None):
    raw=text.encode() if data is None else data
    lines=raw.decode('utf-8',errors='replace').splitlines()
    if offset and lines:lines=lines[1:]
    result={'existing':17}
    o.add_bootstrap_observation(result,lines,offset,offset+len(raw),raw)
    assert result['existing']==17
    return result['bootstrap']


class BootstrapObservationTests(unittest.TestCase):
    def test_all_exact_source_markers_and_stage_statuses(self):
        data=''.join(line('[[EMO_STARTUP]] '+v,'Main') for v in (
            'connect scope=PRIVATE epoch=PRIVATE','connect requested','connect failed type=PRIVATE'))
        data+=''.join(line('[[EMO_CONNECT_BOOTSTRAP]] '+v) for v in (
            'join active request','ignore failure reason=stale_attempt error=PRIVATE',
            'connection aborted error=PRIVATE','connection abort stack=PRIVATE'))
        for stage in o.BOOTSTRAP_STAGES:
            for status in o.BOOTSTRAP_STATUSES:
                tail=' timeoutMs=10000' if status in ('started','timed_out') else ' error=PRIVATE' if status=='failed' else ''
                data+=line('[[EMO_CONNECT_BOOTSTRAP]] stage='+stage+' status='+status+tail)
        value=observe(data)
        self.assertEqual(value['startup'],dict(connect=1,requested=1,failed=1))
        self.assertEqual(value['other'],dict(joined=1,stale=1,aborted=1,unknown=0))
        self.assertTrue(all(count==1 for counts in value['stages'].values() for count in counts.values()))
        self.assertEqual(value['byteCoverage'],'whole_current_file')
        self.assertEqual(value['launchCoverage'],'unknown')
        self.assertNotIn('PRIVATE',json.dumps(value))

    def test_wrong_logger_embedded_marker_and_error_suffix_are_not_events(self):
        marker='[[EMO_CONNECT_BOOTSTRAP]] stage=client_id status=completed'
        value=observe(line(marker,'Main')+line('error='+marker)+line(
            '[[EMO_CONNECT_BOOTSTRAP]] stage=device_alias status=failed error='+marker)
            +line('[[EMO_CONNECT_BOOTSTRAP]] connection abort stack='+marker))
        self.assertEqual(value['stages']['client_id']['completed'],0)
        self.assertEqual(value['stages']['device_alias']['failed'],1)
        self.assertEqual(value['other']['unknown'],0)

    def test_unknown_stage_status_and_malformed_suffix_only_increment_unknown(self):
        forms=('stage=PRIVATE status=started timeoutMs=1','stage=client_id status=PRIVATE',
            'stage=client_id status=completed error=PRIVATE','stage=client_id status=started',
            'stage=client_id status=timed_out timeoutMs=NaN','stage=client_id status=failed',
            'PRIVATE')
        value=observe(''.join(line('[[EMO_CONNECT_BOOTSTRAP]] '+v) for v in forms))
        self.assertEqual(value['other']['unknown'],len(forms))
        self.assertFalse(any(count for counts in value['stages'].values() for count in counts.values()))
        self.assertNotIn('PRIVATE',json.dumps(value))

    def test_tail_partial_encoding_and_long_lines_have_explicit_coverage(self):
        selected=line('[[EMO_STARTUP]] connect requested','Main')
        self.assertEqual(observe('partial\n'+selected,offset=400)['byteCoverage'],'tail_only')
        partial=observe(selected.rstrip('\n'))
        self.assertEqual(partial['byteCoverage'],'partial');self.assertEqual(partial['startup']['requested'],0)
        invalid=observe('',data=b'\xff\n'+selected.encode())
        self.assertEqual(invalid['byteCoverage'],'partial');self.assertGreater(invalid['lineIssues'],0)
        self.assertEqual(observe('X'*8193+'\n')['byteCoverage'],'partial')
        self.assertEqual(observe('')['launchCoverage'],'unknown')

    def test_counts_saturate_without_unbounded_retention(self):
        with patch.object(o,'MAX_COUNT',2):
            value=observe(line('[[EMO_STARTUP]] connect requested','Main')*4)
        self.assertEqual(value['startup']['requested'],2);self.assertTrue(value['countsSaturated'])
        self.assertNotIn('records',value)

    def test_no_io_clock_or_state_read_and_input_is_not_mutated(self):
        data=line('[[EMO_STARTUP]] connect requested','Main').encode();lines=data.decode().splitlines();before=copy.deepcopy(lines)
        result={'existing':17}
        with patch('builtins.open',side_effect=AssertionError('No I/O')),patch.object(o.time,'monotonic',side_effect=AssertionError('No clock')):
            o.add_bootstrap_observation(result,lines,0,len(data),data)
        self.assertEqual(lines,before);self.assertEqual(result['existing'],17)
        self.assertEqual(result['bootstrap']['startup']['requested'],1)

    def test_invalid_input_is_finite_and_does_not_change_existing_counts(self):
        for offset,size,data in ((-1,1,b''),(0,8388609,b''),(0,262145,b'x'*262145),(True,1,b'')):
            result={'existing':17};o.add_bootstrap_observation(result,[],offset,size,data)
            self.assertEqual(result,{'existing':17,'bootstrap':{'byteCoverage':'unavailable','launchCoverage':'unknown'}})

    def test_sanitizer_retains_all_finite_fields_and_drops_private_additions(self):
        value={'stage':'real-apps-register','status':'failed','nativeLogClassifications':[
            {'clientOrdinal':2,'readStatus':'read','bootstrap':observe(line('[[EMO_STARTUP]] connect failed type=PRIVATE','Main'))}]}
        self.assertEqual(public.report_line(json.dumps(value)),value)
        dirty=copy.deepcopy(value);dirty['nativeLogClassifications'][0]['bootstrap']['raw']='PRIVATE'*100000
        self.assertEqual(public.report_line(json.dumps(dirty)),value)
        self.assertEqual(set(schema.BOOTSTRAP_SCHEMA['stages']),set(o.BOOTSTRAP_STAGES))

    def test_exact_observation_hook_and_payload_are_pinned(self):
        self.assertEqual(hashlib.sha256(Path(o.__file__).read_bytes()).hexdigest(),lifecycle.PAYLOAD_HASHES['follow_lifecycle_observation.py'])
        self.assertIn('add_bootstrap_observation(result, lines, offset, size, data)',lifecycle.OBSERVER_CALLS)
        import test_native_follow_lifecycle_patch as fixture
        with patch.object(lifecycle,'BEFORE_SHA256',lifecycle.digest(fixture.SYNTHETIC)):
            result=lifecycle._transform_harness(fixture.SYNTHETIC)
        self.assertEqual(result.count(b'add_bootstrap_observation(result, lines, offset, size, data)'),1)
        lifecycle.prove_controls_unchanged(fixture.SYNTHETIC,result)
        with self.assertRaises(ValueError):
            lifecycle.prove_controls_unchanged(fixture.SYNTHETIC,result.replace(b'lines, offset, size, data)',b'lines, 0, size, data)'))


if __name__=='__main__':unittest.main()
