"""Disposable-only Follow seek/preroll readiness and read-only native observability."""
import argparse
import ast
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAB = 'tool/native_playback_mac/run_lab.py'
PREPARE = 'tool/native_playback_mac/prepare_build.py'
FIXTURE = 'tool/native_playback_mac/test_follow_alignment.py'
STATE = '.native_follow_readiness/manifest.json'
ORIGINAL_STATE = '.native_follow_readiness/original-run_lab.py'
PROOF_STATE = '.native_follow_readiness/contract-proof.json'
CONTRACT_CHECKS = 35
PRECISION_CHECKS = 46
PRECISION_PRIOR_SHA256 = '6eb44ffc54f90dab0df7bd320c68e39f0c764c1af126c05fa29e64da22acdc36'
PROOF_LAYERS = {'priorReadiness': 23, 'finalCompatible': 19, 'sharedWitness': 12}
SHARED_BASELINE_SHA256 = 'dad22e364b950e8f0b500dac13a084b0ac722f6d91dd265cef77759d2e4029ad'
NATIVE_STATE = '.native_mac_lab/seek-observability.json'
NATIVE_ROOT = '.native_mac_lab/just_audio/darwin/just_audio/Sources/just_audio'
NATIVE_PATHS = {'AudioPlayer.h': NATIVE_ROOT + '/include/just_audio/AudioPlayer.h',
                'AudioPlayer.m': NATIVE_ROOT + '/AudioPlayer.m'}
BASELINE = {LAB: '96dda56b6d8d4e674cb35c7426af69e5f67cee869f977bbc1e09cf95c4bfd1a6',
           PREPARE: '4dcb27fa7d93a74823d5727a271459ed6cd0901999bd33e5180afff0e363da0e',
           FIXTURE: 'f324d2f5106a26837aca41c4733e03f3a08c583b7d3cc1e12017bf34812bd8a5'}
# Filled from independently reviewed exact transformations, not runtime source.
AFTER = {'tool/native_playback_mac/run_lab.py': 'caabd06cfa324592da807ee794a99dd3d726f58acc3d7a7db1c023ae6ed87f5c', 'tool/native_playback_mac/prepare_build.py': 'dfdd215375ac1afd5a90e278733f5ca1a1ef5683317f95526933b5b6fe758532', 'tool/native_playback_mac/test_follow_alignment.py': 'cafbeaf89647915cab12d8664a03f186c016f9ca5c10dfc1738d0a3d2bdb63cd'}
NATIVE_HASHES = {'AudioPlayer.h': {'before': 'c8c6df3bc07f10677e0afbeb447c88da2a704b2c8323769247f78768c6a43138', 'after': '6b48fdf8e6bf67849126224151470cb8932d432f2dffd7e6fd8d09ef85796cb2'}, 'AudioPlayer.m': {'before': 'ecec29e1f913f0dca944ca3fb2e45a7ad96a138391af59f99ca3f46dfd5b65b3', 'after': 'dfc408d533c30fe95b8d0a9ad2284f2266fdbaba3377da2bde372fcaad4441c7'}}
PAYLOAD_HASHES = {'alignment_fixture_compatibility.py': 'fcc46886d6091464d0d36b20615bbc88f09f3120deb8655ba2de49cdd1b613c0', 'follow_readiness_helpers.py': 'a23c172a5d009e4271efbcfe939810d3c2ca5da756bca853e8cdf0b86c60edd7', 'instrument_seek_observability.py': '678ccfe3e91b6257eb49144da60203e96bfed2183a75bed4acdd1552bf4a5bfa', 'readiness_contract.py': '0cd4fd059c0d6d0d82f87d10c06bb2dc929f184a14033ccada2fee62e33e0431', 'follow_precision_helpers.py': 'e10280fb4bf79e8d559accfb620791b57575a1d856c64d21eed15301b76cd78e', 'precision_contract.py': 'a6d8eaa238fd33f9eb948b8518d6765091a46f559fa1da198bdf9a570319f3a7', 'legacy_precision_contract.py': 'ff02ebb56a0b39804ec2e8dc69f465d86312bc0c09af8ed5005153583eb2116b', 'legacy_precision_inventory.json': 'ce5c83811af1b67968907639d4dde3fe3b398a9f5b472209074a5c798721906f'}


def digest(data): return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Readiness instrumentation anchor changed')
    return text.replace(old, new, 1)


def payload(name):
    data = (ROOT / 'native_follow_readiness_payload' / name).read_bytes()
    if PAYLOAD_HASHES and digest(data) != PAYLOAD_HASHES[name]:
        raise ValueError('Readiness packaged payload changed')
    return data.decode('utf-8')


