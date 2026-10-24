"""Strict sampled Follow precision, using only already captured native states."""

def follow_convergence_observation(matrix, kind, elapsed_ms, physical_ms=None):
    """External sampled evidence only; no inference about internal recovery success.

    The independent bounded recovery tape may be incomplete. A physical steady
    witness does not turn product exhaustion into an internally settled attempt.
    All times are relative to an already captured Python monotonic origin.
    """
    origins = {'initial': 'observed_task_ready', 'transfer': 'before_transfer_command',
               'rate_change': 'before_rate_change_command'}
    value = {'convergenceKind': kind, 'convergenceOrigin': origins[kind],
        'convergenceBudgetMs': 10000, 'convergenceElapsedMs': elapsed_ms,
        'convergenceState': 'pending' if physical_ms is None else 'sampled_steady',
        'internalRecoveryOutcome': 'unknown'}
    if physical_ms is not None: value['physicalConvergenceMs'] = physical_ms
    measurement = getattr(matrix, 'rate_measurement', None)
    if isinstance(measurement, dict):
        measurement.update(value)
        if kind == 'initial' and 'initialFollowCommandToConvergenceOriginMs' in measurement:
            measurement['initialFollowCommandToObservationMs'] = measurement['initialFollowCommandToConvergenceOriginMs'] + elapsed_ms
    transition = getattr(matrix, 'follow_precision_transition', None)
    if transition is not None and transition['kind'] == kind:
        transition['measurement'].update(value)
        observation = getattr(matrix, 'follow_observation', None)
        if isinstance(observation, dict): observation['precision'] = dict(transition['measurement'])
    return value


def follow_nominal_precision_ready(authority, follower, expected):
    # Property/requested-rate equality is not a physical slope measurement.
    assert type(follower.get('followSyncToleranceMs')) is int
    assert follower['followSyncToleranceMs'] == 50
    lead = follower.get('followLeadCompensationMs')
    assert type(lead) in (int, float) and math.isfinite(lead) and lead == 0
    for value in (authority, follower):
        native = decoded(value)
        assert native['playbackState'] == 3
        assert native.get('seekInProgress') is False
        assert native.get('playingIntent') is True
    assert native_rate_matches(authority, expected)
    assert abs(native_requested_rate(authority) - expected) < 0.0001
    assert native_rate_matches(follower, expected, follower=True)
    lower, upper = follow_native_rate_bounds(follower, expected)
    requested = native_requested_rate(follower)
    assert lower - 0.0001 <= requested <= upper + 0.0001
    return (native_rate_matches(follower, expected)
            and abs(requested - expected) < 0.0001)


