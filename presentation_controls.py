"""Install camera input in this project's AnyLogic animation client."""
from __future__ import annotations

from contextlib import contextmanager
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

from portable_runtime import PROJECT_ROOT, LOCAL_DIR, find_anylogic

P = PROJECT_ROOT
PROFILE = LOCAL_DIR / "controlled-demo-chrome"
STATE = LOCAL_DIR / "controlled-demo-browser.json"
SCRIPT = P / "anylogic/ctrl_wheel.js"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _powershell_json(code):
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); " + code],
        capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError("无法查询本机演示进程，请检查 PowerShell/CIM 是否可用。")
    return json.loads(result.stdout.strip() or "null")


def process_identity(pid):
    pid = int(pid)
    if pid <= 0:
        return None
    return _powershell_json(
        f"Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' | "
        "ForEach-Object {[pscustomobject]@{pid=$_.ProcessId;"
        "started=$_.CreationDate.ToUniversalTime().ToString('o')}} | ConvertTo-Json -Compress"
    )


def browser_apps():
    code = r"""Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" | ForEach-Object {
        if ($_.CommandLine -match '--app="?(http://localhost:\d+)') {
            $animationUrl = $Matches[1]
            $animationProfile = ''
            if ($_.CommandLine -match '(?:"--user-data-dir=([^"]+)"|--user-data-dir="([^"]+)"|--user-data-dir=([^\s"]+))') {
                $animationProfile = if ($Matches[1]) {$Matches[1]} elseif ($Matches[2]) {$Matches[2]} else {$Matches[3]}
            }
            [pscustomobject]@{pid=$_.ProcessId;parent=$_.ParentProcessId;url=$animationUrl;
                profile=$animationProfile;executable=$_.ExecutablePath;
                started=$_.CreationDate.ToUniversalTime().ToString('o')}
        }
    } | ConvertTo-Json -Compress"""
    data = _powershell_json(code)
    return data if isinstance(data, list) else ([data] if data else [])


def alive(url):
    if not isinstance(url, str) or not re.fullmatch(r"http://localhost:\d+", url):
        return False
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def _same_path(first, second):
    try:
        return Path(first).resolve() == Path(second).resolve()
    except (OSError, TypeError, ValueError):
        return False


def owned_model_metadata(url=None):
    """A closed viewer does not invalidate a still-running model we launched."""
    try:
        meta = read(STATE)
        if not isinstance(meta, dict):
            return None
        if not _same_path(meta.get("project_root"), P):
            return None
        if not isinstance(meta.get("url"), str) or not re.fullmatch(r"http://localhost:\d+", meta["url"]):
            return None
        if url is not None and meta.get("url") != url:
            return None
        java = process_identity(meta["java_pid"])
        if not java or java["started"] != meta.get("java_started"):
            return None
        return meta
    except (OSError, KeyError, TypeError, ValueError):
        return None


def owned_metadata(url=None, apps=None):
    """Require directory ownership and both original process creation times."""
    try:
        meta = owned_model_metadata(url)
        if not meta:
            return None
        app = next((item for item in (apps if apps is not None else browser_apps())
                    if item["pid"] == meta["pid"]), None)
        if not app or app["started"] != meta.get("browser_started"):
            return None
        if app["url"] != meta["url"] or not _same_path(app["profile"], PROFILE):
            return None
        if not _same_path(app["executable"], find_anylogic() / "chromium/chromium-win64/chrome.exe"):
            return None
        return meta
    except (OSError, KeyError, TypeError, ValueError):
        return None


@contextmanager
def local_lock(name, timeout=90):
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    with (LOCAL_DIR / name).open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("同一项目的启动操作仍在进行，请稍候重试。")
                time.sleep(.2)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def install(url, java_pid=None):
    with local_lock("presentation-controls.lock"):
        return _install(url, java_pid)


