"""Dedicated bounded8s validation over the unchanged historical source gates."""
PARENT = 'a65819318279f53c06fd8d19794959c39d6b00e8'
MESSAGE = 'test: validate dedicated bounded Follow recovery budget 20261024'
WORKFLOW = 'follow-bounded-budget-green.yml'
REQUEST_PATH = 'requests/follow-bounded-budget-green-20261024.json'
SOURCE_REF = 'refs/heads/fix/follow-bounded-budget-20261024'
SOURCE_SHA = 'bfc1967a8eae65154bdd5e74491f99136dfc198d'
INVENTORY_SHA256 = '1eb1a52bcac9190ad9a1037b7c20e37f9e5e5c6ae15a78514e4c7571893f15e0'
REVIEWED_MANIFEST_SHA256 = {'tool/follow_recovery/test_inventory.json': 'c4ec0ca09b1c36b5cfb3fafcedbf347cbedaeb5cf9e46c19f892470d185ba2a2', 'tool/follow_post_restore/fixed_green_inventory.json': 'c7a52d436fe300af87c5b0d4c1630f88df6b51fa6126f598251e9805e1b0a533', 'tool/follow_anchor_admission_gap/green_inventory.json': '8438b0fdba29711e6f3491b38e604d4417d14b9add9969227734797ab4b01dda', 'tool/follow_directional_settle/green_inventory.json': '2d51865a1d408b8d011326423ba1cf680cd09cc265113967c66e15e4f9f62cc8', 'tool/follow_native_receipt_consumption/green_inventory.json': '8207bc0cc5588db9a1ce8e0e1f5100b8bdc0d47a13d19aa2102e9cbd9806ff36', 'tool/follow_fractional_precision/green_inventory.json': '18e21de53f0ab0da75239f859ca3c5c27444fabf6e2acfb8eee1e308ecc263b9', 'tool/follow_smooth_settlement/green_inventory.json': '3988701534b93b02adf1c1792bcbf01a55be8a1dc953b0b99604b210beb1ee51'}
DIAGNOSTIC_FIXTURE_SHA256 = 'c550151076f03fb36670ef54929fb5af76b20ef711b4dd164d67fb8c6c1e1eab'
RENAMED_CASE = ('test/services/emo_follow_nominal_restore_verification_test.dart', '31ecc7c0826098dfaf9800056a8ec3d9e7364cd313c2f0ce91146b91e6e5ac07', '34f557936588019499483320f414fa277dbbd08e3129f3cd87e96496be81e596')

import hashlib
import json
import re
import sys
from contextlib import ExitStack
from unittest.mock import patch

import follow_ordinary_settle_green as previous
import follow_clock_interval_green as clock
import follow_directional_settle_green as directional
import follow_anchor_admission_green as admission
import native_receipt_consumption_green as receipt
import fractional_precision_green as fractional

TIMING = previous.TIMING
ORIGINAL_INVENTORY = previous.inventory
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-bounded-budget-full-green-validation', attempt=112)
INVENTORY_PATH = 'tool/follow_bounded_budget/green_inventory.json'
EXPECTED_COUNTS = (4, 3)
BUDGET_BASELINE_PATH = 'test/services/emo_follow_bounded_budget_test.dart'
BUDGET_BASELINE_SHA256 = '98dbc33717f6f9b33b4c85d007046f63406b7992d729f02fa2fbbc2ecea03580'
PRIOR_NAMES_SHA256 = 'd96bc2a64d8f1b8b78e30bed4aef60922686418d1a18712a2b31cbca2fd7d3a9'
FROZEN_PRIOR_SHA256 = 'c0ddcbb15a9bda247129ab55307903b13307c0226b4aba0f2c7e822ff6371586'
CHANGED_PRIOR_PATHS = (
    'test/services/emo_follow_post_seek_recovery_test.dart',
    'test/services/emo_follow_nominal_restore_boundary_test.dart',
    'test/services/emo_follow_nominal_restore_verification_test.dart',
    'test/services/emo_follow_anchor_admission_gap_test.dart',
    'test/services/emo_follow_anchor_admission_boundary_test.dart',
    'test/services/emo_follow_directional_settle_test.dart',
    'test/services/emo_follow_directional_boundary_test.dart',
    'test/services/emo_follow_native_receipt_consumption_test.dart',
    'test/services/emo_follow_native_receipt_wake_boundary_test.dart',
    'test/services/emo_follow_fractional_precision_test.dart',
    'test/services/emo_follow_smooth_settlement_boundary_test.dart',
)
# Only effective pin owners are changed, and only during this entry point.
# Existing nested main functions retain their loaders and acceptance checks.
PIN_TARGETS = (
    ('tool/follow_recovery/test_inventory.json', clock, 'RECOVERY_DIGEST',
     'fda39ee980a7a8b93261b3147d0a467adf460af614689a8ec5610fe871deb01a'),
    ('tool/follow_post_restore/fixed_green_inventory.json', directional, 'POST_RESTORE_DIGEST',
     '263dbe2a40cfd6f723f689fe71061cfdb44ac3920b31db50d216adb25cdc42e6'),
    ('tool/follow_anchor_admission_gap/green_inventory.json', admission, 'INVENTORY_SHA256',
     '0bb5f47b2cb9b25c8c5b49cafc3efb2b058ef52ee8ec69ce263948647c545a12'),
    ('tool/follow_directional_settle/green_inventory.json', fractional, 'DIRECTIONAL_INVENTORY_SHA256',
     'c3e17aa8d1cb6ee071149674bdf8b1aafd9fa982e930feaa9ca040201f3b972c'),
    ('tool/follow_native_receipt_consumption/green_inventory.json', receipt, 'INVENTORY_SHA256',
     '7bf0cca302b29c6d1b7dc96dd6eb8060c29d453805c1a4a69872d15b82fe9230'),
    ('tool/follow_fractional_precision/green_inventory.json', fractional, 'INVENTORY_SHA256',
     '9b1fcd4288a1993f2334228184fdecd54ba97911af726d2d682d4424f4681c3e'),
    ('tool/follow_smooth_settlement/green_inventory.json', previous, 'INVENTORY_SHA256',
     'e086df2bfc30773f04d355c860075bff478ad6bbb7b9610188c6dfe2e4977f47'),
)
ORIGINAL_DIAGNOSTIC_SHA256 = 'd76e021d275cb2dcec44132c82aecf76b6b2c84ff4824c1a965b8de9ecb69c74'


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS == (4, 3),
        'Exactly four frozen budget cases and three reviewed boundaries are required.')


