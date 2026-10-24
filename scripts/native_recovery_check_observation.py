"""Pinned private auxiliary observation; public code contains hashes, not source."""
from contextlib import contextmanager
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

SOURCE_SHA = 'bfc1967a8eae65154bdd5e74491f99136dfc198d'
AUX_SHA = '3e06d0a7faf99f3608a2d3734847e683f6d71d07'
AUX_REF = 'refs/heads/test/bounded-budget-observation-20261024'
AUX_TREE = '1d93a046e44c704deb3fca091dc0fde5b960fcb7'
PREFIX = 'tool/native_playback_mac/recovery_check_observation/'
STATE = '.native_recovery_check_observation'
FILES = {'transform.py': ('ae8129d2d78e1f9795c2f321c03685e0a259ab1b88cfdc128154155524b32d65', 51948, '759d25b0c7e2fdae5d4b93b4d156ccb4738ffa0d'), 'schema.json': ('530496ee1d92ce2238ec7fc8769633bcb41aae36c4008920d63c7b026a0bf808', 6071, 'b1f01ab4e151e2d2228385fab69ac39259e576f7'), 'play_policy_schema.json': ('9104b050fcaef7db7111acc4d42fe845d11ff5fb8de9a30d70f992046985adc6', 5920, '0c0aa4375af980bcc22534daf338d703ad7e1fd3'), 'admission_schema.json': ('056abf764544781334ab3a906ad53177495bf422176f8c9d0c0b9cb619cc595a', 2640, '5d603420eeeff08085f0e0138b6a099dc1044f22'), 'README.md': ('23f48e87964d558ee00c682ff90f2b6139bed37bb6d9e6c7c2ce1fc1e83b6b5e', 19768, '3ab8d05605a4e9665b8dc075cac9955af8544ad9'), 'test_transform.py': ('0b9de38999d11f9185626459533029f84a4824a2572debaa7bffa16a7296d8e9', 12917, '315b68ee1dfc4c48c715668c683efd72f2bab817')}
CONTROLLER = 'lib/services/emo_follow_sync_controller.dart'
SERVICE = 'lib/services/audio_player_service.dart'
MAIN = 'tool/native_playback_mac/main.dart'
BASE = {CONTROLLER: '13c0e1c762a33c88d7ed477282a3072a1e6d3d50df277e4a5c327fecd529f3aa', SERVICE: 'beffc2d192c0e6948c7d726f819513e47bfeb5fb6924698d30453e80d0c5a252', MAIN: '7e4b804a9eaeeec929768ddd9ce9a5479639f73f443a8f3e6693916e59565833'}
AFTER = {'lib/services/emo_follow_sync_controller.dart': '5a3184d816a664bcaa8097702aabcf63052476745f40d6e4238509cc3ad65470', 'lib/services/audio_player_service.dart': '37ecf264ecd3fbe2bf08ad79f8cccff324da7ae94a4b83b765751240ccfa3660', 'tool/native_playback_mac/main.dart': '8d93f02446c61bbf1e76325fc0ba513e02d88f5b20aea778aa414d8b83440b6e'}
LOGGED_MAIN = 'd18752ba4db3bd89ba8bb89dedb3d777cd72608ba4d1a017fd749ccfba255026'
LOG_OLD = b'  await Logger.setLogLevel(LogLevel.warning);\n'
LOG_NEW = b'  await Logger.setLogLevel(LogLevel.debug);\n'


def require(ok):
    if not ok: raise ValueError('Private recovery observation integrity refused')


def digest(data): return hashlib.sha256(data).hexdigest()


def owned(root, relative, *, new=False):
    root, relative = Path(root), Path(relative)
    require(not relative.is_absolute() and all(p not in ('.', '..', '.git') for p in relative.parts))
    path = root / relative
    require(not any(p.is_symlink() for p in (path, *path.parents))
            and path.resolve().is_relative_to(root.resolve()))
    require(not path.exists() if new else path.is_file())
    return path


def auxiliary(source):
    source = Path(source)
    require(source.name == 'source' and not any(p.is_symlink() for p in (source, *source.parents)))
    return source.parent / STATE


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result); result[key] = value
        return result
    def invalid(value): raise ValueError('Private observer JSON refused')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def exact(actual, expected):
    require(json.dumps(actual, sort_keys=True, separators=(',', ':')) ==
            json.dumps(expected, sort_keys=True, separators=(',', ':')))


