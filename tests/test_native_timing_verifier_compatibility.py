import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_follow_readiness as r
import native_follow_lifecycle as l
import native_seek_anchor_observation as t
spec = importlib.util.spec_from_file_location('timing_attribution', ROOT / 'scripts/native_attribution/lab_stream_attribution.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)


def write(root, relative, value):
    path = root / relative; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if type(value) is bytes else json.dumps(value).encode())


class TimingVerifierCompatibility(unittest.TestCase):
    def readiness_fixture(self, root):
        write(root, r.STATE, r.expected_manifest()); write(root, r.PROOF_STATE, r.expected_proof())
        write(root, r.PREPARE, b'timing prepare'); write(root, r.FIXTURE, b'fixture')
        write(root, r.ORIGINAL_STATE, b'original')
        original_digest = r.digest
        values = {b'timing prepare': t.AFTER[r.PREPARE], b'fixture': r.AFTER[r.FIXTURE],
                  b'original': r.BASELINE[r.LAB]}
        return patch.object(r, 'digest', side_effect=lambda data: values.get(data, original_digest(data)))

    def test_readiness_requires_explicit_opt_in_and_keeps_old_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.readiness_fixture(root), patch.object(t, 'verify_prepared') as verification:
                old = (root / r.STATE).read_bytes()
                with self.assertRaises(ValueError): r.verify_prepared(root)
                r.verify_prepared(root, timing_observation=True)
                verification.assert_called_once_with(root, require_harness=False)
                self.assertEqual((root / r.STATE).read_bytes(), old)
                changed = r.expected_manifest(); changed['files'][r.PREPARE]['after'] = t.AFTER[r.PREPARE]
                write(root, r.STATE, changed)
                with self.assertRaises(ValueError): r.verify_prepared(root, timing_observation=True)

    def test_compiled_gate_checks_original_getter_manifest_and_new_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            write(root, r.NATIVE_STATE, {'readOnly': True, 'files': r.NATIVE_HASHES})
            values = {}
            for name, relative in r.NATIVE_PATHS.items():
                data = name.encode(); write(root, relative, data); values[data] = t.NATIVE_AFTER[name]
            with patch.object(r, 'verify_prepared'), patch.object(t, 'verify_compiled') as verification, \
                    patch.object(r, 'digest', side_effect=lambda data: values[data]):
                r.verify_compiled(root, timing_observation=True)
                verification.assert_called_once_with(root)
                with self.assertRaises(ValueError): r.verify_compiled(root)
                changed = {name: dict(value, after=t.NATIVE_AFTER[name]) for name, value in r.NATIVE_HASHES.items()}
                write(root, r.NATIVE_STATE, {'readOnly': True, 'files': changed})
                with self.assertRaises(ValueError): r.verify_compiled(root, timing_observation=True)

    def test_lifecycle_flag_retains_original_manifest_and_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            write(root, l.STATE, l.expected_manifest()); write(root, l.LAB_MAIN, l.LOG_NEW)
            write(root, l.LAB, b'timing harness')
            for name in l.PAYLOAD_HASHES: write(root, 'tool/native_playback_mac/' + name, l.payload(name))
            original_digest = l.digest
            with patch.object(l, 'patch_lab_logging', return_value=l.LOG_NEW), \
                    patch.object(l, 'digest', side_effect=lambda data: t.AFTER[l.LAB] if data == b'timing harness' else original_digest(data)), \
                    patch.object(t, 'verify_prepared') as verification:
                old = (root / l.STATE).read_bytes()
                with self.assertRaises(ValueError): l.verify_prepared(root)
                l.verify_prepared(root, timing_observation=True)
                verification.assert_called_once_with(root, require_harness=True)
                self.assertEqual((root / l.STATE).read_bytes(), old)
                changed = l.expected_manifest(); changed['files'][l.LAB]['after'] = t.AFTER[l.LAB]
                write(root, l.STATE, changed)
                with self.assertRaises(ValueError): l.verify_prepared(root, timing_observation=True)

    def test_attribution_opt_in_requires_exact_reverse_then_original_lifecycle(self):
        timing, lifecycle = MagicMock(), MagicMock()
        timing.HARNESS_SHA = a.TIMING_BASELINE_LAB_SHA256
        timing.AFTER = {a.LAB: a.TIMING_OBSERVED_LAB_SHA256}
        lifecycle.AFTER_HARNESS_SHA256 = a.TIMING_BASELINE_LAB_SHA256
        timing.restore_harness.return_value = b'original'
        specification = MagicMock()
        with patch.object(a.importlib.util, 'spec_from_file_location', return_value=specification), \
                patch.object(a.importlib.util, 'module_from_spec', side_effect=[timing, lifecycle]), \
                patch.object(a, 'digest', side_effect=lambda data: {
                    b'observed': a.TIMING_OBSERVED_LAB_SHA256, b'original': a.TIMING_BASELINE_LAB_SHA256}[data]):
            a._verify_timing_observation(Path('/unused'), enabled=True, observed=b'observed')
        timing.verify_prepared.assert_called_once_with(Path('/unused'), require_harness=False)
        timing.restore_harness.assert_called_once_with(b'observed')
        lifecycle.verify_prepared.assert_called_once_with(Path('/unused'), require_harness=False)

    def test_default_and_wrong_type_modes_never_load_extra_observation(self):
        with patch.object(a.importlib.util, 'spec_from_file_location') as loading:
            a._verify_timing_observation(Path('/unused'))
            loading.assert_not_called()
            with self.assertRaises(ValueError): a._verify_timing_observation(Path('/unused'), enabled=1)
        with self.assertRaises(ValueError): r._verify_source_prepared(Path('/unused'), timing_observation=1)
        with self.assertRaises(ValueError): l.verify(Path('/unused'), timing_observation=1)


if __name__ == '__main__': unittest.main()
