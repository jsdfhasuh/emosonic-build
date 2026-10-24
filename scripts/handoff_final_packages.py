"""Fixed dual-native-witness TEST packages. No publication or native execution."""
import base64
import json
import os
import shutil
import sys
from unittest.mock import patch

import current_source_check as request

p = request.p
PARENT = '185816dfbb86aa4966f51efc713cf7ba749918ea'
MESSAGE = 'test: diagnose bounded TEST package full validation 20261024'
WORKFLOW = 'handoff-final-packages.yml'
REQUEST_PATH = 'requests/handoff-final-packages-20261022.json'
SOURCE_REF = 'refs/heads/fix/follow-bounded-budget-20261024'
SOURCE_SHA = 'bfc1967a8eae65154bdd5e74491f99136dfc198d'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
AUXILIARY_SHA = '3e06d0a7faf99f3608a2d3734847e683f6d71d07'
AUXILIARY_REF = 'refs/heads/test/bounded-budget-observation-20261024'
VERSION = '1.0.10+27'
SOURCE_VALIDATION_RUN = 40062350211
SOURCE_VALIDATION_HEAD = '99eff9a11146fe47d3cec5611d5207919f749514'
SOURCE_VALIDATION_JOB = 120778419750
SOURCE_VALIDATION_WORKFLOW = 'follow-bounded-budget-green'
SOURCE_VALIDATION_REQUEST = 'requests/follow-bounded-budget-green-20261024.json'
NATIVE_WORKFLOW = 'handoff-follow-timing'
NATIVE_REQUEST = 'requests/handoff-follow-timing-20261022.json'
NATIVE_MODE = 'native-follow-timing-observation'
# Both fixed runs reached complete strict terminal success, including teardown.
# This acceptance is baked into reviewed code, never supplied by an environment.
SECOND_WITNESS_ACCEPTED = True
EVIDENCE = (
    (40080780672, '68a208eb5b6fd712c1459f313e6222b0e885da2d', 120833766576, 113),
    (40088297493, 'ebf18d6e90a9682deab0b14a3a0529a2e02157f2', 120855662181, 114),
)
NATIVE_STEPS = (
    'Validate native measurement boundaries',
    'Preflight actual HTTP media and strict registration before compilation',
    'Prove actual scoped stream attribution and admit disposable lab-only decoration',
    'Compile three sandboxed same-source native test clients',
    'Measure actual follower transfer and restoration',
    'Measure normal delayed and cancelled actual Handoff',
    'Verify native processes stopped and remove owned test bundles and server',
    'Remove private source and build diagnostics after verified native teardown',
)
SOURCE_VALIDATION_STEPS = (
    'Validate all 282 historical and bounded budget focused cases',
    'Validate complete source analysis, tests, provenance and byte integrity without user Secrets',
    'Remove private source and generated validation outputs',
)


def witness_descriptors():
    return [dict(run_id=run, builder_sha=head, native_job_id=job,
                 request_attempt=attempt) for run, head, job, attempt in EVIDENCE]


REQUEST = dict(source_repository=p.SOURCE, source_ref=SOURCE_REF,
               source_sha=SOURCE_SHA, server_sha=SERVER_SHA, version=VERSION,
               mode='native-proven-build-only', attempt=116,
               auxiliary_observer_sha=AUXILIARY_SHA,
               auxiliary_observer_ref=AUXILIARY_REF,
               source_validation_run_id=SOURCE_VALIDATION_RUN,
               native_witnesses=witness_descriptors(),
               native_witnesses_accepted=SECOND_WITNESS_ACCEPTED)


def require_witness_pins():
    """Fail before token access, API traffic, or source fetch while pending."""
    p.require(SECOND_WITNESS_ACCEPTED is True,
              'Second complete strict native witness has not been accepted.')
    p.require(type(EVIDENCE) is tuple and len(EVIDENCE) == 2
              and all(type(entry) is tuple and len(entry) == 4 for entry in EVIDENCE),
              'Exactly two fixed native witnesses are required.')
    for run, head, job, attempt in EVIDENCE:
        p.require(all(type(value) is int and value > 0 for value in (run, job, attempt)),
                  'Native witness pins are pending or invalid.')
        p.checked_sha(head)
    p.require(all(len({entry[index] for entry in EVIDENCE}) == 2 for index in range(4)),
              'Native witnesses must be distinct complete runs, jobs and requests.')
    for value in (PARENT, SOURCE_SHA, SERVER_SHA, AUXILIARY_SHA, SOURCE_VALIDATION_HEAD):
        p.checked_sha(value)
    p.require(all(type(value) is int and value > 0
                  for value in (SOURCE_VALIDATION_RUN, SOURCE_VALIDATION_JOB)),
              'Source validation pins are invalid.')


