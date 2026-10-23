"""Static export vocabulary. No identities, raw logs, source lines or timestamps."""
STAGES = frozenset({'native-follow-command-observation'})
COUNT = ('integer', 0, 1000000)
CURSOR = ('integer', 0, 1000000000000)
BOOTSTRAP_SCHEMA = {
    'byteCoverage': frozenset({'whole_current_file', 'tail_only', 'partial', 'unavailable'}),
    'launchCoverage': frozenset({'unknown'}), 'lineIssues': COUNT, 'countsSaturated': bool,
    'startup': {key: COUNT for key in ('connect', 'requested', 'failed')},
    'other': {key: COUNT for key in ('joined', 'stale', 'aborted', 'unknown')},
    'stages': {stage: {status: COUNT for status in ('started', 'completed', 'timed_out', 'failed')}
        for stage in ('client_id', 'device_session_id', 'device_alias',
            'playback_context_outbox', 'follow_recovery', 'broadcast_recovery')},
}
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
CORRECTION_REASONS = ('settled', 'hard_drift', 'transport_paused', 'transport_replaced',
    'policy_preempted', 'target_changed', 'rate_owner_changed', 'owner_changed', 'source_changed', 'restore_not_acknowledged', 'seek_error', 'start_follow',
    'start_context_follow', 'stop_follow', 'stop_context_follow', 'restore_context_follow',
    'complete_context_follow_stop', 'source_idle', 'strict_source_rate_changed',
    'drift_within_tolerance', 'hard_seek', 'apply_follow', 'timer', 'dispose',
    'socket_disconnect', 'disconnect', 'soft_seek', 'reset_follow_sync', 'native_receipts_closed')
CORRECTION_EVENTS = ('action_decision', 'seek_recovery_cancelled', 'seek_recovery_exhausted',
    'seek_recovery_restore_failed', 'speed_correction_apply', 'speed_correction_restore',
    'speed_correction_restore_failed', 'speed_setting_invocation')
