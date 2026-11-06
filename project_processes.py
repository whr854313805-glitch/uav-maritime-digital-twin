"""Bounded process queries and ownership checks for this one checkout."""
from pathlib import Path
import json, os, subprocess, time, uuid
from portable_runtime import PROJECT_ROOT as P, LOCAL_DIR, find_anylogic


def atomic_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        tmp.replace(path)
    finally:tmp.unlink(missing_ok=True)


def read_json(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return value if isinstance(value,dict) else None
    except (OSError,ValueError):return None


def powershell_json(code):
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',
            '[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); '+code],
            capture_output=True,text=True,encoding='utf-8',timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as e:raise RuntimeError('Windows process query timed out; no process was taken over.') from e
    if result.returncode:raise RuntimeError('Windows process query failed; no process was taken over.')
    return json.loads(result.stdout.strip() or 'null')


def process_identity(pid):
    if type(pid) is not int or pid<=0:return None
    return powershell_json(f"Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' | ForEach-Object {{"
      "[pscustomobject]@{pid=$_.ProcessId;parent=$_.ParentProcessId;executable=$_.ExecutablePath;command=$_.CommandLine;"
      "started=$_.CreationDate.ToUniversalTime().ToString('o');start_ms=([DateTimeOffset]$_.CreationDate.ToUniversalTime()).ToUnixTimeMilliseconds()}} | ConvertTo-Json -Compress")


def same_path(a,b):
    try:return Path(a).resolve()==Path(b).resolve()
    except (OSError,TypeError,ValueError):return False


def model_session(pid=None):
    launch=read_json(LOCAL_DIR/'launcher-state.json');record=read_json(LOCAL_DIR/'model-session.json')
    if not launch or not record or launch.get('phase') not in ('starting','ready'):return None
    if not same_path(launch.get('project_root'),P) or not same_path(record.get('project_root'),P):return None
    if record.get('launch_id')!=launch.get('launch_id') or not record.get('loopback_only'):return None
    from src.release_checks import release_identity
    if launch.get('release_sha256')!=release_identity(P):return None
    if pid is not None and record.get('java_pid')!=pid:return None
    if not same_path(record.get('workspace'),launch.get('workspace')) or not same_path(record.get('model'),launch.get('model')):return None
    work=Path(launch['workspace']).resolve();model=Path(launch['model']).resolve()
    if not work.is_relative_to(LOCAL_DIR/'anylogic-workspaces') or not model.is_relative_to(LOCAL_DIR/'model'):return None
    java=process_identity(record.get('java_pid'))
    if not java or java.get('start_ms')!=record.get('java_start_ms'):return None
    home=find_anylogic()
    if not any(same_path(java.get('executable'),home/'jre/bin'/name) for name in ('java.exe','javaw.exe')):return None
    if str(work).lower() not in str(java.get('command','')).lower():return None
    record['java_started']=java['started']
    return record


def set_phase(launch, phase, **extra):
    launch.update(phase=phase,updated_unix_s=time.time(),**extra)
    atomic_json(LOCAL_DIR/'launcher-state.json',launch)
    if len(str(launch.get('launch_id','')))==32:
        atomic_json(LOCAL_DIR/'sessions'/(launch['launch_id']+'.json'),launch)


def close_failed_run(launch):
    """Stop only this model's descendants; never kill a user editor by name."""
    if not same_path(launch.get('project_root'),P):raise RuntimeError('Refusing cleanup of another project')
    record=model_session()
    if record and record.get('launch_id')==launch.get('launch_id'):
        stop_tree(record['java_pid'],record['java_start_ms'])
    else:
        # Startup may fail before the model has registered. The unique workspace
        # and exact model main class identify that unregistered child safely.
        rows=powershell_json("Get-CimInstance Win32_Process -Filter \"Name = 'javaw.exe' OR Name = 'java.exe'\" | ForEach-Object {"
          "[pscustomobject]@{pid=$_.ProcessId;executable=$_.ExecutablePath;command=$_.CommandLine;start_ms=([DateTimeOffset]$_.CreationDate.ToUniversalTime()).ToUnixTimeMilliseconds()}} | ConvertTo-Json -Compress")
        for item in (rows if isinstance(rows,list) else [rows] if rows else []):
            if (any(same_path(item.get('executable'),find_anylogic()/'jre/bin'/n) for n in ('java.exe','javaw.exe'))
                and str(launch['workspace']).lower() in str(item.get('command','')).lower()
                and 'ais_visual_demo.Simulation' in str(item.get('command',''))
                and item['start_ms']>=int(launch['started_unix_s']*1000)):
                stop_tree(item['pid'],item['start_ms'])
    # Graceful close only: Windows may preserve a save dialog rather than lose edits.
    editor=launch.get('editor_identity')
    if editor:
        current=process_identity(editor.get('pid'))
        if current and current.get('start_ms')==editor.get('start_ms') and same_path(current.get('executable'),find_anylogic()/'AnyLogic.exe') and str(launch['workspace']).lower() in str(current.get('command','')).lower():
            import ctypes
            from ctypes import wintypes
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
            user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
            @ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
            def visit(hwnd,_):
                value=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(value))
                if value.value==current['pid']:user.PostMessageW(hwnd,0x0010,0,0)
                return True
            user.EnumWindows(visit,0)
            time.sleep(1)
            current=process_identity(editor['pid'])
            if current and current.get('start_ms')==editor.get('start_ms'):
                import hashlib
                model=Path(launch['model'])
                if launch.get('model_sha256') and model.is_file() and hashlib.sha256(model.read_bytes()).hexdigest()==launch['model_sha256']:
                    stop_tree(editor['pid'],editor['start_ms'])
                else:
                    raise RuntimeError('上次本项目编辑器仍在运行；为保留可能的模型编辑，请先关闭该编辑器再重试。')


