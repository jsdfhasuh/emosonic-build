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
FAILURE_LOCATION = """        _failure_location = {}
        _trace = error.__traceback__
        while _trace is not None:
            _module = Path(_trace.tb_frame.f_code.co_filename).name
            if _module in ('run_lab.py', 'extended_handoff.py') and 0 < _trace.tb_lineno <= 100000:
                _failure_location = {'module': _module, 'line': _trace.tb_lineno}
            _trace = _trace.tb_next
"""


def observation(stage, entries):
    return (f"        self.stage = {stage!r}\n"
            "        print(json.dumps({'stage': self.stage, 'status': 'not-verified', "
            "'consistencyObservation': {" + entries + "}}), flush=True)\n")


def patch_text(text):
    replacements = [
        (FAILURE_ENTRY, FAILURE_ENTRY + FAILURE_LOCATION),
        (FAILURE_FIELDS, "                          'failureLocation': _failure_location,\n" + FAILURE_FIELDS),
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
