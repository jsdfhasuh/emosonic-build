"""Draft: disposable native observation only; never changes playback controls."""
import ast
import hashlib
import math
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SOURCE_SHA = 'dca06e757b9d71663e3ffc7d8841775910fefe41'
EXPECTED = {
    'AudioPlayer.h': '6b48fdf8e6bf67849126224151470cb8932d432f2dffd7e6fd8d09ef85796cb2',
    'AudioPlayer.m': 'dfc408d533c30fe95b8d0a9ad2284f2266fdbaba3377da2bde372fcaad4441c7',
}
PREPARE_SHA = 'dfdd215375ac1afd5a90e278733f5ca1a1ef5683317f95526933b5b6fe758532'
HARNESS_SHA = '55ba43b3d08fe525677c544f2dc583cb5aef05699b23ee63a98f01a18aacbb0f'
LAB_ROOT = 'tool/native_playback_mac'
PREPARE = LAB_ROOT + '/prepare_build.py'
HARNESS = LAB_ROOT + '/run_lab.py'
COPIED_HELPER = LAB_ROOT + '/native_seek_anchor_observation.py'
STATE = '.native_timing_observation/manifest.json'
PAYLOAD_DIRECTORY = 'native_seek_anchor_observation_payload'
AFTER = {'tool/native_playback_mac/prepare_build.py': 'a7aea3aa0530bcd6a39c2e91788a4712093f02570ab631790f4d36dd550a6593', 'tool/native_playback_mac/run_lab.py': '44da20c4a134df49d857b800185a287eb8764e4a6563553ff9f89fc0acda59bc'}
NATIVE_AFTER = {'AudioPlayer.h': '007d2925fa33997665d64c0a4e1dd6a74c0b21d69f746eae722e5de48b070201', 'AudioPlayer.m': '6e09059b4440a82c4f6d0e86beb37c38245c714a1f3a9163612d5218766b77e3'}
REJECTION_NAMES = ('budget_or_clock', 'not_healthy', 'primary_identity',
                   'no_timebase', 'effective_rate', 'read_clock', 'capture_quality')