def follow_native_interval_rate(old, current, expected):
    """Prove rate from the same returned native CMTime and its enclosing clocks.

    This removes only the extra integer-millisecond quantization. It makes no
    claim about an unreported intrinsic media timescale or between-sample motion.
    Missing, stale or unpaired data is never a rounded-rate fallback. No reads,
    controls, waits, anchors or vendor receipt sequences enter this proof.
    """
    def finite(value, low, high):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high

    def integer(value, low, high):
        return type(value) is int and low <= value <= high

    def rounded(value):
        # Exact nonnegative llround equivalence without rounding value + 0.5.
        floor = math.floor(value)
        return floor + (value - floor >= 0.5)

    def bounds(value):
        # Guard the returned Float64 seconds-to-ms arithmetic/representation,
        # not unknown CMTime tick accuracy. Outward endpoints also cover Python
        # subtraction/division rounding below. JSON preserves the binary64 value.
        error = 4 * max(math.ulp(value), 1000 * math.ulp(value / 1000))
        return (math.nextafter(value - error, -math.inf),
                math.nextafter(value + error, math.inf))

    def point(native):
        assert type(native) is dict and type(native.get('id')) is str and native['id']
        timing = native.get('timingObservation')
        assert type(timing) is dict
        clock = timing.get('clockObservation')
        assert type(clock) is dict
        assert integer(clock.get('nativeCount'), 1, 65534)
        assert integer(clock.get('ownerCount'), 1, 65534)
        assert integer(clock.get('rateCount'), 0, 65534)
        assert integer(timing.get('seekInvocations'), 0, 65534)
        records = clock.get('native')
        assert type(records) is list and 1 <= len(records) <= 8
        sequences = [row.get('sequence') if type(row) is dict else None for row in records]
        assert all(integer(sequence, 1, clock['nativeCount']) for sequence in sequences)
        assert all(a < b for a, b in zip(sequences, sequences[1:]))
        value = records[-1]
        assert type(value) is dict
        assert integer(value.get('sequence'), 1, 65534) and value['sequence'] == clock['nativeCount']
        assert integer(value.get('owner'), 1, 65534) and value['owner'] == clock['ownerCount']
        assert integer(value.get('rateSequence'), 0, 65534) and value['rateSequence'] == clock['rateCount']
        assert integer(value.get('seekSequence'), 0, 65534) and value['seekSequence'] == timing['seekInvocations']
        assert value.get('positionValid') is True and finite(value.get('positionMs'), 0, 86400000)
        for key in ('wallBeforeMs', 'wallAfterMs', 'monoBeforeMs', 'monoAfterMs'):
            assert finite(value.get(key), 0, 1e15)
        wall = value['wallAfterMs'] - value['wallBeforeMs']
        mono = value['monoAfterMs'] - value['monoBeforeMs']
        assert 0 <= wall <= 1000 and 0 <= mono <= 1000 and abs(wall - mono) <= 2
        assert integer(native.get('positionMs'), 0, 86400000)
        assert native['positionMs'] == rounded(value['positionMs'])
        assert integer(native.get('sampledAtMs'), 0, 10**15)
        assert native['sampledAtMs'] == rounded((value['wallBeforeMs'] + value['wallAfterMs']) / 2)
        assert finite(native.get('sampleUncertaintyMs'), 1, 501)
        assert native['sampleUncertaintyMs'] == wall / 2 + 1
        rates = value.get('rates')
        assert type(rates) is dict and rates.get('identityMatches') is True
        assert integer(rates.get('owner'), 1, 65534) and rates['owner'] == value['owner']
        assert rates.get('playingIntent') is True and rates.get('seeking') is False
        assert integer(rates.get('processingState'), 3, 3) and integer(rates.get('timeControl'), 2, 2)
        assert rates.get('effectiveAvailable') is True and integer(rates.get('effectiveReadCount'), 1, 1)
        for key in ('requestedRate', 'nativeRate', 'effectiveRate'):
            assert finite(rates.get(key), 0, 4) and abs(rates[key] - expected) < 0.0001
        assert rates['requestedRate'] == native.get('requestedRate')
        assert rates['nativeRate'] == native.get('playbackRate')
        for key in ('wallBeforeMs', 'wallAfterMs', 'monoBeforeMs', 'monoAfterMs'):
            assert finite(rates.get(key), 0, 1e15)
        rate_wall = rates['wallAfterMs'] - rates['wallBeforeMs']
        rate_mono = rates['monoAfterMs'] - rates['monoBeforeMs']
        assert 0 <= rate_wall <= 1000 and 0 <= rate_mono <= 1000 and abs(rate_wall-rate_mono) <= 2
        delay = rates['monoBeforeMs'] - value['monoAfterMs']
        assert 0 <= delay <= 1000
        assert abs((rates['wallBeforeMs'] - value['wallAfterMs']) - delay) <= 2
        return value

    assert type(old) is dict and type(current) is dict
    assert type(old.get('id')) is str and old['id'] and old['id'] == current.get('id')
    assert finite(expected, 0.15, 4)
    a, b = point(old), point(current)
    assert b['sequence'] > a['sequence']
    assert (a['owner'], a['rateSequence'], a['seekSequence']) == (b['owner'], b['rateSequence'], b['seekSequence'])
    wall_interval = ((b['wallBeforeMs'] + b['wallAfterMs']) - (a['wallBeforeMs'] + a['wallAfterMs'])) / 2
    mono_interval = ((b['monoBeforeMs'] + b['monoAfterMs']) - (a['monoBeforeMs'] + a['monoAfterMs'])) / 2
    assert abs(wall_interval - mono_interval) <= 2
    # Each position read is enclosed by its own before/after native uptime.
    lower_dt = math.nextafter(bounds(b['monoBeforeMs'])[0] - bounds(a['monoAfterMs'])[1], -math.inf)
    upper_dt = math.nextafter(bounds(b['monoAfterMs'])[1] - bounds(a['monoBeforeMs'])[0], math.inf)
    lower_dp = math.nextafter(bounds(b['positionMs'])[0] - bounds(a['positionMs'])[1], -math.inf)
    upper_dp = math.nextafter(bounds(b['positionMs'])[1] - bounds(a['positionMs'])[0], math.inf)
    assert 0 < lower_dt <= upper_dt and 1 < lower_dp <= upper_dp
    lower_rate = math.nextafter(lower_dp / upper_dt, -math.inf)
    upper_rate = math.nextafter(upper_dp / lower_dt, math.inf)
    return lower_rate > expected - 0.15 and upper_rate < expected + 0.15


