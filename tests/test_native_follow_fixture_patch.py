"""Self-contained public tests; no private repository snapshots are imported."""
import ast
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import types
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_follow_readiness as patcher
from native_follow_readiness_payload import alignment_fixture_compatibility as compat


SYNTHETIC = '''class AlignmentBase:
    def __init__(self):
        self.last = []

run_lab = types.SimpleNamespace(Matrix=AlignmentBase)

def state(t, position, expected):
    return {'sentinelTime': t, 'sentinelPosition': position, 'sentinelRate': expected, 'nativePlayers': [{}]}

class AlignmentMatrix(run_lab.Matrix):
    def __init__(self, clock, offset, expected=1.5, authority_index=0, mutate=None):
        super().__init__()
        self.clock, self.offset, self.expected = clock, offset, expected
        self.authority_index, self.mutate = authority_index, mutate
        self.observed, self.outcomes = [], []

    def states(self):
        a = {'sentinelPosition': 100, 'nativePlayers': [{}]}
        f = {'sentinelPosition': 200, 'nativePlayers': [{}]}
        if self.mutate is not None:
            self.mutate(a, f)
        return a, f

class OriginalContract:
    def test_original_assertion(self):
        assert 2 + 2 == 4

    def test_alignment_and_advancement_share_original_deadline(self):
        matrix = AlignmentMatrix(Clock(), lambda t: -205 if t < 4.7 else 14)
        assert matrix.clock.now < 5.25
'''.encode()


@contextmanager
def synthetic_pins():
    # Production uses fixed reviewed019 hashes. Substitute hashes only for this
    # independent, public fixture to exercise integrity/error paths offline.
    text = SYNTHETIC.decode()
    anchor = '\nclass AlignmentMatrix(run_lab.Matrix):\n'
    text = text.replace(anchor, '\n' + compat.IDENTITY_FIXTURE + anchor)
    anchor = '        self.observed, self.outcomes = [], []\n'
    text = text.replace(anchor, anchor + compat.BASELINE_FIXTURE)
    anchor = '        if self.mutate is not None:\n'
    text = text.replace(anchor, '        add_alignment_fixture_identity(a, f, self.authority_index)\n' + anchor)
    text = text.replace(compat.DEADLINE_ANCHOR, compat.DEADLINE_ANCHOR + compat.DEADLINE_STIMULUS)
    with patch.multiple(compat, BEFORE_SHA256=compat.digest(SYNTHETIC), AFTER_SHA256=compat.digest(text.encode())):
        yield


@contextmanager
def synthetic_source_pins():
    with synthetic_pins():
        before = {patcher.LAB: b'synthetic observed harness', patcher.PREPARE: b'synthetic native builder',
                  patcher.FIXTURE: SYNTHETIC}
        after = {patcher.LAB: b'synthetic reviewed harness', patcher.PREPARE: b'synthetic reviewed builder',
                 patcher.FIXTURE: compat.transform(SYNTHETIC)}
        with patch.multiple(patcher, BASELINE={name: compat.digest(data) for name, data in before.items()},
                AFTER={name: compat.digest(data) for name, data in after.items()}), \
                patch.object(patcher, 'patch_harness', return_value=after[patcher.LAB]), \
                patch.object(patcher, 'patch_prepare', return_value=after[patcher.PREPARE]), \
                patch.object(patcher, 'patch_fixture', side_effect=compat.transform):
            yield before, after


def add_synthetic_proof(root):
    # Only exercises exact manifest validation. The real eleven-test proof is
    # separately run against pinned private source by the hosted preparation.
    (root / patcher.PROOF_STATE).write_text(json.dumps(patcher.expected_proof()))


