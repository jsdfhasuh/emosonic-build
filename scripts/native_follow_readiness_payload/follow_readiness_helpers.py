def follow_correction_identity(states, authority_index, context):
    """Private equality token only: no identities are emitted to diagnostics."""
    assert isinstance(states, list) and len(states) == 3
    authority, follower = states[authority_index], states[2]
    assert isinstance(context, str) and context
    assert authority.get('contextId') == context
    assert follower.get('runtimeMode') == 'follow'
    assert follower.get('followSourceContextId') == context
    queue, index = authority.get('queue'), authority.get('currentIndex')
    assert isinstance(queue, list) and queue and all(isinstance(v, str) and v for v in queue)
    assert type(index) is int and 0 <= index < len(queue)
    assert authority.get('trackId') == queue[index]
    assert follower.get('queue') == queue and follower.get('trackId') == queue[index]
    assert type(follower.get('currentIndex')) is int and follower['currentIndex'] == index
    identities = []
    source_cursors = []
    for state in (authority, follower):
        assert state.get('identitySeedMatches') is True
        assert state.get('connection') == 'ready' and state.get('strictV2') is True
        assert state.get('followNegotiated') is True
        for key in ('clientId', 'deviceSessionId', 'contextId', 'bundleId', 'root'):
            assert isinstance(state.get(key), str) and state[key]
        assert type(state.get('pid')) is int and state['pid'] > 0
        native = decoded(state)
        preflight = state.get('preflightDiagnostics') or {}
        generation = preflight.get('connectionGeneration')
        assert type(generation) is int and generation >= 0
        canonical = (state.get('contexts') or {}).get(context) or {}
        assert canonical.get('authorityClientId') == authority['clientId']
        assert canonical.get('authorityDeviceSessionId') == authority['deviceSessionId']
        cursors = tuple(canonical.get(key) for key in ('epoch', 'controlVersion', 'queueRevision'))
        assert all(type(value) is int and value > 0 for value in cursors)
        source_cursors.append(cursors)
        identities.append((state['clientId'], state['deviceSessionId'], state['contextId'],
            state['pid'], state['bundleId'], state['root'], native['id'], generation, canonical['authorityClientId'],
            canonical['authorityDeviceSessionId'], cursors))
    assert source_cursors[0] == source_cursors[1]
    recovery = follower.get('preflightDiagnostics') or {}
    assert recovery.get('followRecoveryGateActive') is True
    assert recovery.get('recoveryKind') == 'follow' and recovery.get('recoveryPhase') == 'active'
    assert recovery.get('recoveryContextMatchesCurrent') is True
    assert recovery.get('recoveryAuthorityMatchesSelf') is True
    versions = tuple(recovery.get(key) for key in ('recoveryControlVersion', 'recoveryAppliedControlVersion'))
    assert all(type(value) is int and value > 0 for value in versions)
    assert versions[0] == versions[1]
    assert recovery.get('queueHydrating') is False and recovery.get('restoreInProgress') is False
    return (context, tuple(queue), index, tuple(identities), versions)


def native_follow_readiness_pending(authority, follower, expected):
    """Known native seek/preroll states, never proof of a correction's cause.

    Only the premeasurement alignment loop may wait here. Its original five-
    second deadline, exact task identity and later continuous window stay fixed.
    Native preroll can follow either seek completion or source preparation.
    Generic paused playback without an actual in-flight seek is not pending.
    """
    a, f = decoded(authority), decoded(follower)
    common = (a['playbackState'] == 3 and native_rate_matches(authority, expected)
        and f.get('playingIntent') is True and type(f.get('seekInProgress')) is bool
        and f['avPlayerStatus'] == 1 and f['avItemStatus'] == 1 and f['durationMs'] > 0
        and type(f.get('requestedRate')) in (int, float) and math.isfinite(f['requestedRate'])
        and abs(f['requestedRate'] - expected) < 0.0001
        and follower.get('processingState') == 'buffering')
    if not common:
        return False
    seeking = (f['playbackState'] == 4 and f['avTimeControlStatus'] == 0
        and f['playbackRate'] == 0 and f['seekInProgress'] is True)
    preroll = (f['playbackState'] == 2 and f['avTimeControlStatus'] == 1
        and type(f.get('playbackRate')) in (int, float) and math.isfinite(f['playbackRate'])
        and abs(f['playbackRate'] - expected) < 0.0001)
    return seeking or preroll
