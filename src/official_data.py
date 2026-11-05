"""Normalise preserved government data; never invent missing measurements."""
import math
from shapely.geometry import shape

NORMALIZER_VERSION=3

def normalise_buildings(features,origin_lat=22.295):
    """Derive conservative metric envelopes; preserve exact official polygons."""
    seen=set();rows=[];unknown=0
    kx=111000*math.cos(math.radians(origin_lat))
    for feature in features:
        p=feature['properties'];identifier=p['OBJECTID']
        if identifier in seen:raise ValueError('Duplicate government building ID')
        seen.add(identifier)
        if p.get('Status')!='Active':continue
        geometry=shape(feature['geometry'])
        if geometry.is_empty or geometry.geom_type not in ('Polygon','MultiPolygon'):
            raise ValueError('Missing official footprint: '+str(identifier))
        xmin,ymin,xmax,ymax=geometry.bounds
        if not all(math.isfinite(v) for v in geometry.bounds):raise ValueError('Non-finite footprint')
        base,top=p.get('BaseHeight'),p.get('TopHeight')
        valid=all(isinstance(x,(int,float)) and math.isfinite(x) for x in [base,top]) and top>=base
        height=top-base if valid else None
        unknown+=not valid
        rows.append({'id':str(identifier),'name':p.get('BuildingNameEN') or p.get('BuildingNameTC') or 'Building '+str(identifier),
                     'lat':(ymin+ymax)/2,'lon':(xmin+xmax)/2,'height_m':height,'base_hkpd_m':base,'top_hkpd_m':top,
                     'footprint_w_m':(xmax-xmin)*kx,'footprint_l_m':(ymax-ymin)*111000,
                     'height_status':'official_top_minus_base' if valid else 'unknown_conservatively_blocked',
                     'source_kind':'official_derived','use':p.get('BuildingBlockType','unknown'),
                     'official_properties':p,'geometry':feature['geometry']})
    return {'source_kind':'official_derived','source':'Lands Department / CSDI Building',
            'dataset_id':'landsd_rcd_1637211194312_35158','horizontal_crs':'EPSG:4326',
            'vertical_datum':'Hong Kong Principal Datum; height_m=TopHeight-BaseHeight, not TopHeight alone',
            'geometry_model':'official polygon preserved; search uses its conservative bounding rectangle circumcircle + research buffer',
            'unknown_height_policy':'always treat as obstacle; do not replace null height with zero',
            'unknown_height_count':unknown,'buildings':rows}

def verify_feature_ids(expected_ids,features):
    got=[f['properties']['OBJECTID'] for f in features]
    if len(got)!=len(set(got)) or set(got)!=set(expected_ids):raise ValueError('Official feature ID completeness mismatch')

def normalise_registry(xml_bytes):
    import xml.etree.ElementTree as ET
    records=[{c.tag:(c.text or '').strip() for c in r} for r in ET.fromstring(xml_bytes)]
    return {'source_kind':'official_registration_snapshot','records':records,
            'note':'Administrative vessel identities and text location only; no latitude/longitude; not AIS or coordinates.'}

def normalise_ferry_reference(html_bytes):
    import re,html
    text=html.unescape(re.sub('<[^>]+>',' ',html_bytes.decode('utf-8-sig')))
    text=re.sub(r'\s+',' ',text).replace('–','-')
    match=re.search(r'Central - Tsim Sha Tsui\s+Operator:(.*?)Wan Chai - Tsim Sha Tsui\s+Operator:',text)
    if not match:raise ValueError('Transport Department ferry section not found')
    section=match.group(1)
    journey=re.search(r'Journey time:\s*about\s*(\d+)\s*minutes',section)
    if not journey:raise ValueError('Official journey duration missing')
    timetable=section.split('Timetable:',1)[1]
    pattern=r'(\d{1,2}:\d{2}(?:am|pm)-\d{1,2}:\d{2}(?:am|pm))\s+(\d{1,2}:\d{2}(?:am|pm)-\d{1,2}:\d{2}(?:am|pm)|/)\s+(\d+(?:/\d+)?)'
    c2t,t2c=timetable.split('Tsim Sha Tsui to Central',1)
    rows=[]
    for direction,part in [('Central_to_TST',c2t),('TST_to_Central',t2c)]:
        matches=re.findall(pattern,part)
        if len(matches)!=4:raise ValueError('Unexpected ferry schedule schema')
        for weekday,weekend,frequency in matches:rows.append({'direction':direction,'weekday_interval':weekday,'weekend_interval':weekend,'frequency_minutes_published':frequency})
    return {'source_kind':'official_schedule','source':'Transport Department, HKSAR Government','journey_minutes_about':int(journey.group(1)),
            'rows':rows,'note':'Published service interval/frequency, not actual departures, fleet allocation or GPS tracks. Simulation agents remain a separate controlled scenario.'}

