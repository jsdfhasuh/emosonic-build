import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pipeline", ROOT / "scripts/pipeline.py")
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
SHA = p.POLICY["trusted_source_shas"][0]
VERSION = "1.0.6+24"
ENV = {"GITHUB_REPOSITORY": p.BUILDER, "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "1234", "GITHUB_RUN_ATTEMPT": "1", "SOURCE_SHA": SHA, "BUILD_VERSION": VERSION, "RELEASE_MODE": "publish-prerelease", "ANDROID_HOME": "/sdk"}


class ValidationTests(unittest.TestCase):
    def test_strict_versions(self):
        self.assertEqual(p.version(VERSION), (1, 0, 6, 24))
        for bad in ["1.0.6", "v1.0.6+24", "1.0.6+0", "01.0.6+24", "1.0.6+024", "1.0.6+2147483648", "1.0.6+24\n", "1.0.6+24;id", "1.0.6+２４", "-1.0.0+25"]:
            with self.subTest(bad=bad), self.assertRaises(p.GateError):
                p.version(bad)

    def test_version_floor_and_conflicts(self):
        for value in ["1.0.6+22", "1.0.6+23", "1.0.5+99", "2.0.0+23"]:
            with self.subTest(value=value), self.assertRaises(p.GateError):
                p.monotonic(value, ["v1.0.6+23"])
        with self.assertRaises(p.GateError):
            p.monotonic(VERSION, ["android-v1.0.6+24"])
        with self.assertRaises(p.GateError):
            p.monotonic(VERSION, ["legacy-unrecognized"])
        p.monotonic(VERSION, ["v1.0.6+23", "v1.0.5+20"])
        p.monotonic("1.0.7+26", ["android-v1.0.7+25"])

    def test_ref_injection_and_unknown_sha(self):
        for bad in ["--help", "master;id", "$(id)", "x\ny", "../master", "a//b", "refs/heads/a.lock", "https://example.com/x", "a" * 201]:
            with self.subTest(bad=bad), self.assertRaises(p.GateError):
                p.ref_input(bad)
        for good in ["master", SHA, "refs/heads/master", "release/test"]:
            self.assertEqual(p.ref_input(good), good)
        with self.assertRaises(p.GateError):
            p.checked_sha("b" * 40)

    def test_context_rejects_forks_branches_and_events(self):
        with patch.dict(os.environ, ENV, clear=True):
            p.context()
            for key, value in [("GITHUB_REPOSITORY", "someone/emosonic-build"), ("GITHUB_REF", "refs/heads/test"), ("GITHUB_EVENT_NAME", "pull_request_target"), ("GITHUB_RUN_ID", "123\ninjected=1")]:
                with self.subTest(key=key), patch.dict(os.environ, {key: value}), self.assertRaises(p.GateError):
                    p.context()

    def test_missing_secrets_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(p.GateError):
            p.require_secrets(["SOURCE_READ_TOKEN"])

    def test_java_properties_escaping(self):
        self.assertEqual(p.property_escape("a\\b=c:#!"), "a\\\\b\\=c\\:\\#\\!")
        self.assertEqual(p.property_escape("中文"), "\\u4e2d\\u6587")
        for bad in ["", " leading", "trailing ", "line\nbreak"]:
            with self.assertRaises(p.GateError):
                p.property_escape(bad)

    def test_history_pagination_and_owned_draft(self):
        def fake(path, token):
            if "/releases?" in path:
                return [{"id": i, "tag_name": f"v1.0.0+{i}"} for i in range(1, 101)] if "&page=1" in path else [{"id": 101, "tag_name": "android-v1.0.0+101"}]
            return [{"name": "android-v1.0.0+101"}]
        with patch.object(p, "api", side_effect=fake):
            tags = p.history(exclude_id=101, exclude_tag="android-v1.0.0+101")
        self.assertEqual(len(tags), 100)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT)
        self.folder = Path(self.tmp.name)
        self.assertTrue(self.folder.resolve().is_relative_to(ROOT.resolve()))
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        self.apk = self.folder / p.apk_name(VERSION)
        self.write_apk()
        self.metadata()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def write_apk(self, abis=None, extra=None):
        with zipfile.ZipFile(self.apk, "w") as archive:
            for abi in abis or p.POLICY["abis"]:
                archive.writestr("lib/" + abi + "/libapp.so", b"synthetic-test-fixture")
            if extra:
                archive.writestr(extra, b"synthetic")

    def metadata(self):
        digest = p.file_digest(self.apk)
        (self.folder / (self.apk.name + ".sha256")).write_text(digest + "  " + self.apk.name + "\n", encoding="ascii")
        (self.folder / "manifest.json").write_text(json.dumps(p.metadata(VERSION, SHA, digest)), encoding="utf-8")
        return digest

    def test_bundle_checks(self):
        self.assertEqual(p.bundle(self.folder, VERSION, SHA), p.file_digest(self.apk))
        (self.folder / "private.dart").write_text("fixture", encoding="utf-8")
        with self.assertRaises(p.GateError):
            p.bundle(self.folder, VERSION, SHA)

    def test_tampered_apk_and_provenance(self):
        self.apk.write_bytes(b"changed")
        with self.assertRaises(p.GateError):
            p.bundle(self.folder, VERSION, SHA)
        self.metadata()
        value = json.loads((self.folder / "manifest.json").read_text())
        value["source_sha"] = "b" * 40
        (self.folder / "manifest.json").write_text(json.dumps(value))
        with self.assertRaises(p.GateError):
            p.bundle(self.folder, VERSION, SHA)

    def fake_tools(self, cert=None, package=None, debug=False):
        signature = "Signer #1 certificate SHA-256 digest: " + (cert or p.POLICY["certificate_sha256"]) + "\n"
        badging = "package: name='" + (package or p.POLICY["application_id"]) + "' versionCode='24' versionName='1.0.6'\n"
        if debug:
            badging += "application-debuggable\n"
        return patch.object(p, "quiet", side_effect=[signature, badging])

    def test_inspect_accepts_matching_metadata(self):
        with self.fake_tools():
            p.inspect_apk(self.apk, VERSION)

    def test_inspect_rejects_wrong_signer_package_debug_and_version(self):
        for kwargs in [{"cert": "0" * 64}, {"package": "com.example.other"}, {"debug": True}]:
            with self.subTest(kwargs=kwargs), self.fake_tools(**kwargs), self.assertRaises(p.GateError):
                p.inspect_apk(self.apk, VERSION)
        with self.fake_tools(), self.assertRaises(p.GateError):
            p.inspect_apk(self.apk, "1.0.6+25")

    def test_inspect_rejects_missing_abi_and_private_files(self):
        self.write_apk(abis=["arm64-v8a"])
        with self.fake_tools(), self.assertRaises(p.GateError):
            p.inspect_apk(self.apk, VERSION)
        for extra in ["assets/private.dart", "assets/release.jks", "assets/key.properties", "../outside", "assets/debug.symbols"]:
            self.write_apk(extra=extra)
            with self.subTest(extra=extra), self.fake_tools(), self.assertRaises(p.GateError):
                p.inspect_apk(self.apk, VERSION)


