/* Disposable observation state only. No playback state, clock or AV reads. */
#include <stdbool.h>
#include <stddef.h>
#include <math.h>
#define LAB_TIMING_LIMIT 65535u
#define LAB_TIMING_RECORDS 16u
typedef struct {
    double wallBeforeMs, wallAfterMs, monoBeforeMs, monoAfterMs;
    double requestedRate, nativeRate, effectiveRate;
    bool effectiveAvailable, identityMatches, playingIntent, seeking;
    int processingState, timeControl;
    unsigned owner, effectiveReadCount;
} LabTimingRates;
#define LAB_CLOCK_RECORDS 8u
#define LAB_CLOCK_FIRST 2u
typedef struct {
    unsigned sequence, owner, rateSequence, seekSequence;
    double positionMs, wallBeforeMs, wallAfterMs, monoBeforeMs, monoAfterMs;
    LabTimingRates rates;
    bool positionValid;
} LabClockPoint;
static inline bool LabClockPointUsable(LabClockPoint point) {
    return point.owner && point.positionValid && point.rates.identityMatches && point.rates.owner == point.owner &&
        isfinite(point.positionMs) && point.positionMs >= 0 && point.positionMs <= 86400000;
}
typedef struct {
    unsigned sequence, owner;
    double requested;
    LabTimingRates invocation, returned;
    bool returnedSeen, replyBegan, replyReturned, firstAnchorSeen, firstNativeSeen;
    double replyBeginWallMs, replyBeginMonoMs, replyEndWallMs, replyEndMonoMs;
    LabClockPoint priorAnchor, firstAnchor, firstNative;
} LabClockRate;
typedef struct {
    unsigned rates, nativeSamples, anchors, owner, unmatchedReplies;
    LabClockRate rate[LAB_CLOCK_RECORDS];
    LabClockPoint native[LAB_CLOCK_RECORDS], anchor[LAB_CLOCK_RECORDS];
} LabClockState;
static inline unsigned LabClockSlot(unsigned sequence) {
    return sequence <= LAB_CLOCK_FIRST ? sequence - 1 : LAB_CLOCK_FIRST +
        (sequence - LAB_CLOCK_FIRST - 1) % (LAB_CLOCK_RECORDS - LAB_CLOCK_FIRST);
}
static inline unsigned LabClockRetainedSequence(unsigned total, unsigned ordinal) {
    unsigned first = total < LAB_CLOCK_FIRST ? total : LAB_CLOCK_FIRST;
    if (ordinal < first) return ordinal + 1;
    unsigned start = total > LAB_CLOCK_RECORDS ? total - (LAB_CLOCK_RECORDS - LAB_CLOCK_FIRST) + 1 : LAB_CLOCK_FIRST + 1;
    unsigned sequence = start + ordinal - first;
    return sequence <= total ? sequence : 0;
}
static inline LabClockRate *LabClockFindRate(LabClockState *state, unsigned sequence) {
    if (!sequence || sequence > LAB_TIMING_LIMIT) return NULL;
    LabClockRate *record = &state->rate[LabClockSlot(sequence)];
    return record->sequence == sequence ? record : NULL;
}
typedef struct {
    unsigned sequence;
    double targetMs, callbackWallMs, callbackMonoMs;
    LabTimingRates invocation, completion;
    bool callbackSeen, completionSeen, finished, firstNativeSeen, firstAnchorSeen;
    LabClockPoint firstNative, firstAnchor;
} LabTimingSeek;
typedef struct {
    unsigned samplerCalls, samplerRejects[7], samplerAdmits;
    double anchorPositionMs, anchorWallMs, anchorRequestedRate, anchorNativeRate;
    double anchorEffectiveRate, anchorElapsedMs;
    double rejectedRequestedRate, rejectedNativeRate, rejectedEffectiveRate;
    unsigned seekInvocations, seekCallbacks, seekCompletions, unmatchedCallbacks, duplicateCallbacks;
    LabTimingSeek seeks[LAB_TIMING_RECORDS];
} LabTimingState;
static void LabTimingIncrement(unsigned *value) {
    if (*value < LAB_TIMING_LIMIT) ++*value;
}
static unsigned LabTimingBegin(LabTimingState *state, double targetMs, LabTimingRates rates) {
    if (state->seekInvocations == LAB_TIMING_LIMIT) return 0;
    unsigned sequence = ++state->seekInvocations;
    state->seeks[(sequence - 1) % LAB_TIMING_RECORDS] =
        (LabTimingSeek){.sequence=sequence, .targetMs=targetMs, .invocation=rates};
    return sequence;
}
static void LabTimingCallback(LabTimingState *state, unsigned sequence, double wallMs, double monoMs) {
    LabTimingIncrement(&state->seekCallbacks);
    if (!sequence || state->seeks[(sequence - 1) % LAB_TIMING_RECORDS].sequence != sequence) {
        LabTimingIncrement(&state->unmatchedCallbacks); return;
    }
    LabTimingSeek *record = &state->seeks[(sequence - 1) % LAB_TIMING_RECORDS];
    if (record->callbackSeen) {
        LabTimingIncrement(&state->duplicateCallbacks); return;
    }
    record->callbackSeen = true; record->callbackWallMs = wallMs; record->callbackMonoMs = monoMs;
}
static void LabTimingComplete(LabTimingState *state, unsigned sequence, bool finished, LabTimingRates rates) {
    LabTimingIncrement(&state->seekCompletions);
    if (!sequence || state->seeks[(sequence - 1) % LAB_TIMING_RECORDS].sequence != sequence) return;
    LabTimingSeek *record = &state->seeks[(sequence - 1) % LAB_TIMING_RECORDS];
    if (record->completionSeen) return;
    record->completionSeen = true; record->finished = finished; record->completion = rates;
}
