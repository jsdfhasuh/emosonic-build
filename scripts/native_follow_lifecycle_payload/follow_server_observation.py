"""Read-only finite Follow evidence for the owned source019/server5adc fixture.

Schema pinned to server 5adc23da173c5f20188d79aafe8fcc1e656eb38a:
supysonic/db_layer/emo.py EmoFollowSafetyLease, EmoPlaybackContext,
EmoDevicePlaybackState; follow_store.py source-fact checks and durable start ACK.
Rate diagnostics retain the legacy default 1.0 for either absent rate field.
Their equality is descriptive only, not the fixed server recovery predicate.
Never returns private identifiers, fingerprints, nonces, raw ACK or timestamps.
"""
import json
import math
from pathlib import Path
import sqlite3
import time

SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
STATES = frozenset({'idle', 'playing', 'paused', 'stopped', 'buffering', 'loading'})
PHASES = frozenset({'active', 'reconnectGrace', 'cleanupRequired'})
REQUIRED = ('followerClientId', 'followerDeviceSessionId', 'sourceContextId',
            'suspendedContextId', 'sourceClientId', 'sourceDeviceSessionId')
MAX_NUMBER = 1_000_000_000_000


def _number(value, low=0, high=MAX_NUMBER):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Invalid numeric observation')
    return value


def _integer(value):
    if type(value) is not int:
        raise ValueError('Invalid integer observation')
    return _number(value)


def _object(value):
    if value is None or value == '':
        return {}
    if not isinstance(value, str) or len(value) > 131072:
        raise ValueError('Invalid stored observation')
    result = json.loads(value)
    if not isinstance(result, dict):
        raise ValueError('Invalid stored observation')
    return result


def _queue(value):
    if not isinstance(value, str) or len(value) > 131072:
        raise ValueError('Invalid queue observation')
    result = json.loads(value)
    if not isinstance(result, list) or len(result) > 10000 or any(not isinstance(v, str) for v in result):
        raise ValueError('Invalid queue observation')
    return result


def _enum(value, allowed):
    if value not in allowed:
        raise ValueError('Unknown stored observation enum')
    return value


def _remaining(value, now):
    if type(value) is not int or not 0 <= value <= 10**15:
        raise ValueError('Invalid deadline observation')
    return max(-60000, min(60000, value - now))


def _context(connection, context_id):
    return connection.execute('''SELECT lifecycle, state, track_id, queue_json,
        current_index, epoch, version, control_version, queue_revision,
        authority_client_id, authority_device_session_id, playback_json
        FROM emo_playback_context WHERE playback_context_id=?''', (context_id,)).fetchone()


