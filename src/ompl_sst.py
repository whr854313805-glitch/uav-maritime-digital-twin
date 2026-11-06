"""OMPL control::SST adapter. No search, shortcutting or legacy fallback here."""
from pathlib import Path
import hashlib,json,math,subprocess,tempfile
from src.flight_simulation import validate_moving_ships,validate_uav_pair
from src.safe_planning import validate_path

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def solve(checker,corridor,departure_s,reservations=()):
    c=checker;q=corridor;start,end=q['waypoints'][0],q['waypoints'][-1];a,b=[list(c.project(p)) for p in (start,end)]
    speed=float(q['speed_mps']);buffer=float(q['buffer_m']);tol=c.settings['clearance_tolerance_m'];alt=float(q['altitude_m'])
    stats={'algorithm':'OMPL 2.0.2 control::SST','objective':'path_length_subject_to_original_hard_constraints','custom_search_or_shortening_used':False,'hovering':False}
    def fail(reason):return {'found':False,'failure_reason':reason,'geometry_valid':None,'path':None,'trajectory':None,'search':stats}
    if not all(math.isfinite(x) for x in (speed,buffer,alt,departure_s)) or speed<=0 or buffer<=0 or departure_s<0:raise ValueError('Invalid motion request')
    length=math.dist(a,b)
    if length==0:return fail('zero_length_flight')
    if departure_s+length/speed>c.timeline.horizon_s:return fail('ship_data_horizon_exceeded')
    if length/speed>c.search_settings['max_flight_seconds']:return fail('flight_time_limit_exhausted')
    for label,p in [('start',a),('end',b)]:
        if not c.inside(p):return fail(label+'_outside_region')
        if not c.static_edge(tuple(p),tuple(p))[0]:return fail(label+'_building_or_wind_constraint')
    if any(math.dist(a,p)<buffer+tol for p in c.timeline.positions(departure_s)):return fail('start_ship_buffer')
    finish=min(c.timeline.horizon_s,departure_s+c.search_settings['max_flight_seconds'])
    def trajectory(xy,ts):
        path=[c.unproject(p) for p in xy];path[0]=start;path[-1]=end
        return {'path':path,'xy':xy,'times_s':ts,'departure_s':ts[0],'arrival_s':ts[-1],'speed_mps':speed,'altitude_m':alt,'distance_m':sum(math.dist(x,y) for x,y in zip(xy,xy[1:]))}
    def validate(tr):
        if tr['arrival_s']>finish+1e-9:return None
        if any(not c.static_edge(tuple(x),tuple(y))[0] for x,y in zip(tr['xy'],tr['xy'][1:])):return None
        sc=validate_moving_ships(tr,c.timeline,buffer,tol,independent=True)
        geo=validate_path(tr['path'],start,end,[],buffer+tol,c.config,c.inputs['buildings']['buildings'],c)
        separation=c.config['coordination'];pairs=[validate_uav_pair(tr,r,separation['horizontal_separation_m'],separation['vertical_separation_m'],tol,independent=True) for r in reservations]
        times=tr['times_s'];xy=tr['xy']
        if any(y<=x for x,y in zip(times,times[1:])):return None
        error=max(abs(math.dist(x,y)/(tb-ta)-speed) for x,y,ta,tb in zip(xy,xy[1:],times,times[1:]))
        if not sc['valid'] or not geo['geometry_valid'] or any(not p['valid'] for p in pairs) or error>1e-6 or xy[0]!=a or xy[-1]!=b:return None
        stats.update(independent_geometry_check=geo,maximum_speed_error_mps=error)
        return {'found':True,'failure_reason':None,'path':tr['path'],'trajectory':tr,'geometry_valid':True,'distance_m':tr['distance_m'],'ship_check':sc,'search':stats}
    direct=trajectory([a,b],[departure_s,departure_s+length/speed]);accepted=validate(direct)
    if accepted:
        stats['method']='validated_exact_straight_motion_no_search';return accepted
    if reservations:return fail('ompl_single_uav_adapter_does_not_support_reservations')
    runtime=Path(c.inputs.get('ompl_runtime_dir',Path(__file__).resolve().parents[1]/'runtime/ompl'))
    settings=read(runtime/'settings.json');identity=c.inputs.get('ompl_request');profile=None
    # A fixed-request query bound is metadata, never a supplied old path.
    if identity:
        profile=next((p for p in settings['fixed_requests'] if p['request']==identity),None)
    options=profile or settings['default'];upper=min(finish-departure_s,options.get('query_time_upper_s',finish-departure_s))
    stats.update(method='official_SST_plus_explicit_terminal_leg',query_time_upper_s=upper,query_basis=options.get('query_basis','original requested horizon'),seed=options['seed'],solve_seconds=options['solve_seconds'])
    if upper<length/speed:return fail('ompl_query_time_bound_below_direct_lower_bound')
    ships=[]
    for m,segs in zip(c.timeline.ids,c.timeline.segment_tracks):
        for ts,points in segs:
            for i,j in (list(zip(range(len(ts)-1),range(1,len(ts)))) if len(ts)>1 else [(0,0)]):ships.append({'mmsi':m,'ta':float(ts[i])-departure_s,'tb':float(ts[j])-departure_s,'a':list(points[i]),'b':list(points[j])})
    ea=speed*upper/2;ec=length/2;eb=math.sqrt(max(0,ea*ea-ec*ec));u=[(b[i]-a[i])/length for i in range(2)];mid=[(a[i]+b[i])/2 for i in range(2)];ex=math.hypot(ea*u[0],eb*u[1]);ey=math.hypot(ea*u[1],eb*u[0])
    data={'start_xy':a,'end_xy':b,'speed_mps':speed,'buffer_m':buffer,'clearance_tolerance_m':tol,'horizon_s':c.timeline.horizon_s-departure_s,'search_time_upper_s':upper,'grid_step_m':c.step,'building_circles':[[float(p[0]),float(p[1]),float(r)] for p,r in c.buildings],'ships':ships,'bounds':[max(c.xmin,mid[0]-ex),min(c.xmax,mid[0]+ex),max(c.ymin,mid[1]-ey),min(c.ymax,mid[1]+ey)],'propagation_step_s':.1,'maximum_control_steps':50,'solve_seconds':options['solve_seconds'],'seed':options['seed'],'goal_numerical_tolerance_m':options.get('terminal_region_m',15.),'terminal_connector_enabled':True,'state_length_scale_m':length,'state_time_scale_s':length/speed,'selection_radius':options['selection_radius'],'pruning_radius':options['pruning_radius'],'goal_bias':.2}
    worker=(runtime/'sst_worker.exe').resolve();manifest=read(runtime/'manifest.json')
    for name,expected in manifest['runtime_sha256'].items():
        if digest(runtime/name)!=expected:raise ValueError('OMPL runtime hash mismatch: '+name)
    job=Path(c.inputs.get('ompl_output_dir') or tempfile.mkdtemp(prefix='ais_ompl_'));job.mkdir(parents=True,exist_ok=True);inp=job/'ompl_input.json';out=job/'ompl_output.json';inp.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    try:
        # The unchanged worker uses narrow C++ file names. Keep its arguments
        # ASCII and let Windows retain the Unicode working-directory path.
        with (job/'ompl.log').open('w',encoding='utf-8') as log:p=subprocess.run([str(worker),inp.name,out.name],stdout=log,stderr=subprocess.STDOUT,timeout=options['solve_seconds']+30,cwd=job,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:return fail('ompl_runtime_timeout')
    if p.returncode:return fail('ompl_native_process_failed')
    native=read(out);stats.update(native_status=native['status'],library_commit=manifest['commit'],worker_sha256=digest(worker),native_input_sha256=digest(inp),native_output_sha256=digest(out),native_result_file=str(out))
    if not native['exact'] or not native.get('terminal_connection',{}).get('valid'):return fail('ompl_no_exact_solution_within_budget')
    conn=native['terminal_connection']
    if conn['to_xy']!=b or conn['from_xy']!=native['states'][-1]['xy']:return fail('ompl_terminal_connection_identity_mismatch')
    states=native['states']+[{'xy':b,'t':conn['arrival_s']}]
    tr=trajectory([s['xy'] for s in states],[s['t']+departure_s for s in states]);stats.update(native_prefix_unmodified=True,terminal_leg_m=conn['distance_m'])
    if tr['arrival_s']>departure_s+upper+1e-9:return fail('ompl_query_time_bound_exceeded')
    accepted=validate(tr)
    return accepted if accepted else fail('ompl_independent_validation_failed')
