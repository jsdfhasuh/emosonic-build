"""Publishable tests: authored synthetic fixtures only, no private source reads."""
import importlib.util
import math
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_follow_readiness as patcher


def fixtures():
    path = patcher.ROOT / 'native_follow_readiness_payload' / 'readiness_contract.py'
    spec = importlib.util.spec_from_file_location('synthetic_readiness_fixture', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class PublicReadinessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures()
        def decoded(state): return state['nativePlayers'][0]
        self.ns = {'math': math, 'decoded': decoded,
            'native_rate_matches': lambda state, expected: abs(decoded(state)['playbackRate'] - expected) < 0.0001}
        exec(patcher.payload('follow_readiness_helpers.py'), self.ns)

    def test_exact_pending_seek_predicate_and_private_identity(self):
        values = self.fixture.pair(0, paused=True, seek=True)
        self.assertTrue(self.ns['native_follow_readiness_pending'](values[0], values[2], 1.5))
        identity = self.ns['follow_correction_identity'](values, 0, 'authority-context')
        self.assertIsInstance(identity, tuple)


    def test_native_preroll_is_pending_not_ready_or_generic_pause(self):
        values = self.fixture.waiting(0)
        self.assertTrue(self.ns['native_follow_readiness_pending'](values[0], values[2], 1.5))
        for mutate in (lambda n: n.update(playingIntent=False),
                lambda n: n.update(playbackRate=0), lambda n: n.update(playbackRate=1.56),
                lambda n: n.update(requestedRate=1), lambda n: n.update(avItemStatus=0),
                lambda n: n.update(playbackState=4, playbackRate=0, avTimeControlStatus=0)):
            values = self.fixture.waiting(0); mutate(values[2]['nativePlayers'][0])
            self.assertFalse(self.ns['native_follow_readiness_pending'](values[0], values[2], 1.5))

    def test_manual_pause_and_unknown_flags_do_not_admit(self):
        for value in (False, None, 1, 'true'):
            values = self.fixture.pair(0, paused=True, seek=True)
            values[2]['nativePlayers'][0]['playingIntent'] = value
            self.assertFalse(self.ns['native_follow_readiness_pending'](values[0], values[2], 1.5))

    def test_source_and_recovery_cursor_mismatch_fail(self):
        values = self.fixture.pair(0, paused=True, seek=True)
        values[2]['contexts']['authority-context']['controlVersion'] += 1
        with self.assertRaises(AssertionError): self.ns['follow_correction_identity'](values, 0, 'authority-context')
        values = self.fixture.pair(0, paused=True, seek=True)
        values[2]['preflightDiagnostics']['recoveryAppliedControlVersion'] += 1
        with self.assertRaises(AssertionError): self.ns['follow_correction_identity'](values, 0, 'authority-context')

    def test_packaged_payload_pins_and_exact_contract_count(self):
        for name in patcher.PAYLOAD_HASHES: patcher.payload(name)
        self.assertEqual(len(self.fixture.TEST_NAMES), patcher.CONTRACT_CHECKS)
        self.assertEqual(patcher.CONTRACT_CHECKS, 35)
        for mapping in (patcher.BASELINE, patcher.AFTER, patcher.PAYLOAD_HASHES):
            self.assertTrue(all(re.fullmatch(r'[0-9a-f]{64}', value) for value in mapping.values()))

    def test_unreviewed_harness_and_builder_are_refused(self):
        for transform in (patcher.patch_harness, patcher.patch_prepare):
            with self.assertRaises(ValueError): transform(b'synthetic unreviewed source')

    def test_subtest_failure_emits_only_known_parent_ordinal(self):
        class Synthetic(unittest.TestCase):
            def test_allowed(self):
                with self.subTest(private='synthetic-secret-do-not-export'):
                    self.fail('synthetic assertion values stay private')
        result = unittest.TestResult()
        Synthetic('test_allowed').run(result)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(patcher._failed_contract_ordinals(result, ('test_allowed',)), [1])
        self.assertEqual(patcher._failed_contract_ordinals(result, ('different_name',)), [])

if __name__ == '__main__': unittest.main()
