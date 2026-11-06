"""Failure-path regression tests. Only temp directories and owned processes change."""
from pathlib import Path
from copy import deepcopy
from contextlib import nullcontext,redirect_stderr
import io
import ctypes,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time,unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.validation import validate_request
from src.release_checks import verify_workspace,verify_release
from src.ais_single_task import run_task


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


class Contracts(unittest.TestCase):
    def setUp(self):self.request=read(ROOT/'config/ais-single-task.json')
    def test_bad_request_types_and_nonfinite(self):
        cases=[{'start':None},{'start':[True,1]},{'speed_mps':True},{'speed_mps':'15'},
               {'speed_mps':float('nan')},{'buffer_m':float('inf')},{'departure_offset_seconds':-1},
               {'max_expanded_states':True},{'task_id':''},{'window_start_utc':'not a date'},
               {'research_points':{'selection_file':3}},{'start':[91,0]}]
        for change in cases:
            with self.subTest(change=change):
                item=deepcopy(self.request);item.update(change)
                with self.assertRaises(ValueError):validate_request(item)
    def test_original_request_is_valid(self):validate_request(self.request)
    def test_nan_produces_structured_error(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);request=deepcopy(self.request);request['speed_mps']=float('nan')
            result=run_task(root/'no-capture',request,root,publish=False)
            self.assertEqual(result['status'],'error');self.assertIsNone(result['trajectory'])
            saved=list(root.rglob('result.json'));self.assertEqual(len(saved),1)
            self.assertIn('invalid',read(saved[0])['request']['speed_mps'])
    def test_result_write_failure_does_not_return_success(self):
        request=deepcopy(self.request);request['speed_mps']=True
        with tempfile.TemporaryDirectory() as d,redirect_stderr(io.StringIO()),patch('src.ais_single_task.replace_json',side_effect=PermissionError('test readonly')):
            result=run_task(Path(d)/'none',request,Path(d),publish=False)
            self.assertEqual(result['status'],'error');self.assertIn('result_write_failed',result['failure_reason'])
    def test_run_directory_denied_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as d,redirect_stderr(io.StringIO()),patch('src.ais_single_task.Path.mkdir',side_effect=PermissionError('test output denied')):
            result=run_task(Path(d)/'none',self.request,Path(d),publish=False)
            self.assertEqual(result['status'],'error');self.assertIsNone(result['trajectory'])
    def test_early_source_unverified_failure_is_empty_error_packet(self):
        import src.anylogic_workspace as work
        result={'run_id':'failure-test','status':'error','request':deepcopy(self.request),
                'failure_reason':'test early input failure','trajectory':None,'ship_check':None,'capture_id':None,'raw_sha256':None}
        with tempfile.TemporaryDirectory() as d,patch.object(work,'run_task',return_value=result):
            view=work.packet('M2',Path(d),run=True,departure='2026-11-03T21:13:16+08:00')
            self.assertEqual(view['status'],'error');self.assertIsNone(view['trajectory']);self.assertIsNone(view['raw_sha256'])


class DataIdentity(unittest.TestCase):
    def test_real_workspace(self):verify_workspace(ROOT)
    def test_one_kilometre_wrong_display_rejected(self):
        workspace=read(ROOT/'anylogic/workbench/workspace.json')
        vessel=next(v for v in workspace['vessels'] if v['segments'])
        vessel['segments'][0][0]['xy'][0]+=1000
        with self.assertRaisesRegex(ValueError,'workspace'):verify_workspace(ROOT,workspace)
    def test_wrong_display_time_rejected(self):
        workspace=read(ROOT/'anylogic/workbench/workspace.json')
        workspace['vessels'][0]['points'][0]['t']+=2
        with self.assertRaises(ValueError):verify_workspace(ROOT,workspace)
    def test_release_binary_replacement_rejected(self):
        required=['anylogic/native-visual-demo.jar','anylogic/loopback-agent.jar','src/validation.py','src/release_checks.py',
                  'runtime/data/current-data.manifest.json']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);rows=[]
            for name in required:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'original')
                rows.append({'path':name,'bytes':8,'sha256':sha(p)})
            (root/'FILE_MANIFEST.json').write_text(json.dumps({'files':rows}))
            verify_release(root)
            (root/required[0]).write_bytes(b'changed!')
            with self.assertRaisesRegex(ValueError,'identity mismatch'):verify_release(root)