class FixtureCompatibilityTests(unittest.TestCase):
    def source(self, root):
        target = root / patcher.FIXTURE
        target.parent.mkdir(parents=True)
        target.write_bytes(SYNTHETIC)
        (root / patcher.LAB).write_bytes(b'synthetic observed harness')
        (root / patcher.PREPARE).write_bytes(b'synthetic native builder')
        return target

    def test_initial_baseline_has_full_identity_without_clock_or_callbacks(self):
        with synthetic_pins():
            namespace = {'types': types}
            exec(compile(compat.transform(SYNTHETIC), '<synthetic-fixture>', 'exec'), namespace)
        for authority_index in (0, 1):
            clock = types.SimpleNamespace(now=17)
            callbacks = []
            matrix = namespace['AlignmentMatrix'](clock, lambda _: -205,
                authority_index=authority_index, mutate=lambda a, f: callbacks.append((a, f)))
            self.assertEqual(clock.now, 17)
            self.assertEqual(matrix.observed, [])
            self.assertEqual(matrix.outcomes, [])
            self.assertEqual(callbacks, [])
            authority, follower = matrix.last[authority_index], matrix.last[2]
            self.assertEqual(authority['sentinelPosition'], 37088)
            self.assertEqual(follower['sentinelPosition'], 36883)
            self.assertEqual(authority['sentinelTime'], 0)
            self.assertEqual(follower['sentinelTime'], 0)
            self.assertEqual(follower['preflightDiagnostics']['recoveryControlVersion'],
                follower['preflightDiagnostics']['recoveryAppliedControlVersion'])
            for value in (authority, follower):
                self.assertIs(value['nativePlayers'][0]['seekInProgress'], False)
                self.assertIs(value['nativePlayers'][0]['playingIntent'], True)
                self.assertIs(type(value['pid']), int)
                self.assertGreater(value['pid'], 0)
                for key in ('bundleId', 'root', 'clientId', 'deviceSessionId', 'contextId'):
                    self.assertTrue(value[key])
                self.assertEqual(value['contexts']['source-context']['authorityClientId'], authority['clientId'])
                self.assertEqual(value['contexts']['source-context']['authorityDeviceSessionId'], authority['deviceSessionId'])

    def test_metadata_precedes_original_negative_mutations_without_changing_samples(self):
        with synthetic_pins():
            namespace = {'types': types}
            exec(compile(compat.transform(SYNTHETIC), '<synthetic-fixture>', 'exec'), namespace)
        callbacks = []
        def mutate(a, f):
            callbacks.append((a['pid'], f['pid']))
            f['followSourceContextId'] = 'wrong-context'
        matrix = namespace['AlignmentMatrix'](types.SimpleNamespace(now=0), lambda _: 0, mutate=mutate)
        a, f = matrix.states()
        self.assertEqual((a['sentinelPosition'], f['sentinelPosition']), (100, 200))
        self.assertEqual(callbacks, [(100, 102)])
        self.assertEqual(f['followSourceContextId'], 'wrong-context')

    def test_only_declared_stimulus_changes_and_inverse_preserves_all_assertions(self):
        with synthetic_pins():
            result = compat.transform(SYNTHETIC)
        self.assertEqual(compat.original_test_contract(ast.parse(SYNTHETIC)),
                         compat.original_test_contract(ast.parse(compat.restore_deadline_stimulus(result))))

    def test_fake_expiry_runs_original_outcome_first_without_touching_samples(self):
        namespace = {}
        source = 'def install(matrix):\n' + ''.join(line[4:] + '\n' for line in compat.DEADLINE_STIMULUS.splitlines())
        exec(source, namespace)
        clock = types.SimpleNamespace(now=4.89)
        observed = []
        native = {'positionMs':123}
        matrix = types.SimpleNamespace(clock=clock, native=native,
            outcome=lambda name, **kw: observed.append((name, clock.now, dict(native))))
        namespace['install'](matrix)
        matrix.outcome('unrelated')
        self.assertEqual(clock.now, 4.89)
        matrix.outcome('native-follow-aligned')
        self.assertEqual(observed[-1], ('native-follow-aligned', 4.89, {'positionMs':123}))
        self.assertEqual(clock.now, 5)
        self.assertEqual(native, {'positionMs':123})

    def test_integrated_manifest_success_and_one_shot_rejection(self):
        with tempfile.TemporaryDirectory() as tmp, synthetic_source_pins():
            root = Path(tmp)
            target = self.source(root)
            patcher.apply(root)
            add_synthetic_proof(root)
            patcher.verify_prepared(root)
            saved = target.read_bytes()
            with self.assertRaises(ValueError):
                patcher.apply(root)
            self.assertEqual(target.read_bytes(), saved)

    def test_fixture_source_pin_failure_is_nonmutating(self):
        with tempfile.TemporaryDirectory() as tmp, synthetic_source_pins():
            root = Path(tmp)
            target = self.source(root)
            target.write_bytes(SYNTHETIC + b'changed')
            snapshots = {name: (root / name).read_bytes() for name in patcher.BASELINE}
            with self.assertRaises(ValueError):
                patcher.apply(root)
            self.assertEqual(snapshots, {name: (root / name).read_bytes() for name in patcher.BASELINE})
            self.assertFalse((root / patcher.STATE).exists())

    def test_integrated_manifest_exact_keyset_and_boolean_types(self):
        with tempfile.TemporaryDirectory() as tmp, synthetic_source_pins():
            root = Path(tmp)
            self.source(root)
            patcher.apply(root)
            add_synthetic_proof(root)
            state = root / patcher.STATE
            original = json.loads(state.read_text())
            for edit in (lambda m: m.update(originalFixtureTestMethodsUnchanged=1),
                         lambda m: m.update(files={}),
                         lambda m: m.update(extra=True)):
                changed = json.loads(json.dumps(original))
                edit(changed)
                state.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    patcher.verify_prepared(root)
            state.write_text(json.dumps(original))
            patcher.verify_prepared(root)

    def test_prepared_fixture_tamper_rejected_by_integration_gate(self):
        with tempfile.TemporaryDirectory() as tmp, synthetic_source_pins():
            root = Path(tmp)
            target = self.source(root)
            patcher.apply(root)
            add_synthetic_proof(root)
            target.write_bytes(target.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                patcher.verify_prepared(root)

    def test_dangling_fixture_or_state_symlinks_rejected(self):
        for relative in (patcher.FIXTURE, '.native_follow_readiness'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp, synthetic_source_pins():
                root = Path(tmp)
                self.source(root)
                path = root / relative
                if path.exists():
                    path.unlink()
                path.symlink_to(root / 'missing')
                with self.assertRaises(ValueError):
                    patcher.apply(root)
                self.assertFalse((root / 'missing').exists())


if __name__ == '__main__':
    unittest.main()
