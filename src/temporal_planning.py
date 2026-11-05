"""Bounded multi-label A* over grid position AND exact arrival time.

Constant cruise speed, eight grid directions, exact endpoint connectors,
known piecewise-linear ships and previously reserved UAV trajectories.
No hovering, vertical dynamics, time rounding or forecast is introduced.
"""
from collections import Counter
import heapq
import itertools
import math
import numpy as np
from src.safe_planning import SafePlanner,point_segment_distance,validate_path
from src.flight_simulation import ShipTimeline,parameterize,validate_moving_ships,validate_uav_pair


class MovingOnlyTimeline:
    def __init__(self,timeline):
        self.timeline=timeline
        self.sample_seconds=timeline.sample_seconds
        self.horizon_s=timeline.horizon_s
        self.count=timeline.moving.shape[1]
        self.ids=timeline.ids[:self.count]
        if hasattr(timeline,'breakpoints_s'):
            self.breakpoints_s=timeline.breakpoints_s
        self.segmented=getattr(timeline,'segmented',False)
        if self.segmented:
            self.interval_positions=timeline.interval_positions

    def positions(self,t):
        return self.timeline.positions(t)[:self.count]


class TemporalPlanner(SafePlanner):
    def edge_objective_cost(self,length,wind,distance,buffer):
        """Legacy weighted objective; planar AIS overrides this with path length."""
        soft=max(0,(1.5*buffer-distance)/buffer)
        return length*(1+self.settings['wind_cost_weight']*wind/self.settings['wind_threshold_mps']+self.settings['ship_soft_cost_weight']*soft)

    def __init__(self,config,inputs,search_settings):
        super().__init__(config,inputs)
        self.search_settings=dict(search_settings)
        cap=self.search_settings['max_expanded_states']
        duration=self.search_settings['max_flight_seconds']
        if type(cap) is not int or cap<=0 or not math.isfinite(duration) or duration<=0:
            raise ValueError('Positive expansion cap and finite flight-time limit required')
        if 'observed_tracks_path' in inputs:
            from src.ais_data import ObservedTimeline
            if inputs.get('static_vessels') or 'by_minute' in inputs:
                raise ValueError('Observed mode cannot mix legacy synthetic vessel inputs')
            self.timeline=ObservedTimeline(inputs['observed_tracks_path'],self)
        else:
            self.timeline=ShipTimeline(inputs,self,config['time']['vessel_sample_seconds'])
        self.moving_timeline=MovingOnlyTimeline(self.timeline)
        self.static_ship_cache={}

    def _static_edge(self,a,b,buffer_m):
        valid,wind=self.static_edge(a,b)
        if not valid:return None
        key=(tuple(sorted((a,b))),buffer_m)
        if key not in self.static_ship_cache:
            self.static_ship_cache[key]=min((point_segment_distance(p,a,b) for p in self.static_ships),default=math.inf)
        distance=self.static_ship_cache[key]
        if distance<buffer_m+self.settings['clearance_tolerance_m']:return None
        return wind,distance

    def plan_corridor(self,corridor,departure_s,reservations=()):
        start,end=map(list,(corridor['waypoints'][0],corridor['waypoints'][-1]))
        a,b=self.project(start),self.project(end)
        speed= float(corridor['speed_mps']);buffer=float(corridor['buffer_m']);altitude=float(corridor['altitude_m'])
        if not all(math.isfinite(v) for v in [departure_s,speed,buffer,altitude]) or departure_s<0 or speed<=0 or buffer<=0:
            raise ValueError('Invalid time, speed, buffer or altitude')
        stats={'expanded_states':0,'checked_edges':0,'pruned':Counter(),'time_model':'exact_arrival_from_constant_speed_grid_lengths','hovering':False}
        def fail(reason):
            return {'found':False,'failure_reason':reason,'geometry_valid':None,'path':None,'trajectory':None,'search':stats}
        minimum_duration=math.dist(a,b)/speed
        if departure_s+minimum_duration>self.timeline.horizon_s:return fail('ship_data_horizon_exceeded')
        if minimum_duration>self.search_settings['max_flight_seconds']:return fail('flight_time_limit_exhausted')
        for label,p in [('start',a),('end',b)]:
            if not self.inside(p):return fail(label+'_outside_region')
            if not self.static_edge(p,p)[0]:return fail(label+'_building_or_wind_constraint')
        if a==b:return fail('zero_length_flight')
        if any(math.dist(a,p)<buffer+self.settings['clearance_tolerance_m'] for p in self.timeline.positions(departure_s)):
            return fail('start_ship_buffer')
        finish_limit=min(self.timeline.horizon_s,departure_s+self.search_settings['max_flight_seconds'])
        tolerance=self.settings['clearance_tolerance_m'];separation=self.config['coordination']
        active=[r for r in reservations if abs(r['altitude_m']-altitude)<separation['vertical_separation_m']
                and r['arrival_s']>=departure_s and r['departure_s']<=finish_limit]

        def edge(p,q,ta,tb):
            stats['checked_edges']+=1
            if tb>finish_limit+1e-9:
                stats['pruned']['time_limit']+=1;return None
            fixed=self._static_edge(p,q,buffer)
            if fixed is None:stats['pruned']['static_geometry_or_wind']+=1;return None
            segment={'xy':[p,q],'times_s':[ta,tb],'departure_s':ta,'arrival_s':tb,'altitude_m':altitude}
            ships=validate_moving_ships(segment,self.moving_timeline,buffer,tolerance)
            if not ships['valid']:
                stats['pruned'][ships['reason']]+=1;return None
            if any(not validate_uav_pair(segment,r,separation['horizontal_separation_m'],separation['vertical_separation_m'],tolerance)['valid'] for r in active):
                stats['pruned']['uav_separation']+=1;return None
            distance=min(fixed[1],ships['minimum_distance_m'] if ships['minimum_distance_m'] is not None else math.inf)
            return self.edge_objective_cost(math.dist(p,q),fixed[0],distance,buffer)

        # For each start anchor, arrival is fully determined by the numbers of
        # orthogonal and diagonal steps. This exact integer label avoids merging
        # distinct arrivals into a coarse time bin. All future edges depend only
        # on this arrival and location, so lowest cost dominates identical labels.
        anchors=self.anchors(a);offsets=[math.dist(a,self.node_point(n))/speed for n in anchors]
        straight_dt=self.step/speed;diagonal_dt=self.step*math.sqrt(2)/speed
        def arrival(state):
            _,anchor,orthogonal,diagonal=state
            return departure_s+math.fsum([offsets[anchor],orthogonal*straight_dt,diagonal*diagonal_dt])
        frontier=[];counter=itertools.count();costs={};parents={};best_goal=math.inf;goal_parent=None
        direct=edge(a,b,departure_s,departure_s+minimum_duration)
        if direct is not None:
            best_goal=direct;heapq.heappush(frontier,(direct,direct,next(counter),None))
        for index,node in enumerate(anchors):
            point=self.node_point(node);time=departure_s+offsets[index]
            cost=edge(a,point,departure_s,time)
            if cost is None:continue
            state=(node,index,0,0);costs[state]=cost;parents[state]=None
            heapq.heappush(frontier,(cost+math.dist(point,b),cost,next(counter),state))
        goal_nodes=set(self.anchors(b))
        while frontier:
            _,cost,_,state=heapq.heappop(frontier)
            if state is None:
                if cost>best_goal+1e-9:continue
                chain=[];current=goal_parent
                while current is not None:
                    chain.append(self.unproject(self.node_point(current[0])));current=parents[current]
                path=[start]+list(reversed(chain))+[end]
                trajectory=parameterize(path,departure_s,speed,self,altitude)
                # Frozen moving-ship geometry is deliberately not a constraint.
                # Static ships/buildings are checked independently over the line.
                geometry=validate_path(trajectory['path'],start,end,self.static_ships,buffer+tolerance,self.config,self.inputs['buildings']['buildings'],self)
                if not geometry['geometry_valid']:raise RuntimeError('Independent static validation failed')
                ships=validate_moving_ships(trajectory,self.timeline,buffer,tolerance,independent=True)
                pairs=[validate_uav_pair(trajectory,r,separation['horizontal_separation_m'],separation['vertical_separation_m'],tolerance,independent=True) for r in active]
                if not ships['valid'] or any(not p['valid'] for p in pairs):raise RuntimeError('Independent whole-trajectory validation failed')
                return {'found':True,'failure_reason':None,'path':trajectory['path'],'trajectory':trajectory,
                        'geometry_valid':True,'distance_m':trajectory['distance_m'],'ship_check':ships,'search':stats}
            if cost>costs[state]+1e-9:continue
            if stats['expanded_states']>=self.search_settings['max_expanded_states']:return fail('search_budget_exhausted')
            stats['expanded_states']+=1
            node,anchor,orthogonal,diagonal=state;p=self.node_point(node);ta=arrival(state)
            if ta+math.dist(p,b)/speed>finish_limit+1e-9:
                stats['pruned']['time_limit']+=1;continue
            if node in goal_nodes:
                extra=edge(p,b,ta,ta+math.dist(p,b)/speed)
                if extra is not None and cost+extra<best_goal:
                    best_goal=cost+extra;goal_parent=state
                    heapq.heappush(frontier,(best_goal,best_goal,next(counter),None))
            row,col=node
            for dr,dc in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                neighbor=(row+dr,col+dc)
                if not (0<=neighbor[0]<self.rows and 0<=neighbor[1]<self.cols):continue
                diagonal_move=int(dr!=0 and dc!=0)
                candidate=(neighbor,anchor,orthogonal+1-diagonal_move,diagonal+diagonal_move)
                q=self.node_point(neighbor);tb=arrival(candidate)
                if tb+math.dist(q,b)/speed>finish_limit+1e-9:
                    stats['pruned']['time_limit']+=1;continue
                extra=edge(p,q,ta,tb)
                if extra is None:continue
                new_cost=cost+extra
                if new_cost>=best_goal or new_cost>=costs.get(candidate,math.inf)-1e-9:continue
                costs[candidate]=new_cost;parents[candidate]=state
                heapq.heappush(frontier,(new_cost+math.dist(q,b),new_cost,next(counter),candidate))
        if stats['pruned']['time_limit']:
            # Exhausting a horizon-bounded search does not prove that a later
            # departure cannot use a shorter route after a ship has moved.
            return fail('search_horizon_exhausted' if finish_limit==self.timeline.horizon_s else 'flight_time_limit_exhausted')
        return fail('no_temporal_grid_path')


