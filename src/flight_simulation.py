"""Offline trajectory execution and reservation scheduling against moving ships.

Exact closest approach for the declared piecewise-linear kinematic model.
No forecasts, acceleration, vertical takeoff, real flight control or online
unexpected-observation response is claimed.
"""
from bisect import bisect_right
from collections import Counter
import math
import numpy as np

def parameterize(path, departure_s, speed_mps, projection, altitude_m):
    if not math.isfinite(speed_mps) or speed_mps<=0:
        raise ValueError('Speed must be positive')
    if not path or len(path)<2:
        raise ValueError('A flight requires an explicit path')
    points=[projection.project(p) for p in path]
    times=[float(departure_s)];kept=[list(path[0])];xy=[points[0]]
    for p,ll in zip(points[1:],path[1:]):
        distance=math.dist(xy[-1],p)
        if distance<1e-8:continue
        times.append(times[-1]+distance/speed_mps);xy.append(p);kept.append(list(ll))
    if len(times)<2:raise ValueError('Zero-length flight')
    return {'times_s':times,'path':kept,'xy':xy,'altitude_m':float(altitude_m),'departure_s':times[0],'arrival_s':times[-1],'distance_m':sum(math.dist(a,b) for a,b in zip(xy,xy[1:])),'speed_mps':float(speed_mps)}

def position_at(trajectory,t):
    times=trajectory['times_s']
    if t<times[0]-1e-8 or t>times[-1]+1e-8:return None
    if t>=times[-1]:return tuple(trajectory['xy'][-1])
    i=max(0,bisect_right(times,t)-1)
    fraction=(t-times[i])/(times[i+1]-times[i])
    a,b=trajectory['xy'][i:i+2]
    return (a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction)

def closest_relative(a0,a1,b0,b1):
    r=np.asarray(a0,dtype=float)-np.asarray(b0,dtype=float)
    change=np.asarray(a1)-np.asarray(a0)-np.asarray(b1)+np.asarray(b0)
    den=float(np.dot(change,change))
    fraction=min(1,max(0,-float(np.dot(r,change))/den)) if den else 0.0
    return float(np.linalg.norm(r+fraction*change)),fraction

class ShipTimeline:
    def __init__(self,inputs,projection,sample_seconds=60):
        self.sample_seconds=float(sample_seconds)
        self.moving=np.array([[projection.project(p) for p in minute] for minute in inputs['by_minute']],dtype=float).reshape((len(inputs['by_minute']),len(inputs['vessel_order']),2))
        self.static=np.array([projection.project([s['lat'],s['lon']]) for s in inputs['static_vessels']],dtype=float).reshape((-1,2))
        self.ids=inputs['vessel_order']+[s.get('VESSEL_NAME',str(i)) for i,s in enumerate(inputs['static_vessels'])]
        self.horizon_s=(len(inputs['by_minute'])-1)*self.sample_seconds

    def positions(self,t):
        if t<0 or t>self.horizon_s+1e-8:
            raise ValueError('Ship data horizon exceeded; no extrapolation or wrapping')
        index=min(len(self.moving)-1,int(t/self.sample_seconds))
        fraction=(t-index*self.sample_seconds)/self.sample_seconds
        next_index=min(index+1,len(self.moving)-1)
        moving=self.moving[index]*(1-fraction)+self.moving[next_index]*fraction
        return np.concatenate((moving,self.static),axis=0)

def _ship_intervals(trajectory,timeline):
    for ta,tb in zip(trajectory['times_s'],trajectory['times_s'][1:]):
        if hasattr(timeline,'breakpoints_s'):
            # AIS observations are irregular. Every interpolation corner must be
            # checked; a uniform minute grid can miss a between-sample crossing.
            cuts=[ta]+[t for t in timeline.breakpoints_s if ta<t<tb]+[tb]
            yield from zip(cuts,cuts[1:])
            continue
        cuts=[ta]
        index=math.floor(ta/timeline.sample_seconds)+1
        while index*timeline.sample_seconds<tb-1e-9:
            cuts.append(index*timeline.sample_seconds);index+=1
        cuts.append(tb)
        yield from zip(cuts,cuts[1:])