def _summarize(connection, expected, now):
    rows = connection.execute('''SELECT phase, source_playback_context_id,
        source_authority_client_id, source_authority_device_session_id,
        source_connection_nonce, suspended_playback_context_id,
        suspended_authority_client_id, suspended_authority_device_session_id,
        suspended_epoch, suspended_version, suspended_queue_revision,
        suspended_control_version, suspended_applied_control_version,
        follow_reconnect_grace_expires_at_ms, source_recovery_deadline_at_ms,
        start_ack_json FROM emo_follow_safety_lease
        WHERE follower_client_id=? AND follower_device_session_id=? LIMIT 2''',
        (expected['followerClientId'], expected['followerDeviceSessionId'])).fetchall()
    if len(rows) > 1:
        raise ValueError('Ambiguous fixture lease')
    lease = rows[0] if rows else None
    result = {'status': 'read_only_snapshot', 'leasePresent': lease is not None,
              'admissionObserved': 'unknown'}
    if lease is not None:
        ack = _object(lease['start_ack_json'])
        result.update({
            'phase': _enum(lease['phase'], PHASES),
            'sourceContextMatches': lease['source_playback_context_id'] == expected['sourceContextId'],
            'suspendedContextMatches': lease['suspended_playback_context_id'] == expected['suspendedContextId'],
            'sourceAuthorityMatches': lease['source_authority_client_id'] == expected['sourceClientId'] and lease['source_authority_device_session_id'] == expected['sourceDeviceSessionId'],
            'suspendedAuthorityMatchesFollower': lease['suspended_authority_client_id'] == expected['followerClientId'] and lease['suspended_authority_device_session_id'] == expected['followerDeviceSessionId'],
            'startAckPresent': bool(ack),
        })
        if ack:
            if ack.get('action') != 'follow.start' or ack.get('status') != 'active':
                raise ValueError('Invalid durable start observation')
            result['admissionObserved'] = 'accepted'
            result['startAckSourceMatches'] = ack.get('sourcePlaybackContextId') == expected['sourceContextId']
            result['startAckSuspendedMatches'] = ack.get('suspendedPlaybackContextId') == expected['suspendedContextId']
        for field, key in [('suspended_epoch', 'suspendedEpoch'), ('suspended_version', 'suspendedVersion'), ('suspended_queue_revision', 'suspendedQueueRevision'), ('suspended_control_version', 'suspendedControlVersion'), ('suspended_applied_control_version', 'suspendedAppliedControlVersion')]:
            result[key] = _integer(lease[field])
            if ack:
                result[key + 'AckMatches'] = _integer(ack.get(key)) == result[key]
        for field, prefix in [('follow_reconnect_grace_expires_at_ms', 'reconnectGrace'), ('source_recovery_deadline_at_ms', 'sourceRecovery')]:
            value = lease[field]
            result[prefix + 'DeadlinePresent'] = value is not None
            if value is not None:
                remaining = _remaining(value, now)
                result[prefix + 'RemainingMs'] = remaining
                result[prefix + 'Expired'] = remaining <= 0
    source = _context(connection, expected['sourceContextId'])
    result['sourceContextPresent'] = source is not None
    if source is not None:
        queue = _queue(source['queue_json'])
        index = source['current_index']
        playback = _object(source['playback_json'])
        state = _enum(source['state'], STATES)
        result.update({'sourceLifecycleActive': source['lifecycle'] == 'active',
            'sourceState': state,
            'sourceAuthorityMatchesExpected': source['authority_client_id'] == expected['sourceClientId'] and source['authority_device_session_id'] == expected['sourceDeviceSessionId'],
            'sourceQueueLength': len(queue),
            'sourceQueueIndexValid': type(index) is int and 0 <= index < len(queue),
            'sourceEpoch': _integer(source['epoch']),
            'sourceControlVersion': _integer(source['control_version'])})
        result['sourceQueueTrackConsistent'] = result['sourceQueueIndexValid'] and queue[index] == source['track_id']
        device = connection.execute('''SELECT device_session_id, context_epoch,
            applied_control_version, is_authority, state, track_id, position_ms,
            playback_json FROM emo_device_playback_state
            WHERE playback_context_id=? AND owner_client_id=?''',
            (expected['sourceContextId'], expected['sourceClientId'])).fetchone()
        result['sourceDevicePresent'] = device is not None
        if device is not None:
            fact = _object(device['playback_json'])
            result.update({'sourceDeviceGenerationMatches': device['device_session_id'] == expected['sourceDeviceSessionId'],
                'sourceDeviceEpochMatches': _integer(device['context_epoch']) == source['epoch'],
                'sourceDeviceControlMatches': _integer(device['applied_control_version']) == source['control_version'],
                'sourceDeviceIsAuthority': device['is_authority'] == 1,
                'sourceDeviceState': _enum(device['state'], STATES),
                'sourceDeviceStateMatches': device['state'] == state,
                'sourceDeviceTrackMatches': device['track_id'] == source['track_id'],
                'sourceDevicePositionValid': type(device['position_ms']) is int and device['position_ms'] >= 0})
            if lease is not None:
                result['sourceDeviceNonceMatchesLease'] = isinstance(fact.get('_connectionNonce'), str) and fact['_connectionNonce'] == lease['source_connection_nonce']
            rates = (playback.get('playbackRate', 1.0), fact.get('playbackRate', 1.0))
            valid = all(type(r) in (int, float) and math.isfinite(r) and 0.5 <= r <= 2.0 for r in rates)
            result['sourceRatesValid'] = valid
            result['sourceRatesMatch'] = valid and rates[0] == rates[1]
            for field, prefix in [('serverUpdatedAtMs', 'sourceUpdated'), ('positionSampledAtServerMs', 'sourceSample')]:
                stamp = fact.get(field)
                valid = type(stamp) is int and 0 <= stamp <= now
                result[prefix + 'TimeValid'] = valid
                result[prefix + 'FreshWithin2s'] = valid and now - stamp <= 2000
                if valid:
                    result[prefix + 'AgeMs'] = min(60000, now - stamp)
    suspended = _context(connection, expected['suspendedContextId'])
    result['suspendedContextPresent'] = suspended is not None
    if suspended is not None:
        result['suspendedState'] = _enum(suspended['state'], STATES)
        queue = _queue(suspended['queue_json'])
        if 'originalTrackId' in expected:
            result['suspendedTrackMatchesOriginal'] = suspended['track_id'] == expected['originalTrackId']
        if 'originalQueue' in expected:
            result['suspendedQueueMatchesOriginal'] = queue == expected['originalQueue']
        if 'originalIndex' in expected:
            result['suspendedIndexMatchesOriginal'] = suspended['current_index'] == expected['originalIndex']
    return result


def observe_follow_server(state_directory, expected):
    """Use only existing private identities; return finite observation, never control.

    An absent/deleted lease means admission unknown, not rejected. Caller should
    retain the immediate command-return observation before restoration deletes it.
    """
    connection = None
    try:
        if not isinstance(expected, dict) or any(not isinstance(expected.get(k), str) or not expected[k] or len(expected[k]) > 256 for k in REQUIRED):
            return {'status': 'refused_expected_scope'}
        if expected['sourceContextId'] == expected['suspendedContextId']:
            return {'status': 'refused_expected_scope'}
        root = Path(state_directory)
        if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
            return {'status': 'refused_fixture_scope'}
        marker = root / '.native-playback-fixture.json'
        database = root / 'native-playback.db'
        paths = (marker, database, root / 'native-playback.db-wal', root / 'native-playback.db-shm', root / 'native-playback.db-journal')
        if any(p.is_symlink() for p in paths):
            return {'status': 'refused_fixture_scope'}
        if not marker.is_file() or marker.stat().st_size > 4096:
            return {'status': 'refused_fixture_scope'}
        ownership = json.loads(marker.read_text(encoding='utf-8'))
        if not isinstance(ownership, dict) or ownership.get('kind') != 'emosonic-native-playback-fixture':
            return {'status': 'refused_fixture_scope'}
        if not database.is_file() or database.stat().st_size > 64 * 1024 * 1024:
            return {'status': 'refused_database_scope'}
        connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.05)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        return _summarize(connection, expected, int(time.time() * 1000))
    except (ValueError, TypeError, KeyError, OverflowError):
        return {'status': 'malformed_observation'}
    except (OSError, sqlite3.Error):
        return {'status': 'observation_unavailable'}
    finally:
        if connection is not None:
            connection.close()
