"""Synchronize derived catalog metadata without rebuilding frozen display data."""
from contextlib import contextmanager
from pathlib import Path
import json
import msvcrt
import time

from src.ais_replay import replace_json
from src.release_checks import sha, verify_workspace
from src.validation import number, validate_request, validate_result


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


@contextmanager
def catalog_lock(root, timeout=20):
    path = Path(root) / '.local/catalog.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if not path.stat().st_size:
            stream.write(b'0'); stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Another result publication is still running; retry after it finishes')
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def validate_current(root, result, workspace=None, reference=None):
    """A default must be displayable and source-verified, including failures."""
    root = Path(root)
    ref = reference if reference is not None else read(root / 'output/research_points/study/M2/result.json') if workspace else None
    source = workspace['source'] if workspace else ref
    validate_result(result, **({'capture_id': source['capture_id'],
                               'raw_sha256': source['raw_sha256']} if source else {}))
    validate_request(result.get('request'))
    if not result.get('capture_id') or not result.get('raw_sha256') or result['status'] == 'not_tested':
        raise ValueError('Default result needs verified AIS identity and an actual attempt')
    if ref:
        if result.get('projection') is not None and result['projection'] != ref['projection']:
            raise ValueError('latest.json projection differs from the fixed reference')
        if result['status'] == 'planned' and result.get('projection') != ref['projection']:
            raise ValueError('Planned latest.json needs the fixed projection')
        if result.get('window_start_unix_s') is not None:
            number(result['window_start_unix_s'], 'latest window origin')
    return result


def _workspace(root, workspace=None):
    workspace = workspace if workspace is not None else read(root / 'anylogic/workbench/workspace.json')
    verify_workspace(root, workspace)
    provenance = read(root / 'anylogic/workbench/provenance.json')
    if (provenance.get('raw_sha256') != workspace['source']['raw_sha256']
            or provenance.get('scene') != workspace['source']
            or provenance.get('background_png_sha256') != sha(root / 'anylogic/harbour_background.png')):
        raise ValueError('Workspace provenance/source/background mismatch')
    return workspace, provenance


def _items(root, workspace):
    from src.anylogic_workspace import catalog
    items = catalog(root)
    previous = workspace.get('catalog')
    if not isinstance(previous, list):
        raise ValueError('Workspace catalog is missing')
    indexed = {item['key']: item for item in previous}
    if len(indexed) != len(previous) or set(indexed) != {item['key'] for item in items}:
        raise ValueError('Workspace catalog keys differ from saved results')
    for item in items:
        if item['key'] == 'current':
            validate_current(root, read(root / 'output' / item['file']), workspace)
        elif indexed[item['key']] != item:
            raise ValueError('Frozen saved catalog differs: ' + item['key'])
    return items


def _write(root, workspace, provenance, items):
    path = root / 'anylogic/workbench/workspace.json'
    if workspace['catalog'] != items:
        workspace = dict(workspace, catalog=items)
        replace_json(path, workspace)
    expected = sha(path)
    if provenance.get('workspace_sha256') != expected:
        replace_json(root / 'anylogic/workbench/provenance.json', dict(provenance, workspace_sha256=expected))
    return workspace, items


def synchronize_locked(root, workspace=None):
    """Caller holds catalog_lock; only validated current metadata may change."""
    root = Path(root).resolve()
    workspace, provenance = _workspace(root, workspace)
    return _write(root, workspace, provenance, _items(root, workspace))


def synchronize(root, workspace=None):
    with catalog_lock(root):
        return synchronize_locked(root, workspace)


def publish_result(root, result):
    """Serialize publishers/readers; a valid latest can repair an interrupted sync."""
    root = Path(root).resolve()
    with catalog_lock(root):
        path = root / 'anylogic/workbench/workspace.json'
        if not path.exists():
            # Data-only callers have no display cache to synchronize.
            validate_current(root, result)
            replace_json(root / 'output/ais_single_task/latest.json', result)
            return
        workspace, provenance = _workspace(root)
        _items(root, workspace)  # Refuse corrupt frozen entries before publication.
        validate_current(root, result, workspace)
        replace_json(root / 'output/ais_single_task/latest.json', result)
        _write(root, workspace, provenance, _items(root, workspace))
