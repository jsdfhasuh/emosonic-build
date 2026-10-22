"""One fixed 101-case/full-source green gate; historical expected-red is untouched."""
import hashlib
import json
import re
import sys
from unittest.mock import patch

import follow_ingress_proof as ingress
import follow_recovery_check as recovery

PARENT = 'c794d1609a23a28658cbb74027aa79589d797103'
MESSAGE = 'test: validate lifecycle-compatible ingress repair 20261022'
WORKFLOW = 'follow-ingress-green.yml'
REQUEST_PATH = 'requests/follow-ingress-green-20261022.json'
SOURCE_REF = 'refs/heads/test/follow-lifecycle-dispatch-capability-20261022'
SOURCE_SHA = 'e6f7ea84d8ce9a1a29e56f5a083173a9810e4316'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
RECOVERY_INVENTORY_SHA256 = '2c882b974b4a49478ca9d5df5cb9aff094a309a7e8f1e42a1fd20403f841c69b'
INGRESS_INVENTORY_SHA256 = 'fde163ba2e25f529e2ef152523ba5f8df31ff7b1718a3e7398800bb89cfae71e'
REQUEST = dict(recovery.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               server_sha=SERVER_SHA, mode='follow-ingress-full-green-validation', attempt=36)
RECOVERY_INVENTORY = recovery.inventory
ORIGINAL_OBSERVER = recovery.observe_green
ORIGINAL_FULL_OBSERVER = recovery.full_test_observation
LIFECYCLE_INVENTORY_PATH = "tool/follow_ingress/lifecycle_test_inventory.json"
LIFECYCLE_INVENTORY_SHA256 = "5ab6e70f6628cc7f5768c13cd06b71725a8df0d589e1c40d64d9989cb816fdb3"
LIFECYCLE_PATH = "test/services/emo_follow_recovery_lifecycle_test.dart"
DISPATCH_PATH = "test/services/audio_remote_dispatch_position_test.dart"
DISPATCH_SHA256 = "855ca0fbaa775b06409667d6ba9969179a191d0868f8a7749eaf85ec555cb5ae"


def lifecycle_inventory(source):
    require = recovery.request.p.require
    raw = recovery.owned_file(source, LIFECYCLE_INVENTORY_PATH).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == LIFECYCLE_INVENTORY_SHA256, 'Lifecycle inventory changed.')
    value = json.loads(raw)
    require(type(value) is dict and set(value) == {'suites'} and type(value['suites']) is list
            and len(value['suites']) == 1, 'Lifecycle inventory schema invalid.')
    suite = value['suites'][0]
    require(type(suite) is dict and set(suite) == {'path', 'sha256', 'names'}
            and suite['path'] == LIFECYCLE_PATH, 'Lifecycle fixture path invalid.')
    require(hashlib.sha256(recovery.owned_file(source, suite['path']).read_bytes()).hexdigest()
            == suite['sha256'], 'Lifecycle fixture changed.')
    names = suite['names']
    require(type(names) is list and 1 <= len(names) <= 1000
            and all(type(n) is str and 0 < len(n) <= 8192 for n in names)
            and len(set(names)) == len(names), 'Lifecycle names invalid.')
    return suite


def inventory(source):
    # Both existing independent byte/name verifiers remain authoritative.
    suites = RECOVERY_INVENTORY(source)
    recovery.request.p.require(len(suites) == 3 and sorted(len(suite['names']) for suite in suites) == [6, 13, 45],
                               'All original 64 focused cases are required.')
    suite = ingress.inventory(source)
    recovery.request.p.require(suite['path'] not in {item['path'] for item in suites},
                               'Ingress fixture must be an additional suite.')
    lifecycle = lifecycle_inventory(source)
    recovery.request.p.require(lifecycle['path'] not in {s['path'] for s in suites + [suite]},
                               'Lifecycle fixture must be additional.')
    return suites + [suite, lifecycle]


def focused_observation(raw, returncode, **kwargs):
    report = ORIGINAL_OBSERVER(raw, returncode, **kwargs)
    # The three original suites have 45/13/6 pinned cases; only ingress has 3.
    names = kwargs['expected_names']
    if len(names) == 3:
        print(json.dumps(ingress.phase_observation(raw, names)), flush=True)
        print(json.dumps(ingress.dispatch_observation(raw, names)), flush=True)
    return report


def dispatch_full_observation(raw, stderr, paths, source, suites, returncode):
    report = ORIGINAL_FULL_OBSERVER(raw, stderr, paths, source, suites, returncode)
    data = (source / DISPATCH_PATH).read_bytes()
    require = recovery.request.p.require
    require(hashlib.sha256(data).hexdigest() == DISPATCH_SHA256, 'Dispatch fixture bytes changed.')
    # Extract only the exact two adjacent literals from this hash-pinned private file.
    templates = re.findall(r"test\(\s*'([^'\n]*)'\s*'([^'\n]*)',", data.decode('utf-8'))
    require(len(templates) == 1, 'Dispatch name template is not unique.')
    template = ''.join(templates[0])
    names = [template.replace('$android', a).replace('$cancel', c)
             for a in ('false', 'true') for c in ('false', 'true')]
    require(len(set(names)) == 4, 'Dispatch cases are not unique.')
    passed = [False] * 4
    valid = report.get('malformedEvents') == 0 and report.get('reason') not in ('output-limit', 'invalid-output', 'event-limit')
    if valid:
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        matches = [e['suite']['id'] for e in events if e.get('type') == 'suite'
                   and e.get('suite', {}).get('path') in (DISPATCH_PATH, str(source / DISPATCH_PATH))]
        valid = len(matches) == 1
        if valid:
            starts = [e['test'] for e in events if e.get('type') == 'testStart'
                      and e.get('test', {}).get('suiteID') == matches[0]]
            for ordinal, name in enumerate(names):
                found = [t for t in starts if t.get('name') == name]
                if len(found) != 1:
                    continue
                tid = found[0].get('id')
                completed = [e for e in events if e.get('type') == 'testDone' and e.get('testID') == tid]
                errors = [e for e in events if e.get('type') == 'error' and e.get('testID') == tid]
                passed[ordinal] = (type(tid) is int and len(completed) == 1 and not errors
                    and completed[0].get('result') == 'success'
                    and completed[0].get('skipped') is False and completed[0].get('hidden') is False)
    print(json.dumps({'stage': 'dispatch-four-full-suite', 'passedOrdinals':
                      [i + 1 for i, value in enumerate(passed) if value],
                      'expectedTests': 4, 'verified': valid and all(passed)}), flush=True)
    require(returncode != 0 or (valid and all(passed)), 'Four dispatch cases did not all pass.')
    return report


def main():
    # Existing main rejects any stage beyond prepare/fetch/full/focused/cleanup.
    # In particular, no expected-red normalization, native or package stage exists.
    with patch.multiple(recovery, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA,
                        INVENTORY_SHA256=RECOVERY_INVENTORY_SHA256, inventory=inventory), \
            patch.object(ingress, 'INVENTORY_SHA256', INGRESS_INVENTORY_SHA256), \
            patch.object(recovery, 'full_test_observation', dispatch_full_observation):
        if len(sys.argv) == 3 and sys.argv[1:] == ['source', 'focused']:
            with patch.object(recovery, 'observe_green', focused_observation):
                return recovery.main()
        return recovery.main()


if __name__ == '__main__':
    sys.exit(main())
