"""Fixed clock/dispatch repair validation layered on unchanged full-source gates."""
import hashlib
import re
import sys
from unittest.mock import patch

import follow_ingress_green as previous
from follow_ingress_proof import strict_json

PARENT = '2839becc4798f91a00f4760d72098a35e5fadca5'
MESSAGE = 'test: verify real scrobble load boundary and timing repairs 20261022'
WORKFLOW = 'follow-timing-green.yml'
REQUEST_PATH = 'requests/follow-timing-green-20261022.json'
SOURCE_REF = 'refs/heads/fix/follow-clock-and-dispatch-20261022'
SOURCE_SHA = 'a6799a73909cf06d8ba9b830e00d6a628e331205'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-timing-full-green-validation', attempt=45)
COMPONENTS = (
    ('tool/follow_clock_dispatch/scrobble_inventory.json', '8ea210a1b56c25d40de2fa566e44be95bfe7d8899b8aafe78f1f89b12ffc9711', (18,)),
    ('tool/server_clock_source_ownership/green_inventory.json', '9b2dd5591ae9aab6e2988655a3cc74c381c5000c31c453b185b9ff9fbef1fb62', (17, 7)),
    ('tool/follow_soft_seek_dispatch/green_inventory.json', 'd4a3556ed19d951071b46408f3140c8f98cdc9773e2ca07f7c0a662aa78f4f13', (2, 3, 1)),
)
ORIGINAL_INVENTORY = previous.inventory


def component_inventory(source, path, digest, counts):
    require = previous.recovery.request.p.require
    require(re.fullmatch(r'[0-9a-f]{64}', digest) is not None
            and type(counts) is tuple and 1 <= len(counts) <= 4
            and all(type(n) is int and 1 <= n <= 128 for n in counts), 'Reviewed component pins required.')
    file = previous.recovery.owned_file(source, path)
    require(file.stat().st_size <= 65536, 'Private inventory size invalid.')
    raw = file.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'Private inventory changed.')
    value = strict_json(raw)
    require(type(value) is dict and set(value) == {'suites'} and type(value['suites']) is list
            and len(value['suites']) == len(counts), 'Private inventory schema invalid.')
    suites = value['suites']
    for suite, count in zip(suites, counts):
        require(type(suite) is dict and set(suite) == {'path', 'sha256', 'names'}
                and type(suite['path']) is str
                and re.fullmatch(r'test/(?:services|remediation)/[a-z0-9_]+_test\.dart', suite['path'])
                and type(suite['sha256']) is str
                and re.fullmatch(r'[0-9a-f]{64}', suite['sha256']), 'Private fixture schema invalid.')
        fixture = previous.recovery.owned_file(source, suite['path'])
        require(fixture.stat().st_size <= 2 * 1024 * 1024
                and hashlib.sha256(fixture.read_bytes()).hexdigest() == suite['sha256'], 'Frozen fixture changed.')
        names = suite['names']
        require(type(names) is list and len(names) == count
                and all(type(n) is str and 0 < len(n) <= 8192 for n in names)
                and len(set(names)) == count, 'Private visible inventory invalid.')
    return suites


def inventory(source):
    suites = ORIGINAL_INVENTORY(source)
    previous.recovery.request.p.require(len(suites) == 6 and sum(len(s['names']) for s in suites) == 104,
                                        'All previous focused cases are required.')
    for path, digest, counts in COMPONENTS:
        suites += component_inventory(source, path, digest, counts)
    previous.recovery.request.p.require(len({s['path'] for s in suites}) == len(suites),
                                        'Component fixtures must be additional and unique.')
    return suites


def main():
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
