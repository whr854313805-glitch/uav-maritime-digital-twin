"""Versioned departure-search experiment; never edits frozen planner inputs.

The A* route still avoids a single ship snapshot. Continuous validation is
mandatory afterwards. Finer departure sampling is not an optimality proof.
"""
from collections import Counter
import math
import numpy as np
from src.safe_planning import SafePlanner
from src.flight_simulation import (ShipTimeline, parameterize,
    validate_moving_ships, validate_uav_pair)


class DepartureTimePlanner(SafePlanner):
    """Serial, instance-local snapshot adapter over the unchanged A* planner."""
    def __init__(self, config, inputs):
        self.original_frames = inputs['by_minute']
        local_inputs = {**inputs, 'by_minute': [inputs['by_minute'][0]]}
        super().__init__(config, local_inputs)
        self.timeline = ShipTimeline(inputs, self, config['time']['vessel_sample_seconds'])

    def plan_at(self, start, end, departure_s, buffer_m):
        positions = self.timeline.positions(departure_s)
        moving = positions[:len(self.timeline.moving[0])]
        self.inputs['by_minute'] = [[self.unproject(p) for p in moving]]
        return super().plan(start, end, 0, buffer_m)


def departure_delays(step, limit):
    if (type(step) is not int or type(limit) is not int or step <= 0 or limit < 0):
        raise ValueError('Wait step must be a positive integer; limit a nonnegative integer')
    # Always include the exact wait limit, even when not divisible by the step.
    return sorted({*range(0, limit + 1, step), limit})


def schedule_departures(planner, settings, requests):
    delays = departure_delays(settings['wait_step_seconds'], settings['max_wait_seconds'])
    if len({r['task_id'] for r in requests}) != len(requests):
        raise ValueError('Duplicate task ID')
    if any(not math.isfinite(r['requested_s']) or r['requested_s'] < 0 for r in requests):
        raise ValueError('Invalid request time')
    config=planner.config; timeline=planner.timeline
    lookup={c['id']: c for c in config['corridors']}
    priority={cid:i for i,cid in enumerate(settings['priority_order'])}
    separation=config['coordination']; tolerance=config['planning']['clearance_tolerance_m']
    ordered=sorted(requests,key=lambda r:(r['requested_s'],priority.get(r['corridor_id'],999),r['task_id']))
    missions=[]; accepted=[]
    for request in ordered:
        corridor=lookup[request['corridor_id']]; counts=Counter()
        record={**request,'status':'not_scheduled','trajectory':None,'wait_s':None,
                'failure_reason':None,'attempts':[]}
        for delay in delays:
            departure=request['requested_s']+delay
            attempt={'departure_s':departure,'wait_s':delay,'reason':None}
            record['attempts'].append(attempt)
            if departure > timeline.horizon_s:
                attempt['reason']='ship_data_horizon_exceeded'
                counts[attempt['reason']]+=1;break
            distances=np.linalg.norm(timeline.positions(departure)-np.asarray(planner.project(corridor['waypoints'][0])),axis=1)
            attempt['start_minimum_ship_distance_m']=float(min(distances)) if len(distances) else None
            plan=planner.plan_at(corridor['waypoints'][0],corridor['waypoints'][-1],departure,corridor['buffer_m'])
            if not plan['found']:
                attempt['reason']=plan['failure_reason'];counts[attempt['reason']]+=1;continue
            trajectory=parameterize(plan['path'],departure,corridor['speed_mps'],planner,corridor['altitude_m'])
            attempt['trajectory']=trajectory
            ship_check=validate_moving_ships(trajectory,timeline,corridor['buffer_m'],tolerance)
            attempt['ship_check']=ship_check
            if not ship_check['valid']:
                attempt['reason']=ship_check['reason'];counts[attempt['reason']]+=1
                if ship_check['reason']=='ship_data_horizon_exceeded':break
                continue
            pairs=[{'task_id':f['task_id'],**validate_uav_pair(trajectory,f['trajectory'],separation['horizontal_separation_m'],separation['vertical_separation_m'],tolerance)} for f in accepted]
            attempt['pair_checks']=pairs
            if any(not p['valid'] for p in pairs):
                attempt['reason']='uav_separation';counts[attempt['reason']]+=1;continue
            independent_ship=validate_moving_ships(trajectory,timeline,corridor['buffer_m'],tolerance,independent=True)
            independent_pairs=[validate_uav_pair(trajectory,f['trajectory'],separation['horizontal_separation_m'],separation['vertical_separation_m'],tolerance,independent=True) for f in accepted]
            if not independent_ship['valid'] or any(not p['valid'] for p in independent_pairs):
                raise RuntimeError('Analytic and independent validation disagree')
            attempt['reason']='accepted'
            record.update(status='scheduled',trajectory=trajectory,wait_s=delay,
                          ship_check=independent_ship,dynamic_ship_valid=True,
                          dynamic_uav_valid=True,frozen_geometry_valid=plan['geometry_valid'])
            accepted.append(record);break
        record['rejection_counts']=dict(counts)
        if record['status']!='scheduled':
            record['failure_reason']='ship_data_horizon_exceeded' if counts['ship_data_horizon_exceeded'] else 'wait_limit_exhausted'
        missions.append(record)
    return missions
