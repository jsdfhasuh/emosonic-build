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
            @"completion": LabTimingRateDictionary(record.completion),
            @"firstNativeSeen": @(record.firstNativeSeen), @"firstNative": record.firstNativeSeen ? LabClockPointDictionary(record.firstNative) : [NSNull null],
            @"firstAnchorSeen": @(record.firstAnchorSeen), @"firstAnchor": record.firstAnchorSeen ? LabClockPointDictionary(record.firstAnchor) : [NSNull null]
        }];
    }
    NSMutableArray *rejects = [NSMutableArray array];
    for (unsigned index = 0; index < 7; ++index) [rejects addObject:@(_labTiming.samplerRejects[index])];
    return @{
        @"clockObservation": [self labClockObservation],
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
    rates.playingIntent = _playing;
    rates.seeking = CMTIME_IS_VALID(_seekPos);
    rates.processingState = (int)_processingState;
    rates.timeControl = player ? (int)player.timeControlStatus : -1;
    rates.owner = after ? [self labClockOwnerForPlayer:player item:item] : 0;
    after = after && rates.owner > 0;
    rates.identityMatches = after;
    rates.wallAfterMs = [[NSDate date] timeIntervalSince1970] * 1000.0;
    rates.monoAfterMs = [NSProcessInfo processInfo].systemUptime * 1000.0;
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


// Diagnostic ownership only. Weak slots never retain a source across callbacks.
- (unsigned)labClockOwnerForPlayer:(AVQueuePlayer *)player item:(AVPlayerItem *)item {
    if (!player || !item || !_audioSource || player != _player || player.currentItem != item) return 0;
    if (_labClockPlayer != player || _labClockSource != _audioSource || _labClockItem != item || _labClockIndex != _index) {
        if (_labClock.owner == LAB_TIMING_LIMIT) return 0;
        ++_labClock.owner;
        _labClockPlayer = player; _labClockSource = _audioSource; _labClockItem = item; _labClockIndex = _index;
    }
    return _labClock.owner;
}

- (unsigned)labObserveRateInvocation:(double)requested player:(AVQueuePlayer *)player source:(AudioSource *)source item:(AVPlayerItem *)item index:(int)index {
    if (_labClock.rates == LAB_TIMING_LIMIT) return 0;
    LabTimingRates rates = [self labCaptureRatesForPlayer:player source:source item:item index:index];
    unsigned sequence = ++_labClock.rates;
    LabClockRate record = {.sequence=sequence, .owner=rates.owner, .requested=requested, .invocation=rates};
    if (_labClock.anchors) {
        LabClockPoint prior = _labClock.anchor[LabClockSlot(_labClock.anchors)];
        if (prior.owner && prior.owner == rates.owner) record.priorAnchor = prior;
    }
    _labClock.rate[LabClockSlot(sequence)] = record;
    return sequence;
}

- (void)labObserveRateReturn:(unsigned)sequence player:(AVQueuePlayer *)player source:(AudioSource *)source item:(AVPlayerItem *)item index:(int)index {
    LabClockRate *record = LabClockFindRate(&_labClock, sequence);
    if (!record) return;
    record->returned = [self labCaptureRatesForPlayer:player source:source item:item index:index];
    record->returnedSeen = true;
}

- (void)labObserveRateReply:(unsigned)sequence returned:(BOOL)returned {
    LabClockRate *record = LabClockFindRate(&_labClock, sequence);
    if (!record) { LabTimingIncrement(&_labClock.unmatchedReplies); return; }
    double mono = [NSProcessInfo processInfo].systemUptime * 1000.0;
    double wall = [[NSDate date] timeIntervalSince1970] * 1000.0;
    if (returned) { record->replyReturned = true; record->replyEndMonoMs = mono; record->replyEndWallMs = wall; }
    else { record->replyBegan = true; record->replyBeginMonoMs = mono; record->replyBeginWallMs = wall; }
}

- (void)labStoreClockPoint:(LabClockPoint)point anchor:(BOOL)anchor {
    unsigned *count = anchor ? &_labClock.anchors : &_labClock.nativeSamples;
    if (*count == LAB_TIMING_LIMIT) return;
    point.sequence = ++*count;
    point.rateSequence = _labClock.rates;
    point.seekSequence = _labTiming.seekInvocations;
    (anchor ? _labClock.anchor : _labClock.native)[LabClockSlot(point.sequence)] = point;
    LabClockRate *rate = LabClockFindRate(&_labClock, point.rateSequence);
    if (rate && rate->returnedSeen && LabClockPointUsable(point) && point.owner == rate->owner &&
        rate->returned.owner == rate->owner && point.rates.identityMatches &&
        point.rates.requestedRate == rate->requested &&
        point.monoBeforeMs >= rate->returned.monoAfterMs) {
        if (anchor && !rate->firstAnchorSeen) { rate->firstAnchorSeen = true; rate->firstAnchor = point; }
        if (!anchor && !rate->firstNativeSeen) { rate->firstNativeSeen = true; rate->firstNative = point; }
    }
    {
        for (unsigned i=0; i<LAB_TIMING_RECORDS; ++i) {
            LabTimingSeek *seek = &_labTiming.seeks[i];
            if (seek->sequence == point.seekSequence && seek->sequence && seek->completionSeen && LabClockPointUsable(point) &&
                seek->invocation.owner == point.owner && seek->completion.owner == point.owner &&
                point.rates.identityMatches && point.monoBeforeMs >= seek->completion.monoAfterMs) {
                if (anchor && !seek->firstAnchorSeen) { seek->firstAnchorSeen = true; seek->firstAnchor = point; }
                if (!anchor && !seek->firstNativeSeen) { seek->firstNativeSeen = true; seek->firstNative = point; }
            }
        }
    }
}

- (void)labObserveNativePosition:(CMTime)position player:(AVQueuePlayer *)player item:(AVPlayerItem *)item owner:(unsigned)owner wallBefore:(double)wallBefore wallAfter:(double)wallAfter monoBefore:(double)monoBefore monoAfter:(double)monoAfter {
    LabTimingRates rates = [self labCaptureRatesForPlayer:player source:_audioSource item:item index:_index];
    BOOL same = owner && rates.owner == owner && rates.identityMatches;
    if (!same) { rates.identityMatches = false; rates.owner = 0; }
    LabClockPoint point = {.owner=same ? owner : 0, .positionMs=CMTIME_IS_NUMERIC(position) ? CMTimeGetSeconds(position)*1000.0 : NAN,
        .positionValid=CMTIME_IS_NUMERIC(position) && same, .wallBeforeMs=wallBefore, .wallAfterMs=wallAfter,
        .monoBeforeMs=monoBefore, .monoAfterMs=monoAfter, .rates=rates};
    [self labStoreClockPoint:point anchor:NO];
}

- (NSDictionary *)labClockObservation {
    NSMutableArray *rates = [NSMutableArray array], *native = [NSMutableArray array], *anchors = [NSMutableArray array];
    for (unsigned i=0; i<LAB_CLOCK_RECORDS; ++i) {
        unsigned sequence = LabClockRetainedSequence(_labClock.rates, i);
        if (sequence) {
            LabClockRate row = _labClock.rate[LabClockSlot(sequence)];
            [rates addObject:@{ @"sequence": @(row.sequence), @"owner": @(row.owner), @"requested": LabTimingNumber(row.requested),
                @"invocation": LabTimingRateDictionary(row.invocation), @"returned": LabTimingRateDictionary(row.returned), @"returnedSeen": @(row.returnedSeen),
                @"replyBegan": @(row.replyBegan), @"replyReturned": @(row.replyReturned),
                @"replyBeginMonoMs": LabTimingNumber(row.replyBeginMonoMs), @"replyBeginWallMs": LabTimingNumber(row.replyBeginWallMs),
                @"replyEndMonoMs": LabTimingNumber(row.replyEndMonoMs), @"replyEndWallMs": LabTimingNumber(row.replyEndWallMs),
                @"priorAnchor": row.priorAnchor.sequence ? LabClockPointDictionary(row.priorAnchor) : [NSNull null],
                @"firstAnchorSeen": @(row.firstAnchorSeen), @"firstAnchor": row.firstAnchorSeen ? LabClockPointDictionary(row.firstAnchor) : [NSNull null],
                @"firstNativeSeen": @(row.firstNativeSeen), @"firstNative": row.firstNativeSeen ? LabClockPointDictionary(row.firstNative) : [NSNull null] }];
        }
        sequence = LabClockRetainedSequence(_labClock.nativeSamples, i);
        if (sequence) [native addObject:LabClockPointDictionary(_labClock.native[LabClockSlot(sequence)])];
        sequence = LabClockRetainedSequence(_labClock.anchors, i);
        if (sequence) [anchors addObject:LabClockPointDictionary(_labClock.anchor[LabClockSlot(sequence)])];
    }
    return @{ @"rateCount": @(_labClock.rates), @"nativeCount": @(_labClock.nativeSamples), @"anchorCount": @(_labClock.anchors),
        @"ownerCount": @(_labClock.owner), @"unmatchedReplies": @(_labClock.unmatchedReplies),
        @"rates": rates, @"native": native, @"anchors": anchors };
}
