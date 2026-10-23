"""Strict sampled Follow precision, using only already captured native states."""

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
            assert abs(delta_ms / elapsed_ms - expected) < 0.15
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
        'deadline': origin + 5, 'settled': False, 'settledAt': None,
        'processes': tuple(_follow_process_identity(s) for s in states),
        'nativeIds': [tuple(p['id'] for p in players(s)) for s in states],
        'oldTargetTask': (states[1].get('contextId'), tuple(states[1].get('queue') or []),
                          states[1].get('currentIndex'), states[1].get('trackId')),
        'queue': queue, 'index': index, 'track': queue[index],
        'oldAuthority': old_authority, 'oldCursors': old_cursors,
        'newAuthority': new_authority,
        'newCursors': old_cursors if kind == 'rate_change' else None,
        'followerContext': follower['contextId'],
        'oldRate': native_requested_rate(authority), 'identity': old_identity if kind == 'rate_change' else None,
        'candidate': None, 'lastStates': None, 'lastObservedAt': None, 'lastPair': None, 'previousPair': None,
        'measurement': {},
    }


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
        assert target_task in (transition['oldTargetTask'], task)
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
    except (AssertionError, KeyError, TypeError, ValueError):
        raise FollowPrecisionUnsafe('Follow transition owned identity changed') from None


def observe_follow_precision_transition(matrix, states):
    """Consume an existing tuple only. Return pending or enforce strict steady."""
    transition = getattr(matrix, 'follow_precision_transition', None)
    if transition is None:
        return
    _follow_transition_ownership(transition, states)
    now = time.monotonic()
    if not transition['settled'] and now >= transition['deadline']:
        raise FollowPrecisionDeadline('Owned Follow transition exceeded command-origin five seconds')
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
        if not (handoff.get('contextId') == context
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
