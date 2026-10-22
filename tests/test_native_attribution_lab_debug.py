"""Public synthetic verification of the explicit disposable logging opt-in."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
HELPER=(ROOT/'scripts/native_attribution/lab_stream_attribution.py' if (ROOT/'scripts').is_dir() else ROOT/'lab_stream_attribution.py')
SPEC=importlib.util.spec_from_file_location('attribution_lab_debug_test',HELPER)
a=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(a)
ORIGINAL_SHA='7e4b804a9eaeeec929768ddd9ce9a5479639f73f443a8f3e6693916e59565833'
DEBUG_SHA='f8781ae5077924daebc0908500f79e57ee9a80af8e9d25d474468651563d2af0'
OLD=b'  await Logger.setLogLevel(LogLevel.warning);\n'
NEW=b'  await Logger.setLogLevel(LogLevel.debug);\n'

class LabDebugAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.repo=Path(self.tmp.name).resolve(); self.path=self.repo/a.LAB_MAIN
        self.path.parent.mkdir(parents=True); self.path.write_bytes(NEW)
        self.baseline=dict(a.BASELINE_HASHES)

    def test_default_exact_source_pins_stay_unchanged(self):
        self.assertEqual(a.BASELINE_HASHES[a.LAB_MAIN],ORIGINAL_SHA)
        self.assertEqual(a.LAB_DEBUG_MAIN_SHA256,DEBUG_SHA)
        with a.lab_debug_observation(self.repo): self.assertEqual(a.BASELINE_HASHES,self.baseline)
        self.assertEqual(a.BASELINE_HASHES,self.baseline)

    def test_explicit_mode_requires_exact_hash_and_reverse_proof(self):
        # Synthetic digest oracle separates the forward and reverse checks;
        # real-byte pins are independently exercised on the disposable clone.
        def checksum(data): return DEBUG_SHA if data==NEW else ORIGINAL_SHA if data==OLD else 'bad'
        with patch.object(a,'digest',side_effect=checksum):
            with a.lab_debug_observation(self.repo,True):
                self.assertEqual(a.BASELINE_HASHES,dict(self.baseline,**{a.LAB_MAIN:DEBUG_SHA}))
            self.assertEqual(a.BASELINE_HASHES,self.baseline)
            for bad in [NEW+b'x',NEW+NEW,OLD]:
                self.path.write_bytes(bad)
                with self.assertRaises(ValueError):
                    with a.lab_debug_observation(self.repo,True): pass
                self.assertEqual(a.BASELINE_HASHES,self.baseline)

    def test_reverse_mismatch_and_symlink_refused(self):
        with patch.object(a,'digest',side_effect=[DEBUG_SHA,'bad']),self.assertRaises(ValueError):
            with a.lab_debug_observation(self.repo,True): pass
        self.path.unlink(); self.path.symlink_to(self.repo/'missing')
        with self.assertRaises(ValueError):
            with a.lab_debug_observation(self.repo,True): pass

    def test_scope_restored_when_operation_raises(self):
        with patch.object(a,'digest',side_effect=[DEBUG_SHA,ORIGINAL_SHA]):
            with self.assertRaises(RuntimeError):
                with a.lab_debug_observation(self.repo,True): raise RuntimeError('synthetic')
        self.assertEqual(a.BASELINE_HASHES,self.baseline)
        with self.assertRaises(ValueError):
            with a.lab_debug_observation(self.repo,1): pass

    def test_cli_flag_is_explicit_for_all_three_stages(self):
        for stage,func in [('proof','prove_and_patch'),('native','apply_native_handoff'),('verify','verify_applied')]:
            for enabled in (False,True):
                args=['helper',stage,'--repo',str(self.repo),'--expected-lab-before-sha256','0'*64]
                if enabled: args += ['--lab-debug-observation']
                with patch.object(sys,'argv',args),patch.object(a,'lab_debug_observation') as scope,patch.object(a,func) as operation:
                    a.main(); scope.assert_called_once_with(self.repo,enabled=enabled); operation.assert_called_once()

if __name__=='__main__': unittest.main()