def follow_precision_sample(matrix, states, authority_index, context, expected, identity, previous=None, *, measurement=None):
    """Validate every existing tuple; never wait, restart, poll, or skip a tuple.

    This is finite sampled coverage, not a between-sample guarantee. The full
    reported time uncertainty is retained and one media millisecond covers the
    two independently rounded native positions, including at rates below one.
    """
    assert follow_correction_identity(states, authority_index, context) == identity
    authority, follower = states[authority_index], states[2]
    assert native_follow_task_ready(authority, follower, context)
    a, f = decoded(authority), decoded(follower)
    error, time_uncertainty = aligned_drift(authority, follower)
    assert math.isfinite(error) and math.isfinite(time_uncertainty)
    uncertainty = time_uncertainty + 1.0
    worst = abs(error) + uncertainty
    if measurement is None: measurement = matrix.rate_measurement
    measurement.update(precisionDriftMs=error, precisionUncertaintyMs=uncertainty,
        precisionWorstCaseMs=worst,
        precisionMaxWorstCaseMs=max(worst, measurement.get('precisionMaxWorstCaseMs', 0)),
        precisionSamples=measurement.get('precisionSamples', 0) + 1,
        precisionSourceNative=numeric_native_snapshot(a),
        precisionFollowerNative=numeric_native_snapshot(f))
    assert follow_nominal_precision_ready(authority, follower, expected)
    assert time_uncertainty <= 25 and worst <= 50
    if previous is not None:
        for old, current in zip(previous, (a, f)):
            elapsed_ms = current['sampledAtMs'] - old['sampledAtMs']
            delta_ms = current['positionMs'] - old['positionMs']
            assert current['id'] == old['id']
            assert delta_ms > 1
            assert elapsed_ms > current['sampleUncertaintyMs'] + old['sampleUncertaintyMs']
            assert follow_native_interval_rate(old, current, expected)
    return (a, f)


class FollowPrecisionDeadline(TimeoutError):
    """An owned transition expired, not a retryable HTTP read timeout."""


class FollowPrecisionUnsafe(AssertionError):
    """Owned identity or native evidence changed; dependent checks are unsafe."""


def _follow_process_identity(state):
    values = tuple(state.get(key) for key in ('clientId', 'deviceSessionId', 'pid', 'bundleId', 'root'))
    assert all(isinstance(value, str) and value for value in (values[0], values[1], values[3], values[4]))
    assert type(values[2]) is int and values[2] > 0
    generation = (state.get('preflightDiagnostics') or {}).get('connectionGeneration')
    assert type(generation) is int and generation >= 0
    return values + (generation,)


def _follow_canonical_identity(state, context):
    canonical = (state.get('contexts') or {}).get(context) or {}
    authority = (canonical.get('authorityClientId'), canonical.get('authorityDeviceSessionId'))
    cursors = tuple(canonical.get(key) for key in ('epoch', 'controlVersion', 'queueRevision'))
    assert all(isinstance(v, str) and v for v in authority)
    assert all(type(v) is int and v > 0 for v in cursors)
    return authority, cursors


