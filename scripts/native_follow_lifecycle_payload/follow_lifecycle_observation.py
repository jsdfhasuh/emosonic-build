"""Finite, read-only evidence for one owned native Follow-start attempt.

No commands, network calls, sleeps, acceptance gates, or deadline changes.
Private identities stay in memory solely for equality and ownership checks.
"""
import io
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import stat
import time

from follow_server_observation import observe_follow_server

MAX_LOG = 8 * 1024 * 1024
MAX_LINE = 8192
MAX_COUNT = 1000000
PHASES = ('acquiring', 'active', 'restoring', 'stopPending')
REASONS = ('start_ack_failed', 'start_ack_missing', 'start_ack_mismatch',
    'active_record_write_failed', 'local_overlay_start_failed', 'source_context_closed',
    'stop_while_acquiring', 'user_stop', 'retry_stop_pending',
    'application_restart_acquiring_cleanup', 'application_restart_cleanup',
    'reconnect_ack_mismatch', 'source_context_closed_on_reconnect', 'local_mirror_failure',
    'source_recovery_deadline', 'source_context_closed_during_recovery')
EVENTS = ('recovery_record_persisted', 'recovery_cleared', 'local_mirror_failure',
    'ignored_source_apply_failure', 'local_failure_recovery_pending', 'source_status_unavailable',
    'source_recovery_scheduled', 'source_recovery_retry_failed', 'restore_failed_keep_fence',
    'restore_failure_quiesce_failed', 'follow_stop_pending', 'stop_outcome_unknown_disconnect',
    'ready_settlement_failed')
CAUSES = {
    '请选择已登录的服务器': 'missing_scope',
    '原账号的播放队列已经失效': 'stale_queue_owner',
    '账号已切换，已忽略原账号的操作': 'stale_account_context',
    '指定队列含未缓存的歌曲资料，当前无法准备播放': 'uncached_queue_metadata',
    '服务器未返回指定队列的全部歌曲，队列未改变': 'incomplete_server_queue',
    '此歌曲尚未下载，需要联网才能播放': 'source_not_cached',
    '当前歌曲尚未下载': 'source_not_cached',
    '服务器离线，音频来源已失效，请重试本机歌曲': 'source_unavailable',
    'No requested Broadcast tracks could be resolved': 'no_tracks',
    'Effective-at execution exceeded the 1000ms late limit': 'effective_deadline',
}
FRAMES = {
    'AudioPlayerService._getScopedQueueSongs': 'queue_metadata_frame',
    'AudioPlayerService._requireSongPlayable': 'source_policy_admission_frame',
    'AudioPlayerService._playScopedConcatenatingSource': 'scoped_native_queue_frame',
    'AudioPlayerService._setQueuePlaybackTarget': 'queue_target_frame',
    'AudioPlayerService._applyRemotePlaybackPositionAndState': 'remote_position_state_frame',
    'AudioPlayerService._seekNative': 'native_seek_frame',
    'AudioPlayerService._executeSeek': 'seek_command_frame',
    'PlaybackSourcePolicy.evaluate': 'source_policy_frame',
    'PlaybackSourcePolicy.evaluateQueue': 'source_policy_frame',
    'OfflineRequestContext.ensureCurrent': 'account_context_frame',
    'AudioPlayer.setAudioSource': 'player_source_load_frame',
    'AudioPlayer._setAudioSource': 'player_source_load_frame',
    'AudioPlayer.seek': 'player_seek_frame',
    'AudioPlayer.play': 'player_play_frame',
}
ACTIONS = ('applyTrackOrQueue', 'applyStateOnly', 'softCorrectDrift', 'hardSeek',
           'smoothCorrectDrift', 'ignoreProgressHeartbeat')
MARKER = '[[EMO_FOLLOW_R18]] '
LOG_ENTRY = re.compile(r'^\[\d{4}-\d{2}-\d{2}T[\d:.+Z-]+\] \[(?:DEBUG|INFO|WARNING|ERROR)\] \[[A-Za-z0-9_.]+\] (.*)$')
CORRECTION_REASONS = ('settled', 'hard_drift', 'transport_paused', 'transport_replaced',
    'policy_preempted', 'target_changed', 'rate_owner_changed', 'owner_changed', 'source_changed', 'restore_not_acknowledged', 'seek_error', 'start_follow',
    'start_context_follow', 'stop_follow', 'stop_context_follow', 'restore_context_follow',
    'complete_context_follow_stop', 'source_idle', 'strict_source_rate_changed',
    'drift_within_tolerance', 'hard_seek', 'apply_follow', 'timer', 'dispose',
    'socket_disconnect', 'disconnect', 'soft_seek', 'reset_follow_sync', 'native_receipts_closed')
CORRECTION_EVENTS = ('action_decision', 'seek_recovery_cancelled', 'seek_recovery_exhausted',
    'seek_recovery_restore_failed', 'speed_correction_apply', 'speed_correction_restore',
    'speed_correction_restore_failed', 'speed_setting_invocation')
CORRECTION_LIMIT = 128


def _finite_field(token, low, high, *, integer=False):
    pattern = r'-?\d+' if integer else r'-?(?:\d+(?:\.\d+)?)(?:[eE][+-]?\d+)?'
    if not isinstance(token, str) or len(token) > 32 or re.fullmatch(pattern, token) is None:
        return None
    value = int(token) if integer else float(token)
    return value if math.isfinite(value) and low <= value <= high else None