def relative_geos_distance(p,q):
    from shapely.geometry import LineString,Point
    relative=Point(p) if math.dist(p,q)<1e-12 else LineString([p,q])
    return relative.distance(Point(0,0))

def validate_moving_ships(trajectory,timeline,buffer_m,tolerance_m=0,independent=False):
    if trajectory['departure_s']<0 or trajectory['arrival_s']>timeline.horizon_s:
        return {'valid':False,'reason':'ship_data_horizon_exceeded','minimum_distance_m':None,'nearest_ship':None,'closest_time_s':None}
    minimum=math.inf;nearest=None;when=None
    def samples():
        intervals=list(_ship_intervals(trajectory,timeline))
        if getattr(timeline,'segmented',False):
            for ta,tb in intervals:
                yield ta,tb,*timeline.interval_positions(ta,tb)
            # Segment endpoints and isolated observations must also be checked.
            for t in sorted({trajectory['departure_s'],trajectory['arrival_s'],
                             *(t for ab in intervals for t in ab)}):
                yield t,t,*timeline.interval_positions(t,t)
        else:
            for ta,tb in intervals:
                yield ta,tb,timeline.ids,timeline.positions(ta),timeline.positions(tb)
    for ta,tb,ids,b0,b1 in samples():
        a0,a1=position_at(trajectory,ta),position_at(trajectory,tb)
        if not len(b0):continue
        relative0=np.asarray(a0)-b0
        relative1=np.asarray(a1)-b1
        if independent:
            distances=np.array([relative_geos_distance(p,q) for p,q in zip(relative0,relative1)])
            index=int(np.argmin(distances));distance=float(distances[index])
            # Closest time is diagnostic; pass/fail distance comes from GEOS here.
            _,fraction=closest_relative(a0,a1,b0[index],b1[index])
        else:
            change=relative1-relative0
            den=np.einsum('ij,ij->i',change,change)
            numerator=-np.einsum('ij,ij->i',relative0,change)
            fractions=np.clip(np.divide(numerator,den,out=np.zeros_like(den),where=den>0),0,1)
            distances=np.linalg.norm(relative0+fractions[:,None]*change,axis=1)
            index=int(np.argmin(distances));distance=float(distances[index]);fraction=float(fractions[index])
        if distance<minimum:
            minimum,nearest,when=distance,ids[index],ta+fraction*(tb-ta)
    return {'valid':minimum>=buffer_m+tolerance_m,'reason':None if minimum>=buffer_m+tolerance_m else 'moving_ship_buffer','minimum_distance_m':minimum if math.isfinite(minimum) else None,'nearest_ship':nearest,'closest_time_s':when}

def validate_uav_pair(a,b,horizontal_m,vertical_m,tolerance_m=0,independent=False):
    start=max(a['departure_s'],b['departure_s']);end=min(a['arrival_s'],b['arrival_s'])
    if start>end or abs(a['altitude_m']-b['altitude_m'])>=vertical_m:
        return {'valid':True,'overlap':False,'minimum_distance_m':None,'closest_time_s':None}
    cuts=sorted({start,end,*[t for t in a['times_s'] if start<t<end],*[t for t in b['times_s'] if start<t<end]})
    intervals=list(zip(cuts,cuts[1:])) or [(start,end)]
    minimum=math.inf;when=None
    for ta,tb in intervals:
        a0,a1=position_at(a,ta),position_at(a,tb);b0,b1=position_at(b,ta),position_at(b,tb)
        distance,fraction=closest_relative(a0,a1,b0,b1)
        if independent:
            r0=(a0[0]-b0[0],a0[1]-b0[1]);r1=(a1[0]-b1[0],a1[1]-b1[1])
            distance=relative_geos_distance(r0,r1)
        if distance<minimum:minimum,when=distance,ta+fraction*(tb-ta)
    return {'valid':minimum>=horizontal_m+tolerance_m,'overlap':True,'minimum_distance_m':minimum,'closest_time_s':when}

