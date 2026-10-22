- (NSDictionary *)labTimingObservationForPlayer:(AVQueuePlayer *)player item:(AVPlayerItem *)item {
    NSMutableArray *seeks = [NSMutableArray array];
    unsigned total = _labTiming.seekInvocations;
    unsigned first = total > LAB_TIMING_RECORDS ? total - LAB_TIMING_RECORDS + 1 : 1;
    for (unsigned sequence = first; sequence <= total; ++sequence) {
        LabTimingSeek record = _labTiming.seeks[(sequence - 1) % LAB_TIMING_RECORDS];
        [seeks addObject:@{
            @"sequence": @(record.sequence), @"targetMs": LabTimingNumber(record.targetMs),
            @"invocation": LabTimingRateDictionary(record.invocation),
            @"callbackSeen": @(record.callbackSeen), @"callbackWallMs": LabTimingNumber(record.callbackWallMs),
            @"callbackMonoMs": LabTimingNumber(record.callbackMonoMs),
            @"completionSeen": @(record.completionSeen), @"finished": @(record.finished),
            @"completion": LabTimingRateDictionary(record.completion)
        }];
    }
    NSMutableArray *rejects = [NSMutableArray array];
    for (unsigned index = 0; index < 7; ++index) [rejects addObject:@(_labTiming.samplerRejects[index])];
    return @{
        @"samplerCalls": @(_labTiming.samplerCalls), @"samplerRejects": rejects,
        @"samplerAdmits": @(_labTiming.samplerAdmits),
        @"anchorSamePlaybackIdentity": @((BOOL)(_labAnchorPlayer != nil && _labAnchorSource != nil && _labAnchorItem != nil &&
            _labAnchorPlayer == player && _labAnchorSource == _audioSource && _labAnchorItem == item && _labAnchorIndex == _index)),
        @"anchorPositionMs": LabTimingNumber(_labTiming.anchorPositionMs),
        @"anchorWallMs": LabTimingNumber(_labTiming.anchorWallMs),
        @"anchorRequestedRate": LabTimingNumber(_labTiming.anchorRequestedRate),
        @"anchorNativeRate": LabTimingNumber(_labTiming.anchorNativeRate),
        @"anchorEffectiveRate": LabTimingNumber(_labTiming.anchorEffectiveRate),
        @"anchorElapsedMs": LabTimingNumber(_labTiming.anchorElapsedMs),
        @"rejectedRequestedRate": LabTimingNumber(_labTiming.rejectedRequestedRate),
        @"rejectedNativeRate": LabTimingNumber(_labTiming.rejectedNativeRate),
        @"rejectedEffectiveRate": LabTimingNumber(_labTiming.rejectedEffectiveRate),
        @"seekInvocations": @(total), @"seekCallbacks": @(_labTiming.seekCallbacks),
        @"seekCompletions": @(_labTiming.seekCompletions),
        @"unmatchedCallbacks": @(_labTiming.unmatchedCallbacks),
        @"duplicateCallbacks": @(_labTiming.duplicateCallbacks), @"seeks": seeks
    };
}

- (LabTimingRates)labCaptureRatesForPlayer:(AVQueuePlayer *)player source:(AudioSource *)source item:(AVPlayerItem *)item index:(int)index {
    BOOL before = player && source && item && _player == player && _audioSource == source &&
        _index == index && player.currentItem == item;
    LabTimingRates rates = LabTimingCaptureRates(before ? player : nil, before ? _speed : NAN);
    BOOL after = before && _player == player && _audioSource == source && _index == index &&
        player.currentItem == item && rates.identityMatches;
    rates.identityMatches = after;
    if (!after) {
        rates.requestedRate = NAN; rates.nativeRate = NAN; rates.effectiveRate = NAN;
        rates.effectiveAvailable = false;
    }
    return rates;
}

- (unsigned)labObserveSeekInvocation:(CMTime)position player:(AVQueuePlayer *)player source:(AudioSource *)source item:(AVPlayerItem *)item index:(int)index {
    LabTimingRates rates = [self labCaptureRatesForPlayer:player source:source item:item index:index];
    return LabTimingBegin(&_labTiming, CMTIME_IS_NUMERIC(position) ? CMTimeGetSeconds(position) * 1000.0 : NAN, rates);
}

- (void)labObserveSeekCallback:(unsigned)sequence {
    double monotonic = [NSProcessInfo processInfo].systemUptime * 1000.0;
    double wall = [[NSDate date] timeIntervalSince1970] * 1000.0;
    LabTimingCallback(&_labTiming, sequence, wall, monotonic);
}

- (void)labObserveSeekCompletion:(unsigned)sequence finished:(BOOL)finished player:(AVQueuePlayer *)player source:(AudioSource *)source item:(AVPlayerItem *)item index:(int)index {
    LabTimingRates rates = [self labCaptureRatesForPlayer:player source:source item:item index:index];
    LabTimingComplete(&_labTiming, sequence, finished, rates);
}
