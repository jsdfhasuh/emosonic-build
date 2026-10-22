import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_native_diagnostic as d


class DiagnosticTests(unittest.TestCase):
    def test_package_and_release_forbidden(self):
        for stage in ('build', 'build_windows', 'verify', 'publish', 'validate_source'):
            with patch.object(sys, 'argv', ['diagnostic', 'source', stage]), patch.object(d.request, 'main') as call:
                self.assertEqual(d.main(), 1)
                call.assert_not_called()

    def test_scoped_native_override_restored(self):
        before = d.request.PARENT, d.request.WORKFLOW, d.request.REQUEST
        def check():
            self.assertEqual(d.request.PARENT, d.PARENT)
            self.assertEqual(d.request.WORKFLOW, d.WORKFLOW)
            self.assertEqual(d.request.REQUEST['mode'], 'native-diagnostic-only')
            self.assertEqual(sys.argv[1:], ['handoff'])
            return 0
        with patch.object(sys, 'argv', ['diagnostic', 'native', 'handoff']), patch.object(d.native, 'main', side_effect=check):
            self.assertEqual(d.main(), 0)
        self.assertEqual((d.request.PARENT, d.request.WORKFLOW, d.request.REQUEST), before)

    def test_exact_context_and_wrong_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'requests').mkdir()
            (root/d.REQUEST_PATH).write_text(json.dumps(d.REQUEST))
            sha='a'*40
            event={'before':d.PARENT,'after':sha,'ref':'refs/heads/main','forced':False,'deleted':False,'created':False,'head_commit':{'id':sha,'message':d.MESSAGE}}
            path=root/'event.json'; path.write_text(json.dumps(event))
            env={'GITHUB_REPOSITORY':d.request.p.BUILDER,'GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'push','GITHUB_WORKFLOW_REF':d.request.p.BUILDER+'/.github/workflows/'+d.WORKFLOW+'@refs/heads/main','GITHUB_SHA':sha,'GITHUB_RUN_ID':'2','GITHUB_RUN_ATTEMPT':'1','GITHUB_EVENT_PATH':str(path),'SOURCE_SHA':d.request.SOURCE_SHA,'BUILD_VERSION':d.request.VERSION}
            with patch.dict(os.environ,env,clear=True), patch.object(d.request.p,'ROOT',root), patch.object(d.request,'prepare') as prepare, patch.object(sys,'argv',['diagnostic','source','prepare']):
                self.assertEqual(d.main(),0); prepare.assert_called_once()
                event['before']='b'*40; path.write_text(json.dumps(event))
                self.assertEqual(d.main(),1)
