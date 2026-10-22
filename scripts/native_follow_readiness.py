"""Disposable-only Follow seek/preroll readiness and read-only native observability."""
import argparse
import ast
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAB = 'tool/native_playback_mac/run_lab.py'
PREPARE = 'tool/native_playback_mac/prepare_build.py'
FIXTURE = 'tool/native_playback_mac/test_follow_alignment.py'
STATE = '.native_follow_readiness/manifest.json'
ORIGINAL_STATE = '.native_follow_readiness/original-run_lab.py'
PROOF_STATE = '.native_follow_readiness/contract-proof.json'
CONTRACT_CHECKS = 23
NATIVE_STATE = '.native_mac_lab/seek-observability.json'
NATIVE_ROOT = '.native_mac_lab/just_audio/darwin/just_audio/Sources/just_audio'
NATIVE_PATHS = {'AudioPlayer.h': NATIVE_ROOT + '/include/just_audio/AudioPlayer.h',
                'AudioPlayer.m': NATIVE_ROOT + '/AudioPlayer.m'}
BASELINE = {LAB: '96dda56b6d8d4e674cb35c7426af69e5f67cee869f977bbc1e09cf95c4bfd1a6',
           PREPARE: '4dcb27fa7d93a74823d5727a271459ed6cd0901999bd33e5180afff0e363da0e',
           FIXTURE: 'f324d2f5106a26837aca41c4733e03f3a08c583b7d3cc1e12017bf34812bd8a5'}
# Filled from independently reviewed exact transformations, not runtime source.
AFTER = {'tool/native_playback_mac/run_lab.py': 'dad22e364b950e8f0b500dac13a084b0ac722f6d91dd265cef77759d2e4029ad', 'tool/native_playback_mac/prepare_build.py': 'dfdd215375ac1afd5a90e278733f5ca1a1ef5683317f95526933b5b6fe758532', 'tool/native_playback_mac/test_follow_alignment.py': 'fb1a6225d5e96e724930b9798cbed6e12c5d80fbf683de04b5e74853f7aaa4c4'}
NATIVE_HASHES = {'AudioPlayer.h': {'before': 'c8c6df3bc07f10677e0afbeb447c88da2a704b2c8323769247f78768c6a43138', 'after': '6b48fdf8e6bf67849126224151470cb8932d432f2dffd7e6fd8d09ef85796cb2'}, 'AudioPlayer.m': {'before': 'ecec29e1f913f0dca944ca3fb2e45a7ad96a138391af59f99ca3f46dfd5b65b3', 'after': 'dfc408d533c30fe95b8d0a9ad2284f2266fdbaba3377da2bde372fcaad4441c7'}}
PAYLOAD_HASHES = {'alignment_fixture_compatibility.py': 'bef7836fed2c378a9d5d36797d6974d77147006367b97c921930ab7bf700d111', 'follow_readiness_helpers.py': 'a23c172a5d009e4271efbcfe939810d3c2ca5da756bca853e8cdf0b86c60edd7', 'instrument_seek_observability.py': '678ccfe3e91b6257eb49144da60203e96bfed2183a75bed4acdd1552bf4a5bfa', 'readiness_contract.py': '9ef564eaf9ba078343c1466baae870c3821a0a72b22eba7e0eed16a38d15dbe9'}


def digest(data): return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Readiness instrumentation anchor changed')
    return text.replace(old, new, 1)


def payload(name):
    data = (ROOT / 'native_follow_readiness_payload' / name).read_bytes()
    if PAYLOAD_HASHES and digest(data) != PAYLOAD_HASHES[name]:
        raise ValueError('Readiness packaged payload changed')
    return data.decode('utf-8')


