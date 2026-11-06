"""One offline historical task, gated by unchanged AIS quality requirements.

Reuse: ais_replay segmentation, ObservedTimeline, original TemporalPlanner and
its independent continuous closest-approach validation. No new search algorithm.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import uuid
import sys
from src.validation import json_safe

from src.ais_data import digest, timestamp
from src.ais_replay import build_capture, replace_json
from src.project_config import load_config
from src.temporal_planning import TemporalPlanner
from src.ais_segments import OBSERVED_SEGMENTS, select_segments, coverage_report
from src.metric_projection import MetricProjection

def apply_reference_profile(config,request):
    if request.get('parameter_profile')=='reference_90_15_30_utm_v1':
        if request['speed_mps']!=15 or request['buffer_m']!=90:
            raise ValueError('Reference profile requires speed15 and total ship radius90')
        config['projection']={'kind':'utm','crs':'EPSG:32650','proj4':'+proj=utm +zone=50 +datum=WGS84 +units=m +no_defs',
                              'origin_lat':22.295,'origin_lon':114.195}
        config['planning']['building_buffer_m']=30
    elif request.get('parameter_profile'):
        raise ValueError('Unknown parameter profile')
    return config

PROJECT = Path(__file__).resolve().parents[1]
REQUIRED_QUALITY = {'window_seconds': 600, 'max_gap_seconds': 120,
                    'max_speed_mps': 30, 'max_report_age_seconds': 120, 'max_future_seconds': 5}
TASK_COVERAGE = 'task_coverage_v2'
FIXED_WINDOW = 'fixed_600_v1'


def select_window(bundle, start=None, *, policy=FIXED_WINDOW, required_seconds=600, end=None):
    """Select a reproducible observed subset; retain the old audit as v1."""
    if bundle['quality_parameters'] != REQUIRED_QUALITY:
        raise ValueError('quality_parameters_changed: required 600/120/30/120/5')
    if policy == OBSERVED_SEGMENTS:
        return select_segments(bundle, start, required_seconds, end)
    if policy == FIXED_WINDOW:
        fragments = bundle['qualified_fragments']
        required_seconds = 600
        if start is None:
            start = min((f['start'] for f in fragments), default=None)
        end = start + 600 if start is not None else None
    elif policy == TASK_COVERAGE:
        if not math.isfinite(required_seconds) or required_seconds <= 0:
            raise ValueError('Task coverage requires a positive finite duration')
        fragments = [{'mmsi':v['mmsi'], 'segment_index':i,
                      'start':s[0]['timestamp_unix_s'], 'end':s[-1]['timestamp_unix_s']}
                     for v in bundle['vessels'] for i,s in enumerate(v['segments']) if len(s)>=2]
        candidates = [f for f in fragments if
                      (f['start'] <= start <= f['end'] and f['end']-start >= required_seconds
                       if start is not None else f['end']-f['start'] >= required_seconds)]
        if start is None and candidates:
            # Deterministic longest available segment; not chosen for route success.
            best = min(candidates, key=lambda f: (-(f['end']-f['start']), f['start'], f['mmsi']))
            start = best['start']
        if end is None:
            end = max((f['end'] for f in candidates if f['start']<=start and f['end']-start>=required_seconds), default=None) if start is not None else None
        if start is None or end is None or end-start < required_seconds:
            end = None
    else:
        raise ValueError('Unsupported window policy')
    selected = {}
    lookup = {v['mmsi']: v for v in bundle['vessels']}
    for fragment in fragments:
        if start is not None and end is not None and fragment['start'] <= start and fragment['end'] >= end:
            selected[fragment['mmsi']] = lookup[fragment['mmsi']]['segments'][fragment['segment_index']]
    vessels = []
    for vessel in bundle['vessels']:
        intervals = []
        for segment in vessel['segments']:
            gaps = [b['timestamp_unix_s'] - a['timestamp_unix_s'] for a, b in zip(segment, segment[1:])]
            intervals.append({'start': segment[0]['timestamp_unix_s'], 'end': segment[-1]['timestamp_unix_s'],
                              'duration_seconds': segment[-1]['timestamp_unix_s'] - segment[0]['timestamp_unix_s'],
                              'observations': len(segment), 'max_gap_seconds': max(gaps, default=0)})
        longest = max((s['duration_seconds'] for s in intervals), default=0)
        vessels.append({'mmsi': vessel['mmsi'], 'observation_count': len(vessel['points']),
                        'continuous_intervals': intervals, 'longest_seconds': longest,
                        'selected_for_planning': vessel['mmsi'] in selected,
                        'reason': None if vessel['mmsi'] in selected else
                        ('no_600s_contiguous_fragment' if policy == FIXED_WINDOW else 'insufficient_task_duration')
                        if longest < required_seconds else 'does_not_cover_selected_window',
                        'conflicting_observation_count': len(vessel['conflicting_points'])})
    return {'status': 'qualified_observed_subset' if selected else 'insufficient_real_data',
            'rule_version': policy, 'required_seconds': required_seconds,
            'required_duration_kind': 'fixed_window' if policy == FIXED_WINDOW else 'straight_flight_lower_bound_plus_departure_offset',
            'available_seconds': end-start if end is not None else None,
            'quality_parameters': {k:v for k,v in REQUIRED_QUALITY.items() if k!='window_seconds'},
            'window_start_unix_s': start, 'window_end_unix_s': end,
            'observed_vessels': bundle['vessel_count'], 'selected_vessels': sorted(selected),
            'longest_contiguous_seconds': bundle['longest_contiguous_seconds'],
            'vessels': vessels, 'gaps': bundle['breaks'],
            'scope': 'Only qualified observed subset; excluded ships remain unknown, not obstacle-free.'}, selected


def export_window(directory, source, bundle, check, tracks):
    """Persist an auditable adapter snapshot; never copy/fabricate ship positions."""
    quality = {'status': 'usable_observed_subset', 'quality_parameters': check['quality_parameters'],
               'selection_method': 'overlapping_segments' if check['rule_version']==OBSERVED_SEGMENTS else 'contiguous_fragments',
               'rule_version': check['rule_version'], 'required_seconds': check['required_seconds'],
               'window_start_unix_s': check['window_start_unix_s'],
               'window_end_unix_s': check['window_end_unix_s'],
               'tracks_sha256': hashlib.sha256(json.dumps(tracks, sort_keys=True, allow_nan=False).encode()).hexdigest()}
    replace_json(directory / 'quality.json', quality)
    path = directory / 'observed_tracks.json'
    replace_json(path, {'provider': 'AISStream', 'source_capture_directory': str(source.resolve()),
                        'raw_sha256': bundle['raw_sha256'], 'quality': quality, 'tracks': tracks})
    return path


class PlanarObservedPlanner(TemporalPlanner):
    """Official OMPL SST search with the original geometry/timeline checkers; wind excluded."""
    def wind_at(self, point):
        return 0.0  # Excluded term, not a claim of measured calm weather.

    def edge_objective_cost(self,length,wind,distance,buffer):
        return length  # Safety is a hard constraint, not a competing soft cost.

    def plan_corridor(self,corridor,departure_s,reservations=()):
        from src.ompl_sst import solve
        return solve(self,corridor,departure_s,reservations)


def load_environment(root, config):
    path = root / config['data']['buildings']
    manifest_path = root / config['data']['official_manifest']
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if digest(path) != manifest['derived_hashes'][path.name]:
        raise ValueError('Official building snapshot hash mismatch')
    # Check preserved building source files, excluding unrelated weather/terrain.
    for name, expected in manifest['raw_hashes'].items():
        if name.startswith('buildings_') and name.endswith('.geojson'):
            if digest(manifest_path.parent / 'raw' / name) != expected:
                raise ValueError('Official raw building hash mismatch: ' + name)
    buildings = json.loads(path.read_text(encoding='utf-8'))
    for building in buildings['buildings']:
        building['height_m'] = None  # Every footprint blocks; ignore height in this entry only.
    return {'buildings': buildings, 'wind': {'stations': [], 'scope': 'excluded_not_measured_zero'},
            'static_vessels': []}, {'buildings_path': str(path), 'buildings_sha256': digest(path),
                                   'manifest_sha256': digest(manifest_path),
                                   'building_count': len(buildings['buildings']),
                                   'geometry': 'existing conservative footprint envelopes, all heights blocked',
                                   'wind': 'excluded; not historical weather validation'}


def validate_request(request):
    from src.validation import validate_request as strict_validate
    strict_validate(request)


def run_task(source, request, root=PROJECT, publish=True):
    """Report this attempt; publish only source-verified displayable defaults."""
    source, root = Path(source), Path(root)
    directory = root / 'output/ais_single_task/runs' / uuid.uuid4().hex
    result = {'schema_version': 1, 'run_id': directory.name, 'status': 'error',
              'created_at_utc': datetime.now(timezone.utc).isoformat(), 'request': json_safe(deepcopy(request)), 'capture_id': None, 'raw_sha256': None,
              'planner_invoked': False, 'trajectory': None, 'ship_check': None,
              'data_check': None, 'failure_reason': None,
              'experiment': 'Offline recorded-trajectory experiment, not future prediction or real flight safety.'}
    try:
        directory.mkdir(parents=True)
        validate_request(request)
        points = request.get('research_points')
        if points:
            selection_path=(root/points['selection_file']).resolve()
            if not selection_path.is_relative_to(root.resolve()) or digest(selection_path)!=points['selection_sha256']:
                raise ValueError('Research point selection hash/path mismatch')
            selection=json.loads(selection_path.read_text(encoding='utf-8'))
            if (selection['status']!='selected' or selection['gates']!=points['gates'] or
                    [g['point'] for g in selection['gates']]!=[request['start'],request['end']]):
                raise ValueError('Task endpoints differ from recorded research point selection')
        policy = request.get('window_policy', FIXED_WINDOW)
        result['rule_version'] = policy
        config = load_config(root / 'config.yaml')
        apply_reference_profile(config,request)
        if request.get('parameter_profile'):
            ledger=root/'config/parameter-sources.json'
            if ledger.exists():
                result['parameter_provenance']={'file':'config/parameter-sources.json','sha256':digest(ledger),
                    'profile':request['parameter_profile'],'status':'sourced_references_and_explicit_assumptions_not_all_measured'}
        result['base_config_sha256'] = digest(root / 'config.yaml')
        coordinates=MetricProjection(config)
        minimum_flight=math.dist(coordinates.project(request['start']),coordinates.project(request['end']))/request['speed_mps']
        if minimum_flight<=0:raise ValueError('zero_length_flight')
        bundle = build_capture(source)
        manifest = json.loads((source / 'capture.json').read_text(encoding='utf-8'))
        if manifest['status'] != 'captured':
            raise ValueError('A fully completed capture is required for planning')
        result.update(capture_id=bundle['capture_id'], raw_sha256=bundle['raw_sha256'],
                      capture_manifest_sha256=digest(source / 'capture.json'),
                      evidence_kind='protocol_fixture_not_real' if manifest.get('test_fixture_not_real_data') else 'saved_AISStream_capture')
        check, tracks = select_window(bundle, timestamp(request['window_start_utc']) if request.get('window_start_utc') else None,
                                      policy=policy, required_seconds=request['departure_offset_seconds']+minimum_flight)
        check['minimum_flight_seconds'] = minimum_flight
        result['data_check'] = check
        if not tracks:
            result.update(status='rejected_data', failure_reason='no_qualified_600s_observed_window'
                          if policy==FIXED_WINDOW else 'no_recording_window_covering_minimum_task_time'
                          if policy==OBSERVED_SEGMENTS else 'no_observed_window_covering_minimum_task_time')
        else:
            snapshot = export_window(directory, source, bundle, check, tracks)
            config['planning']['wind_cost_weight'] = 0
            inputs, environment = load_environment(root, config)
            inputs['observed_tracks_path'] = snapshot
            inputs['ompl_request'] = deepcopy(request)
            inputs['ompl_output_dir'] = directory
            inputs['ompl_runtime_dir'] = root / 'runtime/ompl' if (root / 'runtime/ompl').exists() else PROJECT / 'runtime/ompl'
            result['environment'] = environment
            result['projection'] = config['projection']
            replace_json(directory / 'planning_config.json', config)
            remaining = check['available_seconds'] - request['departure_offset_seconds']
            flight_cap = request.get('max_flight_seconds')
            settings = {'max_expanded_states':request['max_expanded_states'],
                        'max_flight_seconds': min(remaining, flight_cap) if flight_cap is not None else remaining,
                        'max_refinement_evaluations':256}
            result['search_settings'] = settings
            planner = PlanarObservedPlanner(config, inputs, settings)
            corridor = {'id': request['task_id'], 'waypoints': [request['start'], request['end']],
                        'speed_mps': request['speed_mps'], 'buffer_m': request['buffer_m'], 'altitude_m': 0}
            result['planner_invoked'] = True
            planned = planner.plan_corridor(corridor, request['departure_offset_seconds'])
            result['planning'] = planned
            if planned['found']:
                tr = planned['trajectory']
                covered = 0 <= tr['departure_s'] <= tr['arrival_s'] <= planner.timeline.horizon_s
                result['coverage_check'] = {'valid':covered, 'available_seconds':planner.timeline.horizon_s,
                                            'departure_s':tr['departure_s'], 'arrival_s':tr['arrival_s'],
                                            'actual_flight_seconds':tr['arrival_s']-tr['departure_s']}
                if not covered:raise RuntimeError('Actual planned flight exceeds observed coverage')
                result.update(status='planned', trajectory=planned['trajectory'], ship_check=planned['ship_check'],
                              window_start_unix_s=check['window_start_unix_s'],
                              projection=config['projection'])
                if policy == OBSERVED_SEGMENTS:
                    result['observation_coverage'] = coverage_report(check, tr['departure_s'], tr['arrival_s'])
                    result['coverage_check']['scope'] = 'inside_recording_time_span_only_not_complete_ship_coverage'
                    result['ship_check']['scope'] = 'supported_observations_and_interpolated_segments_only'
            else:
                result.update(status='rejected_planning', failure_reason=planned['failure_reason'])
        if result['status'] == 'planned':
            from src.validation import validate_result
            validate_result(result)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, OverflowError) as error:
        result.update(status='error', failure_reason=str(error), trajectory=None, ship_check=None)
    try:
        result['code_sha256'] = {name: digest(PROJECT / name) for name in
                                 ['src/ais_single_task.py', 'src/metric_projection.py', 'src/ais_segments.py', 'src/ais_replay.py', 'src/ais_data.py',
                                  'src/temporal_planning.py', 'src/ompl_sst.py', 'src/safe_planning.py', 'src/flight_simulation.py',
                                  'src/validation.py', 'src/workspace_catalog.py']}
        replace_json(directory / 'result.json', result)
        if publish:
            from src.workspace_catalog import publish_result
            try:
                publish_result(root, result)
            except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
                # A completed calculation and a failed publication are separate.
                # In particular, never rewrite result.json as error after its
                # valid planned copy has already reached latest.json.
                failure = dict(result, status='error', failure_reason='result_publish_failed: '+str(error),
                               trajectory=None, ship_check=None)
                print(json.dumps(json_safe(failure), ensure_ascii=True, allow_nan=False), file=sys.stderr)
                try:
                    replace_json(directory / 'publication_error.json', failure)
                except (ValueError, TypeError, OSError):
                    pass
                return failure
    except (ValueError, TypeError, OSError) as error:
        result.update(status='error', failure_reason='result_write_failed: '+str(error), trajectory=None, ship_check=None)
        print(json.dumps(json_safe(result), ensure_ascii=True, allow_nan=False), file=sys.stderr)
        try:
            replace_json(directory / 'result.json', result)
        except (ValueError, TypeError, OSError):
            pass  # The caller still receives a structured failure; no old success.
    return result
