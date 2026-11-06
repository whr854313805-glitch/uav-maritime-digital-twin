"""Result/catalog lifecycle tests use copied fixtures, never published originals."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, Mock
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import src.anylogic_workspace as aw
import src.workspace_catalog as wc
from src.ais_replay import replace_json

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CatalogLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.original=read(ROOT/'output/ais_single_task/latest.json')
        names={'config.yaml','config/ais-single-task.json','runtime/data/current-data.manifest.json',
               'anylogic/workbench/workspace.json','anylogic/workbench/provenance.json',
               'anylogic/harbour_background.png','output/ais_single_task/latest.json',
               'output/ais_single_task/ompl_sst/catalog.json','output/research_points/study/study.json'}
        names.update('output/research_points/study/M'+str(n)+'/selection.json' for n in range(1,5))
        for item in aw.catalog():
            names.add('output/'+item['file'])
            if item.get('baseline_file'):names.add('output/'+item['baseline_file'])
        capture='data/ais/captures/'+self.original['capture_id']+'/'
        names.update(capture+name for name in ['capture.json','messages.jsonl'])
        for name in names:
            target=self.root/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,target)
        self.changed=deepcopy(self.original)
        self.changed['run_id']='lifecycle-fixture-new-run'

    def paths(self):
        return [self.root/name for name in ['output/ais_single_task/latest.json',
                'anylogic/workbench/workspace.json','anylogic/workbench/provenance.json']]

    def assert_synced(self, expected):
        workspace=read(self.paths()[1])
        current=next(x for x in workspace['catalog'] if x['key']=='current')
        self.assertEqual(read(self.paths()[0])['run_id'],expected['run_id'])
        self.assertEqual(current['sha256'],sha(self.paths()[0]))
        self.assertEqual(current['request'],expected['request'])
        self.assertEqual(read(self.paths()[2])['workspace_sha256'],sha(self.paths()[1]))

    def test_repeated_publication_keeps_catalog_and_provenance_current(self):
        immutable=deepcopy(read(self.paths()[1]));immutable.pop('catalog')
        for index in range(3):
            self.changed['run_id']='fixture-run-'+str(index)
            wc.publish_result(self.root,self.changed)
            self.assert_synced(self.changed)
        after=read(self.paths()[1]);after.pop('catalog')
        self.assertEqual(immutable,after)

    def test_noop_sync_does_not_rewrite_files(self):
        before=[(p.read_bytes(),p.stat().st_mtime_ns) for p in self.paths()]
        wc.synchronize(self.root);wc.synchronize(self.root)
        self.assertEqual(before,[(p.read_bytes(),p.stat().st_mtime_ns) for p in self.paths()])

    def test_external_valid_latest_is_reconciled_without_reverting_it(self):
        replace_json(self.paths()[0],self.changed)
        body=self.paths()[0].read_bytes()
        wc.synchronize(self.root)
        self.assert_synced(self.changed)
        self.assertEqual(body,self.paths()[0].read_bytes())

    def test_invalid_success_source_projection_or_request_cannot_replace_default(self):
        for name in ['success','source','projection','request']:
            bad=deepcopy(self.changed)
            if name=='success':bad['ship_check']['valid']=False
            elif name=='source':bad['raw_sha256']='0'*64
            elif name=='projection':bad['projection']['origin_lat']+=1
            else:bad['request']['speed_mps']=True
            before=[p.read_bytes() for p in self.paths()]
            with self.subTest(name=name),self.assertRaises(ValueError):wc.publish_result(self.root,bad)
            self.assertEqual(before,[p.read_bytes() for p in self.paths()])

    def test_unknown_source_error_cannot_become_default(self):
        error=deepcopy(self.changed)
        error.update(status='error',trajectory=None,ship_check=None,capture_id=None,raw_sha256=None)
        before=[p.read_bytes() for p in self.paths()]
        with self.assertRaises(ValueError):wc.publish_result(self.root,error)
        self.assertEqual(before,[p.read_bytes() for p in self.paths()])

    def test_source_verified_failure_without_planned_only_fields_is_displayable(self):
        error=deepcopy(self.changed)
        error.update(status='error',trajectory=None,ship_check=None,failure_reason='fixture budget exhausted')
        error.pop('projection',None);error.pop('window_start_unix_s',None)
        wc.publish_result(self.root,error)
        self.assert_synced(error)
        wc.validate_current(self.root,error,reference=self.original)
        with patch.object(aw,'P',self.root):view=aw.packet('current',self.root/'.local/test-packet')
        self.assertEqual(view['status'],'error');self.assertIsNone(view['trajectory'])

    def test_bad_display_geometry_is_not_silently_repaired(self):
        workspace=read(self.paths()[1]);workspace['sites'][0]['xy'][0]+=1000
        replace_json(self.paths()[1],workspace)
        before=[p.read_bytes() for p in self.paths()]
        with self.assertRaisesRegex(ValueError,'sites'):wc.synchronize(self.root)
        self.assertEqual(before,[p.read_bytes() for p in self.paths()])

    def test_frozen_catalog_tamper_is_not_silently_repaired(self):
        workspace=read(self.paths()[1]);workspace['catalog'][0]['request']['speed_mps']=999
        replace_json(self.paths()[1],workspace)
        with self.assertRaisesRegex(ValueError,'Frozen saved catalog'):wc.synchronize(self.root)

    def test_interrupted_workspace_write_recovers_from_valid_published_result(self):
        original=wc.replace_json
        def fail(path,data):
            if Path(path)==self.paths()[1]:raise PermissionError('fixture workspace locked')
            return original(path,data)
        with patch.object(wc,'replace_json',side_effect=fail),self.assertRaises(PermissionError):
            wc.publish_result(self.root,self.changed)
        self.assertEqual(read(self.paths()[0])['run_id'],self.changed['run_id'])
        wc.synchronize(self.root);self.assert_synced(self.changed)

    def test_interrupted_provenance_write_recovers(self):
        original=wc.replace_json
        def fail(path,data):
            if Path(path)==self.paths()[2]:raise PermissionError('fixture provenance locked')
            return original(path,data)
        with patch.object(wc,'replace_json',side_effect=fail),self.assertRaises(PermissionError):
            wc.publish_result(self.root,self.changed)
        wc.synchronize(self.root);self.assert_synced(self.changed)

    def test_loading_current_repairs_old_catalog_and_returns_new_result(self):
        replace_json(self.paths()[0],self.changed)
        with patch.object(aw,'P',self.root):view=aw.packet('current',self.root/'.local/test-packet')
        self.assertEqual(view['run_id'],self.changed['run_id'])
        self.assert_synced(self.changed)

    def test_busy_catalog_lock_has_a_bounded_failure(self):
        code='import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from src.workspace_catalog import catalog_lock\ntry:\n with catalog_lock(Path(sys.argv[2]),timeout=.1): pass\nexcept TimeoutError:\n print("EXPECTED_TIMEOUT")\nelse:\n raise RuntimeError("lock was bypassed")'
        with wc.catalog_lock(self.root):
            result=subprocess.run([sys.executable,'-B','-c',code,str(ROOT),str(self.root)],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(b'EXPECTED_TIMEOUT',result.stdout)

    def test_two_publishing_processes_leave_one_consistent_snapshot(self):
        code='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from src.workspace_catalog import publish_result\nr=Path(sys.argv[2]);v=json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))\nfor i in range(2):\n v["run_id"]=sys.argv[4]+str(i);publish_result(r,v)'
        fixture=self.root/'new.json';replace_json(fixture,self.changed)
        jobs=[subprocess.Popen([sys.executable,'-B','-c',code,str(ROOT),str(self.root),str(fixture),name],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for name in ['first','second']]
        try:
            for job in jobs:
                _,stderr=job.communicate(timeout=30)
                self.assertEqual(job.returncode,0,stderr)
        finally:
            for job in jobs:
                if job.poll() is None:job.kill();job.communicate()
        self.assert_synced(read(self.paths()[0]))

    def test_bad_cli_request_does_not_overwrite_latest(self):
        spec=importlib.util.spec_from_file_location('cli_lifecycle',ROOT/'run_ais_single_task.py')
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        bad=self.root/'bad-request.json';bad.write_bytes(b'{broken')
        before=[p.read_bytes() for p in self.paths()]
        with patch.object(cli,'PROJECT',self.root),patch.object(sys,'argv',['run_ais_single_task.py','--capture',str(self.root),'--request',str(bad)]),redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(),1)
        self.assertEqual(before,[p.read_bytes() for p in self.paths()])

    def test_atomic_write_failure_leaves_no_temporary_garbage(self):
        target=self.root/'atomic.json';replace_json(target,{'old':True})
        with patch('src.ais_replay.os.replace',side_effect=PermissionError('fixture denied')), self.assertRaises(PermissionError):replace_json(target,{'new':True})
        self.assertEqual(read(target),{'old':True})
        self.assertEqual(list(self.root.glob('atomic.json.*.tmp')),[])

    def test_publication_failure_does_not_relabel_an_already_published_calculation(self):
        import src.ais_single_task as task
        request=deepcopy(self.original['request']);request.pop('research_points',None)
        planner=Mock();planner.timeline.horizon_s=self.original['data_check']['available_seconds']
        planner.plan_corridor.return_value=deepcopy(self.original['planning'])
        with patch.object(task,'load_environment',return_value=({},{})),patch.object(task,'PlanarObservedPlanner',return_value=planner),patch.object(wc,'_write',side_effect=PermissionError('fixture interrupted publication')),redirect_stderr(io.StringIO()):
            result=task.run_task(self.root/'data/ais/captures'/self.original['capture_id'],request,self.root)
        self.assertEqual(result['status'],'error')
        self.assertIn('result_publish_failed',result['failure_reason'])
        directory=self.root/'output/ais_single_task/runs'/result['run_id']
        self.assertEqual(read(directory/'result.json')['status'],'planned')
        self.assertEqual(read(self.paths()[0])['status'],'planned')
        self.assertEqual(read(self.paths()[0])['run_id'],result['run_id'])
        self.assertEqual(read(directory/'publication_error.json')['status'],'error')
        wc.synchronize(self.root);self.assert_synced(read(self.paths()[0]))


if __name__=='__main__':unittest.main()
