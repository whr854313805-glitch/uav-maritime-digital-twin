"""Strict request/error contracts. Does not change physical or planning parameters."""
from datetime import datetime
import math


def number(value, name, *, positive=False, nonnegative=False):
    try:
        finite=type(value) in (int,float) and math.isfinite(value)
    except OverflowError:finite=False
    if not finite:
        raise ValueError(name + ' must be a finite number (not bool)')
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(name + ' is outside its allowed range')
    return value


def coordinates(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(name + ' must contain latitude and longitude')
    lat, lon = [number(x, name) for x in value]
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(name + ' coordinates are outside WGS84 bounds')


def parse_departure(value, *, naive_hong_kong=False):
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise ValueError('Departure must be a nonempty ISO datetime, at most 80 characters')
    try:
        dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        if dt.tzinfo is None:
            if not naive_hong_kong:
                raise ValueError('Departure timezone is required')
            from datetime import timezone, timedelta
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        # UTC conversion and timestamp also detect platform/date overflow.
        from datetime import timezone
        dt = dt.astimezone(timezone.utc)
        number(dt.timestamp(), 'Departure timestamp')
        return dt
    except (TypeError, OverflowError, OSError) as exc:
        raise ValueError('Departure is outside the supported datetime range') from exc


def validate_request(request):
    if not isinstance(request, dict):
        raise ValueError('Request must be a JSON object')
    keys = ('task_id', 'start', 'end', 'speed_mps', 'buffer_m', 'departure_offset_seconds', 'max_expanded_states')
    missing = [k for k in keys if k not in request]
    if missing:
        raise ValueError('Missing request fields: ' + ', '.join(missing))
    task = request['task_id']
    if not isinstance(task, str) or not task.strip() or len(task) > 200 or any(ord(c) < 32 for c in task):
        raise ValueError('task_id must be a nonempty identifier, at most 200 characters')
    for key in ('start', 'end'):
        coordinates(request[key], key)
    policy = request.get('window_policy', 'fixed_600_v1')
    if policy not in ('fixed_600_v1', 'task_coverage_v2', 'observed_segments_v3'):
        raise ValueError('Unsupported window policy')
    for key in ('speed_mps', 'buffer_m'):
        number(request[key], key, positive=True)
    offset = number(request['departure_offset_seconds'], 'departure_offset_seconds', nonnegative=True)
    cap = request.get('max_flight_seconds')
    if cap is not None:
        number(cap, 'max_flight_seconds', positive=True)
    if policy == 'fixed_600_v1' and (offset >= 600 or cap is None):
        raise ValueError('Legacy window requires offset < 600 and a flight budget')
    budget = request['max_expanded_states']
    if type(budget) is not int or not 0 < budget <= 1_000_000:
        raise ValueError('Invalid compatibility search budget')
    if request.get('window_start_utc') is not None:
        parse_departure(request['window_start_utc'])
    points = request.get('research_points')
    if points is not None:
        if not isinstance(points, dict) or not isinstance(points.get('selection_file'), str):
            raise ValueError('research_points selection_file is required')
        digest = points.get('selection_sha256')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('research_points requires a SHA256 identity')
        gates = points.get('gates')
        if not isinstance(gates, list) or len(gates) != 2 or not all(isinstance(g, dict) for g in gates):
            raise ValueError('research_points must contain two gate objects')
        for gate in gates:
            coordinates(gate.get('point'), 'research gate')


def json_safe(value, depth=0):
    """Preserve finite values; label unrepresentable inputs rather than inventing them."""
    if depth > 40:
        return '[invalid: nesting too deep]'
    if isinstance(value, float) and not math.isfinite(value):
        return '[invalid number: ' + str(value) + ']'
    if isinstance(value, dict):
        return {str(k): json_safe(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v, depth + 1) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return '[invalid type: ' + type(value).__name__ + ']'


def validate_result(result, *, capture_id=None, raw_sha256=None):
    if not isinstance(result, dict):
        raise ValueError('Result object is missing')
    if result.get('status') not in ('planned', 'error', 'rejected_data', 'rejected_planning', 'not_tested'):
        raise ValueError('Unknown result status')
    # An explicitly unrun historical entry has no run identity. Do not invent
    # one merely to make its schema look like a completed experiment.
    run_id = result.get('run_id')
    if not (result['status'] == 'not_tested' and run_id is None):
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError('Result run_id is missing')
    if result['status'] != 'error':
        validate_request(result.get('request'))
    if capture_id is not None and result.get('capture_id') != capture_id:
        raise ValueError('Result capture identity mismatch')
    if raw_sha256 is not None and result.get('raw_sha256') != raw_sha256:
        raise ValueError('Result raw AIS identity mismatch')
    if result['status'] == 'planned':
        tr = result.get('trajectory')
        if not isinstance(tr, dict) or not isinstance(result.get('projection'), dict):
            raise ValueError('Planned result needs a trajectory and projection')
        xy, ts = tr.get('xy'), tr.get('times_s')
        if not isinstance(xy, list) or not isinstance(ts, list) or len(xy) != len(ts) or len(xy) < 2:
            raise ValueError('Invalid trajectory cardinality')
        for point in xy:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError('Invalid projected trajectory point')
            for v in point:
                number(v, 'trajectory coordinate')
        for t in ts:
            number(t, 'trajectory time')
        if any(b <= a for a, b in zip(ts, ts[1:])):
            raise ValueError('Trajectory times must increase')
        _validate_success(result)
    elif result.get('trajectory') is not None:
        raise ValueError('Nonplanned result must not contain a trajectory')
    return result


def _same_number(actual, expected, name):
    # Existing trajectory verification uses 1e-6 for numerical consistency.
    # This is not a replacement for the planner's physical clearance tolerance.
    number(actual, name)
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-6):
        raise ValueError('Planned result is inconsistent: ' + name)


def _validate_success(result):
    """Validate the success claim and its duplicated numeric summaries.

    This checks the result contract; the original planner/oracles still perform
    the actual continuous collision and geometry validation.
    """
    from pathlib import Path
    from src.metric_projection import MetricProjection
    from src.project_config import load_config

    if type(result.get('schema_version')) is not int or result['schema_version'] != 1:
        raise ValueError('Unsupported planned result schema')
    if result.get('planner_invoked') is not True or result.get('failure_reason') not in (None, ''):
        raise ValueError('Planned result contradicts its planner/failure status')
    planning, ship, coverage = (result.get(k) for k in ('planning', 'ship_check', 'coverage_check'))
    for obj, key, label in ((planning, 'found', 'planning.found'),
                            (planning, 'geometry_valid', 'planning.geometry_valid'),
                            (ship, 'valid', 'ship_check.valid'),
                            (coverage, 'valid', 'coverage_check.valid')):
        if not isinstance(obj, dict) or obj.get(key) is not True:
            raise ValueError('Planned result requires ' + label + '=true')
    if planning.get('failure_reason') not in (None, '') or ship.get('reason') not in (None, ''):
        raise ValueError('Planned result contains a failed check reason')

    request, tr, projection = result['request'], result['trajectory'], result['projection']
    profile = request.get('parameter_profile')
    if profile not in (None, 'reference_90_15_30_utm_v1'):
        raise ValueError('Unknown planned parameter profile')
    if profile and (request['speed_mps'] != 15 or request['buffer_m'] != 90
                    or projection.get('kind') != 'utm' or projection.get('crs') != 'EPSG:32650'):
        raise ValueError('Planned result contradicts its fixed reference profile')
    coordinates([projection.get('origin_lat'), projection.get('origin_lon')], 'projection origin')
    if projection.get('kind') not in ('utm', 'local_equirectangular'):
        raise ValueError('Unsupported planned projection')
    try:
        pr = MetricProjection({'projection': projection})
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise ValueError('Invalid planned projection') from error

    xy, ts, path = tr['xy'], tr['times_s'], tr.get('path')
    if not isinstance(path, list) or len(path) != len(xy):
        raise ValueError('Geographic and projected trajectory lengths differ')
    for index, (geo, point) in enumerate(zip(path, xy)):
        coordinates(geo, 'trajectory path')
        projected = pr.project(geo)
        for value in projected:
            number(value, 'projected path')
        _same_number(math.dist(projected, point), 0, 'trajectory.path/xy[' + str(index) + ']')
    for name, point in (('start', xy[0]), ('end', xy[-1])):
        _same_number(math.dist(pr.project(request[name]), point), 0, 'request.' + name)

    departure = number(tr.get('departure_s'), 'trajectory.departure_s', nonnegative=True)
    arrival = number(tr.get('arrival_s'), 'trajectory.arrival_s', positive=True)
    if arrival <= departure:
        raise ValueError('Planned arrival must follow departure')
    _same_number(ts[0], departure, 'trajectory departure timestamp')
    _same_number(ts[-1], arrival, 'trajectory arrival timestamp')
    _same_number(departure, request['departure_offset_seconds'], 'request departure offset')
    speed = number(tr.get('speed_mps'), 'trajectory.speed_mps', positive=True)
    _same_number(speed, request['speed_mps'], 'request speed')
    lengths = [math.dist(a, b) for a, b in zip(xy, xy[1:])]
    distance = number(tr.get('distance_m'), 'trajectory.distance_m', positive=True)
    _same_number(distance, math.fsum(lengths), 'trajectory distance')
    for length, ta, tb in zip(lengths, ts, ts[1:]):
        _same_number(length / (tb - ta), speed, 'segment speed')

    data = result.get('data_check')
    if not isinstance(data, dict):
        raise ValueError('Planned result needs a recording window')
    window = number(result.get('window_start_unix_s'), 'window_start_unix_s')
    _same_number(data.get('window_start_unix_s'), window, 'recording window start')
    end = number(data.get('window_end_unix_s'), 'recording window end')
    available = number(data.get('available_seconds'), 'available recording seconds', positive=True)
    _same_number(end - window, available, 'recording window duration')
    if request.get('window_start_utc') is not None:
        _same_number(parse_departure(request['window_start_utc']).timestamp(), window, 'requested window start')
    if arrival > available + 1e-6:
        raise ValueError('Planned trajectory exceeds its recording window')
    cap = request.get('max_flight_seconds')
    if cap is not None and arrival - departure > cap + 1e-6:
        raise ValueError('Planned trajectory exceeds the requested flight budget')
    _same_number(coverage.get('actual_flight_seconds'), arrival - departure, 'coverage flight duration')
    # Historical grid records have a shorter coverage summary. Check every field
    # they do contain, without fabricating new fields in those saved originals.
    for key, expected in (('departure_s', departure), ('arrival_s', arrival), ('available_seconds', available)):
        if key in coverage:
            _same_number(coverage[key], expected, 'coverage.' + key)

    minimum = ship.get('minimum_distance_m')
    if 'minimum_distance_m' not in ship:
        raise ValueError('Planned ship check has no distance/unknown marker')
    if minimum is None:
        if ship.get('nearest_ship') is not None or ship.get('closest_time_s') is not None:
            raise ValueError('Unknown ship distance contradicts a nearest-ship claim')
    else:
        number(minimum, 'minimum ship distance', nonnegative=True)
        config = load_config(Path(__file__).resolve().parents[1] / 'config.yaml')
        tolerance = number(config['planning']['clearance_tolerance_m'], 'clearance tolerance', nonnegative=True)
        if minimum < request['buffer_m'] + tolerance:
            raise ValueError('Successful ship check contradicts the requested clearance')
        closest = number(ship.get('closest_time_s'), 'closest ship time')
        if closest < departure - 1e-6 or closest > arrival + 1e-6:
            raise ValueError('Closest ship time is outside the flight')

    if (planning.get('trajectory') != tr or planning.get('path') != path
            or planning.get('ship_check') != ship):
        raise ValueError('Planning and top-level result disagree')
    _same_number(planning.get('distance_m'), distance, 'planning.distance_m')