def patch_harness(original):
    if digest(original) != BASELINE[LAB]:
        raise ValueError('Readiness observed harness pin changed')
    text = original.decode('utf-8')
    text = replace_once(text, '\nclass Matrix:\n', '\n' + payload('follow_readiness_helpers.py') + '\nclass Matrix:\n')
    anchor = '''        previous = None
        while True:
            states = self.states()
            authority, follower = states[authority_index], states[2]
            assert native_follow_task_ready(authority, follower, context)
'''
    replacement = '''        baseline = self.last
        assert native_follow_task_ready(baseline[authority_index], baseline[2], context)
        correction_identity = follow_correction_identity(baseline, authority_index, context)
        self.rate_measurement.update({'correctionReadinessPollCount': 0, 'correctionReadinessElapsedMs': 0})
        previous = None
        while True:
            states = self.states()
            authority, follower = states[authority_index], states[2]
            assert follow_correction_identity(states, authority_index, context) == correction_identity
            if native_follow_readiness_pending(authority, follower, expected):
                elapsed_ms = (time.monotonic() - started) * 1000
                self.rate_measurement.update({
                    'correctionReadinessPollCount': min(25, self.rate_measurement['correctionReadinessPollCount'] + 1),
                    'correctionReadinessElapsedMs': round(min(5000, max(0, elapsed_ms)), 2),
                    'alignmentSourceNative': numeric_native_snapshot(decoded(authority)),
                    'alignmentFollowerNative': numeric_native_snapshot(decoded(follower)),
                })
                if time.monotonic() >= deadline:
                    raise TimeoutError('Native Follow alignment exceeded five-second readiness budget')
                previous = None
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
                continue
            assert native_follow_task_ready(authority, follower, context)
'''
    text = replace_once(text, anchor, replacement)
    text = replace_once(text, '                    consecutiveAlignedSamples=2)', '''                    consecutiveAlignedSamples=2,
                    correctionReadinessPollCount=self.rate_measurement['correctionReadinessPollCount'],
                    correctionReadinessElapsedMs=self.rate_measurement['correctionReadinessElapsedMs'])''')
    anchor = '''    return {key: item[key] for key in fields if key in item
            and type(item[key]) in (int, float) and math.isfinite(item[key])}'''
    text = replace_once(text, anchor, '''    result = {key: item[key] for key in fields if key in item
            and type(item[key]) in (int, float) and math.isfinite(item[key])}
    result.update({key: item[key] for key in ('seekInProgress', 'playingIntent')
                   if type(item.get(key)) is bool})
    return result''')
    ast.parse(text)
    return text.encode('utf-8')


def patch_prepare(original):
    if digest(original) != BASELINE[PREPARE]:
        raise ValueError('Readiness native builder pin changed')
    text = original.decode('utf-8')
    text = replace_once(text, '\ndef main():\n', '\n' + payload('instrument_seek_observability.py') + '\ndef main():\n')
    text = replace_once(text, '    shutil.copytree(source, target)\n', '''    shutil.copytree(source, target)
    seek_sources = instrument_seek_observability(target)
    seek_manifest = build_root / 'seek-observability.json'
    if seek_manifest.exists() or seek_manifest.is_symlink():
        raise RuntimeError('Native seek observation manifest already exists')
    seek_manifest.write_text(json.dumps({'readOnly': True, 'files': seek_sources}, indent=2), encoding='utf-8')
''')
    text = replace_once(text, '                @"requestedRate": @(wrapper.speed),\n', '''                @"requestedRate": @(wrapper.speed),
                @"seekInProgress": @(wrapper.labSeekInProgress),
                @"playingIntent": @(wrapper.labPlayingIntent),
''')
    ast.parse(text)
    return text.encode('utf-8')


def patch_fixture(original):
    namespace = {}
    exec(compile(payload('alignment_fixture_compatibility.py'), '<owned-fixture-compatibility>', 'exec'), namespace)
    return namespace['transform'](original)


def checked(repo, relative, *, new=False):
    repo = Path(repo)
    path = repo / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Readiness source symlink refused')
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError('Readiness source containment refused')
    if new:
        if path.exists(): raise ValueError('Readiness source already instrumented')
        if not path.parent.is_dir(): raise ValueError('Readiness private state directory missing')
    elif not path.is_file():
        raise ValueError('Readiness source is unavailable')
    return path


def expected_manifest():
    return {'status': 'prepared', 'productionRepositoryMutation': False,
            'disposableOnly': True, 'nativeReadOnlyGetters': True, 'originalFixtureTestMethodsUnchanged': True,
            'files': {name: {'before': BASELINE[name], 'after': AFTER[name]} for name in BASELINE},
            'payloads': PAYLOAD_HASHES}


def apply(source_repo):
    files = {name: checked(source_repo, name) for name in BASELINE}
    state_root = checked(source_repo, '.native_follow_readiness', new=True)
    manifest_path = state_root / 'manifest.json'
    originals = {name: path.read_bytes() for name, path in files.items()}
    updates = {LAB: patch_harness(originals[LAB]), PREPARE: patch_prepare(originals[PREPARE]),
               FIXTURE: patch_fixture(originals[FIXTURE])}
    if any(digest(data) != AFTER[name] for name, data in updates.items()):
        raise ValueError('Readiness packaged transformation hash changed')
    state_root.mkdir()
    (state_root / 'original-run_lab.py').write_bytes(originals[LAB])
    for name, data in updates.items(): files[name].write_bytes(data)
    manifest = expected_manifest()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def _verify_source_prepared(source_repo):
    # The attribution gate independently verifies final run_lab bytes against
    # AFTER[LAB] after reversing its own exact transport-only additions.
    for name in PAYLOAD_HASHES: payload(name)
    manifest = json.loads(checked(source_repo, STATE).read_text())
    if (not isinstance(manifest, dict) or manifest != expected_manifest()
            or any(type(manifest.get(key)) is not bool for key in
                   ('productionRepositoryMutation', 'disposableOnly', 'nativeReadOnlyGetters', 'originalFixtureTestMethodsUnchanged'))):
        raise ValueError('Readiness preparation manifest changed')
    for name in (PREPARE, FIXTURE):
        if digest(checked(source_repo, name).read_bytes()) != AFTER[name]:
            raise ValueError('Readiness prepared source changed')
    if digest(checked(source_repo, ORIGINAL_STATE).read_bytes()) != BASELINE[LAB]:
        raise ValueError('Readiness private baseline changed')
    return manifest


