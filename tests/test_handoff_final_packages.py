import base64
import copy
import contextlib
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import handoff_final_packages as c


class FinalPackageTests(unittest.TestCase):
    def pins(self):
        # Unit fixture only, never a candidate witness or publication pin.
        return (c.EVIDENCE[0], (c.EVIDENCE[1][0], c.EVIDENCE[1][1], 129999999999,
                                c.EVIDENCE[1][3]))

    @contextmanager
    def accepted(self):
        with patch.object(c, 'SECOND_WITNESS_ACCEPTED', True), \
                patch.object(c, 'EVIDENCE', self.pins()):
            yield

    def evidence(self):
        inputs = [(c.SOURCE_VALIDATION_RUN, c.SOURCE_VALIDATION_HEAD,
                   c.SOURCE_VALIDATION_JOB, c.SOURCE_VALIDATION_WORKFLOW,
                   'validate-source', c.SOURCE_VALIDATION_STEPS,
                   c.SOURCE_VALIDATION_REQUEST,
                   c.source_declaration('follow-bounded-budget-full-green-validation', 112))]
        inputs += [(run, head, job, c.NATIVE_WORKFLOW, 'native-macos-server',
                    c.NATIVE_STEPS, c.NATIVE_REQUEST, c.native_declaration(attempt))
                   for run, head, job, attempt in self.pins()]
        result = []
        for run, head, job, workflow, name, steps, path, declaration in inputs:
            result.extend([
                {'id': run, 'repository': {'full_name': c.p.BUILDER}, 'head_sha': head,
                 'head_branch': 'main', 'event': 'push', 'run_attempt': 1,
                 'path': f'.github/workflows/{workflow}.yml',
                 'status': 'completed', 'conclusion': 'success'},
                {'total_count': 1, 'jobs': [
                    {'id': job, 'name': name, 'run_id': run, 'head_sha': head,
                     'status': 'completed', 'conclusion': 'success',
                     'steps': [{'name': step, 'status': 'completed', 'conclusion': 'success'}
                               for step in steps]}]},
                {'type': 'file', 'path': path, 'encoding': 'base64',
                 'content': base64.b64encode(json.dumps(declaration).encode()).decode()},
            ])
        return result

    def check(self, data):
        with self.accepted(), patch.dict(os.environ, {'GITHUB_TOKEN': 'unit-placeholder'}), \
                patch.object(c.p, 'api', side_effect=data) as api:
            c.require_native_success()
            return api

    def test_actual_candidate_uses_two_exact_completed_witness_pins(self):
        self.assertIs(c.SECOND_WITNESS_ACCEPTED, True)
        self.assertEqual(c.EVIDENCE, (
            (40080780672, '68a208eb5b6fd712c1459f313e6222b0e885da2d', 120833766576, 113),
            (40088297493, 'ebf18d6e90a9682deab0b14a3a0529a2e02157f2', 120855662181, 114),
        ))
        self.assertTrue(c.REQUEST['native_witnesses_accepted'])
        self.assertEqual(c.REQUEST['native_witnesses'], c.witness_descriptors())

    def test_pending_flag_refuses_before_token_or_network(self):
        for pending in (False, None, 0, 1, 'true'):
            with patch.object(c, 'SECOND_WITNESS_ACCEPTED', pending), \
                    patch.object(c.p, 'require_secrets') as secrets, patch.object(c.p, 'api') as api:
                with self.subTest(pending=pending), self.assertRaises(c.p.GateError):
                    c.require_native_success()
                secrets.assert_not_called()
                api.assert_not_called()

    def test_zero_or_bad_witness_pins_refuse_before_network(self):
        for index in (0, 1):
            for field in (0, 2, 3):
                for bad in (0, -1, True, '123'):
                    pins = list(self.pins()); row = list(pins[index]); row[field] = bad
                    pins[index] = tuple(row)
                    with patch.object(c, 'SECOND_WITNESS_ACCEPTED', True), \
                            patch.object(c, 'EVIDENCE', tuple(pins)), \
                            patch.object(c.p, 'require_secrets') as secrets, patch.object(c.p, 'api') as api:
                        with self.subTest(index=index, field=field, bad=bad), self.assertRaises(c.p.GateError):
                            c.require_native_success()
                        secrets.assert_not_called(); api.assert_not_called()

    def test_distinct_runs_heads_jobs_and_requests_required(self):
        for field in range(4):
            pins = list(self.pins()); second = list(pins[1]); second[field] = pins[0][field]
            pins[1] = tuple(second)
            with patch.object(c, 'SECOND_WITNESS_ACCEPTED', True), \
                    patch.object(c, 'EVIDENCE', tuple(pins)), patch.object(c.p, 'api') as api:
                with self.subTest(field=field), self.assertRaises(c.p.GateError):
                    c.require_native_success()
                api.assert_not_called()

    def test_exact_full_source_and_two_native_witnesses_accepted(self):
        api = self.check(self.evidence())
        self.assertEqual(api.call_count, 9)
        for call in api.call_args_list:
            self.assertTrue(call.args[0].startswith('/repos/jsdfhasuh/emosonic-build/'))
            self.assertEqual(len(call.args), 2)  # GET only, never mutation.
        self.assertEqual(len(c.NATIVE_STEPS), 8)
        self.assertEqual(len(c.SOURCE_VALIDATION_STEPS), 3)

    def test_wrong_pending_failed_cancelled_or_rerun_evidence_rejected(self):
        mutations = [('id', 1), ('head_sha', 'a' * 40), ('head_branch', 'other'),
                     ('repository', {'full_name': 'other/repo'}), ('event', 'pull_request'),
                     ('run_attempt', 2), ('run_attempt', True), ('path', 'other.yml'),
                     ('status', 'in_progress'), ('conclusion', None),
                     ('conclusion', 'failure'), ('conclusion', 'cancelled'),
                     ('conclusion', 'skipped')]
        for index in (0, 3, 6):
            for field, value in mutations:
                data = self.evidence(); data[index][field] = value
                with self.subTest(index=index, field=field, value=value), self.assertRaises(c.p.GateError):
                    self.check(data)

    def test_wrong_missing_duplicate_or_truncated_job_rejected(self):
        for index in (1, 4, 7):
            for field, value in [('id', 1), ('run_id', 1), ('head_sha', 'a' * 40),
                                 ('name', 'other'), ('status', 'in_progress'),
                                 ('conclusion', 'skipped'), ('steps', None)]:
                data = self.evidence(); data[index]['jobs'][0][field] = value
                with self.subTest(index=index, field=field), self.assertRaises(c.p.GateError):
                    self.check(data)
            one = self.evidence()[index]['jobs'][0]
            for jobs in ({'total_count': 0, 'jobs': []}, {'total_count': 101, 'jobs': []},
                         {'total_count': 2, 'jobs': [one]},
                         {'total_count': 2, 'jobs': [one, copy.deepcopy(one)]},
                         {'total_count': True, 'jobs': [one]}):
                data = self.evidence(); data[index] = jobs
                with self.subTest(index=index, jobs=jobs['total_count']), self.assertRaises(c.p.GateError):
                    self.check(data)

    def test_every_strict_step_must_uniquely_succeed(self):
        for index in (1, 4, 7):
            for step_index in range(len(self.evidence()[index]['jobs'][0]['steps'])):
                for mutation in ('missing', 'duplicate', 'pending', 'failure', 'skipped', 'cancelled'):
                    data = self.evidence(); steps = data[index]['jobs'][0]['steps']
                    if mutation == 'missing':
                        steps.pop(step_index)
                    elif mutation == 'duplicate':
                        steps.append(copy.deepcopy(steps[step_index]))
                    elif mutation == 'pending':
                        steps[step_index]['status'] = 'in_progress'
                        steps[step_index]['conclusion'] = None
                    else:
                        steps[step_index]['conclusion'] = mutation
                    with self.subTest(index=index, step=step_index, mutation=mutation), self.assertRaises(c.p.GateError):
                        self.check(data)

    def test_all_declaration_fields_exact_and_missing_extra_rejected(self):
        for index in (2, 5, 8):
            declaration = json.loads(base64.b64decode(self.evidence()[index]['content']))
            for field in (*declaration.keys(), 'unexpected'):
                for missing in (False, True):
                    if missing and field == 'unexpected':
                        continue
                    data = self.evidence(); changed = dict(declaration)
                    if missing:
                        changed.pop(field)
                    else:
                        changed[field] = 'different'
                    data[index]['content'] = base64.b64encode(json.dumps(changed).encode()).decode()
                    with self.subTest(index=index, field=field, missing=missing), self.assertRaises(c.p.GateError):
                        self.check(data)

    def test_old_product_witnesses_never_substitute(self):
        for old in ('c7301a107fd1474ec0d22bb609426a435bc52584',
                    '72e524134c81becacf80ba8ff3f3d7562328347f'):
            for index in (5, 8):
                data = self.evidence(); blob = data[index]
                declaration = json.loads(base64.b64decode(blob['content']))
                declaration['source_sha'] = old
                blob['content'] = base64.b64encode(json.dumps(declaration).encode()).decode()
                with self.subTest(old=old, index=index), self.assertRaises(c.p.GateError):
                    self.check(data)

    def test_declaration_location_and_encoding_guarded(self):
        for index in (2, 5, 8):
            for field, value in [('path', 'other.json'), ('encoding', 'utf-8'),
                                 ('type', 'symlink'), ('content', 'x' * 8192),
                                 ('content', None)]:
                data = self.evidence(); data[index][field] = value
                with self.subTest(index=index, field=field), self.assertRaises(c.p.GateError):
                    self.check(data)

    def test_all_productive_cli_stages_block_while_pending(self):
        for stage in c.request.STAGES:
            if stage == 'cleanup':
                continue
            with patch.object(c, 'SECOND_WITNESS_ACCEPTED', False), \
                    patch.object(sys, 'argv', ['wrapper', stage]), \
                    patch.object(c.request, 'main') as main, patch.object(c.p, 'api') as api, \
                    patch.object(c.p, 'require_secrets') as secrets:
                self.assertEqual(c.main(), 1)
                main.assert_not_called(); api.assert_not_called(); secrets.assert_not_called()

    def test_cleanup_remains_available_without_witness_unlock(self):
        with patch.object(c, 'SECOND_WITNESS_ACCEPTED', False), \
                patch.object(sys, 'argv', ['wrapper', 'cleanup']), \
                patch.object(c.request, 'main', return_value=0) as main, \
                patch.object(c.p, 'api') as api:
            self.assertEqual(c.main(), 0)
            main.assert_called_once(); api.assert_not_called()

    def test_publication_and_native_stages_refused(self):
        for stage in ('publish', 'release', 'native', 'handoff', 'follow', 'deploy'):
            with self.accepted(), patch.object(sys, 'argv', ['wrapper', stage]), \
                    patch.object(c.request, 'main') as main:
                self.assertEqual(c.main(), 1); main.assert_not_called()

    def test_context_and_complete_evidence_precede_prepare(self):
        calls = []
        with self.accepted(), patch.object(sys, 'argv', ['wrapper', 'prepare']), \
                patch.object(c.request, 'context', side_effect=lambda: calls.append('context')), \
                patch.object(c, 'require_native_success', side_effect=lambda: calls.append('evidence')), \
                patch.object(c.request, 'main', side_effect=lambda: calls.append('prepare') or 0):
            self.assertEqual(c.main(), 0)
        self.assertEqual(calls, ['context', 'evidence', 'prepare'])

    def test_failed_evidence_blocks_prepare(self):
        with self.accepted(), patch.object(sys, 'argv', ['wrapper', 'prepare']), \
                patch.object(c.request, 'context'), \
                patch.object(c, 'require_native_success', side_effect=c.p.GateError('pending')), \
                patch.object(c.request, 'main') as main:
            self.assertEqual(c.main(), 1); main.assert_not_called()

    def test_wrapper_patches_restore_on_success_and_exception(self):
        request_fields = ('SOURCE_SHA', 'SOURCE_REF', 'SERVER_SHA', 'REQUEST', 'WORKFLOW',
                          'prepare', 'candidate_metadata')
        pipeline_fields = ('stage_package', 'verify', 'verify_windows', 'apk_name',
                           'installer_name', 'package_name', 'metadata')
        originals = [(module, name, getattr(module, name))
                     for module, fields in ((c.request, request_fields), (c.p, pipeline_fields))
                     for name in fields]
        def invoke():
            self.assertEqual(c.request.SOURCE_SHA, c.SOURCE_SHA)
            self.assertEqual(c.request.REQUEST, c.REQUEST)
            self.assertIs(c.request.prepare, c.prepare)
            self.assertIs(c.request.candidate_metadata, c.package_metadata)
            self.assertIs(c.p.stage_package, c.stage_package)
            self.assertIs(c.p.verify, c.verify)
            self.assertIs(c.p.verify_windows, c.verify_windows)
            return 0
        for action, expected in ((invoke, 0), (RuntimeError('unit failure'), 1)):
            with self.accepted(), patch.object(sys, 'argv', ['wrapper', 'validate_source']), \
                    patch.object(c.request, 'main', side_effect=action):
                self.assertEqual(c.main(), expected)
            for module, name, value in originals:
                self.assertIs(getattr(module, name), value)

    def test_prepare_retains_source_checks_and_only_adapts_names(self):
        def original():
            c.p.output('source_sha', c.SOURCE_SHA)
            c.p.output('version', c.VERSION)
            c.p.output('apk_name', 'original.apk')
            c.p.output('installer_name', 'original.exe')
        with patch.object(c, '_source_prepare', side_effect=original) as original_prepare, \
                patch.object(c.p, 'output') as emit:
            c.prepare()
            original_prepare.assert_called_once_with()
        self.assertEqual(dict(call.args for call in emit.call_args_list), {
            'source_sha': c.SOURCE_SHA, 'version': c.VERSION,
            'apk_name': c.delivery_name(c.VERSION, 'android'),
            'installer_name': c.delivery_name(c.VERSION, 'windows'),
        })

    @contextmanager
    def package_context(self, root):
        with self.accepted(), patch.object(c.p, 'ROOT', root), \
                patch.object(c.request, 'SOURCE_REF', c.SOURCE_REF), \
                patch.object(c.p, 'metadata', c.package_metadata), \
                patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ID': '999',
                                        'GITHUB_RUN_ATTEMPT': '1', 'BUILD_VERSION': c.VERSION,
                                        'SOURCE_SHA': c.SOURCE_SHA}):
            yield

    def make_bundle(self, root, platform):
        raw = root / 'original-built-package'
        raw.write_bytes(b'unit package bytes, not an executable')
        c.stage_package(raw, c.VERSION, c.SOURCE_SHA, platform)
        return root / 'dist'

    def test_delivery_names_include_test_version_full_source_and_reject_overrides(self):
        for platform in ('android', 'windows'):
            name = c.delivery_name(c.VERSION, platform)
            self.assertIn('TEST', name); self.assertIn(c.VERSION, name); self.assertIn(c.SOURCE_SHA, name)
            self.assertLess(len(name) + 67, 256)  # Existing checksum-size bound.
        self.assertTrue(c.delivery_name(c.VERSION, 'android').endswith('.apk'))
        self.assertTrue(c.delivery_name(c.VERSION, 'windows').endswith('-setup.exe'))
        for candidate, platform in (('1.0.11+28', 'android'), (c.VERSION, 'ios')):
            with self.assertRaises(c.p.GateError):
                c.delivery_name(candidate, platform)

    def test_three_file_bundle_manifest_and_original_names_preserved(self):
        original_names = (c.p.apk_name(c.VERSION), c.p.installer_name(c.VERSION))
        for platform in ('android', 'windows'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self.package_context(root):
                    directory = self.make_bundle(root, platform)
                    name = c.delivery_name(c.VERSION, platform)
                    self.assertEqual({p.name for p in directory.iterdir()},
                                     {name, name + '.sha256', platform + '-manifest.json'})
                    digest = c.delivery_bundle(directory, c.VERSION, c.SOURCE_SHA, platform)
                    self.assertEqual((directory / (name + '.sha256')).read_text(), digest + '  ' + name + '\n')
                    data = json.loads((directory / (platform + '-manifest.json')).read_text())
                    self.assertEqual(data['source_sha'], c.SOURCE_SHA)
                    self.assertEqual(data['source_ref'], c.SOURCE_REF)
                    self.assertEqual(data['mode'], 'build-only')
                    self.assertTrue(data['prerelease']); self.assertFalse(data['published'])
                    self.assertEqual(data['package_kind'], 'TEST')
                    self.assertEqual(data['package_filename'], name)
                    evidence = data['test_evidence']
                    self.assertEqual(evidence['native_witnesses'], c.witness_descriptors())
                    self.assertEqual(evidence['isolated_test_server_sha'], c.SERVER_SHA)
                    self.assertEqual(evidence['auxiliary_observer_sha'], c.AUXILIARY_SHA)
                    self.assertEqual(evidence['source_validation']['full_tests'], 3068)
                    self.assertIn('not the package runtime endpoint', evidence['server_scope'])
                    if platform == 'android':
                        self.assertEqual(data['identity']['certificate_sha256'], c.p.POLICY['certificate_sha256'])
                    else:
                        self.assertEqual(data['identity']['authenticode'], 'NotSigned')
                    self.assertEqual((c.p.apk_name(c.VERSION), c.p.installer_name(c.VERSION)), original_names)

    def test_package_bytes_checksum_and_provenance_tampering_rejected(self):
        mutations = ('bytes', 'checksum', 'extra', 'missing', 'wrong-name',
                     'manifest-source', 'manifest-witness', 'manifest-server',
                     'manifest-aux', 'manifest-version', 'manifest-published', 'manifest-name')
        for platform in ('android', 'windows'):
            for mutation in mutations:
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    with self.package_context(root):
                        directory = self.make_bundle(root, platform)
                        name = c.delivery_name(c.VERSION, platform)
                        manifest = directory / (platform + '-manifest.json')
                        if mutation == 'bytes':
                            (directory / name).write_bytes(b'tampered')
                        elif mutation == 'checksum':
                            (directory / (name + '.sha256')).write_text('0' * 64 + '  ' + name + '\n')
                        elif mutation == 'extra':
                            (directory / 'extra.txt').write_text('unexpected')
                        elif mutation == 'missing':
                            manifest.unlink()
                        elif mutation == 'wrong-name':
                            (directory / name).rename(directory / c.p.package_name(c.VERSION, platform))
                        else:
                            data = json.loads(manifest.read_text())
                            if mutation == 'manifest-source': data['source_sha'] = 'b' * 40
                            elif mutation == 'manifest-witness': data['test_evidence']['native_witnesses'][1]['run_id'] = 1
                            elif mutation == 'manifest-server': data['test_evidence']['isolated_test_server_sha'] = 'b' * 40
                            elif mutation == 'manifest-aux': data['test_evidence']['auxiliary_observer_sha'] = 'b' * 40
                            elif mutation == 'manifest-version': data['version'] = '1.0.11+28'
                            elif mutation == 'manifest-published': data['published'] = True
                            elif mutation == 'manifest-name': data['package_filename'] = 'stable.exe'
                            manifest.write_text(json.dumps(data))
                        with self.subTest(platform=platform, mutation=mutation), self.assertRaises(c.p.GateError):
                            c.delivery_bundle(directory, c.VERSION, c.SOURCE_SHA, platform)
                        self.assertEqual(c.p.package_name(c.VERSION, platform),
                                         c.p.apk_name(c.VERSION) if platform == 'android' else c.p.installer_name(c.VERSION))

    def test_symlink_bundle_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.package_context(root):
                directory = self.make_bundle(root, 'android')
                member = directory / c.delivery_name(c.VERSION, 'android')
                member.unlink(); member.symlink_to(root / 'original-built-package')
                with self.assertRaises(c.p.GateError):
                    c.delivery_bundle(directory, c.VERSION, c.SOURCE_SHA)

    def test_fresh_verifiers_inspect_delivered_name_and_propagate_failure(self):
        for platform, method, output in (('android', 'inspect_apk', 'apk_sha256'),
                                         ('windows', 'inspect_windows', 'installer_sha256')):
            for fail in (False, True):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    with self.package_context(root):
                        directory = self.make_bundle(root, platform)
                        directory.rename(root / 'incoming')
                        with patch.object(c.p, method, side_effect=c.p.GateError('unit rejection') if fail else None) as inspect, \
                                patch.object(c.p, 'output') as emit:
                            if fail:
                                with self.assertRaises(c.p.GateError): c.verify_package(platform)
                                emit.assert_not_called()
                            else:
                                c.verify_package(platform)
                                self.assertEqual(emit.call_args.args[0], output)
                            inspect.assert_called_once_with(root / 'incoming' / c.delivery_name(c.VERSION, platform), c.VERSION)

    def test_full_request_and_workflow_contract(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / c.REQUEST_PATH).read_text()), c.REQUEST)
        workflow = (root / '.github/workflows' / c.WORKFLOW).read_text()
        for value in (c.PARENT, c.MESSAGE, c.SOURCE_SHA, c.SOURCE_REF, c.VERSION,
                      'contents: read', 'actions: read', 'validate_source',
                      'needs: [prepare, validate-source]', 'verify_windows', 'if: always()'):
            self.assertIn(value, workflow)
        for forbidden in ('workflow_dispatch', 'RELEASE_WRITE_TOKEN', 'contents: write',
                          'cache: true', 'native-macos-server:', 'scripts/pipeline.py',
                          'scripts/current_source_check.py'):
            self.assertNotIn(forbidden, workflow)
        for platform in ('android', 'windows'):
            self.assertEqual(workflow.count('name: TEST-' + platform + '-v' + c.VERSION + '-' + c.SOURCE_SHA), 2)
        self.assertEqual(workflow.count('retention-days: 1'), 2)
        self.assertEqual(workflow.count('include-hidden-files: false'), 2)
        android_verify = workflow.split('  verify:\n')[1].split('  build-windows:\n')[0]
        windows_verify = workflow.split('  verify-windows:\n')[1]
        for verify in (android_verify, windows_verify):
            self.assertNotIn('secrets.', verify)
            self.assertNotIn('environment:', verify)
        self.assertEqual(workflow.count('needs: [prepare, validate-source]'), 2)

    def test_protected_pipeline_and_native_bytes_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        hashes = {
            'scripts/pipeline.py': 'ff731bbe84babf60b15346ec263a478972d2983fa6bdeac4cf1385ae24ff9e48',
            'scripts/current_source_check.py': 'adef0ecd3b00f8498a5325893cb7697e563c8f513bd3b4e6a073d414c8adbc88',
            'policy.json': 'c888adbea5463b4c5cdaa1ae025766c3b2f87c11dca2e007ab903c9d765cb017',
            '.github/workflows/android.yml': '4dbee3059faab00e11935d374035583e24c13553ded5059004569a95be8cdeef',
            'scripts/native_recovery_check_observation.py': '4e58d0e18482cb8bbcc993c10fecde23e257b194f7d9b9f6d2d5e8d793b7f490',
        }
        for path, digest in hashes.items():
            self.assertEqual(hashlib.sha256((root / path).read_bytes()).hexdigest(), digest, path)
        self.assertEqual(c.p.NATIVE_CONTRACT_TEST_COUNT, 104)
        helper = (root / 'scripts/handoff_final_packages.py').read_text()
        self.assertNotIn('import native_recovery_check_observation', helper)


