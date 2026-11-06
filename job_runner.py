"""Own the complete Python/SST job tree with a Windows kill-on-close Job Object."""
from pathlib import Path
import argparse,ctypes,json,os,subprocess,sys,time
from ctypes import wintypes


def own_job_tree():
    if os.name!='nt':raise RuntimeError('This job runner requires Windows')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    class BASIC(ctypes.Structure):
        _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),('PerJobUserTimeLimit',ctypes.c_int64),
          ('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),
          ('ActiveProcessLimit',wintypes.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(name,ctypes.c_uint64) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
    class EXTENDED(ctypes.Structure):
        _fields_=[('BasicLimitInformation',BASIC),('IoInfo',IO),('ProcessMemoryLimit',ctypes.c_size_t),
                  ('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateJobObjectW(None,None)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    limits=EXTENDED();limits.BasicLimitInformation.LimitFlags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
        error=ctypes.WinError(ctypes.get_last_error());kernel.CloseHandle(handle);raise error
    if not kernel.AssignProcessToJobObject(handle,kernel.GetCurrentProcess()):
        error=ctypes.WinError(ctypes.get_last_error());kernel.CloseHandle(handle);raise error
    # Keep this non-inherited handle open for this supervisor's lifetime. If it is
    # killed/closed, Windows closes the handle and reaps only its assigned children.
    return handle


def owner_handle():
    """Hold the original parent handle and reject a PID reused after our birth."""
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    handle=kernel.OpenProcess(0x100000|0x1000,False,os.getppid())
    if not handle:raise RuntimeError('Job owner has already exited')
    def creation(process):
        times=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(process,*map(ctypes.byref,times)):raise ctypes.WinError(ctypes.get_last_error())
        return (times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
    if creation(handle)>creation(kernel.GetCurrentProcess()):raise RuntimeError('Job owner PID was reused')
    return lambda:kernel.WaitForSingleObject(handle,0)==258


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--timeout',type=float,default=180)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    if not 0<args.timeout<=600:raise ValueError('Job timeout must be in (0,600] seconds')
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command:raise ValueError('Missing job command')
    owner_alive=owner_handle()
    job=own_job_tree()
    child=subprocess.Popen(command)
    deadline=time.monotonic()+args.timeout
    while True:
        if not owner_alive():
            print(json.dumps({'status':'error','failure_reason':'job_owner_exited'}),file=sys.stderr,flush=True)
            return 125
        remaining=deadline-time.monotonic()
        if remaining<=0:
            print(json.dumps({'status':'error','failure_reason':'job_timeout','timeout_seconds':args.timeout}),file=sys.stderr,flush=True)
            return 124
        try:return child.wait(timeout=min(.25,remaining))
        except subprocess.TimeoutExpired:pass


if __name__=='__main__':
    try:code=main()
    except Exception as error:
        print(json.dumps({'status':'error','failure_reason':'job_runner: '+str(error)}),file=sys.stderr,flush=True);code=1
    sys.stdout.flush();sys.stderr.flush()
    os._exit(code) # Closing the process-owned Job Object terminates leftover descendants.
