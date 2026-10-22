"""Read-only instrumentation of the disposable native lab, never production."""
from pathlib import Path

# Exact reviewed assertion text. Replacement only inserts observations before it.
CHECKS = (
    ('target-track', "assert after[1]['trackId'] == source_track", 'trackMatches', "after[1]['trackId'] == source_track"),
    ('target-queue', "assert after[1]['queue'] == source_queue and after[1]['currentIndex'] == source_index", 'queueAndIndexMatch', "after[1]['queue'] == source_queue and after[1]['currentIndex'] == source_index"),
    ('canonical-track', "assert after[1]['contexts'][context]['trackId'] == source_track", 'canonicalTrackMatches', "after[1]['contexts'][context]['trackId'] == source_track"),
    ('canonical-state', "assert after[1]['contexts'][context]['state'] == 'playing'", 'canonicalPlaying', "after[1]['contexts'][context]['state'] == 'playing'"),
    ('canonical-control', "assert after[1]['contexts'][context]['controlVersion'] == after[1]['contexts'][context]['queueControlVersion'] == self.canonical_server_observation['currentCanonical']['controlVersion']", 'controlVersionsMatch', "after[1]['contexts'][context]['controlVersion'] == after[1]['contexts'][context]['queueControlVersion'] == self.canonical_server_observation['currentCanonical']['controlVersion']"),
    ('continuity', 'assert abs(continuity) <= 1000', 'continuityErrorMs', 'continuity'),
    ('native-rate', "assert abs(target['playbackRate'] - 1.5) < 0.0001", 'nativeRate', "target['playbackRate']"),
)
STREAM_ASSERT = """assert any(event.get('event') == 'stream.request' and event.get('nativeLabInstance') == b.role
                   and event.get('trackId') == source_track and event.get('atMs', 0) >= handoff_started_at
                   for event in events)"""
STAGES = frozenset('handoff-check-' + check[0] for check in CHECKS) | {'handoff-check-media-provenance'}


FAILURE_ENTRY = "    def safe_failure(self, error):\n"
FAILURE_FIELDS = "                          'bridgeCommandFailure': command_failure, 'failureStateRefresh': state_refresh,"
FAILURE_LOCATION = """        _stream_summary = {}
        try:
            _events_path = self.fixture_state_directory / 'stream-events.jsonl'
            if _events_path.stat().st_size <= 2000000:
                _events = []
                for _line in _events_path.read_text(encoding='utf-8').splitlines():
                    try:
                        _event = json.loads(_line)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(_event, dict) and _event.get('event') == 'stream.request':
                        _events.append(_event)
                _stream_summary = {'streamCount': len(_events),
                    'authorityStreamCount': sum(e.get('nativeLabInstance') == 'authority' for e in _events),
                    'targetStreamCount': sum(e.get('nativeLabInstance') == 'target' for e in _events),
                    'followerStreamCount': sum(e.get('nativeLabInstance') == 'follower' for e in _events),
                    'unlabelledStreamCount': sum(e.get('nativeLabInstance') not in ('authority', 'target', 'follower') for e in _events)}
        except (OSError, TypeError, AttributeError, ValueError):
            pass
        _failure_location = {}
        _failure_frames = []
        _trace = error.__traceback__
        while _trace is not None:
            _module = Path(_trace.tb_frame.f_code.co_filename).name
            if _module in ('run_lab.py', 'extended_handoff.py') and 0 < _trace.tb_lineno <= 100000:
                _failure_location = {'module': _module, 'line': _trace.tb_lineno}
                if len(_failure_frames) < 8:
                    _failure_frames.append(_failure_location)
            _trace = _trace.tb_next
"""


