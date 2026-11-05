"""Local presentation geometry only. No changes to planner/data snapshots/results."""
from pathlib import Path
import json,hashlib,sys,math,shutil,datetime
import requests
from shapely.geometry import shape,box,LineString
from shapely import set_precision
from shapely.ops import transform,unary_union,polygonize,triangulate
from pyproj import Transformer
B=Path(__file__).resolve().parents[2];P=B/'outputs/uav-maritime-twin-windows';D=Path(__file__).resolve().parent;O=P/'anylogic/visual_demo';backup=D/'before'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
w=read(P/'anylogic/workbench/workspace.json')
if not (D/'protected.json').exists():
    paths=[*sorted((P/'src').glob('*.py')),P/'config.yaml',P/'config/ais-single-task.json',P/'config/parameter-sources.json',P/'anylogic/workbench/workspace.json',P/'output/ais_single_task/ompl_sst/catalog.json',P/'data/ais/captures'/w['source']['capture_id']/'messages.jsonl',P/'data/official/snapshots/28991d3a0c66d1fa/buildings.json',*sorted((P/'runtime/ompl').glob('*.*'))]
    paths +=[P/'output'/i['file'] for i in w['catalog']]
    (D/'protected.json').write_text(json.dumps({str(p):sha(p) for p in paths},indent=2),encoding='utf-8')
for name in ['anylogic/NativeDemoView.java','anylogic/native-visual-demo.jar','anylogic/AIS_Visual_Demo.alp','anylogic/visual_demo/support.json','build_anylogic_visual.py']:
    dst=backup/name
    if not dst.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/name,dst)
service='https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1637221267230_27829/FeatureServer/6/query'
rawpath=D/'coast_raw.geojson'
if not rawpath.exists():
    params={'f':'geojson','where':"CLASS='SLN' AND TYPE='COA'",'geometry':'114.105,22.255,114.29,22.34','geometryType':'esriGeometryEnvelope','inSR':4326,'outSR':4326,'spatialRel':'esriSpatialRelIntersects','outFields':'*','resultRecordCount':3000}
    response=requests.get(service,params=params,timeout=40);response.raise_for_status();rawpath.write_bytes(response.content)
    (D/'coast_request.json').write_text(json.dumps({'url':response.url,'fetched_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bytes':len(response.content),'http_status':response.status_code,'sha256':sha(rawpath),'dataset':'landsd_rcd_1637221267230_27829','layer':'HYDRLINE CLASS=SLN TYPE=COA','scale':'1:100000 generalized topographic coastline; display only'},indent=2),encoding='utf-8')
coast=read(rawpath);assert coast['features'] and not coast.get('exceededTransferLimit')
projection=Transformer.from_crs(4326,32650,always_xy=True);project=lambda g:transform(projection.transform,g)
llbox=box(114.105,22.255,114.29,22.34);bounds=project(llbox).bounds;clip=box(*bounds)
segments=[]
for f in coast['features']:
    assert f['properties']['CLASS']=='SLN' and f['properties']['TYPE']=='COA'
    g=project(shape(f['geometry'])).intersection(clip)
    if not g.is_empty:segments.extend([g] if g.geom_type=='LineString' else list(g.geoms))
for f in read(D/'reclamation_raw.geojson')['features']:
    assert f['properties']['CLASS']=='SLN' and f['properties']['TYPE']=='RLE'
    g=project(shape(f['geometry'])).intersection(clip)
    if not g.is_empty:segments.extend([g] if g.geom_type=='LineString' else list(g.geoms))
# Close the displayed crop at its boundary, preserving official coastline edges.
network=unary_union([set_precision(g,.01) for g in [*segments,clip.boundary]])
regions=list(polygonize(network))
vegetation=[]
for f in read(D/'land_raw.geojson')['features']:
    g=project(shape(f['geometry'])).intersection(clip)
    if not g.is_empty:vegetation.extend([g] if g.geom_type=='Polygon' else [p for p in getattr(g,'geoms',[]) if p.geom_type=='Polygon'])
vegseeds=[g.representative_point() for g in vegetation]
source=P/'data/official/snapshots/28991d3a0c66d1fa/buildings.json';records=read(source)['buildings']
land=[r for r in regions if any(r.covers(seed) for seed in vegseeds)]
assert len(land)>=2,f'Coastline did not close into independently identifiable land regions: {len(regions)} regions, {len(land)} land, {len(segments)} lines'
land_geometry=unary_union(land)
def polygons(g):return [g] if g.geom_type=='Polygon' else [p for p in getattr(g,'geoms',[]) if p.geom_type=='Polygon']
def rings(g):
    result=[]
    for p in polygons(g.simplify(3,preserve_topology=True)):
        # Preserve holes by triangulating only polygons with interior rings.
        if p.interiors:
            pieces=[piece for t in triangulate(p) for piece in polygons(t.intersection(p)) if piece.area>1e-8]
            assert all(not piece.interiors for piece in pieces)
            assert abs(sum(piece.area for piece in pieces)-p.area)<.01
            result.extend([list(t.exterior.coords) for t in pieces])
        else:result.append(list(p.exterior.coords))
    return result