class PublishTests(unittest.TestCase):
    setUp = ArtifactTests.setUp
    tearDown = ArtifactTests.tearDown
    write_apk = ArtifactTests.write_apk
    metadata = ArtifactTests.metadata

    def test_existing_release_cannot_be_overwritten(self):
        with patch.object(p, "bundle", return_value="0" * 64), patch.object(p, "history", return_value={"v1.0.6+23"}), patch.object(p, "api", return_value={"id": 99}) as request, patch.dict(os.environ, {"RELEASE_WRITE_TOKEN": "synthetic-test-token", "VERIFIED_APK_SHA256": "0" * 64}), self.assertRaises(p.GateError):
            with patch("builtins.print"):
                p.publish()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(len(request.call_args.args), 2)  # GET only, no payload.

    def test_missing_write_token_cannot_publish(self):
        with patch.object(p, "api") as request, self.assertRaises(p.GateError):
            p.publish()
        request.assert_not_called()

    def test_verifier_digest_mismatch_cannot_publish(self):
        with patch.object(p, "bundle", return_value="0" * 64), patch.object(p, "api") as request, patch.dict(os.environ, {"RELEASE_WRITE_TOKEN": "synthetic-test-token", "VERIFIED_APK_SHA256": "1" * 64}), self.assertRaises(p.GateError):
            p.publish()
        request.assert_not_called()

    def test_publish_api_contract_and_no_binary_execution(self):
        incoming = self.folder / "incoming"
        incoming.mkdir()
        for file in list(self.folder.iterdir()):
            if file.is_file():
                file.rename(incoming / file.name)
        self.apk = incoming / p.apk_name(VERSION)
        calls, uploaded = [], []
        def fake(path, token=None, method="GET", data=None, upload=False):
            calls.append((path, method, data, upload))
            if upload:
                name = p.urllib.parse.parse_qs(p.urllib.parse.urlsplit(path).query)["name"][0]
                uploaded.append({"name": name})
                return {"name": name, "size": len(data), "digest": "sha256:" + p.hashlib.sha256(data).hexdigest()}
            if path.endswith("/releases/latest"):
                return {"id": 10, "prerelease": False}
            if "/git/ref/" in path or "/releases/tags/" in path:
                return None
            if path == f"/repos/{p.DEST}":
                return {"full_name": p.DEST, "private": False, "default_branch": "main"}
            if "/commits/" in path:
                return {"sha": "c" * 40}
            if method == "POST":
                return {"id": 11}
            if method == "PATCH":
                return {"draft": False, "prerelease": True}
            return {"draft": True, "prerelease": True, "tag_name": "android-v" + VERSION, "assets": uploaded}
        with patch.object(p, "ROOT", self.folder), patch.object(p, "api", side_effect=fake), patch.object(p, "history", return_value={"v1.0.6+23"}), patch.object(p, "quiet", side_effect=AssertionError("Publisher must not execute binaries")), patch.dict(os.environ, {"RELEASE_WRITE_TOKEN": "synthetic-test-token", "VERIFIED_APK_SHA256": p.file_digest(self.apk)}):
            with patch("builtins.print"):
                p.publish()
        writes = [(method, data) for _, method, data, upload in calls if method != "GET" and not upload]
        self.assertEqual([m for m, _ in writes], ["POST", "PATCH"])
        for _, body in writes:
            self.assertTrue(body["prerelease"])
            self.assertEqual(body["make_latest"], "false")
        self.assertEqual(writes[0][1]["tag_name"], "android-v" + VERSION)

    def test_conflict_causes_no_write(self):
        incoming = self.folder / "incoming"
        incoming.mkdir()
        for file in list(self.folder.iterdir()):
            if file.is_file():
                file.rename(incoming / file.name)
        with patch.object(p, "ROOT", self.folder), patch.object(p, "history", return_value={"v1.0.6+24"}), patch.object(p, "api") as request, patch.dict(os.environ, {"RELEASE_WRITE_TOKEN": "synthetic-test-token", "VERIFIED_APK_SHA256": p.file_digest(incoming / p.apk_name(VERSION))}), self.assertRaises(p.GateError):
            p.publish()
        request.assert_not_called()


class WorkflowTests(unittest.TestCase):
    def test_workflow_trust_boundaries(self):
        text = (ROOT / ".github/workflows/android.yml").read_text(encoding="utf-8")
        self.assertNotIn("pull_request_target", text)
        self.assertNotIn("--clobber", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("secrets: inherit", text)
        self.assertEqual(text.count("RELEASE_WRITE_TOKEN: ${{ secrets.RELEASE_WRITE_TOKEN }}"), 1)
        prefix, publish = text.split("\n  publish:\n")
        self.assertNotIn("RELEASE_WRITE_TOKEN", prefix)
        self.assertNotIn("SOURCE_READ_TOKEN", publish)
        self.assertNotIn("ANDROID_KEY", publish)
        for action in p.re.findall(r"uses: (\S+)", text):
            self.assertRegex(action, r"^[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
        self.assertEqual(text.count("uses: actions/checkout@"), text.count("persist-credentials: false"))
        for run in p.re.findall(r"run: ([^\n]+)", text):
            self.assertNotIn("${{", run)


if __name__ == "__main__":
    unittest.main()