def _install(url, java_pid=None):
    if not alive(url):
        raise RuntimeError("本项目的 AnyLogic 演示尚未启动。")
    apps = browser_apps()
    model_meta = owned_model_metadata(url)
    meta = owned_metadata(url, apps)
    if java_pid is None:
        if not model_meta:
            raise RuntimeError("该窗口没有本项目的运行记录，未接管其他演示窗口。")
        java_pid = model_meta["java_pid"]
    java = process_identity(java_pid)
    if not java:
        raise RuntimeError("演示进程已经退出，请重新启动。")
    native_apps = [app for app in apps if app["url"] == url and app["parent"] == java_pid]
    if not native_apps and not (model_meta and model_meta["java_pid"] == java_pid):
        raise RuntimeError("没有找到该模型进程对应的原生动画窗口。")
    reuse = False
    debug = meta.get("debug_port") if meta else None
    if debug:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{int(debug)}/json/version", timeout=1):
                reuse = True
        except (OSError, ValueError):
            pass
    if not reuse:
        if meta:
            raise RuntimeError("现有演示窗口的控制连接已失效。请关闭该演示后重新启动。")
        PROFILE.mkdir(parents=True, exist_ok=True)
        portfile = PROFILE / "DevToolsActivePort"
        portfile.unlink(missing_ok=True)
        executable = find_anylogic() / "chromium/chromium-win64/chrome.exe"
        child = subprocess.Popen([
            str(executable), "--app=" + url, "--user-data-dir=" + str(PROFILE),
            "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0", "--no-first-run",
        ])
        for _ in range(100):
            if portfile.exists():
                lines = portfile.read_text(encoding="utf-8").splitlines()
                if lines and lines[0].isdigit():
                    debug = int(lines[0])
                    break
            if child.poll() is not None:
                raise RuntimeError("AnyLogic 动画客户端未能启动。")
            time.sleep(.1)
        else:
            raise RuntimeError("等待动画客户端的本地控制连接超时。")
        browser = process_identity(child.pid)
        if not browser:
            raise RuntimeError("动画客户端已经退出。")
        meta = {
            "project_root": str(P), "pid": child.pid, "browser_started": browser["started"],
            "debug_port": debug, "url": url, "profile": str(PROFILE),
            "java_pid": int(java_pid), "java_started": java["started"],
        }
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("缺少 Playwright。请先运行项目的环境初始化脚本。") from exc
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{debug}")
        context = browser.contexts[0]
        script = SCRIPT.read_text(encoding="utf-8")
        context.add_init_script(script)
        page = next((item for item in context.pages if item.url.rstrip("/") == url), None)
        if page is None:
            raise RuntimeError("动画客户端页面与本项目运行地址不一致。")
        page.wait_for_load_state("domcontentloaded")
        page.evaluate(script)
        page.wait_for_function("()=>window.__maritimeViewControls?.installed", timeout=20000)
        meta["controls_installed"] = True
        temp_state = STATE.with_suffix(".tmp")
        temp_state.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        temp_state.replace(STATE)
        (LOCAL_DIR / "visual_endpoint.txt").write_text(url, encoding="utf-8")
    for app in native_apps:
        if app["pid"] != meta["pid"]:
            identity = process_identity(app["pid"])
            if identity and identity["started"] == app["started"]:
                try:
                    os.kill(app["pid"], 15)
                except ProcessLookupError:
                    pass
    return meta


def install_for_model(java_pid):
    java_pid = int(java_pid)
    for _ in range(100):
        apps = browser_apps()
        meta = owned_metadata(apps=apps)
        if meta and meta["java_pid"] == java_pid and alive(meta["url"]):
            return install(meta["url"], java_pid)
        app = next((item for item in apps if item["parent"] == java_pid), None)
        if app and alive(app["url"]):
            return install(app["url"], java_pid)
        if not process_identity(java_pid):
            raise RuntimeError("等待动画时模型进程已退出。")
        time.sleep(.3)
    raise RuntimeError("等待本模型的原生动画窗口超时，请查看 AnyLogic 错误输出。")
