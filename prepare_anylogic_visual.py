"""Display-only local export. Never modifies planning inputs/results."""
from pathlib import Path
import json,hashlib,sys,math
from shapely.geometry import Polygon
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P))
from src.metric_projection import MetricProjection
D=P/'anylogic/visual_demo';D.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
w=read(P/'anylogic/workbench/workspace.json');ref=read(P/'output/ais_single_task/latest.json');pr=MetricProjection({'projection':ref['projection']})
centres=[]
for i in w['catalog']:
 if i['key'] in ['M1','M2','M3','M4']:
  a,b=pr.project(i['start']),pr.project(i['end']);centres.append([(a[0]+b[0])/2,(a[1]+b[1])/2])
footprints=[];source=P/'output/ais_replay/buildings_display.geojson'
for f in read(source)['features']:
 g=f['geometry'];polys=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
 for poly in polys:
  ll=poly[0];centre=[sum(p[1] for p in ll)/len(ll),sum(p[0] for p in ll)/len(ll)];c=pr.project(centre)
  if min(math.dist(c,t) for t in centres)>1200:continue
  projected=[pr.project([q[1],q[0]]) for q in ll]
  polygon=Polygon(projected)
  if not polygon.is_valid:polygon=polygon.buffer(0)
  if polygon.geom_type!='Polygon':continue
  simplified=polygon.simplify(2,preserve_topology=True)
  for tolerance in [4,8]:
   if len(simplified.exterior.coords)>64:simplified=polygon.simplify(tolerance,preserve_topology=True)
  fallback=len(simplified.exterior.coords)>64
  if fallback:simplified=polygon.envelope
  footprints.append({'center':c,'xy':list(simplified.exterior.coords),'display_simplified':True,'rectangle_fallback':fallback})
v=read(P/'output/ais_single_task/encounter_verification/verification.json');cases={r['run_id']:{'case_id':r['case_id'],'direct_check':r['direct_all_observed_ship_check']} for r in v['cases']}
for row in v['cases']:
 if row['selection']['category']=='singleton':
  cases[row['run_id']]['observation_time_s']=row['selection']['closest_time_s']
  cases[row['run_id']]['observation_mmsi']=row['selection']['nearest_ship']
for item in w['catalog']:
 if item.get('baseline_run_id') in cases:
  current=read(P/'output'/item['file'])
  cases[current['run_id']]=dict(cases[item['baseline_run_id']],comparison_source_run_id=item['baseline_run_id'])
demo_results={}
for key,kind in [('M2','straight'),('M4','building'),('encounter_M1_same_direction','same_direction'),('encounter_M1_opposing','opposing'),('encounter_M1_start_conflict','rejection'),('encounter_M1_singleton','singleton')]:
 item=next(c for c in w['catalog'] if c['key']==key);saved=read(P/'output'/item['file']);demo_results[saved['run_id']]={'kind':kind,'key':key,'result_sha256':sha(P/'output'/item['file'])}
from src.ais_single_task import apply_reference_profile,load_environment
from src.project_config import load_config
from select_research_points import StaticSiteChecker
from shapely.geometry import box,LineString
from shapely.ops import nearest_points
from src.flight_simulation import closest_relative,position_at,parameterize
from verify_ais_encounters import raw_oracle
config=apply_reference_profile(load_config(P/'config.yaml'),read(P/'config/ais-single-task.json'))
inputs,building_source=load_environment(P,config)
checker=StaticSiteChecker(config,inputs)
# Exact same projected conservative rectangles as original independent validation.
envelopes=[list(checker.building_envelope(b)) for b in inputs['buildings']['buildings']]
rectangles=[box(x-a,y-b,x+a,y+b) for x,y,a,b in envelopes]
building_checks={}
rows=[]
for vessel in w['vessels']:
 for segment in vessel['segments']:
  for a,b in (list(zip(segment,segment[1:])) if len(segment)>1 else [(segment[0],segment[0])]):
   rows.append((vessel['mmsi'],a['t'],b['t'],a['xy'],b['xy']))
ship_checks={}
for run,entry in demo_results.items():
 saved=read(P/'output'/next(c['file'] for c in w['catalog'] if c['key']==entry['key']))
 tr=saved.get('trajectory')
 if not tr:continue
 line=LineString(tr['xy']);index=min(range(len(rectangles)),key=lambda i:line.distance(rectangles[i]))
 u,b=nearest_points(line,rectangles[index]);distance=u.distance(b)
 capture_start=saved['window_start_unix_s']-w['origin']+tr['departure_s']
 building_checks[run]={'minimum_rectangle_clearance_m':distance,'closest_capture_s':capture_start+line.project(u)/saved['request']['speed_mps'],
   'envelope_index':index,'route_xy':list(u.coords)[0],'boundary_xy':list(b.coords)[0],
   'definition':'Distance to conservative projected building bounding rectangle, not facade survey; original 30m threshold unchanged.'}
 offset=saved['window_start_unix_s']-w['origin']
 actual={**tr,'times_s':[t+offset for t in tr['times_s']]}
 oracle=raw_oracle(actual,rows)
 assert abs(oracle['minimum_distance_m']-saved['ship_check']['minimum_distance_m'])<1e-5
 end=capture_start+math.dist(tr['xy'][0],tr['xy'][-1])/saved['request']['speed_mps']
 direct={'xy':[tr['xy'][0],tr['xy'][-1]],'times_s':[capture_start,end],'departure_s':capture_start,'arrival_s':end}
 best=(math.inf,None,None)
 for mmsi,ta,tb,a,b in rows:
  lo=max(direct['departure_s'],ta);hi=min(direct['arrival_s'],tb)
  if lo>hi:continue
  def ship(t):return a if ta==tb else [x+(y-x)*(t-ta)/(tb-ta) for x,y in zip(a,b)]
  d,f=closest_relative(position_at(direct,lo),position_at(direct,hi),ship(lo),ship(hi))
  if d<best[0]:best=(d,lo+f*(hi-lo),mmsi)
 ship_checks[run]={'planned_continuous_check':oracle,'direct_minimum_m':best[0] if math.isfinite(best[0]) else None,'direct_closest_capture_s':best[1],'direct_mmsi':best[2]}
result={'schema_version':2,'demo_results':demo_results,'raw_sha256':w['source']['raw_sha256'],'building_source_sha256':sha(source),'footprints':footprints,'case_checks':cases,
 'planning_envelopes':envelopes,'planning_building_source':building_source,'building_checks':building_checks,'ship_comparison_checks':ship_checks,
 'display_only':{'uav_vertical_offset':35,'uniform_building_extrusion':40,'ship_icon_length':24,'ship_icon_width':9,'max_visible_buildings':100,
 'background_simplification':'Display only: preserve-topology simplification 2/4/8m until <=64 vertices, rectangle fallback; all 35335 unsimplified planning envelopes retained for distances and original planning.',
 'note':'All Z, icon sizes, camera values and building extrusion are illustrative, never passed to Python planning; XY, times and distance remain original.'}}
(D/'support.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print('Display footprints:',len(footprints),'bytes:',(D/'support.json').stat().st_size)