def patch_harness(original):
    if digest(original) != BASELINE[LAB]:
        raise ValueError('Readiness observed harness pin changed')
    text = original.decode('utf-8')
    text = replace_once(text, '\nclass Matrix:\n', '\n' + payload('follow_readiness_helpers.py') + '\nclass Matrix:\n')
    anchor = '''        previous = None
        while True:
            states = self.states()
            authority, follower = states[authority_index], states[2]
            assert native_follow_task_ready(authority, follower, context)
'''
    replacement = '''        baseline = self.last
        assert native_follow_task_ready(baseline[authority_index], baseline[2], context)
        correction_identity = follow_correction_identity(baseline, authority_index, context)
        self.rate_measurement.update({'correctionReadinessPollCount': 0, 'correctionReadinessElapsedMs': 0})
        previous = None
        while True:
            states = self.states()
            authority, follower = states[authority_index], states[2]
            assert follow_correction_identity(states, authority_index, context) == correction_identity
            if native_follow_readiness_pending(authority, follower, expected):
                elapsed_ms = (time.monotonic() - started) * 1000
                self.rate_measurement.update({
                    'correctionReadinessPollCount': min(25, self.rate_measurement['correctionReadinessPollCount'] + 1),
                    'correctionReadinessElapsedMs': round(min(5000, max(0, elapsed_ms)), 2),
                    'alignmentSourceNative': numeric_native_snapshot(decoded(authority)),
                    'alignmentFollowerNative': numeric_native_snapshot(decoded(follower)),
                })
                if time.monotonic() >= deadline:
                    raise TimeoutError('Native Follow alignment exceeded five-second readiness budget')
                previous = None
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
                continue
            assert native_follow_task_ready(authority, follower, context)
'''
    text = replace_once(text, anchor, replacement)
    text = replace_once(text, '                    consecutiveAlignedSamples=2)', '''                    consecutiveAlignedSamples=2,
                    correctionReadinessPollCount=self.rate_measurement['correctionReadinessPollCount'],
                    correctionReadinessElapsedMs=self.rate_measurement['correctionReadinessElapsedMs'])''')
    anchor = '''    return {key: item[key] for key in fields if key in item
            and type(item[key]) in (int, float) and math.isfinite(item[key])}'''
    text = replace_once(text, anchor, '''    result = {key: item[key] for key in fields if key in item
            and type(item[key]) in (int, float) and math.isfinite(item[key])}
    result.update({key: item[key] for key in ('seekInProgress', 'playingIntent')
                   if type(item.get(key)) is bool})
    return result''')
    ast.parse(text)
    return strengthen_follow_precision(share_advancement_witness(text.encode('utf-8')))


def shared_witness_operations():
    """Only the same-call final aligned pair may fund existing movement checks."""
    return (
        ('    def follow_alignment(self, context, authority_index, expected, started, deadline):\n',
         '    def follow_alignment(self, context, authority_index, expected, started, deadline, advancement_witness=None):\n'
         '        if advancement_witness is not None:\n'
         '            assert type(advancement_witness) is list and not advancement_witness\n'),
        ('                return follower\n',
         '                if advancement_witness is not None:\n'
         '                    advancement_witness.append((context, authority_index, expected, follower, previous[1]))\n'
         '                return follower\n'),
        ('        aligned_state = None\n', '        aligned_state = None\n        advancement_witness = []\n'),
        ('                follow_context, authority_index, expected, readiness_started, readiness_deadline)\n',
         '                follow_context, authority_index, expected, readiness_started, readiness_deadline,\n'
         '                advancement_witness=advancement_witness)\n'),
        ('        anchor = first\n        previous = first\n        while True:\n'
         '            time.sleep(0.1)\n            first_state = observe()\n            first = decoded(first_state)\n',
         '        anchor = first\n'
         '        if aligned_state is not None:\n'
         '            assert len(advancement_witness) == 1\n'
         '            witness_context, witness_authority, witness_rate, witness_state, anchor = advancement_witness[0]\n'
         '            assert witness_context == follow_context and witness_authority == authority_index and witness_rate == expected\n'
         '            assert witness_state is first_state\n'
         '        previous = anchor\n'
         '        reuse_aligned_advancement = aligned_state is not None\n'
         '        while True:\n'
         '            if reuse_aligned_advancement:\n'
         '                reuse_aligned_advancement = False\n'
         '            else:\n'
         '                time.sleep(0.1)\n                first_state = observe()\n                first = decoded(first_state)\n'),
    )


def share_advancement_witness(original):
    text = original.decode('utf-8')
    for old, new in shared_witness_operations(): text = replace_once(text, old, new)
    result = text.encode('utf-8')
    if restore_advancement_witness(result) != original:
        raise ValueError('Shared readiness witness inverse changed')
    before, after = ast.parse(original), ast.parse(result)
    old_asserts = [ast.dump(n) for n in ast.walk(before) if isinstance(n, ast.Assert)]
    new_asserts = [ast.dump(n) for n in ast.walk(after) if isinstance(n, ast.Assert)]
    if any(new_asserts.count(item) < old_asserts.count(item) for item in old_asserts):
        raise ValueError('Shared readiness removed an original assertion')
    tail = "        self.rate_measurement['firstNative'] = numeric_native_snapshot(first)\n"
    if original.count(tail.encode()) != 1 or result.split(tail.encode(), 1)[1] != original.split(tail.encode(), 1)[1]:
        raise ValueError('Shared readiness changed strict measurement or later controls')
    return result


def restore_advancement_witness(shared):
    text = shared.decode('utf-8')
    for old, new in reversed(shared_witness_operations()): text = replace_once(text, new, old)
    return text.encode('utf-8')