def expected_proof():
    return {'status': 'passed', 'checks': CONTRACT_CHECKS, 'baseline': BASELINE[LAB],
            'patched': AFTER[LAB], 'suiteSha256': PAYLOAD_HASHES['readiness_contract.py']}


class _ContractProofFailure(ValueError):
    pass


def _failed_contract_ordinals(result, names):
    # A unittest subtest owns parameters which must never reach public output.
    # Use only its parent method's exact allowlisted ordinal, not id()/str().
    ordinals = set()
    for test, _ in result.errors + result.failures:
        owner = getattr(test, 'test_case', test)
        name = getattr(owner, '_testMethodName', None)
        if type(name) is str and name in names:
            ordinals.add(names.index(name) + 1)
    return sorted(ordinals)[:CONTRACT_CHECKS]


def _verify_contract(source_repo):
    _verify_source_prepared(source_repo)
    proof_path = checked(source_repo, PROOF_STATE, new=True)
    baseline = checked(source_repo, ORIGINAL_STATE).read_bytes()
    patched = checked(source_repo, LAB).read_bytes()
    if digest(patched) != AFTER[LAB]:
        raise ValueError('Readiness contract harness changed')
    module_path = ROOT / 'native_follow_readiness_payload' / 'readiness_contract.py'
    spec = importlib.util.spec_from_file_location('owned_readiness_contract', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = module.TEST_NAMES
    if len(names) != CONTRACT_CHECKS or len(set(names)) != CONTRACT_CHECKS:
        raise ValueError('Readiness contract test names changed')
    suite = module.suite(baseline, patched)
    result = unittest.TestResult()
    suite.run(result)
    if (result.testsRun != CONTRACT_CHECKS or result.errors or result.failures
            or result.skipped or result.expectedFailures or result.unexpectedSuccesses):
        ordinals = _failed_contract_ordinals(result, names)
        print(json.dumps({'stage': 'native-follow-readiness-proof', 'status': 'failed',
            'checks': min(CONTRACT_CHECKS, max(0, result.testsRun)),
            'failedTestOrdinals': ordinals[:CONTRACT_CHECKS],
            'errorCategory': 'runner' if result.errors else 'assertion'}), flush=True)
        raise _ContractProofFailure('Readiness deterministic contract proof failed')
    _verify_source_prepared(source_repo)
    if digest(checked(source_repo, LAB).read_bytes()) != AFTER[LAB]:
        raise ValueError('Readiness contract harness changed during proof')
    proof = expected_proof()
    checked(source_repo, PROOF_STATE, new=True).write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(json.dumps({'stage': 'native-follow-readiness-proof', 'status': 'passed', 'checks': CONTRACT_CHECKS}), flush=True)
    return proof


def verify_contract(source_repo):
    try:
        return _verify_contract(source_repo)
    except _ContractProofFailure:
        raise
    except Exception:
        print(json.dumps({'stage': 'native-follow-readiness-proof', 'status': 'failed',
            'checks': 0, 'failedTestOrdinals': [], 'errorCategory': 'runner'}), flush=True)
        raise ValueError('Readiness deterministic contract runner failed') from None


def verify_prepared(source_repo):
    manifest = _verify_source_prepared(source_repo)
    proof = json.loads(checked(source_repo, PROOF_STATE).read_text())
    if not isinstance(proof, dict) or proof != expected_proof() or type(proof.get('checks')) is not int:
        raise ValueError('Readiness contract proof manifest changed')
    return manifest


def verify_compiled(source_repo):
    verify_prepared(source_repo)
    manifest = json.loads(checked(source_repo, NATIVE_STATE).read_text())
    if (not isinstance(manifest, dict) or manifest != {'readOnly': True, 'files': NATIVE_HASHES}
            or type(manifest.get('readOnly')) is not bool):
        raise ValueError('Readiness native getter manifest changed')
    for name, hashes in NATIVE_HASHES.items():
        if digest(checked(source_repo, NATIVE_PATHS[name]).read_bytes()) != hashes['after']:
            raise ValueError('Readiness native getter source changed')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('apply', 'proof', 'verify-prepared', 'verify-compiled'))
    parser.add_argument('--repo', required=True, type=Path)
    args = parser.parse_args()
    {'apply': apply, 'proof': verify_contract, 'verify-prepared': verify_prepared, 'verify-compiled': verify_compiled}[args.stage](args.repo)


if __name__ == '__main__': main()
