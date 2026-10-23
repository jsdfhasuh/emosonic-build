"""One pinned native matrix with read-only timing observations; no publishing."""
from contextlib import ExitStack
from functools import partial
import sys
from unittest.mock import patch
import handoff_follow_readiness as base
import native_follow_lifecycle as lifecycle
import native_seek_anchor_observation as timing
import native_recovery_check_observation as recovery_observation

PARENT = 'fdb853174dc19b4a52012a4959c1f9ab2afb9994'
MESSAGE = 'test: measure bounded recovery admission 20261023'
WORKFLOW = 'handoff-follow-timing.yml'
REQUEST_PATH = 'requests/handoff-follow-timing-20261022.json'
SOURCE_SHA = 'f6251a2a0e6441f174d05b488bc0fb1b41d52e39'
SOURCE_REF = 'refs/heads/fix/follow-initial-apply-flow-lint-20261023'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
REQUEST = dict(base.REQUEST, source_sha=SOURCE_SHA, source_ref=SOURCE_REF,
               server_sha=SERVER_SHA, mode='native-follow-timing-observation', attempt=101, proof_run_id=39745934922, validation_run_id=39767536382, ingress_validation_run_id=39966140487,
               auxiliary_observer_sha=recovery_observation.AUX_SHA, auxiliary_observer_ref=recovery_observation.AUX_REF)
NATIVE_STAGES = ('prepare','dependencies','unit','preflight','attribution','build','handoff','follow','cleanup')


def require_causal_proof():
    p=base.request.p
    run=p.api('/repos/jsdfhasuh/emosonic-build/actions/runs/39745934922')
    p.require(type(run) is dict and run.get('id')==39745934922
              and run.get('head_sha')=='4a099e5ecc1aa6e997dd1f776994590e57da774e'
              and run.get('path')=='.github/workflows/follow-seek-latency-proof.yml'
              and run.get('event')=='push' and run.get('head_branch')=='main'
              and run.get('status')=='completed' and run.get('conclusion')=='success',
              'Exact causal proof must pass before native timing observation.')
    jobs=p.api('/repos/jsdfhasuh/emosonic-build/actions/runs/39745934922/jobs?per_page=100')
    p.require(type(jobs) is dict and type(jobs.get('jobs')) is list,'Causal jobs unavailable.')
    matches=[j for j in jobs['jobs'] if type(j) is dict and j.get('name')=='red-baseline']
    p.require(len(matches)==1 and matches[0].get('run_id')==39745934922
              and matches[0].get('head_sha')=='4a099e5ecc1aa6e997dd1f776994590e57da774e'
              and matches[0].get('status')=='completed' and matches[0].get('conclusion')=='success','Causal job must pass.')
    steps=matches[0].get('steps',[])
    for name in ('Require exact real-controller held-seek feedback regression','Remove private baseline and generated diagnostics'):
        found=[s for s in steps if type(s) is dict and s.get('name')==name]
        p.require(len(found)==1 and found[0].get('conclusion')=='success','Causal proof and cleanup must succeed.')



VALIDATION_RUN = 39767536382
VALIDATION_HEAD = 'e3b181c40054f9cc4892deeb6f2eadd308920f1d'
VALIDATION_STEPS = {
    'validate-source': (
        'Validate exact recovery, provenance and original regression inventories',
        'Validate complete source analysis, tests, provenance and byte integrity without user Secrets',
        'Remove private source and generated validation outputs',
    ),
    'observer-bool-proof': (
        'Prove exact Foundation BOOL serialization and strict mismatch rejection',
    ),
}