PAYLOAD_HASHES = {'lab_timing_getters.inc': 'a7af57b018ccd066f48a7f3215bc20e1ed4353dd21f03720c6605e8e87afcecb', 'lab_timing_native.inc': 'c296f47b02e340d0185daa4277464dca27f77a003ad0cfff88079c7981e79f00', 'lab_timing_state.h': '546e1c25720f424a1d7353a28700058e1a30734e22f328761663501cc4d51abd'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(name):
    path = ROOT / PAYLOAD_DIRECTORY / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('Observation payload unavailable')
    data = path.read_bytes()
    if not PAYLOAD_HASHES or digest(data) != PAYLOAD_HASHES.get(name):
        raise ValueError('Observation payload pin mismatch')
    return data.decode('utf-8')


class Transform:
    """Reversal is byte-exact, not a claim based merely on matching asserts."""
    def __init__(self, text):
        self.before = text
        self.text = text
        self.operations = []

    def once(self, old, new):
        if self.text.count(old) != 1 or old == new:
            raise ValueError('Observation anchor is ambiguous')
        self.text = self.text.replace(old, new, 1)
        self.operations.append((old, new))

    def finish(self):
        restored = self.text
        for old, new in reversed(self.operations):
            if restored.count(new) != 1:
                raise ValueError('Observation inverse is ambiguous')
            restored = restored.replace(new, old, 1)
        if restored != self.before:
            raise ValueError('Observation source roundtrip failed')
        return self.text


def _sample_transform(method):
    change = Transform(method)
    header = '- (void)samplePositionAnchor {\n'
    change.once(header, header + '    LabTimingIncrement(&_labTiming.samplerCalls);\n')
    # Only return statements at the seven existing guard exits are replaced.
    if change.text.count('return;') != 7:
        raise ValueError('Sampler guard count changed')
    original = change.text
    counter = iter(range(7))
    changed = re.sub(r'\breturn;', lambda _: 'do { LabTimingIncrement(&_labTiming.samplerRejects['
                     + str(next(counter)) + ']); return; } while (0);', original)
    change.once(original, changed)
    anchor = '''            CFRelease(timebase);
            do { LabTimingIncrement(&_labTiming.samplerRejects[4]); return; } while (0);'''
    change.once(anchor, '''            _labTiming.rejectedRequestedRate = requestedRate;
            _labTiming.rejectedNativeRate = actualRate;
            _labTiming.rejectedEffectiveRate = effectiveRate;
''' + anchor)
    anchor = '        _updatePosition = (int)positionMs;'
    change.once(anchor, '''        LabTimingIncrement(&_labTiming.samplerAdmits);
        _labTiming.anchorPositionMs = positionMs;
        _labTiming.anchorWallMs = sampledWall;
        _labTiming.anchorRequestedRate = requestedRate;
        _labTiming.anchorNativeRate = actualRate;
        _labTiming.anchorEffectiveRate = effectiveRate;
        _labTiming.anchorElapsedMs = elapsedMs;
        _labAnchorPlayer = player;
        _labAnchorSource = source;
        _labAnchorItem = item;
        _labAnchorIndex = index;
''' + anchor)
    change.once('        _updatePosition = (int)positionMs;', """        unsigned labOwner = [self labClockOwnerForPlayer:player item:item];
        LabTimingRates labRates = {.requestedRate=requestedRate, .nativeRate=actualRate, .effectiveRate=effectiveRate,
            .effectiveAvailable=true, .effectiveReadCount=2, .identityMatches=labOwner>0, .playingIntent=true, .seeking=false,
            .processingState=(int)ready, .timeControl=(int)AVPlayerTimeControlStatusPlaying, .owner=labOwner,
            .wallBeforeMs=wallBefore, .wallAfterMs=wallAfter, .monoBeforeMs=readStarted*1000.0, .monoAfterMs=ended*1000.0};
        LabClockPoint labPoint = {.owner=labOwner, .positionMs=positionMs, .positionValid=labOwner>0,
            .wallBeforeMs=wallBefore, .wallAfterMs=sampledWall, .monoBeforeMs=readStarted*1000.0,
            .monoAfterMs=sampledMonotonic*1000.0, .rates=labRates};
        [self labStoreClockPoint:labPoint anchor:YES];
        _updatePosition = (int)positionMs;""")
    return change.finish()


def _implementation_transform(text):
    change = Transform(text)
    anchor = '@implementation AudioPlayer {'
    helpers = payload('lab_timing_state.h') + '\n' + payload('lab_timing_native.inc') + '\n'
    change.once(anchor, helpers + anchor + '''\n    LabTimingState _labTiming;
    __weak AVQueuePlayer *_labAnchorPlayer;
    __weak AudioSource *_labAnchorSource;
    __weak AVPlayerItem *_labAnchorItem;
    int _labAnchorIndex;
    LabClockState _labClock;
    __weak AVQueuePlayer *_labClockPlayer;
    __weak AudioSource *_labClockSource;
    __weak AVPlayerItem *_labClockItem;
    int _labClockIndex;''')
    anchor = '- (float)speed {\n    return _speed;\n}'
    change.once(anchor, anchor + '\n\n' + payload('lab_timing_getters.inc'))
    start = change.text.index('- (void)samplePositionAnchor {')
    end = change.text.index('\n#endif', start)
    method = change.text[start:end]
    change.once(method, _sample_transform(method))
    anchor = '        [_indexedAudioSources[_index] seek:position completionHandler:^(BOOL finished) {\n'
    change.once(anchor, '''        __weak AVQueuePlayer *labTimingPlayer = _player;
        __weak AudioSource *labTimingSource = _audioSource;
        __weak AVPlayerItem *labTimingItem = _player.currentItem;
        int labTimingIndex = _index;
        unsigned labTimingSequence = [self labObserveSeekInvocation:position player:labTimingPlayer source:labTimingSource item:labTimingItem index:labTimingIndex];
''' + anchor + '            [self labObserveSeekCallback:labTimingSequence];\n')
    anchor = '''            self->_seekPos = kCMTimeInvalid;
            [self broadcastPlaybackEvent];
            if (completionHandler) {'''
    change.once(anchor, '''            self->_seekPos = kCMTimeInvalid;
            [self broadcastPlaybackEvent];
            [self labObserveSeekCompletion:labTimingSequence finished:finished player:labTimingPlayer source:labTimingSource item:labTimingItem index:labTimingIndex];
            if (completionHandler) {''')
    change.once('- (void)setSpeed:(float)speed {\n', '- (void)setSpeed:(float)speed {\n' + """    __weak AVQueuePlayer *labRatePlayer = _player;
    __weak AudioSource *labRateSource = _audioSource;
    __weak AVPlayerItem *labRateItem = _player.currentItem;
    int labRateIndex = _index;
    unsigned labRateSequence = [self labObserveRateInvocation:speed player:labRatePlayer source:labRateSource item:labRateItem index:labRateIndex];
""")
    change.once('    [self updatePosition];\n}\n\n- (void)setLoopMode:', """    [self updatePosition];
    [self labObserveRateReturn:labRateSequence player:labRatePlayer source:labRateSource item:labRateItem index:labRateIndex];
}

- (void)setLoopMode:""")
    old = '            [self setSpeed:(float)[request[@"speed"] doubleValue]];\n            result(@{});'
    change.once(old, """            unsigned labRateBefore = _labClock.rates;
            [self setSpeed:(float)[request[@"speed"] doubleValue]];
            unsigned labReplySequence = _labClock.rates == labRateBefore + 1 ? _labClock.rates : 0;
            [self labObserveRateReply:labReplySequence returned:NO];
            result(@{});
            [self labObserveRateReply:labReplySequence returned:YES];""")
    result = change.finish()
    # Extra rate reads are event-bound; no added position reads or polling.
    if result.count('indexedSource.position') != text.count('indexedSource.position'):
        raise ValueError('Observation added a position read')
    return result


def transform_native(header, implementation):
    originals = {'AudioPlayer.h': header, 'AudioPlayer.m': implementation}
    if any(digest(data) != EXPECTED[name] for name, data in originals.items()):
        raise ValueError('Observation native source pin mismatch')
    change = Transform(header.decode('utf-8'))
    anchor = '@property (readonly, nonatomic) float speed;'
    change.once(anchor, anchor + '\n- (NSDictionary *)labTimingObservationForPlayer:(AVQueuePlayer *)player item:(AVPlayerItem *)item;' +
        '\n- (unsigned)labClockOwnerForPlayer:(AVQueuePlayer *)player item:(AVPlayerItem *)item;' +
        '\n- (void)labObserveNativePosition:(CMTime)position player:(AVQueuePlayer *)player item:(AVPlayerItem *)item owner:(unsigned)owner wallBefore:(double)wallBefore wallAfter:(double)wallAfter monoBefore:(double)monoBefore monoAfter:(double)monoAfter;')
    updated = {'AudioPlayer.h': change.finish().encode('utf-8'),
               'AudioPlayer.m': _implementation_transform(implementation.decode('utf-8')).encode('utf-8')}
    return updated


def instrument_native_timing(target):
    """Called ONLY after the existing copied-source seek getters are installed."""
    base = Path(target) / 'darwin/just_audio/Sources/just_audio'
    paths = {'AudioPlayer.h': base / 'include/just_audio/AudioPlayer.h',
             'AudioPlayer.m': base / 'AudioPlayer.m'}
    for path in paths.values():
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Observation native path refused')
    originals = {name: path.read_bytes() for name, path in paths.items()}
    updated = transform_native(originals['AudioPlayer.h'], originals['AudioPlayer.m'])
    if {name: digest(data) for name, data in updated.items()} != NATIVE_AFTER:
        raise ValueError('Observation native output pin mismatch')
    for name, path in paths.items():
        path.write_bytes(updated[name])
    return {name: {'before': EXPECTED[name], 'after': digest(data)} for name, data in updated.items()}


def patch_prepare(original):
    """Returns draft builder bytes; caller owns copy/manifest integration."""
    if digest(original) != PREPARE_SHA:
        raise ValueError('Observation builder source pin mismatch')
    change = Transform(original.decode('utf-8'))
    change.once('import hashlib\n', 'import hashlib\nfrom native_seek_anchor_observation import instrument_native_timing\n')
    anchor = '    seek_sources = instrument_seek_observability(target)\n'
    change.once(anchor, anchor + '''    timing_manifest = build_root / 'timing-observability.json'
    if timing_manifest.exists() or timing_manifest.is_symlink():
        raise RuntimeError('Native timing manifest already exists')
    timing_sources = instrument_native_timing(target)
    for name in seek_sources:
        if seek_sources[name]['after'] != timing_sources[name]['before']:
            raise RuntimeError('Native observation chain mismatch')
    timing_manifest.write_text(json.dumps({'readOnlyPlaybackObservation': True, 'files': timing_sources}), encoding='utf-8')
''')
    anchor = '                @"requestedRate": @(wrapper.speed),\n'
    change.once(anchor, anchor + '                @"timingObservation": [wrapper labTimingObservationForPlayer:engine item:item],\n')
    anchor = '            NSTimeInterval started = [[NSDate date] timeIntervalSince1970] * 1000.0;\n'
    change.once(anchor, '            unsigned labClockOwner = [wrapper labClockOwnerForPlayer:engine item:engine.currentItem];\n' +
        '            double labMonoStarted = [NSProcessInfo processInfo].systemUptime * 1000.0;\n' + anchor)
    anchor = '            NSTimeInterval ended = [[NSDate date] timeIntervalSince1970] * 1000.0;\n'
    change.once(anchor, anchor + '            double labMonoEnded = [NSProcessInfo processInfo].systemUptime * 1000.0;\n' +
        '            [wrapper labObserveNativePosition:position player:engine item:item owner:labClockOwner wallBefore:started wallAfter:ended monoBefore:labMonoStarted monoAfter:labMonoEnded];\n')
    result = change.finish()
    if result.count('engine.currentTime') != original.decode('utf-8').count('engine.currentTime'):
        raise ValueError('Native observation added a media position read')
    ast.parse(result)
    return result.encode('utf-8')


def _checked(repo, relative, *, fresh=False):
    repo = Path(repo)
    path = repo / relative
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Observation source symlink refused')
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError('Observation source containment refused')
    if fresh:
        if path.exists(): raise ValueError('Observation path is not fresh')
    elif not path.is_file():
        raise ValueError('Observation source unavailable')
    return path


def expected_manifest():
    return {
        'status': 'prepared', 'productionRepositoryMutation': False,
        'disposableOnly': True, 'originalHarnessAstUnchanged': True,
        'noAdditionalPositionRead': True, 'eventBoundTimebaseRateObservation': True,
        'nativeBaseSourceSha': SOURCE_SHA,
        'files': {
            PREPARE: {'before': PREPARE_SHA, 'after': AFTER[PREPARE]},
            HARNESS: {'before': HARNESS_SHA, 'after': AFTER[HARNESS]},
        },
        'helperSha256': digest(Path(__file__).read_bytes()),
        'payloads': PAYLOAD_HASHES,
        'native': {name: {'before': EXPECTED[name], 'after': NATIVE_AFTER[name]} for name in EXPECTED},
    }


def apply(repo):
    """After readiness/lifecycle, before attribution. Disposable source only."""
    before = {name: _checked(repo, name).read_bytes() for name in (PREPARE, HARNESS)}
    updates = {PREPARE: patch_prepare(before[PREPARE]), HARNESS: patch_harness(before[HARNESS])}
    if {name: digest(data) for name, data in updates.items()} != AFTER:
        raise ValueError('Observation source output pin mismatch')
    for name in PAYLOAD_HASHES: payload(name)
    state = _checked(repo, '.native_timing_observation', fresh=True)
    helper = _checked(repo, COPIED_HELPER, fresh=True)
    directory = _checked(repo, LAB_ROOT + '/' + PAYLOAD_DIRECTORY, fresh=True)
    state.mkdir(); directory.mkdir()
    for name, data in updates.items(): _checked(repo, name).write_bytes(data)
    helper.write_bytes(Path(__file__).read_bytes())
    for name in PAYLOAD_HASHES:
        (directory / name).write_text(payload(name), encoding='utf-8')
    manifest = expected_manifest()
    (state / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
    return manifest


def verify_prepared(repo, require_harness=True):
    if type(require_harness) is not bool:
        raise ValueError('Observation verification mode refused')
    if not _manifest_equal(json.loads(_checked(repo, STATE).read_text()), expected_manifest()):
        raise ValueError('Observation manifest mismatch')
    for name in (PREPARE, HARNESS) if require_harness else (PREPARE,):
        if digest(_checked(repo, name).read_bytes()) != AFTER[name]:
            raise ValueError('Observation prepared source mismatch')
    if digest(_checked(repo, COPIED_HELPER).read_bytes()) != expected_manifest()['helperSha256']:
        raise ValueError('Observation copied helper mismatch')
    for name, expected in PAYLOAD_HASHES.items():
        payload(name)
        if digest(_checked(repo, LAB_ROOT + '/' + PAYLOAD_DIRECTORY + '/' + name).read_bytes()) != expected:
            raise ValueError('Observation copied payload mismatch')
    return {'status': 'verified'}


def _manifest_equal(actual, expected):
    return type(actual) is dict and json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False)


def verify_compiled(repo):
    verify_prepared(repo, require_harness=False)
    base = '.native_mac_lab/just_audio/darwin/just_audio/Sources/just_audio/'
    paths = {'AudioPlayer.h': base + 'include/just_audio/AudioPlayer.h', 'AudioPlayer.m': base + 'AudioPlayer.m'}
    for name, relative in paths.items():
        if digest(_checked(repo, relative).read_bytes()) != NATIVE_AFTER[name]:
            raise ValueError('Observation compiled source mismatch')
    timing = {'readOnlyPlaybackObservation': True, 'files': {
        name: {'before': EXPECTED[name], 'after': NATIVE_AFTER[name]} for name in EXPECTED}}
    if not _manifest_equal(json.loads(_checked(repo, '.native_mac_lab/timing-observability.json').read_text()), timing):
        raise ValueError('Observation compiled manifest mismatch')
    original = {'AudioPlayer.h': 'c8c6df3bc07f10677e0afbeb447c88da2a704b2c8323769247f78768c6a43138',
                'AudioPlayer.m': 'ecec29e1f913f0dca944ca3fb2e45a7ad96a138391af59f99ca3f46dfd5b65b3'}
    seek = {'readOnly': True, 'files': {name: {'before': original[name], 'after': EXPECTED[name]} for name in original}}
    if not _manifest_equal(json.loads(_checked(repo, '.native_mac_lab/seek-observability.json').read_text()), seek):
        raise ValueError('Observation original getter chain mismatch')
    return {'status': 'verified'}


def summarize_state(state, previous=None, elapsed_ms=None, paired_state=None):
    """Reuse the existing sample, never call its assertive decoder or poll."""
    if type(state) is not dict:
        return {'status': 'unavailable'}
    native = state.get('nativePlayers')
    if type(native) is not list or len(native) != 1 or type(native[0]) is not dict:
        return {'status': 'unavailable'}
    try:
        result = summarize(native[0], state)
        if elapsed_ms is not None:
            result['clockHistory'] = clock_history(previous, state, native[0], elapsed_ms, paired_state)
        return result
    except (ArithmeticError, KeyError, TypeError, ValueError):
        return {'status': 'malformed'}


def patch_harness(original):
    if digest(original) != HARNESS_SHA:
        raise ValueError('Observation harness source pin mismatch')
    change = Transform(original.decode('utf-8'))
    change.once('import argparse\n', 'import argparse\nfrom native_seek_anchor_observation import summarize_state\n')
    anchor = '''            authority, follower = states[authority_index], states[2]
            assert follow_correction_identity(states, authority_index, context) == correction_identity'''
    addition = '''            self.rate_measurement['nativeTiming'] = {
                'authority': summarize_state(authority, self.rate_measurement.get('nativeTiming', {}).get('authority'), (time.monotonic() - started) * 1000, follower),
                'follower': summarize_state(follower, self.rate_measurement.get('nativeTiming', {}).get('follower'), (time.monotonic() - started) * 1000, authority),
            }
'''
    change.once(anchor, anchor.replace('            assert ', addition + '            assert ', 1))
    result = change.finish()
    # Remove only the new import and one new observational assignment. The full
    # original AST, including every assertion/control/deadline, must be equal.
    class Projection(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None if node.module == 'native_seek_anchor_observation' else node
        def visit_Assign(self, node):
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript)
                    and ast.unparse(node.targets[0]) == "self.rate_measurement['nativeTiming']"):
                return None
            return node
    projected = Projection().visit(ast.parse(result))
    if ast.dump(projected, include_attributes=False) != ast.dump(ast.parse(original), include_attributes=False):
        raise ValueError('Observation changed original harness AST')
    return result.encode('utf-8')


