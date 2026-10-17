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
ENV = {"GITHUB_REPOSITORY": p.BUILDER, "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "1234", "GITHUB_RUN_ATTEMPT": "1", "SOURCE_SHA": SHA, "BUILD_VERSION": VERSION, "RELEASE_MODE": "publish-stable", "ANDROID_HOME": "/sdk"}


class ValidationTests(unittest.TestCase):
    def test_strict_versions(self):
        self.assertEqual(p.version(VERSION), (1, 0, 6, 24))
        for bad in ["1.0.6", "v1.0.6+24", "1.0.6+0", "01.0.6+24", "1.0.6+024", "1.0.6+2147483648", "1.0.6+65536", "65536.0.0+24", "1.0.6+24\n", "1.0.6+24;id", "1.0.6+２４", "-1.0.0+25"]:
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
        (self.folder / "android-manifest.json").write_text(json.dumps(p.metadata(VERSION, SHA, digest)), encoding="utf-8")
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
        value = json.loads((self.folder / "android-manifest.json").read_text())
        value["source_sha"] = "b" * 40
        (self.folder / "android-manifest.json").write_text(json.dumps(value))
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
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT)
        self.folder = Path(self.tmp.name).resolve()
        self.assertTrue(self.folder.is_relative_to(ROOT.resolve()))
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        self.incoming = self.folder / "incoming"
        self.digests = {}
        for platform in ("android", "windows"):
            directory = self.incoming / platform
            directory.mkdir(parents=True)
            name = p.package_name(VERSION, platform)
            package = directory / name
            package.write_bytes(("synthetic-" + platform).encode())
            digest = p.file_digest(package)
            self.digests[platform] = digest
            (directory / (name + ".sha256")).write_text(digest + "  " + name + "\n", encoding="ascii")
            (directory / (platform + "-manifest.json")).write_text(json.dumps(p.metadata(VERSION, SHA, digest, platform)), encoding="utf-8")
        os.environ.update({"VERIFIED_APK_SHA256": self.digests["android"], "VERIFIED_INSTALLER_SHA256": self.digests["windows"], "RELEASE_WRITE_TOKEN": "synthetic-test-token"})
        self.calls = []
        self.uploaded = []
        self.published = False
        self.fail_upload = False
        self.corrupt_remote = False
        self.changed_latest = False
        self.root = patch.object(p, "ROOT", self.folder)
        self.root.start()

    def tearDown(self):
        self.root.stop()
        self.env.stop()
        self.tmp.cleanup()

    def fake_api(self, path, token=None, method="GET", data=None, upload=False):
        self.calls.append((path, method, data, upload))
        if upload:
            if self.fail_upload and len(self.uploaded) == 3:
                raise p.GateError("Synthetic upload failure.")
            name = p.urllib.parse.parse_qs(p.urllib.parse.urlsplit(path).query)["name"][0]
            value = {"name": name, "size": len(data), "digest": "sha256:" + p.hashlib.sha256(data).hexdigest()}
            self.uploaded.append(value)
            return value
        if path.endswith("/releases/latest"):
            return {"id": 11 if self.published else (12 if self.changed_latest and self.uploaded else 10), "prerelease": False}
        if "/git/ref/" in path or "/releases/tags/" in path:
            return None
        if path == f"/repos/{p.DEST}":
            return {"full_name": p.DEST, "private": False, "default_branch": "main"}
        if "/commits/" in path:
            return {"sha": "c" * 40}
        if method == "POST":
            return {"id": 11}
        if method == "PATCH":
            self.published = True
            return {"draft": False, "prerelease": False}
        assets = [dict(a) for a in self.uploaded]
        if self.corrupt_remote:
            assets[0]["digest"] = "sha256:" + "0" * 64
        return {"draft": True, "prerelease": False, "tag_name": "v" + VERSION, "assets": assets}

    def run_publish(self):
        with patch.object(p, "api", side_effect=self.fake_api), patch.object(p, "history", return_value={"v1.0.6+23"}), patch.object(p, "quiet", side_effect=AssertionError("Publisher must not execute binaries")), patch("builtins.print"):
            p.publish()

    def test_existing_release_cannot_be_overwritten(self):
        with patch.object(p, "history", return_value={"v1.0.6+23"}), patch.object(p, "api", return_value={"id": 99}) as request, self.assertRaises(p.GateError):
            p.publish()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(len(request.call_args.args), 2)

    def test_missing_write_token_cannot_publish(self):
        del os.environ["RELEASE_WRITE_TOKEN"]
        with self.assertRaises(p.GateError):
            self.run_publish()
        self.assertEqual(self.calls, [])

    def test_verifier_digest_mismatch_cannot_publish(self):
        for key in ("VERIFIED_APK_SHA256", "VERIFIED_INSTALLER_SHA256"):
            with self.subTest(key=key), patch.dict(os.environ, {key: "0" * 64}), self.assertRaises(p.GateError):
                self.run_publish()
        self.assertEqual(self.calls, [])

    def test_publish_api_contract_and_no_binary_execution(self):
        self.run_publish()
        writes = [(method, data) for _, method, data, upload in self.calls if method != "GET" and not upload]
        self.assertEqual([m for m, _ in writes], ["POST", "PATCH"])
        self.assertEqual(writes[0][1]["tag_name"], "v" + VERSION)
        self.assertFalse(writes[0][1]["prerelease"])
        self.assertTrue(writes[0][1]["draft"])
        self.assertEqual(writes[0][1]["make_latest"], "false")
        self.assertEqual(writes[1][1], {"draft": False, "prerelease": False, "make_latest": "true"})
        self.assertEqual(len(self.uploaded), 6)
        # Match the unchanged client tag parser and per-platform asset suffixes.
        self.assertRegex(writes[0][1]["tag_name"], r"^v?(\d+\.\d+\.\d+)\+([1-9]\d*)$")
        names = [a["name"] for a in self.uploaded]
        self.assertEqual([n for n in names if n.endswith(".apk")], [p.apk_name(VERSION)])
        self.assertEqual([n for n in names if n.endswith((".exe", ".msi"))], [p.installer_name(VERSION)])

    def test_conflict_causes_no_write(self):
        with patch.object(p, "history", return_value={"v1.0.6+24"}), patch.object(p, "api") as request, self.assertRaises(p.GateError):
            p.publish()
        request.assert_not_called()

    def test_each_missing_platform_blocks_publication(self):
        for platform in ("android", "windows"):
            directory = self.incoming / platform
            outside = self.folder / platform
            directory.rename(outside)
            with self.subTest(platform=platform), self.assertRaises(p.GateError):
                self.run_publish()
            outside.rename(directory)
        self.assertEqual(self.calls, [])

    def test_windows_wrong_version_source_or_run_rejected(self):
        manifest = self.incoming / "windows/windows-manifest.json"
        original = manifest.read_text()
        for key, value in [("version", "1.0.6+23"), ("source_sha", "b" * 40), ("run_id", "999"), ("platform", "android")]:
            data = json.loads(original)
            data[key] = value
            manifest.write_text(json.dumps(data))
            with self.subTest(key=key), self.assertRaises(p.GateError):
                self.run_publish()
        self.assertEqual(self.calls, [])

    def test_upload_failure_retains_draft(self):
        self.fail_upload = True
        with self.assertRaises(p.GateError):
            self.run_publish()
        self.assertFalse(self.published)
        self.assertNotIn("PATCH", [method for _, method, _, _ in self.calls])
        self.assertNotIn("DELETE", [method for _, method, _, _ in self.calls])

    def test_remote_corruption_blocks_latest(self):
        self.corrupt_remote = True
        with self.assertRaises(p.GateError):
            self.run_publish()
        self.assertFalse(self.published)

    def test_concurrent_release_blocks_latest(self):
        self.changed_latest = True
        with self.assertRaises(p.GateError):
            self.run_publish()
        self.assertFalse(self.published)


