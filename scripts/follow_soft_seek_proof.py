"""One fixed component expected-red proof; no native, package or release claim."""
from functools import partial
import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

import follow_ingress_proof as red
from follow_ingress_proof import strict_json, bounded_run, bounded_quiet
from current_native_check import native_env
from fixed_flutter_green import GreenVerificationError, observe_green
from follow_recovery_check import owned_file

request = red.request
PARENT = '80a776c1cc1969dac2400f7aa4b6632d7b04841f'
MESSAGE = 'test: prove exact soft-seek captured target 20261022'
WORKFLOW = 'follow-soft-seek-proof.yml'
REQUEST_PATH = 'requests/follow-soft-seek-proof-20261022.json'
SOURCE_REF = 'refs/heads/test/follow-soft-seek-dispatch-20261022'
SOURCE_SHA = '9abf18305c58d832879e88ff32b2352b9ef7f50e'
BASELINE_SHA = 'e6f7ea84d8ce9a1a29e56f5a083173a9810e4316'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
INVENTORY_PATH = 'tool/follow_soft_seek_dispatch/test_inventory.json'
INVENTORY_SHA256 = '93ba9635de7c81893d40505bbc22a045976c977bb324991ed553e9967dcaafe6'
ASSERTION_MARKER = 'FOLLOW_SOFT_SEEK_CAPTURED_TARGET_SURVIVED_ACTOR_WAIT'
EXPECTED_COUNT = 2
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-soft-seek-expected-red-proof', attempt=43)
STAGE = 'entry'


def inventory(source):
    p = request.p
    path = owned_file(source, INVENTORY_PATH)
    p.require(path.stat().st_size <= 65536, 'Private inventory size invalid.')
    raw = path.read_bytes()
    p.require(hashlib.sha256(raw).hexdigest() == INVENTORY_SHA256,
              'Private inventory changed.')
    value = strict_json(raw)
    p.require(type(value) is dict and set(value) == {'suites'}
              and type(value['suites']) is list and len(value['suites']) == 1,
              'Private suite inventory invalid.')
    suite = value['suites'][0]
    p.require(type(suite) is dict and set(suite) == {'path', 'sha256', 'names', 'causalOrdinal'},
              'Private suite schema invalid.')
    p.require(type(suite['path']) is str and re.fullmatch(
        r'test/services/[a-z0-9_]+_test\.dart', suite['path']), 'Private fixture path invalid.')
    p.require(type(suite['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', suite['sha256']),
              'Private fixture digest invalid.')
    fixture = owned_file(source, suite['path'])
    p.require(fixture.stat().st_size <= 2 * 1024 * 1024
              and hashlib.sha256(fixture.read_bytes()).hexdigest() == suite['sha256'],
              'Frozen fixture changed.')
    names = suite['names']
    p.require(type(names) is list and len(names) == EXPECTED_COUNT
              and all(type(name) is str and 0 < len(name) <= 8192 for name in names)
              and len(set(names)) == EXPECTED_COUNT and type(suite['causalOrdinal']) is int
              and 1 <= suite['causalOrdinal'] <= EXPECTED_COUNT, 'Private visible inventory invalid.')
    return suite



def prove():
    global STAGE
    p = request.p
    STAGE = 'source-context'
    source, _, sha, _ = p.source_context(require_server=False)
    env = native_env()
    STAGE = 'initial-fingerprint'
    before = p.source_fingerprint(source, sha, env)
    try:
        STAGE = 'inventory'
        p.require(type(EXPECTED_COUNT) is int and 2 <= EXPECTED_COUNT <= 128,
                  'Reviewed component count required.')
        suite = inventory(source)
        STAGE = 'codegen'
        with patch.object(p, 'quiet', partial(bounded_quiet, suite=suite)):
            p.codegen(source, env)
        STAGE = 'flutter-test'
        result, reason = bounded_run(['flutter', 'test', '--no-pub', '--reporter=json', suite['path']],
                                     cwd=source, env=env)
        basename = Path(suite['path']).name
        observation = observe_green(result.stdout, result.returncode, expected_names=suite['names'],
                                    fixture_basename=basename, stderr=result.stderr)
        if reason:
            observation['captureFailure'] = reason
        print(json.dumps(observation), flush=True)
        p.require(reason is None, 'Bounded Flutter capture did not complete.')
        STAGE = 'expected-red-verification'
        report = red.exact_red(result.stdout, result.returncode, names=suite['names'], basename=basename,
                               causal_ordinal=suite['causalOrdinal'], stderr=result.stderr,
                               expected_count=EXPECTED_COUNT, assertion_marker=ASSERTION_MARKER)
        report['stage'] = 'follow-soft-seek-red'
    finally:
        old_stage = STAGE
        STAGE = 'final-fingerprint'
        p.require(p.source_fingerprint(source, sha, env) == before, 'Frozen source bytes changed.')
        STAGE = old_stage
    print(json.dumps(report), flush=True)


def main():
    global STAGE
    STAGE = 'entry'
    try:
        p = request.p
        p.require(len(sys.argv) == 3 and sys.argv[1] == 'source'
                  and sys.argv[2] in ('prepare', 'fetch', 'red', 'cleanup'),
                  'Only fixed soft-seek proof stages are allowed.')
        stage = sys.argv[2]
        STAGE = stage
        p.checked_sha(SOURCE_SHA)
        p.checked_sha(BASELINE_SHA)
        p.require(SOURCE_SHA != BASELINE_SHA and SOURCE_REF.startswith('refs/heads/test/'),
                  'Reviewed unchanged-algorithm baseline required.')
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                            SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA), patch.object(p, 'quiet', bounded_quiet):
            request.context()
            if stage == 'red':
                prove()
            else:
                request.run(stage)
        return 0
    except GreenVerificationError as exc:
        report = dict(exc.report, stage='follow-soft-seek-red')
        print(json.dumps(report), flush=True)
    except Exception as exc:
        category = type(exc).__name__
        known = ('GateError', 'TimeoutExpired', 'ValueError', 'TypeError', 'KeyError',
                 'JSONDecodeError', 'OSError', 'FileNotFoundError', 'PermissionError')
        print(json.dumps(dict(stage='follow-soft-seek-proof-failure', failedStage=STAGE,
                              commandStage=red.STAGE if STAGE == 'codegen' else None,
                              category=category if category in known else 'other')), flush=True)
    return 1


if __name__ == '__main__':
    sys.exit(main())