def restore_harness(observed):
    """Reverse only this fixed observation layer, never write source bytes."""
    text = observed.decode('utf-8')
    imported = 'from native_seek_anchor_observation import summarize_state\n'
    addition = '''            self.rate_measurement['nativeTiming'] = {
                'authority': summarize_state(authority, self.rate_measurement.get('nativeTiming', {}).get('authority'), (time.monotonic() - started) * 1000, follower),
                'follower': summarize_state(follower, self.rate_measurement.get('nativeTiming', {}).get('follower'), (time.monotonic() - started) * 1000, authority),
            }
'''
    if text.count(imported) != 1 or text.count(addition) != 1:
        raise ValueError('Observation harness inverse anchors changed')
    original = text.replace(imported, '', 1).replace(addition, '', 1).encode('utf-8')
    if digest(original) != HARNESS_SHA or patch_harness(original) != observed:
        raise ValueError('Observation harness inverse pin mismatch')
    return original


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _rates(raw):
    if type(raw) is not dict:
        return None
    fields = ('wallBeforeMs', 'wallAfterMs', 'monoBeforeMs', 'monoAfterMs')
    if not all(number(raw.get(key), 0, 1e15) for key in fields):
        return None
    wall = raw['wallAfterMs'] - raw['wallBeforeMs']
    mono = raw['monoAfterMs'] - raw['monoBeforeMs']
    if not 0 <= mono <= 1000 or not 0 <= wall <= 1000 or abs(wall - mono) > 2:
        return None
    result = {'captureElapsedMs': mono, 'clockBracketConsistent': True,
              'effectiveRateStatus': 'unavailable',
              'samePlaybackIdentity': raw.get('identityMatches') is True}
    if type(raw.get('effectiveReadCount')) is int and 0 <= raw['effectiveReadCount'] <= 2:
        result['effectiveRateReadCount'] = raw['effectiveReadCount']
        result['effectiveRateReadBasis'] = 'existing_sampler_locals' if raw['effectiveReadCount'] == 2 else 'event_bound_capture'
    if raw.get('identityMatches') is not True:
        result['effectiveRateStatus'] = 'unavailable_identity_changed'
        return result
    for key in ('requestedRate', 'nativeRate'):
        if number(raw.get(key), -2, 4):
            result[key] = raw[key]
    if raw.get('effectiveAvailable') is True and number(raw.get('effectiveRate'), -2, 4):
        result['effectiveRateStatus'] = 'available'
        result['effectiveRate'] = raw['effectiveRate']
        if 'nativeRate' in result:
            result['positiveNominalRateWithHeldClock'] = result['nativeRate'] > 0 and raw['effectiveRate'] == 0
    for key in ('playingIntent', 'seeking'):
        if type(raw.get(key)) is bool: result[key] = raw[key]
    for old, new, low, high in (('owner', 'nativeOwnerOrdinal', 0, 65535),
            ('processingState', 'processingState', 0, 4), ('timeControl', 'timeControl', -1, 2),
            ('effectiveReadCount', 'effectiveRateReadCount', 0, 2)):
        if type(raw.get(old)) is int and low <= raw[old] <= high: result[new] = raw[old]
    return result


