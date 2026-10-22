"""macOS-only Foundation serialization proof; no player, media, or network."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import native_seek_anchor_observation as timing

STAGE = 'native-anchor-bool-proof'
CASE_COUNT = 11
BASELINE_PAYLOAD_SHA256 = '4bdad8b89b6dddd3019df3ff149d7250f795b216a6222a269be6482691153782'
KEY = 'anchorSamePlaybackIdentity'
PHASES = frozenset(('platform', 'extract', 'compile', 'run', 'baseline', 'patched', 'reducer'))
REASONS = frozenset(('requires_macos', 'source_contract', 'compile_failed', 'execution_failed',
                     'invalid_output', 'wrong_json_type', 'wrong_json_value', 'wrong_reducer_result'))
SCHEMA = {
    'status': frozenset(('passed', 'failed')), 'phase': PHASES, 'reason': REASONS,
    'caseOrdinal': ('integer', 0, CASE_COUNT), 'caseCount': ('integer', 11, 11),
    'baselineNumericOne': ('integer', 1, 1), 'patchedBooleanTrue': ('integer', 1, 1),
    'patchedBooleanFalse': ('integer', 10, 10), 'reducerResidualIncluded': ('integer', 1, 1),
    'reducerResidualOmitted': ('integer', 21, 21),
}


class ProofFailure(Exception):
    def __init__(self, phase, reason, ordinal=0):
        assert phase in PHASES and reason in REASONS and type(ordinal) is int and 0 <= ordinal <= CASE_COUNT
        self.record = {'stage': STAGE, 'status': 'failed', 'phase': phase,
                       'reason': reason, 'caseOrdinal': ordinal}
        super().__init__('Bounded serialization proof failed')


def expressions():
    """Extract the exact boxed value, then prove the one-cast inverse by hash."""
    text = timing.payload('lab_timing_getters.inc')
    pattern = r'@"anchorSamePlaybackIdentity": (@\([^;]+?\)),\n        @"anchorPositionMs"'
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ProofFailure('extract', 'source_contract')
    corrected = matches[0].group(1)
    if not corrected.startswith('@((BOOL)(') or not corrected.endswith('))'):
        raise ProofFailure('extract', 'source_contract')
    original = '@(' + corrected[len('@((BOOL)('):-2] + ')'
    baseline = text[:matches[0].start(1)] + original + text[matches[0].end(1):]
    if timing.digest(baseline.encode('utf-8')) != BASELINE_PAYLOAD_SHA256:
        raise ProofFailure('extract', 'source_contract')
    return original, corrected


def source_text():
    original, corrected = expressions()
    template = '''
static id FUNCTION(unsigned ordinal) {
    NSObject *one = [NSObject new];
    NSObject *other = [NSObject new];
    id _labAnchorPlayer = one, _labAnchorSource = one, _labAnchorItem = one;
    id player = one, _audioSource = one, item = one;
    int _labAnchorIndex = 7, _index = 7;
    switch (ordinal) {
        case 1: player = other; break;
        case 2: _audioSource = other; break;
        case 3: item = other; break;
        case 4: _index = 8; break;
        case 5: _labAnchorPlayer = nil; break;
        case 6: _labAnchorSource = nil; break;
        case 7: _labAnchorItem = nil; break;
        case 8: player = nil; break;
        case 9: _audioSource = nil; break;
        case 10: item = nil; break;
        default: break;
    }
    return EXPRESSION;
}
'''
    body = '#import <Foundation/Foundation.h>\n#include <stdio.h>\n'
    body += template.replace('FUNCTION', 'baseline').replace('EXPRESSION', original)
    body += template.replace('FUNCTION', 'corrected').replace('EXPRESSION', corrected)
    body += '''
int main(void) {
    @autoreleasepool {
        NSMutableArray *before = [NSMutableArray array], *after = [NSMutableArray array];
        for (unsigned ordinal = 0; ordinal < 11; ++ordinal) {
            [before addObject:baseline(ordinal)];
            [after addObject:corrected(ordinal)];
        }
        NSData *data = [NSJSONSerialization dataWithJSONObject:@{ @"baseline": before, @"patched": after }
            options:0 error:NULL];
        if (!data) return 2;
        return fwrite(data.bytes, 1, data.length, stdout) == data.length ? 0 : 3;
    }
}
'''
    return body


def _reducer_snapshot(value):
    return {'sampledAtMs': 1000400, 'positionMs': 10450, 'timingObservation': {
        'samplerCalls': 1, 'samplerAdmits': 1, 'samplerRejects': [0] * 7,
        'seekInvocations': 0, 'seekCallbacks': 0, 'seekCompletions': 0,
        'unmatchedCallbacks': 0, 'duplicateCallbacks': 0, 'seeks': [],
        'anchorPositionMs': 10000, 'anchorWallMs': 1000100, 'anchorRequestedRate': 1.5,
        'anchorSamePlaybackIdentity': value}}


def validate_output(raw):
    if type(raw) is not dict or set(raw) != {'baseline', 'patched'}:
        raise ProofFailure('run', 'invalid_output')
    if any(type(raw[k]) is not list or len(raw[k]) != CASE_COUNT for k in raw):
        raise ProofFailure('run', 'invalid_output')
    for index in range(CASE_COUNT):
        before, after = raw['baseline'][index], raw['patched'][index]
        if type(before) is not int:
            raise ProofFailure('baseline', 'wrong_json_type', index + 1)
        if before != int(index == 0):
            raise ProofFailure('baseline', 'wrong_json_value', index + 1)
        if type(after) is not bool:
            raise ProofFailure('patched', 'wrong_json_type', index + 1)
        if after is not (index == 0):
            raise ProofFailure('patched', 'wrong_json_value', index + 1)
        for value, available in ((before, False), (after, index == 0)):
            anchor = timing.summarize(_reducer_snapshot(value))['lastAdmittedAnchor']
            if (anchor['samePlaybackIdentity'] is not available or
                    ('nativeMinusAnchorProjectionMs' in anchor) is not available):
                raise ProofFailure('reducer', 'wrong_reducer_result', index + 1)
    return {'stage': STAGE, 'status': 'passed', 'caseCount': CASE_COUNT,
            'baselineNumericOne': 1, 'patchedBooleanTrue': 1, 'patchedBooleanFalse': 10,
            'reducerResidualIncluded': 1, 'reducerResidualOmitted': 21}


def child_environment(directory):
    env = dict(os.environ)
    for name in ('GITHUB_ENV', 'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY'):
        env.pop(name, None)
    env['TMPDIR'] = str(directory)
    return env


def prove():
    if sys.platform != 'darwin':
        raise ProofFailure('platform', 'requires_macos')
    source = source_text()
    with tempfile.TemporaryDirectory(prefix='native-anchor-bool-') as temporary:
        root = Path(temporary).resolve(strict=True)
        path, binary = root / 'proof.m', root / 'proof'
        path.write_text(source, encoding='utf-8')
        env = child_environment(root)
        try:
            result = subprocess.run(['/usr/bin/xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra',
                                     '-Werror', '-framework', 'Foundation', str(path), '-o', str(binary)],
                                    env=env, cwd=root, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            raise ProofFailure('compile', 'compile_failed') from None
        if result.returncode != 0:
            raise ProofFailure('compile', 'compile_failed')
        try:
            result = subprocess.run([str(binary)], env=env, cwd=root, capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            raise ProofFailure('run', 'execution_failed') from None
        if result.returncode != 0:
            raise ProofFailure('run', 'execution_failed')
        if len(result.stdout) > 4096 or result.stderr:
            raise ProofFailure('run', 'invalid_output')
        try:
            raw = json.loads(result.stdout)
        except (UnicodeError, ValueError):
            raise ProofFailure('run', 'invalid_output') from None
        return validate_output(raw)


def main():
    try:
        result = prove()
    except ProofFailure as failure:
        result = failure.record
    except Exception:
        result = ProofFailure('extract', 'source_contract').record
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