def source_declaration(mode, attempt):
    return dict(source_repository=p.SOURCE, source_ref=SOURCE_REF,
                source_sha=SOURCE_SHA, server_sha=SERVER_SHA, version=VERSION,
                mode=mode, attempt=attempt)


def native_declaration(attempt):
    return dict(source_declaration(NATIVE_MODE, attempt),
                proof_run_id=39745934922, validation_run_id=39767536382,
                ingress_validation_run_id=SOURCE_VALIDATION_RUN,
                auxiliary_observer_sha=AUXILIARY_SHA,
                auxiliary_observer_ref=AUXILIARY_REF)


def require_evidence(run_id, head, job_id, workflow, job_name, names,
                     declaration_path, expected_declaration, token):
    run = p.api(f'/repos/{p.BUILDER}/actions/runs/{run_id}', token)
    p.require(type(run) is dict and type(run.get('id')) is int and run['id'] == run_id
              and type(run.get('repository')) is dict
              and run['repository'].get('full_name') == p.BUILDER
              and run.get('head_sha') == head and run.get('head_branch') == 'main'
              and run.get('event') == 'push' and type(run.get('run_attempt')) is int
              and run['run_attempt'] == 1
              and run.get('path') == f'.github/workflows/{workflow}.yml'
              and run.get('status') == 'completed' and run.get('conclusion') == 'success',
              'Fixed evidence run must match and completely succeed.')
    jobs = p.api(f'/repos/{p.BUILDER}/actions/runs/{run_id}/jobs?per_page=100', token)
    p.require(type(jobs) is dict and type(jobs.get('total_count')) is int
              and 0 < jobs['total_count'] <= 100 and type(jobs.get('jobs')) is list
              and len(jobs['jobs']) == jobs['total_count'], 'Evidence jobs are incomplete.')
    matches = [job for job in jobs['jobs'] if type(job) is dict and job.get('name') == job_name]
    p.require(len(matches) == 1, 'Required evidence job is missing or duplicated.')
    job = matches[0]
    p.require(type(job.get('id')) is int and job['id'] == job_id
              and job.get('run_id') == run_id and job.get('head_sha') == head
              and job.get('status') == 'completed' and job.get('conclusion') == 'success'
              and type(job.get('steps')) is list, 'Evidence job identity or result mismatch.')
    for name in names:
        steps = [step for step in job['steps'] if type(step) is dict and step.get('name') == name]
        p.require(len(steps) == 1 and steps[0].get('status') == 'completed'
                  and steps[0].get('conclusion') == 'success',
                  'Every strict evidence and cleanup step must uniquely succeed.')
    blob = p.api(f'/repos/{p.BUILDER}/contents/{declaration_path}?ref={head}', token)
    p.require(type(blob) is dict and blob.get('encoding') == 'base64'
              and blob.get('path') == declaration_path and blob.get('type') == 'file'
              and type(blob.get('content')) is str and len(blob['content']) < 8192,
              'Immutable evidence declaration is unavailable.')
    declaration = json.loads(base64.b64decode(''.join(blob['content'].split()), validate=True))
    p.require(declaration == expected_declaration, 'Evidence source, observer or version mismatch.')


def require_native_success():
    require_witness_pins()
    p.require_secrets(['GITHUB_TOKEN'])
    token = os.environ['GITHUB_TOKEN']
    require_evidence(SOURCE_VALIDATION_RUN, SOURCE_VALIDATION_HEAD, SOURCE_VALIDATION_JOB,
                     SOURCE_VALIDATION_WORKFLOW, 'validate-source', SOURCE_VALIDATION_STEPS,
                     SOURCE_VALIDATION_REQUEST,
                     source_declaration('follow-bounded-budget-full-green-validation', 112), token)
    for run, head, job, attempt in EVIDENCE:
        require_evidence(run, head, job, NATIVE_WORKFLOW, 'native-macos-server',
                         NATIVE_STEPS, NATIVE_REQUEST, native_declaration(attempt), token)


def delivery_name(candidate, platform):
    p.require(candidate == VERSION and platform in ('android', 'windows'),
              'Unexpected TEST package version or platform.')
    suffix = '.apk' if platform == 'android' else '-setup.exe'
    return f'EmoSonic-TEST-{platform}-v{candidate}-{SOURCE_SHA}{suffix}'


_source_prepare = request.prepare
_candidate_metadata = request.candidate_metadata
_bundle = p.bundle