def summarize(native, dart_state=None):
    """Private timestamps enter; only explicit finite observations leave."""
    raw = native.get('timingObservation') if type(native) is dict else None
    if type(raw) is not dict:
        return {'status': 'unavailable'}
    counts = ('samplerCalls', 'samplerAdmits', 'seekInvocations', 'seekCallbacks',
              'seekCompletions', 'unmatchedCallbacks', 'duplicateCallbacks')
    rejects = raw.get('samplerRejects')
    if (not all(type(raw.get(k)) is int and 0 <= raw[k] <= 65535 for k in counts)
            or type(rejects) is not list or len(rejects) != 7
            or not all(type(v) is int and 0 <= v <= 65535 for v in rejects)):
        return {'status': 'malformed'}
    result = {'status': 'observed', **{k: raw[k] for k in counts},
              'samplerRejects': dict(zip(REJECTION_NAMES, rejects)),
              'counterCapReached': any(raw[k] == 65535 for k in counts) or 65535 in rejects,
              'seekScope': 'same_item_native_only',
              'desiredTimelineAgeStatus': 'unavailable',
              'seekRecordsDropped': max(0, raw['seekInvocations'] - 16),
              'seekRecords': []}
    result['clockObservation'] = clock_observation(raw.get('clockObservation'))
    at = native.get('sampledAtMs')
    records = raw.get('seeks')
    expected_sequences = list(range(max(1, raw['seekInvocations'] - 15), raw['seekInvocations'] + 1))
    if (type(records) is not list or len(records) != len(expected_sequences)
            or any(type(row) is not dict or row.get('sequence') != sequence
                   for row, sequence in zip(records, expected_sequences))):
        result['seekRecordCoverage'] = 'malformed'
        return result
    result['seekRecordCoverage'] = 'tail' if raw['seekInvocations'] > 16 else 'complete'
    for record in records:
        if (type(record) is not dict or type(record.get('sequence')) is not int
                or not 1 <= record['sequence'] <= raw['seekInvocations']):
            result['seekRecordCoverage'] = 'malformed'; continue
        entry = {'sequence': record['sequence']}
        if number(record.get('targetMs'), 0, 86400000):
            entry['requestedTargetMs'] = record['targetMs']
        invocation = record.get('invocation')
        begin = _rates(invocation)
        if begin is None:
            entry['status'] = 'invalid_clock_bracket'
            result['seekRecords'].append(entry); continue
        entry.update(status='pending', invocation=begin)
        if number(at, 0, 1e15):
            age = at - (invocation['wallBeforeMs'] + invocation['wallAfterMs']) / 2
            if number(age, -1000, 600000): entry['invocationAgeMs'] = age
        if record.get('callbackSeen') is True and number(record.get('callbackMonoMs'), 0, 1e15):
            delay = record['callbackMonoMs'] - invocation['monoAfterMs']
            callback_wall = record.get('callbackWallMs')
            coherent = (number(delay, 0, 600000) and number(callback_wall, 0, 1e15)
                        and abs(callback_wall - invocation['wallAfterMs'] - delay) <= 2)
            entry['callbackClockConsistent'] = bool(coherent)
            if coherent: entry['callbackAfterInvocationMs'] = delay
        if record.get('completionSeen') is True:
            completion = record.get('completion')
            end = _rates(completion)
            if end is None:
                entry['status'] = 'invalid_clock_bracket'
            else:
                elapsed = completion['monoBeforeMs'] - invocation['monoAfterMs']
                wall_elapsed = completion['wallBeforeMs'] - invocation['wallAfterMs']
                consistent = number(elapsed, 0, 600000) and abs(wall_elapsed - elapsed) <= 2
                entry['intervalClockConsistent'] = bool(consistent)
                entry['status'] = 'completed' if consistent else 'invalid_clock_bracket'
                entry['completion'] = end
                if type(record.get('finished')) is bool: entry['finished'] = record['finished']
                if consistent:
                    entry['completionAfterInvocationMs'] = elapsed
                    entry['observationBracketMs'] = begin['captureElapsedMs'] + end['captureElapsedMs']
        for flag, field, dest, basis in (('firstNativeSeen','firstNative','firstNativeObservation','item_current_time'),
                ('firstAnchorSeen','firstAnchor','firstAdmittedAnchor','source_relative_sampler')):
            entry[dest+'Status'] = 'unavailable'
            if record.get(flag) is True:
                point = clock_point(record.get(field), invocation['monoAfterMs'], invocation['wallAfterMs'], basis)
                valid = (point is not None and point['nativeOwnerOrdinal'] > 0 and
                    point['nativeOwnerOrdinal'] == begin.get('nativeOwnerOrdinal') == entry.get('completion', {}).get('nativeOwnerOrdinal') and
                    point['seekInvocationOrdinal'] == record['sequence'])
                entry[dest+'Status'] = 'observed' if valid else 'invalid_record'
                if valid: entry[dest] = point
        result['seekRecords'].append(entry)
    if raw['samplerAdmits']:
        anchor = {'samePlaybackIdentity': raw.get('anchorSamePlaybackIdentity') is True}
        for old, new, low, high in (
                ('anchorPositionMs', 'positionMs', 0, 86400000),
                ('anchorRequestedRate', 'requestedRate', 0, 4),
                ('anchorNativeRate', 'nativeRate', 0, 4),
                ('anchorEffectiveRate', 'effectiveRate', 0, 4),
                ('anchorElapsedMs', 'captureElapsedMs', 0, 1000)):
            if number(raw.get(old), low, high): anchor[new] = raw[old]
        if number(at, 0, 1e15) and number(raw.get('anchorWallMs'), 0, 1e15):
            age = at - raw['anchorWallMs']
            if number(age, -1000, 600000): anchor['ageAtNativeSnapshotMs'] = age
            if (anchor['samePlaybackIdentity'] and number(age, 0, 600000) and 'positionMs' in anchor and 'requestedRate' in anchor
                    and number(native.get('positionMs'), 0, 86400000)):
                residual = native['positionMs'] - anchor['positionMs'] - age * anchor['requestedRate']
                if number(residual, -86400000, 86400000):
                    anchor['nativeMinusAnchorProjectionMs'] = residual
        if anchor['samePlaybackIdentity'] and type(dart_state) is dict and 'positionMs' in anchor:
            event_at, event_position = dart_state.get('eventUpdatedAtMs'), dart_state.get('eventPositionMs')
            if number(event_at, 0, 1e15) and number(event_position, 0, 86400000):
                delta = event_at - raw.get('anchorWallMs', -1)
                if number(delta, -600000, 600000): anchor['dartEventMinusAnchorTimeMs'] = delta
                residual = event_position - anchor['positionMs']
                if number(residual, -86400000, 86400000): anchor['dartEventMinusAnchorPositionMs'] = residual
        result['lastAdmittedAnchor'] = anchor
    if rejects[4]:
        result['lastEffectiveRateRejection'] = {
            new: raw[old] for old, new in (
                ('rejectedRequestedRate', 'requestedRate'), ('rejectedNativeRate', 'nativeRate'),
                ('rejectedEffectiveRate', 'effectiveRate')) if number(raw.get(old), -2, 4)}
    return result