def precision_operations():
    return (
        ('\nclass Matrix:\n', '\n' + payload('follow_precision_helpers.py') + '\nclass Matrix:\n'),
        ('            aligned = abs(error) <= tolerance + uncertainty and uncertainty <= 25\n',
         '            nominal = follow_nominal_precision_ready(authority, follower, expected)\n'
         '            aligned = nominal and abs(error) + uncertainty + 1.0 <= 50 and uncertainty <= 25\n'),
        ('        readiness_deadline = readiness_started + 5\n        def observe():\n',
         '        readiness_deadline = readiness_started + 5\n'
         '        precision_identity = (follow_correction_identity(self.last, authority_index, follow_context)\n'
         '            if follow_context is not None else None)\n'
         '        precision_previous = None\n'
         '        def observe():\n'
         '            nonlocal precision_previous\n'),
        ('                assert native_rate_matches(states[authority_index], expected)\n            return states[index]\n',
         '                assert native_rate_matches(states[authority_index], expected)\n'
         '                if precision_previous is not None:\n'
         '                    precision_previous = follow_precision_sample(self, states, authority_index,\n'
         '                        follow_context, expected, precision_identity, precision_previous)\n'
         '            return states[index]\n'),
        ("        self.rate_measurement['firstNative'] = numeric_native_snapshot(first)\n",
         "        self.rate_measurement['firstNative'] = numeric_native_snapshot(first)\n"
         '        if follow_context is not None:\n'
         '            assert self.last[index] is first_state\n'
         '            precision_previous = follow_precision_sample(self, self.last, authority_index,\n'
         '                follow_context, expected, precision_identity)\n'),
    ) + precision_transition_operations() + convergence_operations()


