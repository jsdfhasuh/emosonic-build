"""Public synthetic source exercises exact transformations and provenance gates."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts' if (ROOT / 'scripts').is_dir() else ROOT
sys.path.insert(0, str(SCRIPTS))
import native_follow_lifecycle as p

SYNTHETIC = b'''from urllib.error import HTTPError, URLError
from pathlib import Path
class Matrix:
    def wait(self, stage, reject_terminal_handoff=False):
        while True:
            try:
                states = self.states()
                if reject_terminal_handoff:
                    assert states
            finally:
                pass
    def run(self, follower, context, follower_original):
        if follower is not None:
            follower.command('follow', contextId=context)
            assert context
    def failure(self):
        return {'safe': True,
                          'waitObservation': getattr(self, 'wait_observation', {}),
                }
def main(temporary):
    state = Path(temporary) / 'server'
'''
MAIN = b'void main() async {\n  await Logger.setLogLevel(LogLevel.warning);\n}\n'


class LifecyclePatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        (self.repo/'tool/native_playback_mac').mkdir(parents=True)
        (self.repo/p.LAB).write_bytes(SYNTHETIC)
        (self.repo/p.LAB_MAIN).write_bytes(MAIN)
        self.patches = [patch.object(p, 'BEFORE_SHA256', p.digest(SYNTHETIC)),
            patch.object(p, 'MAIN_BEFORE_SHA256', p.digest(MAIN)),
            patch.object(p, 'MAIN_AFTER_SHA256', p.digest(MAIN.replace(p.LOG_OLD,p.LOG_NEW)))]
        for item in self.patches: item.start(); self.addCleanup(item.stop)
        self.after = p._transform_harness(SYNTHETIC)
        item = patch.object(p,'AFTER_HARNESS_SHA256',p.digest(self.after)); item.start(); self.addCleanup(item.stop)

    def test_exact_transform_preserves_every_original_assert_and_control(self):
        result = p.patch_harness(SYNTHETIC)
        proof = p.prove_controls_unchanged(SYNTHETIC,result)
        self.assertTrue(all(proof.values()))
        self.assertIn(b'Path(temporary).resolve(strict=True)', result)
        for method in ('wait','run','failure'):
            before = [n for n in ast.walk(ast.parse(SYNTHETIC)) if isinstance(n,ast.FunctionDef) and n.name==method][0]
            after = [n for n in ast.walk(ast.parse(result)) if isinstance(n,ast.FunctionDef) and n.name==method][0]
            self.assertEqual(ast.dump(before),ast.dump(p.OriginalProjection().visit(copy.deepcopy(after))))

    def test_assert_deadline_command_or_observer_arguments_change_fails(self):
        for old,new in [(b'assert context',b'assert True'),(b'while True:',b'while False:'),
            (b"follower.command('follow', contextId=context)",b"follower.command('pause', contextId=context)"),
            (b'observe_follow_wait(self, stage, states)',b'observe_follow_wait(self, stage, [])')]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                p.prove_controls_unchanged(SYNTHETIC,self.after.replace(old,new))

    def test_apply_verify_and_payload_only_composed_harness(self):
        manifest = p.apply(self.repo)
        self.assertEqual(manifest,p.verify_prepared(self.repo))
        self.assertIs(manifest['productionRepositoryMutation'],False)
        self.assertIs(manifest['labOnlyDiagnosticLogging'],True)
        (self.repo/p.LAB).write_bytes(self.after+b'\n# later reviewed attribution\n')
        with self.assertRaises(ValueError): p.verify_prepared(self.repo)
        self.assertEqual(manifest,p.verify_prepared(self.repo,require_harness=False))
        with self.assertRaises(ValueError): p.verify_prepared(self.repo,require_harness=1)

    def test_manifest_tampering_and_boolean_lookalikes_fail(self):
        p.apply(self.repo)
        target=self.repo/p.STATE; original=json.loads(target.read_text())
        for transform in (lambda m:m.update(files={}),lambda m:m.update(added={}),
            lambda m:m.update(labOnlyDiagnosticLogging=1),lambda m:m.update(payloads={}),
            lambda m:m.update(unrecognized='secret')):
            value=copy.deepcopy(original); transform(value); target.write_text(json.dumps(value))
            with self.assertRaises(ValueError): p.verify_prepared(self.repo,require_harness=False)
        target.write_text(json.dumps(original))
        p.verify_prepared(self.repo)

    def test_payload_and_logging_tamper_fail_without_harness_check(self):
        p.apply(self.repo)
        for relative in ['tool/native_playback_mac/follow_lifecycle_observation.py',p.LAB_MAIN]:
            target=self.repo/relative; original=target.read_bytes(); target.write_bytes(original+b'\n')
            with self.assertRaises(ValueError): p.verify_prepared(self.repo,require_harness=False)
            target.write_bytes(original)

    def test_new_symlink_or_existing_destination_is_refused_before_write(self):
        target=self.repo/'tool/native_playback_mac/follow_lifecycle_observation.py'
        target.symlink_to(self.repo/'missing')
        with self.assertRaises(ValueError): p.apply(self.repo)
        self.assertEqual((self.repo/p.LAB).read_bytes(),SYNTHETIC)
        self.assertEqual((self.repo/p.LAB_MAIN).read_bytes(),MAIN)
        target.unlink(); target.write_text('preexisting')
        with self.assertRaises(ValueError): p.apply(self.repo)

    def test_reapply_and_changed_baseline_refused(self):
        (self.repo/p.LAB).write_bytes(SYNTHETIC+b'\n')
        with self.assertRaises(ValueError): p.apply(self.repo)
        (self.repo/p.LAB).write_bytes(SYNTHETIC); p.apply(self.repo)
        with self.assertRaises(ValueError): p.apply(self.repo)

    def test_logging_is_one_reversible_lab_setting_only(self):
        updated=p.patch_lab_logging(MAIN)
        self.assertEqual(updated.replace(p.LOG_NEW,p.LOG_OLD),MAIN)
        with self.assertRaises(ValueError): p.patch_lab_logging(MAIN+b'\n')
        with self.assertRaises(ValueError): p.patch_lab_logging(updated)


if __name__ == '__main__': unittest.main()