def fingerprints():
    def row(path):
        return dict(baseSha256=BASE[path], overlaySha256=AFTER[path],
                    inverseSha256=BASE[path], inverseByteIdentical=True)
    return dict(schemaVersion=2, controller=row(CONTROLLER), audioService=row(SERVICE), labMain=row(MAIN),
                controllerOperationCount=41, serviceOperationCount=20, labMainOperationCount=3,
                recordLimit=128, truncationRecordLimit=1, droppedCountLimit=1000000,
                policyRecordLimit=32, policyTruncationRecordLimit=1,
                admissionSummaryLimit=4, admissionAttemptCountLimit=5,
                nativeRunPerformed=False, productSourceModified=False)


def fetch_manifest():
    return dict(source=SOURCE_SHA, auxiliary=AUX_SHA, auxiliaryRef=AUX_REF,
                auxiliaryTree=AUX_TREE, files={n: v[0] for n, v in FILES.items()})


def package(source):
    root = auxiliary(source)
    require(root.is_dir() and not root.is_symlink())
    require({p.name for p in root.iterdir()} in (set(FILES) | {'fetch.json'}, set(FILES) | {'fetch.json', 'applied.json'}))
    for name, (sha, size, blob) in FILES.items():
        data = owned(root, name).read_bytes()
        require(len(data) == size and digest(data) == sha
                and hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + data).hexdigest() == blob)
    exact(strict_json(owned(root, 'fetch.json').read_bytes()), fetch_manifest())
    return root


def fetch(source, p):
    """Only called from the already-credentialed source fetch stage."""
    root = auxiliary(source); owned(root.parent, root.name, new=True)
    p.require_secrets(['SOURCE_READ_TOKEN'])
    env = os.environ.copy()
    token = env.pop('SOURCE_READ_TOKEN')
    credential = base64.b64encode(('x-access-token:' + token).encode()).decode()
    env.update({'GIT_CONFIG_COUNT': '2', 'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
                'GIT_CONFIG_VALUE_0': 'AUTHORIZATION: basic ' + credential,
                'GIT_CONFIG_KEY_1': 'credential.helper', 'GIT_CONFIG_VALUE_1': '',
                'GIT_TERMINAL_PROMPT': '0'})
    url = 'https://github.com/' + p.SOURCE + '.git'
    require(p.quiet(['git', 'ls-remote', '--exit-code', url, AUX_REF], source, env).strip() == AUX_SHA + '\t' + AUX_REF)
    p.quiet(['git', 'fetch', '--quiet', '--depth=1', '--no-tags', url, AUX_SHA], source, env)
    clean_env = {k: v for k, v in env.items() if not k.startswith('GIT_CONFIG_')}
    require(p.quiet(['git', 'rev-parse', 'HEAD'], source, clean_env).strip() == SOURCE_SHA)
    require(p.quiet(['git', 'rev-parse', AUX_SHA + '^{tree}'], source, clean_env).strip() == AUX_TREE)
    # cat-file reads the actual parent even when the auxiliary tip is shallow.
    commit = p.quiet(['git', 'cat-file', '-p', AUX_SHA], source, clean_env)
    require([line for line in commit.splitlines() if line.startswith('parent ')] == ['parent ' + SOURCE_SHA])
    changes = p.quiet(['git', 'diff-tree', '--no-commit-id', '--name-status', '-r', SOURCE_SHA, AUX_SHA], source, clean_env)
    require(set(changes.splitlines()) == {'A\t' + PREFIX + name for name in FILES} and len(changes.splitlines()) == len(FILES))
    rows = p.quiet(['git', 'ls-tree', '-rz', '--full-tree', AUX_SHA, '--', PREFIX], source, clean_env)
    require(set(rows.split('\0')[:-1]) == {'100644 blob ' + values[2] + '\t' + PREFIX + name for name, values in FILES.items()}
            and rows.endswith('\0') and len(rows.split('\0')) == len(FILES) + 1)
    data = {}
    for name, (sha, size, blob) in FILES.items():
        value = p.quiet(['git', 'show', AUX_SHA + ':' + PREFIX + name], source, clean_env).encode('utf-8')
        require(len(value) == size and digest(value) == sha); data[name] = value
    root.mkdir(mode=0o700)
    for name, value in data.items(): owned(root, name, new=True).write_bytes(value)
    owned(root, 'fetch.json', new=True).write_text(json.dumps(fetch_manifest(), sort_keys=True))
    package(source)


