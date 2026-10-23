"""Hash-pinned disposable test-fixture compatibility, with no runtime changes.

AlignmentMatrix metadata is extended. One obsolete deadline fixture receives an
explicit fake-clock expiry after alignment; all original assertions are retained.
No runtime control, native sample, rate guard, or real deadline changes.
"""
import ast
import hashlib

TARGET = 'tool/native_playback_mac/test_follow_alignment.py'
BEFORE_SHA256 = 'f324d2f5106a26837aca41c4733e03f3a08c583b7d3cc1e12017bf34812bd8a5'
AFTER_SHA256 = 'cafbeaf89647915cab12d8664a03f186c016f9ca5c10dfc1738d0a3d2bdb63cd'

IDENTITY_FIXTURE = 'def add_alignment_fixture_identity(authority, follower, authority_index):\n    """Synthetic process/task metadata, without altering playback observations."""\n    authority_id = \'fixture-authority-\' + str(authority_index)\n    authority_device = \'fixture-device-\' + str(authority_index)\n    for role, value in ((authority_index, authority), (2, follower)):\n        value.update(clientId=\'fixture-authority-\' + str(role),\n            deviceSessionId=\'fixture-device-\' + str(role), pid=100 + role,\n            bundleId=\'fixture.bundle.\' + str(role), root=\'/owned/fixture/\' + str(role),\n            identitySeedMatches=True, strictV2=True, followNegotiated=True, connection=\'ready\',\n            contexts={\'source-context\': {\'authorityClientId\': authority_id,\n                \'authorityDeviceSessionId\': authority_device, \'epoch\': 1,\n                \'controlVersion\': 2, \'queueRevision\': 1}},\n            preflightDiagnostics={\'connectionGeneration\': 1})\n        value[\'nativePlayers\'][0].update(seekInProgress=False, playingIntent=True)\n    follower[\'contextId\'] = \'original-fixture-context\'\n    follower[\'preflightDiagnostics\'].update(followRecoveryGateActive=True,\n        recoveryKind=\'follow\', recoveryPhase=\'active\', recoveryContextMatchesCurrent=True,\n        recoveryAuthorityMatchesSelf=True, recoveryControlVersion=3, recoveryAppliedControlVersion=3,\n        queueHydrating=False, restoreInProgress=False)\n'
BASELINE_FIXTURE = "        # Match the real native-follow-start sample without advancing the clock\n        # or changing the measured synthetic sequence and mutation callbacks.\n        authority = state(0, 37088, self.expected)\n        authority.update(contextId='source-context', queue=['track'], currentIndex=0, trackId='track')\n        follower = state(0, 37088 + self.offset(0), self.expected)\n        follower.update(runtimeMode='follow', followSourceContextId='source-context',\n            queue=['track'], currentIndex=0, trackId='track', followMaxCorrectionFraction=.04,\n            followSyncToleranceMs=50, followLeadCompensationMs=0)\n        add_alignment_fixture_identity(authority, follower, self.authority_index)\n        self.last = [{}, {}, follower]\n        self.last[self.authority_index] = authority\n"


DEADLINE_TEST = 'test_alignment_and_advancement_share_original_deadline'
DEADLINE_ANCHOR = ("    def test_alignment_and_advancement_share_original_deadline(self):\n"
    "        matrix = AlignmentMatrix(Clock(), lambda t: -205 if t < 4.7 else 14)\n")
DEADLINE_STIMULUS = ("        original_outcome = matrix.outcome\n"
    "        def expire_after_alignment(name, **metrics):\n"
    "            original_outcome(name, **metrics)\n"
    "            if name == 'native-follow-aligned':\n"
    "                matrix.clock.now = max(matrix.clock.now, 5.0)\n"
    "        matrix.outcome = expire_after_alignment\n")


def restore_deadline_stimulus(updated):
    text = updated.decode('utf-8')
    if text.count(DEADLINE_STIMULUS) != 1:
        raise ValueError('Fixture deadline inverse changed')
    return text.replace(DEADLINE_STIMULUS, '', 1).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Fixture anchor changed')
    return text.replace(old, new, 1)


def original_test_contract(tree):
    return {
        'tests': {node.name: ast.dump(node) for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')},
        'assertions': [ast.dump(node) for node in ast.walk(tree) if isinstance(node, ast.Assert)],
    }


def transform(original):
    if digest(original) != BEFORE_SHA256:
        raise ValueError('Fixture source pin changed')
    text = original.decode('utf-8')
    before_contract = original_test_contract(ast.parse(text))
    anchor = '\nclass AlignmentMatrix(run_lab.Matrix):\n'
    text = once(text, anchor, '\n' + IDENTITY_FIXTURE + anchor)
    anchor = '        self.observed, self.outcomes = [], []\n'
    text = once(text, anchor, anchor + BASELINE_FIXTURE)
    anchor = '        if self.mutate is not None:\n'
    text = once(text, anchor,
                '        add_alignment_fixture_identity(a, f, self.authority_index)\n' + anchor)
    text = once(text, DEADLINE_ANCHOR, DEADLINE_ANCHOR + DEADLINE_STIMULUS)
    restored = restore_deadline_stimulus(text.encode('utf-8'))
    if original_test_contract(ast.parse(restored)) != before_contract:
        raise ValueError('Fixture original test contract changed')
    result = text.encode('utf-8')
    if digest(result) != AFTER_SHA256:
        raise ValueError('Fixture transformation pin changed')
    return result