def precision_transition_operations():
    """Explicit owned transition seams only; no additional state fetch."""
    return (('        self.follow_connection_generations = None\n',
  '        self.follow_connection_generations = None\n        self.follow_precision_transition = None\n'),
 ('                states = self.states()\n                if reject_terminal_handoff:\n',
  '                states = self.states()\n'
  "                if stage == 'handoff-native-completion':\n"
  '                    observe_follow_precision_transition(self, states)\n'
  '                if reject_terminal_handoff:\n'),
 ('        readiness_deadline = readiness_started + 5\n        precision_identity',
  '        readiness_deadline = readiness_started + 5\n'
  '        transition = self.follow_precision_transition\n'
  '        transition_reused = False\n'
  '        readiness_entry = readiness_started\n'
  '        if follow_context is not None and transition is not None:\n'
  "            assert transition['context'] == follow_context and transition['expected'] == expected\n"
  '            assert authority_index == 1\n'
  "            readiness_started, readiness_deadline = transition['origin'], transition['deadline']\n"
  '        precision_identity'),
 ('            states = self.states()\n            if follow_context is not None:\n',
  '            states = self.states()\n'
  '            observe_follow_precision_transition(self, states)\n'
  '            if follow_context is not None:\n'),
 ('            aligned_state = self.follow_alignment(\n'
  '                follow_context, authority_index, expected, readiness_started, readiness_deadline,\n'
  '                advancement_witness=advancement_witness)\n',
  "            if transition is not None and transition['settled']:\n"
  "                assert transition['settledAt'] < transition['deadline']\n"
  "                assert transition['lastStates'] is self.last\n"
  "                assert 0 <= readiness_entry-transition['lastObservedAt'] <= 0.2\n"
  '                assert follow_correction_identity(self.last, authority_index, follow_context) == '
  "transition['identity']\n"
  '                aligned_state = self.last[index]\n'
  '                advancement_witness.append((follow_context, authority_index, expected, aligned_state, '
  "transition['previousPair'][1]))\n"
  '                transition_reused = True\n'
  "                self.outcome('native-follow-aligned', consecutiveAlignedSamples=2,\n"
  "                    waitDurationMs=(transition['settledAt']-transition['origin'])*1000,\n"
  "                    alignedDriftMs=transition['measurement']['precisionDriftMs'],\n"
  "                    readUncertaintyMs=transition['measurement']['precisionUncertaintyMs'])\n"
  '            else:\n'
  '                aligned_state = self.follow_alignment(\n'
  '                    follow_context, authority_index, expected, readiness_started, readiness_deadline,\n'
  '                    advancement_witness=advancement_witness)\n'),
 ('            if time.monotonic() >= readiness_deadline:\n'
  "                raise TimeoutError('Native playing position did not begin advancing')\n",
  '            if time.monotonic() >= readiness_deadline and not transition_reused:\n'
  "                raise TimeoutError('Native playing position did not begin advancing')\n"),
 ("            follower.command('follow', contextId=context)\n",
  '            self.follow_initial_command_started = time.monotonic()\n'
  "            follower.command('follow', contextId=context)\n"),
 ("            self.wait('native-follow-start', lambda ss: native_follow_task_ready(ss[0], ss[2], "
  'context))\n',
  "            self.wait('native-follow-start', lambda ss: native_follow_task_ready(ss[0], ss[2], context))\n"
  '            self.follow_initial_acquisition_ms = '
  '(time.monotonic()-self.follow_initial_command_started)*1000\n'),
 ("        self.outcome(label, measuredRate=round(measured, 4), nativeRate=last['playbackRate'],\n",
  '        if follow_context is not None and authority_index == 0:\n'
  "            self.rate_measurement['initialFollowAcquisitionMs'] = getattr(self, "
  "'follow_initial_acquisition_ms', 0)\n"
  "            initial_origin = getattr(self, 'follow_initial_command_started', readiness_started)\n"
  "            self.rate_measurement['initialFollowCommandToMeasurementEndMs'] = "
  '(time.monotonic()-initial_origin)*1000\n'
  "        self.outcome(label, measuredRate=round(measured, 4), nativeRate=last['playbackRate'],\n"),
 ("        self.stage = 'handoff-A-to-B'\n        a.command('handoff'",
  "        self.stage = 'handoff-A-to-B'\n"
  '        if follower is not None:\n'
  "            begin_follow_precision_transition(self, before_states, context, 'transfer', 1.5, "
  'time.monotonic())\n'
  "        _handoff_response = a.command('handoff'"),
 ("                  targetDeviceSessionId=target_identity['deviceSessionId'])\n        after = self.wait('handoff-native-completion'",
  "                  targetDeviceSessionId=target_identity['deviceSessionId'])\n"
  "        if follower is not None:\n"
  "            pin_follow_transfer_command(self, _handoff_response)\n"
  "        after = self.wait('handoff-native-completion'"),
 ("target_identity['clientId'], target_identity['deviceSessionId']), reject_terminal_handoff=True)\n",
  "target_identity['clientId'], target_identity['deviceSessionId']), reject_terminal_handoff=True,\n"
  "            timeout=max(0, self.follow_precision_transition['deadline']-time.monotonic()) if follower is "
  'not None else 45)\n'),
 ('            unsettled_at = None\n            maximum = 0\n',
  "            unsettled_at = self.follow_precision_transition['origin']\n            maximum = 0\n"),
 ("                if abs(error) <= ss[2]['followSyncToleranceMs'] + uncertainty and uncertainty <= 25:\n"
  '                    unsettled_at = None\n'
  '                elif unsettled_at is None:\n'
  '                    unsettled_at = time.monotonic()\n'
  '                else:\n'
  "                    self.record_follow_condition('lab_five_second_settling', time.monotonic() - "
  'unsettled_at <= 5)\n',
  '                try:\n'
  '                    observe_follow_precision_transition(self, ss)\n'
  '                except FollowPrecisionUnsafe:\n'
  "                    self.record_follow_condition('safe_follow_task', False)\n"
  "                    self.follow_outcomes.update(continuity='failed', rate_change='unavailable', "
  "restoration='unavailable')\n"
  '                    self.require_follow_success()\n'
  '                except (AssertionError, TimeoutError):\n'
  "                    condition = 'steady_sample_precision' if self.follow_precision_transition['settled'] "
  "else 'lab_five_second_settling'\n"
  '                    self.record_follow_condition(condition, False)\n'
  "                self.follow_observation['precision'] = "
  "dict(self.follow_precision_transition['measurement'])\n"
  "                unsettled_at = None if self.follow_precision_transition['settled'] else "
  "self.follow_precision_transition['origin']\n"),
 ('            first = decoded(ss[2])\n            while time.monotonic() < end:\n',
  '            first = decoded(ss[2])\n'
  '            try:\n'
  '                observe_follow_precision_transition(self, ss)\n'
  '            except FollowPrecisionUnsafe:\n'
  "                self.record_follow_condition('safe_follow_task', False)\n"
  "                self.follow_outcomes.update(continuity='failed', rate_change='unavailable', "
  "restoration='unavailable')\n"
  '                self.require_follow_success()\n'
  '            except (AssertionError, TimeoutError):\n'
  "                condition = 'steady_sample_precision' if self.follow_precision_transition['settled'] else "
  "'lab_five_second_settling'\n"
  '                self.record_follow_condition(condition, False)\n'
  '            while time.monotonic() < end:\n'),
 ("            self.record_follow_condition('native_35s_progression', last['positionMs'] > "
  "first['positionMs'] + 40000)\n",
  "            self.record_follow_condition('native_35s_progression', last['positionMs'] > "
  "first['positionMs'] + 40000)\n"
  "            self.record_follow_condition('lab_five_second_settling', "
  "self.follow_precision_transition['settled'])\n"),
 ("'maximumAlignedDriftMs': round(maximum, 2), 'conditions': self.follow_conditions}), flush=True)\n",
  "'maximumAlignedDriftMs': round(maximum, 2), 'conditions': self.follow_conditions,\n"
  "                              'rateMeasurement': self.follow_precision_transition['measurement']}), "
  'flush=True)\n'
  '            self.follow_precision_transition = None\n'),
 ("        self.clients[1].command('speed', speed=0.8)\n",
  "        begin_follow_precision_transition(self, self.last, context, 'rate_change', 0.8, started)\n"
  "        self.clients[1].command('speed', speed=0.8)\n"),
 ('            authority, follower = states[1:3]\n'
  '            elapsed_ms = (time.monotonic() - started) * 1000\n',
  '            authority, follower = states[1:3]\n'
  '            observe_follow_precision_transition(self, states)\n'
  '            elapsed_ms = (time.monotonic() - started) * 1000\n'),
 ('                  follow_context=context, authority_index=1)\n',
  '                  follow_context=context, authority_index=1)\n'
  '        self.follow_precision_transition = None\n'),
 ("FOLLOW_CONDITIONS = {'native_evidence',",
  "FOLLOW_CONDITIONS = {'steady_sample_precision', 'native_evidence',"),
 ('            authority, follower = states[authority_index], states[2]\n'
  '            assert follow_correction_identity',
  '            authority, follower = states[authority_index], states[2]\n'
  '            observe_follow_precision_transition(self, states)\n'
  '            assert follow_correction_identity'),
 ('        deadline = time.monotonic() + 5\n        while True:\n',
  '        measurement_started = time.monotonic()\n        deadline = measurement_started + 5\n        while True:\n'),
 ('            if elapsed >= 3:\n                break\n            if time.monotonic() >= deadline:\n',
  '            strict_window = follow_context is not None or self.follow_precision_transition is not None\n'
  '            measurement_now = time.monotonic()\n'
  '            if strict_window and measurement_now >= deadline:\n'
  "                raise TimeoutError('Strict Follow measurement exceeded original five seconds')\n"
  '            if elapsed >= 3 and (not strict_window or measurement_now-measurement_started >= 3):\n'
  '                break\n            if time.monotonic() >= deadline:\n'),
 ('            except (URLError, ConnectionError, TimeoutError):\n',
  '            except FollowPrecisionDeadline:\n'
  '                raise\n'
  '            except (URLError, ConnectionError, TimeoutError):\n'))



