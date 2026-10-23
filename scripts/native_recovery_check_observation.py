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

SOURCE_SHA = 'f6251a2a0e6441f174d05b488bc0fb1b41d52e39'
AUX_SHA = 'e19bf7da3bdee9bb202728a30ad7db38c883d29e'
AUX_REF = 'refs/heads/test/immediate-play-policy-observation-20261023'
AUX_TREE = 'cdc936920eface1f30d8718da6e8a6d1e179f4c2'
PREFIX = 'tool/native_playback_mac/recovery_check_observation/'
STATE = '.native_recovery_check_observation'
FILES = {'transform.py': ('7ed83093945322da1a7aff141a64befea9df357dd03bf6b9cbe25dbe2d40a21d', 41596, 'de66910830b81fa3903ade4d996f684f75b3c71f'), 'schema.json': ('530496ee1d92ce2238ec7fc8769633bcb41aae36c4008920d63c7b026a0bf808', 6071, 'b1f01ab4e151e2d2228385fab69ac39259e576f7'), 'play_policy_schema.json': ('9104b050fcaef7db7111acc4d42fe845d11ff5fb8de9a30d70f992046985adc6', 5920, '0c0aa4375af980bcc22534daf338d703ad7e1fd3'), 'README.md': ('16e3c71c5f5fd4f169e4f477a5ec06959154237357d5ee5c65a905d57452e627', 13991, 'a5913216c85dd8e2902153d2dab5e53fd3e9ec5c'), 'test_transform.py': ('a04b10d9e4bfc6abf58eea454b6fefc521e6fa9a98cd3f2f88a745647d681300', 8605, 'ef911e1eb048ea4a3b509b8f360a5595bf09c9be')}
CONTROLLER = 'lib/services/emo_follow_sync_controller.dart'
SERVICE = 'lib/services/audio_player_service.dart'
MAIN = 'tool/native_playback_mac/main.dart'
BASE = {CONTROLLER: '113320f040275374526ba15defc37f85d8e2e149ebbf31e93fdb37109950f1ef', SERVICE: 'beffc2d192c0e6948c7d726f819513e47bfeb5fb6924698d30453e80d0c5a252', MAIN: '7e4b804a9eaeeec929768ddd9ce9a5479639f73f443a8f3e6693916e59565833'}
AFTER = {CONTROLLER: 'cf069243315944b661cdb99e2cb10a885a7f1e667773c8cf4e4d17728136258c', SERVICE: 'f362779d03ad01cee0cd9b5a1edfd04bf5ba356b33751553f360475976603ea5', MAIN: 'a10b9bc32b65cb62319d6fc7a35a11e61977bda7adc2e5db60ae7fa774708717'}
LOGGED_MAIN = '4e6ecf2e4b8471f3186f0763e32ed053372ed1a7066e3496c33dbbb7df927ea1'
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
                controllerOperationCount=32, serviceOperationCount=15, labMainOperationCount=2,
                recordLimit=128, truncationRecordLimit=1, droppedCountLimit=1000000,
                policyRecordLimit=32, policyTruncationRecordLimit=1,
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
