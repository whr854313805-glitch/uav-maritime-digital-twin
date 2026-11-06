"""Maintainer command: explicitly record the reviewed tracked/unignored release tree."""
from pathlib import Path
import hashlib,json,subprocess

ROOT=Path(__file__).resolve().parents[2]


def main():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
    rows=[]
    for name in sorted(set(names)):
        if not name or name=='FILE_MANIFEST.json':continue
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or name.startswith(('.env','.local/','data/','output/')):raise ValueError('Local/secret path in release: '+name)
        if not p.is_file():continue
        body=p.read_bytes()
        if len(body)>=100*1024**2:raise ValueError('GitHub file size exceeded: '+name)
        rows.append({'path':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
    result={'version':'F25-Windows-security-quality-20261106','files':rows,'bytes':sum(r['bytes'] for r in rows),
            'note':'Reviewed release identity, not a publisher signature. Runtime data/results remain byte-identical. Manifest excludes itself.'}
    (ROOT/'FILE_MANIFEST.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8',newline='')
    print(json.dumps({'files':len(rows),'bytes':result['bytes']}))


if __name__=='__main__':main()