def convergence_operations():
    """Only external Follow convergence is ten seconds; measurement stays five."""
    # Fifty 200 ms intervals plus the initial tuple; terminal polls are not eligible.
    return (('        readiness_deadline = readiness_started + 5\n        transition =',
  '        readiness_deadline = readiness_started + (10 if follow_context is not None else 5)\n'
  '        transition ='),
 ('        precision_previous = None\n        def observe():',
  '        precision_previous = None\n'
  '        if follow_context is not None:\n'
  '            if transition is None:\n'
  "                self.rate_measurement['initialFollowAcquisitionMs'] = getattr(self, "
  "'follow_initial_acquisition_ms', 0)\n"
  "                self.rate_measurement['initialFollowCommandToConvergenceOriginMs'] = "
  "(readiness_started-getattr(self, 'follow_initial_command_started', readiness_started))*1000\n"
  "                follow_convergence_observation(self, 'initial', 0)\n"
  '            else:\n'
  "                self.rate_measurement.update(transition['measurement'])\n"
  '        def observe():'),
 ("                    'correctionReadinessPollCount': min(25,",
  "                    'correctionReadinessPollCount': min(51,"),
 ("'correctionReadinessElapsedMs': round(min(5000, max(0, elapsed_ms)), 2)",
  "'correctionReadinessElapsedMs': round(min(10000, max(0, elapsed_ms)), 2)"),
 ('                if time.monotonic() >= deadline:\n'
  "                    raise TimeoutError('Native Follow alignment exceeded five-second readiness budget')",
  '                if self.follow_precision_transition is None:\n'
  "                    follow_convergence_observation(self, 'initial', elapsed_ms)\n"
  '                if time.monotonic() >= deadline:\n'
  "                    raise TimeoutError('Native Follow alignment exceeded ten-second convergence budget')"),
 ('            if time.monotonic() >= deadline:\n'
  "                raise TimeoutError('Native Follow alignment exceeded five-second readiness budget')",
  '            if self.follow_precision_transition is None:\n'
  "                follow_convergence_observation(self, 'initial', "
  "self.rate_measurement['alignmentElapsedMs'])\n"
  '            if time.monotonic() >= deadline:\n'
  "                raise TimeoutError('Native Follow alignment exceeded ten-second convergence budget')"),
 ("            if stable:\n                self.outcome('native-follow-aligned',",
  '            if stable:\n'
  '                if self.follow_precision_transition is None:\n'
  "                    follow_convergence_observation(self, 'initial', "
  "self.rate_measurement['alignmentElapsedMs'],\n"
  "                        self.rate_measurement['alignmentElapsedMs'])\n"
  "                self.outcome('native-follow-aligned',"),
 ('        deadline = started + 5\n'
  "        self.rate_measurement = {'expectedRate': 0.8, 'readinessTimeoutMs': 5000}",
  '        deadline = started + 10\n'
  "        self.rate_measurement = {'expectedRate': 0.8, 'readinessTimeoutMs': 10000}"),
 ('Explicit Follow rate change did not converge within five seconds',
  'Explicit Follow rate change did not converge within ten seconds'),
 ("\n                     'hard_drift_limit', 'lab_five_second_settling', 'native_35s_progression',\n",
  "\n                     'hard_drift_limit', 'lab_ten_second_convergence', 'native_35s_progression',\n"),
 ('\n'
  "                condition = 'steady_sample_precision' if self.follow_precision_transition['settled'] else "
  "'lab_five_second_settling'\n",
  '\n'
  "                condition = 'steady_sample_precision' if self.follow_precision_transition['settled'] else "
  "'lab_ten_second_convergence'\n"),
 ('\n'
  "                    condition = 'steady_sample_precision' if self.follow_precision_transition['settled'] "
  "else 'lab_five_second_settling'\n",
  '\n'
  "                    condition = 'steady_sample_precision' if self.follow_precision_transition['settled'] "
  "else 'lab_ten_second_convergence'\n"),
 ('\n'
  "            self.record_follow_condition('lab_five_second_settling', "
  "self.follow_precision_transition['settled'])\n",
  '\n'
  "            self.record_follow_condition('lab_ten_second_convergence', "
  "self.follow_precision_transition['settled'])\n"),
 ('        # Both readiness phases share the original five-second deadline.\n',
  '        # Both phases share one deadline: ten seconds for Follow, five otherwise.\n'))

def strengthen_follow_precision(original):
    text = original.decode('utf-8')
    for old, new in precision_operations(): text = replace_once(text, old, new)
    result = text.encode('utf-8')
    if restore_follow_precision(result) != original:
        raise ValueError('Strict Follow precision inverse changed')
    before, after = ast.parse(original), ast.parse(result)
    old_asserts = [ast.dump(n) for n in ast.walk(before) if isinstance(n, ast.Assert)]
    new_asserts = [ast.dump(n) for n in ast.walk(after) if isinstance(n, ast.Assert)]
    if any(new_asserts.count(item) < old_asserts.count(item) for item in old_asserts):
        raise ValueError('Strict Follow precision removed an original assertion')
    return result


