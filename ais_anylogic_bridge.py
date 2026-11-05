"""Local file/process adapter, reusable by AnyLogic or a later desktop client.

No planner rewrite, HTTP server, live API or API key in the display process.
"""
import argparse,json,math
from pathlib import Path
from src.ais_single_task import run_task
from src.ais_replay import build_capture,replace_json
from src.metric_projection import MetricProjection

P=Path(__file__).resolve().parent
CASES={'success':'M1_same_direction','rejection':'M1_start_conflict'}
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def export_scene(target):
    """Exact saved positions/segments in projected meters, not resampled tracks."""
    result=read(P/'output/ais_single_task/encounter_verification/M1_same_direction/result.json')
    source=P/'data/ais/captures'/result['capture_id'];bundle=build_capture(source)
    assert result['raw_sha256']==bundle['raw_sha256']
    projection=MetricProjection({'projection':result['projection']})
    a,b=[projection.project(result['request'][name]) for name in ['start','end']]
    xmin=min(a[0],b[0])-500;xmax=max(a[0],b[0])+500
    ymin=min(a[1],b[1])-500;ymax=max(a[1],b[1])+500
    lines=[f"SCENE\t{bundle['start']}\t{xmin}\t{xmax}\t{ymin}\t{ymax}\t{bundle['raw_sha256']}"]
    for vessel in bundle['vessels']:
        for index,segment in enumerate(vessel['segments']):
            for point in segment:
                x,y=projection.project([point['latitude'],point['longitude']])
                lines.append(f"SHIP\t{vessel['mmsi']}\t{index}\t{point['timestamp_unix_s']-bundle['start']}\t{x}\t{y}\t{point['raw_line']}")
    # Crop only the background DISPLAY to the fixed M1 view; planning uses all buildings.
    geometry=read(P/'output/ais_replay/buildings_display.geojson');count=0
    for feature in geometry['features']:
        shape=feature['geometry'];polys=shape['coordinates'] if shape['type']=='MultiPolygon' else [shape['coordinates']]
        for polygon in polys:
            outer=[projection.project([lat,lon]) for lon,lat,*rest in polygon[0]]
            if max(p[0] for p in outer)<xmin or min(p[0] for p in outer)>xmax or max(p[1] for p in outer)<ymin or min(p[1] for p in outer)>ymax:continue
            lines.append('BUILDING\t'+'\t'.join(str(v) for xy in outer for v in xy));count+=1
    target.mkdir(parents=True,exist_ok=True)
    (target/'scene.tsv').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    replace_json(target/'scene_source.json',{'capture_id':bundle['capture_id'],'raw_sha256':bundle['raw_sha256'],
                 'position_count':bundle['valid_position_count'],'vessel_count':bundle['vessel_count'],
                 'view_crop_margin_m':500,'view_crop_basis':'Display extent only, not planner or safety threshold',
                 'background_polygons_in_view':count,'coordinate_crs':'EPSG:32650','gap_limit_seconds':120})


def run(case,target):
    template=P/f'output/ais_single_task/encounter_verification/{CASES[case]}/request.json'
    request=read(template)
    capture=read(P/f'output/ais_single_task/encounter_verification/{CASES[case]}/result.json')['capture_id']
    target.mkdir(parents=True,exist_ok=True)
    result=run_task(P/'data/ais/captures'/capture,request,P,publish=False)
    replace_json(target/'result.json',result)
    bundle=read(P/'output/ais_replay/bundle.json')
    assert bundle['capture_id']==capture and bundle['raw_sha256']==result['raw_sha256']
    lines=[f"RESULT\t{result['status']}\t{result['failure_reason'] or ''}\t{result['run_id']}\t{result['raw_sha256']}"]
    if result['status']=='planned':
        tr=result['trajectory'];delta=result['window_start_unix_s']-bundle['start']
        lines.append(f"SUMMARY\t{tr['distance_m']}\t{tr['arrival_s']-tr['departure_s']}\t{result['ship_check']['minimum_distance_m']}")
        for t,xy in zip(tr['times_s'],tr['xy']):lines.append(f"UAV\t{t+delta}\t{xy[0]}\t{xy[1]}")
    else:
        # Rejected task still has its requested departure for synchronized vessel display.
        from src.ais_data import timestamp
        lines.append(f"REJECT_TIME\t{timestamp(request['window_start_utc'])-bundle['start']}")
    (target/'display.tsv').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--case',choices=CASES);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare-workbench',action='store_true');parser.add_argument('--load-key');parser.add_argument('--run-key');parser.add_argument('--departure')
    args=parser.parse_args()
    if args.prepare_workbench:
        from src.anylogic_workspace import prepare
        prepare(args.output)
    elif args.load_key or args.run_key:
        from src.anylogic_workspace import packet
        print(packet(args.load_key or args.run_key,args.output,run=bool(args.run_key),departure=args.departure)['status'])
    elif args.prepare:export_scene(args.output)
    elif args.case:print(run(args.case,args.output)['status'])
    else:parser.error('--prepare or --case required')