def begin_follow_precision_transition(matrix, states, context, kind, expected, origin):
    """One owned command, one deadline; no drift-triggered or heartbeat rearm."""
    assert kind in ('transfer', 'rate_change')
    assert getattr(matrix, 'follow_precision_transition', None) is None
    source_index = 0 if kind == 'transfer' else 1
    authority, follower = states[source_index], states[2]
    old_identity = follow_correction_identity(states, source_index, context)
    old_authority, old_cursors = _follow_canonical_identity(authority, context)
    new_authority = (states[1]['clientId'], states[1]['deviceSessionId'])
    queue = tuple(authority['queue']); index = authority['currentIndex']
    matrix.follow_precision_transition = {
        'kind': kind, 'context': context, 'expected': expected, 'origin': origin,
        'deadline': origin + 10, 'settled': False, 'settledAt': None,
        'processes': tuple(_follow_process_identity(s) for s in states),
        'nativeIds': [tuple(p['id'] for p in players(s)) for s in states],
        'oldTargetTask': (states[1].get('contextId'), tuple(states[1].get('queue') or []),
                          states[1].get('currentIndex'), states[1].get('trackId')),
        'queue': queue, 'index': index, 'track': queue[index],
        'oldAuthority': old_authority, 'oldCursors': old_cursors,
        'newAuthority': new_authority,
        'handoffId': None, 'targetBindingGeneration': None,
        'previousHandoffIds': tuple((state.get('handoff') or {}).get('id') for state in states[:2]),
        'newCursors': old_cursors if kind == 'rate_change' else None,
        'followerContext': follower['contextId'],
        'oldRate': native_requested_rate(authority), 'identity': old_identity if kind == 'rate_change' else None,
        'candidate': None, 'lastStates': None, 'lastObservedAt': None, 'lastPair': None, 'previousPair': None,
        'measurement': {},
    }


def _follow_handoff_matches(transition, state, role):
    record = state.get('handoff') or {}
    allowed = ('starting', 'preparing', 'ready', 'committing', 'completed') if role == 'source' else ('preparing', 'ready', 'committing', 'completed')
    control = transition['oldCursors'][1]
    expected_control = control + (1 if record.get('status') in ('committing', 'completed') else 0)
    return (type(record.get('controlVersion')) is int and record['controlVersion'] == expected_control
        and type(record.get('canonicalControlVersion')) is int and record['canonicalControlVersion'] == control
        and isinstance(record.get('id'), str) and bool(record['id'])
        and record['id'] == transition['handoffId'] and record.get('role') == role
        and record.get('status') in allowed and record.get('contextId') == transition['context']
        and record.get('sourceClientId') == transition['oldAuthority'][0]
        and record.get('targetClientId') == transition['newAuthority'][0]
        and record.get('targetDeviceSessionId') == transition['newAuthority'][1]
        and (record.get('sourceDeviceSessionId') == transition['oldAuthority'][1]
             if role == 'target' else record.get('sourceDeviceSessionId') in (None, transition['oldAuthority'][1])))


def pin_follow_transfer_command(matrix, response):
    """Use the existing command response, not an additional state read or ACK claim."""
    transition = matrix.follow_precision_transition
    try:
        assert transition['kind'] == 'transfer' and transition['handoffId'] is None
        assert type(response) is dict and response.get('ok') is True
        state = response['state']
        assert _follow_process_identity(state) == transition['processes'][0]
        identifier = (state.get('handoff') or {}).get('id')
        assert isinstance(identifier, str) and identifier and identifier not in transition['previousHandoffIds']
        candidate = dict(transition, handoffId=identifier)
        assert _follow_handoff_matches(candidate, state, 'source')
        transition['handoffId'] = identifier
    except (AssertionError, KeyError, TypeError, ValueError):
        raise FollowPrecisionUnsafe('Follow transfer command identity changed') from None