def restore_follow_precision(updated):
    text = updated.decode('utf-8')
    for old, new in reversed(precision_operations()): text = replace_once(text, new, old)
    return text.encode('utf-8')


def patch_prepare(original):
    if digest(original) != BASELINE[PREPARE]:
        raise ValueError('Readiness native builder pin changed')
    text = original.decode('utf-8')
    text = replace_once(text, '\ndef main():\n', '\n' + payload('instrument_seek_observability.py') + '\ndef main():\n')
    text = replace_once(text, '    shutil.copytree(source, target)\n', '''    shutil.copytree(source, target)
    seek_sources = instrument_seek_observability(target)
    seek_manifest = build_root / 'seek-observability.json'
    if seek_manifest.exists() or seek_manifest.is_symlink():
        raise RuntimeError('Native seek observation manifest already exists')
    seek_manifest.write_text(json.dumps({'readOnly': True, 'files': seek_sources}, indent=2), encoding='utf-8')
''')
    text = replace_once(text, '                @"requestedRate": @(wrapper.speed),\n', '''                @"requestedRate": @(wrapper.speed),
                @"seekInProgress": @(wrapper.labSeekInProgress),
                @"playingIntent": @(wrapper.labPlayingIntent),
''')
    ast.parse(text)
    return text.encode('utf-8')


def patch_fixture(original):
    namespace = {}
    exec(compile(payload('alignment_fixture_compatibility.py'), '<owned-fixture-compatibility>', 'exec'), namespace)
    return namespace['transform'](original)


def checked(repo, relative, *, new=False):
    repo = Path(repo)
    path = repo / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Readiness source symlink refused')
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError('Readiness source containment refused')
    if new:
        if path.exists(): raise ValueError('Readiness source already instrumented')
        if not path.parent.is_dir(): raise ValueError('Readiness private state directory missing')
    elif not path.is_file():
        raise ValueError('Readiness source is unavailable')
    return path


def expected_manifest():
    return {'status': 'prepared', 'productionRepositoryMutation': False,
            'disposableOnly': True, 'nativeReadOnlyGetters': True, 'originalFixtureTestMethodsUnchanged': False, 'originalFixtureAssertionsUnchanged': True,
            'fixtureTestMethodsChanged': ['test_alignment_and_advancement_share_original_deadline'],
            'strictSampledFollowAcceptance': True,
            'externalFollowConvergenceBudgetMs': 10000, 'strictMeasurementTimeoutMs': 5000,
            'productRecoveryBudgetUnchanged': True, 'physicalConvergenceIsNotInternalRecoverySuccess': True,
            'strictFollowDriftBoundMs': 50, 'strictFollowPropertyEpsilon': 0.0001,
            'strictFollowPositionRoundingAllowanceMs': 1,
            'strictFollowCoverage': 'existing_sampled_tuples_not_between_samples',
            'sharedAlignmentAdvancementWitness': True, 'allOriginalAdvancementAssertionsPreserved': True,
            'files': {name: {'before': BASELINE[name], 'after': AFTER[name]} for name in BASELINE},
            'payloads': PAYLOAD_HASHES}


def apply(source_repo):
    files = {name: checked(source_repo, name) for name in BASELINE}
    state_root = checked(source_repo, '.native_follow_readiness', new=True)
    manifest_path = state_root / 'manifest.json'
    originals = {name: path.read_bytes() for name, path in files.items()}
    updates = {LAB: patch_harness(originals[LAB]), PREPARE: patch_prepare(originals[PREPARE]),
               FIXTURE: patch_fixture(originals[FIXTURE])}
    if any(digest(data) != AFTER[name] for name, data in updates.items()):
        raise ValueError('Readiness packaged transformation hash changed')
    state_root.mkdir()
    (state_root / 'original-run_lab.py').write_bytes(originals[LAB])
    for name, data in updates.items(): files[name].write_bytes(data)
    manifest = expected_manifest()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def _verify_source_prepared(source_repo, *, timing_observation=False):
    # The attribution gate independently verifies final run_lab bytes against
    # AFTER[LAB] after reversing its own exact transport-only additions.
    if type(timing_observation) is not bool:
        raise ValueError('Readiness timing observation mode refused')
    expected_prepare = AFTER[PREPARE]
    if timing_observation:
        import native_seek_anchor_observation as timing
        if timing.PREPARE_SHA != AFTER[PREPARE] or timing.EXPECTED != {
                name: hashes['after'] for name, hashes in NATIVE_HASHES.items()}:
            raise ValueError('Readiness timing baseline chain changed')
        timing.verify_prepared(source_repo, require_harness=False)
        expected_prepare = timing.AFTER[PREPARE]
    for name in PAYLOAD_HASHES: payload(name)
    manifest = json.loads(checked(source_repo, STATE).read_text())
    if (not isinstance(manifest, dict) or manifest != expected_manifest()
            or any(type(manifest.get(key)) is not bool for key in
                   ('productionRepositoryMutation', 'disposableOnly', 'nativeReadOnlyGetters', 'originalFixtureTestMethodsUnchanged',
                    'sharedAlignmentAdvancementWitness', 'allOriginalAdvancementAssertionsPreserved', 'originalFixtureAssertionsUnchanged'))):
        raise ValueError('Readiness preparation manifest changed')
    for name in (PREPARE, FIXTURE):
        expected_hash = expected_prepare if name == PREPARE else AFTER[name]
        if digest(checked(source_repo, name).read_bytes()) != expected_hash:
            raise ValueError('Readiness prepared source changed')
    if digest(checked(source_repo, ORIGINAL_STATE).read_bytes()) != BASELINE[LAB]:
        raise ValueError('Readiness private baseline changed')
    return manifest


