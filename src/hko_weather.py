"""Traceable HKO wind CSV and official station coordinates; no synthetic fallback.

Snapshot data are observations at their stated time, not a historical 24h feed.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import csv
import hashlib
import io
import math
import re
from zoneinfo import ZoneInfo
import requests

WIND_URL='https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/latest_10min_wind.csv'
STATIONS_URL='https://www.hko.gov.hk/en/cis/stn.htm'
DATASET_URL='https://data.gov.hk/en-data/dataset/hk-hko-rss-latest-ten-minute-wind-info'
HK=ZoneInfo('Asia/Hong_Kong')
NORMALIZER_VERSION=2
COMPASS=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
WORDS=['north','northnortheast','northeast','eastnortheast','east','eastsoutheast','southeast','southsoutheast','south','southsouthwest','southwest','westsouthwest','west','westnorthwest','northwest','northnorthwest']

class WeatherDataError(ValueError):
    pass

def normal_name(value):
    return re.sub(r'[^a-z0-9]','',value.casefold())

def dms_to_degrees(value):
    match=re.fullmatch(r'\s*(\d+)\s*[°º]\s*(\d+)\s*[\'′]\s*(\d+(?:\.\d+)?)\s*["″]\s*',value)
    if not match:
        raise WeatherDataError('Unrecognised official coordinate: '+value)
    deg,minute,second=map(float,match.groups())
    if minute>=60 or second>=60:
        raise WeatherDataError('Invalid coordinate minutes/seconds')
    return deg+minute/60+second/3600

class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[];self.row=None;self.cell=None;self.allowed=False;self.table_id=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            self.table_id=dict(attrs).get('id')
            self.allowed=self.table_id in ('manned','automatic','weather_buoy','wind')
        if tag=='tr' and self.allowed: self.row=[]
        if tag in ('td','th') and self.row is not None:self.cell=[]
        if tag=='br' and self.cell is not None:self.cell.append(' ')
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.row is not None:
            self.rows.append((self.table_id,self.row));self.row=None
        if tag=='table':self.allowed=False

def parse_station_locations(raw):
    parser=_TableRows();parser.feed(raw.decode('utf-8-sig'))
    result={}
    for table_id,cells in parser.rows:
        if len(cells)<3:continue
        if table_id!='wind' and (len(cells)<5 or '✔' not in cells[4]):continue
        # A terminated station has a date range, intentionally not accepted here.
        m=re.fullmatch(r'(.*?)\s*\(([A-Z0-9]+)\)\s*\(\d{2}/\d{2}/\d{4}\)',cells[0])
        if not m:continue
        try:lat,lon=dms_to_degrees(cells[1]),dms_to_degrees(cells[2])
        except WeatherDataError:continue
        if not (20<lat<24 and 112<lon<116):continue
        name,code=m.groups()
        key=normal_name(name.rstrip('* '))
        if key in result:
            raise WeatherDataError('Ambiguous official station name: '+name)
        result[key]={'id':code,'name':name.rstrip('* '),'lat':lat,'lon':lon,'latitude_dms':cells[1],'longitude_dms':cells[2],'coordinate_source':STATIONS_URL}
    # CSV abbreviation versus explicitly named Kowloon station on the official table.
    if 'starferrykowloon' in result:result['starferry']=result['starferrykowloon']
    if 'tuenmungovernmentoffices' in result:result['tuenmun']=result['tuenmungovernmentoffices']
    # Official station-page footnote: Tap Mun wind was replaced by Tap Mun East in 2017.
    if 'tapmuneast' in result:result['tapmun']=result['tapmuneast']
    if len(result)<3:raise WeatherDataError('Official station table was not parsed; no coordinate guessing')
    return result

def _speed(value, allow_calm=False):
    value=(value or '').strip()
    if allow_calm and value.casefold()=='calm':return 0.0
    if value.casefold() in ('','n/a','na','-'):return None
    try:number=float(value)
    except ValueError:raise WeatherDataError('Invalid wind speed: '+value)
    if not math.isfinite(number) or number<0:raise WeatherDataError('Negative or non-finite wind speed')
    return number/3.6

def _direction(value):
    key=normal_name(value)
    if key in ('calm','variable','na',''):return None
    if key in WORDS:return WORDS.index(key)*22.5
    if key in [c.casefold() for c in COMPASS]:return [c.casefold() for c in COMPASS].index(key)*22.5
    raise WeatherDataError('Unknown wind direction: '+value)

def parse_wind_csv(raw, locations):
    text=raw.decode('utf-8-sig')
    reader=csv.DictReader(io.StringIO(text))
    fields=reader.fieldnames or []
    expected=['Date time','Automatic Weather Station','10-Minute Mean Wind Direction(Compass points)','10-Minute Mean Speed(km/hour)','10-Minute Maximum Gust(km/hour)']
    if fields!=expected:raise WeatherDataError('HKO CSV schema changed or response was not wind CSV')
    stations={};excluded=[]
    for row in reader:
        name=(row.get(expected[1]) or '').strip()
        try:
            observed=datetime.strptime(row[expected[0]].strip(),'%Y%m%d%H%M').replace(tzinfo=HK)
            mean=_speed(row.get(expected[3]),allow_calm=True)
            direction_text=(row.get(expected[2]) or '').strip()
            if mean is None and direction_text.casefold()=='calm':mean=0.0
            if mean is None:
                excluded.append({'station':name,'reason':'missing_mean_speed'});continue
            direction=_direction(direction_text)
            gust=_speed(row.get(expected[4]),allow_calm=True)
            key=normal_name(name)
            if key not in locations:
                excluded.append({'station':name,'reason':'no_verified_coordinate_match'});continue
            record={**locations[key],'name':name,'speed':mean,'dir':direction,'direction_text':direction_text,'gust_mps':gust,'observed_at':observed.isoformat(),'source_kind':'observation','unit':'m/s','raw_unit':'km/h'}
            previous=stations.get(record['id'])
            if previous and previous['observed_at']==record['observed_at']:
                if previous!=record:raise WeatherDataError('Conflicting duplicate station observation')
            elif previous is None or observed > datetime.fromisoformat(previous['observed_at']):
                stations[record['id']]=record
        except (TypeError,KeyError,ValueError) as error:
            raise WeatherDataError(f'Invalid HKO record for {name}: {error}') from error
    if not stations:raise WeatherDataError('No valid observed winds with verified coordinates; no fallback')
    return sorted(stations.values(),key=lambda s:s['id']),excluded

def observation_status(snapshot,now=None,max_age_seconds=1800):
    now=now or datetime.now(HK)
    if now.tzinfo is None:raise WeatherDataError('Freshness clock must include timezone')
    stations=snapshot.get('stations',[])
    if not stations:return {'state':'unavailable','age_seconds':None}
    observed=[datetime.fromisoformat(s['observed_at']) for s in stations]
    if any(t.tzinfo is None for t in observed):raise WeatherDataError('Observation timestamps must include timezone')
    ages=[(now-t).total_seconds() for t in observed]
    if min(ages)<-300:return {'state':'future_clock','age_seconds':max(ages)}
    return {'state':'stale' if max(ages)>max_age_seconds else 'fresh','age_seconds':max(0,max(ages)),'max_age_seconds':max_age_seconds}

def fetch_snapshot(session=None):
    session=session or requests.Session()
    raw={}
    for key,url in [('wind',WIND_URL),('stations',STATIONS_URL)]:
        response=session.get(url,timeout=(5,20))
        response.raise_for_status();raw[key]=response.content
    fetched=datetime.now(HK)
    locations=parse_station_locations(raw['stations'])
    stations,excluded=parse_wind_csv(raw['wind'],locations)
    snapshot={'schema_version':1,'normalizer_version':NORMALIZER_VERSION,'source':'Hong Kong Observatory latest 10-minute wind CSV','source_kind':'observation','data_url':WIND_URL,'dataset_url':DATASET_URL,'coordinates_url':STATIONS_URL,'fetched_at':fetched.isoformat(),'note':'A frozen observation snapshot, not 24-hour wind history or a forecast. Spatial interpolation is an approximation. HKO labels this data provisional.','stations':stations,'excluded_records':excluded,'raw_hashes':{k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}}
    snapshot['status_at_fetch']=observation_status(snapshot,fetched)
    return snapshot,raw