building_rows=[];west,south,east,north=114.12,22.27,114.27,22.32
landmark_ids={'244524':'IFC 2','161009':'IFC 1','201050':'ICC','123697':'Bank of China','124613':'HKCEC','250931':'Clock Tower'}
for b in records:
    if not(west-.008<=b['lon']<=east+.008 and south-.008<=b['lat']<=north+.008):continue
    g=project(shape(b['geometry']))
    height=b.get('height_m');known=isinstance(height,(int,float)) and math.isfinite(height) and height>0
    for p in polygons(g):
        simplified=p.simplify(2,preserve_topology=True)
        if len(simplified.exterior.coords)>64:simplified=p.simplify(5,preserve_topology=True)
        if len(simplified.exterior.coords)>96:simplified=p.envelope
        center=list(p.representative_point().coords)[0]
        building_rows.append({'id':b['id'],'name':b['name'],'center':center,'xy':list(simplified.exterior.coords),'height_m':height if known else 40.,'height_source':'official_top_minus_base' if known else 'illustrative_fallback_40m','landmark':landmark_ids.get(str(b['id']),''),'footprint_source':'official footprint simplified for display only'})
landmarks=[b for b in building_rows if b['landmark']]
assert len(landmarks)>=6
mid=[sum(b['center'][i] for b in landmarks)/len(landmarks) for i in range(2)]
city_extent=max(max(b['center'][i] for b in landmarks)-min(b['center'][i] for b in landmarks) for i in range(2))*1.7
output={'schema_version':1,'projection':'EPSG:32650','display_only':True,'land':rings(land_geometry),'coastlines':[list(g.simplify(2,preserve_topology=True).coords) for g in segments if g.geom_type=='LineString'],'vegetation':rings(unary_union(vegetation).intersection(land_geometry)),'buildings':building_rows,'landmarks':landmarks,'overview_center_xy':mid,'overview_extent_m':max(5000,city_extent),'provenance':{'buildings_file':str(source),'buildings_sha256':sha(source),'coast_raw_sha256':sha(rawpath),'coast_request':read(D/'coast_request.json'),'vegetation_raw_sha256':sha(D/'land_raw.geojson'),'land_processing':'Official generalized coastline polygonized with crop boundary; land components identified by independently official vegetation representative points. Derived display background, not certified surveyed land polygon. Vegetation never used as complete land extent.','geometry_simplification_m':3,'unknown_building_height_m':40,'height_basis':'Official stored TopHeight minus BaseHeight, not promotional architectural height; unknown 40m remains illustrative; flat ground is display only.','runtime_network_requests':0}}
patches=[p.simplify(12,preserve_topology=True) for p in vegetation if not p.interiors and p.area>=5000 and land_geometry.covers(p)]
output['vegetation']=[list(p.exterior.coords) for p in sorted(patches,key=lambda p:p.area,reverse=True)[:100]]
output['provenance'].update(vegetation_processing='Selected official vegetation polygons without interior holes, area >=5000 m2, simplified 12m; at most 100 display patches, not a complete vegetation inventory.',reclamation_raw_sha256=sha(D/'reclamation_raw.geojson'),reclamation_request=read(D/'reclamation_request.json'),coastline_closure_precision_grid_m=.01,land_processing='Official generalized coastline and reclamation edges polygonized with crop boundary on a 0.01m processing grid; land components identified by independent official vegetation representative points. Derived generalized display background, not certified surveyed land polygon.')
(O/'scenery.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
(D/'preparation.json').write_text(json.dumps({'land_regions':len(land),'land_rings':len(output['land']),'coast_segments':len(segments),'vegetation_rings':len(output['vegetation']),'buildings':len(building_rows),'landmarks':[(b['landmark'],b['height_m']) for b in landmarks],'scenery_bytes':(O/'scenery.json').stat().st_size,'scenery_sha256':sha(O/'scenery.json'),'provenance':output['provenance']},ensure_ascii=False,indent=2),encoding='utf-8')
assert all(sha(p)==h for p,h in read(D/'protected.json').items())
print('Prepared local scenery:',len(land),'land components,',len(segments),'coastlines,',len(building_rows),'buildings,',len(landmarks),'landmarks')
