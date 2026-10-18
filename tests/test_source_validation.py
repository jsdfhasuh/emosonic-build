"""Synthetic source validation contracts. No private source or credentials."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_pipeline import p, ENV, SHA, VERSION

VENDOR_TEST = "test/services/native_start_dependency_contract_test.dart"
VENDOR_CHECK = "tool/native_start/verify_vendored_source.py"
TEST_PATHS = {VENDOR_TEST, "test/synthetic_test.dart"}


def events(paths=TEST_PATHS, count=2):
    stream = [{"type": "start", "protocolVersion": "0.1.1", "time": 0},
              {"type": "allSuites", "count": len(paths), "time": 0}]
    identifier = 0
    for name in sorted(paths):
        suite, loader, group = identifier, identifier + 1, identifier + 2
        identifier += 3
        stream += [
            {"type": "suite", "suite": {"id": suite, "path": name}, "time": 0},
            {"type": "testStart", "test": {"id": loader, "suiteID": suite, "groupIDs": [], "name": "private loader"}, "time": 0},
            {"type": "testDone", "testID": loader, "hidden": True, "skipped": False, "result": "success", "time": 0},
            {"type": "group", "group": {"id": group, "suiteID": suite, "parentID": None, "testCount": count}, "time": 0},
        ]
        for _ in range(count):
            stream += [
                {"type": "testStart", "test": {"id": identifier, "suiteID": suite, "groupIDs": [group], "name": "private test secret"}, "time": 0},
                {"type": "print", "testID": identifier, "messageType": "print", "message": "private secret traceback path", "time": 0},
                {"type": "testDone", "testID": identifier, "hidden": False, "skipped": False, "result": "success", "time": 0},
            ]
            identifier += 1
        stream += [
            {"type": "testStart", "test": {"id": identifier, "suiteID": suite, "groupIDs": [group], "name": "private teardown"}, "time": 0},
            {"type": "testDone", "testID": identifier, "hidden": True, "skipped": False, "result": "success", "time": 0},
        ]
        identifier += 1
    stream.append({"type": "done", "success": True, "time": 1})
    return stream


def report(stream):
    return "\n".join(json.dumps(event) for event in stream) + "\n"


class ReporterTests(unittest.TestCase):
    def setUp(self):
        self.source = Path("/synthetic/source")
        self.stream = events()

    def parse(self, stream=None):
        return p.flutter_test_summary(report(self.stream if stream is None else stream),
                                      self.source, TEST_PATHS)

    def test_counts_only_real_tests_not_hidden_loaders_or_hooks(self):
        self.assertEqual(self.parse(), {"passed": 4, "suites": 2, "hidden": 4, "skipped": 0, "failed": 0})

    def test_suite_count_may_arrive_after_interleaved_tests(self):
        count = self.stream.pop(1)
        self.stream.insert(-1, count)
        self.assertEqual(self.parse()["passed"], 4)

    def test_absolute_suite_paths_are_normalized(self):
        for event in self.stream:
            if event["type"] == "suite":
                event["suite"]["path"] = str(self.source / event["suite"]["path"])
        self.assertEqual(self.parse()["suites"], 2)

    def test_missing_start_completion_and_suite_declaration_are_rejected(self):
        for kind in ("start", "done", "allSuites"):
            with self.subTest(kind=kind), self.assertRaises(p.GateError):
                self.parse([e for e in self.stream if e["type"] != kind])

    def test_false_null_numeric_or_absent_success_never_passes(self):
        for value in (False, None, 1, "true"):
            stream = copy.deepcopy(self.stream)
            stream[-1]["success"] = value
            with self.subTest(value=value), self.assertRaises(p.GateError):
                self.parse(stream)
        self.stream[-1].pop("success")
        with self.assertRaises(p.GateError):
            self.parse()

    def test_empty_or_no_meaningful_tests_fail(self):
        for stream in ([], events(count=0), [{"type": "start", "protocolVersion": "0.1.1", "time": 0},
                        {"type": "allSuites", "count": 0, "time": 0},
                        {"type": "done", "success": True, "time": 0}]):
            with self.assertRaises(p.GateError):
                self.parse(stream)

    def test_empty_discovered_suite_with_no_root_group_counts_zero(self):
        stream = events()
        suite = next(e["suite"]["id"] for e in stream if e["type"] == "suite")
        removed = {e["test"]["id"] for e in stream if e["type"] == "testStart"
                   and e["test"]["suiteID"] == suite and e["test"]["groupIDs"]}
        stream = [e for e in stream if not
                  (e["type"] == "group" and e["group"]["suiteID"] == suite
                   or e["type"] == "testStart" and e["test"]["id"] in removed
                   or e.get("testID") in removed)]
        self.assertEqual(self.parse(stream), {"passed": 2, "suites": 2, "hidden": 3,
                                             "skipped": 0, "failed": 0})

    def test_failure_error_and_skipped_results_fail_even_if_done_succeeds(self):
        for overrides in ({"result": "failure"}, {"result": "error"}, {"skipped": True},
                          {"hidden": "false"}, {"skipped": 0}, {"result": None}):
            stream = copy.deepcopy(self.stream)
            event = next(e for e in stream if e["type"] == "testDone" and not e["hidden"])
            event.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(p.GateError):
                self.parse(stream)

    def test_hidden_lifecycle_failure_or_skip_still_fails(self):
        for overrides in ({"result": "failure"}, {"skipped": True}):
            stream = copy.deepcopy(self.stream)
            next(e for e in stream if e["type"] == "testDone" and e["hidden"]).update(overrides)
            with self.assertRaises(p.GateError):
                self.parse(stream)

    def test_late_error_after_successful_completion_fails(self):
        identifier = next(e["testID"] for e in self.stream if e["type"] == "testDone")
        self.stream.insert(-1, {"type": "error", "testID": identifier,
                               "error": "private secret", "stackTrace": "private path", "time": 1})
        with self.assertRaises(p.GateError) as error:
            self.parse()
        self.assertNotIn("private secret", str(error.exception))
        self.assertNotIn("private path", str(error.exception))

    def test_duplicate_start_done_suite_and_test_events_fail(self):
        for kind in ("start", "allSuites", "suite", "testStart", "testDone", "done"):
            stream = copy.deepcopy(self.stream)
            index = next(i for i, event in enumerate(stream) if event["type"] == kind)
            stream.insert(index + 1, copy.deepcopy(stream[index]))
            with self.subTest(kind=kind), self.assertRaises(p.GateError):
                self.parse(stream)

    def test_unmatched_test_completion_or_unfinished_test_fails(self):
        stream = copy.deepcopy(self.stream)
        next(e for e in stream if e["type"] == "testDone")["testID"] = 999
        with self.assertRaises(p.GateError):
            self.parse(stream)
        del self.stream[next(i for i, e in enumerate(self.stream) if e["type"] == "testDone")]
        with self.assertRaises(p.GateError):
            self.parse()

    def test_mismatched_suite_and_root_group_counts_fail(self):
        for kind, field in (("allSuites", "count"), ("group", "testCount")):
            stream = copy.deepcopy(self.stream)
            event = next(e for e in stream if e["type"] == kind)
            target = event["group"] if kind == "group" else event
            target[field] += 1
            with self.subTest(kind=kind), self.assertRaises(p.GateError):
                self.parse(stream)

    def test_missing_vendor_suite_and_unexpected_suite_fail(self):
        with self.assertRaises(p.GateError):
            self.parse(events({"test/synthetic_test.dart"}))
        for name in ("test/unexpected_test.dart", "../escape_test.dart", "/outside/test.dart", None):
            stream = copy.deepcopy(self.stream)
            next(e for e in stream if e["type"] == "suite")["suite"]["path"] = name
            with self.subTest(name=name), self.assertRaises(p.GateError):
                self.parse(stream)

    def test_bool_or_negative_ids_and_unlinked_groups_fail(self):
        for value in (True, -1, "1", 99999):
            stream = copy.deepcopy(self.stream)
            next(e for e in stream if e["type"] == "testStart")["test"]["suiteID"] = value
            with self.assertRaises(p.GateError):
                self.parse(stream)

    def test_malformed_plaintext_duplicate_keys_and_nonfinite_json_fail(self):
        for raw in ("", "private secret", "[]\n", "{}\n", report(self.stream) + "private trailer",
                    '{"type":"start","type":"done","time":0}\n',
                    '{"type":"start","time":NaN}\n',
                    "\ufffd" + report(self.stream), report(self.stream)[:-3]):
            with self.subTest(raw=raw[:20]), self.assertRaises(p.GateError):
                p.flutter_test_summary(raw, self.source, TEST_PATHS)

    def test_unknown_protocol_or_event_fails_closed(self):
        self.stream[0]["protocolVersion"] = "0.2.0"
        with self.assertRaises(p.GateError):
            self.parse()
        self.stream = events()
        self.stream.insert(-1, {"type": "unknown", "time": 0})
        with self.assertRaises(p.GateError):
            self.parse()


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".test-", dir=p.ROOT)
        self.source = Path(self.tmp.name) / "source"
        self.source.mkdir()
        (self.source / ".gitignore").write_text("build/\n.dart_tool/\n*.g.dart\n")
        (self.source / "source.dart").write_bytes(b"source\r\nunchanged\x00\xff")
        (self.source / "tracked.g.dart").write_text("tracked generated stays protected")
        self.git("init", "--quiet")
        self.git("config", "core.autocrlf", "false")
        self.git("add", "-f", ".gitignore", "source.dart", "tracked.g.dart")
        self.git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
                 "commit", "--quiet", "-m", "Synthetic source fixture")
        self.sha = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.source, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True).stdout.decode()

    def fingerprint(self):
        return p.source_fingerprint(self.source, self.sha, p.build_env())

    def test_exact_binary_and_crlf_bytes_match_commit(self):
        first = self.fingerprint()
        self.assertEqual(first, self.fingerprint())
        self.assertEqual(first[1], {".gitignore", "source.dart", "tracked.g.dart"})

    def test_ignored_generated_outputs_do_not_change_fingerprint(self):
        first = self.fingerprint()
        (self.source / "build").mkdir()
        (self.source / "build/output.bin").write_bytes(b"generated")
        (self.source / ".dart_tool").mkdir()
        (self.source / ".dart_tool/cache").write_bytes(b"generated")
        (self.source / "new.g.dart").write_text("generated")
        self.assertEqual(first, self.fingerprint())

    def test_tracked_generated_files_cannot_change_even_if_ignored(self):
        (self.source / "tracked.g.dart").write_text("modified")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_line_endings_and_byte_mutations_are_not_normalized(self):
        for data in (b"source\nunchanged\x00\xff", b"source\r\nunchanged\x00\xfe"):
            (self.source / "source.dart").write_bytes(data)
            with self.assertRaises(p.GateError):
                self.fingerprint()

    def test_index_changes_do_not_hide_mutated_source(self):
        (self.source / "source.dart").write_bytes(b"modified")
        self.git("add", "source.dart")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_assume_unchanged_does_not_hide_mutated_source(self):
        self.git("update-index", "--assume-unchanged", "source.dart")
        (self.source / "source.dart").write_bytes(b"modified")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_missing_source_and_symlink_replacements_fail(self):
        path = self.source / "source.dart"
        path.unlink()
        with self.assertRaises(p.GateError):
            self.fingerprint()
        path.symlink_to(self.source / "tracked.g.dart")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_nonignored_new_files_and_changed_modes_fail(self):
        added = self.source / "unexpected.dart"
        added.write_text("new private code")
        with self.assertRaises(p.GateError):
            self.fingerprint()
        added.unlink()
        path = self.source / "source.dart"
        path.chmod(0o755)
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_changed_head_fails(self):
        self.git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
                 "commit", "--quiet", "--allow-empty", "-m", "Synthetic second commit")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_staged_new_source_cannot_hide_from_inventory(self):
        (self.source / "new.dart").write_text("new private code")
        self.git("add", "new.dart")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_repository_info_excludes_cannot_hide_new_source(self):
        (self.source / "unexpected.dart").write_text("new private code")
        (self.source / ".git/info/exclude").write_text("unexpected.dart\n")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_global_excludes_cannot_hide_new_source(self):
        (self.source / "unexpected.dart").write_text("new private code")
        ignore = Path(self.tmp.name) / "global-ignore"
        ignore.write_text("unexpected.dart\n")
        self.git("config", "core.excludesFile", str(ignore))
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_new_self_hiding_ignore_rules_fail(self):
        folder = self.source / "new"
        folder.mkdir()
        (folder / ".gitignore").write_text("*\n")
        (folder / "unexpected.dart").write_text("new private code")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_new_staged_ignore_rules_fail(self):
        folder = self.source / "new"
        folder.mkdir()
        (folder / ".gitignore").write_text("*\n")
        self.git("add", "-f", "new/.gitignore")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_new_ignore_rules_inside_ignored_generated_outputs_fail(self):
        folder = self.source / "build/generated"
        folder.mkdir(parents=True)
        (folder / ".gitignore").write_text("*\n")
        with self.assertRaises(p.GateError):
            self.fingerprint()

    def test_executable_owner_bit_must_match_git_mode(self):
        path = self.source / "source.dart"
        path.chmod(0o755)
        self.git("add", "source.dart")
        self.git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
                 "commit", "--quiet", "-m", "Synthetic executable fixture")
        self.sha = self.git("rev-parse", "HEAD").strip()
        self.fingerprint()
        path.chmod(0o645)
        with self.assertRaises(p.GateError):
            self.fingerprint()


class SourceValidationTests(unittest.TestCase):
    def setUp(self):
        self.source = Path("/synthetic/source")
        self.paths = TEST_PATHS | {VENDOR_CHECK, "pubspec.yaml"}
        self.calls = []
        self.failure = None

    def fake_quiet(self, args, source, env):
        self.assertEqual(source, self.source)
        self.calls.append(args)
        for name in ("SOURCE_READ_TOKEN", "GITHUB_TOKEN", "RELEASE_WRITE_TOKEN",
                     "ANDROID_KEYSTORE_BASE64", "ANDROID_KEY_PASSWORD", "ANDROID_KEY_ALIAS",
                     "DEFAULT_SERVER_URL", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "GITHUB_ENV", "GITHUB_PATH"):
            self.assertNotIn(name, env)
        if self.failure == len(self.calls):
            raise p.GateError("Synthetic tool failure.")
        return report(events()) if args[1] == "test" else "private tool output suppressed"

    def run_stage(self, fingerprint=None):
        sensitive = {name: "synthetic-secret" for name in
                     ("SOURCE_READ_TOKEN", "GITHUB_TOKEN", "RELEASE_WRITE_TOKEN",
                      "ANDROID_KEYSTORE_BASE64", "ANDROID_KEY_PASSWORD", "ANDROID_KEY_ALIAS",
                      "DEFAULT_SERVER_URL", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "GITHUB_ENV", "GITHUB_PATH")}
        with patch.dict(os.environ, sensitive, clear=True), \
             patch.object(p, "source_context", return_value=(self.source, VERSION, SHA, None)) as context, \
             patch.object(p, "source_fingerprint", side_effect=fingerprint or [("hash", self.paths), ("hash", self.paths)]) as check, \
             patch.object(p, "quiet", side_effect=self.fake_quiet):
            p.validate_source()
            context.assert_called_once_with(require_server=False)
            self.assertEqual(check.call_count, 2)

    def test_complete_stage_runs_codegen_vendor_analyze_full_tests_and_integrity(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.run_stage()
        self.assertEqual(self.calls, [
            ["flutter", "pub", "get"],
            ["dart", "run", "scripts/check_navigation_consistency.dart"],
            ["dart", "run", "build_runner", "build", "--delete-conflicting-outputs"],
            [p.sys.executable, VENDOR_CHECK],
            ["flutter", "analyze", "--no-pub", "--fatal-infos", "--fatal-warnings"],
            ["flutter", "test", "--no-pub", "--reporter=json"],
        ])
        self.assertIn("4 tests; 2 suites; 4 hidden lifecycle events; 0 skipped; 0 failed.", buffer.getvalue())
        for private in ("synthetic-secret", "private tool", "private test", "private loader", VENDOR_TEST):
            self.assertNotIn(private, buffer.getvalue())

    def test_each_failed_tool_stops_later_tools_and_rechecks_integrity(self):
        for stage in range(1, 7):
            self.calls = []
            self.failure = stage
            with patch("builtins.print"), self.assertRaises(p.GateError):
                self.run_stage()
            self.assertEqual(len(self.calls), stage)

    def test_source_mutation_fails_even_after_successful_tests(self):
        with patch("builtins.print"), self.assertRaises(p.GateError):
            self.run_stage([("before", self.paths), ("after", self.paths)])

    def test_vendor_validation_must_be_present(self):
        for missing in (VENDOR_CHECK, VENDOR_TEST):
            self.paths = (TEST_PATHS | {VENDOR_CHECK, "pubspec.yaml"}) - {missing}
            self.calls.clear()
            with self.assertRaises(p.GateError):
                self.run_stage()
            self.assertEqual(self.calls, [])

    def test_source_context_validation_does_not_need_server_configuration(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=p.ROOT) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "pubspec.yaml").write_text("version: " + VERSION + "\n")
            with patch.dict(os.environ, ENV, clear=True), patch.object(p, "ROOT", root), \
                 patch.object(p, "quiet", side_effect=[SHA, p.POLICY["flutter_sha"]]), \
                 patch.object(p.shutil, "which", return_value=str(root / "sdk/bin/flutter")):
                self.assertEqual(p.source_context(require_server=False), (source, VERSION, SHA, None))

    def test_source_context_validation_still_rejects_wrong_sdk_or_source(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=p.ROOT) as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "pubspec.yaml").write_text("version: " + VERSION + "\n")
            for replies in (["b" * 40], [SHA, "b" * 40]):
                with patch.dict(os.environ, ENV, clear=True), patch.object(p, "ROOT", root), \
                     patch.object(p, "quiet", side_effect=replies), \
                     patch.object(p.shutil, "which", return_value=str(root / "sdk/bin/flutter")), \
                     self.assertRaises(p.GateError):
                    p.source_context(require_server=False)

    def test_nonzero_private_tool_output_is_never_printed(self):
        result = subprocess.CompletedProcess(["synthetic"], 1, b"private source secret",
                                             b"private path and assertion")
        output = io.StringIO()
        with patch.object(p, "context"), patch.object(p.sys, "argv", ["pipeline.py", "validate_source"]), \
             patch.object(p, "validate_source", side_effect=lambda: p.quiet(["synthetic"])), \
             patch.object(p.subprocess, "run", return_value=result), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(p.main(), 1)
        self.assertIn("exit 1", output.getvalue())
        self.assertNotIn("private", output.getvalue())
        self.assertNotIn("secret", output.getvalue())

    def test_malformed_private_test_output_is_never_printed(self):
        output = io.StringIO()
        with patch.object(p, "context"), patch.object(p.sys, "argv", ["pipeline.py", "validate_source"]), \
             patch.object(p, "validate_source", side_effect=lambda: p.flutter_test_summary(
                 "private source names and secret", self.source, TEST_PATHS)), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(p.main(), 1)
        self.assertNotIn("private source names", output.getvalue())
        self.assertNotIn("secret", output.getvalue())

    def test_workflow_has_one_fetch_secret_no_validation_secrets_and_always_cleans(self):
        workflow = (p.ROOT / ".github/workflows/android.yml").read_text()
        section = workflow.split("\n  validate-source:\n")[1].split("\n  build:\n")[0]
        self.assertEqual(section.count("secrets."), 1)
        self.assertIn("SOURCE_READ_TOKEN: ${{ secrets.SOURCE_READ_TOKEN }}", section)
        self.assertIn("persist-credentials: false", section)
        self.assertIn("flutter-version: '3.41.2'", section)
        self.assertIn("SOURCE_SHA: ${{ needs.prepare.outputs.source_sha }}", section)
        self.assertIn("BUILD_VERSION: ${{ needs.prepare.outputs.version }}", section)
        validation = section.split("run: python3 scripts/pipeline.py fetch")[1]
        self.assertNotIn("secrets.", validation)
        self.assertIn("if: always()", validation)
        self.assertIn("run: python3 scripts/pipeline.py cleanup", validation)
        self.assertNotIn("upload-artifact", section)

    def test_both_platforms_and_publish_require_successful_validation(self):
        workflow = (p.ROOT / ".github/workflows/android.yml").read_text()
        for name in ("build", "build-windows", "publish"):
            section = re.split(r"\n  [a-z][a-z-]*:\n",
                               workflow.split("\n  " + name + ":\n", 1)[1], maxsplit=1)[0]
            self.assertIn("validate-source", next(line for line in section.splitlines() if "needs:" in line))
        self.assertIn("python3 scripts/pipeline.py build", workflow)
        self.assertIn("python scripts/pipeline.py build_windows", workflow)


if __name__ == "__main__":
    unittest.main()

