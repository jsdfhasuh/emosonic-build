import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts' if (ROOT / 'scripts').is_dir() else ROOT
sys.path.insert(0, str(SCRIPTS / 'native_follow_lifecycle_payload'))
import follow_server_observation as o

NOW = 1792645000000
SECRET = 'DO_NOT_EMIT_PRIVATE_VALUE'


class FollowServerObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / '.native-playback-fixture.json').write_text(json.dumps({'kind': 'emosonic-native-playback-fixture'}))
        self.db = self.root / 'native-playback.db'
        self.e = dict(followerClientId='follower', followerDeviceSessionId='follower-device', sourceContextId='source-context', suspendedContextId='original-context', sourceClientId='source', sourceDeviceSessionId='source-device', originalTrackId='old-track', originalQueue=['old-track'], originalIndex=0)
        self.cx = sqlite3.connect(self.db)
        self.addCleanup(self.cx.close)
        self.cx.executescript('''CREATE TABLE emo_follow_safety_lease (
            phase TEXT, source_playback_context_id TEXT, source_authority_client_id TEXT,
            source_authority_device_session_id TEXT, source_connection_nonce TEXT,
            suspended_playback_context_id TEXT, suspended_authority_client_id TEXT,
            suspended_authority_device_session_id TEXT, suspended_epoch INTEGER,
            suspended_version INTEGER, suspended_queue_revision INTEGER,
            suspended_control_version INTEGER, suspended_applied_control_version INTEGER,
            follow_reconnect_grace_expires_at_ms INTEGER, source_recovery_deadline_at_ms INTEGER,
            start_ack_json TEXT, follower_client_id TEXT, follower_device_session_id TEXT);
        CREATE TABLE emo_playback_context (playback_context_id TEXT, lifecycle TEXT,
            state TEXT, track_id TEXT, queue_json TEXT, current_index INTEGER, epoch INTEGER,
            version INTEGER, control_version INTEGER, queue_revision INTEGER,
            authority_client_id TEXT, authority_device_session_id TEXT, playback_json TEXT);
        CREATE TABLE emo_device_playback_state (playback_context_id TEXT, owner_client_id TEXT,
            device_session_id TEXT, context_epoch INTEGER, applied_control_version INTEGER,
            is_authority INTEGER, state TEXT, track_id TEXT, position_ms INTEGER, playback_json TEXT);''')
        ack = dict(action='follow.start', status='active', sourcePlaybackContextId='source-context', suspendedPlaybackContextId='original-context', suspendedEpoch=1, suspendedVersion=2, suspendedQueueRevision=3, suspendedControlVersion=4, suspendedAppliedControlVersion=4, privateSecret=SECRET)
        self.cx.execute('INSERT INTO emo_follow_safety_lease VALUES (' + ','.join('?'*18) + ')', ('active','source-context','source','source-device',SECRET,'original-context','follower','follower-device',1,2,3,4,4,None,NOW+30000,json.dumps(ack),'follower','follower-device'))
        self.cx.execute('INSERT INTO emo_playback_context VALUES (' + ','.join('?'*13) + ')', ('source-context','active','playing','track-a',json.dumps(['track-a','track-b']),0,1,2,5,3,'source','source-device',json.dumps({'playbackRate':1.5,'secret':SECRET})))
        self.cx.execute('INSERT INTO emo_playback_context VALUES (' + ','.join('?'*13) + ')', ('original-context','active','paused','old-track',json.dumps(['old-track']),0,1,2,4,3,'follower','follower-device','{}'))
        self.cx.execute('INSERT INTO emo_device_playback_state VALUES (' + ','.join('?'*10) + ')', ('source-context','source','source-device',1,5,1,'playing','track-a',6000,json.dumps({'playbackRate':1.5,'_connectionNonce':SECRET,'serverUpdatedAtMs':NOW-500,'positionSampledAtServerMs':NOW-500})))
        self.cx.commit()

    def observe(self):
        with patch.object(o.time, 'time', return_value=NOW/1000):
            return o.observe_follow_server(self.root, self.e)

    def test_active_ack_and_fresh_source_are_finite(self):
        result = self.observe()
        self.assertEqual(result['status'], 'read_only_snapshot')
        self.assertEqual(result['admissionObserved'], 'accepted')
        self.assertEqual(result['sourceRecoveryRemainingMs'],30000)
        self.assertTrue(result['sourceSampleFreshWithin2s'])
        self.assertTrue(result['suspendedQueueMatchesOriginal'])
        self.assertTrue(result['sourceDeviceNonceMatchesLease'])
        self.assertNotIn(SECRET,json.dumps(result))
        for private in ['follower-device','source-context','old-track','track-a','start_ack_json','nonce','userName']:
            self.assertNotIn(private,json.dumps(result))

    def test_deleted_row_is_unknown_not_rejected(self):
        self.cx.execute('DELETE FROM emo_follow_safety_lease');self.cx.commit()
        result=self.observe()
        self.assertFalse(result['leasePresent'])
        self.assertEqual(result['admissionObserved'],'unknown')
        self.assertNotIn('phase',result)

    def test_source_deadline_and_stale_fact_are_distinct(self):
        self.cx.execute("UPDATE emo_follow_safety_lease SET phase='cleanupRequired', source_recovery_deadline_at_ms=?",(NOW-1,))
        self.cx.execute('UPDATE emo_device_playback_state SET playback_json=?',(json.dumps({'serverUpdatedAtMs':NOW-2100,'positionSampledAtServerMs':NOW+1}),));self.cx.commit()
        result=self.observe()
        self.assertTrue(result['sourceRecoveryExpired'])
        self.assertFalse(result['sourceUpdatedFreshWithin2s'])
        self.assertFalse(result['sourceSampleTimeValid'])
        self.assertEqual(result['sourceUpdatedAgeMs'],2100)

    def test_malformed_unknown_phase_ack_queue_fail_closed(self):
        original_ack = self.cx.execute('SELECT start_ack_json FROM emo_follow_safety_lease').fetchone()[0]
        for sql in ["UPDATE emo_follow_safety_lease SET phase='private-secret-phase'", "UPDATE emo_follow_safety_lease SET start_ack_json='[]'", "UPDATE emo_playback_context SET queue_json='not-json'", "UPDATE emo_follow_safety_lease SET suspended_epoch=-1"]:
            with self.subTest(sql=sql):
                self.cx.execute(sql); self.cx.commit()
                self.assertEqual(self.observe(), {'status': 'malformed_observation'})
                self.cx.execute("UPDATE emo_follow_safety_lease SET phase='active', suspended_epoch=1, start_ack_json=?", (original_ack,))
                self.cx.execute("UPDATE emo_playback_context SET queue_json=? WHERE playback_context_id='source-context'", (json.dumps(['track-a','track-b']),))
                self.cx.execute("UPDATE emo_playback_context SET queue_json=? WHERE playback_context_id='original-context'", (json.dumps(['old-track']),))
                self.cx.commit()

    def test_unknown_ack_fields_ignored_not_forwarded(self):
        data=json.loads(self.cx.execute('SELECT start_ack_json FROM emo_follow_safety_lease').fetchone()[0]);data['arbitrary']={'payload':SECRET};self.cx.execute('UPDATE emo_follow_safety_lease SET start_ack_json=?',(json.dumps(data),));self.cx.commit()
        self.assertNotIn(SECRET,json.dumps(self.observe()))

    def test_symlink_database_marker_and_parent_refused(self):
        other=self.root/'other.db';other.write_bytes(self.db.read_bytes());self.cx.close();self.db.unlink();self.db.symlink_to(other)
        self.assertEqual(self.observe(),{'status':'refused_fixture_scope'})

    def test_sidecar_symlink_refused(self):
        (self.root/'native-playback.db-wal').symlink_to(self.root/'outside')
        self.assertEqual(self.observe(),{'status':'refused_fixture_scope'})

    def test_missing_or_wrong_owner_and_expected_scope_refused(self):
        (self.root/'.native-playback-fixture.json').write_text('{"kind":"other"}')
        self.assertEqual(self.observe(),{'status':'refused_fixture_scope'})
        self.e['sourceContextId']=self.e['suspendedContextId']
        self.assertEqual(self.observe(),{'status':'refused_expected_scope'})

    def test_readonly_database_and_all_files_unchanged(self):
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir() if p.is_file()}
        self.observe()
        after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before,after)

    def test_missing_schema_is_unavailable_no_private_error(self):
        self.cx.execute('DROP TABLE emo_follow_safety_lease');self.cx.commit()
        self.assertEqual(self.observe(),{'status':'observation_unavailable'})

    def test_parent_and_marker_symlink_refused(self):
        link=self.root/'linked-root'; link.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(o.observe_follow_server(link,self.e), {'status':'refused_fixture_scope'})
        marker=self.root/'.native-playback-fixture.json'; other=self.root/'marker.json'; marker.rename(other);marker.symlink_to(other)
        self.assertEqual(self.observe(), {'status':'refused_fixture_scope'})

    def test_ambiguous_lease_refused(self):
        self.cx.execute('INSERT INTO emo_follow_safety_lease SELECT * FROM emo_follow_safety_lease');self.cx.commit()
        self.assertEqual(self.observe(), {'status':'malformed_observation'})

    def test_readonly_connection_mode_and_query_only(self):
        real=sqlite3.connect
        seen=[]
        def connect(database, **kwargs):
            self.assertTrue(database.endswith('?mode=ro'));self.assertTrue(kwargs['uri'])
            conn=real(database, **kwargs);conn.set_trace_callback(seen.append);return conn
        with patch.object(o.sqlite3,'connect',side_effect=connect):
            self.observe()
        self.assertIn('PRAGMA query_only=ON',seen)
        self.assertTrue(all(q.startswith(('SELECT','PRAGMA query_only=ON','BEGIN')) for q in seen))

    def test_missing_database_not_created(self):
        self.cx.close(); self.db.unlink()
        self.assertEqual(self.observe(), {'status':'refused_database_scope'})
        self.assertFalse(self.db.exists())

    def test_controller_canonical_root_supports_system_alias_without_trusting_links(self):
        # Models macOS /var -> /private/var. Only the controller that created
        # TemporaryDirectory resolves this root; observer never adopts a link.
        alias=self.root/'var'; alias.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(o.observe_follow_server(alias,self.e), {'status':'refused_fixture_scope'})
        with patch.object(o.time,'time',return_value=NOW/1000):
            safe=o.observe_follow_server(alias.resolve(strict=True),self.e)
        self.assertEqual(safe['status'],'read_only_snapshot')
        # Canonicalizing the root does not admit child symlinks.
        (self.root/'native-playback.db-shm').symlink_to(self.root/'outside-shm')
        self.assertEqual(o.observe_follow_server(alias.resolve(strict=True),self.e), {'status':'refused_fixture_scope'})