RATE_SCHEMA = {
    'captureElapsedMs': ('number', 0, 1000), 'clockBracketConsistent': bool,
    'requestedRate': ('number', -2, 4), 'nativeRate': ('number', -2, 4),
    'effectiveRate': ('number', -2, 4),
    'effectiveRateStatus': frozenset(('available', 'unavailable', 'unavailable_identity_changed')),
    'samePlaybackIdentity': bool,
    'positiveNominalRateWithHeldClock': bool,
}
SCHEMA = {
    'status': frozenset(('observed', 'unavailable', 'malformed')),
    **{key: ('integer', 0, 65535) for key in (
        'samplerCalls', 'samplerAdmits', 'seekInvocations', 'seekCallbacks',
        'seekCompletions', 'unmatchedCallbacks', 'duplicateCallbacks', 'seekRecordsDropped')},
    'samplerRejects': {key: ('integer', 0, 65535) for key in REJECTION_NAMES},
    'counterCapReached': bool, 'seekScope': frozenset(('same_item_native_only',)),
    'desiredTimelineAgeStatus': frozenset(('unavailable',)),
    'seekRecordCoverage': frozenset(('complete', 'tail', 'malformed')),
    'seekRecords': ('list', {
        'sequence': ('integer', 1, 65535), 'requestedTargetMs': ('number', 0, 86400000),
        'status': frozenset(('pending', 'completed', 'invalid_clock_bracket')),
        'invocation': RATE_SCHEMA, 'completion': RATE_SCHEMA,
        'invocationAgeMs': ('number', -1000, 600000), 'finished': bool,
        'callbackAfterInvocationMs': ('number', 0, 600000), 'callbackClockConsistent': bool,
        'intervalClockConsistent': bool, 'completionAfterInvocationMs': ('number', 0, 600000),
        'observationBracketMs': ('number', 0, 2000),
    }, 16),
    'lastAdmittedAnchor': {
        'samePlaybackIdentity': bool,
        'positionMs': ('number', 0, 86400000), 'requestedRate': ('number', 0, 4),
        'nativeRate': ('number', 0, 4), 'effectiveRate': ('number', 0, 4),
        'captureElapsedMs': ('number', 0, 1000), 'ageAtNativeSnapshotMs': ('number', -1000, 600000),
        'nativeMinusAnchorProjectionMs': ('number', -86400000, 86400000),
        'dartEventMinusAnchorTimeMs': ('number', -600000, 600000),
        'dartEventMinusAnchorPositionMs': ('number', -86400000, 86400000),
    },
    'lastEffectiveRateRejection': {key: ('number', -2, 4) for key in ('requestedRate', 'nativeRate', 'effectiveRate')},
}