class LatestRecovery(unittest.TestCase):
    def setUp(self):self.module=load('bootstrap_tests',ROOT/'scripts/bootstrap_project.py')
    def fixture(self,root):
        import zipfile
        name='output/ais_single_task/latest.json';original=read(ROOT/name)
        data=json.dumps(original,allow_nan=False).encode();archive=root/'runtime/data/current-data.zip'
        archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive,'w') as z:z.writestr(name,data)
        (archive.parent/'current-data.manifest.json').write_text(json.dumps({'archive_sha256':sha(archive),
          'files':[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}))
        target=root/name;target.parent.mkdir(parents=True);target.write_bytes(b'{broken')
        return target,original
    def test_corrupt_latest_blocks_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target,_=self.fixture(root)
            (root/'.local').mkdir();(root/'.local/data-bootstrap.json').write_text('{"complete":true}')
            with self.assertRaisesRegex(ValueError,'latest.json is invalid'):self.module.restore(root)
            self.assertEqual(target.read_bytes(),b'{broken');self.assertFalse((root/'.local/data-bootstrap.json').exists())
    def test_explicit_recovery_preserves_bad_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target,original=self.fixture(root)
            self.module.restore(root,recover_latest=True)
            self.assertEqual(read(target),original)
            backup=list((root/'.local/recovery').glob('latest-*.json'));self.assertEqual(len(backup),1)
            self.assertEqual(backup[0].read_bytes(),b'{broken')
    def test_missing_projection_cannot_report_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target,original=self.fixture(root);original.pop('projection',None)
            target.write_text(json.dumps(original),encoding='utf-8')
            with self.assertRaises(ValueError):self.module.restore(root)
    def test_valid_new_latest_is_retained(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target,original=self.fixture(root);original['run_id']='new-run'
            target.write_text(json.dumps(original),encoding='utf-8')
            before=target.read_bytes();self.module.restore(root)
            self.assertEqual(target.read_bytes(),before)
    def test_interrupted_extract_is_resumable(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target,original=self.fixture(root);target.unlink()
            with patch.object(self.module.tempfile,'mkstemp',side_effect=OSError('test disk full')):
                with self.assertRaises(OSError):self.module.restore(root)
            self.assertFalse(target.exists());self.module.restore(root);self.assertEqual(read(target),original)


class ProcessBoundaries(unittest.TestCase):
    def test_success_report_survives_english_console_and_unicode_path(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'中文验收';root.mkdir()
            code=('import importlib.util,sys;sys.stdout.reconfigure(encoding="cp1252",errors="strict");'
                's=importlib.util.spec_from_file_location("verify_cli",'+repr(str(ROOT/'scripts/verify_project.py'))+');'
                'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);'
                'm.verify=lambda project,recompute:{"passed":True};'
                'sys.argv=["verify_project.py","--project",'+repr(str(root))+'];raise SystemExit(m.main())')
            result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
            self.assertIn('中文验收',result.stdout.decode('utf-8'))
            self.assertTrue(read(root/'.local/verification.json')['passed'])
    def test_process_query_is_bounded(self):
        import project_processes as proc
        with patch.object(proc.subprocess,'run',side_effect=subprocess.TimeoutExpired('powershell',8)):
            with self.assertRaisesRegex(RuntimeError,'timed out'):proc.process_identity(123)
    def test_wrong_pid_not_taken_over(self):
        import presentation_controls as controls
        with patch.object(controls,'model_session',return_value=None),patch.object(controls,'browser_apps') as browsers:
            with self.assertRaises(RuntimeError):controls.install_for_model(123)
            browsers.assert_not_called()
    def test_running_release_mismatch_not_reused(self):
        import project_processes as proc
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'FILE_MANIFEST.json').write_text(json.dumps({'files':[{'path':'src/validation.py','bytes':1,'sha256':'changed'}]}))
            launch={'project_root':d,'phase':'ready','launch_id':'test','release_sha256':'previous-release'}
            record={'project_root':d,'launch_id':'test','loopback_only':True}
            with patch.object(proc,'P',root),patch.object(proc,'LOCAL_DIR',root/'.local'),patch.object(proc,'read_json',side_effect=[launch,record]),patch.object(proc,'process_identity') as identity:
                self.assertIsNone(proc.model_session());identity.assert_not_called()
    def test_wrong_project_session_not_accepted(self):
        import project_processes as proc
        with patch.object(proc,'read_json',return_value={'phase':'starting','project_root':'C:/other-project'}),patch.object(proc,'process_identity') as identity:
            self.assertIsNone(proc.model_session());identity.assert_not_called()
    def test_pid_reuse_cycle_is_not_followed(self):
        from project_processes import owned_descendants
        rows=[{'pid':100,'parent':200,'start_ms':20},{'pid':200,'parent':100,'start_ms':10},
              {'pid':300,'parent':100,'start_ms':30}]
        self.assertEqual([r['pid'] for r in owned_descendants(rows,100,20)],[300,100])
        self.assertEqual(owned_descendants(rows,100,19),[])
    def test_client_early_exit_is_reaped(self):
        import presentation_controls as controls
        fake=unittest.mock.Mock();fake.poll.return_value=None
        with tempfile.TemporaryDirectory() as d,patch.object(controls,'PROFILE',Path(d)),patch.object(controls,'find_anylogic',return_value=Path(d)),patch.object(controls.subprocess,'Popen',return_value=fake),patch.object(controls.time,'sleep',side_effect=RuntimeError('test init interrupted')):
            with self.assertRaisesRegex(RuntimeError,'interrupted'):controls._start_client('http://localhost:123')
            fake.terminate.assert_called_once()
    def test_cleanup_preserves_edited_model_and_active_workspace(self):
        import project_processes as proc
        with tempfile.TemporaryDirectory() as d,patch.object(proc,'P',Path(d)),patch.object(proc,'LOCAL_DIR',Path(d)/'.local'):
            local=Path(d)/'.local';key='a'*32;work=local/'anylogic-workspaces'/key;model=local/'model'/key
            work.mkdir(parents=True);model.mkdir(parents=True);(model/'AIS_Visual_Demo.alp').write_text('generated');(work/'editor.log').write_text('test diagnostic')
            record={'project_root':d,'launch_id':key,'model_sha256':sha(model/'AIS_Visual_Demo.alp')}
            proc.atomic_json(local/'sessions'/(key+'.json'),record)
            with patch.object(proc,'powershell_json',return_value=[{'CommandLine':str(work)}]):
                self.assertEqual(proc.cleanup_finished_sessions(keep=0),[]);self.assertTrue(work.exists())
            (model/'AIS_Visual_Demo.alp').write_text('user edits')
            with patch.object(proc,'powershell_json',return_value=[]):
                self.assertEqual(proc.cleanup_finished_sessions(keep=0),[]);self.assertTrue(model.exists())
    def test_cleanup_finished_cache_keeps_diagnostic_log(self):
        import project_processes as proc
        with tempfile.TemporaryDirectory() as d,patch.object(proc,'P',Path(d)),patch.object(proc,'LOCAL_DIR',Path(d)/'.local'):
            local=Path(d)/'.local';key='b'*32;work=local/'anylogic-workspaces'/key;model=local/'model'/key
            work.mkdir(parents=True);model.mkdir(parents=True);(model/'AIS_Visual_Demo.alp').write_text('generated');(work/'editor.log').write_text('test diagnostic')
            record={'project_root':d,'launch_id':key,'model_sha256':sha(model/'AIS_Visual_Demo.alp')}
            proc.atomic_json(local/'sessions'/(key+'.json'),record)
            with patch.object(proc,'powershell_json',return_value=[]):self.assertEqual(proc.cleanup_finished_sessions(keep=0),[key])
            self.assertFalse(work.exists());self.assertFalse(model.exists());self.assertEqual((local/'logs'/(key+'-editor.log')).read_text(),'test diagnostic')
    def test_bad_settings_path_type(self):
        import portable_runtime as env
        with tempfile.TemporaryDirectory() as d,patch.object(env,'PROJECT_ROOT',Path(d)):
            (Path(d)/'settings.local.json').write_text('{"python":true}')
            with self.assertRaises(RuntimeError):env.settings()
    def startup_context(self,root):
        import start_full_demo as start
        import presentation_controls as controls
        import project_processes as proc
        from contextlib import ExitStack
        stack=ExitStack()
        for obj,name,value in [(start,'P',root),(start,'LOCAL_DIR',root/'.local'),(proc,'LOCAL_DIR',root/'.local'),
            (start,'find_python',lambda:Path(sys.executable).resolve()),
            (start,'check_environment',lambda:{'anylogic_home':str(root),'python':sys.executable,'release_sha256':'test-release'}),
            (start,'close_failed_run',lambda _:None),
            (controls,'owned_metadata',lambda **kw:None),(controls,'owned_model_metadata',lambda:None),
            (controls,'local_lock',lambda *a,**kw:nullcontext())]:stack.enter_context(patch.object(obj,name,value))
        (root/'model.alp').write_text('test model')
        stack.enter_context(patch('prepare_portable_model.prepare_model',return_value=root/'model.alp'))
        stack.enter_context(patch.object(sys,'argv',['start_full_demo.py']))
        return stack,start
    def test_spawn_failure_records_failed_state(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.startup_context(root)[0] as stack:
                import start_full_demo as start
                with patch.object(start.subprocess,'Popen',side_effect=OSError('test spawn denied')):
                    with self.assertRaises(OSError):start.main()
            record=read(root/'.local/launcher-state.json');self.assertEqual(record['phase'],'failed')
    def test_pending_startup_does_not_spawn_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.startup_context(root)[0]:
                import start_full_demo as start
                with patch.object(start,'launch_pending',return_value=True),patch.object(start.subprocess,'Popen') as spawn:
                    with self.assertRaises(RuntimeError):start.main()
                    spawn.assert_not_called()


@unittest.skipUnless(os.name=='nt','Windows Job Objects')
class JobOwnership(unittest.TestCase):
    @staticmethod
    def alive(pid):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x100000,False,pid)
        if not handle:return False
        try:return kernel.WaitForSingleObject(handle,0)==258
        finally:kernel.CloseHandle(handle)
    def run_tree(self,parent_exit=False,terminate_supervisor=False):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'child.json'
            code='import subprocess,sys,time,json; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(120)"]); Path('+repr(str(target))+').write_text(json.dumps({"child":p.pid})); '+('' if parent_exit else 'time.sleep(120)')
            unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
            runner=subprocess.Popen([sys.executable,str(ROOT/'job_runner.py'),'--timeout','2','--',sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                until=time.monotonic()+8
                while not target.exists() and runner.poll() is None and time.monotonic()<until:time.sleep(.05)
                self.assertTrue(target.exists(),'Supervisor failed to start owned child')
                child=read(target)['child']
                if terminate_supervisor:runner.terminate()
                stdout,stderr=runner.communicate(timeout=8)
                until=time.monotonic()+3
                while self.alive(child) and time.monotonic()<until:time.sleep(.05)
                self.assertFalse(self.alive(child),'Owned descendant survived supervisor exit')
                self.assertIsNone(unrelated.poll(),'Unrelated process was terminated')
                if not terminate_supervisor:self.assertEqual(runner.returncode,0 if parent_exit else 124,stderr.decode(errors='replace'))
            finally:
                if runner.poll() is None:runner.kill();runner.wait()
                unrelated.terminate();unrelated.wait()
    def test_forcibly_closed_owner_reaps_job_tree(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'child.json'
            command=[sys.executable,str(ROOT/'job_runner.py'),'--timeout','120','--',sys.executable,'-c',
                'import os,json,time;from pathlib import Path;Path('+repr(str(target))+').write_text(json.dumps({"child":os.getpid()}));time.sleep(120)']
            owner=subprocess.Popen([sys.executable,'-c','import subprocess,time;subprocess.Popen('+repr(command)+');time.sleep(120)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                until=time.monotonic()+8
                while not target.exists() and time.monotonic()<until:time.sleep(.05)
                self.assertTrue(target.exists());child=read(target)['child'];owner.kill();owner.wait(timeout=3)
                until=time.monotonic()+4
                while self.alive(child) and time.monotonic()<until:time.sleep(.05)
                self.assertFalse(self.alive(child),'Job survived its forcibly closed model/owner')
            finally:
                if owner.poll() is None:owner.kill();owner.wait()
    def test_job_timeout_reaps_descendants_only(self):self.run_tree()
    def test_normal_parent_exit_reaps_orphan(self):self.run_tree(parent_exit=True)
    def test_killed_supervisor_reaps_descendants(self):self.run_tree(terminate_supervisor=True)


if __name__=='__main__':unittest.main(verbosity=2)
