"""Read-only audit of published claims, benchmark data, links and demo media."""
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

from PIL import Image, ImageSequence

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'poker_lab'))


def main():
    from pokerlab.strategies import all_strategies,selectable_strategies
    assert len(all_strategies())==80 and len(selectable_strategies())==86
    assert len(json.loads((ROOT/'research/papers.json').read_text())['papers'])==18
    spec=importlib.util.spec_from_file_location('research_report',ROOT/'research/build_report.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    final=json.loads((module.RESULTS/'benchmark.json').read_text());module.audit(final)
    initial=module.RESULTS/'screening_v1'
    data=json.loads((initial/'benchmark.json').read_text())
    assert hashlib.sha256((initial/'hands.csv.gz').read_bytes()).hexdigest()==data['raw_sha256']
    assert hashlib.sha256((initial/'blueprints.json').read_bytes()).hexdigest()==data['blueprint_sha256']
    with gzip.open(initial/'hands.csv.gz','rt') as f:initial_count=sum(1 for _ in csv.DictReader(f))
    assert initial_count==data['total_hands']==192500
    manifest=json.loads((module.RESULTS/'manifest.json').read_text())
    for path,digest in manifest['sha256'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
    checked_links=0
    for path in ROOT.rglob('*.md'):
        if any(part.startswith('.') or part in ('upstream','node_modules') for part in path.relative_to(ROOT).parts):continue
        content=path.read_text()
        targets=re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',content)+re.findall(r'(?:src|href)="([^"]+)"',content)
        for target in targets:
            if re.match(r'^(?:[a-z]+:|#|/)',target):continue
            target=target.split('#')[0].split(' "')[0].strip('<>')
            assert (path.parent/target).exists(),f'Broken local link in {path}: {target}'
            checked_links+=1
    media=json.loads((ROOT/'docs/media/manifest.json').read_text())
    for item in media['outputs']:
        path=ROOT/item['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        with Image.open(path) as image:
            assert image.is_animated and image.n_frames>1
            duration=sum(f.info.get('duration',0) for f in ImageSequence.Iterator(image))
            assert duration==item['duration_ms'],(path,duration,item['duration_ms'])
        assert item['bytes']<8_000_000,'README GIF exceeds 8 MB budget'
    for arch in ('arm64','intel'):
        d=json.loads((ROOT/f'desktop/validation-v2-macos-{arch}.json').read_text())
        assert d['fields_wrong']==d['repeat_fields_wrong']==0
        assert d['coverage']>=.98 and d['critical_correct_frames']/d['frames']>=.85
        assert d['validation']['passed']
    summary={'passed':True,'original_policies':80,'selectable_policies':86,'papers':18,
        'audited_final_hands':final['total_hands'],'retained_initial_hands':initial_count,
        'local_links_checked':checked_links,'animations_checked':len(media['outputs']),
        'scope':'Data, media and link integrity; not live capture or production accuracy.'}
    if '--output' in sys.argv:
        Path(sys.argv[sys.argv.index('--output')+1]).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