# No cross-layer clock origins or continuous-hold/causal inference are assumed.
def clock_point(raw, base_mono, base_wall, basis):
    if type(raw) is not dict or not all(type(raw.get(k)) is int and 0 <= raw[k] <= 65535
            for k in ('sequence', 'owner', 'rateSequence', 'seekSequence')) or not raw['sequence']:
        return None
    bracket = _rates({**raw, 'identityMatches': raw.get('owner', 0) > 0})
    if bracket is None: return None
    mono = (raw['monoBeforeMs'] + raw['monoAfterMs']) / 2
    wall = (raw['wallBeforeMs'] + raw['wallAfterMs']) / 2
    offset = mono - base_mono
    if not number(offset, -600000, 600000) or abs(wall - base_wall - offset) > 2: return None
    out = {'ordinal':raw['sequence'], 'nativeOwnerOrdinal':raw['owner'], 'rateRequestOrdinal':raw['rateSequence'],
        'seekInvocationOrdinal':raw['seekSequence'], 'basis':basis, 'offsetMs':offset,
        'sampleUncertaintyMs':bracket['captureElapsedMs']/2+1,
        'samePlaybackIdentity':raw['owner'] > 0 and type(raw.get('rates')) is dict and
            raw['rates'].get('identityMatches') is True and raw['rates'].get('owner') == raw['owner'],
        'positionStatus':'unavailable'}
    if out['samePlaybackIdentity'] and raw.get('positionValid') is True and number(raw.get('positionMs'), 0, 86400000):
        out['positionMs'] = raw['positionMs']; out['positionStatus']='observed'
    rates = _rates(raw.get('rates'))
    if rates is not None:
        out['rateCapture'] = rates
        if type(raw.get('rates')) is dict:
            delta = raw['rates']['monoBeforeMs'] - raw['monoAfterMs']
            wall_delta = raw['rates']['wallBeforeMs'] - raw['wallAfterMs']
            if number(delta,-1000,1000) and abs(wall_delta-delta)<=2:
                out['rateCaptureStartRelativeToPositionEndMs']=delta
    return out


