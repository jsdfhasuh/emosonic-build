"""Run the approved disposable macOS lab, never production or release artifacts."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import current_source_check as request
import pipeline as p

OLD_SERVER = 'bcbb99e935fb4eb0799ab40fff893303cf2966df'
STAGES = ('prepare', 'dependencies', 'unit', 'preflight', 'build', 'handoff', 'follow', 'cleanup')


# Finite public report vocabulary. Unknown keys and strings are never echoed.
PUBLIC_STAGES = frozenset({
    'server-startup', 'server-probe', 'server-fixture-initialized',
    'real-server-and-media-ready', 'server-preflight-only', 'real-server-preflight',
    'private-fixture-cleanup', 'sandbox-preferences-and-private-fixture-cleanup',
    'native-mac-app-matrix', 'mac-app-orchestration', 'mac-app-build',
    'isolated-sandboxed-test-bundles', 'resolve-read-only-native-instrumentation',
    'resolve-official-dependencies', 'generate-code', 'analyze-mac-lab-entrypoint', 'build-authority', 'build-target',
    'build-follower', 'real-apps-isolated-and-registered', 'native-follow-aligned',
    'handoff-native-completion', 'follower-beyond-30-second-window',
    'follow-explicit-rate-change-applied', 'follow-original-paused-task-and-speed-restored',
    'native-handoff-and-pause', 'follow-restoration-and-native-pause',
    'extended-cold-target-ready', 'extended-real-delayed-handoff',
    'extended-cancel-rejects-late-playback', 'failed-preflight-loopback-observations',
    'server-runtime-failure-observation', 'handoff-A-to-B',
    'handoff-server-observation-capability', 'handoff-server-canonical-consistency',
    'handoff-canonical-consistency',
}) | frozenset(base + suffix for base in (
    'source-avplayer-rate-1.5', 'target-avplayer-rate-1.5', 'follower-avplayer-rate-1.5',
    'authority-after-follow-rate-change', 'follower-after-follow-rate-change')
    for suffix in ('', ':post-seek-native-readiness', ':native-advancement-readiness',
                   ':native-follow-alignment'))
PUBLIC_STATUSES = frozenset({'passed', 'failed', 'not-verified', 'unavailable'})
PUBLIC_ERRORS = frozenset({'AssertionError', 'TimeoutError', 'BridgeCommandFailure',
    'HTTPError', 'URLError', 'RuntimeError', 'ConnectionError', 'KeyError',
    'TypeError', 'ValueError', 'OSError', 'FileNotFoundError', 'CalledProcessError'})
PUBLIC_METRICS = frozenset({
    'count', 'exitCode', 'positionMs', 'measuredRate', 'nativeRate', 'elapsedSeconds',
    'nativeSamples', 'waitDurationMs', 'alignedDriftMs', 'readUncertaintyMs',
    'consecutiveAlignedSamples', 'nativePositionMs', 'totalReadinessMs',
    'authorityNativeRate', 'followerNativeRate', 'continuityErrorMs',
    'maximumAlignedDriftMs', 'originalRequestedRate', 'targetDelaySeconds',
    'observationSeconds', 'sourceMeasuredRate', 'freshActualGeneration',
    'currentHandoffConfirmed', 'delayedMediaResponseConfirmed',
    'appMatrixExecuted', 'physicalAudibilityVerified',
})


# Reviewed, path-specific diagnostic schemas; no identifiers or free text.
HANDOFF_STATES = frozenset(['cancelled', 'committing', 'completed', 'failed', 'preparing', 'ready', 'starting', 'timedOut'])
HANDOFF_ERROR_CODES = frozenset(['commit_cancelled', 'commit_failed', 'commit_timeout', 'context_closed', 'dependency_failed', 'execution_unknown', 'invalid_handoff_prepare', 'missing_source_client', 'prepare_failed', 'prepare_timeout', 'server_restart', 'source_changed', 'start_failed', 'start_timeout'])
PROTOCOL_CODES = frozenset(['authority_offline', 'bad_request', 'capability_required', 'client_sequence_conflict', 'conflict', 'context_closed', 'forbidden', 'internal_error', 'not_found', 'not_supported', 'queue_required', 'rate_limited', 'restore_in_progress', 'stale_version', 'unauthorized'])
CONNECTION_STATES = frozenset(['authenticated', 'disconnected', 'ready', 'registered', 'socketConnected'])
LAB_STATES = frozenset(['active', 'disabled', 'failed', 'negotiating', 'probing'])
FAILURE_REASONS = frozenset(['authority_device_unavailable', 'authority_socket_unavailable', 'clock_gate_incomplete', 'commit_effective_at_missing', 'commit_position_at_or_beyond_duration', 'commit_position_missing', 'commit_received_too_late', 'complete_before_effective_at', 'complete_control_version_conflict', 'complete_device_mismatch', 'complete_duration_invalid', 'complete_not_playing', 'complete_position_conflict', 'complete_queue_index_conflict', 'complete_rate_conflict', 'complete_sample_in_future', 'complete_sample_late', 'complete_sample_stale', 'complete_track_conflict', 'control_version_conflict', 'controller_role_required', 'duration_bounds_mismatch', 'effective_at_capability_required', 'execution_before_effective_at', 'execution_too_late', 'handoff_already_in_progress', 'handoff_execution_before_effective_at', 'handoff_execution_too_late', 'handoff_position_at_or_beyond_duration', 'handoff_start_ack_timeout', 'invalid_actual_position', 'playback_not_playing', 'playback_rate_mismatch', 'playing_source_sample_stale', 'position_projection_mismatch', 'position_sample_in_future', 'position_sample_stale', 'prepare_enqueue_failed', 'provisional_control_version_mismatch', 'queue_index_mismatch', 'requester_generation_changed', 'scheduled_commit_cancelled', 'source_control_not_settled', 'source_device_state_incomplete', 'source_device_state_missing', 'source_not_playing', 'source_sample_in_future', 'source_sample_stale', 'source_state_not_authoritative', 'source_state_wrong_epoch', 'source_state_wrong_pair', 'source_track_mismatch', 'start_ack_control_mismatch', 'target_capability_required', 'target_client_offline', 'target_generation_changed', 'target_generation_offline', 'track_id_mismatch', 'unrecognized'])

ROLES = frozenset({'authority', 'target', 'follower'})
NUMBER = ('number', -1_000_000_000_000, 1_000_000_000_000)
COUNTER = ('integer', 0, 1_000_000_000_000)
NATIVE_SCHEMA = {
    **{key: ('number', 0, 1_000_000_000_000) for key in
       ('positionMs', 'durationMs', 'sampleUncertaintyMs')},
    **{key: ('number', 0, 100) for key in ('playbackRate', 'requestedRate')},
    'playbackState': ('integer', 0, 4),
    **{key: ('integer', 0, 2) for key in
       ('avPlayerStatus', 'avItemStatus', 'avTimeControlStatus')},
}
HANDOFF_SCHEMA = {
    'role': frozenset({'source', 'target', 'unrecognized'}),
    'status': HANDOFF_STATES | {'unrecognized'},
    'errorCode': HANDOFF_ERROR_CODES | PROTOCOL_CODES | {'unrecognized'},
    'protocolErrorCode': PROTOCOL_CODES,
    'knownFailureReason': FAILURE_REASONS,
    'exceptionCategory': frozenset({'TimeoutException', 'StateError'}),
    **{key: bool for key in ('present', 'contextMatches', 'sourceMatchesExpected',
       'targetPairMatchesExpected', 'prepared', 'provisionalCommitAccepted',
       'provisionalPlaybackStarted', 'releaseHandled')},
    'controlVersion': COUNTER, 'canonicalControlVersion': COUNTER,
}
CLIENT_SCHEMA = {
    'role': ROLES,
    'connection': CONNECTION_STATES | {'unrecognized'},
    'labStatus': LAB_STATES | {'unrecognized'},
    'bindingRole': frozenset({'localAuthority', 'handoffTarget', 'follower',
                             'broadcastParticipant', 'unrecognized'}),
    'bindingPhase': frozenset({'provisional', 'reconciling', 'confirmed', 'unrecognized'}),
    **{key: bool for key in ('actualIdentityPresent', 'identitySeedMatches',
       'bindingContextMatches', 'currentContextMatches', 'canonicalContextPresent',
       'canonicalAuthorityIsSource', 'canonicalAuthorityIsTarget', 'canonicalTrackMatches',
       'trackMatches', 'queueMatches', 'indexMatches', 'nativeEvidenceValid',
       'nativePlaying', 'nativeStopped', 'queueAndContextControlAgree')},
    **{key: COUNTER for key in ('controlVersion', 'queueControlVersion',
       'canonicalAppliedControlVersion', 'observedOwnAppliedControlVersion',
       'localExecutionControlVersion')},
    'nativePlayerCount': ('integer', 0, 100),
    'native': ('list', NATIVE_SCHEMA, 2),
    'handoff': HANDOFF_SCHEMA,
    'handoffHistory': ('list', HANDOFF_SCHEMA, 8),
}
DIAGNOSTIC_SCHEMA = {
    'handoffDiagnostics': ('list', CLIENT_SCHEMA, 3),
    'handoffBeforeStart': ('list', CLIENT_SCHEMA, 3),
    'nativeErrors': ('list', {
        'role': ROLES,
        'nativeErrorDomain': frozenset({'AVFoundationErrorDomain', 'NSURLErrorDomain',
            'NSOSStatusErrorDomain', 'CoreMediaErrorDomain', 'NSCocoaErrorDomain',
            'other-native-domain'}),
        'nativeErrorCode': ('integer', -2147483648, 2147483647),
    }, 3),
    'nativePlayback': ('list', {
        'clientOrdinal': ('integer', 0, 2),
        'trackMatchesFirstClient': bool, 'queueMatchesFirstClient': bool,
        'native': ('list', NATIVE_SCHEMA, 2),
    }, 3),
}


PLAYBACK_STATES = frozenset({'idle', 'playing', 'paused', 'stopped', 'buffering',
                            'loading', 'unrecognized'})
CANONICAL_SCHEMA = {
    'state': PLAYBACK_STATES, 'queueState': PLAYBACK_STATES,
    **{key: bool for key in ('trackPresent', 'trackMatchesBaseline', 'queuePresent',
       'queueIndexValid', 'queueMatchesBaseline', 'queueIndexMatchesBaseline',
       'queueTrackPresent', 'queueTrackMatchesCurrentSong',
       'canonicalTrackMatchesQueueCurrentSong', 'authorityIsSource', 'authorityIsTarget')},
    **{key: COUNTER for key in ('trackFixtureIndex', 'queueLength', 'queueCurrentIndex',
       'queueCurrentSongFixtureIndex', 'queueTrackFixtureIndex', 'controlVersion',
       'appliedControlVersion', 'version', 'epoch', 'queueControlVersion',
       'queueRevision', 'queueVersion', 'queueEpoch')},
    'positionMs': NUMBER, 'queuePositionMs': NUMBER, 'playbackRate': ('number', 0, 100),
}
CLIENT_SCHEMA['canonicalStateAndQueue'] = CANONICAL_SCHEMA
DIAGNOSTIC_SCHEMA['serverCanonicalObservation'] = {
    'status': frozenset({'read_only_snapshot', 'refused_unowned_fixture',
        'refused_database_scope', 'context_absent', 'observation_unavailable'}),
    'errorType': frozenset({'OperationalError', 'DatabaseError', 'ValueError',
        'JSONDecodeError', 'KeyError', 'TypeError', 'OSError', 'FileNotFoundError', 'OtherError'}),
    'currentCanonical': CANONICAL_SCHEMA, 'cachedCanonicalPayload': CANONICAL_SCHEMA,
    'devices': ('list', {
        'role': frozenset({'authority', 'target'}), 'state': PLAYBACK_STATES,
        **{key: bool for key in ('present', 'generationMatches', 'isAuthority',
                                'trackPresent', 'trackMatchesBaseline')},
        **{key: COUNTER for key in ('trackFixtureIndex', 'appliedControlVersion', 'epoch')},
        'positionMs': NUMBER, 'playbackRate': ('number', 0, 100),
    }, 2),
    'handoff': {
        'status': HANDOFF_STATES | {'timeout', 'committed', 'timed_out', 'canceled',
                                    'aborted', 'superseded', 'unrecognized'},
        **{key: COUNTER for key in ('baseControlVersion', 'provisionalControlVersion', 'epoch')},
        'completionCanonicalPresent': bool, 'completionCanonical': CANONICAL_SCHEMA,
        'completionProof': {
            'trackPresent': bool, 'trackMatchesBaseline': bool,
            **{key: COUNTER for key in ('trackFixtureIndex', 'queueIndex', 'appliedControlVersion')},
            'positionMs': NUMBER, 'playbackRate': ('number', 0, 100),
        },
    },
}


def diagnostic_value(value, schema):
    if schema is bool:
        return value if type(value) is bool else None
    if isinstance(schema, frozenset):
        return value if type(value) is str and value in schema else None
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            return None
        result = {}
        for key, field_schema in schema.items():
            if key in value:
                clean = diagnostic_value(value[key], field_schema)
                if clean is not None:
                    result[key] = clean
        return result or None
    if schema[0] == 'list':
        if not isinstance(value, list):
            return None
        result = [diagnostic_value(item, schema[1]) for item in value[:schema[2]]]
        return [item for item in result if item is not None]
    if schema[0] in ('number', 'integer'):
        accepted = (int,) if schema[0] == 'integer' else (int, float)
        if type(value) in accepted and schema[1] <= value <= schema[2]:
            return value
    return None


def report_line(line):
    try:
        data = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    result = {key: value for key, value in data.items()
              if key in PUBLIC_METRICS and type(value) in (bool, int, float)
              and (type(value) is bool or -1_000_000_000_000 <= value <= 1_000_000_000_000)}
    for key, allowed in (('stage', PUBLIC_STAGES), ('status', PUBLIC_STATUSES),
                         ('errorType', PUBLIC_ERRORS)):
        if isinstance(data.get(key), str) and data[key] in allowed:
            result[key] = data[key]
    result.update(diagnostic_value(data, DIAGNOSTIC_SCHEMA) or {})
    return result if result else None


def native_env():
    env = p.build_env()
    for name in ('GITHUB_ENV', 'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY'):
        env.pop(name, None)
    return env


def output_path():
    # Identities are validated by request.context before this helper is called.
    base = Path(os.environ['RUNNER_TEMP'])
    p.require(base.is_absolute() and base.is_dir(), 'Invalid runner temporary root.')
    output = base / ('emosonic-current-native-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'])
    p.require(not output.is_symlink() and output.resolve().parent == base.resolve(),
              'Unsafe native output path.')
    return output


def cleanup():
    output = output_path()
    server = p.ROOT / '.native-server'
    p.require(not server.is_symlink() and server.resolve().parent == p.ROOT.resolve(),
              'Unsafe native server cleanup path.')
    # Never signal guessed PIDs. Refuse deletion if process inspection fails or
    # any command still references this job's source, bundles, or server tree.
    scan = subprocess.run(['ps', '-ww', '-axo', 'pid=,command='], capture_output=True,
                          text=True, env=native_env())
    p.require(scan.returncode == 0 and bool(scan.stdout.strip()),
              'Native process cleanup could not be verified; no files removed.')
    roots = (str(output.resolve()), str(server.resolve()), str((p.ROOT / 'source').resolve()))
    for line in scan.stdout.splitlines():
        parts = line.strip().split(None, 1)
        p.require(len(parts) == 2 and parts[0].isdigit(), 'Native process inspection was incomplete.')
        if int(parts[0]) != os.getpid() and any(root in parts[1] for root in roots):
            raise p.GateError('Native processes may remain; cleanup is not verified and no files removed.')
    for directory in (output, server):
        if directory.exists():
            p.require(directory.is_dir(), 'Unexpected native cleanup target.')
            shutil.rmtree(directory)
    print('Owned native output and isolated server directories removed after process inspection; no processes were signalled.')


def execute(command, label, report=False):
    source = p.ROOT / 'source'
    log = source / '.native-builder-private.log'
    with log.open('wb') as out:
        result = subprocess.run(command, cwd=source, env=native_env(), stdout=out, stderr=subprocess.STDOUT)
    if report:
        # No raw source, compiler strings, URLs, identities, credentials or traces.
        for line in log.read_text(errors='replace').splitlines():
            safe = report_line(line)
            if safe:
                print(json.dumps(safe), flush=True)
    print(json.dumps({'stage': label, 'status': 'passed' if result.returncode == 0 else 'failed', 'exitCode': result.returncode}), flush=True)
    p.require(result.returncode == 0, 'Native stage failed; private output is not uploaded.')


def main():
    try:
        p.require(len(sys.argv) == 2 and sys.argv[1] in STAGES, 'Invalid native stage.')
        request.context()
        p.require(sys.platform == 'darwin', 'A genuine macOS runner is required.')
        p.require(os.environ.get('EMOSONIC_MAC_LAB_NETWORK_APPROVED') == '1', 'Test-network approval missing.')
        if sys.argv[1] == 'cleanup':
            cleanup()
            return 0
        source = p.ROOT / 'source'
        server = p.ROOT / '.native-server'
        p.require(p.quiet(['git', 'rev-parse', 'HEAD'], source).strip() == request.SOURCE_SHA, 'Wrong client source.')
        p.require(p.quiet(['git', 'rev-parse', 'HEAD'], server).strip() == request.SERVER_SHA, 'Wrong server source.')
        runner = source / 'tool/native_playback_mac/run_lab.py'
        stage = sys.argv[1]
        if stage == 'prepare':
            data = runner.read_text()
            p.require(data.count(OLD_SERVER) == 1 and request.SERVER_SHA not in data, 'Unexpected native server-pin input.')
            runner.write_text(data.replace(OLD_SERVER, request.SERVER_SHA))
            print('Only the disposable lab server revision guard was updated; production client/server code is unchanged.')
        elif stage == 'dependencies':
            execute([sys.executable, '-m', 'pip', 'install', '-r', str(server / 'requirements.txt'), 'websocket-client'], 'server-dependencies')
        elif stage == 'unit':
            execute([sys.executable, '-m', 'unittest', 'discover', '-s', 'tool/native_playback_mac', '-p', 'test_*.py'], 'native-measurement-guards')
        elif stage == 'preflight':
            execute([sys.executable, str(runner), '--server-repo', str(server), '--server-preflight'], 'isolated-current-server-preflight', True)
        else:
            output = output_path()
            if stage == 'build':
                # Verify the official SDK revision before any test app compilation.
                p.source_context(require_server=False)
                execute(['flutter', 'test', '--reporter', 'expanded', 'test/services/native_lab_control_admission_test.dart'], 'native-control-admission')
                execute([sys.executable, 'tool/native_playback_mac/prepare_build.py', '--output', str(output), '--run-id', os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'], '--allow-test-network-entitlements', '--with-follower'], 'native-test-bundle-build', True)
                manifest = json.loads((output / 'bundles.json').read_text())
                p.require([b['instance'] for b in manifest['bundles']] == ['authority', 'target', 'follower'], 'Wrong native bundle identities.')
                manifest['bundles'] = manifest['bundles'][:2]
                (output / 'two-client-bundles.json').write_text(json.dumps(manifest))
            else:
                args = [sys.executable, str(runner), '--server-repo', str(server), '--bundles', str(output / ('two-client-bundles.json' if stage == 'handoff' else 'bundles.json'))]
                if stage == 'handoff':
                    args.append('--extended-handoff')
                execute(args, 'native-' + stage + '-matrix', True)
    except p.GateError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    except Exception:
        print('ERROR: Native lab failed; sensitive details suppressed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