def expected_proof():
    return {'status': 'passed', 'checks': CONTRACT_CHECKS, 'baseline': BASELINE[LAB],
            'patched': AFTER[LAB], 'suiteSha256': PAYLOAD_HASHES['readiness_contract.py'],
            'sharedBaseline': SHARED_BASELINE_SHA256, 'readinessProofLayers': PROOF_LAYERS,
            'priorAcceptanceHarness': PRECISION_PRIOR_SHA256,
            'precision': {'checks': PRECISION_CHECKS, 'suiteSha256': PAYLOAD_HASHES['precision_contract.py'],
                'baseline': PRECISION_PRIOR_SHA256, 'patched': AFTER[LAB]}}


class _ContractProofFailure(ValueError):
    pass


def _failed_contract_ordinals(result, names):
    # A unittest subtest owns parameters which must never reach public output.
    # Use only its parent method's exact allowlisted ordinal, not id()/str().
    ordinals = set()
    for test, _ in result.errors + result.failures:
        owner = getattr(test, 'test_case', test)
        name = getattr(owner, '_testMethodName', None)
        if type(name) is str and name in names:
            ordinals.add(names.index(name) + 1)
    return sorted(ordinals)[:CONTRACT_CHECKS]


def _verify_contract(source_repo):
    _verify_source_prepared(source_repo)
    proof_path = checked(source_repo, PROOF_STATE, new=True)
    baseline = checked(source_repo, ORIGINAL_STATE).read_bytes()
    patched = checked(source_repo, LAB).read_bytes()
    if digest(patched) != AFTER[LAB]:
        raise ValueError('Readiness contract harness changed')
    module_path = ROOT / 'native_follow_readiness_payload' / 'readiness_contract.py'
    spec = importlib.util.spec_from_file_location('owned_readiness_contract', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = module.TEST_NAMES
    if len(names) != CONTRACT_CHECKS or len(set(names)) != CONTRACT_CHECKS:
        raise ValueError('Readiness contract test names changed')
    prior_precision = restore_follow_precision(patched)
    if digest(prior_precision) != PRECISION_PRIOR_SHA256:
        raise ValueError('Strict precision inverse baseline changed')
    shared_baseline = restore_advancement_witness(prior_precision)
    if digest(shared_baseline) != SHARED_BASELINE_SHA256:
        raise ValueError('Shared readiness baseline changed')
    suite = module.suite(baseline, prior_precision, shared_baseline)
    result = unittest.TestResult()
    suite.run(result)
    if (result.testsRun != CONTRACT_CHECKS or result.errors or result.failures
            or result.skipped or result.expectedFailures or result.unexpectedSuccesses):
        ordinals = _failed_contract_ordinals(result, names)
        print(json.dumps({'stage': 'native-follow-readiness-proof', 'status': 'failed',
            'checks': min(CONTRACT_CHECKS, max(0, result.testsRun)),
            'failedTestOrdinals': ordinals[:CONTRACT_CHECKS],
            'errorCategory': 'runner' if result.errors else 'assertion'}), flush=True)
        raise _ContractProofFailure('Readiness deterministic contract proof failed')
    precision_path = ROOT / 'native_follow_readiness_payload' / 'precision_contract.py'
    spec = importlib.util.spec_from_file_location('owned_precision_contract', precision_path)
    precision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(precision)
    if len(precision.TEST_NAMES) != PRECISION_CHECKS or len(set(precision.TEST_NAMES)) != PRECISION_CHECKS:
        raise ValueError('Precision contract test names changed')
    precision_result = unittest.TestResult()
    precision.suite(prior_precision, patched).run(precision_result)
    if (precision_result.testsRun != PRECISION_CHECKS or precision_result.errors or precision_result.failures
            or precision_result.skipped or precision_result.expectedFailures or precision_result.unexpectedSuccesses):
        print(json.dumps({'stage': 'native-follow-precision-proof', 'status': 'failed',
            'checks': min(PRECISION_CHECKS, max(0, precision_result.testsRun)),
            'failedTestOrdinals': _failed_contract_ordinals(precision_result, precision.TEST_NAMES),
            'errorCategory': 'runner' if precision_result.errors else 'assertion'}), flush=True)
        raise _ContractProofFailure('Strict Follow precision contract failed')
    print(json.dumps({'stage': 'native-follow-precision-proof', 'status': 'passed', 'checks': PRECISION_CHECKS}), flush=True)
    _verify_source_prepared(source_repo)
    if digest(checked(source_repo, LAB).read_bytes()) != AFTER[LAB]:
        raise ValueError('Readiness contract harness changed during proof')
    proof = expected_proof()
    checked(source_repo, PROOF_STATE, new=True).write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(json.dumps({'stage': 'native-follow-readiness-proof', 'status': 'passed', 'checks': CONTRACT_CHECKS}), flush=True)
    return proof


def verify_contract(source_repo):
    try:
        return _verify_contract(source_repo)
    except _ContractProofFailure:
        raise
    except Exception:
        print(json.dumps({'stage': 'native-follow-readiness-proof', 'status': 'failed',
            'checks': 0, 'failedTestOrdinals': [], 'errorCategory': 'runner'}), flush=True)
        raise ValueError('Readiness deterministic contract runner failed') from None


def verify_units(source_repo):
    """70 prior provenance, 63 final compatible, 46 final precision executions.

    These overlapping layers are not 179 unique tests. Every original discovery
    identity is verified before the seven explicitly mapped superseded cases are
    selected out of the final-compatible layer. The original 70 are still run.
    """
    layer = 'inventory'
    try:
        verify_prepared(source_repo, timing_observation=True)
        import native_seek_anchor_observation as timing
        final = checked(source_repo, LAB).read_bytes()
        if digest(final) != timing.AFTER[LAB]:
            raise ValueError('Final unit harness pin changed')
        prior = restore_follow_precision(patch_harness(checked(source_repo, ORIGINAL_STATE).read_bytes()))
        if digest(prior) != PRECISION_PRIOR_SHA256:
            raise ValueError('Prior unit provenance inverse changed')
        module_path = ROOT / 'native_follow_readiness_payload' / 'legacy_precision_contract.py'
        spec = importlib.util.spec_from_file_location('owned_legacy_precision_contract', module_path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for layer, content, count in (('prior', prior, 70), ('final_compatible', final, 63)):
            result = module.run_layer(checked(source_repo, LAB).parent, content, layer)
            if result['status'] != 'passed' or result['count'] != count:
                print(json.dumps({'stage': 'native-follow-unit-layers', 'status': 'failed',
                    'unitLayer': layer, 'failedCaseOrdinals': result['failedCaseOrdinals'],
                    'errorCategory': result['errorCategory']}), flush=True)
                raise _ContractProofFailure('Fixed Follow unit layer failed')
        layer = 'precision'
        spec = importlib.util.spec_from_file_location('owned_final_precision_contract',
            ROOT / 'native_follow_readiness_payload' / 'precision_contract.py')
        precision = importlib.util.module_from_spec(spec); spec.loader.exec_module(precision)
        if len(precision.TEST_NAMES) != PRECISION_CHECKS or len(set(precision.TEST_NAMES)) != PRECISION_CHECKS:
            raise ValueError('Final precision inventory changed')
        result = unittest.TestResult(); precision.suite(prior, final).run(result)
        if (result.testsRun != PRECISION_CHECKS or result.errors or result.failures
                or result.skipped or result.expectedFailures or result.unexpectedSuccesses):
            print(json.dumps({'stage': 'native-follow-unit-layers', 'status': 'failed', 'unitLayer': layer,
                'failedCaseOrdinals': _failed_contract_ordinals(result, precision.TEST_NAMES),
                'errorCategory': 'runner' if result.errors else 'assertion'}), flush=True)
            raise _ContractProofFailure('Final composed precision cases failed')
        verify_prepared(source_repo, timing_observation=True)
        if checked(source_repo, LAB).read_bytes() != final:
            raise ValueError('Final unit source changed')
        result = {'stage': 'native-follow-unit-layers', 'status': 'passed',
            'priorProvenanceChecks': 70, 'finalCompatibleChecks': 63, 'finalPrecisionChecks': PRECISION_CHECKS}
        print(json.dumps(result), flush=True)
        return result
    except _ContractProofFailure:
        raise
    except Exception:
        print(json.dumps({'stage': 'native-follow-unit-layers', 'status': 'failed',
            'unitLayer': layer, 'failedCaseOrdinals': [], 'errorCategory': 'runner'}), flush=True)
        raise ValueError('Fixed Follow unit layer runner failed') from None


def verify_prepared(source_repo, *, timing_observation=False):
    manifest = _verify_source_prepared(source_repo, timing_observation=timing_observation)
    proof = json.loads(checked(source_repo, PROOF_STATE).read_text())
    if not isinstance(proof, dict) or proof != expected_proof() or type(proof.get('checks')) is not int:
        raise ValueError('Readiness contract proof manifest changed')
    return manifest


def verify_compiled(source_repo, *, timing_observation=False):
    verify_prepared(source_repo, timing_observation=timing_observation)
    manifest = json.loads(checked(source_repo, NATIVE_STATE).read_text())
    if (not isinstance(manifest, dict) or manifest != {'readOnly': True, 'files': NATIVE_HASHES}
            or type(manifest.get('readOnly')) is not bool):
        raise ValueError('Readiness native getter manifest changed')
    expected_native = {name: hashes['after'] for name, hashes in NATIVE_HASHES.items()}
    if timing_observation:
        import native_seek_anchor_observation as timing
        timing.verify_compiled(source_repo)
        expected_native = timing.NATIVE_AFTER
    for name, hashes in NATIVE_HASHES.items():
        if digest(checked(source_repo, NATIVE_PATHS[name]).read_bytes()) != expected_native[name]:
            raise ValueError('Readiness native getter source changed')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('apply', 'proof', 'verify-prepared', 'verify-compiled'))
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--timing-observation', action='store_true')
    args = parser.parse_args()
    if args.timing_observation:
        if args.stage not in ('verify-prepared', 'verify-compiled'):
            parser.error('timing observation is verification-only')
        {'verify-prepared': verify_prepared, 'verify-compiled': verify_compiled}[args.stage](args.repo, timing_observation=True)
    else:
        {'apply': apply, 'proof': verify_contract, 'verify-prepared': verify_prepared, 'verify-compiled': verify_compiled}[args.stage](args.repo)


if __name__ == '__main__': main()
