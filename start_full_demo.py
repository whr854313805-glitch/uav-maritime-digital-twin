"""Start or focus the current checkout's six-case AnyLogic demonstration."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from portable_runtime import PROJECT_ROOT, LOCAL_DIR, find_anylogic, find_python

P = PROJECT_ROOT
MODEL = P / "anylogic/AIS_Visual_Demo.alp"


def focus(pid):
    """Focus only this checkout's recorded Chromium process."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetForegroundWindow.restype = wintypes.HWND
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.BringWindowToTop.argtypes = [wintypes.HWND]
    user.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    matches = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        window_pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid and user.IsWindowVisible(hwnd):
            matches.append(hwnd)
        return True

    user.EnumWindows(visit, 0)
    if not matches:
        return False
    hwnd = matches[0]
    user.ShowWindow(hwnd, 9)
    user.SetForegroundWindow(hwnd)
    if user.GetForegroundWindow() != hwnd:
        current = ctypes.windll.kernel32.GetCurrentThreadId()
        foreground = user.GetWindowThreadProcessId(user.GetForegroundWindow(), None)
        attached = user.AttachThreadInput(current, foreground, True)
        try:
            user.BringWindowToTop(hwnd)
            user.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user.AttachThreadInput(current, foreground, False)
    return True


def check_environment():
    if os.name != "nt":
        raise RuntimeError("此运行包面向 Windows 10/11 64 位系统。")
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("需要 64 位 Python。请使用项目自带的 Windows Python 运行库。")
    home = find_anylogic()
    python = find_python()
    required = [MODEL, P / "anylogic/native-visual-demo.jar", P / "anylogic/ctrl_wheel.js",
                P / "prepare_portable_model.py", P / "runtime/ompl/sst_worker.exe"]
    missing_files = [str(path.relative_to(P)) for path in required if not path.is_file()]
    if missing_files:
        raise RuntimeError("项目文件不完整：" + ", ".join(missing_files))
    imports = {"playwright.sync_api": "playwright", "numpy": "numpy", "shapely": "shapely",
               "pyproj": "pyproj", "yaml": "PyYAML", "PIL.Image": "Pillow"}
    failures = []
    for module, package in imports.items():
        try:
            importlib.import_module(module)
        except (ImportError, OSError) as exc:
            failures.append(f"{package}: {exc}")
    if failures:
        raise RuntimeError("Python 依赖不可用：" + "; ".join(failures) + "。请先运行项目的环境初始化脚本。")
    return {"ok": True, "project_root": str(P), "local_directory": str(LOCAL_DIR),
            "anylogic_home": str(home), "python": str(python),
            "model_template": str(MODEL), "platform": "Windows x64"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只检查运行环境，不打开演示")
    parser.add_argument("--controls-only", type=int, metavar="JAVA_PID", help=argparse.SUPPRESS)
    args = parser.parse_args()
    python = find_python()
    current_python = Path(sys.executable).resolve()
    same_installation = (
        python.parent == current_python.parent
        and python.name.lower() in ("python.exe", "pythonw.exe")
        and current_python.name.lower() in ("python.exe", "pythonw.exe")
    )
    if python != current_python and not same_installation:
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if args.controls_only else {}
        completed = subprocess.run([str(python), str(Path(__file__).resolve()), *sys.argv[1:]], **options)
        return completed.returncode
    if args.check:
        print(json.dumps(check_environment(), ensure_ascii=False, indent=2))
        return 0
    from presentation_controls import alive, install, install_for_model, local_lock, owned_metadata, owned_model_metadata
    if args.controls_only:
        install_for_model(args.controls_only)
        print("本模型的中键平移与 Ctrl+滚轮缩放已就绪。")
        return 0
    checked = check_environment()
    from prepare_portable_model import prepare_model

    with local_lock("launch.lock", timeout=150):
        meta = owned_model_metadata()
        if meta and alive(meta["url"]):
            meta = install(meta["url"], meta["java_pid"])
            focus(meta["pid"])
            print("已打开本项目正在运行的完整演示。")
            return 0
        model = prepare_model(P, Path(checked["anylogic_home"]), python)
        # Eclipse forwards -r to an already open workspace without running it.
        # A fresh workspace makes closing and restarting the model reliable,
        # while leaving all existing editors and any unsaved work untouched.
        workspace = LOCAL_DIR / "anylogic-workspaces" / uuid.uuid4().hex[:12]
        workspace.mkdir(parents=True, exist_ok=False)
        environment = os.environ.copy()
        environment.update(ANYLOGIC_HOME=checked["anylogic_home"], UAV_PROJECT_ROOT=str(P), UAV_PYTHON=str(python))
        child = subprocess.Popen([
            str(Path(checked["anylogic_home"]) / "AnyLogic.exe"), "-data", str(workspace),
            "-nosplash", "-r", str(model), "Simulation",
        ], cwd=str(P), env=environment)
        (LOCAL_DIR / "launcher-state.json").write_text(json.dumps({
            "project_root": str(P), "workspace": str(workspace), "model": str(model),
            "editor_launcher_pid": child.pid, "started_unix_s": time.time(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("正在启动 AnyLogic 完整演示，请稍候……", flush=True)
        for _ in range(100):
            meta = owned_metadata()
            if meta and alive(meta["url"]):
                focus(meta["pid"])
                print("完整演示已就绪。")
                return 0
            time.sleep(1)
        print("已启动 AnyLogic。若出现提示，请运行 Simulation；若启动失败，请查看模型错误和 anylogic/visual_demo/controls_setup.log。")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ImportError, ValueError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
