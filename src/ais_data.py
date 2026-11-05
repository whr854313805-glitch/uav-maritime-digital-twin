"""AISStream-only acquisition and offline audit. No synthetic fallback.

Protocol: https://aisstream.io/documentation
Interpolation/QC thresholds are project assumptions, not service guarantees.
"""
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid

ENDPOINT = 'wss://stream.aisstream.io/v0/stream'
POSITION_TYPES = ('PositionReport', 'StandardClassBPositionReport', 'ExtendedClassBPositionReport')


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def timestamp(value):
    # Provider time_utc is provider message time, not a full on-board GNSS timestamp.
    text = str(value).strip().removesuffix(' UTC').replace('Z', '+00:00')
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError('timezone_missing')
    return dt.timestamp()


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    south, west, north, east = config['bbox']
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError('Invalid bbox')
    numbers = [config['capture_seconds'], *config['quality'].values()]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in numbers):
        raise ValueError('Quality and capture limits must be positive finite numbers')
    return config


def load_key(root):
    value = os.environ.get('AISSTREAM_API_KEY', '').strip()
    if value:
        return value
    path = Path(root)/'.env.local'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.strip().partition('=')
            if sep and name == 'AISSTREAM_API_KEY':
                value = value.strip().strip('"\'')
                if value and value != 'REPLACE_LOCALLY':
                    return value
    raise ValueError('缺少 AISSTREAM_API_KEY。请在工程 .env.local 本地填写；不要发到聊天中。')


def collect(root, config, key, connector=None):
    """One bounded TLS connection. Failures remain explicit; rerun creates a new capture."""
    if not key:
        raise ValueError('API key required')
    if connector is None:
        from websockets.sync.client import connect
        connector = connect
    directory = Path(root)/'data/ais/captures'/uuid.uuid4().hex
    directory.mkdir(parents=True)
    manifest = {'schema_version': 1, 'provider': 'AISStream', 'endpoint': ENDPOINT,
                'started_at_utc': utcnow(), 'status': 'collecting', 'config': config,
                'subscription_confirmed': False, 'message_count': 0,
                'raw_format': 'JSONL: local receipt time plus decoded original response text; secrets redacted if echoed',
                'time_basis': 'provider time_utc; local receipt time retained separately',
                'transport_library': 'websockets 15.0.1; TLS verification on; permessage-deflate'}
    raw = directory/'messages.jsonl'
    dump(directory/'capture.json', manifest)
    try:
        with raw.open('w', encoding='utf-8') as out:
            with connector(ENDPOINT, compression='deflate', open_timeout=10, close_timeout=2, max_size=2**20) as ws:
                south, west, north, east = config['bbox']
                ws.send(json.dumps({'APIKey': key, 'BoundingBoxes': [[[south, west], [north, east]]],
                                    'FilterMessageTypes': list(POSITION_TYPES)}))
                # Never log the outbound subscription: it contains the secret.
                start = time.monotonic()
                while time.monotonic()-start < config['capture_seconds']:
                    remaining = config['capture_seconds']-(time.monotonic()-start)
                    try:
                        message = ws.recv(timeout=min(2, remaining))
                    except TimeoutError:
                        if not manifest['subscription_confirmed'] and time.monotonic()-start > 10:
                            raise ValueError('subscription_confirmation_timeout')
                        continue
                    text = message.decode('utf-8') if isinstance(message, bytes) else message
                    safe_text = text.replace(key, '[REDACTED]')
                    out.write(json.dumps({'received_at_utc': utcnow(), 'payload': safe_text}, ensure_ascii=False)+'\n')
                    out.flush()
                    manifest['message_count'] += 1
                    msg = json.loads(text)
                    if 'error' in msg or 'Error' in msg:
                        raise ValueError('provider_subscription_error; inspect preserved redacted response')
                    if msg.get('MessageType') == 'SubscriptionConfirmation':
                        if not msg.get('Message', {}).get('CompressionEnabled'):
                            raise ValueError('compression_not_confirmed')
                        manifest['subscription_confirmed'] = True
                    if manifest['message_count'] % 100 == 0:
                        print('AIS received messages:', manifest['message_count'], flush=True)
        manifest['status'] = 'captured' if manifest['subscription_confirmed'] else 'failed'
    except KeyboardInterrupt:
        manifest.update(status='interrupted', error='capture_interrupted; partial observations retained')
    except Exception as error:
        manifest.update(status='failed', error=str(error).replace(key, '[REDACTED]'))
    manifest.update(finished_at_utc=utcnow(), raw_sha256=digest(raw), raw_bytes=raw.stat().st_size)
    dump(directory/'capture.json', manifest)
    return directory, manifest


