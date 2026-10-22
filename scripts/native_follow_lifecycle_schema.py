"""Static export vocabulary. No identities, raw logs, source lines or timestamps."""
STAGES = frozenset({'native-follow-command-observation'})
COUNT = ('integer', 0, 1000000)
CURSOR = ('integer', 0, 1000000000000)
SERVER_SCHEMA = {
    'status': frozenset({'read_only_snapshot', 'refused_expected_scope', 'refused_fixture_scope',
        'refused_database_scope', 'malformed_observation', 'observation_unavailable'}),
    'admissionObserved': frozenset({'accepted', 'unknown'}),
    'phase': frozenset({'active', 'reconnectGrace', 'cleanupRequired'}),
    **{key: bool for key in ('leasePresent', 'sourceContextMatches', 'suspendedContextMatches',
        'sourceAuthorityMatches', 'suspendedAuthorityMatchesFollower', 'startAckPresent',
        'startAckSourceMatches', 'startAckSuspendedMatches', 'sourceContextPresent',
        'sourceLifecycleActive', 'sourceAuthorityMatchesExpected', 'sourceQueueIndexValid',
        'sourceQueueTrackConsistent', 'sourceDevicePresent', 'sourceDeviceGenerationMatches',
        'sourceDeviceEpochMatches', 'sourceDeviceControlMatches', 'sourceDeviceIsAuthority',
        'sourceDeviceStateMatches', 'sourceDeviceTrackMatches', 'sourceDevicePositionValid',
        'sourceDeviceNonceMatchesLease', 'sourceRatesValid', 'sourceRatesMatch',
        'suspendedContextPresent', 'suspendedTrackMatchesOriginal', 'suspendedQueueMatchesOriginal',
        'suspendedIndexMatchesOriginal')},
    **{key: CURSOR for key in ('suspendedEpoch', 'suspendedVersion', 'suspendedQueueRevision',
        'suspendedControlVersion', 'suspendedAppliedControlVersion', 'sourceEpoch', 'sourceControlVersion')},
    **{key + 'AckMatches': bool for key in ('suspendedEpoch', 'suspendedVersion', 'suspendedQueueRevision',
        'suspendedControlVersion', 'suspendedAppliedControlVersion')},
    **{prefix + suffix: bool for prefix in ('reconnectGrace', 'sourceRecovery')
        for suffix in ('DeadlinePresent', 'Expired')},
    **{prefix + 'RemainingMs': ('number', -60000, 60000) for prefix in ('reconnectGrace', 'sourceRecovery')},
    **{key: frozenset({'idle', 'playing', 'paused', 'stopped', 'buffering', 'loading'})
        for key in ('sourceState', 'sourceDeviceState', 'suspendedState')},
    'sourceQueueLength': ('integer', 0, 10000),
    **{prefix + suffix: bool for prefix in ('sourceUpdated', 'sourceSample')
        for suffix in ('TimeValid', 'FreshWithin2s')},
    **{prefix + 'AgeMs': ('integer', 0, 60000) for prefix in ('sourceUpdated', 'sourceSample')},
}
PHASES = ('acquiring', 'active', 'restoring', 'stopPending')
REASONS = ('start_ack_failed', 'start_ack_missing', 'start_ack_mismatch', 'active_record_write_failed',
    'local_overlay_start_failed', 'source_context_closed', 'stop_while_acquiring', 'user_stop',
    'retry_stop_pending', 'application_restart_acquiring_cleanup', 'application_restart_cleanup',
    'reconnect_ack_mismatch', 'source_context_closed_on_reconnect', 'local_mirror_failure',
    'source_recovery_deadline', 'source_context_closed_during_recovery')
EVENTS = ('recovery_record_persisted', 'recovery_cleared', 'local_mirror_failure',
    'ignored_source_apply_failure', 'local_failure_recovery_pending', 'source_status_unavailable',
    'source_recovery_scheduled', 'source_recovery_retry_failed', 'restore_failed_keep_fence',
    'restore_failure_quiesce_failed', 'follow_stop_pending', 'stop_outcome_unknown_disconnect',
    'ready_settlement_failed')
