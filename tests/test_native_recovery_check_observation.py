import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_recovery_check_observation as c
import handoff_follow_timing as wrapper


def blob(data): return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class RecoveryAuxiliaryTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, fetched=True):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'; source.mkdir()
            originals = {c.CONTROLLER: b'synthetic controller\n', c.SERVICE: b'synthetic service\n', c.MAIN: c.LOG_OLD + b'synthetic main\n'}
            updates = {name: value + b'synthetic observation\n' for name, value in originals.items()}
            payloads = {name: ('synthetic ' + name + '\n').encode() for name in c.FILES}
            pins = {name: (c.digest(data), len(data), blob(data)) for name, data in payloads.items()}
            for name, data in originals.items():
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            with patch.multiple(c, FILES=pins, BASE={n:c.digest(d) for n,d in originals.items()},
                                AFTER={n:c.digest(d) for n,d in updates.items()},
                                LOGGED_MAIN=c.digest(updates[c.MAIN].replace(c.LOG_OLD,c.LOG_NEW,1))):
                root = c.auxiliary(source)
                if fetched:
                    root.mkdir()
                    for name,data in payloads.items():(root/name).write_bytes(data)
                    (root/'fetch.json').write_text(json.dumps(c.fetch_manifest()))
                yield source,root,originals,updates,payloads

    def invoker(self, updates, events=None):
        def invoke(root,args,env):
            if events is not None:events.append(args[0])
            flags=dict(zip(args[1::2],args[2::2]))
            if args[0]=='apply':
                Path(flags['--output']).write_bytes(updates[c.CONTROLLER])
                Path(flags['--service-output']).write_bytes(updates[c.SERVICE])
                Path(flags['--main-output']).write_bytes(updates[c.MAIN])
                Path(flags['--manifest']).write_text(json.dumps(c.fingerprints()))
            else:
                self.assertEqual(Path(flags['--input']).read_bytes(),updates[c.CONTROLLER])
                self.assertEqual(Path(flags['--service-input']).read_bytes(),updates[c.SERVICE])
                self.assertEqual(Path(flags['--main-input']).read_bytes(),updates[c.MAIN])
            return c.fingerprints()
        return invoke

    def test_exact_fixed_auxiliary_contract(self):
        self.assertEqual(c.AUX_SHA,'7fa511fc73dfe3d91543965c189965105630c6fd')
        self.assertEqual(c.AUX_TREE,'6998a607d80f7c1885d04cc1b958e8e5227b17b6')
        self.assertEqual(c.SOURCE_SHA,wrapper.SOURCE_SHA)
        self.assertEqual(set(c.FILES),{'transform.py','schema.json','play_policy_schema.json','admission_schema.json','README.md','test_transform.py'})
        self.assertEqual(c.FILES['schema.json'][0], '530496ee1d92ce2238ec7fc8769633bcb41aae36c4008920d63c7b026a0bf808')
        self.assertEqual(wrapper.REQUEST['auxiliary_observer_sha'],c.AUX_SHA)
        self.assertEqual(wrapper.REQUEST['auxiliary_observer_ref'],c.AUX_REF)
        self.assertEqual(wrapper.REQUEST['attempt'],110)
        self.assertEqual(wrapper.INGRESS_RUN,40051389321)

    def test_exact_three_file_manifest_and_policy_bounds(self):
        value=c.fingerprints()
        self.assertEqual(set(c.BASE),{c.CONTROLLER,c.SERVICE,c.MAIN})
        self.assertEqual(set(c.AFTER),set(c.BASE))
        self.assertEqual(value['schemaVersion'],2)
        self.assertEqual((value['controllerOperationCount'],value['serviceOperationCount'],value['labMainOperationCount']),(41,20,3))
        self.assertEqual((value['recordLimit'],value['policyRecordLimit'],value['policyTruncationRecordLimit']),(128,32,1))
        self.assertEqual((value['admissionSummaryLimit'],value['admissionAttemptCountLimit']),(4,5))
        admission=Path(__file__).resolve().parent/'fixtures/recovery_admission_schema.json'
        self.assertEqual(c.digest(admission.read_bytes()),c.FILES['admission_schema.json'][0])
        contract=Path(__file__).resolve().parent/'fixtures/play_policy_schema.json'
        self.assertEqual(c.digest(contract.read_bytes()),c.FILES['play_policy_schema.json'][0])
        for key,path in (('controller',c.CONTROLLER),('audioService',c.SERVICE),('labMain',c.MAIN)):
            self.assertEqual(value[key],dict(baseSha256=c.BASE[path],overlaySha256=c.AFTER[path],
                inverseSha256=c.BASE[path],inverseByteIdentical=True))

    def test_each_composed_source_tamper_is_rejected_without_mutation(self):
        for relative in (c.CONTROLLER,c.SERVICE,c.MAIN):
            with self.subTest(source=relative),self.fixture() as (source,root,originals,updates,_),patch.object(c,'invoke',side_effect=self.invoker(updates)):
                c.apply_after_pristine(source,c.SOURCE_SHA,{},lambda *a:('synthetic',set(originals)))
                main=source/c.MAIN;main.write_bytes(updates[c.MAIN].replace(c.LOG_OLD,c.LOG_NEW,1))
                c.verify(source)
                target=source/relative;target.write_bytes(target.read_bytes()+b'changed')
                before={name:(source/name).read_bytes() for name in originals}
                with self.assertRaises(ValueError):c.verify(source)
                self.assertEqual(before,{name:(source/name).read_bytes() for name in originals})

    def test_package_requires_exact_hash_size_blob_and_no_extra_files(self):
        for change in ('content','extra','missing','manifest','symlink'):
            with self.subTest(change=change),self.fixture() as (source,root,*_):
                c.package(source)
                if change=='content':(root/'transform.py').write_bytes(b'other')
                elif change=='extra':(root/'other.py').write_bytes(b'other')
                elif change=='missing':(root/'schema.json').unlink()
                elif change=='manifest':(root/'fetch.json').write_text('{}')
                else:
                    (root/'README.md').unlink();(root/'README.md').symlink_to(root/'schema.json')
                with self.assertRaises(ValueError):c.package(source)

    def test_owned_paths_refuse_traversal_absolute_symlinks_and_wrong_source_root(self):
        with self.fixture() as (source,root,*_):
            for name in ('../outside','/absolute','.git/config'):
                with self.subTest(name=name),self.assertRaises(ValueError):c.owned(root,name)
            with self.assertRaises(ValueError):c.auxiliary(root)
            link=root/'link';link.symlink_to(source)
            with self.assertRaises(ValueError):c.owned(root,'link/file',new=True)

    def test_strict_json_rejects_duplicate_nonfinite_and_type_aliases(self):
        for raw in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):c.strict_json(raw)
        with self.assertRaises(ValueError):c.exact({'x':1},{'x':True})
        with self.assertRaises(ValueError):c.exact({'x':1,'other':0},{'x':1})

    def fetch_api(self,source,payloads,mutate=None):
        seen=[]
        def quiet(args,cwd,env):
            seen.append((args,dict(env)));self.assertEqual(cwd,source)
            if args[1]=='ls-remote':return c.AUX_SHA+'\t'+c.AUX_REF+'\n' if mutate!='ref' else '0'*40+'\t'+c.AUX_REF+'\n'
            if args[1]=='fetch':return ''
            if args[1]=='rev-parse':return (c.SOURCE_SHA if args[2]=='HEAD' else c.AUX_TREE)+'\n'
            if args[1]=='cat-file':return 'tree '+c.AUX_TREE+'\nparent '+('0'*40 if mutate=='parent' else c.SOURCE_SHA)+'\n\nsynthetic\n'
            if args[1]=='diff-tree':return ''.join('A\t'+c.PREFIX+n+'\n' for n in c.FILES)+('M\tlib/unreviewed.dart\n' if mutate=='delta' else '')
            if args[1]=='ls-tree':return ''.join('100644 blob '+v[2]+'\t'+c.PREFIX+n+'\0' for n,v in c.FILES.items())+('120000 blob '+'0'*40+'\t'+c.PREFIX+'other\0' if mutate=='path' else '')
            if args[1]=='show':
                name=args[2].split('/')[-1];return 'changed' if mutate=='bytes' else payloads[name].decode()
            self.fail('unexpected command')
        return SimpleNamespace(SOURCE='owner/private',quiet=quiet,require_secrets=Mock()),seen

    def test_fetch_exact_parent_tree_allowlist_and_subprocess_only_credentials(self):
        with self.fixture(False) as (source,root,_,__,payloads),patch.dict(c.os.environ,{'SOURCE_READ_TOKEN':'SYNTHETIC_TOKEN'},clear=True):
            p,seen=self.fetch_api(source,payloads);c.fetch(source,p);c.package(source)
            self.assertEqual(len(list(root.iterdir())),7)
            for args,env in seen:
                self.assertNotIn('SYNTHETIC_TOKEN',' '.join(args));self.assertNotIn('SOURCE_READ_TOKEN',env)
                self.assertEqual('GIT_CONFIG_VALUE_0' in env,args[1] in ('ls-remote','fetch'))
            self.assertFalse(any('checkout' in args or 'reset' in args for args,env in seen))

    def test_fetch_refuses_changed_ref_parent_delta_path_and_bytes(self):
        for change in ('ref','parent','delta','path','bytes'):
            with self.subTest(change=change),self.fixture(False) as (source,root,_,__,payloads),patch.dict(c.os.environ,{'SOURCE_READ_TOKEN':'SYNTHETIC'},clear=True):
                p,_=self.fetch_api(source,payloads,change)
                with self.assertRaises(ValueError):c.fetch(source,p)
                self.assertFalse(root.exists())

    def test_apply_checks_pristine_twice_then_exact_inverse_without_mutating_inputs_early(self):
        with self.fixture() as (source,root,originals,updates,_):
            events=[]
            def fingerprint(*args):
                events.append('fingerprint')
                self.assertTrue(all((source/n).read_bytes()==v for n,v in originals.items()))
                return ('synthetic',set(originals))
            with patch.object(c,'invoke',side_effect=self.invoker(updates,events)):
                self.assertEqual(c.apply_after_pristine(source,c.SOURCE_SHA,{},fingerprint),('synthetic',set(originals)))
            self.assertEqual(events,['fingerprint','apply','fingerprint','check-inverse'])
            self.assertTrue(all((source/n).read_bytes()==v for n,v in updates.items()))
            self.assertEqual(set(p.name for p in root.parent.iterdir()),{'source',c.STATE})

    def test_apply_failure_never_admits_outputs_or_applied_manifest(self):
        with self.fixture() as (source,root,originals,updates,_),patch.object(c,'invoke',side_effect=ValueError('synthetic')):
            with self.assertRaises(ValueError):c.apply_after_pristine(source,c.SOURCE_SHA,{},lambda *a:('synthetic',set(originals)))
            self.assertTrue(all((source/n).read_bytes()==v for n,v in originals.items()))
            self.assertFalse((root/'applied.json').exists())

    def test_composed_inverse_uses_scratch_and_rejects_tampering(self):
        with self.fixture() as (source,root,originals,updates,_),patch.object(c,'invoke',side_effect=self.invoker(updates)):
            c.apply_after_pristine(source,c.SOURCE_SHA,{},lambda *a:('synthetic',set(originals)))
            main=source/c.MAIN;main.write_bytes(updates[c.MAIN].replace(c.LOG_OLD,c.LOG_NEW,1));before=main.read_bytes()
            c.verify(source);self.assertEqual(main.read_bytes(),before)
            main.write_bytes(before+b'changed')
            with self.assertRaises(ValueError):c.verify(source)

    def test_private_cli_rejects_failure_stderr_extra_fields_and_secret_env(self):
        good=json.dumps(c.fingerprints()).encode()
        for result in (SimpleNamespace(returncode=1,stdout=good,stderr=b''),SimpleNamespace(returncode=0,stdout=good,stderr=b'private'),SimpleNamespace(returncode=0,stdout=good[:-1]+b',"extra":1}',stderr=b'')):
            with patch.object(c.subprocess,'run',return_value=result),self.assertRaises(ValueError):c.invoke(Path('/synthetic'),[],{})
        with patch.object(c.subprocess,'run') as run,self.assertRaises(ValueError):c.invoke(Path('/synthetic'),[],{'SOURCE_READ_TOKEN':'synthetic'})
        run.assert_not_called()

    def test_lifecycle_scope_restores_even_after_exception_and_cleanup_is_owned(self):
        module=SimpleNamespace(MAIN_BEFORE_SHA256='old',MAIN_AFTER_SHA256='after')
        with self.assertRaises(RuntimeError),c.lifecycle_pins(module):
            self.assertEqual(module.MAIN_BEFORE_SHA256,c.AFTER[c.MAIN]);raise RuntimeError('synthetic')
        self.assertEqual((module.MAIN_BEFORE_SHA256,module.MAIN_AFTER_SHA256),('old','after'))
        with self.fixture() as (source,root,*_):
            c.cleanup(source);self.assertFalse(root.exists());self.assertTrue(source.exists())

    def test_wrapper_fetch_after_success_and_cleanup_even_after_exception(self):
        with patch.object(sys,'argv',['gate','source','fetch']),patch.object(wrapper.base,'main',return_value=0),patch.object(c,'fetch') as fetch:
            self.assertEqual(wrapper.main(),0);fetch.assert_called_once()
        with patch.object(sys,'argv',['gate','source','cleanup']),patch.object(wrapper.base,'main',side_effect=RuntimeError('synthetic')),patch.object(c,'cleanup') as cleanup:
            self.assertEqual(wrapper.main(),1);cleanup.assert_called_once()

    def test_prepare_hook_is_once_and_restores_fingerprint_without_double_decorations(self):
        original=wrapper.base.request.p.source_fingerprint
        calls=[]
        def run():
            wrapper.base.request.p.source_fingerprint(Path('source'),c.SOURCE_SHA,{})
            return 0
        with patch.object(sys,'argv',['gate','native','prepare']),patch.object(wrapper.base,'main',side_effect=run),patch.object(c,'apply_after_pristine',side_effect=lambda *a,**k:calls.append(('private',k['original_fingerprint']))),patch.object(wrapper.lifecycle,'apply',side_effect=lambda *a:calls.append(('lifecycle',None))),patch.object(wrapper.timing,'apply',side_effect=lambda *a:calls.append(('timing',None))),patch.object(c,'verify'):
            self.assertEqual(wrapper.main(),0)
        self.assertEqual([row[0] for row in calls],['private','lifecycle','timing'])
        self.assertIs(calls[0][1],original)
        self.assertIs(wrapper.base.request.p.source_fingerprint,original)

    def test_attribution_recovery_optin_preserves_default_and_restores_hashes(self):
        path=Path(__file__).resolve().parents[1]/'scripts/native_attribution/lab_stream_attribution.py'
        spec=importlib.util.spec_from_file_location('synthetic_attribution_recovery',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        old=dict(module.BASELINE_HASHES);helper=SimpleNamespace(verify=Mock(),LOGGED_MAIN=c.LOGGED_MAIN)
        with patch.object(module,'RECOVERY_HELPER',helper):
            with self.assertRaises(ValueError):
                with module.lab_debug_observation(Path('synthetic'),enabled=False):pass
            with self.assertRaises(RuntimeError):
                with module.lab_debug_observation(Path('synthetic'),enabled=True):
                    self.assertEqual(module.BASELINE_HASHES[module.LAB_MAIN],c.LOGGED_MAIN);raise RuntimeError('synthetic')
        self.assertEqual(module.BASELINE_HASHES,old);helper.verify.assert_called_once()


if __name__=='__main__':unittest.main()
