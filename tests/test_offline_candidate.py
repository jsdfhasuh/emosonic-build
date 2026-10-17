import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import offline_candidate as c


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "requests").mkdir()
        (self.root / c.REQUEST_PATH).write_text(json.dumps(c.REQUEST))
        self.event = {"before": c.PARENT, "after": "a" * 40, "ref": "refs/heads/main",
                      "created": False, "deleted": False, "forced": False,
                      "head_commit": {"id": "a" * 40, "message": c.MESSAGE}}
        self.event_path = self.root / "event.json"
        self.event_path.write_text(json.dumps(self.event))
        self.env = {"GITHUB_REPOSITORY": c.p.BUILDER, "GITHUB_REF": "refs/heads/main",
                    "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": "a" * 40,
                    "GITHUB_RUN_ID": "1234", "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_WORKFLOW_REF": c.p.BUILDER + "/.github/workflows/offline-candidate.yml@refs/heads/main",
                    "GITHUB_EVENT_PATH": str(self.event_path), "SOURCE_SHA": c.SHA,
                    "BUILD_VERSION": c.SOURCE_VERSION}
        self.root_patch = patch.object(c.p, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.print_patch = patch("builtins.print")
        self.print_patch.start()
        self.addCleanup(self.print_patch.stop)
        self.env_patch = patch.dict(os.environ, self.env, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_exact_push_and_same_run_retry_are_allowed(self):
        c.context()
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "2"}):
            c.context()

    def test_other_contexts_and_release_credentials_are_rejected(self):
        for key, value in [("GITHUB_REPOSITORY", "someone/fork"), ("GITHUB_REF", "refs/heads/test"),
                           ("GITHUB_EVENT_NAME", "workflow_dispatch"), ("GITHUB_WORKFLOW_REF", "other"),
                           ("GITHUB_SHA", "bad"), ("GITHUB_RUN_ID", "12\ninjected=1"),
                           ("SOURCE_SHA", "b" * 40), ("BUILD_VERSION", "1.0.6+24"),
                           ("RELEASE_WRITE_TOKEN", "synthetic"), ("RELEASE_MODE", "publish-stable")]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}), self.assertRaises(c.p.GateError):
                c.context()

    def test_later_push_force_push_or_wrong_marker_is_rejected(self):
        for key, value in [("before", "b" * 40), ("after", "c" * 40), ("ref", "refs/heads/test"),
                           ("forced", True), ("deleted", True), ("created", True),
                           ("head_commit", {"id": "a" * 40, "message": "ordinary change"})]:
            self.event_path.write_text(json.dumps(dict(self.event, **{key: value})))
            with self.subTest(key=key), self.assertRaises(c.p.GateError):
                c.context()

    def test_request_version_sha_mode_or_symlink_cannot_change(self):
        request = self.root / c.REQUEST_PATH
        for key, value in [("source_sha", "b" * 40), ("source_version", "1.0.6+24"),
                           ("version_code", 24), ("version_name", "1.0.6"), ("mode", "publish-stable")]:
            request.write_text(json.dumps(dict(c.REQUEST, **{key: value})))
            with self.subTest(key=key), self.assertRaises(c.p.GateError):
                c.context()
        target = self.root / "redirect.json"
        target.write_text(json.dumps(c.REQUEST))
        request.unlink()
        request.symlink_to(target)
        with self.assertRaises(c.p.GateError):
            c.context()

    def test_fetch_checks_original_pubspec_then_exact_sha(self):
        with patch.dict(os.environ, {"SOURCE_READ_TOKEN": "synthetic"}), patch.object(c.p, "remote_source_version", return_value=c.SOURCE_VERSION) as version, patch.object(c.p, "fetch") as fetch:
            c.fetch()
        version.assert_called_once_with(c.SHA, "synthetic")
        fetch.assert_called_once_with()
        with patch.dict(os.environ, {"SOURCE_READ_TOKEN": "synthetic"}), patch.object(c.p, "remote_source_version", return_value="1.0.6+24"), patch.object(c.p, "fetch") as fetch, self.assertRaises(c.p.GateError):
            c.fetch()
        fetch.assert_not_called()

    def test_baseline_uses_pinned_digest_and_actual_apk_inspection(self):
        from io import BytesIO
        with patch.object(c.urllib.request, "urlopen", return_value=BytesIO(b"apk")), patch.object(c.p, "file_digest", return_value=c.p.POLICY["baseline_apk_sha256"]), patch.object(c.p, "inspect_apk") as inspect:
            c.baseline()
        inspect.assert_called_once_with(self.root / "baseline.apk", "1.0.6+23")
        self.assertFalse((self.root / "baseline.apk").exists())
        with patch.object(c.urllib.request, "urlopen", return_value=BytesIO(b"apk")), patch.object(c.p, "file_digest", return_value="0" * 64), patch.object(c.p, "inspect_apk") as inspect, self.assertRaises(c.p.GateError):
            c.baseline()
        inspect.assert_not_called()
        self.assertFalse((self.root / "baseline.apk").exists())

    def make_bundle(self):
        apk = self.root / "synthetic.apk"
        apk.write_bytes(b"synthetic-apk")
        c.stage(apk)
        return self.root / "dist"

    def test_bundle_has_test_identity_and_exact_source(self):
        directory = self.make_bundle()
        self.assertEqual(c.bundle(directory), c.p.file_digest(directory / c.APK_NAME))
        manifest = json.loads((directory / "android-test-manifest.json").read_text())
        self.assertEqual(manifest["source_sha"], c.SHA)
        self.assertEqual(manifest["source_ref"], c.SOURCE_REF)
        self.assertEqual(manifest["source_version"], "1.0.6+23")
        self.assertEqual(manifest["version_name"], "1.0.6-offline.601d6b4")
        self.assertEqual(manifest["version_code"], 23)
        self.assertTrue(manifest["prerelease"])
        self.assertFalse(manifest["published"])

    def test_extra_private_file_and_provenance_tampering_are_rejected(self):
        directory = self.make_bundle()
        extra = directory / "private.dart"
        extra.write_text("synthetic")
        with self.assertRaises(c.p.GateError):
            c.bundle(directory)
        extra.unlink()
        path = directory / "android-test-manifest.json"
        manifest = json.loads(path.read_text())
        manifest["source_sha"] = "b" * 40
        path.write_text(json.dumps(manifest))
        with self.assertRaises(c.p.GateError):
            c.bundle(directory)

    def test_verifier_inspects_actual_labeled_binary(self):
        directory = self.make_bundle()
        directory.rename(self.root / "incoming")
        with patch.object(c.p, "inspect_apk") as inspect:
            c.verify()
        inspect.assert_called_once_with(self.root / "incoming" / c.APK_NAME, c.PACKAGE_VERSION)

    def test_no_publishing_entrypoint(self):
        with patch.object(sys, "argv", ["offline_candidate.py", "publish"]), patch.object(c.p, "publish") as publish:
            self.assertEqual(c.main(), 1)
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