def prepare():
    # Reuse the existing branch/version check, adapting only delivery outputs.
    emit = p.output
    def named_output(name, value):
        if name == 'apk_name':
            value = delivery_name(VERSION, 'android')
        elif name == 'installer_name':
            value = delivery_name(VERSION, 'windows')
        emit(name, value)
    with patch.object(p, 'output', named_output):
        _source_prepare()


def package_metadata(candidate, sha, digest, platform='android'):
    p.require(candidate == VERSION and sha == SOURCE_SHA, 'TEST provenance source mismatch.')
    data = _candidate_metadata(candidate, sha, digest, platform)
    data.update(package_kind='TEST', package_filename=delivery_name(candidate, platform),
                test_evidence={
                    'native_witnesses': witness_descriptors(),
                    'native_workflow': NATIVE_WORKFLOW + '.yml',
                    'source_validation': {
                        'run_id': SOURCE_VALIDATION_RUN, 'builder_sha': SOURCE_VALIDATION_HEAD,
                        'job_id': SOURCE_VALIDATION_JOB,
                        'workflow': SOURCE_VALIDATION_WORKFLOW + '.yml',
                        'focused_cases': 282, 'focused_suites': 37,
                        'full_tests': 3068, 'analysis_findings': 0,
                    },
                    'isolated_test_server_sha': SERVER_SHA,
                    'server_scope': 'Native test evidence only, not the package runtime endpoint.',
                    'auxiliary_observer_sha': AUXILIARY_SHA,
                    'auxiliary_observer_ref': AUXILIARY_REF,
                })
    return data


def delivery_bundle(directory, candidate, sha, platform='android'):
    # Never change installer_name: the original Windows build output and embedded
    # Inno OutputBaseFilename must retain their original identity checks.
    with patch.object(p, 'package_name', delivery_name):
        return _bundle(directory, candidate, sha, platform)


def stage_package(path, candidate, sha, platform):
    dist = p.ROOT / 'dist'
    dist.mkdir(mode=0o700)
    destination = dist / delivery_name(candidate, platform)
    p.require(path.is_file() and not path.is_symlink(), 'Invalid built TEST package.')
    shutil.copyfile(path, destination)
    digest = p.file_digest(destination)
    (dist / (destination.name + '.sha256')).write_text(
        digest + '  ' + destination.name + '\n', encoding='ascii', newline='\n')
    (dist / (platform + '-manifest.json')).write_text(
        json.dumps(p.metadata(candidate, sha, digest, platform), indent=2) + '\n',
        encoding='utf-8', newline='\n')
    delivery_bundle(dist, candidate, sha, platform)


def verify_package(platform):
    candidate, sha = os.environ['BUILD_VERSION'], p.checked_sha(os.environ['SOURCE_SHA'])
    directory = p.ROOT / 'incoming'
    digest = delivery_bundle(directory, candidate, sha, platform)
    package = directory / delivery_name(candidate, platform)
    if platform == 'android':
        p.inspect_apk(package, candidate)
        p.output('apk_sha256', digest)
        print('Independent TEST APK signature, identity, version, ABI and provenance passed.')
    else:
        p.inspect_windows(package, candidate)
        p.output('installer_sha256', digest)
        print('Independent TEST Windows identity, version, x64, NotSigned and provenance passed.')


def verify():
    verify_package('android')


def verify_windows():
    verify_package('windows')


def validate_source_observed():
    # Reuse only the existing finite observation context, not any historical
    # green entrypoint or pin chain. Empty inventory removes name annotations;
    # the original pipeline still discovers, runs and strictly verifies ALL tests.
    import follow_recovery_check as source_validation
    with patch.object(source_validation, 'inventory', return_value=[]), \
            patch.object(source_validation, 'STAGE', source_validation.STAGE):
        return source_validation.validate_full()


def main():
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in request.STAGES:
            raise p.GateError('Only fixed TEST build-only stages are allowed.')
        # Cleanup remains available after a failure; every productive stage fails
        # closed while pins are pending, including direct fetch/tool invocations.
        if sys.argv[1] != 'cleanup':
            require_witness_pins()
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, VERSION=VERSION,
                            SOURCE_REF=SOURCE_REF, SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA,
                            prepare=prepare, candidate_metadata=package_metadata), \
                patch.multiple(p, stage_package=stage_package, verify=verify,
                               verify_windows=verify_windows):
            if sys.argv[1] == 'prepare':
                request.context()
                require_native_success()
            if sys.argv[1] == 'validate_source':
                return validate_source_observed()
            return request.main()
    except Exception:
        print('ERROR: Fixed TEST package validation failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