def schedule_temporal(planner,settings,requests):
    from src.departure_search import departure_delays
    delays=departure_delays(settings['wait_step_seconds'],settings['max_wait_seconds'])
    if len({r['task_id'] for r in requests})!=len(requests):raise ValueError('Duplicate task IDs')
    if any(not math.isfinite(r['requested_s']) or r['requested_s']<0 for r in requests):raise ValueError('Invalid request time')
    priority={cid:i for i,cid in enumerate(settings['priority_order'])}
    lookup={c['id']:c for c in planner.config['corridors']}
    ordered=sorted(requests,key=lambda r:(r['requested_s'],priority.get(r['corridor_id'],999),r['task_id']))
    missions=[];reserved=[]
    for request in ordered:
        corridor=lookup[request['corridor_id']];counts=Counter()
        record={**request,'status':'not_scheduled','trajectory':None,'wait_s':None,'failure_reason':None,'attempts':[]}
        for delay in delays:
            departure=request['requested_s']+delay
            planned=planner.plan_corridor(corridor,departure,reserved)
            attempt={'departure_s':departure,'wait_s':delay,'reason':planned['failure_reason'],'search':planned['search']}
            record['attempts'].append(attempt)
            if departure<=planner.timeline.horizon_s:
                ds=np.linalg.norm(planner.timeline.positions(departure)-np.asarray(planner.project(corridor['waypoints'][0])),axis=1)
                attempt['start_minimum_ship_distance_m']=float(min(ds)) if len(ds) else None
            if not planned['found']:
                counts[planned['failure_reason']]+=1
                if planned['failure_reason']=='ship_data_horizon_exceeded':break
                continue
            trajectory=planned['trajectory'];attempt.update(reason='accepted',trajectory=trajectory,ship_check=planned['ship_check'])
            record.update(status='scheduled',trajectory=trajectory,wait_s=delay,ship_check=planned['ship_check'],dynamic_ship_valid=True,dynamic_uav_valid=True,static_geometry_valid=True)
            reserved.append(trajectory);break
        record['rejection_counts']=dict(counts)
        if record['status']!='scheduled':
            record['failure_reason']='ship_data_horizon_exceeded' if counts['ship_data_horizon_exceeded'] else 'search_budget_exhausted' if counts['search_budget_exhausted'] else 'flight_time_limit_exhausted' if counts['flight_time_limit_exhausted'] else 'search_horizon_exhausted' if counts['search_horizon_exhausted'] else 'wait_limit_exhausted'
        missions.append(record)
        print(request['task_id'],record['status'],'wait',record['wait_s'],'attempts',len(record['attempts']),flush=True)
    return missions