def invoke(root, args, env):
    require(not any(any(word in k.upper() for word in ('TOKEN', 'PASSWORD', 'SECRET', 'KEYSTORE', 'KEY_ALIAS')) for k in env))
    result = subprocess.run([sys.executable, str(root / 'transform.py'), *map(str, args)],
                            cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, check=False)
    require(result.returncode == 0 and len(result.stdout) <= 8192 and not result.stderr)
    value = strict_json(result.stdout); exact(value, fingerprints())
    return value


def normalized_main(data, logged):
    require(type(logged) is bool)
    if logged:
        require(digest(data) == LOGGED_MAIN and data.count(LOG_NEW) == 1)
        data = data.replace(LOG_NEW, LOG_OLD, 1)
    require(digest(data) == AFTER[MAIN])
    return data


def observation_env():
    excluded = {'DEFAULT_SERVER_URL', 'GITHUB_ENV', 'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY'}
    return {k: v for k, v in os.environ.items() if k not in excluded
            and not any(word in k.upper() for word in ('TOKEN', 'PASSWORD', 'SECRET', 'KEYSTORE', 'KEY_ALIAS'))}


def verify(source, *, logged=True):
    root = package(source)
    exact(strict_json(owned(root, 'applied.json').read_bytes()), fingerprints())
    controller = owned(source, CONTROLLER).read_bytes()
    service = owned(source, SERVICE).read_bytes()
    main = normalized_main(owned(source, MAIN).read_bytes(), logged)
    require(digest(controller) == AFTER[CONTROLLER] and digest(service) == AFTER[SERVICE])
    with tempfile.TemporaryDirectory(prefix='recovery-inverse-', dir=root.parent) as temp:
        scratch = Path(temp)
        (scratch / 'controller').write_bytes(controller); (scratch / 'service').write_bytes(service)
        (scratch / 'main').write_bytes(main)
        return invoke(root, ['check-inverse', '--input', scratch / 'controller',
            '--service-input', scratch / 'service', '--main-input', scratch / 'main'], observation_env())


def apply_after_pristine(source, sha, env, original_fingerprint):
    require(sha == SOURCE_SHA)
    before = original_fingerprint(source, sha, env)
    root = package(source); owned(root, 'applied.json', new=True)
    for name, expected in BASE.items(): require(digest(owned(source, name).read_bytes()) == expected)
    with tempfile.TemporaryDirectory(prefix='recovery-apply-', dir=root.parent) as temp:
        scratch = Path(temp)
        report = invoke(root, ['apply', '--input', owned(source, CONTROLLER), '--output', scratch / 'controller',
                              '--service-input', owned(source, SERVICE), '--service-output', scratch / 'service',
                              '--main-input', owned(source, MAIN), '--main-output', scratch / 'main',
                              '--manifest', scratch / 'manifest.json'], env)
        exact(strict_json(owned(scratch, 'manifest.json').read_bytes()), report)
        updates = {CONTROLLER: owned(scratch, 'controller').read_bytes(), SERVICE: owned(scratch, 'service').read_bytes(),
                   MAIN: owned(scratch, 'main').read_bytes()}
        require(all(digest(data) == AFTER[name] for name, data in updates.items()))
        # Prove the private transformer touched no checkout bytes before admission.
        require(original_fingerprint(source, sha, env) == before)
        for name, data in updates.items(): owned(source, name).write_bytes(data)
        owned(root, 'applied.json', new=True).write_text(json.dumps(report, sort_keys=True))
    verify(source, logged=False)
    return before


@contextmanager
def lifecycle_pins(module):
    with patch.multiple(module, MAIN_BEFORE_SHA256=AFTER[MAIN], MAIN_AFTER_SHA256=LOGGED_MAIN):
        yield


def cleanup(source):
    root = auxiliary(source)
    require(not root.is_symlink() and not any(p.is_symlink() for p in root.parents))
    if root.exists():
        require(root.is_dir() and root.resolve().parent == Path(source).resolve().parent)
        shutil.rmtree(root)