class WindowsTests(unittest.TestCase):
    def test_original_windows_entrypoint_receives_only_build_configuration(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as directory:
            source = Path(directory).resolve()
            self.assertTrue(source.is_relative_to(ROOT.resolve()))
            pubspec = source / "pubspec.yaml"
            pubspec.write_text("version: 1.0.6+22\n")
            with patch.dict(os.environ, {"RELEASE_WRITE_TOKEN": "synthetic", "SOURCE_READ_TOKEN": "synthetic", "ANDROID_KEY_ALIAS": "synthetic"}), patch.object(p.os, "name", "nt"), patch.object(p, "source_context", return_value=(source, VERSION, SHA, "https://example.com/")), patch.object(p, "check_windows_source"), patch.object(p, "windows_tool", return_value=source / "ISCC.exe"), patch.object(p, "codegen"), patch.object(p, "quiet") as run, patch.object(p, "inspect_windows"), patch.object(p, "stage_package") as stage, patch("builtins.print"):
                p.build_windows()
            command, cwd, env = run.call_args.args
            self.assertEqual(command, ["cmd.exe", "/d", "/c", "build_windows.bat"])
            self.assertEqual(cwd, source)
            self.assertEqual(env["APP_UPDATE_SOURCE"], "github")
            self.assertEqual(env["GITHUB_RELEASE_REPOSITORY"], p.DEST)
            for secret in ("SOURCE_READ_TOKEN", "RELEASE_WRITE_TOKEN", "ANDROID_KEY_ALIAS"):
                self.assertNotIn(secret, env)
            self.assertEqual(pubspec.read_text(), "version: 1.0.6+22\n")
            self.assertEqual(stage.call_args.args[1:], (VERSION, SHA, "windows"))

    def test_original_windows_script_and_template_are_pinned(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as directory:
            source = Path(directory).resolve()
            self.assertTrue(source.is_relative_to(ROOT.resolve()))
            bat = source / "build_windows.bat"
            iss = source / "windows/installer/emosonic.iss"
            iss.parent.mkdir(parents=True)
            bat.write_bytes(b"synthetic-script")
            iss.write_bytes(b"synthetic-template")
            with patch.dict(p.POLICY, {"windows_build_script_blob": p.git_blob(bat), "windows_installer_template_blob": p.git_blob(iss)}):
                p.check_windows_source(source)
                iss.write_bytes(b"changed-template")
                with self.assertRaises(p.GateError):
                    p.check_windows_source(source)

    def test_installer_identity_and_old_package_rename_rejected(self):
        fields = {"AppName": "EmoSonic", "AppId": p.POLICY["windows_app_id"], "AppVersion": "1.0.6", "DefaultDirName": p.POLICY["windows_install_dir"], "PrivilegesRequired": "lowest", "OutputBaseFilename": p.installer_name(VERSION)[:-4]}
        def text(data):
            return "[Setup]\n" + "\n".join(k + "=" + v for k, v in data.items()) + "\n[Files]\n"
        p.setup_identity(text(fields), VERSION)
        for key, value in [("AppId", "different-guid"), ("AppVersion", "1.0.5"), ("PrivilegesRequired", "admin"), ("DefaultDirName", "{pf}\\EmoSonic"), ("OutputBaseFilename", "emosonic_windows_v1.0.6+23_setup")]:
            with self.subTest(key=key), self.assertRaises(p.GateError):
                p.setup_identity(text(dict(fields, **{key: value})), VERSION)

    def test_embedded_windows_version_cannot_be_faked_by_filename(self):
        info = {"file": VERSION, "product": VERSION, "numeric": [1, 0, 6, 24], "name": "EmoSonic", "original": "emosonic.exe", "debug": False, "signature": "NotSigned"}
        p.validate_windows_version(info, VERSION)
        for key, value in [("file", "1.0.6+23"), ("numeric", [1, 0, 6, 23]), ("product", "1.0.6+23"), ("debug", True), ("signature", "HashMismatch")]:
            with self.subTest(key=key), self.assertRaises(p.GateError):
                p.validate_windows_version(dict(info, **{key: value}), VERSION)

    def test_temporary_version_restores_on_failure(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as directory:
            folder = Path(directory).resolve()
            self.assertTrue(folder.is_relative_to(ROOT.resolve()))
            pubspec = folder / "pubspec.yaml"
            original = b"name: synthetic\r\nversion: 1.0.6+22\r\n"
            pubspec.write_bytes(original)
            with self.assertRaises(RuntimeError):
                with p.temporary_version(folder, VERSION):
                    self.assertIn(b"version: 1.0.6+24", pubspec.read_bytes())
                    raise RuntimeError("synthetic failure")
            self.assertEqual(pubspec.read_bytes(), original)

    def test_batch_metacharacters_rejected(self):
        self.assertEqual(p.windows_server("https://example.com/music/"), "https://example.com/music/")
        for bad in ['https://example.com/%PATH%', 'https://example.com/a&whoami', 'https://example.com/"', 'https://example.com/!PATH!', 'https://example.com/a b']:
            with self.subTest(bad=bad), self.assertRaises(p.GateError):
                p.windows_server(bad)

    def test_build_env_has_no_pat_or_android_signing_secrets(self):
        with patch.dict(os.environ, {"SOURCE_READ_TOKEN": "synthetic", "RELEASE_WRITE_TOKEN": "synthetic", "ANDROID_KEYSTORE_BASE64": "synthetic", "ANDROID_KEY_ALIAS": "synthetic", "ANDROID_KEY_PASSWORD": "synthetic", "DEFAULT_SERVER_URL": "https://example.com", "JAVA_HOME": "sdk"}, clear=True):
            self.assertEqual(p.build_env(), {"JAVA_HOME": "sdk"})

    def test_x64_pe_validation(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as directory:
            folder = Path(directory).resolve()
            self.assertTrue(folder.is_relative_to(ROOT.resolve()))
            exe = folder / "fixture.exe"
            header = bytearray(64)
            header[:2] = b"MZ"
            p.struct.pack_into("<I", header, 60, 64)
            exe.write_bytes(header + b"PE\0\0\x64\x86")
            p.pe_x64(exe)
            exe.write_bytes(header + b"PE\0\0\x4c\x01")
            with self.assertRaises(p.GateError):
                p.pe_x64(exe)


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
        self.assertIn("needs: [prepare, build, verify, build-windows, verify-windows]", publish)
        self.assertNotIn("always()", publish)
        self.assertNotIn("publish-prerelease", text)
        windows = text.split("\n  build-windows:\n")[1].split("\n  verify-windows:\n")[0]
        self.assertIn("environment: windows-build", windows)
        self.assertNotIn("ANDROID_KEY", windows)
        verifier = text.split("\n  verify-windows:\n")[1].split("\n  publish:\n")[0]
        self.assertNotIn("secrets.", verifier)
        for action in p.re.findall(r"uses: (\S+)", text):
            self.assertRegex(action, r"^[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
        self.assertEqual(text.count("uses: actions/checkout@"), text.count("persist-credentials: false"))
        for run in p.re.findall(r"run: ([^\n]+)", text):
            self.assertNotIn("${{", run)


if __name__ == "__main__":
    unittest.main()