class PackageSourceObservationTests(unittest.TestCase):
    def fixture(self):
        import test_source_validation as fixtures
        return fixtures

    def run_validation(self, stream=None, returncode=0, *, changed=False,
                       process_error=False, observer_error=False, cap_reason=None):
        import follow_recovery_check as observation
        fixtures = self.fixture()
        source = Path('/synthetic/owned-source')
        paths = set(fixtures.TEST_PATHS) | {fixtures.VENDOR_CHECK, 'pubspec.yaml', 'lib/private.dart'}
        raw = fixtures.report(fixtures.events() if stream is None else stream)
        calls = []
        environments = []
        originals = (c.p.quiet, c.p.source_fingerprint, c.p.validate_source,
                     c.p.flutter_test_summary, observation.inventory, observation.STAGE)
        def original_quiet(args, cwd=None, env=None):
            calls.append(tuple(args)); environments.append(dict(env or {}))
            return 'PRIVATE_SETUP_CONTENT'
        def process(args, **kwargs):
            calls.append(tuple(args)); environments.append(dict(kwargs['env']))
            self.assertEqual(kwargs['cwd'], source)
            self.assertEqual(set(kwargs), {'cwd', 'env', 'stdout', 'stderr', 'check'})
            self.assertIs(kwargs['stdout'], subprocess.PIPE)
            self.assertIs(kwargs['stderr'], subprocess.PIPE)
            self.assertIs(kwargs['check'], False)
            self.assertIs(c.p.validate_source, originals[2])
            if process_error:
                raise OSError('PRIVATE_LAUNCH_ERROR')
            if tuple(args) == observation.ANALYZE_COMMAND:
                return subprocess.CompletedProcess(args, 0, b'PRIVATE_ANALYSIS_NOTE', b'PRIVATE_ANALYSIS_STDERR')
            self.assertEqual(tuple(args), observation.FULL_TEST_COMMAND)
            return subprocess.CompletedProcess(args, returncode, raw.encode(), b'PRIVATE_TEST_STDERR')
        env = {name: 'PRIVATE_ENV_VALUE' for name in (
            'SOURCE_READ_TOKEN', 'GITHUB_TOKEN', 'RELEASE_WRITE_TOKEN',
            'ANDROID_KEYSTORE_BASE64', 'ANDROID_KEY_PASSWORD', 'ANDROID_KEY_ALIAS',
            'DEFAULT_SERVER_URL', 'GITHUB_OUTPUT', 'GITHUB_STEP_SUMMARY', 'GITHUB_ENV', 'GITHUB_PATH')}
        output = io.StringIO()
        with contextlib.ExitStack() as scope:
            scope.enter_context(patch.dict(os.environ, env, clear=True))
            scope.enter_context(patch.object(sys, 'argv', ['wrapper', 'validate_source']))
            scope.enter_context(patch.object(c.request, 'context'))
            scope.enter_context(patch.object(c.p, 'source_context', return_value=(source, c.VERSION, c.SOURCE_SHA, None)))
            fingerprint = scope.enter_context(patch.object(c.p, 'source_fingerprint', side_effect=[
                ('before', paths), ('changed' if changed else 'before', paths)]))
            scope.enter_context(patch.object(c.p, 'quiet', side_effect=original_quiet))
            scope.enter_context(patch.object(subprocess, 'run', side_effect=process))
            parser = scope.enter_context(patch.object(c.p, 'flutter_test_summary', wraps=originals[3]))
            old_inventory = scope.enter_context(patch.object(observation, 'inventory', side_effect=AssertionError('Historical inventory must not load')))
            if observer_error:
                scope.enter_context(patch.object(observation, 'full_test_observation', side_effect=RuntimeError('PRIVATE_OBSERVER_ERROR')))
            if cap_reason:
                scope.enter_context(patch.object(observation, 'observe_green', return_value={'reason': cap_reason, 'errors': []}))
            scope.enter_context(contextlib.redirect_stdout(output))
            scope.enter_context(contextlib.redirect_stderr(output))
            result = c.main()
            old_inventory.assert_not_called()
            fingerprint_count = fingerprint.call_count
            parser_calls = list(parser.call_args_list)
        self.assertEqual((c.p.quiet, c.p.source_fingerprint, c.p.validate_source,
                          c.p.flutter_test_summary, observation.inventory, observation.STAGE), originals)
        text = output.getvalue()
        for private in ('PRIVATE_', 'private test secret', 'private loader',
                        'private secret traceback path', str(source), *paths):
            self.assertNotIn(private, text)
        reports = [json.loads(line) for line in text.splitlines() if line.startswith('{')]
        return dict(result=result, calls=calls, environments=environments,
                    fingerprint_count=fingerprint_count, parser_calls=parser_calls,
                    reports=reports, text=text, raw=raw, paths=paths, source=source)

    def failed_stream(self):
        fixtures = self.fixture()
        stream = fixtures.events()
        test = next(e['test'] for e in stream if e['type'] == 'testStart' and e['test']['groupIDs'])
        suite = next(e['suite'] for e in stream if e['type'] == 'suite' and e['suite']['id'] == test['suiteID'])
        done = next(e for e in stream if e['type'] == 'testDone' and e['testID'] == test['id'])
        done['result'] = 'failure'
        stream.insert(-1, {'type': 'error', 'testID': test['id'], 'time': 1,
                          'isFailure': True,
                          'error': 'TestFailure: PRIVATE_CASE_TOKEN\nExpected: true\nActual: <false>',
                          'stackTrace': '/synthetic/owned-source/' + suite['path'] + ' 17:3 PRIVATE_STACK_TOKEN'})
        stream[-1]['success'] = False
        return stream, suite['path']

    def test_only_validate_source_uses_observation_context(self):
        for stage in c.request.STAGES:
            with patch.object(sys, 'argv', ['wrapper', stage]), \
                    patch.object(c.request, 'context'), patch.object(c, 'require_native_success'), \
                    patch.object(c.request, 'main', return_value=0) as original, \
                    patch.object(c, 'validate_source_observed', return_value=7) as observed:
                self.assertEqual(c.main(), 7 if stage == 'validate_source' else 0)
                if stage == 'validate_source':
                    observed.assert_called_once_with(); original.assert_not_called()
                else:
                    original.assert_called_once_with(); observed.assert_not_called()

    def test_complete_original_commands_counts_and_secret_free_environment(self):
        result = self.run_validation()
        fixtures = self.fixture()
        self.assertEqual(result['result'], 0)
        self.assertEqual(result['calls'], [
            ('flutter', 'pub', 'get'),
            ('dart', 'run', 'scripts/check_navigation_consistency.dart'),
            ('dart', 'run', 'build_runner', 'build', '--delete-conflicting-outputs'),
            (sys.executable, fixtures.VENDOR_CHECK),
            ('flutter', 'analyze', '--no-pub', '--fatal-infos', '--fatal-warnings'),
            ('flutter', 'test', '--no-pub', '--reporter=json'),
        ])
        self.assertEqual(result['fingerprint_count'], 2)
        self.assertEqual(len(result['parser_calls']), 1)
        self.assertEqual(result['parser_calls'][0].args[0], result['raw'])
        self.assertEqual(result['parser_calls'][0].args[2], fixtures.TEST_PATHS)
        self.assertTrue(all(not env for env in result['environments']))
        full = next(r for r in result['reports'] if r['stage'] == 'full-tests-observation')
        self.assertEqual(full['visibleTests'], 4)
        self.assertEqual(full['hiddenTests'], 4)
        self.assertEqual(full['completedTests'], 8)
        self.assertEqual(full['results'], {'success': 8, 'failure': 0, 'error': 0})
        self.assertIs(full['terminalSuccess'], True)
        self.assertIn('4 tests; 2 suites; 4 hidden lifecycle events; 0 skipped; 0 failed.', result['text'])

    def test_actual_failure_remains_failure_with_finite_counts_and_location(self):
        stream, name = self.failed_stream()
        result = self.run_validation(stream, 1)
        self.assertEqual(result['result'], 1)
        self.assertEqual(result['fingerprint_count'], 2)
        self.assertEqual(result['parser_calls'], [])
        full = next(r for r in result['reports'] if r['stage'] == 'full-tests-observation')
        self.assertEqual(full['exitCode'], 1)
        self.assertEqual(full['visibleTests'], 4)
        self.assertEqual(full['completedTests'], 8)
        self.assertEqual(full['results'], {'success': 7, 'failure': 1, 'error': 0})
        self.assertIs(full['terminalSuccess'], False)
        self.assertEqual(full['errors'][0]['fileOrdinal'], sorted(result['paths']).index(name) + 1)
        self.assertEqual(full['errors'][0]['locations'], [{'line': 17, 'column': 3}])
        self.assertEqual(full['errors'][0]['category'], 'TestFailure')
        self.assertEqual(full['errors'][0]['expected'], True)
        self.assertEqual(full['errors'][0]['actual'], False)
        self.assertNotIn('testOrdinal', full['errors'][0])

    def test_zero_diagnostic_failures_cannot_normalize_nonzero_exit(self):
        result = self.run_validation(returncode=1)
        full = next(r for r in result['reports'] if r['stage'] == 'full-tests-observation')
        self.assertEqual(full['results']['failure'], 0)
        self.assertIs(full['terminalSuccess'], True)
        self.assertEqual(result['result'], 1)
        self.assertEqual(result['fingerprint_count'], 2)
        self.assertEqual(result['parser_calls'], [])

    def test_success_exit_still_requires_original_strict_full_parser(self):
        fixtures = self.fixture()
        for mutation in ('missing-terminal', 'skip', 'hidden-failure', 'late-error', 'missing-suite'):
            stream = fixtures.events()
            if mutation == 'missing-terminal': stream.pop()
            elif mutation == 'skip': next(e for e in stream if e['type'] == 'testDone')['skipped'] = True
            elif mutation == 'hidden-failure': next(e for e in stream if e['type'] == 'testDone' and e['hidden'])['result'] = 'failure'
            elif mutation == 'late-error': stream.insert(-1, {'type': 'error', 'time': 1, 'error': 'PRIVATE_LATE_ERROR'})
            elif mutation == 'missing-suite': stream = [e for e in stream if e['type'] != 'suite']
            with self.subTest(mutation=mutation):
                result = self.run_validation(stream, 0)
                self.assertEqual(result['result'], 1)
                self.assertEqual(result['fingerprint_count'], 2)
                self.assertEqual(len(result['parser_calls']), 1)
                self.assertEqual(result['parser_calls'][0].args[0], result['raw'])

    def test_frozen_source_change_still_overrides_passing_report(self):
        result = self.run_validation(changed=True)
        self.assertEqual(result['result'], 1)
        self.assertEqual(result['fingerprint_count'], 2)
        self.assertEqual(len(result['parser_calls']), 1)
        self.assertIn('Frozen source fingerprint changed during validation.', result['text'])

    def test_diagnostic_caps_do_not_truncate_or_replace_acceptance_stream(self):
        for reason in ('output-limit', 'event-limit', 'invalid-output'):
            with self.subTest(reason=reason):
                result = self.run_validation(cap_reason=reason)
                self.assertEqual(result['result'], 0)
                self.assertEqual(result['parser_calls'][0].args[0], result['raw'])
                full = next(r for r in result['reports'] if r['stage'] == 'full-tests-observation')
                self.assertEqual(full['reason'], reason)
                self.assertEqual(full['errors'], [])

    def test_finite_error_location_and_scalar_caps_preserve_privacy(self):
        stream, name = self.failed_stream()
        error = next(e for e in stream if e['type'] == 'error')
        error['error'] = 'TestFailure: PRIVATE_CASE_TOKEN\nExpected: 1000001\nActual: 99999999999999999'
        error['stackTrace'] = '\n'.join('/synthetic/owned-source/' + name + f' {line}:3 PRIVATE_STACK_TOKEN' for line in range(1, 12))
        stream[-1:-1] = [copy.deepcopy(error) for _ in range(25)]
        result = self.run_validation(stream, 1)
        full = next(r for r in result['reports'] if r['stage'] == 'full-tests-observation')
        self.assertEqual(result['result'], 1)
        self.assertEqual(full['errorCount'], 26)
        self.assertEqual(len(full['errors']), 20)
        self.assertTrue(all(len(item.get('locations', [])) <= 5 for item in full['errors']))
        self.assertTrue(all('expected' not in item and 'actual' not in item for item in full['errors']))
        self.assertLess(len(json.dumps(full)), 20000)

    def test_observer_and_launch_exceptions_fail_closed_restore_and_recheck(self):
        for options in ({'process_error': True}, {'observer_error': True}):
            with self.subTest(options=options):
                result = self.run_validation(**options)
                self.assertEqual(result['result'], 1)
                self.assertEqual(result['fingerprint_count'], 2)
                self.assertEqual(result['parser_calls'], [])

    def test_pending_witness_blocks_before_observer_context(self):
        with patch.object(c, 'SECOND_WITNESS_ACCEPTED', False), \
                patch.object(sys, 'argv', ['wrapper', 'validate_source']), \
                patch.object(c, 'validate_source_observed') as observed, \
                patch.object(c.request, 'main') as main, patch.object(c.p, 'api') as api:
            self.assertEqual(c.main(), 1)
            observed.assert_not_called(); main.assert_not_called(); api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
