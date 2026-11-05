"""Reproducible pier-anchored 2D cruise gates; not physical landing sites.

Source: preserved TD ferry stops, LandsD building envelopes and Marine Dept
fairways. Deterministic static geometry only; no AIS success-based selection.
"""
import argparse
import json
import math
from pathlib import Path
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from src.ais_data import digest
from src.ais_replay import replace_json
from src.ais_single_task import PROJECT, load_environment
from src.official_data import normalise_ferry_piers
from src.project_config import load_config
from src.safe_planning import SafePlanner


class StaticSiteChecker(SafePlanner):
    def wind_at(self,point):
        return 0.0  # Same explicitly excluded wind term as the 2D task entry.


def select_gates(piers, planner, fairways, step_m=25):
    if len(piers)!=2 or not math.isfinite(step_m) or step_m<=0:
        raise ValueError('Exactly two pier anchors and a positive finite step required')
    xy=[planner.project([p['lat'],p['lon']]) for p in piers]
    length=math.dist(*xy)
    if length<=0:raise ValueError('Distinct pier anchors required')
    gates=[];trials=[]
    # Limit each offset to one third of anchor separation, retaining a genuine
    # cross-water middle segment instead of allowing two endpoints to converge.
    for i,pier in enumerate(piers):
        a,b=xy[i],xy[1-i];chosen=None
        for j in range(math.floor(length/3/step_m)+1):
            offset=j*step_m
            point=(a[0]+(b[0]-a[0])*offset/length,a[1]+(b[1]-a[1])*offset/length)
            ll=planner.unproject(point)
            free=planner.static_edge(point,point)[0]
            in_water_context=fairways.covers(Point(ll[1],ll[0]))
            trials.append({'anchor_stop_id':pier['stop_id'],'offset_m':offset,'point':ll,
                           'static_free':free,'inside_official_fairway':in_water_context})
            if free and in_water_context:
                clearance=min((math.dist(point,center)-radius for center,radius in planner.buildings),default=None)
                chosen={'anchor':pier,'point':ll,'offset_m':offset,
                        'minimum_building_envelope_clearance_m':clearance,
                        'role':'derived_2D_cruise_gate_not_takeoff_or_landing_site'}
                break
        if chosen is None:
            return {'status':'no_candidate','failed_anchor':pier['stop_id'],'trials':trials,'gates':gates}
        gates.append(chosen)
    gate_distance=math.dist(*(planner.project(g['point']) for g in gates))
    return {'status':'selected','method':'official_pier_anchors_first_static_free_fairway_gate_v1',
            'sampling_step_m':step_m,'max_offset_fraction':1/3,'anchor_distance_m':length,
            'gates':gates,'gate_distance_m':gate_distance,'trials':trials,
            'scope':'Only middle cruise segment. Pier-to-gate legs not modelled. Fairway is water-traffic context, not UAV permission.'}


def main(apply=False):
    config=load_config();inputs,environment=load_environment(PROJECT,config)
    manifest_path=PROJECT/config['data']['official_manifest'];folder=manifest_path.parent
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    hashes={}
    for name in ['STOP_FERRY.xml','RSTOP_FERRY.xml','ROUTE_FERRY.xml']:
        path=folder/'raw'/name
        if digest(path)!=manifest['raw_hashes'][name]:raise ValueError('Official pier source changed: '+name)
        hashes['raw/'+name]=digest(path)
    piers=normalise_ferry_piers(*( (folder/'raw'/name).read_bytes() for name in ['STOP_FERRY.xml','RSTOP_FERRY.xml','ROUTE_FERRY.xml']))
    if piers!=json.loads((folder/'ferry_piers.json').read_text(encoding='utf-8')):
        raise ValueError('Pier coordinates do not reproduce from preserved official XML')
    water_path=folder/'fairways.geojson'
    if digest(water_path)!=manifest['derived_hashes'][water_path.name]:raise ValueError('Fairway snapshot changed')
    hashes.update(ferry_piers_json=digest(folder/'ferry_piers.json'),fairways_geojson=digest(water_path))
    fairways=unary_union([shape(f['geometry']) for f in json.loads(water_path.read_text(encoding='utf-8'))['features']])
    planner=StaticSiteChecker(config,inputs)
    result=select_gates(piers['stops'],planner,fairways)
    result.update(environment=environment,source_sha256=hashes,
                  references=['https://www.td.gov.hk/en/transport_in_hong_kong/public_transport/ferries/service_details/index_t.html',
                  'https://www.cyberport.hk/wp-content/uploads/Press-Release-SF-Pioneers-New-Landscape-for-Hong-Kongs-Low-Altitude-Logistics.pdf',
                  'https://link.springer.com/article/10.1007/s40747-025-01837-5'],
                  reference_relationship='Fixed real facility selection inspired by published cases;25m gate construction is explicit project adaptation, not copied paper method.',
                  selector_code_sha256=digest(Path(__file__)),selection_uses_AIS_or_route_success=False)
    output=PROJECT/'output/research_points/selection.json';replace_json(output,result)
    if result['status']!='selected':
        print(json.dumps(result,ensure_ascii=False,indent=2));return 2
    config_path=PROJECT/'config/ais-single-task.json'
    if apply:
        request=json.loads(config_path.read_text(encoding='utf-8'))
        previous=PROJECT/'output/research_points/previous_task_config.json'
        if not previous.exists():replace_json(previous,request)
        request.update(task_id='AIS_TST_CENTRAL_CRUISE',start=result['gates'][0]['point'],end=result['gates'][1]['point'],
                       research_points={'method':result['method'],'selection_file':'output/research_points/selection.json',
                                        'selection_sha256':digest(output),'gates':result['gates'],
                                        'roles':[g['role'] for g in result['gates']]},
                       parameter_basis='Endpoints derived from official ferry route7030 anchors using static geometry only;16m/s and150m ship buffer retained research assumptions. Middle cruise segment only; not pier takeoff/landing or certified drone service.')
        replace_json(config_path,request)
    print(json.dumps({k:result[k] for k in ['status','gates','anchor_distance_m','gate_distance_m']},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    raise SystemExit(main(parser.parse_args().apply))
