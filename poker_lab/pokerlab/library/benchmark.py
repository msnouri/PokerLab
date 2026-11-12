"""Paired-deal comparison of the library policies against S55.

Every candidate plays the same deals from the same seats against the same
opponents, so the reported difference to S55 removes most card luck. Stacks
reset every hand (cash-game chips, no ICM). Opponents are this repository's
own heuristic baselines, so results say nothing about human or solver fields.

    python -m pokerlab.library.benchmark --deals 3000 --workers 2
"""
import argparse
import json
import math
from multiprocessing import Pool
from pathlib import Path
from ..engine import play_hand
from ..strategies import selectable_strategies,baseline_strategies

OUT=Path(__file__).resolve().parents[2]/'library_results'/'benchmark.json'
BB=20
FORMATS={
 'six_max_100bb':dict(players=6,depth=100,field='mixed'),
 'six_max_15bb':dict(players=6,depth=15,field='mixed'),
 'heads_up_100bb_vs_S55':dict(players=2,depth=100,field='S55'),
 'heads_up_12bb_vs_S55':dict(players=2,depth=12,field='S55'),
}
CANDIDATES=('S55','T01','T02','T03','T04')


def chunk(args):
    name,candidate,deals,offset=args
    spec=FORMATS[name];registry={s.id:s for s in selectable_strategies()}
    hero=registry[candidate];n=spec['players']
    opponents=[registry['S55']] if spec['field']=='S55' else baseline_strategies(spec['field'])[:n-1]
    nets=[]
    for d in range(offset,offset+deals):
        for seat in range(n):
            table=opponents[:seat]+[hero]+opponents[seat:]
            # Identical seed for every candidate: same cards, same opponent variates.
            result=play_hand(table,[spec['depth']*BB]*n,BB,seed=9_000_000+d*7+len(name))
            nets.append(result['net'][seat]/BB)
    return name,candidate,offset,nets


def summarize(nets,base=None):
    n=len(nets);mean=sum(nets)/n
    sd=math.sqrt(sum((x-mean)**2 for x in nets)/(n-1))
    row={'hands':n,'bb_per_100':round(100*mean,2),'ci95':round(196*sd/math.sqrt(n),2)}
    if base is not None:
        diff=[a-b for a,b in zip(nets,base)];m=sum(diff)/n
        s=math.sqrt(sum((x-m)**2 for x in diff)/(n-1))
        row['paired_vs_S55_bb_per_100']=round(100*m,2);row['paired_ci95']=round(196*s/math.sqrt(n),2)
    return row


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--deals',type=int,default=3000)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    size=250
    jobs=[(f,c,min(size,args.deals-o),o) for f in FORMATS for c in CANDIDATES for o in range(0,args.deals,size)]
    collected={}
    with Pool(args.workers) as pool:
        for name,candidate,offset,nets in pool.imap_unordered(chunk,jobs):
            collected.setdefault((name,candidate),{})[offset]=nets
    results={}
    for name in FORMATS:
        flat={c:[x for o in sorted(collected[(name,c)]) for x in collected[(name,c)][o]] for c in CANDIDATES}
        results[name]={c:summarize(flat[c],None if c=='S55' else flat['S55']) for c in CANDIDATES}
        print(name)
        for c,row in results[name].items():print('  ',c,row,flush=True)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'schema_version':1,'deals_per_format':args.deals,'big_blind':BB,
        'formats':FORMATS,'opponents':'baseline_strategies("mixed") or S55; stacks reset each hand',
        'scope':'Simulated chips against in-repo heuristics; not evidence about human, solver or real-money play.',
        'results':results},indent=2)+'\n')


if __name__=='__main__':main()