def _follow_owned_provisional_target(transition, states):
    """Protocol-owned preparation is pending only, never a precision witness."""
    if transition['kind'] != 'transfer' or transition['newCursors'] is not None:
        return False
    target = states[1]
    binding = target.get('binding') or {}
    if not (binding.get('role') == 'handoffTarget' and binding.get('phase') == 'provisional'
            and binding.get('contextId') == transition['context']
            and type(binding.get('generation')) is int and binding['generation'] > 0
            and _follow_handoff_matches(transition, states[0], 'source')
            and _follow_handoff_matches(transition, target, 'target')
            and (target.get('handoff') or {}).get('prepared') is True):
        return False
    generation = transition['targetBindingGeneration']
    if generation is not None and binding['generation'] != generation:
        return False
    if target.get('contextId') not in (None, transition['oldTargetTask'][0], transition['context']):
        return False
    physical = (tuple(target.get('queue') or []), target.get('currentIndex'), target.get('trackId'))
    expected = (transition['queue'], transition['index'], transition['track'])
    status = target['handoff']['status']
    if physical != expected and not (status == 'preparing' and physical == transition['oldTargetTask'][1:]):
        return False
    transition['targetBindingGeneration'] = binding['generation']
    return True


def _follow_transition_ownership(transition, states):
    try:
        assert type(states) is list and len(states) == 3
        assert tuple(_follow_process_identity(s) for s in states) == transition['processes']
        for i, state in enumerate(states):
            current = tuple(p['id'] for p in players(state))
            old = transition['nativeIds'][i]
            # An empty pre-load target registry may create its one owned player.
            if not old and current and i == 1 and transition['kind'] == 'transfer':
                transition['nativeIds'][i] = current
            else:
                assert current == old
        context = transition['context']
        follower = states[2]
        assert follower.get('contextId') == transition['followerContext']
        assert follower.get('runtimeMode') == 'follow'
        assert follower.get('followSourceContextId') == context
        task = (context, transition['queue'], transition['index'], transition['track'])
        assert (context, tuple(follower.get('queue') or []), follower.get('currentIndex'), follower.get('trackId')) == task
        target_task = (states[1].get('contextId'), tuple(states[1].get('queue') or []),
                       states[1].get('currentIndex'), states[1].get('trackId'))
        pending_target = _follow_owned_provisional_target(transition, states)
        binding = states[1].get('binding') or {}
        if binding.get('phase') == 'provisional':
            assert pending_target
        elif binding.get('role') == 'handoffTarget':
            assert binding.get('phase') == 'confirmed' and binding.get('contextId') == context
            assert type(binding.get('generation')) is int and binding['generation'] > 0
            generation = transition['targetBindingGeneration']
            assert generation is None or binding['generation'] == generation
            assert target_task == task
            transition['targetBindingGeneration'] = binding['generation']
        assert target_task in (transition['oldTargetTask'], task) or pending_target
        for i in (1, 2):
            value = states[i]
            canonical = (value.get('contexts') or {}).get(context)
            if not canonical and i == 1 and transition['newCursors'] is None:
                continue
            authority, cursors = _follow_canonical_identity(value, context)
            assert authority in (transition['oldAuthority'], transition['newAuthority'])
            if authority == transition['oldAuthority'] and transition['oldAuthority'] != transition['newAuthority']:
                assert cursors == transition['oldCursors']
            elif transition['newCursors'] is not None:
                assert cursors == transition['newCursors']
        return pending_target
    except (AssertionError, KeyError, TypeError, ValueError):
        raise FollowPrecisionUnsafe('Follow transition owned identity changed') from None


