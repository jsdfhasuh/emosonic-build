"""One pinned native matrix with read-only timing observations; no publishing."""
from contextlib import ExitStack
from functools import partial
import sys
from unittest.mock import patch
import handoff_follow_readiness as base
import native_follow_lifecycle as lifecycle
import native_seek_anchor_observation as timing

PARENT = '4a099e5ecc1aa6e997dd1f776994590e57da774e'
MESSAGE = 'test: observe native seek and anchor timing 20261022'
WORKFLOW = 'handoff-follow-timing.yml'
REQUEST_PATH = 'requests/handoff-follow-timing-20261022.json'
SOURCE_SHA = '1efc826b85c305bd60210aa705444114c1a0d5e2'
SOURCE_REF = 'refs/heads/fix/darwin-position-anchor-20261022'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
REQUEST = dict(base.REQUEST, source_sha=SOURCE_SHA, source_ref=SOURCE_REF,
               server_sha=SERVER_SHA, mode='native-follow-timing-observation', attempt=18, proof_run_id=39745934922)
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
        if category=='source' and stage=='prepare': require_causal_proof()
        source = base.request.p.ROOT / 'source'
        with ExitStack() as stack:
            stack.enter_context(patch.multiple(base, PARENT=PARENT,MESSAGE=MESSAGE,
                WORKFLOW=WORKFLOW,REQUEST_PATH=REQUEST_PATH,REQUEST=REQUEST,
                SOURCE_SHA=SOURCE_SHA,SOURCE_REF=SOURCE_REF,
                OBSERVED_HARNESS_SHA256=timing.AFTER[timing.HARNESS],
                ATTRIBUTION_EXTRA_ARGS=('--lab-debug-observation','--lab-timing-observation')))
            stack.enter_context(patch.object(base.request,'SERVER_SHA',SERVER_SHA))
            stack.enter_context(patch.dict(base.native.RATE_SCHEMA,
                {'nativeTiming': {'authority': timing.SCHEMA, 'follower': timing.SCHEMA}}))
            if category == 'native' and stage in ('unit','attribution','build','handoff','follow'):
                lifecycle.verify_prepared(source,require_harness=stage in ('unit','attribution'),timing_observation=True)
                timing.verify_prepared(source,require_harness=stage in ('unit','attribution'))
                for name in ('verify_prepared','verify_compiled'):
                    stack.enter_context(patch.object(base.readiness,name,
                        partial(getattr(base.readiness,name),timing_observation=True)))
            result = base.main()
            if result == 0 and category == 'native':
                if stage == 'prepare':
                    lifecycle.apply(source)
                    timing.apply(source)
                elif stage in ('build','handoff','follow'):
                    timing.verify_compiled(source)
            return result
    except Exception:
        label = stage if stage in (*NATIVE_STAGES,'fetch','entry') else 'invalid'
        print('ERROR: Fixed native timing stage failed: '+label+'; private details suppressed.',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