SNAPSHOT_SCHEMA = {
    'runtimeMode': frozenset({'solo', 'follow', 'broadcast', 'not_observed', 'unrecognized'}),
    'recoveryPhase': frozenset(PHASES + ('terminalFeedbackPending', 'not_observed', 'unrecognized')),
    'processingState': frozenset({'idle', 'loading', 'buffering', 'ready', 'completed', 'not_observed', 'unrecognized'}),
    **{key: bool for key in ('followSourceMatches', 'sameFollowerIdentity', 'sameAuthorityIdentity',
        'originalTaskMatches', 'sourceTaskMatches', 'followRecoveryGateActive', 'restoreInProgress',
        'queueHydrating', 'seekInProgress', 'playingIntent', 'nativePlaying', 'nativePaused')},
    'requestedRate': ('number', 0, 10), 'positionMs': ('number', 0, 86400000),
}
LOG_SCHEMA = {
    'coverage': frozenset({'complete', 'partial', 'truncated', 'rotated', 'ownership_refused',
        'file_bound_exceeded', 'unavailable'}),
    'bytesRead': ('integer', 0, 8388608),
    **{key: bool for key in ('stackTruncated', 'lineTruncated', 'partialFinalLine', 'partialInitialLine', 'invalidEncoding')},
    **{key: COUNT for key in ('unknownReasonCount', 'unknownPhaseCount', 'seekBoundedTimeoutCount', 'speedRestoreFailedCount')},
    'events': {key: COUNT for key in EVENTS}, 'phases': {key: COUNT for key in PHASES},
    'clearReasons': {key: COUNT for key in REASONS},
    'mirrorCauses': {key: COUNT for key in ('missing_scope', 'stale_queue_owner', 'stale_account_context',
        'uncached_queue_metadata', 'incomplete_server_queue', 'source_not_cached', 'source_unavailable',
        'no_tracks', 'effective_deadline', 'other')},
    'mirrorStackFrames': {key: COUNT for key in ('queue_metadata_frame', 'source_policy_admission_frame',
        'scoped_native_queue_frame', 'queue_target_frame', 'remote_position_state_frame', 'native_seek_frame',
        'seek_command_frame', 'source_policy_frame', 'account_context_frame', 'player_source_load_frame',
        'player_seek_frame', 'player_play_frame')},
    'syncActions': {key: COUNT for key in ('applyTrackOrQueue', 'applyStateOnly', 'softCorrectDrift', 'hardSeek',
        'smoothCorrectDrift', 'ignoreProgressHeartbeat')},
}
FOLLOW_LIFECYCLE_SCHEMA = {
    'status': frozenset({'observing', 'observed', 'not_observed', 'observation_unavailable'}),
    'originalPausedTask': SNAPSHOT_SCHEMA, 'commandState': SNAPSHOT_SCHEMA,
    'commandDurationMs': ('number', 0, 45000),
    **{key: bool for key in ('commandReturned', 'commandOk', 'sampleCountSaturated',
        'transitionsTruncated', 'seenFollowRuntime', 'seenActiveRecovery', 'seenSourceTask',
        'seenNativeReady', 'seenRestoring', 'seenOriginalAfterFollow', 'identityChangeObserved')},
    'sampleCount': ('integer', 0, 1000), 'transitionCount': COUNT, 'observationErrorCount': COUNT,
    'transitions': ('list', {**SNAPSHOT_SCHEMA, 'phase': frozenset({'command_return', 'wait'}),
        'elapsedMs': ('number', 0, 90000)}, 12),
    'serverFollow': ('list', {'milestone': frozenset({'command_return', 'active_recovery', 'restoring',
        'original_after_follow', 'native_ready', 'failure'}), 'observation': SERVER_SCHEMA}, 6),
    'ownedLog': LOG_SCHEMA,
}