def retained_sequences(count):
    return list(range(1, min(2, count)+1)) + list(range(max(3, count-5), count+1))


def clock_observation(raw):
    if type(raw) is not dict: return {'status':'unavailable'}
    counts = ('rateCount','nativeCount','anchorCount','ownerCount','unmatchedReplies')
    if not all(type(raw.get(k)) is int and 0 <= raw[k] <= 65535 for k in counts): return {'status':'malformed'}
    out = {'status':'observed', **{k:raw[k] for k in counts},
        'clockDomain':'native_uptime_paired_epoch', 'dartAckReceipt':'unavailable',
        'recoveryArmAge':'unavailable', 'intervalAttribution':'unknown',
        'counterCapReached':any(raw[k] == 65535 for k in counts), 'rateRecords':[], 'nativeObservations':[], 'admittedAnchors':[]}
    for field, count in (('rates','rateCount'), ('native','nativeCount'), ('anchors','anchorCount')):
        values = raw.get(field); expected = retained_sequences(raw[count])
        if type(values) is not list or len(values) != len(expected) or any(type(row) is not dict or
                type(row.get('sequence')) is not int or row['sequence'] != seq for row,seq in zip(values,expected)):
            return {'status':'malformed'}
        out[field+'Dropped'] = max(0, raw[count]-8)
    out['coverage'] = 'first_and_tail' if any(out[k+'Dropped'] for k in ('rates','native','anchors')) else 'complete_retained_events'
    for row in raw['rates']:
        invocation = row.get('invocation'); begin = _rates(invocation)
        item = {'ordinal':row['sequence'], 'status':'invalid_clock_bracket', 'nativeReplyMeaning':'dispatch_not_dart_ack'}
        if begin is not None:
            item.update(status='setter_invoked', invocation=begin)
            if number(row.get('requested'), -2, 4): item['requestedNewRate'] = row['requested']
            bm,bw = invocation['monoAfterMs'], invocation['wallAfterMs']
            returned = row.get('returned'); end = _rates(returned)
            if row.get('returnedSeen') is True and end is not None:
                offset = returned['monoBeforeMs'] - bm
                if number(offset,0,600000) and abs(returned['wallBeforeMs']-bw-offset)<=2:
                    item.update(status='setter_returned', returned=end, returnAfterInvocationMs=offset)
            for flag, mono, wall, dest in (
                    ('replyBegan','replyBeginMonoMs','replyBeginWallMs','replyDispatchAfterInvocationMs'),
                    ('replyReturned','replyEndMonoMs','replyEndWallMs','replyReturnAfterInvocationMs')):
                if row.get(flag) is True and number(row.get(mono),0,1e15) and number(row.get(wall),0,1e15):
                    delta=row[mono]-bm
                    if number(delta,0,600000) and abs(row[wall]-bw-delta)<=2: item[dest]=delta
            for source, flag, basis, dest in (
                    ('priorAnchor',None,'source_relative_sampler','priorAdmittedAnchor'),
                    ('firstAnchor','firstAnchorSeen','source_relative_sampler','firstAdmittedAnchor'),
                    ('firstNative','firstNativeSeen','item_current_time','firstNativeObservation')):
                item[dest+'Status']='unavailable'
                if flag is None or row.get(flag) is True:
                    point=clock_point(row.get(source),bm,bw,basis)
                    valid=(point is not None and point['nativeOwnerOrdinal'] > 0 and
                        point['nativeOwnerOrdinal'] == begin.get('nativeOwnerOrdinal'))
                    if flag is not None:
                        valid=(valid and point['nativeOwnerOrdinal'] == item.get('returned',{}).get('nativeOwnerOrdinal') and
                            point['rateRequestOrdinal'] == row['sequence'] and
                            point['offsetMs'] >= item.get('returnAfterInvocationMs',float('inf')))
                    if valid: item[dest]=point; item[dest+'Status']='observed'
                    elif flag is not None and row.get(flag) is True: item[dest+'Status']='invalid_record'
        out['rateRecords'].append(item)
    for source,dest,basis in (('native','nativeObservations','item_current_time'),('anchors','admittedAnchors','source_relative_sampler')):
        records=raw[source]
        if records and all(number(records[0].get(k),0,1e15) for k in ('monoBeforeMs','wallBeforeMs')):
            for row in records:
                point=clock_point(row,records[0]['monoBeforeMs'],records[0]['wallBeforeMs'],basis)
                if point is not None: out[dest].append(point)
    out['invalidRecords'] = (len(raw['native'])-len(out['nativeObservations']) + len(raw['anchors'])-len(out['admittedAnchors']) +
        sum(row['status']=='invalid_clock_bracket' for row in out['rateRecords']))
    return out


CLOCK_ROW_SCHEMA = {
    'ordinal':('integer',1,65535), 'readinessElapsedMs':('number',0,600000),
    'remainingReadinessBudgetMs':('number',0,5000), 'serverClockOffsetMs':('number',-600000,600000),
    'latencySampleCount':('integer',0,65535), 'nativePositionMs':('number',0,86400000),
    'nativeRate':('number',-2,4), 'requestedRate':('number',-2,4),
    'nativeSampleUncertaintyMs':('number',0,1000), 'dartSampleUncertaintyMs':('number',0,1000),
    'dartMinusNativeSampleMs':('number',-1000,1000), 'pairedNativeSampleDeltaMs':('number',-1000,1000),
    'seekInProgress':bool, 'playingIntent':bool, 'nativeState':('integer',0,4),
}