def owned_descendants(rows,pid,start_ms):
    """Reject reused PIDs and cycles in a Windows process snapshot."""
    index={r['pid']:r for r in rows}
    root=index.get(pid)
    if not root or root['start_ms']!=start_ms:return []
    owned=[root];seen={pid}
    for parent in owned:
        for child in rows:
            if child['pid'] not in seen and child['parent']==parent['pid'] and child['start_ms']>=parent['start_ms']:
                seen.add(child['pid']);owned.append(child)
    return list(reversed(owned))


def terminate_identity(pid,start_ms):
    """Check creation time on the opened handle, so PID reuse cannot change target."""
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000|0x0001,False,pid)
    if not handle:return False
    try:
        created,exited,kernel_time,user_time=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*map(ctypes.byref,(created,exited,kernel_time,user_time))):return False
        actual=((created.dwHighDateTime<<32)|created.dwLowDateTime)//10000-11644473600000
        if actual!=start_ms:return False
        return bool(kernel.TerminateProcess(handle,1))
    finally:kernel.CloseHandle(handle)


def stop_tree(pid,start_ms):
    rows=powershell_json("Get-CimInstance Win32_Process | ForEach-Object {"
       "[pscustomobject]@{pid=$_.ProcessId;parent=$_.ParentProcessId;start_ms=([DateTimeOffset]$_.CreationDate.ToUniversalTime()).ToUnixTimeMilliseconds()}} | ConvertTo-Json -Compress")
    for item in owned_descendants(rows or [],pid,start_ms):
        terminate_identity(item['pid'],item['start_ms'])


def verify_listener(port,pid):
    rows=powershell_json(f"Get-NetTCPConnection -State Listen -LocalPort {int(port)} -ErrorAction Stop | Where-Object {{$_.OwningProcess -eq {int(pid)}}} | Select-Object LocalAddress | ConvertTo-Json -Compress")
    rows=rows if isinstance(rows,list) else [rows] if rows else []
    if not rows or any(r['LocalAddress'] not in ('127.0.0.1','::1') for r in rows):
        raise RuntimeError('Model listener is not restricted to loopback; startup refused.')


def launch_pending(launch):
    if not launch or not same_path(launch.get('project_root'),P) or launch.get('phase')!='starting':return False
    editor=launch.get('editor_identity')
    if not editor:return time.time()-launch.get('started_unix_s',0)<30
    current=process_identity(editor.get('pid'))
    return bool(current and current.get('start_ms')==editor.get('start_ms'))


def cleanup_finished_sessions(keep=3):
    """Keep recent diagnostics; remove only ended, unedited generated session caches."""
    import shutil,hashlib
    directory=LOCAL_DIR/'sessions'
    if not directory.exists():return []
    records=sorted(directory.glob('*.json'),key=lambda p:(read_json(p) or {}).get('started_unix_s',p.stat().st_mtime),reverse=True)
    if len(records)<=keep:return []
    rows=powershell_json("Get-CimInstance Win32_Process | Select-Object CommandLine | ConvertTo-Json -Compress")
    commands=[str(r.get('CommandLine','')).replace('/','\\').lower() for r in (rows or [])]
    removed=[]
    for file in records[keep:]:
        launch=read_json(file);key=file.stem
        if len(key)!=32 or any(c not in '0123456789abcdef' for c in key) or not launch or launch.get('launch_id')!=key or not same_path(launch.get('project_root'),P):continue
        workspace=(LOCAL_DIR/'anylogic-workspaces'/key).resolve();model=(LOCAL_DIR/'model'/key).resolve()
        if not workspace.is_relative_to((LOCAL_DIR/'anylogic-workspaces').resolve()) or not model.is_relative_to((LOCAL_DIR/'model').resolve()):continue
        # CIM may expose an 8.3 alias (notably RUNNER~1) rather than the long path.
        # Preserve either representation; never prune a possibly active session.
        forms=path_forms(LOCAL_DIR/'anylogic-workspaces'/key)|path_forms(LOCAL_DIR/'model'/key)
        if any(form in cmd for form in forms for cmd in commands):continue
        alp=model/'AIS_Visual_Demo.alp'
        if not alp.exists() or not launch.get('model_sha256') or hashlib.sha256(alp.read_bytes()).hexdigest()!=launch['model_sha256']:continue
        log=workspace/'editor.log'
        if log.exists():
            target=LOCAL_DIR/'logs'/(key+'-editor.log');target.parent.mkdir(exist_ok=True);shutil.copy2(log,target)
        try:
            if workspace.is_dir():shutil.rmtree(workspace)
            if model.is_dir():shutil.rmtree(model)
        except OSError:continue # A locked cache can be retried; never force unrelated handles.
        launch['caches_removed']=True;atomic_json(file,launch);removed.append(key)
    return removed


def path_forms(path):
    import ctypes
    original=Path(path);canonical=original.resolve()
    forms={str(original),str(canonical)}
    if os.name=='nt':
        from ctypes import wintypes
        function=ctypes.WinDLL('kernel32',use_last_error=True).GetShortPathNameW
        function.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,wintypes.DWORD]
        buffer=ctypes.create_unicode_buffer(32768)
        size=function(str(canonical),buffer,len(buffer))
        if 0<size<len(buffer):forms.add(buffer.value)
    return {f.replace('/','\\').lower() for f in forms}
