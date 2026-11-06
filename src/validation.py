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
    if not isinstance(result, dict) or not isinstance(result.get('run_id'), str):
        raise ValueError('Result object/run_id is missing')
    if result.get('status') not in ('planned', 'error', 'rejected_data', 'rejected_planning', 'not_tested'):
        raise ValueError('Unknown result status')
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
    elif result.get('trajectory') is not None:
        raise ValueError('Nonplanned result must not contain a trajectory')
    return result
