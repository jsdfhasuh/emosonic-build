/* Only actual seek events add CoreMedia rate reads. There are no position reads. */
static id LabTimingNumber(double value) {
    return isfinite(value) ? @(value) : [NSNull null];
}
static LabTimingRates LabTimingCaptureRates(AVQueuePlayer *player, double requested) {
    LabTimingRates sample = {0};
    sample.monoBeforeMs = [NSProcessInfo processInfo].systemUptime * 1000.0;
    sample.wallBeforeMs = [[NSDate date] timeIntervalSince1970] * 1000.0;
    sample.requestedRate = requested;
    sample.nativeRate = player ? player.rate : NAN;
    sample.effectiveRate = NAN;
    AVPlayerItem *item = player.currentItem;
    CMTimebaseRef timebase = item.timebase;
    if (timebase) {
        CFRetain(timebase);
        sample.effectiveRate = CMTimebaseGetEffectiveRate(timebase);
        sample.effectiveAvailable = isfinite(sample.effectiveRate);
        sample.identityMatches = player.currentItem == item && item.timebase == timebase;
        CFRelease(timebase);
    } else {
        sample.identityMatches = player && item && player.currentItem == item;
    }
    sample.wallAfterMs = [[NSDate date] timeIntervalSince1970] * 1000.0;
    sample.monoAfterMs = [NSProcessInfo processInfo].systemUptime * 1000.0;
    return sample;
}
static NSDictionary *LabTimingRateDictionary(LabTimingRates value) {
    return @{
        @"wallBeforeMs": LabTimingNumber(value.wallBeforeMs), @"wallAfterMs": LabTimingNumber(value.wallAfterMs),
        @"monoBeforeMs": LabTimingNumber(value.monoBeforeMs), @"monoAfterMs": LabTimingNumber(value.monoAfterMs),
        @"requestedRate": LabTimingNumber(value.requestedRate), @"nativeRate": LabTimingNumber(value.nativeRate),
        @"effectiveRate": LabTimingNumber(value.effectiveRate), @"effectiveAvailable": @(value.effectiveAvailable),
        @"identityMatches": @(value.identityMatches)
    };
}
