"""Release identity and derived-display verification; no planning changes."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import math


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def release_identity(root):
    manifest=json.loads((Path(root)/'FILE_MANIFEST.json').read_text(encoding='utf-8-sig'))
    mutable={'anylogic/workbench/workspace.json','anylogic/workbench/provenance.json'}
    rows=[r for r in manifest['files'] if r['path'] not in mutable and
          (r['path'].startswith(('src/','anylogic/','config/','scripts/','runtime/ompl/')) or '/' not in r['path'] and r['path'].endswith('.py'))]
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def verify_release(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'FILE_MANIFEST.json').read_text(encoding='utf-8-sig'))
    mutable = {'anylogic/workbench/workspace.json', 'anylogic/workbench/provenance.json'}
    checked = 0
    for row in manifest['files']:
        rel = row['path']
        if rel in mutable:
            continue
        if not (rel.startswith(('src/', 'anylogic/', 'config/', 'scripts/', 'runtime/ompl/')) or '/' not in rel and rel.endswith('.py')):
            continue
        file = (root / rel).resolve()
        if not file.is_relative_to(root) or not file.is_file() or file.stat().st_size != row['bytes'] or sha(file) != row['sha256']:
            raise ValueError('Release file identity mismatch: ' + rel)
        checked += 1
    required = {'anylogic/native-visual-demo.jar', 'anylogic/loopback-agent.jar', 'src/validation.py', 'src/release_checks.py'}
    if not required.issubset({row['path'] for row in manifest['files']}):
        raise ValueError('Release manifest is missing required security components')
    return {'immutable_files_verified': checked, 'release_sha256':release_identity(root)}


def _equal(actual, expected, path):
    if isinstance(expected, float):
        good = type(actual) in (int, float) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-6)
    elif isinstance(expected, dict):
        good = isinstance(actual, dict) and actual.keys() == expected.keys()
        if good:
            for key in expected:
                _equal(actual[key], expected[key], path + '.' + key)
    elif isinstance(expected, list):
        good = isinstance(actual, list) and len(actual) == len(expected)
        if good:
            for i, (a, b) in enumerate(zip(actual, expected)):
                _equal(a, b, path + '[' + str(i) + ']')
    else:
        good = type(actual) is type(expected) and actual == expected
    if not good:
        raise ValueError('Derived workspace differs from raw AIS: ' + path)


def verify_workspace(root, workspace=None):
    from src.ais_replay import build_capture
    from src.metric_projection import MetricProjection
    root = Path(root).resolve()
    read = lambda p: json.loads(Path(p).read_text(encoding='utf-8-sig'))
    workspace = workspace if workspace is not None else read(root / 'anylogic/workbench/workspace.json')
    capture_id = workspace.get('source', {}).get('capture_id')
    if not isinstance(capture_id, str) or len(capture_id) != 32 or any(c not in '0123456789abcdef' for c in capture_id):
        raise ValueError('Invalid workspace capture identity')
    bundle = build_capture(root / 'data/ais/captures' / capture_id)
    if workspace['source'].get('raw_sha256') != bundle['raw_sha256']:
        raise ValueError('Workspace raw AIS identity mismatch')
    # Projection comes from a fixed accepted result, not from a mutable latest file.
    ref = read(root / 'config/ais-single-task.json')
    from src.project_config import load_config
    from src.ais_single_task import apply_reference_profile
    projection = apply_reference_profile(load_config(root / 'config.yaml'), ref)['projection']
    pr = MetricProjection({'projection': projection})
    def point(p):
        q = deepcopy(p)
        q['xy'] = list(pr.project([p['latitude'], p['longitude']]))
        q['t'] = p['timestamp_unix_s'] - bundle['start']
        return q
    vessels = [{'mmsi': v['mmsi'], 'points': [point(p) for p in v['points']],
                'segments': [[point(p) for p in seg] for seg in v['segments']]} for v in bundle['vessels']]
    _equal(workspace.get('vessels'), vessels, 'vessels')
    for key, value in [('origin', bundle['start']), ('end', bundle['end']), ('duration', bundle['end'] - bundle['start'])]:
        _equal(workspace.get(key), value, key)
    return {'vessels_checked': len(vessels), 'raw_points_checked': bundle['valid_position_count'],
            'coordinates_times_and_segments_match_raw_AIS': True}
