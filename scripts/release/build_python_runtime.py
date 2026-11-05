"""Build the project's isolated, offline Windows x64 Python distribution.

Run with the verified Python 3.11 development interpreter. Source package files
come from installed wheel RECORDs, including DLLs, data and third-party notices.
No developer venv paths or script launchers enter the runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

from packaging.requirements import Requirement

ROOT_PACKAGES = (
    "numpy", "shapely", "pyproj", "PyYAML", "Pillow", "playwright",
    "websockets", "requests",
)
CHUNK_BYTES = 40 * 1024 * 1024
PYTHON_SOURCE = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def packages():
    found = {}
    pending = list(ROOT_PACKAGES)
    while pending:
        requested = pending.pop(0)
        dist = metadata.distribution(requested)
        canonical = dist.metadata["Name"].lower().replace("_", "-")
        if canonical in found:
            continue
        found[canonical] = dist
        for text in dist.requires or ():
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            dependency = metadata.distribution(requirement.name)
            if dependency.version not in requirement.specifier:
                raise RuntimeError(f"Installed dependency does not satisfy {text}")
            pending.append(requirement.name)
    return [found[name] for name in sorted(found)]


def distribution_files(dist):
    for relative in dist.files or ():
        if ".." in relative.parts or "__pycache__" in relative.parts:
            continue
        if str(relative).endswith((".pyc", ".pyo")):
            continue
        source = Path(dist.locate_file(relative))
        if source.is_file():
            yield relative, source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--scan-only", action="store_true")
    args = parser.parse_args()
    selected = packages()
    rows = []
    for dist in selected:
        files = list(distribution_files(dist))
        largest = max(files, key=lambda pair: pair[1].stat().st_size)
        rows.append({
            "name": dist.metadata["Name"], "version": dist.version,
            "bytes": sum(path.stat().st_size for _, path in files),
            "file_count": len(files), "largest_file": str(largest[0]),
            "largest_file_bytes": largest[1].stat().st_size,
        })
    print(json.dumps({"packages": rows, "package_total_bytes": sum(row["bytes"] for row in rows)}, indent=2), flush=True)
    if args.scan_only:
        return
    if sys.version_info[:2] != (3, 11) or platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Build this runtime with the verified Windows x64 Python 3.11 interpreter")
    destination = args.destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"Destination must be new or empty: {destination}")
    runtime = destination / "runtime" / "python"
    runtime.mkdir(parents=True)
    with zipfile.ZipFile(args.python_archive) as archive:
        for info in archive.infolist():
            target = (runtime / info.filename).resolve()
            if not target.is_relative_to(runtime):
                raise RuntimeError("Python archive contains an unsafe path")
        archive.extractall(runtime)
    site = runtime / "Lib" / "site-packages"
    site.mkdir(parents=True)
    for dist in selected:
        for relative, source in distribution_files(dist):
            target = site / str(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    # Embedded Python ignores host PYTHONPATH and the Windows Python registry.
    # ../.. is the project root relative to runtime/python; no local absolute path.
    (runtime / "python311._pth").write_text(
        "python311.zip\n.\nLib\\site-packages\n..\\..\nimport site\n", encoding="ascii"
    )
    smoke = subprocess.run(
        [str(runtime / "python.exe"), "-I", "-c", (
            "import json,sys,pathlib,numpy,shapely,pyproj,yaml,PIL,websockets,requests; "
            "assert pathlib.Path(sys.path[-1])==pathlib.Path(sys.executable).parents[2]; "
            "from playwright.sync_api import sync_playwright; "
            "from shapely.geometry import Point; "
            "from pyproj import Transformer; "
            "assert Point(0,0).distance(Point(3,4))==5; "
            "xy=Transformer.from_crs(4326,32650,always_xy=True).transform(114.17,22.294); "
            "assert all(abs(a-b)<1e-9 for a,b in zip(Transformer.from_crs(32650,4326,always_xy=True).transform(*xy),(114.17,22.294))); "
            "p=sync_playwright().start(); assert p.chromium is not None; p.stop(); "
            "print(json.dumps({'python':sys.version.split()[0],'executable':sys.executable,'isolated':sys.flags.isolated,'sys_path':sys.path,'playwright_driver_started':True}))"
        )],
        cwd=destination, capture_output=True, text=True,
        env={"SystemRoot": str(Path("C:/Windows")), "PATH": str(Path("C:/Windows/System32")),
             "TEMP": str(destination), "TMP": str(destination), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if smoke.returncode:
        raise RuntimeError(f"Isolated runtime validation failed: {smoke.stderr}")
    smoke_result = json.loads(smoke.stdout)
    bundle = destination / "windows-python.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(runtime.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
                archive.write(path, path.relative_to(runtime).as_posix())
    parts_dir = destination / "runtime" / "packages"
    parts_dir.mkdir()
    parts = []
    with bundle.open("rb") as source:
        index = 1
        while chunk := source.read(CHUNK_BYTES):
            part = parts_dir / f"windows-python.zip.part{index:02d}"
            part.write_bytes(chunk)
            parts.append({"file": part.name, "bytes": len(chunk), "sha256": digest(part)})
            index += 1
    manifest = {
        "schema_version": 1,
        "platform": "windows-x86_64",
        "python_version": "3.11.9",
        "python_source": PYTHON_SOURCE,
        "python_archive_sha256": digest(args.python_archive),
        "archive_sha256": digest(bundle), "archive_bytes": bundle.stat().st_size,
        "parts": parts,
        "packages": {row["name"]: row["version"] for row in rows},
        "critical_files": [
            {"file": path.relative_to(runtime).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}
            for path in sorted(runtime.rglob("*"))
            if path.is_file() and (
                path.name in {"python.exe", "python311.dll", "python311._pth", "node.exe", "proj.db", "cli.js"}
                or path.suffix.lower() in {".pyd", ".dll"}
            )
        ],
        "file_count": sum(1 for path in runtime.rglob("*") if path.is_file() and "__pycache__" not in path.parts),
        "expanded_bytes": sum(path.stat().st_size for path in runtime.rglob("*") if path.is_file() and "__pycache__" not in path.parts),
        "notes": [
            "Contains the official Python embedded license and original package wheel licenses/metadata.",
            "Contains Playwright's driver, not a downloaded browser. Uses the user's separately installed AnyLogic Chromium.",
            "Current AIS and AnyLogic workflow only. Historical scipy/pandas/rasterio/Jupyter pipelines are not included.",
        ],
    }
    (parts_dir / "windows-python.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (destination / "requirements-runtime.lock.txt").write_text(
        "# Verified offline runtime; not the historical full-development requirements.\n"
        + "\n".join(f"{row['name']}=={row['version']}" for row in rows) + "\n", encoding="utf-8"
    )
    (destination / "runtime-build-verification.json").write_text(
        json.dumps({"complete": True, "isolated_smoke": smoke_result, "package_scan": rows, "manifest": manifest}, indent=2), encoding="utf-8"
    )
    print(json.dumps({"destination": str(destination), "archive_bytes": manifest["archive_bytes"], "parts": parts, "isolated_smoke": smoke_result}, indent=2), flush=True)


if __name__ == "__main__":
    main()
