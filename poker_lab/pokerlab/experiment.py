"""Seeded matched-deal screening, fresh validation, and sit-and-go testing."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from dataclasses import asdict
from collections import Counter
from functools import lru_cache
import argparse,csv,json,hashlib,platform,sys,time,random
import numpy as np
from scipy.stats import t
from .strategies import all_strategies,baseline_strategies,registry_rows
from .engine import play_hand

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'results'
BLINDS=(20,30,40,60,100,150,200,300)
PAYOUTS=(50.,30.,20.,0.,0.,0.,0.,0.)


def write_csv(path,rows):
    if not rows:return
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def ci(values):
    a=np.asarray(values,dtype=float); n=len(a)
    if n<2:return float(a.mean()),float(a.mean())
    error=t.ppf(.975,n-1)*a.std(ddof=1)/np.sqrt(n)
    return float(a.mean()-error),float(a.mean()+error)


def cash_job(payload):
    sid,hands,seed,field=payload
    strategy=next(s for s in all_strategies() if s.id==sid)
    lineup=[strategy]+baseline_strategies(field)
    rows=[];counts=Counter();latencies=[]
    for h in range(hands):
        hero=h%8
        seating=[lineup[(i-hero)%8] for i in range(8)]
        r=play_hand(seating,[2000]*8,20,seed+h*1009)
        net=r['net'][hero]
        rows.append({'strategy':sid,'hand':h,'seed':seed+h*1009,'seat':hero,
                     'net_chips':net,'net_bb':net/20,'field':field})
        counts.update(r['counts'][hero]);latencies.extend(r['times_ns'])
    nets=[row['net_bb'] for row in rows];lo,hi=ci(np.array(nets)*100)
    return dict(strategy=sid,family=strategy.family,hands=hands,field=field,
                bb_per_100=float(np.mean(nets)*100),ci95_low=lo,ci95_high=hi,
                net_chips=sum(row['net_chips'] for row in rows),
                profitable_hand_pct=float(np.mean(np.array(nets)>0)*100),
                raises=counts['raise'],calls=counts['call'],folds=counts['fold'],checks=counts['check'],
                decisions_timed=len(latencies),latency_p99_ms=float(np.percentile(latencies,99)/1e6),
                over_1ms=sum(x>1_000_000 for x in latencies)),rows


@lru_cache(maxsize=10000)
def icm(stacks,payouts):
    """Exact ICM expected points of survivors, not Monte Carlo ICM."""
    if len(stacks)==1:return (payouts[0],)
    total=sum(stacks);ans=[0.]*len(stacks)
    if not any(payouts):return tuple(ans)
    for first,stack in enumerate(stacks):
        p=stack/total;ans[first]+=p*payouts[0]
        rest=icm(stacks[:first]+stacks[first+1:],payouts[1:])
        for j,value in enumerate(rest):ans[j+(j>=first)]+=p*value
    return tuple(ans)


def tournament(strategy,seed,field='mixed',cap=200,payouts=PAYOUTS):
    lineup=[strategy]+baseline_strategies(field)
    # Initial hero seat is matched across candidates and randomized over tables.
    offset=seed%8
    ids=list(range(8));ids=ids[-offset:]+ids[:-offset] if offset else ids
    stacks={i:2000 for i in ids};stats={i:[3.,10.,2.,8.] for i in ids}
    points={i:0. for i in ids};finish={};total_decisions=0;above=0;times=[]
    played=0
    for h in range(cap):
        n=len(ids)
        if n<=1:break
        bb=BLINDS[min(h//25,len(BLINDS)-1)]
        played+=1
        before=[stacks[i] for i in ids]
        r=play_hand([lineup[i] for i in ids],before,bb,seed*100003+h*1009,
                    stats=[stats[i] for i in ids],tournament=True)
        total_decisions+=r['decisions'];times.extend(r['times_ns'])
        for i,stack in zip(ids,r['after']):stacks[i]=stack
        busted=[i for i in ids if stacks[i]==0]
        # Simultaneous busts: larger start-of-hand stack finishes higher.
        # Equal start stacks split the tied finishing positions' points.
        if busted:
            ordered=sorted(busted,key=lambda i:before[ids.index(i)])
            first_rank=n
            k=0
            while k<len(ordered):
                j=k+1
                while j<len(ordered) and before[ids.index(ordered[j])]==before[ids.index(ordered[k])]:j+=1
                ranks=list(range(first_rank-(j-k)+1,first_rank+1))
                award=sum(payouts[r-1] for r in ranks)/(j-k)
                for i in ordered[k:j]:points[i]=award;finish[i]=float(np.mean(ranks))
                first_rank-=j-k;k=j
        ids=[i for i in ids if stacks[i]>0]
        assert sum(stacks.values())==16000
        if ids:ids=ids[1:]+ids[:1]
    if len(ids)==1:
        points[ids[0]]=payouts[0];finish[ids[0]]=1.
        capped=False
    else:
        shares=icm(tuple(stacks[i] for i in ids),tuple(payouts[:len(ids)]))
        for i,p in zip(ids,shares):points[i]=p
        capped=True
    assert abs(sum(points.values())-sum(payouts))<1e-7
    hero=0
    return dict(strategy=strategy.id,seed=seed,field=field,hands=played,
                points=points[hero],finish=finish.get(hero,''),capped=int(capped),
                final_chips=stacks[hero],decisions=total_decisions,
                over_1ms=sum(x>1_000_000 for x in times),
                latency_p99_ms=float(np.percentile(times,99)/1e6))


def tournament_job(payload):
    sid,tables,seed,field=payload
    strategy=next(s for s in all_strategies() if s.id==sid)
    rows=[tournament(strategy,seed+k,field) for k in range(tables)]
    values=[r['points'] for r in rows];lo,hi=ci(values)
    return dict(strategy=sid,family=strategy.family,field=field,tables=tables,
                mean_points=float(np.mean(values)),ci95_low=lo,ci95_high=hi,
                wins=sum(r['finish']==1 for r in rows),
                top3=sum(r['finish']!='' and r['finish']<=3 for r in rows),
                capped_tables=sum(r['capped'] for r in rows),
                table_hands=sum(r['hands'] for r in rows)),rows


def league_block(payload):
    block,rounds=payload
    strategies=all_strategies();order=list(range(80))
    random.Random(44001111+block).shuffle(order)
    rows=[]
    for g in range(10):
        group=order[g*8:g*8+8]
        for rotation in range(rounds):
            seats=group[rotation:]+group[:rotation]
            seed=54001111+block*100003+g*1009+rotation*53
            r=play_hand([strategies[i] for i in seats],[2000]*8,20,seed)
            for seat,i in enumerate(seats):
                rows.append(dict(strategy=strategies[i].id,hand=block*8+rotation,
                                 block=block,seat=seat,seed=seed,net_bb=r['net'][seat]/20))
    return {},rows


def run_league(hands,workers):
    jobs=[(b,min(8,hands-b*8)) for b in range((hands+7)//8)]
    _,rows=parallel(jobs,league_block,workers,'self-play')
    by={s.id:[] for s in all_strategies()}
    for r in rows:by[r['strategy']].append(r['net_bb'])
    summary=[]
    for s in all_strategies():
        vals=np.array(by[s.id])*100;lo,hi=ci(vals)
        summary.append(dict(strategy=s.id,family=s.family,hands=len(vals),
                            bb_per_100=float(vals.mean()),ci95_low=lo,ci95_high=hi))
    summary.sort(key=lambda x:-x['bb_per_100']);rows.sort(key=lambda x:(x['strategy'],x['hand']))
    write_csv(RESULTS/'selfplay.csv',summary);write_csv(RESULTS/'selfplay_hands.csv',rows)
    assert abs(sum(r['net_bb'] for r in rows))<1e-6
    print('Self-play leaders:',[(r['strategy'],round(r['bb_per_100'],2)) for r in summary[:8]],flush=True)


def parallel(jobs,fn,workers,label):
    summaries=[];details=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(fn,j):j[0] for j in jobs}
        for k,future in enumerate(as_completed(futures),1):
            summary,rows=future.result();summaries.append(summary);details.extend(rows)
            if k%8==0 or k==len(jobs):print(f'{label}: {k}/{len(jobs)} complete',flush=True)
    return summaries,details


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--hands',type=int,default=500)
    p.add_argument('--validation-hands',type=int,default=2000)
    p.add_argument('--tables',type=int,default=128)
    p.add_argument('--workers',type=int,default=8)
    p.add_argument('--stage',choices=['screen','league','validate','tournament','all'],default='all')
    args=p.parse_args();RESULTS.mkdir(exist_ok=True)
    start=time.time()
    write_csv(ROOT/'strategies.csv',registry_rows())
    if args.stage in ['league','all']:
        run_league(args.hands,args.workers)
    if args.stage in ['screen','all']:
        jobs=[(s.id,args.hands,20261111,'mixed') for s in all_strategies()]
        summary,rows=parallel(jobs,cash_job,args.workers,'screen')
        summary.sort(key=lambda x:x['bb_per_100'],reverse=True)
        rows.sort(key=lambda x:(x['strategy'],x['hand']))
        write_csv(RESULTS/'screening.csv',summary);write_csv(RESULTS/'screening_hands.csv',rows)
        print('Screening leaders:',[(r['strategy'],round(r['bb_per_100'],2)) for r in summary[:8]],flush=True)
    if args.stage in ['validate','all']:
        screen=list(csv.DictReader((RESULTS/'screening.csv').open()))
        # Keep every mechanism in the validation set, alongside the raw top 8.
        selected=[r['strategy'] for r in screen[:8]];seen=set()
        if (RESULTS/'selfplay.csv').exists():
            selected.extend(r['strategy'] for r in list(csv.DictReader((RESULTS/'selfplay.csv').open()))[:8])
        for r in screen:
            if r['family'] not in seen:
                seen.add(r['family']);selected.append(r['strategy'])
        selected=list(dict.fromkeys(selected))
        jobs=[(sid,args.validation_hands,71261111,'mixed') for sid in selected]
        summary,rows=parallel(jobs,cash_job,args.workers,'validation')
        summary.sort(key=lambda x:x['bb_per_100'],reverse=True)
        rows.sort(key=lambda x:(x['strategy'],x['hand']))
        write_csv(RESULTS/'validation.csv',summary);write_csv(RESULTS/'validation_hands.csv',rows)
        print('Validation leaders:',[(r['strategy'],round(r['bb_per_100'],2)) for r in summary[:8]],flush=True)
    if args.stage in ['tournament','all']:
        valid=list(csv.DictReader((RESULTS/'validation.csv').open()))
        selected=[r['strategy'] for r in valid[:8]]
        # Different opponent fields are sensitivity tests, not pooled as IID hands.
        jobs=[(sid,args.tables,91001111,field) for sid in selected for field in ['mixed','tight','aggressive']]
        summary,rows=parallel(jobs,tournament_job,args.workers,'tournament')
        summary.sort(key=lambda x:(x['field'],-x['mean_points']))
        rows.sort(key=lambda x:(x['strategy'],x['field'],x['seed']))
        write_csv(RESULTS/'tournaments.csv',summary);write_csv(RESULTS/'tournament_tables.csv',rows)
    manifest=dict(date='2026-11-11',python=sys.version,platform=platform.platform(),
                  parameters=vars(args),elapsed_seconds=time.time()-start,
                  format='Eight-player no-limit Texas Holdem; offline research, not official event engine',
                  baseline_fields=['mixed','tight','aggressive'],blind_schedule=BLINDS,payouts=PAYOUTS,
                  decisions_deadline_enforced=False,preflop_samples_per_class=4000,
                  postflop_samples_per_decision=48,
                  seeds={'screen':20261111,'validation':71261111,'tournament':91001111})
    hashes={}
    for path in sorted(ROOT.rglob('*')):
        if (path.is_file() and path.suffix in ['.py','.json']
            and '__pycache__' not in str(path) and 'results' not in path.relative_to(ROOT).parts):
            hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest['source_sha256']=hashes
    (RESULTS/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Finished in {time.time()-start:.1f} seconds',flush=True)

if __name__=='__main__':main()
