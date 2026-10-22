"""Fixed post-restoration repair on unchanged 152-case/full-source gates."""
import sys
from unittest.mock import patch
import follow_timing_green as previous

PARENT = '8bb951fa5c7195a0ef43a705b2fd76ed2bca4a10'
MESSAGE = 'test: validate post-restore native settlement repair 20261022'
WORKFLOW = 'follow-post-restore-green.yml'
REQUEST_PATH = 'requests/follow-post-restore-green-20261022.json'
SOURCE_REF = 'refs/heads/fix/follow-post-restore-verification-20261022'
SOURCE_SHA = '3093662be2bcc31fefde455baf5d6f68e51784dc'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-post-restore-full-green-validation', attempt=49)
COMPONENTS = (('tool/follow_post_restore/fixed_green_inventory.json', '535d86b9cd441c952554eb67f0627bcf50dba13175369ab0e122f718fa464854', (4, 5)),)
ORIGINAL_INVENTORY = previous.inventory


def inventory(source):
    suites = ORIGINAL_INVENTORY(source)
    require = previous.previous.recovery.request.p.require
    require(len(suites) == 12 and sum(len(s['names']) for s in suites) == 152,
            'All previous focused cases are required.')
    for path, digest, counts in COMPONENTS:
        suites += previous.component_inventory(source, path, digest, counts)
    require(len({s['path'] for s in suites}) == len(suites),
            'Post-restoration fixtures must be additional and unique.')
    return suites


def main():
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