def normalise_ferry_piers(stops_xml,sequence_xml,route_xml):
    import xml.etree.ElementTree as ET
    from pyproj import Transformer
    def records(raw):return [{c.tag:(c.text or '').strip() for c in r} for r in ET.fromstring(raw)]
    stops={r['STOP_ID']:r for r in records(stops_xml)}
    routes=[r for r in records(route_xml) if r.get('ROUTE_ID')=='7030']
    if len(routes)!=1 or routes[0]['ROUTE_NAMEE']!='Tsim Sha Tsui - Central':raise ValueError('Expected official ferry route 7030 not found')
    sequence=[r for r in records(sequence_xml) if r.get('ROUTE_ID')=='7030' and r.get('ROUTE_SEQ')=='1']
    sequence=sorted(sequence,key=lambda r:int(r['STOP_SEQ']))
    if len(sequence)!=2:raise ValueError('Expected two official route stops')
    transformer=Transformer.from_crs(2326,4326,always_xy=True);result=[]
    for row in sequence:
        stop=stops[row['STOP_ID']];x,y=float(stop['X']),float(stop['Y']);lon,lat=transformer.transform(x,y)
        result.append({'stop_id':row['STOP_ID'],'name':row['STOP_NAMEE'],'x_hk1980':x,'y_hk1980':y,'lat':lat,'lon':lon,'source_kind':'official_derived'})
    return {'source_kind':'official_derived','route_id':'7030','stops':result,'journey_minutes_about':int(routes[0]['JOURNEY_TIME']),'coordinate_source_crs':'EPSG:2326','output_crs':'EPSG:4326'}

def ferry_scenario(reference,piers,minutes=1440,fleet_size=3):
    """Schedule-constrained synthetic motion, never actual dispatch or AIS.

    Published frequency ranges use their midpoint to allocate round-trip dwell.
    Trips already under way finish after service close; no teleport at closure.
    """
    import re
    def clock(value):
        match=re.fullmatch(r'(\d+):(\d+)(am|pm)',value)
        if not match:raise ValueError('Invalid official service clock')
        h,m,half=match.groups();return int(h)%12*60+int(m)+(720 if half=='pm' else 0)
    rows=[r for r in reference['rows'] if r['direction']=='Central_to_TST']
    intervals=[]
    for row in rows:
        a,b=row['weekday_interval'].split('-');freq=[int(x) for x in row['frequency_minutes_published'].split('/')]
        intervals.append((clock(a),clock(b),sum(freq)/len(freq)))
    opening=min(a for a,b,f in intervals);closing=max(b for a,b,f in intervals)
    def frequency(t):return next((f for a,b,f in intervals if a<=t<b),intervals[-1][2])
    # Route 7030 sequence 1 is explicitly TST -> Central in ROUTE_FERRY.
    # Do not guess locality from pier names (the TST name is Salisbury Road).
    stops=piers['stops'];tst,central=stops
    endpoints=[[central['lat'],central['lon']],[tst['lat'],tst['lon']]];journey=reference['journey_minutes_about'];tracks=[];events=[]
    for i in range(fleet_size):
        departure=opening+i*frequency(opening);side=0;legs=[]
        while departure<closing:
            arrival=departure+journey;legs.append((departure,arrival,side,1-side))
            events.append({'agent_id':f'StarFerry_{i}','departure_minute':departure,'arrival_minute':arrival,'source_kind':'synthetic_schedule_constrained'})
            dwell=max(1,(fleet_size*frequency(departure)-2*journey)/2)
            side=1-side;departure=arrival+dwell
        track=[];index=0;last=endpoints[0]
        for minute in range(minutes):
            while index<len(legs) and minute>=legs[index][1]:last=endpoints[legs[index][3]];index+=1
            if index<len(legs) and legs[index][0]<=minute<legs[index][1]:
                a,b,left,right=legs[index];u=(minute-a)/(b-a);point=[endpoints[left][k]+u*(endpoints[right][k]-endpoints[left][k]) for k in [0,1]]
            else:point=list(last)
            track.append(point)
        tracks.append(track)
    return tracks,events