def clock_history(previous, state, native, elapsed_ms, paired_state):
    previous=previous.get('clockHistory') if type(previous) is dict else None
    count=previous.get('count',0) if type(previous) is dict else 0
    if type(count) is not int or not 0 <= count <= 65535: count=0
    count=min(65535,count+1)
    row={'ordinal':count}
    if number(elapsed_ms,0,600000): row.update(readinessElapsedMs=elapsed_ms,remainingReadinessBudgetMs=max(0,5000-elapsed_ms))
    for data, old, new in ((state,'serverClockOffsetMs','serverClockOffsetMs'),(state,'latencySampleCount','latencySampleCount'),
            (state,'dartPositionSampleUncertaintyMs','dartSampleUncertaintyMs'),(native,'positionMs','nativePositionMs'),
            (native,'playbackRate','nativeRate'),(native,'requestedRate','requestedRate'),
            (native,'sampleUncertaintyMs','nativeSampleUncertaintyMs'),(native,'seekInProgress','seekInProgress'),
            (native,'playingIntent','playingIntent'),(native,'playbackState','nativeState')):
        row[new]=data.get(old)
    at=native.get('sampledAtMs'); dart=state.get('dartPositionSampledAtMs')
    if number(at,0,1e15) and number(dart,0,1e15): row['dartMinusNativeSampleMs']=dart-at
    pair=paired_state.get('nativePlayers') if type(paired_state) is dict else None
    if type(pair) is list and len(pair)==1 and type(pair[0]) is dict and number(at,0,1e15) and number(pair[0].get('sampledAtMs'),0,1e15):
        row['pairedNativeSampleDeltaMs']=at-pair[0]['sampledAtMs']
    rows=previous.get('records',[]) if type(previous) is dict else []
    if type(rows) is not list or len(rows)>8: rows=[]
    rows=rows+[row]; rows=rows if len(rows)<=8 else rows[:2]+rows[-6:]
    clean=[]
    for item in rows:
        if type(item) is not dict: continue
        clean.append({k:v for k,v in item.items() if k in CLOCK_ROW_SCHEMA and
            ((CLOCK_ROW_SCHEMA[k] is bool and type(v) is bool) or
             (type(CLOCK_ROW_SCHEMA[k]) is tuple and number(v,*CLOCK_ROW_SCHEMA[k][1:]) and
              (CLOCK_ROW_SCHEMA[k][0]!='integer' or type(v) is int)))})
    return {'count':count,'dropped':max(0,count-8),'counterCapReached':count==65535,'coverage':'first_and_tail' if count>8 else 'complete_retained_samples',
        'clockDomain':'harness_elapsed_and_paired_native_epoch', 'recoveryArmAge':'unavailable', 'records':clean}


RATE_SCHEMA.update({'playingIntent':bool,'seeking':bool,'processingState':('integer',0,4),'timeControl':('integer',-1,2),
    'nativeOwnerOrdinal':('integer',0,65535),'effectiveRateReadCount':('integer',0,2),
    'effectiveRateReadBasis':frozenset(('existing_sampler_locals','event_bound_capture'))})
CLOCK_POINT_SCHEMA = {'ordinal':('integer',1,65535),'nativeOwnerOrdinal':('integer',0,65535),
    'rateRequestOrdinal':('integer',0,65535),'seekInvocationOrdinal':('integer',0,65535),
    'basis':frozenset(('item_current_time','source_relative_sampler')),'offsetMs':('number',-600000,600000),
    'sampleUncertaintyMs':('number',0,1000),'rateCaptureStartRelativeToPositionEndMs':('number',-1000,1000),'samePlaybackIdentity':bool,'positionStatus':frozenset(('observed','unavailable')),'positionMs':('number',0,86400000),'rateCapture':RATE_SCHEMA}
SCHEMA['seekRecords'][1]['firstNativeObservation']=CLOCK_POINT_SCHEMA
SCHEMA['seekRecords'][1]['firstAdmittedAnchor']=CLOCK_POINT_SCHEMA
for field in ('firstNativeObservationStatus','firstAdmittedAnchorStatus'):
    SCHEMA['seekRecords'][1][field]=frozenset(('unavailable','observed','invalid_record'))
SCHEMA['clockObservation']={
    'status':frozenset(('observed','unavailable','malformed')),
    **{k:('integer',0,65535) for k in ('rateCount','nativeCount','anchorCount','ownerCount','unmatchedReplies','ratesDropped','nativeDropped','anchorsDropped','invalidRecords')},
    'clockDomain':frozenset(('native_uptime_paired_epoch',)), 'dartAckReceipt':frozenset(('unavailable',)),
    'recoveryArmAge':frozenset(('unavailable',)), 'intervalAttribution':frozenset(('unknown',)), 'counterCapReached':bool,
    'coverage':frozenset(('first_and_tail','complete_retained_events')),
    'nativeObservations':('list',CLOCK_POINT_SCHEMA,8),'admittedAnchors':('list',CLOCK_POINT_SCHEMA,8),
    'rateRecords':('list',{'ordinal':('integer',1,65535),'status':frozenset(('invalid_clock_bracket','setter_invoked','setter_returned')),
        'nativeReplyMeaning':frozenset(('dispatch_not_dart_ack',)), 'requestedNewRate':('number',-2,4),
        'invocation':RATE_SCHEMA,'returned':RATE_SCHEMA,
        **{k:('number',0,600000) for k in ('returnAfterInvocationMs','replyDispatchAfterInvocationMs','replyReturnAfterInvocationMs')},
        'priorAdmittedAnchor':CLOCK_POINT_SCHEMA,'firstAdmittedAnchor':CLOCK_POINT_SCHEMA,'firstNativeObservation':CLOCK_POINT_SCHEMA,
        **{k: frozenset(('unavailable','observed','invalid_record')) for k in ('priorAdmittedAnchorStatus','firstAdmittedAnchorStatus','firstNativeObservationStatus')}},8)}
SCHEMA['clockHistory']={'counterCapReached':bool,'count':('integer',0,65535),'dropped':('integer',0,65535),
    'coverage':frozenset(('first_and_tail','complete_retained_samples')),
    'clockDomain':frozenset(('harness_elapsed_and_paired_native_epoch',)), 'recoveryArmAge':frozenset(('unavailable',)),
    'records':('list',CLOCK_ROW_SCHEMA,8)}
