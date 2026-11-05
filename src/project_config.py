"""One configuration and validated frozen inputs for planning and presentation."""
from collections import defaultdict
from pathlib import Path
import csv
import json
import math
import hashlib
from datetime import datetime
import yaml

ROOT = Path(__file__).resolve().parents[1]

def load_config(path=None):
    path = Path(path) if path else ROOT / 'config.yaml'
    config = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
    p, r = config['planning'], config['region']
    positive = ['grid_step_m', 'wind_sample_step_m', 'wind_threshold_mps']
    if any(not math.isfinite(float(p[k])) or p[k] <= 0 for k in positive):
        raise ValueError('Planning scale and thresholds must be finite and positive')
    if r['lat_min'] >= r['lat_max'] or r['lon_min'] >= r['lon_max']:
        raise ValueError('Invalid study bounds')
    ids = [c['id'] for c in config['corridors']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate corridor ID')
    for c in config['corridors']:
        if c['buffer_m'] <= 0 or c['speed_mps'] <= 0 or len(c['waypoints']) < 2:
            raise ValueError('Invalid corridor')
    return config

def load_inputs(config, root=ROOT):
    data = config['data']
    positions = defaultdict(list)
    with (root / data['vessel_positions']).open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            point = [float(row['latitude']), float(row['longitude'])]
            if not all(math.isfinite(v) for v in point):
                raise ValueError('Non-finite vessel position')
            positions[row['vessel_id']].append(point)
    duration = config['time']['duration_minutes']
    if not positions or any(len(v) != duration for v in positions.values()):
        raise ValueError('Each vessel must have exactly duration_minutes samples')
    order = sorted(positions)
    by_minute = [[positions[vid][minute] for vid in order] for minute in range(duration)]
    result = {'vessel_order': order, 'by_minute': by_minute}
    with (root / data['vessel_metadata']).open(encoding='utf-8-sig', newline='') as f:
        result['vessel_metadata'] = {row['vessel_id']:row for row in csv.DictReader(f)}
    for key in ['static_vessels', 'wind', 'buildings']:
        result[key] = json.loads((root / data[key]).read_text(encoding='utf-8-sig'))
    stations = result['wind'].get('stations', [])
    if not stations or any(not all(math.isfinite(float(s[k])) for k in ['speed','lat','lon']) or s['speed'] < 0 for s in stations):
        raise ValueError('Missing or invalid wind observations: no implicit fallback')
    mode=config.get('weather',{}).get('mode','climatology')
    if mode not in ('climatology','observation_snapshot'):
        raise ValueError('Unsupported wind mode: live streaming is not implemented')
    kind=result['wind'].get('source_kind','climatology')
    if mode=='observation_snapshot':
        if kind!='observation':
            raise ValueError('Observation mode requires observed data; refusing substitute')
        for station in stations:
            observed=datetime.fromisoformat(station['observed_at'])
            if observed.tzinfo is None or station.get('unit')!='m/s' or station.get('source_kind')!='observation':
                raise ValueError('Observation requires timezone, m/s and source label')
        from src.hko_weather import parse_station_locations,parse_wind_csv
        try:
            raw_wind=(root/data['wind_raw']).read_bytes()
            raw_stations=(root/data['station_coordinates_raw']).read_bytes()
        except (KeyError,OSError) as error:
            raise ValueError('Observed wind requires preserved raw CSV and station coordinates') from error
        expected=result['wind']['raw_hashes']
        if hashlib.sha256(raw_wind).hexdigest()!=expected['wind'] or hashlib.sha256(raw_stations).hexdigest()!=expected['stations']:
            raise ValueError('Saved weather raw hash mismatch')
        parsed,excluded=parse_wind_csv(raw_wind,parse_station_locations(raw_stations))
        if parsed!=stations or excluded!=result['wind']['excluded_records']:
            raise ValueError('Normalised observations do not reproduce from preserved official raw data')
    elif kind=='observation':
        raise ValueError('Observed wind must use explicit observation_snapshot mode')
    if 'official_manifest' in data:
        directory=(root/data['official_manifest']).parent
        manifest=json.loads((root/data['official_manifest']).read_text(encoding='utf-8'))
        for name,digest in manifest['raw_hashes'].items():
            if hashlib.sha256((directory/'raw'/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('Official raw file hash mismatch: '+name)
        for name,digest in manifest['derived_hashes'].items():
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('Official derived file hash mismatch: '+name)
        result['official_data']={k:manifest[k] for k in ['snapshot_id','received_buildings','unknown_height_buildings','fairway_features','registry_records','source_attribution']}
        for key in ['fairways','vessel_registry','terrain_metadata','ferry_reference','ferry_piers']:
            if key in data:result[key]=json.loads((root/data[key]).read_text(encoding='utf-8'))
    return result
