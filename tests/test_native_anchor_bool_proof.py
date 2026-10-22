import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_anchor_bool_proof as proof


def output():
    return {'baseline': [1] + [0] * 10, 'patched': [True] + [False] * 10}


class NativeAnchorBoolProof(unittest.TestCase):
    def test_extracted_expression_reverses_exact_original_payload(self):
        original, corrected = proof.expressions()
        self.assertEqual(corrected, '@((BOOL)(' + original[2:-1] + '))')
        self.assertEqual(original.count('&&'), 6)
        text = proof.source_text()
        self.assertIn('return ' + original + ';', text)
        self.assertIn('return ' + corrected + ';', text)
        self.assertIn('#import <Foundation/Foundation.h>', text)
        self.assertNotIn('AVFoundation', text)

    def test_exact_red_green_and_every_mismatch_reaches_real_reducer(self):
        result = proof.validate_output(output())
        self.assertEqual(result['caseCount'], 11)
        self.assertEqual(result['reducerResidualIncluded'], 1)
        self.assertEqual(result['reducerResidualOmitted'], 21)

    def test_wrong_numeric_boolean_and_mismatch_types_fail_closed(self):
        for phase in ('baseline', 'patched'):
            for index in range(11):
                raw = output()
                raw[phase][index] = bool(raw[phase][index]) if phase == 'baseline' else int(raw[phase][index])
                with self.assertRaises(proof.ProofFailure) as caught: proof.validate_output(raw)
                self.assertEqual(caught.exception.record['phase'], phase)
                self.assertEqual(caught.exception.record['caseOrdinal'], index + 1)
                self.assertEqual(caught.exception.record['reason'], 'wrong_json_type')

    def test_wrong_truth_value_is_not_serialization_success(self):
        for phase in ('baseline', 'patched'):
            for index in range(11):
                raw = output()
                raw[phase][index] = 1 - raw[phase][index] if phase == 'baseline' else not raw[phase][index]
                with self.assertRaises(proof.ProofFailure): proof.validate_output(raw)

    def test_non_macos_is_failure_not_skipped_or_false_green(self):
        with patch.object(proof.sys, 'platform', 'linux'):
            with self.assertRaises(proof.ProofFailure) as caught: proof.prove()
        self.assertEqual(caught.exception.record['reason'], 'requires_macos')

    def test_child_environment_strips_command_files(self):
        names = ('GITHUB_ENV', 'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY')
        with patch.dict(proof.os.environ, dict.fromkeys(names, 'PRIVATE')):
            env = proof.child_environment(Path('/owned'))
        self.assertTrue(all(name not in env for name in names))
        self.assertEqual(env['TMPDIR'], '/owned')

    def test_failure_output_contains_only_finite_codes(self):
        raw = io.StringIO()
        with patch.object(proof, 'prove', side_effect=RuntimeError('PRIVATE TOKEN /private/source')):
            with contextlib.redirect_stdout(raw): code = proof.main()
        self.assertEqual(code, 1)
        record = json.loads(raw.getvalue())
        self.assertEqual(record, proof.ProofFailure('extract', 'source_contract').record)

    def test_malformed_or_unknown_output_rejected(self):
        for raw in (None, {}, dict(output(), secret='PRIVATE'), {'baseline': [], 'patched': []}):
            with self.assertRaises(proof.ProofFailure): proof.validate_output(raw)

    def test_bounded_compile_failure_is_never_causal_red(self):
        with patch.object(proof.sys, 'platform', 'darwin'):
            with patch.object(proof.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'', b'PRIVATE')):
                with self.assertRaises(proof.ProofFailure) as caught: proof.prove()
        self.assertEqual(caught.exception.record['phase'], 'compile')
        self.assertEqual(caught.exception.record['reason'], 'compile_failed')


if __name__ == '__main__': unittest.main()