def require_recovery_validation():
    p=base.request.p
    endpoint=f'/repos/jsdfhasuh/emosonic-build/actions/runs/{VALIDATION_RUN}'
    run=p.api(endpoint)
    p.require(type(run) is dict and type(run.get('id')) is int and run['id']==VALIDATION_RUN
              and run.get('head_sha')==VALIDATION_HEAD
              and run.get('path')=='.github/workflows/follow-recovery-check.yml'
              and run.get('event')=='push' and run.get('head_branch')=='main'
              and type(run.get('run_attempt')) is int and run['run_attempt']==1
              and run.get('status')=='completed' and run.get('conclusion')=='success',
              'Exact recovery validation must complete successfully before native testing.')
    jobs=p.api(endpoint+'/jobs?per_page=100')
    p.require(type(jobs) is dict and type(jobs.get('jobs')) is list
              and type(jobs.get('total_count')) is int
              and jobs['total_count']==len(jobs['jobs'])<=100,
              'Complete recovery validation jobs unavailable.')
    for job_name, names in VALIDATION_STEPS.items():
        matches=[j for j in jobs['jobs'] if type(j) is dict and j.get('name')==job_name]
        p.require(len(matches)==1, 'Exact recovery validation job missing or duplicated.')
        job=matches[0]
        p.require(job.get('run_id')==VALIDATION_RUN and job.get('head_sha')==VALIDATION_HEAD
                  and job.get('status')=='completed' and job.get('conclusion')=='success'
                  and type(job.get('steps')) is list, 'Recovery validation job must succeed.')
        for name in names:
            steps=[s for s in job['steps'] if type(s) is dict and s.get('name')==name]
            p.require(len(steps)==1 and steps[0].get('status')=='completed'
                      and steps[0].get('conclusion')=='success',
                      'Recovery tests, full validation, BOOL proof and cleanup must succeed.')


INGRESS_RUN = 39966140487
INGRESS_HEAD = 'd03a90db5341ceed03eb2d200eae0b270804f0fc'
INGRESS_STEPS = {'validate-source': (
    'Validate all prior and initial apply receipt focused cases',
    'Validate complete source analysis, tests, provenance and byte integrity without user Secrets',
    'Remove private source and generated validation outputs',
)}


def require_ingress_validation():
    p=base.request.p
    endpoint=f'/repos/jsdfhasuh/emosonic-build/actions/runs/{INGRESS_RUN}'
    run=p.api(endpoint)
    p.require(type(run) is dict and type(run.get('id')) is int and run['id']==INGRESS_RUN
              and run.get('head_sha')==INGRESS_HEAD
              and run.get('path')=='.github/workflows/initial-apply-receipt-green.yml'
              and run.get('event')=='push' and run.get('head_branch')=='main'
              and type(run.get('run_attempt')) is int and run['run_attempt']==1
              and run.get('status')=='completed' and run.get('conclusion')=='success',
              'Exact ingress validation must complete successfully before native testing.')
    jobs=p.api(endpoint+'/jobs?per_page=100')
    p.require(type(jobs) is dict and type(jobs.get('jobs')) is list
              and type(jobs.get('total_count')) is int
              and jobs['total_count']==len(jobs['jobs'])<=100,
              'Complete ingress validation jobs unavailable.')
    for job_name, names in INGRESS_STEPS.items():
        matches=[j for j in jobs['jobs'] if type(j) is dict and j.get('name')==job_name]
        p.require(len(matches)==1, 'Exact ingress validation job missing or duplicated.')
        job=matches[0]
        p.require(job.get('run_id')==INGRESS_RUN and job.get('head_sha')==INGRESS_HEAD
                  and job.get('status')=='completed' and job.get('conclusion')=='success'
                  and type(job.get('steps')) is list, 'Ingress validation job must succeed.')
        for name in names:
            steps=[s for s in job['steps'] if type(s) is dict and s.get('name')==name]
            p.require(len(steps)==1 and steps[0].get('status')=='completed'
                      and steps[0].get('conclusion')=='success',
                      'Ingress tests, full validation and cleanup must succeed.')