def sample_trajectory(trajectory,projection,step_seconds=1):
    if step_seconds<=0:raise ValueError('Sample step must be positive')
    start,end=trajectory['departure_s'],trajectory['arrival_s']
    times=[start+i*step_seconds for i in range(int((end-start)/step_seconds)+1)]
    if not times or end-times[-1]>1e-8:times.append(end)
    for t in times:
        lat,lon=projection.unproject(position_at(trajectory,t))
        yield {'sim_time_s':t,'latitude':lat,'longitude':lon,'model_altitude_m':trajectory['altitude_m'],'speed_mps':trajectory['speed_mps'],'phase':'arrived' if abs(t-end)<1e-8 else 'flying'}

def schedule_requests(planner,inputs,settings,requests):
    config=planner.config
    timeline=ShipTimeline(inputs,planner,config['time']['vessel_sample_seconds'])
    corridor_lookup={c['id']:c for c in config['corridors']}
    priority={cid:i for i,cid in enumerate(settings['priority_order'])}
    requests=sorted(requests,key=lambda r:(r['requested_s'],priority.get(r['corridor_id'],999),r['task_id']))
    step=settings['wait_step_seconds'];limit=settings['max_wait_seconds']
    if not isinstance(step,int) or not isinstance(limit,int) or step<=0 or limit<0:raise ValueError('Invalid waiting policy')
    if len({r['task_id'] for r in requests})!=len(requests):raise ValueError('Duplicate task ID')
    separation=config['coordination'];tolerance=config['planning']['clearance_tolerance_m']
    flights=[];out=[]
    for request in requests:
        corridor=corridor_lookup[request['corridor_id']]
        rejection_counts=Counter();record={**request,'status':'not_scheduled','trajectory':None,'wait_s':None,'failure_reason':None}
        for delay in range(0,int(limit)+1,int(step)):
            departure=request['requested_s']+delay
            if departure>timeline.horizon_s:
                rejection_counts['ship_data_horizon_exceeded']+=1;break
            minute=int(departure/timeline.sample_seconds)
            planned=planner.plan(corridor['waypoints'][0],corridor['waypoints'][-1],minute,corridor['buffer_m'])
            if not planned['found']:
                rejection_counts[planned['failure_reason']]+=1;continue
            trajectory=parameterize(planned['path'],departure,corridor['speed_mps'],planner,corridor['altitude_m'])
            ships=validate_moving_ships(trajectory,timeline,corridor['buffer_m'],tolerance)
            if not ships['valid']:
                rejection_counts[ships['reason']]+=1
                if ships['reason']=='ship_data_horizon_exceeded':break
                continue
            pair_results=[validate_uav_pair(trajectory,f['trajectory'],separation['horizontal_separation_m'],separation['vertical_separation_m'],tolerance) for f in flights]
            if any(not check['valid'] for check in pair_results):
                rejection_counts['uav_separation']+=1;continue
            # Independent GEOS distances re-check accepted whole flights and reservations.
            independent_ships=validate_moving_ships(trajectory,timeline,corridor['buffer_m'],independent=True)
            independent_pairs=[validate_uav_pair(trajectory,f['trajectory'],separation['horizontal_separation_m'],separation['vertical_separation_m'],independent=True) for f in flights]
            if not independent_ships['valid'] or any(not p['valid'] for p in independent_pairs):
                rejection_counts['independent_dynamic_validation_failed']+=1;continue
            record.update(status='scheduled',trajectory=trajectory,wait_s=delay,ship_check=independent_ships,dynamic_ship_valid=True,dynamic_uav_valid=True,frozen_geometry_valid=planned['geometry_valid'])
            flights.append(record);break
        if record['status']=='not_scheduled':
            record['failure_reason']='ship_data_horizon_exceeded' if 'ship_data_horizon_exceeded' in rejection_counts else 'wait_limit_exhausted'
        record['rejection_counts']=dict(rejection_counts)
        out.append(record)
    return out,timeline
