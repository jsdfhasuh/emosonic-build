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
