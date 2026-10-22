"""One exact same-version rebuild, isolated from stable publication."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

import pipeline as p

SOURCE_REF = 'refs/heads/codex/fix-discovery-cache-banners-20261022'
SOURCE_SHA = 'c381e75f32a084068e803c847e9887497e1cec37'
SERVER_SHA = '8e9a319002c0ffa6054cd98e06dd271070ed729b'
VERSION = '1.0.10+27'
PARENT = '9ac5235b312f0427e3a33e78388bf641c34d0741'
MESSAGE = 'test: rebuild current client for isolated server tests 20261022'
WORKFLOW = 'current-source-check.yml'
REQUEST_PATH = 'requests/current-source-20261022.json'
REQUEST = {'source_repository': p.SOURCE, 'source_ref': SOURCE_REF,
           'source_sha': SOURCE_SHA, 'server_sha': SERVER_SHA,
           'version': VERSION, 'mode': 'build-only', 'attempt': 1}
STAGES = ('prepare', 'fetch', 'validate_source', 'build', 'verify',
          'android_tools', 'windows_tools', 'build_windows', 'verify_windows', 'cleanup')


def context():
    p.require(p.POLICY['builder_repository'] == p.BUILDER
              and p.POLICY['source_repository'] == p.SOURCE
              and p.POLICY['release_repository'] == p.DEST
              and p.POLICY['source_ref'] == p.SOURCE_REF, 'Repository policy mismatch.')
    p.require(os.environ.get('GITHUB_REPOSITORY') == p.BUILDER, 'Wrong repository.')
    p.require(os.environ.get('GITHUB_REF') == 'refs/heads/main', 'Only trusted main may run.')
    p.require(os.environ.get('GITHUB_EVENT_NAME') == 'push', 'Only the fixed rebuild push may run.')
    p.require(os.environ.get('GITHUB_WORKFLOW_REF') == p.BUILDER + '/.github/workflows/' + WORKFLOW + '@refs/heads/main', 'Wrong rebuild workflow.')
    sha = p.checked_sha(os.environ.get('GITHUB_SHA'))
    for name in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        p.require(re.fullmatch(r'[1-9][0-9]*', os.environ.get(name, '')), 'Invalid workflow identity.')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    p.require(event.get('before') == PARENT and event.get('after') == sha
              and event.get('ref') == 'refs/heads/main' and event.get('forced') is False
              and event.get('deleted') is False and event.get('created') is False,
              'Not the fixed rebuild transition.')
    head = event.get('head_commit') or {}
    p.require(head.get('id') == sha and head.get('message') == MESSAGE, 'Wrong rebuild marker.')
    request = p.ROOT / REQUEST_PATH
    p.require(request.is_file() and not request.is_symlink()
              and json.loads(request.read_text(encoding='utf-8')) == REQUEST, 'Wrong rebuild request.')
    p.require(os.environ.get('SOURCE_REF', SOURCE_REF) == SOURCE_REF, 'Source ref override rejected.')
    p.require(os.environ.get('SOURCE_SHA') == SOURCE_SHA
              and os.environ.get('BUILD_VERSION') == VERSION, 'Source override rejected.')
    p.require(not os.environ.get('RELEASE_WRITE_TOKEN') and not os.environ.get('RELEASE_MODE'),
              'Release credentials and modes are forbidden.')


def prepare():
    p.require_secrets(['SOURCE_READ_TOKEN'])
    token = os.environ['SOURCE_READ_TOKEN']
    ref = p.api(f'/repos/{p.SOURCE}/git/ref/' + SOURCE_REF.removeprefix('refs/'), token)
    p.require(isinstance(ref, dict) and ref.get('ref') == SOURCE_REF
              and ref.get('object', {}).get('type') == 'commit'
              and ref['object']['sha'] == SOURCE_SHA, 'Candidate branch has moved; review the rebuild request.')
    p.require(p.remote_source_version(SOURCE_SHA, token) == VERSION, 'Source version changed.')
    # This endpoint cannot publish. Existing stable prepare/publish gates are untouched.
    p.output('source_sha', SOURCE_SHA)
    p.output('version', VERSION)
    p.output('apk_name', f'emosonic_android_v{VERSION}.apk')
    p.output('installer_name', p.installer_name(VERSION))
    print('Exact candidate source selected for a build-only same-version rebuild; no release publication.')


_stable_metadata = p.metadata


def candidate_metadata(candidate, sha, digest, platform='android'):
    data = _stable_metadata(candidate, sha, digest, platform)
    data.update(source_ref=SOURCE_REF, prerelease=True, mode='build-only', published=False)
    return data


def run(stage):
    p.require(stage in STAGES, 'Stage is not allowed in the build-only workflow.')
    context()
    original_metadata = p.metadata
    try:
        p.metadata = candidate_metadata
        if stage == 'prepare':
            prepare()
        else:
            getattr(p, stage)()
    finally:
        p.metadata = original_metadata


def main():
    try:
        p.require(len(sys.argv) == 2, 'Exactly one stage is required.')
        run(sys.argv[1])
    except p.GateError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    except Exception:
        print('ERROR: Rebuild failed; sensitive details suppressed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
