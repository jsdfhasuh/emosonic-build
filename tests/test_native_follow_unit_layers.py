"""Synthetic runner checks, never private case names or fixture source."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_follow_readiness as r
import current_native_check as public
spec=importlib.util.spec_from_file_location('public_legacy_units',r.ROOT/'native_follow_readiness_payload/legacy_precision_contract.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

class Case:
    def __init__(self,name):self.name=name
    def id(self):return self.name

class UnitLayersTests(unittest.TestCase):
    def synthetic(self):
        contract=copy.deepcopy(u.inventory());cases=[Case('synthetic.case.%02d'%i) for i in range(70)]
        for row,case in zip(contract['cases'],cases):row['caseSha256']=u.digest(case.id().encode())
        return contract,cases

    def test_exact_discovery_precedes_selection_and_no_unrelated_drop(self):
        contract,cases=self.synthetic()
        self.assertEqual(len(u.select_exact(cases,contract,'prior')),70)
        self.assertEqual(len(u.select_exact(cases,contract,'final_compatible')),63)
        for changed in (cases[:-1],cases+[Case('unrelated')],[Case('changed')]+cases[1:],cases[:-1]+[cases[0]]):
            with self.assertRaises(AssertionError):u.select_exact(changed,contract,'final_compatible')

    def test_all_seven_superseded_cases_have_actual_final_mapping(self):
        c=u.inventory();rows=[x for x in c['cases'] if 'finalPrecisionOrdinals' in x]
        self.assertEqual(len(rows),7)
        self.assertTrue(all(all(type(n) is int and 1<=n<=35 for n in x['finalPrecisionOrdinals']) for x in rows))
        encoded=json.dumps(c);self.assertNotIn('privateCase',encoded)
        self.assertEqual(sum(x['classification']=='metadata_only_final' for x in c['cases']),9)

    def test_exact_file_inventory_includes_all_recursive_test_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'unexpected').mkdir();(root/'unexpected/test_extra.py').write_text('')
            with self.assertRaises(AssertionError):u.run_layer(root,b'', 'prior')

    def test_subprocess_environment_is_stripped_and_temp_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=b'synthetic';(root/'test_synthetic.py').write_bytes(data)
            contract={'testFiles':{'test_synthetic.py':u.digest(data)}}
            result={'status':'passed','count':63,'failedCaseOrdinals':[],'errorCategory':'assertion'}
            calls=[]
            def run(argv,**options):
                calls.append(options)
                self.assertTrue(Path(options['cwd']).is_dir())
                self.assertEqual(options['env']['TMPDIR'],str(options['cwd']))
                self.assertEqual(argv[1],'-B');self.assertEqual(options['timeout'],60)
                for key in ('GITHUB_ENV','GITHUB_OUTPUT','GITHUB_PATH','GITHUB_STEP_SUMMARY','PYTHONPATH','PYTHONHOME'):
                    self.assertNotIn(key,options['env'])
                return SimpleNamespace(returncode=0,stdout=json.dumps(result).encode(),stderr=b'')
            with patch.object(u,'inventory',return_value=contract),patch.object(u,'DEPENDENCIES',()),patch.object(u.subprocess,'run',run),patch.dict(u.os.environ,{'GITHUB_ENV':'private','PYTHONPATH':'private'}):
                self.assertEqual(u.run_layer(root,b'harness','final_compatible'),result)
            self.assertFalse(Path(calls[0]['cwd']).exists())

    def test_no_skip_or_expected_failure_is_success(self):
        source=Path(u.__file__).read_text()
        for field in ('result.skipped','result.expectedFailures','result.unexpectedSuccesses'):
            self.assertIn(field,source)
        self.assertIn('result.testsRun==len(selected)',source)

    def test_finite_layer_summary_and_invalid_ordinals(self):
        sample={'stage':'native-follow-unit-layers','status':'passed','priorProvenanceChecks':70,'finalCompatibleChecks':63,'finalPrecisionChecks':35}
        self.assertEqual(public.report_line(json.dumps(sample)),sample)
        sample={'stage':'native-follow-unit-layers','status':'failed','unitLayer':'prior','failedCaseOrdinals':[1,70],'errorCategory':'assertion'}
        self.assertEqual(public.report_line(json.dumps(sample)),sample)
        sample.update(unitLayer='private',failedCaseOrdinals=[0,71],privateCase='secret')
        result=public.report_line(json.dumps(sample));self.assertNotIn('unitLayer',result);self.assertNotIn('privateCase',result);self.assertEqual(result.get('failedCaseOrdinals',[]),[])

if __name__=='__main__':unittest.main()
