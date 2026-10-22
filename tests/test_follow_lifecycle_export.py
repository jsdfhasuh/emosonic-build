"""Complete finite export coverage without private identifiers or arbitrary logs."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_native_check as native
from native_follow_lifecycle_schema import FOLLOW_LIFECYCLE_SCHEMA, STAGES


def populated(schema):
    if schema is bool:
        return True
    if isinstance(schema, frozenset):
        return sorted(schema)[0]
    if isinstance(schema, dict):
        return {key: populated(value) for key, value in schema.items()}
    if schema[0] == 'list':
        return [populated(schema[1])]
    return min(schema[2], max(schema[1], 3))


def contaminate(value):
    if isinstance(value, dict):
        value['privateNonce'] = 'private fixture token never export'
        value['rawStack'] = 'private source path never export'
        value['clientId'] = 'private client identifier'
        for item in list(value.values()):
            contaminate(item)
    elif isinstance(value, list):
        for item in value:
            contaminate(item)


class LifecycleExportTests(unittest.TestCase):
    def test_every_finite_field_survives_complete_export(self):
        expected = {'stage': next(iter(STAGES)), 'status': 'not-verified',
                    'followLifecycle': populated(FOLLOW_LIFECYCLE_SCHEMA)}
        self.assertEqual(native.report_line(json.dumps(expected)), expected)
        contaminated = json.loads(json.dumps(expected))
        contaminate(contaminated)
        self.assertEqual(native.report_line(json.dumps(contaminated)), expected)

    def test_actual_observer_synthetic_full_output_survives_export(self):
        fixture = Path(__file__).resolve().parent / 'fixtures/follow_lifecycle_full_observation.json'
        expected = json.loads(fixture.read_text())
        self.assertEqual(native.report_line(json.dumps(expected)), expected)
        contaminated = json.loads(json.dumps(expected))
        contaminate(contaminated)
        self.assertEqual(native.report_line(json.dumps(contaminated)), expected)

    def test_unknown_values_and_numeric_types_fail_closed(self):
        value = {'stage': 'native-follow-command-observation', 'followLifecycle': {
            'status': 'private error text', 'commandDurationMs': float('inf'),
            'sampleCount': True, 'commandReturned': 'true',
            'ownedLog': {'coverage': 'private path', 'clearReasons': {
                'local_mirror_failure': 'private exception', 'unknown_private_reason': 1}},
            'serverFollow': [{'milestone': 'failure', 'observation': {
                'admissionObserved': 'private nonce', 'leasePresent': True,
                'rawAck': {'secret': 'private credential'}}}]}}
        self.assertEqual(native.report_line(json.dumps(value)), {
            'stage': 'native-follow-command-observation', 'followLifecycle': {
                'serverFollow': [{'milestone': 'failure', 'observation': {'leasePresent': True}}]}})

    def test_list_count_bounds_preserve_limit(self):
        value = populated(FOLLOW_LIFECYCLE_SCHEMA)
        value['transitions'] *= 20
        value['serverFollow'] *= 20
        result = native.report_line(json.dumps({'followLifecycle': value}))['followLifecycle']
        self.assertEqual(len(result['transitions']), 12)
        self.assertEqual(len(result['serverFollow']), 6)


if __name__ == '__main__':
    unittest.main()
