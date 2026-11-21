"""Check the downloaded November evidence offline, without launching a solver."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]


def read(name):
    return json.loads((ROOT / name).read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    release = json.loads((PROJECT / 'FILE_MANIFEST.json').read_bytes())
    for item in release['files']:
        if item['path'].startswith('research/ais-2026-11/'):
            require(sha256((PROJECT / item['path']).read_bytes()).hexdigest() == item['sha256'], item['path'])
    archives = read('archive-manifest.json')
    with ZipFile(PROJECT/'runtime/data/current-data.zip') as original:
        for name,ref in read('study-inputs.json').items():
            body=(PROJECT/name).read_bytes() if ref['source']=='project' else original.read(name)
            require(sha256(body).hexdigest()==ref['sha256'] and len(body)==ref['bytes'],name)
    for name, manifest in archives.items():
        with ZipFile(ROOT / name) as archive:
            require(sha256((ROOT / name).read_bytes()).hexdigest() == manifest['sha256'], name)
            require(sorted(archive.namelist()) == sorted(manifest['files']), name + ' file list')
            for file, checksum in manifest['files'].items():
                require(sha256(archive.read(file)).hexdigest() == checksum, name + '/' + file)

    campaign = read('延长AIS观测验证结果.json')
    journal = read('journal.json')
    slots = {slot['slot']:slot for slot in journal['slots'].values()}
    require(len(slots) == 48 and campaign['complete'], 'Incomplete campaign')
    required_pairs = set()
    attempts = {}
    for slot in slots.values():
        for a in slot['attempts']:
            require(a['capture_id'] not in attempts, 'Duplicate journal capture')
            attempts[a['capture_id']] = a
        if slot['status'] == 'candidate':
            required_pairs.update((slot['slot'], route) for route in ('M1','M2','M3','M4'))
    results = campaign['attempts']
    require(len(results) == len(required_pairs) == 76, 'Campaign run count')
    require({(r['slot'],r['route']) for r in results} == required_pairs, 'Missing or duplicate route/window')
    require(Counter(r['evaluation'] for r in results) ==
            {'planned_with_observed_ship_check':75, 'verified_start_rejection':1}, 'Campaign outcomes')
    require(sum((r.get('seconds_without_any_supported_ship') or 0)>0 for r in results)==12, 'Coverage gaps')
    for r in results:
        slot = slots[r['slot']]
        require((r['departure_hkt'],r['capture_id']) == (slot['fixed_departure_hkt'],slot['capture_id']), r['run_id'])

    history = read('额外AIS样本初步验证.json')['attempts']
    precheck = read('首窗完整性复核.json')['attempts']
    require(len(history)==len(precheck)==4, 'Secondary records')
    all_runs = results+history+precheck
    ids = {r['run_id'] for r in all_runs}
    require(len(ids)==len(all_runs), 'Duplicate run ID')
    with ZipFile(ROOT/'ais-captures.zip') as raw, ZipFile(ROOT/'run-records.zip') as runs:
        capture_hash = {}
        for file in raw.namelist():
            if not file.endswith('/capture.json'):
                continue
            prefix=file.rsplit('/',1)[0]
            ident=prefix.rsplit('/',1)[-1]
            data=sha256(raw.read(prefix+'/messages.jsonl')).hexdigest()
            meta=json.loads(raw.read(file))
            if 'raw_sha256' in meta:
                require(data==meta['raw_sha256'],file)
            else:
                require(meta['status']=='collecting' and ident not in attempts,file)
            if ident in attempts:
                require(data==attempts[ident]['raw_sha256'],ident)
            require(ident not in capture_hash,'Duplicate capture ID')
            capture_hash[ident]=data
        require(attempts.keys() <= capture_hash.keys(),'Missing journal capture')
        require({f.split('/')[1] for f in runs.namelist() if f.startswith('runs/')}==ids,'Missing run folder')
        for row in all_runs:
            key=row['run_id']
            full=json.loads(runs.read('runs/'+key+'/result.json'))
            require(full['run_id']==key and full['status']==row['status'],key)
            require(capture_hash[row['capture_id']]==row['raw_sha256'],key+' capture source')
            if row in precheck:
                require(full['status']=='error',key)
            else:
                require(full['capture_id']==row['capture_id'] and full['raw_sha256']==row['raw_sha256'],key)
        stop, = [r for r in results if r['evaluation']=='verified_start_rejection']
        require((ROOT/'M4-rejected-result.json').read_bytes()==runs.read('runs/'+stop['run_id']+'/result.json'),'M4 example')
    print('VERIFIED: archive checksums, 48 windows, 76 main runs (75 planned, 1 rejected; 12 with coverage gaps), '
          '4 historical runs and 4 preliminary errors.')


if __name__=='__main__':
    main()
