"""Restore the exact reviewed offline inputs; no network, planning or credentials."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def restore(root=ROOT, recover_latest=False):
    root = Path(root).resolve()
    (root/'.local/data-bootstrap.json').unlink(missing_ok=True)
    manifest_path = root / 'runtime/data/current-data.manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    archive = root / 'runtime/data/current-data.zip'
    if sha(archive) != manifest['archive_sha256']:
        raise ValueError('Offline data archive is damaged. Download the complete repository again.')
    restored = []
    with zipfile.ZipFile(archive) as z:
        for record in manifest['files']:
            name = record['path']
            target = (root / name).resolve()
            if not target.is_relative_to(root) or not name.startswith(('data/', 'output/')):
                raise ValueError('Unexpected offline input path: ' + name)
            if target.is_file():
                if sha(target) == record['sha256']:
                    continue
                # A newly computed latest result is intentional. Keep it; catalog()
                # and the verifier check its own input identity independently.
                if name == 'output/ais_single_task/latest.json':
                    sys.path.insert(0, str(root))
                    from src.validation import validate_result
                    try:
                        candidate = json.loads(target.read_text(encoding='utf-8-sig'))
                        original = json.loads(z.read(name))
                        validate_result(candidate, capture_id=original['capture_id'], raw_sha256=original['raw_sha256'])
                        if candidate.get('projection') != original.get('projection'):
                            raise ValueError('latest.json projection differs from the fixed reference')
                        from src.validation import number
                        number(candidate.get('window_start_unix_s'), 'latest window origin')
                    except (ValueError, TypeError, KeyError, OSError) as error:
                        if not recover_latest:
                            raise ValueError('latest.json is invalid: '+str(error)+'. Run scripts/bootstrap_project.py --recover-latest to preserve it and restore the original saved default.') from error
                        import uuid
                        backup = root / '.local/recovery' / ('latest-' + uuid.uuid4().hex + '.json')
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, backup)
                        if sha(backup) != sha(target):
                            raise ValueError('Recovery backup verification failed')
                        print('Invalid latest preserved at '+str(backup)+'; restoring original saved default, not claiming a new planning success.')
                    else:
                        continue
                else:
                    raise ValueError('Reviewed input was changed: ' + name + '. Preserve your changes before restoring a fresh copy.')
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=target.name + '.', suffix='.tmp', dir=target.parent)
            temp = Path(temporary)
            try:
                with os.fdopen(fd, 'wb') as out, z.open(name) as source:
                    shutil.copyfileobj(source, out)
                if temp.stat().st_size != record['bytes'] or sha(temp) != record['sha256']:
                    raise ValueError('Offline input integrity check failed: ' + name)
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)
            restored.append(name)
    local = root / '.local'
    local.mkdir(exist_ok=True)
    (local / 'data-bootstrap.json').write_text(json.dumps({
        'complete': True, 'manifest_sha256': sha(manifest_path),
        'reviewed_files': len(manifest['files']), 'restored_files': restored,
        'scope': 'Exact original bytes restored; no source data or model parameter changed.'
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Offline inputs ready: ' + str(len(manifest['files'])) + ' reviewed files.')


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, default=ROOT)
    parser.add_argument('--recover-latest', action='store_true')
    args = parser.parse_args()
    try:
        sys.path.insert(0,str(args.project.resolve()))
        from src.release_checks import verify_release
        verify_release(args.project)
        restore(args.project,args.recover_latest)
    except Exception as error:
        print('Data setup failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