def normalize(envelope, config):
    msg = json.loads(envelope['payload'])
    kind = msg.get('MessageType')
    if kind not in POSITION_TYPES:
        raise ValueError('not_position_report')
    payload = msg.get('Message', {}).get(kind, {})
    if payload.get('Valid') is False:
        raise ValueError('provider_invalid_position')
    meta = msg.get('MetaData', {})
    mmsi = str(meta['MMSI'])
    if len(mmsi) != 9 or not mmsi.isdecimal() or mmsi == '000000000':
        raise ValueError('invalid_mmsi')
    if 'UserID' in payload and str(payload['UserID']) != mmsi:
        raise ValueError('mmsi_mismatch')
    # Do not substitute metadata's potentially last-known position for message coordinates.
    lat, lon = float(payload['Latitude']), float(payload['Longitude'])
    south, west, north, east = config['bbox']
    if not (math.isfinite(lat) and math.isfinite(lon) and south <= lat <= north and west <= lon <= east):
        raise ValueError('invalid_or_outside_bbox')
    t = timestamp(meta['time_utc']);received = timestamp(envelope['received_at_utc'])
    age = received-t
    if age > config['quality']['max_report_age_seconds'] or age < -config['quality']['max_future_seconds']:
        raise ValueError('stale_or_future_report')
    return {'mmsi': mmsi, 'timestamp_unix_s': t, 'latitude': lat, 'longitude': lon,
            'received_at_utc': envelope['received_at_utc'], 'message_type': kind,
            'classification': 'provider_reported_AIS_position'}


def distance_m(a, b):
    lat1,lat2 = map(math.radians, [a['latitude'], b['latitude']])
    dlat = lat2-lat1;dlon = math.radians(b['longitude']-a['longitude'])
    h = math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000*2*math.asin(min(1, math.sqrt(h)))