def require_pins():
    require_counts()
    require = TIMING.previous.recovery.request.p.require
    valid_hash = lambda value: type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value)
    require(type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
            and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/fix/[a-zA-Z0-9_./-]+', SOURCE_REF)
            and INVENTORY_PATH == 'tool/follow_bounded_budget/green_inventory.json'
            and valid_hash(INVENTORY_SHA256)
            and type(REVIEWED_MANIFEST_SHA256) is dict
            and set(REVIEWED_MANIFEST_SHA256) == {row[0] for row in PIN_TARGETS}
            and all(valid_hash(REVIEWED_MANIFEST_SHA256[path])
                    and REVIEWED_MANIFEST_SHA256[path] != old
                    for path, _, _, old in PIN_TARGETS)
            and valid_hash(DIAGNOSTIC_FIXTURE_SHA256)
            and DIAGNOSTIC_FIXTURE_SHA256 != ORIGINAL_DIAGNOSTIC_SHA256
            and type(RENAMED_CASE) is tuple and len(RENAMED_CASE) == 3
            and RENAMED_CASE[0] == 'test/services/emo_follow_nominal_restore_verification_test.dart'
            and all(valid_hash(value) for value in RENAMED_CASE[1:])
            and RENAMED_CASE[1] != RENAMED_CASE[2]
            and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
            'Complete reviewed bounded budget pins are required.')
    # Check every historical owner before changing any of them. This prevents
    # silently overriding a newly changed historical contract.
    require(all(getattr(module, field) == old for _, module, field, old in PIN_TARGETS)
            and fractional.DIAGNOSTIC_FIXTURE_SHA256 == ORIGINAL_DIAGNOSTIC_SHA256,
            'Exact unchanged historical pin owners are required.')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True,
                                     separators=(',', ':')).encode('ascii')).hexdigest()


def name_hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def require_prior_contract(suites):
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 35 and sum(len(s['names']) for s in suites) == 275
            and len({s['path'] for s in suites}) == 35
            and len({name for s in suites for name in s['names']}) == 275,
            'Every one of the 275 historical cases is required.')
    renamed_path, old_name, new_name = RENAMED_CASE
    names = []
    renamed = 0
    for suite in suites:
        hashes = [name_hash(name) for name in suite['names']]
        if suite['path'] == renamed_path:
            require(hashes.count(new_name) == 1 and old_name not in hashes,
                    'The single explicitly reviewed policy rename is required.')
            hashes = [old_name if value == new_name else value for value in hashes]
            renamed += 1
        names.append([suite['path'], hashes])
    require(renamed == 1 and digest(names) == PRIOR_NAMES_SHA256,
            'Historical paths, ordering and all other names must remain unchanged.')
    frozen = [[s['path'], s['sha256']] for s in suites
              if s['path'] not in CHANGED_PRIOR_PATHS]
    require(len(frozen) == 24 and digest(frozen) == FROZEN_PRIOR_SHA256,
            'Every unrelated historical fixture must remain byte-identical.')


def inventory(source):
    require_counts()
    suites = ORIGINAL_INVENTORY(source)
    require_prior_contract(suites)
    require = TIMING.previous.recovery.request.p.require
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == (4, 3)
            and additional[0]['path'] == BUDGET_BASELINE_PATH
            and additional[0]['sha256'] == BUDGET_BASELINE_SHA256,
            'Both complete budget suites and the exact frozen four-case baseline are required.')
    suites = [*suites, *additional]
    require(len(suites) == 37 and sum(len(s['names']) for s in suites) == 282
            and len({s['path'] for s in suites}) == 37
            and len({name for s in suites for name in s['names']}) == 282,
            'All 282 cases across 37 unique suites are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Bounded budget pins or historical contracts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with ExitStack() as scope:
        for path, module, field, _ in PIN_TARGETS:
            scope.enter_context(patch.object(module, field, REVIEWED_MANIFEST_SHA256[path]))
        scope.enter_context(patch.object(fractional, 'DIAGNOSTIC_FIXTURE_SHA256', DIAGNOSTIC_FIXTURE_SHA256))
        scope.enter_context(patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
            SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory))
        return previous.main()


if __name__ == '__main__':
    raise SystemExit(main())