def observe_follow_precision_transition(matrix, states):
    """Consume an existing tuple only. Return pending or enforce strict steady."""
    transition = getattr(matrix, 'follow_precision_transition', None)
    if transition is None:
        return
    pending_target = _follow_transition_ownership(transition, states)
    now = time.monotonic()
    follow_convergence_observation(matrix, transition['kind'], (now-transition['origin'])*1000,
        (transition['settledAt']-transition['origin'])*1000 if transition['settled'] else None)
    if not transition['settled'] and now >= transition['deadline']:
        raise FollowPrecisionDeadline('Owned Follow transition exceeded command-origin ten seconds')
    if pending_target:
        transition['candidate'] = None
        return
    if transition['lastStates'] is states:
        return
    context, expected = transition['context'], transition['expected']
    authority, follower = states[1], states[2]
    if transition['newCursors'] is None:
        handoff = authority.get('handoff') or {}
        completed = (handoff.get('status') == 'completed'
            and playing(authority) and stopped(states[0]) and playing(follower))
        if not completed:
            return
        if not (handoff.get('id') == transition['handoffId'] and transition['handoffId'] is not None
                and handoff.get('contextId') == context
                and (handoff.get('sourceClientId'), handoff.get('sourceDeviceSessionId')) == transition['oldAuthority']
                and (handoff.get('targetClientId'), handoff.get('targetDeviceSessionId')) == transition['newAuthority']):
            raise FollowPrecisionUnsafe('Completed transfer does not match the owned command')
        pair, cursors = _follow_canonical_identity(authority, context)
        if pair != transition['newAuthority']:
            raise FollowPrecisionUnsafe('Completed transfer has wrong authority')
        transition['newCursors'] = cursors
    required = (transition['newAuthority'], transition['newCursors'])
    if any(_follow_canonical_identity(s, context) != required for s in (authority, follower)):
        transition['candidate'] = None
        return
    try:
        identity = follow_correction_identity(states, 1, context)
        if transition['identity'] is None:
            transition['identity'] = identity
        assert identity == transition['identity']
    except (AssertionError, KeyError, TypeError, ValueError):
        raise FollowPrecisionUnsafe('Follow transition control identity changed') from None
    if transition['settled']:
        pair = follow_precision_sample(matrix, states, 1, context, expected,
            transition['identity'], transition['lastPair'], measurement=transition['measurement'])
        transition['previousPair'], transition['lastPair'] = transition['lastPair'], pair
        transition['lastStates'] = states
        transition['lastObservedAt'] = now
        return
    a, f = decoded(authority), decoded(follower)
    lower, upper = follow_native_rate_bounds(follower, expected)
    for native, allowed in ((a, (expected, transition['oldRate'])),):
        assert any(abs(native['playbackRate'] - rate) < .0001 for rate in allowed) or native['playbackState'] != 3
    for native in (a, f):
        requested = native.get('requestedRate')
        assert type(requested) in (int, float) and math.isfinite(requested)
        assert abs(requested-transition['oldRate']) < .0001 or lower-.0001 <= requested <= upper+.0001
        assert native.get('playingIntent') is True
        assert native['avPlayerStatus'] == 1 and native['avItemStatus'] == 1
        assert (native['playbackState'] == 3 and native.get('seekInProgress') is False
            or native['playbackState'] == 2 and native['avTimeControlStatus'] == 1
            or native['playbackState'] == 4 and native['playbackRate'] == 0 and native.get('seekInProgress') is True)
    if not native_follow_task_ready(authority, follower, context):
        transition['candidate'] = None
        return
    assert abs(f['playbackRate']-transition['oldRate']) < .0001 or lower-.0001 <= f['playbackRate'] <= upper+.0001
    if not native_rate_matches(authority, expected) or not native_rate_matches(follower, expected):
        transition['candidate'] = None
        return
    if not follow_nominal_precision_ready(authority, follower, expected):
        transition['candidate'] = None
        return
    error, uncertainty = aligned_drift(authority, follower)
    eligible = math.isfinite(error) and math.isfinite(uncertainty) and uncertainty <= 25 and abs(error)+uncertainty+1 <= 50
    previous = transition['candidate']
    stable = eligible and previous is not None
    if stable:
        for old, current in zip(previous, (a, f)):
            dt = current['sampledAtMs']-old['sampledAtMs']; dp=current['positionMs']-old['positionMs']
            stable = (stable and current['id']==old['id'] and dp>1
                and dt>current['sampleUncertaintyMs']+old['sampleUncertaintyMs']
                and abs(dp/dt-expected)<.15)
    transition['candidate'] = (a,f) if eligible else None
    if stable:
        # Actual validation time, not an earlier native sample timestamp.
        if time.monotonic() >= transition['deadline']:
            raise FollowPrecisionDeadline('Owned Follow transition proof exceeded original deadline')
        transition['lastPair'] = follow_precision_sample(matrix, states, 1, context, expected,
            transition['identity'], previous, measurement=transition['measurement'])
        transition['previousPair'] = previous
        transition['lastStates'] = states
        transition['lastObservedAt'] = now
        transition['settled'] = True
        transition['settledAt'] = now
        follow_convergence_observation(matrix, transition['kind'], (now-transition['origin'])*1000,
            (now-transition['origin'])*1000)