def _correction_event(body, logger):
    """Known invocation/decision logs only, never evidence of native completion."""
    if logger == 'AudioPlayerService' and body.startswith('Setting playback speed to: '):
        value = _finite_field(body[len('Setting playback speed to: '):], .5, 2)
        return {'event': 'speed_setting_invocation', **({'rate': value} if value is not None else {})}, int(value is None)
    if logger != 'EmoRealtimeClient' or not body.startswith('[[EMO_FOLLOW_SYNC]] '):
        return None, 0
    body = body[len('[[EMO_FOLLOW_SYNC]] '):]
    if body.startswith('action='):
        action = body.split(' ', 1)[0][7:]
        if action not in ACTIONS: return None, 0
        row = {'event': 'action_decision', 'action': action}
        # These are the existing ordinary-policy decision inputs logged BEFORE
        # bounded recovery handling, not its later common-time recovery drift.
        match = re.fullmatch(r'action=\S+ trackId=\S+ index=\S+ positionMs=(\S+) driftMs=(\S+) '
            r'correction=(\S+) settled=(\S+) adaptiveFollowDelayMs=(\S+) followLeadCompensationMs=(\S+) '
            r'followSyncToleranceMs=(\S+) latencySamples=\S+ sourceControlChanged=(\S+)', body)
        if not match: return row, 1
        position, drift, correction, settled, delay, lead, tolerance, changed = match.groups()
        invalid = 0
        for token, key, low, high in ((position, 'positionMs', 0, 86400000),
                (drift, 'driftMs', -86400000, 86400000), (delay, 'adaptiveFollowDelayMs', 0, 60000),
                (lead, 'followLeadCompensationMs', -60000, 60000), (tolerance, 'followSyncToleranceMs', 0, 60000)):
            value = _finite_field(token, low, high, integer=True)
            if value is not None: row[key] = value
            else: invalid += 1
        for token, key in ((settled, 'settled'), (changed, 'sourceControlChanged')):
            if token in ('true', 'false'): row[key] = token == 'true'
            else: invalid += 1
        if correction in ('speedUp', 'slowDown', 'rateLimited', 'seek', 'none'):
            row['correction'] = correction
        else: invalid += 1
        return row, invalid
    names = (
        ('seekRecovery cancelled reason=', 'seek_recovery_cancelled'),
        ('seekRecovery exhausted supported=', 'seek_recovery_exhausted'),
        ('seekRecovery restore failed error=', 'seek_recovery_restore_failed'),
        ('speedCorrection restore failed reason=', 'speed_correction_restore_failed'),
        ('speedCorrection restore reason=', 'speed_correction_restore'),
        ('speedCorrection apply ', 'speed_correction_apply'),
    )
    event = next((name for prefix, name in names if body.startswith(prefix)), None)
    if event is None:
        return None, 0
    row, invalid = {'event': event}, 0
    if event == 'seek_recovery_restore_failed':
        return row, 0  # Error content is deliberately not parsed.
    if event == 'seek_recovery_exhausted':
        value = body[len('seekRecovery exhausted supported='):]
        if value in ('true', 'false'): row['supported'] = value == 'true'
        else: invalid += 1
        return row, invalid
    if event == 'speed_correction_apply':
        match = re.fullmatch(r'speedCorrection apply targetKey=\S+ driftMs=(\S+) baseSpeed=(\S+) syncSpeed=(\S+) (durationMs|remainingMs)=(\S+)', body)
        if not match: return row, 1
        for token, (key, low, high, integer) in zip(match.group(1, 2, 3, 5), (
                ('driftMs', -86400000, 86400000, True), ('baseSpeed', .5, 2, False),
                ('syncSpeed', .5, 2, False), (match.group(4), 0, 5000, True))):
            value = _finite_field(token, low, high, integer=integer)
            if value is not None: row[key] = value
            else: invalid += 1
        return row, invalid
    if event == 'seek_recovery_cancelled':
        reason = body[len('seekRecovery cancelled reason='):]
    elif event == 'speed_correction_restore_failed':
        match = re.match(r'speedCorrection restore failed reason=(\S+) error=', body)
        reason = match.group(1) if match else None
    else:
        match = re.fullmatch(r'speedCorrection restore reason=(\S+) targetKey=\S+ speed=(\S+)', body)
        reason = match.group(1) if match else None
        value = _finite_field(match.group(2), .5, 2) if match else None
        if value is not None: row['rate'] = value
        else: invalid += 1
    row['reason'] = reason if reason in CORRECTION_REASONS else 'unrecognized'
    return row, invalid


