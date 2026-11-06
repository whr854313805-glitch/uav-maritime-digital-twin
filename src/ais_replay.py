"""Read actual preserved AIS responses; split gaps instead of inventing motion.

Reuses ais_data.normalize/distance_m and the existing Leaflet dashboard.
Fragment qualification is additional to, not a replacement for, whole-track audit.
"""
from collections import Counter, defaultdict
from pathlib import Path
import json
import os
import uuid
from src.ais_data import ENDPOINT, normalize, distance_m, digest, dump

PROJECT = Path(__file__).resolve().parents[1]


def replace_json(path, data):
    """Readers see either the previous or complete new replay bundle."""
    path = Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        dump(temporary,data);os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def build_capture(directory):
    directory=Path(directory)
    capture=json.loads((directory/'capture.json').read_text(encoding='utf-8'))
    if capture['status']=='collecting' or not capture['subscription_confirmed'] or capture['endpoint']!=ENDPOINT:
        raise ValueError('Replay requires a finished, confirmed AISStream capture')
    if digest(directory/'messages.jsonl')!=capture['raw_sha256']:
        raise ValueError('Raw capture hash mismatch')
    quality=capture['config']['quality'];groups=defaultdict(list);discarded=Counter()
    valid_count=0
    for line_number,line in enumerate((directory/'messages.jsonl').read_text(encoding='utf-8').splitlines(),1):
        try:
            p=normalize(json.loads(line),capture['config']);valid_count+=1
            p['raw_line']=line_number;groups[p['mmsi']].append(p)
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            discarded[str(error)]+=1
    vessels=[];breaks=[];fragments=[];duplicates=0
    for mmsi,points in sorted(groups.items()):
        points.sort(key=lambda p:(p['timestamp_unix_s'],p['raw_line']))
        by_time=defaultdict(list)
        for p in points:by_time[p['timestamp_unix_s']].append(p)
        clean=[];conflicts=[]
        for t,rows in by_time.items():
            locations={(p['latitude'],p['longitude']) for p in rows}
            if len(locations)>1:
                conflicts.extend(rows);continue
            clean.append(rows[0]);duplicates+=len(rows)-1
        # Preserve conflicting observations as explicit excluded evidence. Never
        # interpolate across their time even if the remaining endpoints look valid.
        conflict_times=sorted({p['timestamp_unix_s'] for p in conflicts})
        segments=[];segment=[]
        for p in clean:
            if segment:
                a=segment[-1];dt=p['timestamp_unix_s']-a['timestamp_unix_s']
                reason=None
                if any(a['timestamp_unix_s']<=t<=p['timestamp_unix_s'] for t in conflict_times):reason='conflicting_position'
                elif dt>quality['max_gap_seconds']:reason='observation_gap_exceeded'
                elif distance_m(a,p)/dt>quality['max_speed_mps']:reason='position_jump_exceeded'
                if reason:
                    segments.append(segment);segment=[]
                    breaks.append({'mmsi':mmsi,'start':a['timestamp_unix_s'],'end':p['timestamp_unix_s'],
                                   'seconds':dt,'reason':reason})
            segment.append(p)
        if segment:segments.append(segment)
        for index,segment in enumerate(segments):
            if len(segment)>=2 and segment[-1]['timestamp_unix_s']-segment[0]['timestamp_unix_s']>=quality['window_seconds']:
                gaps=[b['timestamp_unix_s']-a['timestamp_unix_s'] for a,b in zip(segment,segment[1:])]
                fragments.append({'mmsi':mmsi,'segment_index':index,'start':segment[0]['timestamp_unix_s'],
                                  'end':segment[-1]['timestamp_unix_s'],'duration_seconds':segment[-1]['timestamp_unix_s']-segment[0]['timestamp_unix_s'],
                                  'max_gap_seconds':max(gaps),'observation_count':len(segment)})
        vessels.append({'mmsi':mmsi,'points':clean,'segments':segments,'conflicting_points':conflicts})
    all_times=[p['timestamp_unix_s'] for vessel in vessels for p in vessel['points']]
    return {'schema_version':1,'capture_id':directory.name,'provider':'AISStream','endpoint':ENDPOINT,
            'capture_started_at_utc':capture['started_at_utc'],'capture_finished_at_utc':capture['finished_at_utc'],
            'capture_status':capture['status'],'capture_seconds':capture['config']['capture_seconds'],
            'bbox':capture['config']['bbox'],'quality_parameters':quality,'raw_sha256':capture['raw_sha256'],
            'raw_bytes':capture['raw_bytes'],'valid_position_count':valid_count,'vessel_count':len(vessels),
            'displayed_observation_count':sum(len(v['points']) for v in vessels),'duplicates':duplicates,
            'discarded_messages':dict(discarded),'start':min(all_times,default=None),'end':max(all_times,default=None),
            'vessels':vessels,'breaks':breaks,'qualified_fragments':fragments,'qualified_fragment_count':len(fragments),
            'longest_contiguous_seconds':max((s[-1]['timestamp_unix_s']-s[0]['timestamp_unix_s'] for v in vessels for s in v['segments']),default=0),
            'scope':'Observed vessel subset, not complete regional coverage. Dashed edges and moving between-point markers are processed interpolation, not observations. Gaps/jumps are disconnected.',
            'timing':'provider time_utc; local received_at_utc and raw-line provenance retained',
            'qualification':'same original numeric QC; 600s contiguous fragment scan is separate from legacy whole-track/common-window audit'}


def publish_capture(directory):
    data=build_capture(directory);directory=Path(directory)
    replace_json(PROJECT/'output/ais_replay/bundle.json',data)
    fragments={'status':'usable_contiguous_fragments' if data['qualified_fragment_count'] else 'no_qualified_contiguous_fragment',
               'capture_id':data['capture_id'],'quality_parameters':data['quality_parameters'],
               'longest_contiguous_seconds':data['longest_contiguous_seconds'],
               'qualified_fragments':data['qualified_fragments'],'gap_breaks':data['breaks'],
               'scope':'Fragment-local qualification; does not imply a common multi-vessel window or all-ship safety.'}
    dump(directory/'fragments_quality.json',fragments)
    dump(directory/'replay_manifest.json',{k:v for k,v in data.items() if k not in ('vessels','breaks')})
    return data