LOG_HELPER = r'''
def bounded_owned_log_counts(root, expected_root):
    result = {'readStatus': 'unverified'}
    try:
        root, expected_root = Path(root), Path(expected_root)
        if not root.is_absolute() or root != expected_root or '..' in root.parts:
            return result
        log = root / 'logs/debug.log'
        if any(path.is_symlink() for path in (log, *log.parents)):
            result['readStatus'] = 'symlink_refused'
            return result
        if log.resolve() != expected_root.resolve() / 'logs/debug.log':
            return result
        size = log.stat().st_size
        if size > 8 * 1024 * 1024:
            result['readStatus'] = 'oversized'
            return result
        if not log.is_file():
            return result
        with log.open('rb') as stream:
            offset = max(0, size - 256 * 1024)
            stream.seek(offset)
            data = stream.read(256 * 1024)
        lines = data.decode('utf-8', errors='replace').splitlines()
        if offset and lines:
            lines = lines[1:]  # Ignore a potentially partial first line.
        counts = dict.fromkeys(('scopedNativeQueueBeforePlay', 'scopedSingleSourceBeforePlay',
            'staleExecutionGuard', 'staleCommandSideEffect', 'playFailed', 'playSlowStart'), 0)
        for line in lines:
            tokens = line.split()
            lease = '[[AUDIO_EXECUTION_LEASE]] stale_audio_callback_dropped' in line
            if lease and 'source=triggerPlay:scopedNativeQueue:beforePlay' in tokens:
                counts['scopedNativeQueueBeforePlay'] += 1
            if lease and 'source=triggerPlay:scopedSingleSource:beforePlay' in tokens:
                counts['scopedSingleSourceBeforePlay'] += 1
            for key, marker in (
                ('staleExecutionGuard', '[[CMD_DROP]] staleExecutionGuard'),
                ('staleCommandSideEffect', '[[AUDIO_EXECUTION_LEASE]] stale_command_side_effect_dropped'),
                ('playFailed', '[[PLAYER_ACT]] op=play failed'),
                ('playSlowStart', '[[PLAYER_ACT]] op=play slow-start')):
                counts[key] += marker in line
        result.update(readStatus='read', **{key: min(value, 1000000) for key, value in counts.items()})
    except (OSError, ValueError, TypeError):
        result['readStatus'] = 'unavailable'
    return result

def owned_client_log_counts(client, state):
    refused = {'readStatus': 'ownership_refused'}
    try:
        bundle = client.bundle_id
        role = client.role
        if role not in ('authority', 'target', 'follower') or not isinstance(bundle, str):
            return refused
        if not bundle.startswith('com.example.emosonic.nativelab.r') or not bundle.endswith('.' + role):
            return refused
        if any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for char in bundle):
            return refused
        if state.get('bundleId') != bundle or type(state.get('pid')) is not int or state['pid'] != client.process.pid:
            return refused
        expected = Path.home() / 'Library/Containers' / bundle / 'Data/Library/Application Support' / bundle / ('native-playback-lab-' + role)
        root = Path(state.get('root'))
        sentinel = expected / '.native-mac-lab.json'
        if root != expected or any(path.is_symlink() for path in (sentinel, *sentinel.parents)):
            return refused
        if not sentinel.is_file() or sentinel.stat().st_size > 4096:
            return refused
        metadata = json.loads(sentinel.read_text(encoding='utf-8'))
        if not isinstance(metadata, dict) or metadata.get('kind') != 'emosonic-native-mac-lab' or metadata.get('bundleId') != bundle or metadata.get('instance') != role:
            return refused
        return bounded_owned_log_counts(root, expected)
    except (OSError, ValueError, TypeError, AttributeError):
        return refused

'''

def observation(stage, entries):
    return (f"        self.stage = {stage!r}\n"
            "        print(json.dumps({'stage': self.stage, 'status': 'not-verified', "
            "'consistencyObservation': {" + entries + "}}), flush=True)\n")


