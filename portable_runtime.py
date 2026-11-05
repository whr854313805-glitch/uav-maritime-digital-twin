"""Resolve this checkout's local tools; machine settings are never repository data."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_DIR = PROJECT_ROOT / ".local"


def settings() -> dict:
    path = PROJECT_ROOT / "settings.local.json"
    if not path.exists():
        return {}
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"无法读取本机配置 {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("settings.local.json 必须是 JSON 对象。")
    return result


def _local_path(value: str | os.PathLike) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(str(value))))
    return (PROJECT_ROOT / path if not path.is_absolute() else path).resolve()


def _anylogic_home(value: str | os.PathLike) -> Path:
    path = _local_path(value)
    return path.parent if path.name.lower() == "anylogic.exe" else path


def _validate_anylogic(path: Path) -> Path:
    required = [path / "AnyLogic.exe", path / "chromium/chromium-win64/chrome.exe"]
    if not all(item.is_file() for item in required):
        raise RuntimeError(f"AnyLogic 安装不完整或路径不正确：{path}")
    if not any((path / "plugins").glob("com.anylogic.engine_8.9.*")):
        raise RuntimeError(f"需要 AnyLogic 8.9 系列（本项目验收版本为 8.9.10）：{path}")
    return path


def _registry_installations():
    if os.name != "nt":
        return
    import winreg

    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, index)) as child:
                                name = winreg.QueryValueEx(child, "DisplayName")[0]
                                if "anylogic" in name.lower():
                                    yield winreg.QueryValueEx(child, "InstallLocation")[0]
                        except OSError:
                            continue
            except OSError:
                continue


def find_anylogic() -> Path:
    explicit = os.environ.get("ANYLOGIC_HOME") or settings().get("anylogic_home")
    if explicit:
        return _validate_anylogic(_anylogic_home(explicit))
    candidates = list(_registry_installations())
    on_path = shutil.which("AnyLogic.exe")
    if on_path:
        candidates.append(on_path)
    search_roots = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "C:/__not_installed__")) / "Programs",
    ]
    search_roots.extend(Path(f"{letter}:/anylogic") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ")
    for root in search_roots:
        if root.is_dir():
            candidates.extend(sorted(root.glob("AnyLogic*"), reverse=True))
            if (root / "AnyLogic.exe").is_file():
                candidates.append(root)
    seen = set()
    for candidate in candidates:
        path = _anylogic_home(candidate)
        if path in seen:
            continue
        seen.add(path)
        try:
            return _validate_anylogic(path)
        except RuntimeError:
            continue
    raise RuntimeError(
        "未找到 AnyLogic 8.9。请单独安装 AnyLogic 8.9.10 PLE，"
        '然后在 settings.local.json 中设置 "anylogic_home"，或设置 ANYLOGIC_HOME 环境变量。'
    )


def find_python() -> Path:
    explicit = os.environ.get("UAV_PYTHON") or settings().get("python")
    if explicit:
        path = _local_path(explicit)
        if not path.is_file():
            raise RuntimeError(f"配置的 Python 不存在：{path}")
        return path
    for path in (
        PROJECT_ROOT / "runtime/python/python.exe",
        PROJECT_ROOT / ".venv/Scripts/python.exe",
        Path(sys.executable),
    ):
        if path.is_file():
            return path.resolve()
    raise RuntimeError("没有可用的 Python。请先运行项目的环境初始化脚本。")
