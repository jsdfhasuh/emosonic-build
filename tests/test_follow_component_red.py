"""Synthetic fixtures only: fixed component inventories cannot weaken old red proof."""
import json
import unittest

from test_follow_ingress_proof import c, fixture, raw, NAMES, BASE, SECRET


class ComponentRedTests(unittest.TestCase):
    def component(self):
        events = fixture()
        names = NAMES + ['synthetic third control', 'synthetic fourth control']
        for tid, name in enumerate(names[3:], 10):
            events[-1:-1] = [dict(type='testStart', test=dict(id=tid, name=name)),
                             dict(type='testDone', testID=tid, result='success',
                                  hidden=False, skipped=False)]
        next(e for e in events if e['type'] == 'error')['error'] = 'SYNTHETIC_COMPONENT_CAUSAL_MARKER'
        return events, names

    def verify(self, events, names, **kwargs):
        return c.exact_red(raw(events), 1, names=names, basename=BASE,
                           causal_ordinal=1, **kwargs)

    def test_explicit_count_marker_and_all_controls(self):
        events, names = self.component()
        report = self.verify(events, names, expected_count=5,
                             assertion_marker='SYNTHETIC_COMPONENT_CAUSAL_MARKER')
        self.assertEqual(report['passedControls'], 4)
        self.assertEqual(report['visibleTests'], 5)
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertTrue(all(name not in json.dumps(report) for name in names))

    def test_default_ingress_proof_does_not_accept_new_count_or_marker(self):
        events, names = self.component()
        with self.assertRaises(c.GreenVerificationError):
            self.verify(events, names)
        self.assertEqual(self.verify(fixture(), NAMES)['passedControls'], 2)

    def test_invalid_or_unbounded_configuration_rejected(self):
        for count in (True, 0, 1, 129, '3', None):
            with self.subTest(count=count), self.assertRaises(c.GreenVerificationError):
                self.verify(fixture(), NAMES, expected_count=count)
        for marker in ('', 'private/path', 'a' * 200, None, True):
            with self.subTest(marker=marker), self.assertRaises(c.GreenVerificationError):
                self.verify(fixture(), NAMES, assertion_marker=marker)

    def test_late_control_error_and_hidden_skip_are_never_normalized(self):
        for kind in ('extra-error', 'failed-control', 'skipped-hidden'):
            events, names = self.component()
            if kind == 'extra-error':
                events.insert(-1, dict(type='error', testID=11, isFailure=False, error=SECRET))
            else:
                done = next(e for e in events if e.get('type') == 'testDone'
                            and e.get('testID') == (11 if kind == 'failed-control' else 3))
                done['result' if kind == 'failed-control' else 'skipped'] = 'failure' if kind == 'failed-control' else True
            with self.subTest(kind=kind), self.assertRaises(c.GreenVerificationError):
                self.verify(events, names, expected_count=5,
                            assertion_marker='SYNTHETIC_COMPONENT_CAUSAL_MARKER')


if __name__ == '__main__':
    unittest.main()