def patch_text(text):
    setup_anchor = "    result['preflight'] = preflight\n"
    setup_extra = """    _queue = state.get('queue')
    _index = state.get('currentIndex')
    result['queueLength'] = len(_queue) if isinstance(_queue, list) else None
    result['currentIndex'] = _index if type(_index) is int else None
    result['trackPresent'] = isinstance(state.get('trackId'), str) and bool(state.get('trackId'))
    result['queueIndexValid'] = isinstance(_queue, list) and type(_index) is int and 0 <= _index < len(_queue)
    result['queueTrackMatchesActual'] = result['queueIndexValid'] and _queue[_index] == state.get('trackId')
"""
    load_anchor = "        a.command('playQueue', trackIds=ids)\n"
    load_observation = """        _load_started = time.monotonic()
        _load_response = a.command('playQueue', trackIds=ids)
        _load_state = _load_response.get('state') or {}
        print(json.dumps({'stage': 'source-load-command-returned', 'status': 'not-verified',
            'waitObservation': {'elapsedMs': (time.monotonic() - _load_started) * 1000},
            'nativePlayback': [{'clientOrdinal': 0,
                'setup': local_setup_diagnostic(_load_state),
                'native': [numeric_native_snapshot(item) for item in (_load_state.get('nativePlayers') or [])[:2] if isinstance(item, dict)]}]}), flush=True)
"""
    wait_anchor = "        until = time.monotonic() + timeout\n"
    wait_prefix = """        _wait_started = time.monotonic()
        self.wait_observation = {'waitStage': stage, 'timeoutSeconds': timeout, 'pollCount': 0, 'elapsedMs': 0}
"""
    poll_anchor = "                states = self.states()\n"
    poll_prefix = """                self.wait_observation['pollCount'] += 1
                self.wait_observation['elapsedMs'] = (time.monotonic() - _wait_started) * 1000
"""
    replacements = [
        ('class Matrix:\n', LOG_HELPER + '\nclass Matrix:\n'),
        (load_anchor, load_observation),
        (wait_anchor, wait_prefix + wait_anchor),
        (poll_anchor, poll_prefix + poll_anchor),
        (setup_anchor, setup_extra + setup_anchor),
        (FAILURE_ENTRY, FAILURE_ENTRY + FAILURE_LOCATION),
        (FAILURE_FIELDS, "                          'failureLocation': _failure_location, 'failureFrames': _failure_frames, 'startupStreams': _stream_summary,\n                          'nativeLogClassifications': [dict(clientOrdinal=i, **owned_client_log_counts(client, state)) for i, (client, state) in enumerate(zip(self.clients[:3], self.last[:3]))],\n                          'waitObservation': getattr(self, 'wait_observation', {}),\n" + FAILURE_FIELDS),
    ]
    for label, assertion, key, expression in CHECKS:
        original = '        ' + assertion
        entries = repr(key) + ': ' + expression
        if label == 'continuity':
            entries += ", 'sampleElapsedMs': target['sampledAtMs'] - start['sampledAtMs'], 'sourcePositionMs': start['positionMs'], 'targetPositionMs': target['positionMs']"
        replacements.append((original, observation('handoff-check-' + label, entries) + original))
    original = '        ' + STREAM_ASSERT
    prefix = """        _stream = [event for event in events if event.get('event') == 'stream.request']
        _role = [event for event in _stream if event.get('nativeLabInstance') == b.role]
        _track = [event for event in _role if event.get('trackId') == source_track]
        _timed = [event for event in _track if type(event.get('atMs')) in (int, float)]
"""
    entries = ("'streamCount': len(_stream), 'targetStreamCount': len(_role), "
               "'targetTrackStreamCount': len(_track), 'numericTimestampCount': len(_timed), "
               "'postStartStreamCount': sum(event['atMs'] >= handoff_started_at for event in _timed), "
               "'latestRequestDeltaMs': max((event['atMs'] - handoff_started_at for event in _timed), default=None)")
    replacements.append((original, prefix + observation('handoff-check-media-provenance', entries) + original))
    if any(text.count(old) != 1 for old, _ in replacements) or any(stage in text for stage in STAGES):
        raise ValueError('Native observation patch requires exact unpatched assertions.')
    for old, new in replacements:
        text = text.replace(old, new, 1)
    return text


def apply_observations(target):
    target = Path(target)
    if target.name != 'run_lab.py' or target.parent.name != 'native_playback_mac' or target.parent.parent.name != 'tool':
        raise ValueError('Wrong native observation target.')
    if any(path.is_symlink() for path in (target, *target.parents)):
        raise ValueError('Native observation target must not be a symlink.')
    text = patch_text(target.read_text(encoding='utf-8'))
    compile(text, '<disposable-native-lab>', 'exec')
    target.write_text(text, encoding='utf-8')
