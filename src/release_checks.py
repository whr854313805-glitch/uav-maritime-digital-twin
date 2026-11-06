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
          (r['path'].startswith(('src/','anylogic/','config/','scripts/','runtime/ompl/'))
           or r['path']=='runtime/data/current-data.manifest.json' or '/' not in r['path'] and r['path'].endswith('.py'))]
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
        if not (rel.startswith(('src/', 'anylogic/', 'config/', 'scripts/', 'runtime/ompl/'))
                or rel == 'runtime/data/current-data.manifest.json' or '/' not in rel and rel.endswith('.py')):
            continue
        file = (root / rel).resolve()
        if not file.is_relative_to(root) or not file.is_file() or file.stat().st_size != row['bytes'] or sha(file) != row['sha256']:
            raise ValueError('Release file identity mismatch: ' + rel)
        checked += 1
    required = {'anylogic/native-visual-demo.jar', 'anylogic/loopback-agent.jar', 'src/validation.py',
                'src/release_checks.py', 'src/workspace_catalog.py', 'runtime/data/current-data.manifest.json'}
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
        raise ValueError('Derived workspace differs from approved inputs: ' + path)


def workspace_geometry(root, projection):
    """Derive display geometry from the reviewed frozen selections and region.

    Never use editable workspace coordinates as the expected values. Checking
    the original input manifest also rejects a study/selection changed in step
    with a damaged workspace.
    """
    from src.metric_projection import MetricProjection
    from src.project_config import load_config
    from src.validation import coordinates, number

    root = Path(root).resolve()
    manifest = json.loads((root / 'runtime/data/current-data.manifest.json').read_text(encoding='utf-8-sig'))
    records = {row['path']: row for row in manifest['files']}

    def frozen(name):
        row = records.get(name)
        file = (root / name).resolve()
        if (not row or not file.is_relative_to(root) or not file.is_file()
                or file.stat().st_size != row['bytes'] or sha(file) != row['sha256']):
            raise ValueError('Frozen display input identity mismatch: ' + name)
        return json.loads(file.read_text(encoding='utf-8-sig'))

    study = frozen('output/research_points/study/study.json')
    tasks = study.get('tasks')
    if (not isinstance(tasks, list) or [task.get('id') for task in tasks] != ['M1', 'M2', 'M3', 'M4']
            or study.get('point_count') != 8 or study.get('task_count') != 4):
        raise ValueError('Frozen display study must contain the original eight points/four tasks')
    pr = MetricProjection({'projection': projection})
    sites = []
    for task in tasks:
        selection = frozen('output/research_points/study/' + task['id'] + '/selection.json')
        gates = selection.get('gates')
        if (selection.get('status') != 'selected' or not isinstance(gates, list) or len(gates) != 2
                or task.get('gates') != gates):
            raise ValueError('Display study and frozen selection disagree: ' + task['id'])
        for index, gate in enumerate(gates):
            coordinates(gate['point'], 'frozen research point')
            anchor = gate['anchor']
            coordinates([anchor['lat'], anchor['lon']], 'frozen pier anchor')
            sites.append({'task': task['id'], 'role': '起点' if index == 0 else '终点',
                          'point': deepcopy(gate['point']), 'xy': list(pr.project(gate['point'])),
                          'anchor': deepcopy(anchor),
                          'anchor_xy': list(pr.project([anchor['lat'], anchor['lon']])),
                          'offset_m': gate['offset_m']})

    region = load_config(root / 'config.yaml')['region']
    south, north, west, east = [number(region[key], 'display region')
                               for key in ('lat_min', 'lat_max', 'lon_min', 'lon_max')]
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError('Invalid fixed display region')
    corners = [pr.project([lat, lon]) for lat in (south, north) for lon in (west, east)]
    bounds = [min(p[0] for p in corners), max(p[0] for p in corners),
              min(p[1] for p in corners), max(p[1] for p in corners)]
    return sites, bounds


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
    sites, bounds = workspace_geometry(root, projection)
    _equal(workspace.get('sites'), sites, 'sites')
    # Source coordinates/metadata are frozen exactly; the metre-based derived
    # XY values above retain the established 1e-6 numerical tolerance.
    for actual, expected in zip(workspace['sites'], sites):
        for key in ('point', 'anchor', 'offset_m'):
            if actual[key] != expected[key]:
                raise ValueError('Frozen display site differs: ' + key)
    _equal(workspace.get('bounds'), bounds, 'bounds')
    return {'vessels_checked': len(vessels), 'raw_points_checked': bundle['valid_position_count'],
            'coordinates_times_and_segments_match_raw_AIS': True,
            'frozen_sites_and_anchors_checked': len(sites), 'fixed_region_bounds_verified': True}
