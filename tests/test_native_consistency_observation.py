import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_consistency_observation as o
import current_native_check as n


def fixture():
    assertions = ['        ' + item[1] for item in o.CHECKS]
    assertions.append('        ' + o.STREAM_ASSERT)
    return ('class Lab:\n    def run(self):\n' + '\n'.join(assertions) + '\n' + o.FAILURE_ENTRY +
            "        print(json.dumps({'stage': self.stage,\n" + o.FAILURE_FIELDS + "\n        }))\n")


class ObservationTests(unittest.TestCase):
    def test_assertion_asts_identical(self):
        original = fixture()
        patched = o.patch_text(original)
        assertions = lambda text: [ast.dump(node) for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Assert)]
        self.assertEqual(assertions(original), assertions(patched))
        self.assertEqual(len(assertions(patched)), 8)
        self.assertTrue(o.STAGES <= n.PUBLIC_STAGES)
        for stage in o.STAGES:
            self.assertEqual(patched.count(repr(stage)), 1)

    def test_refuses_repeat_missing_or_duplicated_assertion(self):
        for text in (o.patch_text(fixture()), fixture().replace(o.CHECKS[0][1], 'pass'), fixture() + '\n' + fixture()):
            with self.assertRaises(ValueError):
                o.patch_text(text)

    def test_constrained_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'tool/native_playback_mac/run_lab.py'
            target.parent.mkdir(parents=True)
            target.write_text(fixture())
            o.apply_observations(target)
            self.assertIn('handoff-check-continuity', target.read_text())
            wrong = target.parent / 'other.py'
            wrong.write_text(fixture())
            with self.assertRaises(ValueError):
                o.apply_observations(wrong)
            target.unlink()
            target.symlink_to(wrong)
            with self.assertRaises(ValueError):
                o.apply_observations(target)

    def test_traceback_hook_returns_only_known_module_and_line(self):
        namespace = {'Path': Path}
        snippet = 'def collect(error):\n' + ''.join(line[4:] + '\n' for line in o.FAILURE_LOCATION.splitlines()) + '    return _failure_location\n'
        exec(snippet, namespace)
        for filename, expected in (('/private/token/run_lab.py', {'module': 'run_lab.py', 'line': 1}),
                                   ('/private/token/extended_handoff.py', {'module': 'extended_handoff.py', 'line': 1}),
                                   ('/private/token/secret.py', {})):
            try:
                exec(compile('raise AssertionError()', filename, 'exec'))
            except AssertionError as error:
                self.assertEqual(namespace['collect'](error), expected)

    def test_failure_location_never_exposes_arbitrary_paths_or_text(self):
        for module in ('run_lab.py', 'extended_handoff.py'):
            self.assertEqual(n.report_line(json.dumps({'failureLocation': {'module': module, 'line': 123}})),
                             {'failureLocation': {'module': module, 'line': 123}})
        for line in (True, 0, 100001, 'secret', float('nan')):
            self.assertFalse(n.report_line(json.dumps({'failureLocation': {
                'module': '/private/run_lab.py', 'line': line, 'message': 'secret'}})))

    def test_diagnostics_are_finite_typed_and_private(self):
        value = {'stage': 'handoff-check-media-provenance', 'consistencyObservation': {
            'streamCount': 4, 'targetStreamCount': 0, 'latestRequestDeltaMs': -42.5,
            'trackMatches': True, 'canonicalPlaying': 'private', 'targetTrackStreamCount': True,
            'nativeRate': float('inf'), 'continuityErrorMs': float('nan'),
            'atMs': 1777777777777, 'url': 'secret', 'sourcePositionMs': 'secret',
            'numericTimestampCount': -1, 'postStartStreamCount': 1000001}}
        self.assertEqual(n.report_line(json.dumps(value)), {'stage': 'handoff-check-media-provenance',
            'consistencyObservation': {'streamCount': 4, 'targetStreamCount': 0,
                'latestRequestDeltaMs': -42.5, 'trackMatches': True}})

if __name__ == '__main__':
    unittest.main()
