/* Disposable observation state only. No playback state, clock or AV reads. */
#include <stdbool.h>
#include <math.h>
#define LAB_TIMING_LIMIT 65535u
#define LAB_TIMING_RECORDS 16u
typedef struct {
    double wallBeforeMs, wallAfterMs, monoBeforeMs, monoAfterMs;
    double requestedRate, nativeRate, effectiveRate;
    bool effectiveAvailable, identityMatches;
} LabTimingRates;
typedef struct {
    unsigned sequence;
    double targetMs, callbackWallMs, callbackMonoMs;
    LabTimingRates invocation, completion;
    bool callbackSeen, completionSeen, finished;
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
