"""Current AIS workstation data/controller adapter; no new planning algorithm."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from copy import deepcopy
import json,hashlib,uuid,textwrap
from PIL import Image,ImageDraw
from src.ais_single_task import run_task
from src.ais_replay import build_capture,replace_json
from src.metric_projection import MetricProjection
from src.validation import parse_departure, validate_result
from src.release_checks import workspace_geometry

P=Path(__file__).resolve().parents[1]
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def hk(t):return datetime.fromtimestamp(t,timezone(timedelta(hours=8))).isoformat()


def catalog(root=None):
    root=Path(root) if root is not None else P
    items=[]
    def add(key,label,path,can_run=True):
        f=root/'output'/path
        if not f.exists():return
        r=read(f);request=r['request']
        items.append({'key':key,'label':label,'file':path,'sha256':sha(f),'status':r['status'],
                      'can_run':can_run and r['status']!='not_tested','request':request,
                      'departure':request.get('window_start_utc') or '',
                      'start':request['start'],'end':request['end']})
    for n in range(1,5):add(f'M{n}',f'M{n} 固定任务',f'research_points/study/M{n}/result.json')
    add('current','当前默认结果','ais_single_task/latest.json')
    for n in range(1,5):add(f'detour_M{n}',f'M{n} 直线冲突专项',f'ais_single_task/detour_verification/M{n}_result.json')
    for key,label in [('M1_start_conflict','起点过近'),('M1_opposing','相向运动'),('M1_same_direction','同向运动'),('M1_singleton','孤立实测点')]:
        add('encounter_'+key,label+'案例',f'ais_single_task/encounter_verification/{key}/result.json')
    for grid in [100,200,400]:add('grid_'+str(grid),f'网格对照 {grid}米',f'ais_single_task/grid_sensitivity/{grid}/result.json',False)
    repair=root/'output/ais_single_task/ompl_sst/catalog.json'
    if repair.exists():
        overrides=read(repair)
        for item in items:
            replacement=overrides['overrides'].get(item['key'])
            if not replacement:continue
            path=(root/'output'/replacement['file']).resolve()
            if not path.is_relative_to((root/'output').resolve()):raise ValueError('Repaired result outside output')
            baseline=read(root/'output'/item['file']);current=read(path)
            if (replacement['baseline_file']!=item['file'] or replacement['baseline_sha256']!=item['sha256'] or
                    sha(path)!=replacement['sha256'] or current['request']!=baseline['request'] or
                    current['raw_sha256']!=baseline['raw_sha256']):
                raise ValueError('Repaired result differs from its fixed request or AIS source')
            item.update(file=replacement['file'],sha256=sha(path),status=current['status'],
                        baseline_file=replacement['baseline_file'],baseline_run_id=baseline['run_id'],
                        algorithm=overrides['algorithm'])
    return items


def prepare(target):
    from src.workspace_catalog import catalog_lock
    with catalog_lock(P):
        return _prepare(target)


def _prepare(target):
    target.mkdir(parents=True,exist_ok=True)
    ref=read(P/'output/research_points/study/M2/result.json');source=P/'data/ais/captures'/ref['capture_id']
    bundle=build_capture(source)
    if bundle['raw_sha256']!=ref['raw_sha256']:raise ValueError('Workspace source mismatch')
    pr=MetricProjection({'projection':ref['projection']})
    def point(p):
        q=deepcopy(p);q['xy']=pr.project([p['latitude'],p['longitude']]);q['t']=p['timestamp_unix_s']-bundle['start'];return q
    vessels=[{'mmsi':v['mmsi'],'points':[point(q) for q in v['points']],
              'segments':[[point(q) for q in s] for s in v['segments']]} for v in bundle['vessels']]
    sites,bounds=workspace_geometry(P,ref['projection'])
    xmin,xmax,ymin,ymax=bounds;w=5000;h=round(w*(ymax-ymin)/(xmax-xmin))
    image=Image.new('RGB',(w,h),'#e8eff4');draw=ImageDraw.Draw(image)
    geompath=P/'output/ais_replay/buildings_display.geojson';geo=read(geompath);polygons=0
    def pixel(lon,lat):
        x,y=pr.project([lat,lon]);return ((x-xmin)/(xmax-xmin)*w,(ymax-y)/(ymax-ymin)*h)
    for feat in geo['features']:
        geometry=feat['geometry'];parts=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
        for poly in parts:
            draw.polygon([pixel(*q[:2]) for q in poly[0]],fill='#c4cfd7',outline='#99aab6')
            for hole in poly[1:]:draw.polygon([pixel(*q[:2]) for q in hole],fill='#e8eff4')
            polygons+=1
    image.save(P/'anylogic/harbour_background.png')
    payload={'schema_version':1,'origin':bundle['start'],'end':bundle['end'],'duration':bundle['end']-bundle['start'],
             'bounds':bounds,'vessels':vessels,'sites':sites,'catalog':catalog(),'breaks':bundle['breaks'],
             'source':{'capture_id':bundle['capture_id'],'raw_sha256':bundle['raw_sha256'],'raw_bytes':bundle['raw_bytes'],
               'positions':bundle['valid_position_count'],'vessels':bundle['vessel_count'],'break_count':len(bundle['breaks']),
               'longest_seconds':bundle['longest_contiguous_seconds'],'quality':bundle['quality_parameters'],
               'display_features':len(geo['features']),'display_polygons':polygons,
               'background_source_sha256':sha(geompath),'raster_width':w,'raster_height':h,
               'raster_basis':'Local display raster of official outlines; no planning geometry is rasterized or altered.'},
             'job':read(P/'output/ais_hour_job.json') if (P/'output/ais_hour_job.json').exists() else {}}
    replace_json(target/'workspace.json',payload)
    replace_json(target/'provenance.json',{'workspace_sha256':sha(target/'workspace.json'),'raw_sha256':bundle['raw_sha256'],
              'background_png_sha256':sha(P/'anylogic/harbour_background.png'),'scene':payload['source']})
    return payload


def sections(result,item,workspace):
    c=result.get('data_check') or {};sc=result.get('ship_check') or {};oc=result.get('observation_coverage') or {}
    parts={'任务检查':[f"任务：{item['label']}",f"状态：{result['status']}",f"原因：{result.get('failure_reason') or '无'}",
         f"run_id：{result.get('run_id','无，本案例未运行')}",f"参数：90m / 15m/s / 建筑30m / UTM50N",
         f"窗口：{c.get('window_start_unix_s')} → {c.get('window_end_unix_s')}",
         f"窗口可用秒：{c.get('available_seconds')}",f"连续距离检查：{sc}",
         '缺口不参与避障；结果仅针对已观测船舶。'],
         '逐船覆盖':[],
         'AIS来源':[f'{k}：{v}' for k,v in workspace['source'].items()]+['船位唯一来源：AISStream；第三方汇聚，非香港官方接口。','原始点、合格插值与未知区间分开。120秒等为工程设定。',f"采集状态文件：{workspace['job']}"]}
    for v in c.get('vessels',[]):
        parts['逐船覆盖'] += [f"船{v['mmsi']}：{v['observation_count']}观测，最长{v['longest_seconds']:.3f}s；参与={v['selected_for_planning']}"]
        for s in v['continuous_intervals']:parts['逐船覆盖'].append(f"  {hk(s['start'])} → {hk(s['end'])} ({s['duration_seconds']:.3f}s)")
        cv=next((q for q in oc.get('vessels',[]) if q['mmsi']==v['mmsi']),None)
        if cv:parts['逐船覆盖'].append(f"  本任务支持{cv['supported_seconds']:.3f}s，未知{cv['unknown_seconds']:.3f}s")
    parts['八点依据']=['8点来自官方渡轮交通联系筛选，非获批起降点，不代表最优布点。']
    for s in workspace['sites']:parts['八点依据'] += [f"{s['task']} {s['role']}：{s['point']}",f"码头：{s['anchor'].get('name_zh',s['anchor']['name'])}，偏移{s['offset_m']}m"]
    parts['实验汇总']=['遇船4分类只有3个不同出发组合；相向和孤立点同次任务。横穿仍未找到合格样本。',
                       '网格100/200/400为修复前历史结果；当前采用官方SST，不能套用旧网格结论。']
    for q in workspace['catalog']:parts['实验汇总'].append(f"{q['label']}：{q['status']}；{'允许重新规划' if q['can_run'] else '仅查看原结果'}")
    tr=result.get('trajectory')
    search=(result.get('planning') or {}).get('search',{})
    algorithm='官方OMPL SST；直线合格时直接飞；整条路线独立检查' if search.get('algorithm')=='OMPL 2.0.2 control::SST' else '历史保存结果；以该结果记录为准'
    parts['任务检查'].append('算法：'+algorithm)
    if tr:parts['任务检查'] += [f"航程{tr['distance_m']:.6f}m，航时{tr['arrival_s']-tr['departure_s']:.6f}s",
                                f"参与船数{len(oc.get('task_participating_vessels',[]))}；有缺口船数{oc.get('vessels_with_unknown_positions')}"]
    return {k:[chunk for row in rows for chunk in (textwrap.wrap(str(row),width=35,replace_whitespace=False) or [''])] for k,rows in parts.items()}


def packet(key,target,run=False,departure=None):
    from src.workspace_catalog import catalog_lock, synchronize_locked
    with catalog_lock(P):
        workspace,items=synchronize_locked(P,read(P/'anylogic/workbench/workspace.json'))
        item=next((q for q in items if q['key']==key),None)
        if item is None:raise ValueError('Unknown catalog key')
        saved=None if run else read(P/'output'/item['file'])
    target.mkdir(parents=True,exist_ok=True)
    if run:
        if not item['can_run']:raise ValueError('This saved experiment is view-only; use a fixed task to replan')
        req=deepcopy(item['request'])
        try:
            if departure is not None:
                dt=parse_departure(departure,naive_hong_kong=True)
                req['window_start_utc']=dt.astimezone(timezone.utc).isoformat()
            result=run_task(P/'data/ais/captures'/workspace['source']['capture_id'],req,P,publish=False)
        except (ValueError,OverflowError,OSError,TypeError) as error:
            result={'status':'error','failure_reason':'出发时间无效：'+str(error),'submitted_departure':departure,'run_id':uuid.uuid4().hex,'request':req,
                    'trajectory':None,'capture_id':workspace['source']['capture_id'],'raw_sha256':workspace['source']['raw_sha256']}
    else:result=saved
    validate_result(result)
    if result['status']!='error' and (result.get('capture_id')!=workspace['source']['capture_id'] or result.get('raw_sha256')!=workspace['source']['raw_sha256']):
        raise ValueError('Result and workspace AIS identity mismatch')
    replace_json(target/'result.json',result)
    req=result['request'];tr=deepcopy(result.get('trajectory'));start=workspace['origin']
    if tr:
        delta=result['window_start_unix_s']-start
        tr['times_s']=[t+delta for t in tr['times_s']];tr['departure_s']+=delta;tr['arrival_s']+=delta
    pr=MetricProjection({'projection':read(P/'output/research_points/study/M2/result.json')['projection']})
    try:when=datetime.fromisoformat(req['window_start_utc']).timestamp()-start
    except (ValueError,TypeError):when=0
    view={'key':key,'label':item['label'],'status':result['status'],'reason':result.get('failure_reason') or '',
          'run_id':result.get('run_id','saved_'+key),'trajectory':tr,'departure':when,
          'start_xy':pr.project(req['start']),'end_xy':pr.project(req['end']),
          'ship_check':result.get('ship_check'),
          'checks':{'ships':result.get('ship_check',{}).get('valid') is True if isinstance(result.get('ship_check'),dict) else False,
                    'geometry':(result.get('planning') or {}).get('geometry_valid') is True,
                    'coverage':(result.get('coverage_check') or {}).get('valid') is True},
          'sections':sections(result,item,workspace),
          'origin':start,'raw_sha256':result.get('raw_sha256'),'can_run':item['can_run'],
          'result_json':str((target/'result.json').resolve())}
    replace_json(target/'packet.json',view)
    return view
