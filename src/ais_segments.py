"""Observed segments only: no holding, extrapolation, or gap bridging.

Linear interpolation already exists in the project. MovingPandas' trajectory
interpolate_position_at is a method reference, not transplanted source code.
"""
import math

OBSERVED_SEGMENTS = 'observed_segments_v3'


def select_segments(bundle, start, required_seconds, end):
    if not math.isfinite(required_seconds) or required_seconds <= 0:
        raise ValueError('Task duration must be positive and finite')
    start = bundle['start'] if start is None else start
    end = bundle['end'] if end is None else end
    valid = (start is not None and end is not None and
             bundle['start'] <= start < end <= bundle['end'] and end-start >= required_seconds)
    tracks = {}
    vessels = []
    for v in bundle['vessels']:
        segments = [s for s in v['segments'] if valid and
                    s[0]['timestamp_unix_s'] <= end and s[-1]['timestamp_unix_s'] >= start]
        if segments:
            tracks[v['mmsi']] = segments
        intervals = [{'start':s[0]['timestamp_unix_s'], 'end':s[-1]['timestamp_unix_s'],
                      'duration_seconds':s[-1]['timestamp_unix_s']-s[0]['timestamp_unix_s'],
                      'observations':len(s), 'max_gap_seconds':max(
                          (b['timestamp_unix_s']-a['timestamp_unix_s'] for a,b in zip(s,s[1:])), default=0)}
                     for s in v['segments']]
        vessels.append({'mmsi':v['mmsi'], 'observation_count':len(v['points']),
                        'continuous_intervals':intervals,
                        'longest_seconds':max((s['duration_seconds'] for s in intervals), default=0),
                        'selected_for_planning':bool(segments),
                        'reason':None if segments else 'no_supported_position_in_window',
                        'conflicting_observation_count':len(v['conflicting_points'])})
    return {'status':'observed_segments_available' if tracks else 'insufficient_real_data',
            'rule_version':OBSERVED_SEGMENTS, 'required_seconds':required_seconds,
            'required_duration_kind':'recording_time_span_not_contiguous_ship_coverage',
            'available_seconds':end-start if valid else None,
            'window_start_unix_s':start if valid else None, 'window_end_unix_s':end if valid else None,
            'quality_parameters':{k:v for k,v in bundle['quality_parameters'].items() if k!='window_seconds'},
            'observed_vessels':bundle['vessel_count'], 'selected_vessels':sorted(tracks),
            'longest_contiguous_seconds':bundle['longest_contiguous_seconds'],
            'vessels':vessels, 'gaps':bundle['breaks'],
            'scope':'All valid overlapping observations/segments; missing positions unknown. No real-world safety claim.'}, tracks


def coverage_report(check, departure_s, arrival_s):
    """Report each recorded vessel, including ones with no task-time support."""
    start = check['window_start_unix_s']+departure_s
    end = check['window_start_unix_s']+arrival_s
    duration = end-start
    rows = []
    any_support = []
    for v in check['vessels']:
        intervals = [(max(start,s['start']),min(end,s['end'])) for s in v['continuous_intervals']
                     if s['start']<=end and s['end']>=start]
        unknown = []; cursor = start
        for a,b in intervals:
            if a>cursor: unknown.append([cursor,a])
            cursor=max(cursor,b)
            if b>a: any_support.append((a,b))
        if cursor<end: unknown.append([cursor,end])
        supported=sum(b-a for a,b in intervals)
        rows.append({'mmsi':v['mmsi'], 'has_task_observation':bool(intervals),
                     'supported_seconds':supported, 'unknown_seconds':max(0,duration-supported),
                     'supported_intervals_unix_s':intervals, 'unknown_intervals_unix_s':unknown})
    union=[]
    for a,b in sorted(any_support):
        if union and a<=union[-1][1]:union[-1][1]=max(union[-1][1],b)
        else:union.append([a,b])
    return {'scope':'recorded_vessels_only_not_all_regional_vessels',
            'status':'unknown_positions_present' if any(r['unknown_seconds']>1e-6 for r in rows) else 'recorded_vessels_supported',
            'real_world_safety_verified':False, 'task_duration_seconds':duration,
            'task_participating_vessels':[r['mmsi'] for r in rows if r['has_task_observation']],
            'fully_supported_vessels':[r['mmsi'] for r in rows if r['unknown_seconds']<=1e-6],
            'vessels_with_unknown_positions':sum(r['unknown_seconds']>1e-6 for r in rows),
            'seconds_without_any_supported_ship':max(0,duration-sum(b-a for a,b in union)),
            'vessels':rows}
