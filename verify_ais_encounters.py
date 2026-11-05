"""Fixed-protocol historical AIS encounter acceptance; baseline results untouched.

Reference: existing detour scan, parameterize/closest_relative and original 2D
planner. Direction groups below are descriptive project bins, not COLREG rules.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
from collections import Counter
from shapely.geometry import LineString, Point
from src.ais_replay import build_capture, replace_json
from src.ais_single_task import apply_reference_profile, load_environment, run_task
from src.project_config import load_config
from src.flight_simulation import parameterize, position_at, closest_relative
from select_research_points import StaticSiteChecker

P=Path(__file__).resolve().parent
D=P/'output/ais_single_task/encounter_verification'
GROUPS=['start_conflict','opposing','crossing','same_direction','stationary','singleton','instant_only']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def ship_at(row,t):
    _,ta,tb,a,b=row
    return a if ta==tb else [x+(y-x)*(t-ta)/(tb-ta) for x,y in zip(a,b)]


def group(row,tr,lo,hi):
    if row[1]==row[2]:return 'singleton',None
    if hi==lo:return 'instant_only',None
    va=[b-a for a,b in zip(tr['xy'][0],tr['xy'][-1])]
    vb=[b-a for a,b in zip(row[3],row[4])]
    length=math.hypot(*vb)
    if length<=1e-9:return 'stationary',None
    cosine=sum(a*b for a,b in zip(va,vb))/(math.hypot(*va)*length)
    angle=math.degrees(math.acos(max(-1,min(1,cosine))))
    return ('opposing' if angle>=135 else 'same_direction' if angle<=45 else 'crossing'),angle


def closest(tr,row):
    lo=max(tr['departure_s'],row[1]);hi=min(tr['arrival_s'],row[2])
    if lo>hi:return None
    distance,f=closest_relative(position_at(tr,lo),position_at(tr,hi),ship_at(row,lo),ship_at(row,hi))
    category,angle=group(row,tr,lo,hi)
    return {'minimum_distance_m':distance,'closest_time_s':lo+f*(hi-lo),
            'nearest_ship':row[0],'support_interval_s':list(row[1:3]),
            'overlap_seconds':hi-lo,'category':category,'direction_angle_degrees':angle}


def raw_oracle(tr,rows):
    """Independent GEOS distance on relative paths, over ALL raw valid segments."""
    best=math.inf;nearest=None
    for row in rows:
        for ta,tb in zip(tr['times_s'],tr['times_s'][1:]):
            lo=max(ta,row[1]);hi=min(tb,row[2])
            if lo>hi:continue
            u=position_at(tr,lo);v=position_at(tr,hi)
            a=ship_at(row,lo);b=ship_at(row,hi)
            r=[x-y for x,y in zip(u,a)];s=[x-y for x,y in zip(v,b)]
            distance=(Point(r) if r==s else LineString([r,s])).distance(Point(0,0))
            if distance<best:best,nearest=distance,row[0]
    return {'minimum_distance_m':best if math.isfinite(best) else None,'nearest_ship':nearest}


def main():
    D.mkdir(parents=True,exist_ok=True)
    study=read(P/'output/research_points/study/study.json')
    source=P/'data/ais/captures'/study['capture_id']
    base=read(P/'config/ais-single-task.json')
    config=apply_reference_profile(load_config(P/'config.yaml'),base)
    inputs,_=load_environment(P,config);projection=StaticSiteChecker(config,inputs)
    bundle=build_capture(source);origin=bundle['start'];horizon=bundle['end']-origin
    protected=[P/'output/ais_single_task/latest.json',P/'config/ais-single-task.json',source/'messages.jsonl']
    protected+=sorted((P/'output/research_points/study').rglob('*.json'))
    before={str(path.relative_to(P)):digest(path) for path in protected}
    rows=[]
    for vessel in bundle['vessels']:
        for segment in vessel['segments']:
            for a,b in (list(zip(segment,segment[1:])) if len(segment)>1 else [(segment[0],segment[0])]):
                rows.append((vessel['mmsi'],a['timestamp_unix_s']-origin,b['timestamp_unix_s']-origin,
                             projection.project([a['latitude'],a['longitude']]),projection.project([b['latitude'],b['longitude']])))
    protocol={'version':'real_ais_encounters_v1','capture_id':bundle['capture_id'],'raw_sha256':bundle['raw_sha256'],
              'profile':base['parameter_profile'],'window_policy':base['window_policy'],
              'departure_step_seconds':5,'routes':'original frozen M1-M4; departures from capture first point',
              'selection':'Earliest eligible departure per route/category, chosen before ALL replanning; one attempt, no replacement after failure.',
              'eligibility':'Start-conflict cases need a known start conflict; route cases need static-clear direct path and clear known start/end positions.',
              'categories':{'opposing':'>=135 degrees','same_direction':'<=45 degrees','crossing':'45<angle<135',
                            'stationary':'two observed endpoints with projected displacement <=1e-9 m',
                            'singleton':'one-point valid segment; no direction inferred',
                            'instant_only':'two-point segment overlaps flight at only one instant; no motion case claimed'},
              'basis':'Project descriptive bins, not maritime right-of-way or certified encounter rules. Existing closest_relative and planner reused.',
              'gap_rule':'Original <=120 s qualified interpolation only; missing positions excluded without blocking.',
              'limits':'Fixed four routes and one capture; adjacent scan hits correlated; 5s grid may miss events. No general success-rate claim.',
              'baseline_unchanged':True,'created_at_utc':datetime.now(timezone.utc).isoformat()}
    replace_json(D/'protocol.json',protocol)
    hits=[];selected=[];scan=[];availability=[]
    for task in study['tasks']:
        request=read(P/'output'/task['request_file'])
        a,b=projection.project(request['start']),projection.project(request['end'])
        duration=math.dist(a,b)/request['speed_mps'];radius=request['buffer_m'];tol=config['planning']['clearance_tolerance_m']
        direct_clear=bool(projection.static_edge(a,b)[0]);line=LineString([a,b])
        nearby=[row for row in rows if line.distance(Point(row[3]) if row[3]==row[4] else LineString(row[3:5]))<radius+tol]
        first={};counts=Counter();eligible=Counter();departures=0;conflict_departures=set()
        for departure in range(0,math.floor(horizon-duration)+1,5):
            departures+=1
            tr=parameterize([request['start'],request['end']],departure,request['speed_mps'],projection,0)
            start=raw_oracle({'xy':[a,a],'times_s':[departure,departure],'departure_s':departure,'arrival_s':departure},rows)
            end=raw_oracle({'xy':[b,b],'times_s':[tr['arrival_s'],tr['arrival_s']],'departure_s':tr['arrival_s'],'arrival_s':tr['arrival_s']},rows)
            start_clear=start['minimum_distance_m'] is None or start['minimum_distance_m']>=radius+tol
            end_clear=end['minimum_distance_m'] is None or end['minimum_distance_m']>=radius+tol
            common={'task':task['id'],'departure_s':departure,
                    'departure_utc':datetime.fromtimestamp(origin+departure,timezone.utc).isoformat(),
                    'direct_static_clear':direct_clear,'start_check':start,'end_check':end}
            if not start_clear:
                record={**common,'category':'start_conflict',**start,'eligible':True}
                hits.append(record);counts['start_conflict']+=1;eligible['start_conflict']+=1
                first.setdefault('start_conflict',record)
            # Keep every conflict segment, not only whichever ship is globally nearest.
            for row in nearby:
                event=closest(tr,row)
                if event is None or event['minimum_distance_m']>=radius+tol:continue
                category=event['category'];allowed=direct_clear and start_clear and end_clear
                record={**common,**event,'eligible':allowed}
                hits.append(record);counts[category]+=1;conflict_departures.add(departure)
                if allowed:
                    eligible[category]+=1
                    # Source order breaks ties; independent of replan outcome.
                    first.setdefault(category,record)
        for category in GROUPS:
            availability.append({'task':task['id'],'category':category,'raw_segment_events':counts[category],
                                 'eligible_events':eligible[category],
                                 'status':'selected' if category in first else 'not_found' if not counts[category] else 'excluded_by_endpoint_or_static_constraint'})
            if category in first:selected.append({'case_id':task['id']+'_'+category,'selection':first[category]})
        scan.append({'task':task['id'],'scanned_departures':departures,'direct_static_clear':direct_clear,
                     'direct_conflict_departures':len(conflict_departures),'raw_segment_events':dict(counts),'eligible_events':dict(eligible)})
        print('SCAN',scan[-1],flush=True)
    replace_json(D/'scan_events.json',hits)
    replace_json(D/'selection.json',{'protocol_sha256':digest(D/'protocol.json'),'cases':selected,'availability':availability,'scan':scan})
    selection_hash=digest(D/'selection.json')
    completed=[]
    for case in selected:
        cid=case['case_id'];event=case['selection'];directory=D/cid;directory.mkdir(exist_ok=True)
        task=next(t for t in study['tasks'] if t['id']==event['task'])
        request=read(P/'output'/task['request_file'])
        request.update(task_id=cid.upper(),window_start_utc=event['departure_utc'],departure_offset_seconds=0,
                       window_start_basis='Fixed protocol: earliest eligible per route/category, selected before replanning; baseline unchanged')
        replace_json(directory/'request.json',request)
        print('RUN',cid,event['departure_utc'],flush=True)
        result=run_task(source,request,P,publish=False)
        replace_json(directory/'result.json',result)
        outcome={'case_id':cid,'selection':event,'run_id':result['run_id'],'status':result['status'],
                 'failure_reason':result['failure_reason'],'validation':'not_verified',
                 'result_file':str((directory/'result.json').relative_to(P/'output')).replace('\\','/'),
                 'selection_sha256':selection_hash}
        direct=parameterize([request['start'],request['end']],event['departure_s'],request['speed_mps'],projection,0)
        outcome['direct_all_observed_ship_check']=raw_oracle(direct,rows)
        if event['category']=='start_conflict':
            outcome['validation']='passed_expected_rejection' if result['status']=='rejected_planning' and result['failure_reason']=='start_ship_buffer' else 'failed_expected_rejection'
        elif result['status']=='planned':
            tr=json.loads(json.dumps(result['trajectory']));delta=result['window_start_unix_s']-origin
            tr['times_s']=[t+delta for t in tr['times_s']];tr['departure_s']+=delta;tr['arrival_s']+=delta
            independent=raw_oracle(tr,rows);actual=result['ship_check']['minimum_distance_m']
            agrees=(actual is None and independent['minimum_distance_m'] is None) or (actual is not None and independent['minimum_distance_m'] is not None and math.isclose(actual,independent['minimum_distance_m'],abs_tol=1e-5,rel_tol=0))
            valid=result['planning']['geometry_valid'] and result['ship_check']['valid'] and agrees and (actual is None or actual>=request['buffer_m']+tol-1e-6)
            outcome.update(validation='passed_observed_route_check' if valid else 'failed_independent_check',
                           independent_geos_raw_check=independent,distance_m=tr['distance_m'],
                           selected_ship_after_check=raw_oracle(tr,[row for row in rows if row[0]==event['nearest_ship']]),
                           direct_distance_m=math.dist(tr['xy'][0],tr['xy'][-1]),
                           flight_seconds=tr['arrival_s']-tr['departure_s'],
                           participating_vessels=result['observation_coverage']['task_participating_vessels'])
        else:
            outcome['validation']='planning_failed_no_feasibility_proof'
        completed.append(outcome)
        replace_json(D/'verification.json',{'protocol':protocol,'selection_sha256':selection_hash,'cases':completed,
                     'availability':availability,'scan':scan,'complete':len(completed)==len(selected),
                     'summary':dict(Counter(row['validation'] for row in completed))})
        print('DONE',cid,outcome['status'],outcome['validation'],flush=True)
    after={str(path.relative_to(P)):digest(path) for path in protected}
    assert before==after,'Baseline inputs or results changed'
    replace_json(D/'baseline_integrity.json',{'unchanged':True,'files':before})
    print('COMPLETE',dict(Counter(row['validation'] for row in completed)),flush=True)


if __name__=='__main__':main()