CORRECTION_SEQUENCE_SCHEMA = {
    'timeBasis': frozenset({'first_selected_log_event_wall'}),
    'recordRetention': frozenset({'first64_last64'}),
    'monotonicClockPaired': bool, 'recoveryWindowStartObserved': bool,
    'wallClockRegressionObserved': bool, 'recordsTruncated': bool,
    **{name: COUNT for name in ('eventCount', 'recordsDropped', 'unknownReasonCount', 'invalidFieldCount', 'timestampIssueCount')},
    'counts': {name: COUNT for name in CORRECTION_EVENTS},
    'records': ('list', {
        'ordinal': ('integer', 1, 1000000), 'event': frozenset(CORRECTION_EVENTS),
        'timeStatus': frozenset({'unavailable', 'unpaired_wall'}), 'wallOffsetMs': ('number', -600000, 600000),
        'action': frozenset({'applyTrackOrQueue', 'applyStateOnly', 'softCorrectDrift', 'hardSeek',
            'smoothCorrectDrift', 'ignoreProgressHeartbeat'}),
        'reason': frozenset(CORRECTION_REASONS + ('unrecognized',)), 'supported': bool,
        'positionMs': ('integer', 0, 86400000), 'settled': bool, 'sourceControlChanged': bool,
        'correction': frozenset({'speedUp', 'slowDown', 'rateLimited', 'seek', 'none'}),
        'adaptiveFollowDelayMs': ('integer', 0, 60000), 'followLeadCompensationMs': ('integer', -60000, 60000),
        'followSyncToleranceMs': ('integer', 0, 60000),
        'driftMs': ('integer', -86400000, 86400000), 'durationMs': ('integer', 0, 5000),
        **{name: ('number', .5, 2) for name in ('rate', 'baseSpeed', 'syncSpeed')},
    }, 128),
}
RECOVERY_CHECK_REASONS = ('recovery_started', 'receipt_accepted', 'wake_deferred', 'wake_queued_ignored', 'wake_busy', 'wake_dispatch', 'check_enter', 'inactive_or_cancelled', 'owner_or_service_changed', 'source_owner_changed', 'deadline_reached', 'exhausted_or_ticking', 'source_not_current', 'seek_pending', 'missing_nominal_ack', 'anchor_snapshot', 'baseline_stale', 'baseline_adopted', 'missing_or_nonprogressing_anchor', 'anchor_age_rejected', 'nominal_floor_rejected', 'nominal_progress_rejected', 'effective_anchor_too_early', 'nonfinite_drift', 'eligible_progress', 'before_rate_write', 'check_finally', 'seek_future_finally', 'truncated')
RECOVERY_CHECK_SCHEMA = {
    'status': frozenset({'unavailable', 'invalid', 'observed'}),
    'coverage': frozenset({'complete', 'incomplete'}),
    'snapshotBasis': frozenset({'existing_state_endpoint_not_alignment_sample'}),
    'sequenceBasis': frozenset({'vendor_position_receipt_not_native_observer_ordinal'}),
    'timeBasis': frozenset({'existing_control_flow_values_no_new_clock'}),
    'nullFields': frozenset({'omitted_unavailable'}),
    'producerStatus': frozenset({'recording', 'truncated'}),
    'schemaVersion': ('integer', 1, 1), 'recordLimit': ('integer', 128, 128),
    'truncationRecordLimit': ('integer', 1, 1), 'attemptCount': ('integer', 0, 129),
    'droppedCount': COUNT, 'droppedCountSaturated': bool,
    'records': ('list', {
        'v': ('integer', 1, 1), 'eventOrdinal': ('integer', 1, 129),
        'recoveryOrdinal': ('integer', 0, 129), 'reason': frozenset(RECOVERY_CHECK_REASONS),
        **{key: ('integer', -9007199254740991, 9007199254740991)
           for key in ('cachedSequence', 'baselineSequence', 'lastObservedSequence', 'nominalSequenceFloor')},
        **{key: bool for key in ('seekPending', 'ticking', 'supported', 'ownedRatePresent', 'receiptPending', 'receiptScheduled', 'cancelled', 'exhausted')},
        'ageMs': ('number', -86400000, 86400000),
        'floorPositionMs': ('integer', -86400000, 86400000),
    }, 129),
}
PLAY_POLICY_PHASES = ('policy_begin', 'policy_end', 'policy_threw',
    'post_policy_owner_rejected', 'post_policy_owner_accepted', 'play_submitted',
    'native_baseline', 'native_progress', 'superseded_trigger', 'superseded_seek',
    'disposed', 'player_recreated', 'closed', 'truncated')
PLAY_POLICY_SCHEMA = {
    'status': frozenset({'unavailable', 'invalid', 'observed'}),
    'coverage': frozenset({'complete', 'incomplete'}),
    'snapshotBasis': frozenset({'existing_state_endpoint_not_alignment_sample'}),
    'timeBasis': frozenset({'process_local_stopwatch_not_native_clock'}),
    'receiptBasis': frozenset({'accepted_service_receipt_not_native_observer_ordinal'}),
    'measurementMeaning': frozenset({'in_process_observation_not_native_start_latency'}),
    'nativeLoadAttribution': frozenset({'unverified'}),
    'nullFields': frozenset({'omitted_unavailable'}),
    'producerStatus': frozenset({'recording', 'truncated'}),
    'schemaVersion': ('integer', 1, 1), 'recordLimit': ('integer', 32, 32),
    'truncationRecordLimit': ('integer', 1, 1), 'attemptCount': ('integer', 0, 33),
    'droppedCount': COUNT, 'droppedCountSaturated': bool,
    'pendingTriggerOrdinal': ('integer', 1, 32),
    'records': ('list', {
        'eventOrdinal': ('integer', 1, 33), 'triggerOrdinal': ('integer', 1, 32),
        'phase': frozenset(PLAY_POLICY_PHASES),
        'elapsedUs': ('integer', 0, 9007199254740991),
        'vendorSequence': ('integer', 0, 9007199254740991),
        'policyOutcome': frozenset({'local', 'remote', 'denied', 'unknown'}),
        'cacheKind': frozenset({'cached', 'network', 'unknown'}),
        'nativeLoadAttribution': frozenset({'unverified'}),
        **{key: bool for key in ('currentTrigger', 'serviceOwnerMatches',
            'sampleAfterPlayRequest', 'receiptProgress')},
    }, 33),
}
ADMISSION_REASONS = ('payload_not_playing', 'existing_attempt_owner',
    'rate_or_not_playing', 'prepared_not_allowed_or_unsupported',
    'prepared_owner_missing', 'prepared_owner_threw', 'cache_not_ready_or_stale', 'admitted')