class _CorrectionSequence:
    """Small finite reducer. File order is authoritative; wall time is unpaired."""
    def __init__(self):
        self.origin = self.previous = None
        self.value = {'timeBasis': 'first_selected_log_event_wall', 'monotonicClockPaired': False,
            'recoveryWindowStartObserved': False, 'eventCount': 0, 'recordsDropped': 0,
            'recordRetention': 'first64_last64',
            'recordsTruncated': False, 'unknownReasonCount': 0, 'invalidFieldCount': 0,
            'timestampIssueCount': 0, 'wallClockRegressionObserved': False,
            'counts': dict.fromkeys(CORRECTION_EVENTS, 0), 'records': []}

    def observe(self, line, body):
        header = re.match(r'^\[([^\]]+)\] \[(?:DEBUG|INFO|WARNING|ERROR)\] \[([A-Za-z0-9_.]+)\] ', line)
        if not header: return
        row, invalid = _correction_event(body, header.group(2))
        if row is None: return
        value = self.value
        _increment(value, 'eventCount'); _increment(value['counts'], row['event'])
        value['invalidFieldCount'] = min(MAX_COUNT, value['invalidFieldCount'] + invalid)
        if row.get('reason') == 'unrecognized': _increment(value, 'unknownReasonCount')
        row['ordinal'] = value['eventCount']
        row['timeStatus'] = 'unavailable'
        stamp = header.group(1)
        try:
            # Dart DateTime ISO output has three or six fractional digits. Do
            # not infer the timezone of local wall timestamps or pair them
            # with the controller Stopwatch / Python monotonic clock.
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}(?:\d{3})?Z?', stamp) is None:
                raise ValueError('Unsupported timestamp')
            now = datetime.fromisoformat(stamp)
            if value['eventCount'] == 1: self.origin = now
            if self.origin is None or now.tzinfo != self.origin.tzinfo:
                raise ValueError('Unpaired timestamp basis')
            if self.previous is not None and now < self.previous:
                value['wallClockRegressionObserved'] = True
            self.previous = now
            offset = (now - self.origin).total_seconds() * 1000
            if not -600000 <= offset <= 600000: raise ValueError('Timestamp bound')
            row['wallOffsetMs'] = round(offset, 3)
            row['timeStatus'] = 'unpaired_wall'
        except (ValueError, TypeError, OverflowError):
            _increment(value, 'timestampIssueCount')
        if len(value['records']) < CORRECTION_LIMIT:
            value['records'].append(row)
        else:
            value['recordsTruncated'] = True
            _increment(value, 'recordsDropped')
            value['records'].pop(CORRECTION_LIMIT // 2)
            value['records'].append(row)


def _increment(values, key):
    values[key] = min(MAX_COUNT, values.get(key, 0) + 1)


def _number(value, maximum=45000):
    return round(min(maximum, max(0, value)), 3) if type(value) in (int, float) and math.isfinite(value) else None


def _flag(value):
    return value if type(value) is bool else None


def _enum(value, values):
    return value if isinstance(value, str) and value in values else 'not_observed' if value is None else 'unrecognized'


def _parse_log_lines(lines):
    """Return only exact allowlisted values; stack frames are presence facts."""
    result = {'events': dict.fromkeys(EVENTS, 0), 'phases': dict.fromkeys(PHASES, 0),
        'clearReasons': dict.fromkeys(REASONS, 0), 'unknownReasonCount': 0,
        'unknownPhaseCount': 0, 'mirrorCauses': dict.fromkeys(sorted(set(CAUSES.values()) | {'other'}), 0),
        'mirrorStackFrames': dict.fromkeys(sorted(set(FRAMES.values())), 0),
        'syncActions': dict.fromkeys(ACTIONS, 0), 'seekBoundedTimeoutCount': 0,
        'speedRestoreFailedCount': 0, 'stackTruncated': False}
    stack_lines = 0
    in_stack = False
    corrections = _CorrectionSequence()
    for line in lines:
        if len(line) > 8192:
            in_stack = False
            continue
        entry = LOG_ENTRY.fullmatch(line)
        body = entry.group(1) if entry else None
        if body is not None and body.startswith(MARKER + 'local mirror stack:'):
            in_stack, stack_lines = True, 0
            line = body[len(MARKER + 'local mirror stack:'):].strip()
            if not line:
                continue
        if in_stack:
            # Only contiguous Dart frame/asynchronous-suspension lines belong
            # to this block. Never inspect arbitrary later log messages.
            match = re.fullmatch(r'\s*#\d+\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)(?:\.<anonymous closure>)?\s+\([^\n]*\)\s*', line)
            suspension = line.strip() == '<asynchronous suspension>'
            if match or suspension:
                stack_lines += 1
                if stack_lines <= 64 and match and match.group(1) in FRAMES:
                    _increment(result['mirrorStackFrames'], FRAMES[match.group(1)])
                if stack_lines > 64:
                    result['stackTruncated'] = True
                continue
            in_stack = False
        if body is None:
            continue
        corrections.observe(line, body)
        if body.startswith(MARKER):
            body = body[len(MARKER):]
            event = body.split(' ', 1)[0]
            if event in EVENTS:
                _increment(result['events'], event)
                # Only fields before error= are protocol tokens. Error strings
                # must never inject phase/reason or sync-action observations.
                fields = body.split(' error=', 1)[0].split()
                if event == 'recovery_record_persisted':
                    phases = [v[6:] for v in fields if v.startswith('phase=')]
                    if len(phases) == 1 and phases[0] in PHASES:
                        _increment(result['phases'], phases[0])
                    else:
                        result['unknownPhaseCount'] = min(MAX_COUNT, result['unknownPhaseCount'] + 1)
                if event == 'recovery_cleared':
                    reasons = [v[7:] for v in fields if v.startswith('reason=')]
                    if len(reasons) == 1 and reasons[0] in REASONS:
                        _increment(result['clearReasons'], reasons[0])
                    else:
                        result['unknownReasonCount'] = min(MAX_COUNT, result['unknownReasonCount'] + 1)
                if event == 'local_mirror_failure':
                    message = body.split(' error=', 1)[1].strip() if ' error=' in body else ''
                    for prefix in ('Exception: ', 'Bad state: '):
                        if message.startswith(prefix):
                            message = message[len(prefix):]
                            break
                    _increment(result['mirrorCauses'], CAUSES.get(message, 'other'))
            continue
        if body.startswith('[[EMO_FOLLOW_SYNC]] '):
            fields = body[len('[[EMO_FOLLOW_SYNC]] '):].split(' error=', 1)[0].split()
            actions = [v[7:] for v in fields if v.startswith('action=')]
            if len(actions) == 1 and actions[0] in ACTIONS:
                _increment(result['syncActions'], actions[0])
        if body.startswith('[[PLAYER_ACT]] op=seek bounded-timeout '):
            result['seekBoundedTimeoutCount'] = min(MAX_COUNT, result['seekBoundedTimeoutCount'] + 1)
        if body.startswith('[[EMO_FOLLOW_SYNC]] speedCorrection restore failed '):
            result['speedRestoreFailedCount'] = min(MAX_COUNT, result['speedRestoreFailedCount'] + 1)
    result['correctionSequence'] = corrections.value
    return result


def _bounded_lines(stream, limit, stats, *, discard_first=False):
    """Stream at most the pinned file-size delta; never retain an oversized line."""
    remaining = limit
    discard = discard_first
    oversized = False
    stats.update(bytesRead=0, lineTruncated=False, partialFinalLine=False,
                 partialInitialLine=discard_first, invalidEncoding=False)
    while remaining:
        raw = stream.readline(min(MAX_LINE + 1, remaining))
        if not raw:
            stats['partialFinalLine'] = True
            break
        remaining -= len(raw)
        stats['bytesRead'] += len(raw)
        newline = raw.endswith(b'\n')
        if discard or oversized or len(raw) > MAX_LINE:
            stats['lineTruncated'] |= oversized or len(raw) > MAX_LINE
            oversized = not newline
            if newline:
                discard = False
            yield ''  # End any companion stack block at a discarded line.
            continue
        if not newline:
            stats['partialFinalLine'] = True
            yield ''
            continue
        try:
            yield raw[:-1].decode('utf-8').rstrip('\r')
        except UnicodeDecodeError:
            stats['invalidEncoding'] = True
            yield ''
    if discard or oversized:
        stats['partialFinalLine'] = True


def _stream_log(stream, limit, *, discard_first=False):
    stats = {}
    result = _parse_log_lines(_bounded_lines(stream, limit, stats, discard_first=discard_first))
    result.update(stats)
    result['coverage'] = ('partial' if any(stats[k] for k in
        ('lineTruncated', 'partialFinalLine', 'partialInitialLine', 'invalidEncoding')) else 'complete')
    return result


def parse_log_slice(data, *, complete=True):
    """Synthetic-fixture API; runtime streams from the owned file directly."""
    result = _stream_log(io.BytesIO(data), min(MAX_LOG, len(data)))
    if not complete or len(data) > MAX_LOG:
        result['coverage'] = 'truncated'
    return result


class _LogBoundExceeded(ValueError):
    pass


def _owned_log(client, state):
    role, bundle = client.role, client.bundle_id
    if (role != 'follower' or not isinstance(bundle, str)
            or not re.fullmatch(r'com\.example\.emosonic\.nativelab\.r[A-Za-z0-9.-]+\.follower', bundle)
            or state.get('bundleId') != bundle or type(state.get('pid')) is not int
            or state['pid'] != client.process.pid):
        raise ValueError('Refused owned observation')
    root = Path.home() / 'Library/Containers' / bundle / 'Data/Library/Application Support' / bundle / 'native-playback-lab-follower'
    marker = root / '.native-mac-lab.json'
    log = root / 'logs/debug.log'
    if state.get('root') != str(root) or any(p.is_symlink() for p in (marker, log, *marker.parents, *log.parents)):
        raise ValueError('Refused owned observation')
    if not marker.is_file() or marker.stat().st_size > 4096:
        raise ValueError('Refused owned observation')
    metadata = json.loads(marker.read_text())
    if (type(metadata) is not dict or metadata.get('kind') != 'emosonic-native-mac-lab'
            or metadata.get('bundleId') != bundle or metadata.get('instance') != role):
        raise ValueError('Refused owned observation')
    return log


def _open_regular(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Refused log observation')
        if info.st_size > MAX_LOG:
            raise _LogBoundExceeded('Owned log exceeds observation bound')
        return os.fdopen(descriptor, 'rb'), info
    except Exception:
        os.close(descriptor)
        raise


def capture_log_cursor(client, state):
    try:
        path = _owned_log(client, state)
        stream, info = _open_regular(path)
        with stream:
            stream.seek(max(0, info.st_size - 64))
            anchor = stream.read(min(64, info.st_size))
        return {'status': 'captured', 'device': info.st_dev, 'inode': info.st_ino,
                'offset': info.st_size, 'anchor': anchor}
    except _LogBoundExceeded:
        return {'status': 'file_bound_exceeded'}
    except ValueError:
        return {'status': 'ownership_refused'}
    except (OSError, TypeError, AttributeError, json.JSONDecodeError):
        return {'status': 'unavailable'}


def read_log_since(client, state, cursor):
    if cursor.get('status') != 'captured':
        return {'coverage': cursor.get('status') if cursor.get('status') in ('ownership_refused', 'unavailable', 'file_bound_exceeded') else 'unavailable'}
    try:
        path = _owned_log(client, state)
        stream, info = _open_regular(path)
        with stream:
            offset = cursor['offset']
            if (info.st_dev != cursor['device'] or info.st_ino != cursor['inode'] or info.st_size < offset):
                return {'coverage': 'rotated'}
            stream.seek(max(0, offset - 64))
            if stream.read(min(64, offset)) != cursor['anchor']:
                return {'coverage': 'rotated'}
            stream.seek(offset)
            return _stream_log(stream, info.st_size - offset,
                discard_first=bool(cursor['anchor']) and not cursor['anchor'].endswith(b'\n'))
    except _LogBoundExceeded:
        return {'coverage': 'file_bound_exceeded'}
    except ValueError:
        return {'coverage': 'ownership_refused'}
    except (OSError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        return {'coverage': 'unavailable'}


def _identity(state):
    values = tuple(state.get(key) for key in ('pid', 'bundleId', 'root', 'clientId', 'deviceSessionId'))
    if type(values[0]) is not int or values[0] <= 0 or any(not isinstance(v, str) or not v for v in values[1:]):
        return None
    return values


def _task(state):
    queue, index, track = state.get('queue'), state.get('currentIndex'), state.get('trackId')
    if (not isinstance(queue, list) or not queue or any(not isinstance(v, str) or not v for v in queue)
            or type(index) is not int or not 0 <= index < len(queue) or queue[index] != track):
        return None
    return tuple(queue), index, track


def _snapshot(state, original, source, context):
    public = state.get('preflightDiagnostics')
    public = public if isinstance(public, dict) else {}
    native = state.get('nativePlayers')
    item = native[0] if isinstance(native, list) and len(native) == 1 and isinstance(native[0], dict) else {}
    original_task, source_task, current_task = _task(original), _task(source), _task(state)
    rate = item.get('playbackRate')
    rate_valid = type(rate) in (int, float) and math.isfinite(rate)
    native_state = item.get('playbackState')
    return {'runtimeMode': _enum(state.get('runtimeMode'), ('solo', 'follow', 'broadcast')),
        'recoveryPhase': _enum(public.get('recoveryPhase'), PHASES + ('terminalFeedbackPending',)),
        'followSourceMatches': bool(context) and state.get('followSourceContextId') == context,
        'sameFollowerIdentity': _identity(original) is not None and _identity(state) == _identity(original),
        'originalTaskMatches': original_task is not None and current_task == original_task,
        'sourceTaskMatches': source_task is not None and current_task == source_task,
        'followRecoveryGateActive': _flag(public.get('followRecoveryGateActive')),
        'restoreInProgress': _flag(public.get('restoreInProgress')),
        'queueHydrating': _flag(public.get('queueHydrating')),
        'processingState': _enum(state.get('processingState'), ('idle', 'loading', 'buffering', 'ready', 'completed')),
        'seekInProgress': _flag(item.get('seekInProgress')), 'playingIntent': _flag(item.get('playingIntent')),
        'nativePlaying': type(native_state) is int and native_state == 3 and rate_valid and rate > 0,
        'nativePaused': type(native_state) is int and native_state == 4 and rate_valid and rate == 0,
        'requestedRate': _number(item.get('requestedRate'), 10),
        'positionMs': _number(item.get('positionMs'), 86400000)}


class FollowLifecycleObservation:
    def __init__(self, matrix, context, original, ready_predicate):
        self.client = matrix.clients[2]
        self.original = original
        self.source = matrix.last[0]
        self.context = context
        self.ready_predicate = ready_predicate
        self.directory = matrix.fixture_state_directory
        self.started = time.monotonic()
        self.cursor = capture_log_cursor(self.client, original)
        self.expected = {'followerClientId': original.get('clientId'),
            'followerDeviceSessionId': original.get('deviceSessionId'), 'sourceContextId': context,
            'suspendedContextId': original.get('contextId'), 'sourceClientId': self.source.get('clientId'),
            'sourceDeviceSessionId': self.source.get('deviceSessionId'), 'originalTrackId': original.get('trackId'),
            'originalQueue': original.get('queue'), 'originalIndex': original.get('currentIndex')}
        self.value = {'status': 'observing', 'originalPausedTask': _snapshot(original, original, self.source, context),
            'commandReturned': False, 'commandOk': None, 'sampleCount': 0, 'transitionCount': 0,
            'observationErrorCount': 0, 'sampleCountSaturated': False,
            'transitionsTruncated': False, 'seenFollowRuntime': False, 'seenActiveRecovery': False,
            'seenSourceTask': False, 'seenNativeReady': False, 'seenRestoring': False,
            'seenOriginalAfterFollow': False, 'identityChangeObserved': False, 'transitions': [], 'serverFollow': []}
        self.last_signature = None
        self.server_milestones = set()
        self.finished = False

    def _server(self, milestone):
        if milestone in self.server_milestones or len(self.server_milestones) >= 6:
            return
        self.server_milestones.add(milestone)
        try:
            observation = observe_follow_server(self.directory, self.expected)
        except Exception:
            observation = {'status': 'observation_unavailable'}
        self.value['serverFollow'].append({'milestone': milestone, 'observation': observation})

    def _observe(self, state, source, *, phase):
        snap = _snapshot(state, self.original, source, self.context)
        snap['sameAuthorityIdentity'] = _identity(self.source) is not None and _identity(source) == _identity(self.source)
        self.value['identityChangeObserved'] |= not snap['sameFollowerIdentity'] or not snap['sameAuthorityIdentity']
        self.value['seenFollowRuntime'] |= snap['runtimeMode'] == 'follow' and snap['followSourceMatches']
        self.value['seenActiveRecovery'] |= snap['followRecoveryGateActive'] is True and snap['recoveryPhase'] == 'active'
        self.value['seenSourceTask'] |= snap['sourceTaskMatches']
        self.value['seenRestoring'] |= snap['restoreInProgress'] is True or snap['recoveryPhase'] == 'restoring'
        self.value['seenOriginalAfterFollow'] |= ((self.value['seenFollowRuntime'] or self.value['seenActiveRecovery'])
            and snap['runtimeMode'] != 'follow' and snap['originalTaskMatches'] and snap['followRecoveryGateActive'] is False)
        try:
            ready = self.ready_predicate(source, state, self.context) is True
        except Exception:
            ready = False  # Original predicate still runs and preserves failure.
        self.value['seenNativeReady'] |= ready
        signature = tuple(snap.get(k) for k in ('runtimeMode', 'recoveryPhase', 'followSourceMatches',
            'originalTaskMatches', 'sourceTaskMatches', 'followRecoveryGateActive', 'restoreInProgress',
            'processingState', 'seekInProgress', 'playingIntent', 'nativePlaying', 'nativePaused'))
        if signature != self.last_signature:
            self.last_signature = signature
            self.value['transitionCount'] = min(MAX_COUNT, self.value['transitionCount'] + 1)
            if len(self.value['transitions']) < 12:
                self.value['transitions'].append({'phase': phase, 'elapsedMs': _number((time.monotonic() - self.started) * 1000, 90000), **snap})
            else:
                self.value['transitionsTruncated'] = True
        if phase != 'command_return':
            for milestone, reached in (('active_recovery', snap['recoveryPhase'] == 'active'),
                    ('restoring', snap['recoveryPhase'] == 'restoring' or snap['restoreInProgress'] is True),
                    ('original_after_follow', self.value['seenOriginalAfterFollow']), ('native_ready', ready)):
                if reached:
                    self._server(milestone)
        return snap

    def command_returned(self, reply):
        self.value['commandReturned'] = True
        self.value['commandDurationMs'] = _number((time.monotonic() - self.started) * 1000)
        self.value['commandOk'] = _flag(reply.get('ok')) if isinstance(reply, dict) else None
        state = reply.get('state') if isinstance(reply, dict) else None
        if isinstance(state, dict):
            self.value['commandState'] = self._observe(state, self.source, phase='command_return')
        self._server('command_return')

    def sample(self, states):
        self.value['sampleCountSaturated'] |= self.value['sampleCount'] >= 1000
        self.value['sampleCount'] = min(1000, self.value['sampleCount'] + 1)
        if isinstance(states, list) and len(states) >= 3:
            self._observe(states[2], states[0], phase='wait')

    def finish(self):
        if not self.finished:
            self.finished = True
            self._server('failure')
            self.value['ownedLog'] = read_log_since(self.client, self.original, self.cursor)
            self.value['status'] = 'observed'
        return self.value


def begin_follow_lifecycle(matrix, context, original, ready_predicate):
    try:
        matrix.follow_lifecycle_observation = FollowLifecycleObservation(matrix, context, original, ready_predicate)
    except Exception:
        matrix.follow_lifecycle_observation = None


def observe_follow_command(matrix, reply):
    try:
        observer = getattr(matrix, 'follow_lifecycle_observation', None)
        if observer is not None:
            observer.command_returned(reply)
            print(json.dumps({'stage': 'native-follow-command-observation',
                'status': 'not-verified', 'followLifecycle': observer.value}, allow_nan=False), flush=True)
    except Exception:
        if observer is not None:
            _increment(observer.value, 'observationErrorCount')


def observe_follow_wait(matrix, stage, states):
    if stage != 'native-follow-start':
        return
    try:
        observer = getattr(matrix, 'follow_lifecycle_observation', None)
        if observer is not None:
            observer.sample(states)
    except Exception:
        if observer is not None:
            _increment(observer.value, 'observationErrorCount')


def finish_follow_lifecycle(matrix):
    try:
        observer = getattr(matrix, 'follow_lifecycle_observation', None)
        result = dict(observer.finish()) if observer is not None else {'status': 'not_observed'}
    except Exception:
        result = {'status': 'observation_unavailable'}
    # Reuse the exact final samples already held by Matrix. No state request,
    # new native read, control, or inference about the last recovery decision.
    try:
        result['endpointTiming'] = _endpoint_timing(getattr(matrix, 'last', None))
    except Exception:
        result['endpointTiming'] = {'status': 'unavailable'}
    return result


RECOVERY_CHECK_REASONS = ('recovery_started', 'receipt_accepted', 'wake_deferred', 'wake_queued_ignored', 'wake_busy', 'wake_dispatch', 'check_enter', 'inactive_or_cancelled', 'owner_or_service_changed', 'source_owner_changed', 'deadline_reached', 'exhausted_or_ticking', 'source_not_current', 'seek_pending', 'missing_nominal_ack', 'anchor_snapshot', 'baseline_stale', 'baseline_adopted', 'missing_or_nonprogressing_anchor', 'anchor_age_rejected', 'nominal_floor_rejected', 'nominal_progress_rejected', 'effective_anchor_too_early', 'nonfinite_drift', 'eligible_progress', 'before_rate_write', 'check_finally', 'seek_future_finally', 'truncated')
RECOVERY_CHECK_FLAGS = ('seekPending', 'ticking', 'supported', 'ownedRatePresent', 'receiptPending', 'receiptScheduled', 'cancelled', 'exhausted')
RECOVERY_CHECK_SEQUENCES = ('cachedSequence', 'baselineSequence', 'lastObservedSequence', 'nominalSequenceFloor')
RECOVERY_CHECK_FIELDS = frozenset(('v', 'eventOrdinal', 'recoveryOrdinal', 'reason', 'cachedSequence', 'baselineSequence', 'lastObservedSequence', 'nominalSequenceFloor', 'seekPending', 'ticking', 'supported', 'ownedRatePresent', 'receiptPending', 'receiptScheduled', 'cancelled', 'exhausted', 'ageMs', 'floorPositionMs'))


def _recovery_check_record(value):
    """Validate the frozen uniform record before omitting unavailable nulls."""
    if type(value) is not dict or set(value) != RECOVERY_CHECK_FIELDS:
        raise ValueError('Checkpoint fields changed')
    if type(value['v']) is not int or value['v'] != 1:
        raise ValueError('Checkpoint version changed')
    if type(value['eventOrdinal']) is not int or not 1 <= value['eventOrdinal'] <= 129:
        raise ValueError('Checkpoint ordinal changed')
    if type(value['reason']) is not str or value['reason'] not in RECOVERY_CHECK_REASONS:
        raise ValueError('Checkpoint reason changed')
    if (value['eventOrdinal'] == 129) != (value['reason'] == 'truncated'):
        raise ValueError('Checkpoint truncation changed')
    for key in RECOVERY_CHECK_FLAGS:
        if type(value[key]) is not bool: raise ValueError('Checkpoint flag changed')
    bounds = {'recoveryOrdinal': (0, 129), 'floorPositionMs': (-86400000, 86400000),
              **{key: (-9007199254740991, 9007199254740991) for key in RECOVERY_CHECK_SEQUENCES}}
    for key, (low, high) in bounds.items():
        item = value[key]
        if item is not None and (type(item) is not int or not low <= item <= high):
            raise ValueError('Checkpoint integer changed')
    age = value['ageMs']
    if age is not None and (type(age) not in (int, float) or not math.isfinite(age) or not -86400000 <= age <= 86400000):
        raise ValueError('Checkpoint age changed')
    return {key: item for key, item in value.items() if item is not None}


def _recovery_check_snapshot(value):
    """Project a retained endpoint field without reading a client or clock.

    Complete coverage means all observer attempts through this snapshot, not a
    completed recovery episode or a successful playback outcome.
    """
    if value is None: return {'status': 'unavailable'}
    try:
        keys = {'schemaVersion', 'status', 'recordLimit', 'truncationRecordLimit',
            'attemptCount', 'droppedCount', 'droppedCountSaturated', 'records'}
        if type(value) is not dict or set(value) != keys:
            raise ValueError('Snapshot fields changed')
        for key, expected in (('schemaVersion', 1), ('recordLimit', 128), ('truncationRecordLimit', 1)):
            if type(value[key]) is not int or value[key] != expected:
                raise ValueError('Snapshot version or bound changed')
        for key, maximum in (('attemptCount', 129), ('droppedCount', 1000000)):
            if type(value[key]) is not int or not 0 <= value[key] <= maximum:
                raise ValueError('Snapshot counter changed')
        if type(value['droppedCountSaturated']) is not bool or value['status'] not in ('recording', 'truncated'):
            raise ValueError('Snapshot status changed')
        if (value['attemptCount'] == 129) != (value['status'] == 'truncated'):
            raise ValueError('Snapshot truncation status changed')
        if value['droppedCountSaturated'] and value['droppedCount'] != 1000000:
            raise ValueError('Snapshot saturation changed')
        if type(value['records']) is not list or len(value['records']) > 129:
            raise ValueError('Snapshot record bound changed')
        records = [_recovery_check_record(row) for row in value['records']]
        ordinals = [row['eventOrdinal'] for row in records]
        if ordinals != sorted(set(ordinals)) or any(n > value['attemptCount'] for n in ordinals):
            raise ValueError('Snapshot ordinal order changed')
        complete = (value['status'] == 'recording' and value['droppedCount'] == 0
            and value['droppedCountSaturated'] is False and value['attemptCount'] <= 128
            and ordinals == list(range(1, value['attemptCount'] + 1)))
        return {'status': 'observed', 'coverage': 'complete' if complete else 'incomplete',
            'snapshotBasis': 'existing_state_endpoint_not_alignment_sample',
            'sequenceBasis': 'vendor_position_receipt_not_native_observer_ordinal',
            'timeBasis': 'existing_control_flow_values_no_new_clock',
            'nullFields': 'omitted_unavailable', 'producerStatus': value['status'],
            **{key: value[key] for key in ('schemaVersion', 'recordLimit', 'truncationRecordLimit',
                'attemptCount', 'droppedCount', 'droppedCountSaturated')}, 'records': records}
    except (ValueError, TypeError, OverflowError, RecursionError):
        return {'status': 'invalid'}



PLAY_POLICY_PHASES = ('policy_begin', 'policy_end', 'policy_threw',
    'post_policy_owner_rejected', 'post_policy_owner_accepted', 'play_submitted',
    'native_baseline', 'native_progress', 'superseded_trigger', 'superseded_seek',
    'disposed', 'player_recreated', 'closed', 'truncated')
PLAY_POLICY_FLAGS = ('currentTrigger', 'serviceOwnerMatches', 'sampleAfterPlayRequest', 'receiptProgress')
PLAY_POLICY_FIELDS = frozenset(('eventOrdinal', 'triggerOrdinal', 'phase', 'elapsedUs',
    'policyOutcome', 'currentTrigger', 'cacheKind', 'vendorSequence',
    'serviceOwnerMatches', 'sampleAfterPlayRequest', 'receiptProgress', 'nativeLoadAttribution'))


def _play_policy_record(value):
    """Validate the complete private schema, then omit only unavailable nulls."""
    if type(value) is not dict or set(value) != PLAY_POLICY_FIELDS:
        raise ValueError('Policy observation fields changed')
    ordinal, phase = value['eventOrdinal'], value['phase']
    if type(ordinal) is not int or not 1 <= ordinal <= 33 or type(phase) is not str or phase not in PLAY_POLICY_PHASES:
        raise ValueError('Policy observation ordinal or phase changed')
    if (ordinal == 33) != (phase == 'truncated'):
        raise ValueError('Policy observation truncation changed')
    if phase == 'truncated':
        if any(value[key] is not None for key in PLAY_POLICY_FIELDS - {'eventOrdinal', 'phase'}):
            raise ValueError('Policy observation marker changed')
    else:
        if type(value['triggerOrdinal']) is not int or not 1 <= value['triggerOrdinal'] <= 32:
            raise ValueError('Policy observation trigger changed')
        if type(value['nativeLoadAttribution']) is not str or value['nativeLoadAttribution'] != 'unverified':
            raise ValueError('Policy observation attribution changed')
    for key in ('elapsedUs', 'vendorSequence'):
        if value[key] is not None and (type(value[key]) is not int or not 0 <= value[key] <= 9007199254740991):
            raise ValueError('Policy observation integer changed')
    for key in PLAY_POLICY_FLAGS:
        if value[key] is not None and type(value[key]) is not bool:
            raise ValueError('Policy observation flag changed')
    for key, allowed in (('policyOutcome', ('local', 'remote', 'denied', 'unknown')),
                         ('cacheKind', ('cached', 'network', 'unknown'))):
        if value[key] is not None and (type(value[key]) is not str or value[key] not in allowed):
            raise ValueError('Policy observation enum changed')
    return {key: item for key, item in value.items() if item is not None}


def _play_policy_snapshot(value):
    """Reuse a state endpoint, without I/O or a clock read.

    Complete covers attempts through this snapshot, not an entire playback
    episode. Stopwatch offsets describe in-process observations, not native
    start latency. Vendor receipt sequences are not native observer ordinals;
    neither the native load nor a cross-clock origin is attributed here.
    """
    if value is None: return {'status': 'unavailable'}
    try:
        keys = {'schemaVersion', 'status', 'recordLimit', 'truncationRecordLimit',
            'attemptCount', 'droppedCount', 'droppedCountSaturated', 'records', 'pendingTriggerOrdinal'}
        if type(value) is not dict or set(value) != keys:
            raise ValueError('Policy snapshot fields changed')
        for key, expected in (('schemaVersion', 1), ('recordLimit', 32), ('truncationRecordLimit', 1)):
            if type(value[key]) is not int or value[key] != expected:
                raise ValueError('Policy snapshot version or bound changed')
        for key, maximum in (('attemptCount', 33), ('droppedCount', 1000000)):
            if type(value[key]) is not int or not 0 <= value[key] <= maximum:
                raise ValueError('Policy snapshot count changed')
        pending = value['pendingTriggerOrdinal']
        if pending is not None and (type(pending) is not int or not 1 <= pending <= 32):
            raise ValueError('Policy snapshot pending trigger changed')
        if type(value['status']) is not str or value['status'] not in ('recording', 'truncated') or type(value['droppedCountSaturated']) is not bool:
            raise ValueError('Policy snapshot status changed')
        if (value['attemptCount'] == 33) != (value['status'] == 'truncated'):
            raise ValueError('Policy snapshot truncation changed')
        if value['droppedCountSaturated'] and value['droppedCount'] != 1000000:
            raise ValueError('Policy snapshot saturation changed')
        if type(value['records']) is not list or len(value['records']) > 33:
            raise ValueError('Policy snapshot record bound changed')
        records = [_play_policy_record(row) for row in value['records']]
        ordinals = [row['eventOrdinal'] for row in records]
        if ordinals != sorted(set(ordinals)) or any(n > value['attemptCount'] for n in ordinals):
            raise ValueError('Policy snapshot ordinal order changed')
        complete = (value['status'] == 'recording' and value['droppedCount'] == 0
            and value['droppedCountSaturated'] is False
            and ordinals == list(range(1, value['attemptCount'] + 1)))
        result = {'status': 'observed', 'coverage': 'complete' if complete else 'incomplete',
            'snapshotBasis': 'existing_state_endpoint_not_alignment_sample',
            'timeBasis': 'process_local_stopwatch_not_native_clock',
            'receiptBasis': 'accepted_service_receipt_not_native_observer_ordinal',
            'measurementMeaning': 'in_process_observation_not_native_start_latency',
            'nativeLoadAttribution': 'unverified', 'nullFields': 'omitted_unavailable',
            'producerStatus': value['status'], **{key: value[key] for key in (
                'schemaVersion', 'recordLimit', 'truncationRecordLimit', 'attemptCount',
                'droppedCount', 'droppedCountSaturated')}, 'records': records}
        if pending is not None: result['pendingTriggerOrdinal'] = pending
        return result
    except (ValueError, TypeError, OverflowError, RecursionError):
        return {'status': 'invalid'}


BOOTSTRAP_STAGES = ('client_id', 'device_session_id', 'device_alias',
    'playback_context_outbox', 'follow_recovery', 'broadcast_recovery')
BOOTSTRAP_STATUSES = ('started', 'completed', 'timed_out', 'failed')
_BOOTSTRAP_ENTRY = re.compile(r'^\[\d{4}-\d{2}-\d{2}T[\d:.+Z-]+\] \[(?:DEBUG|INFO|WARNING|ERROR)\] \[(Main|EmoRealtimeClient)\] (.*)$')


def add_bootstrap_observation(result, lines, offset, size, data):
    """Reuse the existing owned 256 KiB tail, never perform another read.

    Whole-current-file coverage is not lifetime coverage: prior rotation or
    debug suppression is unknown, so zero counts never prove no startup.
    Arbitrary scope, identity, error type, error and stack suffixes stay private.
    """
    try:
        if (type(result) is not dict or type(lines) is not list or type(data) is not bytes
                or type(offset) is not int or type(size) is not int
                or not 0 <= offset <= size <= MAX_LOG or len(data) > 256 * 1024):
            raise ValueError('Bootstrap observation bounds changed')
        issues = 0
        try:
            data.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            issues += 1
        partial = bool(data) and not data.endswith(b'\n')
        issues += int(partial or offset + len(data) != size)
        value = {'byteCoverage': 'tail_only' if offset else 'whole_current_file',
            'launchCoverage': 'unknown', 'lineIssues': 0, 'countsSaturated': False,
            'startup': dict.fromkeys(('connect', 'requested', 'failed'), 0),
            'other': dict.fromkeys(('joined', 'stale', 'aborted', 'unknown'), 0),
            'stages': {stage: dict.fromkeys(BOOTSTRAP_STATUSES, 0) for stage in BOOTSTRAP_STAGES}}
        def count(group, key):
            if group[key] >= MAX_COUNT:
                value['countsSaturated'] = True
            group[key] = min(MAX_COUNT, group[key] + 1)
        for index, line in enumerate(lines):
            if type(line) is not str or len(line) > MAX_LINE or '\ufffd' in line:
                issues += 1
                continue
            if partial and index == len(lines)-1:
                continue
            entry = _BOOTSTRAP_ENTRY.fullmatch(line)
            if entry is None:
                continue
            logger, body = entry.groups()
            if logger == 'Main' and body.startswith('[[EMO_STARTUP]] '):
                suffix = body[len('[[EMO_STARTUP]] '):]
                if suffix.startswith('connect scope='):
                    count(value['startup'], 'connect')
                elif suffix == 'connect requested':
                    count(value['startup'], 'requested')
                elif suffix.startswith('connect failed type='):
                    count(value['startup'], 'failed')
                else:
                    count(value['other'], 'unknown')
            elif logger == 'EmoRealtimeClient' and body.startswith('[[EMO_CONNECT_BOOTSTRAP]] '):
                suffix = body[len('[[EMO_CONNECT_BOOTSTRAP]] '):]
                if suffix == 'join active request':
                    count(value['other'], 'joined')
                elif suffix.startswith('ignore failure reason=stale_attempt error='):
                    count(value['other'], 'stale')
                elif suffix.startswith('connection aborted error='):
                    count(value['other'], 'aborted')
                elif suffix.startswith('connection abort stack='):
                    continue  # Never parse stack content, even embedded markers.
                else:
                    match = re.fullmatch(r'stage=(\w+) status=(\w+)(.*)', suffix)
                    if match is None:
                        count(value['other'], 'unknown'); continue
                    stage, status, tail = match.groups()
                    valid_tail = (status == 'completed' and tail == ''
                        or status in ('started', 'timed_out') and re.fullmatch(r' timeoutMs=\d{1,9}', tail) is not None
                        or status == 'failed' and tail.startswith(' error='))
                    if stage not in BOOTSTRAP_STAGES or status not in BOOTSTRAP_STATUSES or not valid_tail:
                        count(value['other'], 'unknown'); continue
                    count(value['stages'][stage], status)
        value['lineIssues'] = min(MAX_COUNT, issues)
        if issues:
            value['byteCoverage'] = 'partial'
        result['bootstrap'] = value
    except Exception:
        result['bootstrap'] = {'byteCoverage': 'unavailable', 'launchCoverage': 'unknown'}


ADMISSION_REASONS = ('payload_not_playing', 'existing_attempt_owner',
    'rate_or_not_playing', 'prepared_not_allowed_or_unsupported',
    'prepared_owner_missing', 'prepared_owner_threw', 'cache_not_ready_or_stale', 'admitted')
ADMISSION_PATHS = ('unknown', 'cache', 'prepared')
ADMISSION_PREPARED_REASONS = ('unsupported_or_unhydrated_or_not_ready',
    'native_anchor_missing', 'native_anchor_not_ready_or_stale', 'owner_rejected', 'owner_accepted')


def _admission_snapshot(value):
    """Validate a retained endpoint without reads or acceptance side effects.

    Ordinals identify begin-attempt invocations, not recovery/native owners or
    callers. Complete covers summaries of attempts through this snapshot only;
    routes that bypass begin are outside its scope. Admission is not proof of a
    seek's execution, completion, or settled playback. No timing is inferred.
    """
    if value is None: return {'status': 'unavailable'}
    try:
        keys = {'schemaVersion', 'attemptCount', 'overflow', 'droppedCount',
            'droppedCountSaturated', 'summaries'}
        if type(value) is not dict or set(value) != keys:
            raise ValueError('Admission snapshot fields changed')
        if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
            raise ValueError('Admission schema changed')
        for key, maximum in (('attemptCount', 5), ('droppedCount', MAX_COUNT)):
            if type(value[key]) is not int or not 0 <= value[key] <= maximum:
                raise ValueError('Admission counter changed')
        if type(value['overflow']) is not bool or type(value['droppedCountSaturated']) is not bool:
            raise ValueError('Admission flag changed')
        if value['overflow'] != (value['attemptCount'] == 5):
            raise ValueError('Admission overflow changed')
        if value['droppedCountSaturated'] and value['droppedCount'] != MAX_COUNT:
            raise ValueError('Admission saturation changed')
        if type(value['summaries']) is not list or len(value['summaries']) > 4:
            raise ValueError('Admission summary bound changed')
        summaries, ordinals = [], []
        for row in value['summaries']:
            if type(row) is not dict or set(row) != {'invocationOrdinal', 'reason', 'path', 'preparedReason'}:
                raise ValueError('Admission summary fields changed')
            ordinal = row['invocationOrdinal']
            if type(ordinal) is not int or not 1 <= ordinal <= min(4, value['attemptCount']):
                raise ValueError('Admission invocation changed')
            for key, allowed in (('reason', ADMISSION_REASONS), ('path', ADMISSION_PATHS)):
                if type(row[key]) is not str or row[key] not in allowed:
                    raise ValueError('Admission enum changed')
            prepared = row['preparedReason']
            if prepared is not None and (type(prepared) is not str or prepared not in ADMISSION_PREPARED_REASONS):
                raise ValueError('Admission prepared reason changed')
            summaries.append({key: item for key, item in row.items() if item is not None})
            ordinals.append(ordinal)
        if ordinals != sorted(set(ordinals)):
            raise ValueError('Admission invocation ordering changed')
        complete = (not value['overflow'] and value['droppedCount'] == 0
            and not value['droppedCountSaturated']
            and ordinals == list(range(1, value['attemptCount'] + 1)))
        return {'status': 'observed', 'coverage': 'complete' if complete else 'incomplete',
            'snapshotBasis': 'existing_state_endpoint_not_alignment_sample',
            'ordinalBasis': 'begin_invocation_not_recovery_or_native_owner',
            'scope': 'begin_attempts_not_all_policy_routes', 'callerAttribution': 'unverified',
            'measurementMeaning': 'admission_not_seek_completion_or_readiness',
            'nullFields': 'omitted_unavailable',
            **{key: value[key] for key in ('schemaVersion', 'attemptCount', 'overflow',
                'droppedCount', 'droppedCountSaturated')}, 'summaries': summaries}
    except (ValueError, TypeError, OverflowError, RecursionError):
        return {'status': 'invalid'}


def _endpoint_timing(states):
    if type(states) is not list or not 1 <= len(states) <= 3:
        return {'status': 'unavailable'}
    output = {'status': 'observed', 'meaning': 'latest_stored_fact_not_controller_decision', 'clients': []}
    fields = (
        ('runtimeAdaptiveDelayMs', 0, 60000), ('configuredMinDelayMs', 0, 60000),
        ('configuredMaxDelayMs', 0, 60000), ('lastObservedControllerDriftMs', -86400000, 86400000),
        ('observedSourceSampleAgeMs', -60000, 600000), ('observedSourceReceiveAgeMs', -60000, 600000),
        ('observedSourceAppliedControlVersion', 0, 1e12), ('observedProjectionDelayMs', 0, 60000),
        ('observedProjectedTargetMs', 0, 86400000))
    def number(value, low, high):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    for ordinal, state in enumerate(states):
        if type(state) is not dict: continue
        row = {'clientOrdinal': ordinal}
        if 'followRecoveryCheckDiagnostics' in state:
            row['recoveryChecks'] = _recovery_check_snapshot(state['followRecoveryCheckDiagnostics'])
        if 'playPolicyDiagnostics' in state:
            row['playPolicy'] = _play_policy_snapshot(state['playPolicyDiagnostics'])
        if 'recoveryAdmissionDiagnostics' in state:
            row['recoveryAdmission'] = _admission_snapshot(state['recoveryAdmissionDiagnostics'])
        raw = state.get('followTimingDiagnostics')
        if type(raw) is dict:
            for name, low, high in fields:
                if number(raw.get(name), low, high): row[name] = raw[name]
            for name in ('observedSourceFactPresent', 'observedSourceFactMatchesCurrent', 'observedSourceTimingValid'):
                if type(raw.get(name)) is bool: row[name] = raw[name]
            if raw.get('observedProjectionBasis') in ('strict_sampled_at', 'unavailable'):
                row['observedProjectionBasis'] = raw['observedProjectionBasis']
        if number(state.get('serverClockOffsetMs'), -600000, 600000):
            row['serverClockOffsetMs'] = state['serverClockOffsetMs']
        if type(state.get('latencySampleCount')) is int and 0 <= state['latencySampleCount'] <= MAX_COUNT:
            row['latencySampleCount'] = state['latencySampleCount']
        if number(state.get('dartPositionMs'), 0, 86400000): row['dartPositionMs'] = state['dartPositionMs']
        if number(state.get('dartPositionSampleUncertaintyMs'), 0, 1000):
            row['dartSampleUncertaintyMs'] = state['dartPositionSampleUncertaintyMs']
        native = state.get('nativePlayers')
        if type(native) is list and len(native) == 1 and type(native[0]) is dict:
            item = native[0]
            for old, new, low, high in (
                    ('positionMs', 'nativePositionMs', 0, 86400000),
                    ('playbackRate', 'nativeRate', 0, 2), ('requestedRate', 'requestedRate', .5, 2),
                    ('sampleUncertaintyMs', 'nativeSampleUncertaintyMs', 0, 1000)):
                if number(item.get(old), low, high): row[new] = item[old]
            dart_at, native_at = state.get('dartPositionSampledAtMs'), item.get('sampledAtMs')
            if number(dart_at, 0, 1e15) and number(native_at, 0, 1e15):
                skew = dart_at - native_at
                if number(skew, -1000, 1000):
                    row['dartReadSkewMs'] = skew
                    if (type(item.get('playbackState')) is int and item['playbackState'] == 3
                            and 'nativePositionMs' in row and 'nativeRate' in row
                            and row['nativeRate'] > 0 and item.get('seekInProgress') is False
                            and item.get('playingIntent') is True
                            and type(item.get('avTimeControlStatus')) is int and item['avTimeControlStatus'] == 2
                            and row.get('observedProjectionBasis') == 'strict_sampled_at'
                            and 'observedProjectedTargetMs' in row):
                        residual = row['nativePositionMs'] + skew * row['nativeRate'] - row['observedProjectedTargetMs']
                        if number(residual, -86400000, 86400000):
                            row['nativeMinusObservedTargetAtDartReadMs'] = round(residual, 3)
        output['clients'].append(row)
    return output
