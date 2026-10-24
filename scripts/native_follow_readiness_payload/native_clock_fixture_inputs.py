"""Synthetic test inputs only; never installed into the native/runtime harness.

Construct same-snapshot raw clock coordinates after intentional fixture mutations.
The supplied decoded implementation still validates original inputs first. This
adapter never replaces the actual interval predicate, adds reads, or repairs a
changed identity, rate, position, health flag, or sample timestamp.
"""


def decoded_with_native_clock(actual_decoded):
    sample_sequences = {}
    def decoded_fixture(state):
        native = actual_decoded(state)
        samples = sample_sequences.setdefault(native['id'], {})
        timestamp = native['sampledAtMs']
        sequence = samples.setdefault(timestamp, len(samples) + 1)
        radius = native['sampleUncertaintyMs'] - 1
        before, after = timestamp - radius, timestamp + radius
        rates = {'owner': 1, 'identityMatches': True,
            'playingIntent': native.get('playingIntent'), 'seeking': native.get('seekInProgress'),
            'processingState': native['playbackState'], 'timeControl': native['avTimeControlStatus'],
            'effectiveAvailable': True, 'effectiveReadCount': 1,
            'requestedRate': native['requestedRate'], 'nativeRate': native['playbackRate'],
            'effectiveRate': native['playbackRate'],
            'wallBeforeMs': after, 'wallAfterMs': after,
            'monoBeforeMs': after, 'monoAfterMs': after}
        point = {'sequence': sequence, 'owner': 1, 'rateSequence': 1, 'seekSequence': 1,
            'positionValid': True, 'positionMs': native['positionMs'],
            'wallBeforeMs': before, 'wallAfterMs': after,
            'monoBeforeMs': before, 'monoAfterMs': after, 'rates': rates}
        native['timingObservation'] = {'seekInvocations': 1,
            'clockObservation': {'nativeCount': sequence, 'ownerCount': 1,
                'rateCount': 1, 'native': [point]}}
        return native
    return decoded_fixture


def legacy_state_with_native_uncertainty(actual_state):
    """Materialize only the hash-verified legacy constructor's decimal default.

    This wrapper runs before mutation callbacks or test code receive the state.
    Subsequent uncertainty changes are never normalized by decoded construction.
    """
    def state_fixture(*args, **kwargs):
        state = actual_state(*args, **kwargs)
        native = state['nativePlayers'][0]
        assert native['sampleUncertaintyMs'] == 1.01
        radius = native['sampleUncertaintyMs'] - 1
        before, after = native['sampledAtMs'] - radius, native['sampledAtMs'] + radius
        native['sampleUncertaintyMs'] = (after - before) / 2 + 1
        return state
    return state_fixture