ADMISSION_PATHS = ('unknown', 'cache', 'prepared')
ADMISSION_PREPARED_REASONS = ('unsupported_or_unhydrated_or_not_ready',
    'native_anchor_missing', 'native_anchor_not_ready_or_stale', 'owner_rejected', 'owner_accepted')
ADMISSION_SCHEMA = {
    'status': frozenset({'unavailable', 'invalid', 'observed'}),
    'coverage': frozenset({'complete', 'incomplete'}),
    'snapshotBasis': frozenset({'existing_state_endpoint_not_alignment_sample'}),
    'ordinalBasis': frozenset({'begin_invocation_not_recovery_or_native_owner'}),
    'scope': frozenset({'begin_attempts_not_all_policy_routes'}),
    'callerAttribution': frozenset({'unverified'}),
    'measurementMeaning': frozenset({'admission_not_seek_completion_or_readiness'}),
    'nullFields': frozenset({'omitted_unavailable'}),
    'schemaVersion': ('integer', 1, 1), 'attemptCount': ('integer', 0, 5),
    'overflow': bool, 'droppedCount': COUNT, 'droppedCountSaturated': bool,
    'summaries': ('list', {
        'invocationOrdinal': ('integer', 1, 4), 'reason': frozenset(ADMISSION_REASONS),
        'path': frozenset(ADMISSION_PATHS), 'preparedReason': frozenset(ADMISSION_PREPARED_REASONS),
    }, 4),
}
ENDPOINT_TIMING_SCHEMA = {
    'status': frozenset({'observed', 'unavailable'}),
    'meaning': frozenset({'latest_stored_fact_not_controller_decision'}),
    'clients': ('list', {
        'clientOrdinal': ('integer', 0, 2),
        'recoveryChecks': RECOVERY_CHECK_SCHEMA,
        'playPolicy': PLAY_POLICY_SCHEMA,
        'recoveryAdmission': ADMISSION_SCHEMA,
        **{name: ('number', 0, 60000) for name in ('runtimeAdaptiveDelayMs', 'configuredMinDelayMs',
            'configuredMaxDelayMs', 'observedProjectionDelayMs')},
        **{name: ('number', -86400000, 86400000) for name in ('lastObservedControllerDriftMs',
            'nativeMinusObservedTargetAtDartReadMs')},
        **{name: ('number', -60000, 600000) for name in ('observedSourceSampleAgeMs', 'observedSourceReceiveAgeMs')},
        'observedSourceAppliedControlVersion': ('number', 0, 1e12),
        **{name: bool for name in ('observedSourceFactPresent', 'observedSourceFactMatchesCurrent', 'observedSourceTimingValid')},
        'observedProjectionBasis': frozenset({'strict_sampled_at', 'unavailable'}),
        **{name: ('number', 0, 86400000) for name in ('observedProjectedTargetMs', 'dartPositionMs', 'nativePositionMs')},
        'serverClockOffsetMs': ('number', -600000, 600000), 'dartReadSkewMs': ('number', -1000, 1000),
        'latencySampleCount': COUNT,
        'nativeRate': ('number', 0, 2), 'requestedRate': ('number', .5, 2),
        'nativeSampleUncertaintyMs': ('number', 0, 1000),
        'dartSampleUncertaintyMs': ('number', 0, 1000),
    }, 3),
}
LOG_SCHEMA = {
    'correctionSequence': CORRECTION_SEQUENCE_SCHEMA,
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
    'endpointTiming': ENDPOINT_TIMING_SCHEMA,
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