def main():
    stage = 'entry'
    try:
        if len(sys.argv) != 3:
            raise ValueError('Invalid fixed timing validation stage')
        category, stage = sys.argv[1:]
        if category == 'source':
            if stage not in ('prepare','fetch','cleanup'):
                raise ValueError('Package and publishing stages forbidden')
        elif category != 'native' or stage not in NATIVE_STAGES:
            raise ValueError('Unknown native timing validation stage')
        if category=='source' and stage=='prepare':
            require_causal_proof()
            require_recovery_validation()
            require_ingress_validation()
        source = base.request.p.ROOT / 'source'
        with ExitStack() as stack:
            stack.enter_context(patch.multiple(base, PARENT=PARENT,MESSAGE=MESSAGE,
                WORKFLOW=WORKFLOW,REQUEST_PATH=REQUEST_PATH,REQUEST=REQUEST,
                SOURCE_SHA=SOURCE_SHA,SOURCE_REF=SOURCE_REF,
                OBSERVED_HARNESS_SHA256=timing.AFTER[timing.HARNESS],
                ATTRIBUTION_EXTRA_ARGS=('--lab-debug-observation','--lab-timing-observation','--lab-recovery-observation')))
            stack.enter_context(patch.object(base.request,'SERVER_SHA',SERVER_SHA))
            stack.enter_context(patch.dict(base.native.RATE_SCHEMA,
                {'nativeTiming': {'authority': timing.SCHEMA, 'follower': timing.SCHEMA}}))
            if category == 'native' and stage != 'cleanup':
                stack.enter_context(recovery_observation.lifecycle_pins(lifecycle))
                if stage == 'prepare':
                    original_fingerprint = base.request.p.source_fingerprint
                    stack.enter_context(patch.object(base.request.p, 'source_fingerprint',
                        partial(recovery_observation.apply_after_pristine, original_fingerprint=original_fingerprint)))
                else:
                    recovery_observation.verify(source)
            if category == 'native' and stage in ('unit','attribution','build','handoff','follow'):
                lifecycle.verify_prepared(source,require_harness=stage in ('unit','attribution'),timing_observation=True)
                timing.verify_prepared(source,require_harness=stage in ('unit','attribution'))
                for name in ('verify_prepared','verify_compiled'):
                    stack.enter_context(patch.object(base.readiness,name,
                        partial(getattr(base.readiness,name),timing_observation=True)))
            unit_invocations = 0
            if category == 'native' and stage == 'unit':
                def fixed_unit_execute(command, label, report=False):
                    nonlocal unit_invocations
                    expected = [sys.executable, '-m', 'unittest', 'discover', '-s',
                                'tool/native_playback_mac', '-p', 'test_*.py']
                    base.request.p.require(type(command) is list and command == expected
                        and all(type(value) is str for value in command)
                        and type(label) is str and label == 'native-measurement-guards'
                        and report is False and unit_invocations == 0,
                        'Unexpected fixed native unit invocation.')
                    unit_invocations += 1
                    with patch.dict(base.native.os.environ, base.native.native_env(), clear=True):
                        result = base.readiness.verify_units(source)
                    expected_result = {'stage': 'native-follow-unit-layers', 'status': 'passed',
                        'priorProvenanceChecks': 70, 'finalCompatibleChecks': 63, 'finalPrecisionChecks': 40}
                    base.request.p.require(type(result) is dict and result == expected_result
                        and all(type(result[key]) is type(value) for key, value in expected_result.items()),
                        'Exact native unit layers must all pass.')
                stack.enter_context(patch.object(base.native, 'execute', fixed_unit_execute))
            if category == 'source' and stage == 'cleanup':
                try:
                    return base.main()
                finally:
                    recovery_observation.cleanup(source)
            result = base.main()
            if result == 0 and category == 'native' and stage == 'unit':
                base.request.p.require(unit_invocations == 1, 'Fixed native unit invocation missing.')
            if result == 0 and category == 'source' and stage == 'fetch':
                recovery_observation.fetch(source, base.request.p)
            if result == 0 and category == 'native':
                if stage == 'prepare':
                    lifecycle.apply(source)
                    timing.apply(source)
                    recovery_observation.verify(source)
                elif stage in ('build','handoff','follow'):
                    timing.verify_compiled(source)
            return result
    except Exception:
        label = stage if stage in (*NATIVE_STAGES,'fetch','entry') else 'invalid'
        print('ERROR: Fixed native timing stage failed: '+label+'; private details suppressed.',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