def audit(directory, start_utc=None):
    directory = Path(directory)
    manifest = json.loads((directory/'capture.json').read_text(encoding='utf-8'))
    if manifest['endpoint'] != ENDPOINT or not manifest['subscription_confirmed']:
        raise ValueError('Not a confirmed AISStream capture')
    if digest(directory/'messages.jsonl') != manifest['raw_sha256']:
        raise ValueError('Raw capture hash mismatch')
    config = manifest['config'];q = config['quality']
    dropped = Counter();groups = defaultdict(list)
    for line in (directory/'messages.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            point = normalize(json.loads(line), config)
            groups[point['mmsi']].append(point)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            dropped[str(error)] += 1
    excluded = {};usable = {}
    for mmsi, points in groups.items():
        points.sort(key=lambda p:p['timestamp_unix_s'])
        unique = {};conflict = False
        for p in points:
            t = p['timestamp_unix_s']
            if t in unique:
                if (p['latitude'],p['longitude']) != (unique[t]['latitude'],unique[t]['longitude']):
                    conflict = True
                else:
                    dropped['duplicate'] += 1
            unique[t] = p
        points = list(unique.values())
        if conflict:
            excluded[mmsi] = 'conflicting_positions_same_timestamp';continue
        if len(points) < 2:
            excluded[mmsi] = 'too_few_observations';continue
        gaps = [b['timestamp_unix_s']-a['timestamp_unix_s'] for a,b in zip(points,points[1:])]
        if max(gaps) > q['max_gap_seconds']:
            excluded[mmsi] = 'observation_gap_exceeded';continue
        if any(distance_m(a,b)/dt > q['max_speed_mps'] for a,b,dt in zip(points,points[1:],gaps)):
            excluded[mmsi] = 'position_jump_exceeded';continue
        if points[-1]['timestamp_unix_s']-points[0]['timestamp_unix_s'] < q['window_seconds']:
            excluded[mmsi] = 'track_duration_insufficient';continue
        usable[mmsi] = points
    start = timestamp(start_utc) if start_utc else min((p[0]['timestamp_unix_s'] for p in usable.values()),default=None)
    end = start+q['window_seconds'] if start is not None else None
    selected = {}
    for mmsi, points in usable.items():
        if points[0]['timestamp_unix_s'] <= start and points[-1]['timestamp_unix_s'] >= end:
            selected[mmsi] = points
        else:
            excluded[mmsi] = 'does_not_cover_selected_window'
    status = 'usable_observed_subset' if selected else 'insufficient_real_data'
    report = {'schema_version':1, 'status':status, 'capture_status':manifest['status'],
              'source_raw_sha256':manifest['raw_sha256'], 'source_raw_bytes':manifest['raw_bytes'],
              'observed_vessels':len(groups), 'selected_vessels':len(selected), 'excluded_vessels':excluded,
              'discarded_messages':dict(dropped), 'quality_parameters':q,
              'window_start_unix_s':start, 'window_end_unix_s':end,
              'scope':'selected observed vessels only; not complete regional coverage or actual flight safety',
              'timing':'provider time_utc, not independently verified GNSS event time',
              'interpolation':'piecewise linear between retained observations; derived positions are not observations',
              'experiment':'offline known-recorded-trajectory experiment, not live prediction',
              'parameter_basis':'project data-quality thresholds; not official AIS accuracy or legal limits'}
    report['tracks_sha256'] = hashlib.sha256(json.dumps(selected,sort_keys=True,allow_nan=False).encode()).hexdigest()
    dump(directory/'quality.json',report)
    # No exported dataset when qualification fails; old/synthetic inputs are never substituted.
    snapshot = directory/'observed_tracks.json'
    if selected:
        dump(snapshot, {'schema_version':1,'provider':'AISStream','endpoint':ENDPOINT,
                        'raw_sha256':manifest['raw_sha256'],'quality':report,'tracks':selected})
    elif snapshot.exists():
        # Keep previous output as historical evidence, but never report it as this audit's result.
        report['stale_snapshot_present_do_not_use'] = True
        dump(directory/'quality.json',report)
    return report


class ObservedTimeline:
    """Exact piecewise-linear local XY interpolation at irregular observed times."""
    def __init__(self, snapshot, projection):
        import numpy as np
        data = json.loads(Path(snapshot).read_text(encoding='utf-8'))
        directory = Path(snapshot).parent
        current = json.loads((directory/'quality.json').read_text(encoding='utf-8'))
        raw_directory = Path(data.get('source_capture_directory', directory))
        if current != data['quality'] or digest(raw_directory/'messages.jsonl') != data['raw_sha256']:
            raise ValueError('Stale snapshot or raw capture changed; run audit again')
        if 'source_capture_directory' in data:
            # New fragment export: reproduce selection from preserved raw evidence,
            # rather than trusting a self-declared quality label or edited track hash.
            from src.ais_replay import build_capture
            from src.ais_single_task import select_window
            check, expected = select_window(build_capture(raw_directory), current['window_start_unix_s'],
                                            policy=current.get('rule_version', 'fixed_600_v1'),
                                            required_seconds=current.get('required_seconds', 600),
                                            end=current['window_end_unix_s'])
            if (expected != data['tracks'] or not expected or
                    check['window_end_unix_s'] != current['window_end_unix_s']):
                raise ValueError('Fragment snapshot does not reproduce from raw capture')
        if hashlib.sha256(json.dumps(data['tracks'],sort_keys=True,allow_nan=False).encode()).hexdigest() != current['tracks_sha256']:
            raise ValueError('Normalised tracks changed; run audit again')
        if data['quality']['status'] != 'usable_observed_subset' or not data['tracks']:
            raise ValueError('Observed dataset not qualified')
        self.origin_s = data['quality']['window_start_unix_s']
        self.horizon_s = data['quality']['window_end_unix_s']-self.origin_s
        self.ids = sorted(data['tracks']);self.sample_seconds = None
        self.tracks = []
        self.segmented = current.get('rule_version') == 'observed_segments_v3'
        self.segment_tracks = []
        cuts = {0.,self.horizon_s}
        for mmsi in self.ids:
            if self.segmented:
                segments=[]
                for points in data['tracks'][mmsi]:
                    ts=[p['timestamp_unix_s']-self.origin_s for p in points]
                    xy=[projection.project([p['latitude'],p['longitude']]) for p in points]
                    if (not ts or any(b<=a or b-a>120 for a,b in zip(ts,ts[1:]))
                            or not np.isfinite(xy).all()):
                        raise ValueError('Invalid observed segment')
                    cuts.update(t for t in ts if 0<=t<=self.horizon_s)
                    segments.append((ts,xy))
                self.segment_tracks.append(segments)
                continue
            points = data['tracks'][mmsi]
            ts = [p['timestamp_unix_s']-self.origin_s for p in points]
            xy = [projection.project([p['latitude'],p['longitude']]) for p in points]
            if ts[0] > 0 or ts[-1] < self.horizon_s or any(b<=a for a,b in zip(ts,ts[1:])):
                raise ValueError('Invalid observed time coverage')
            if not np.isfinite(xy).all():
                raise ValueError('Non-finite projected coordinates')
            cuts.update(t for t in ts if 0 < t < self.horizon_s)
            self.tracks.append((ts,xy))
        self.breakpoints_s = sorted(cuts)
        # Compatibility: existing wrapper only uses moving.shape[1] for vessel count.
        self.moving = np.empty((0,len(self.ids),2));self.static = np.empty((0,2))

    def positions(self,t):
        import numpy as np
        if not math.isfinite(t) or t < 0 or t > self.horizon_s:
            raise ValueError('Observed ship horizon exceeded; no extrapolation')
        if self.segmented:
            return self.interval_positions(t,t)[1]
        positions = []
        for ts,xy in self.tracks:
            i = min(len(ts)-2,max(0,bisect_right(ts,t)-1))
            q = (t-ts[i])/(ts[i+1]-ts[i])
            positions.append([a+(b-a)*q for a,b in zip(xy[i],xy[i+1])])
        return np.asarray(positions)

    def interval_positions(self,ta,tb):
        """Stable IDs for the segments supporting this entire elementary interval.

        The caller splits at every observation. Never connect separate segments,
        even when positions exist at BOTH ends of a long missing interval.
        Zero duration checks preserve isolated actual observations.
        """
        import numpy as np
        if not (0<=ta<=tb<=self.horizon_s):
            raise ValueError('Observed ship horizon exceeded; no extrapolation')
        ids=[];a=[];b=[]
        def at(ts,xy,t):
            if len(ts)==1:return xy[0]
            i=min(len(ts)-2,max(0,bisect_right(ts,t)-1))
            q=(t-ts[i])/(ts[i+1]-ts[i])
            return [x+(y-x)*q for x,y in zip(xy[i],xy[i+1])]
        for mmsi,segments in zip(self.ids,self.segment_tracks):
            for ts,xy in segments:
                if ts[0]<=ta and tb<=ts[-1]:
                    ids.append(mmsi);a.append(at(ts,xy,ta));b.append(at(ts,xy,tb));break
        return ids,np.asarray(a,dtype=float).reshape((-1,2)),np.asarray(b,dtype=float).reshape((-1,2))
