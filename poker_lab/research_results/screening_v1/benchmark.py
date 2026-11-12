"""Frozen-policy, duplicate-deal benchmarks. No evaluation-time training.

Each statistical unit is a shuffled deal, averaged over both HU seat assignments
or all six six-max assignments. Confidence intervals never count those repeated
assignments as independent deals. All candidates share evaluation deck seeds.
"""
import argparse,csv,gzip,hashlib,json,math,random,time
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from itertools import combinations
from pathlib import Path
import numpy as np
from scipy.stats import t as student
from ..engine import play_hand
from ..strategies import selectable_strategies
from .train import ASSET

CANDIDATES=('S55','R01','R02','R03','R04','R05','R06')
OPPONENTS=('S08','S18','S23','S33')
FIELD=('S08','S18','S23','S33','S78')


def job(spec):
    protocol,candidate,opponent,start,count,seed_base=spec
    strategies={s.id:s for s in selectable_strategies()};rows=[];modes=Counter();times=[];research_times=[]
    for deal in range(start,start+count):
        seed=seed_base+deal*1009
        for seat in range(2 if protocol!='six_max' else 6):
            if protocol=='six_max':
                lineup=[strategies[x] for x in FIELD];lineup.insert(seat,strategies[candidate])
            else:lineup=[strategies[candidate],strategies[opponent]] if seat==0 else [strategies[opponent],strategies[candidate]]
            result=play_hand(lineup,[2000]*len(lineup),20,seed)
            if sum(result['net'])!=0:raise AssertionError('Chip conservation failure')
            rows.append((protocol,candidate,opponent,deal,seat,seed,result['net'][seat]/20))
            for key,value in result['counts'][seat].items():
                if key.startswith('mode_'):modes[key[5:]]+=value
            for ns,mode in zip(result['seat_times_ns'][seat],result['seat_modes'][seat]):
                if len(times)<600:times.append(ns/1e6)
                if mode=='research_blueprint' and len(research_times)<600:research_times.append(ns/1e6)
    return rows,dict(modes),times,research_times


def interval(values):
    a=np.asarray(values,float);mean=float(a.mean())
    error=float(student.ppf(.975,len(a)-1)*a.std(ddof=1)/math.sqrt(len(a))) if len(a)>1 else 0.
    return {'bb100':mean,'ci95_low':mean-error,'ci95_high':mean+error,'independent_deals':len(a)}


def summarize(rows,mode_data,timing_data):
    grouped=defaultdict(lambda:defaultdict(list))
    for protocol,candidate,opponent,deal,seat,seed,bb in rows:
        grouped[(protocol,candidate,opponent)][deal].append(bb*100)
    pairs={k:{deal:float(np.mean(v)) for deal,v in units.items()} for k,units in grouped.items()}
    results=[]
    for key,units in sorted(pairs.items()):
        protocol,candidate,opponent=key;timing,research=timing_data[key];modes=mode_data[key];n=sum(modes.values())
        result=dict(protocol=protocol,candidate=candidate,opponent=opponent,**interval(list(units.values())),
                    policy_modes=dict(modes),research_lookup_fraction=modes.get('research_blueprint',0)/max(1,n),
                    decision_p50_ms=float(np.median(timing)),decision_p95_ms=float(np.quantile(timing,.95)),
                    blueprint_p95_ms=float(np.quantile(research,.95)) if research else None)
        if protocol=='field' and candidate!='S55':
            baseline=pairs[('field','S55',opponent)]
            result['paired_difference_vs_s55']=interval([units[d]-baseline[d] for d in units])
        results.append(result)
    aggregate=[]
    for candidate in CANDIDATES:
        values=[];diff=[]
        for opponent in OPPONENTS:
            units=pairs.get(('field',candidate,opponent),{})
            baseline=pairs.get(('field','S55',opponent),{})
            values.extend(units.values());diff.extend(units[d]-baseline[d] for d in units)
        if not values:continue
        row=dict(candidate=candidate,**interval(values),paired_difference_vs_s55=interval(diff))
        delta=np.asarray(diff,float)
        if candidate!='S55' and delta.std(ddof=1)>0:
            statistic=delta.mean()/(delta.std(ddof=1)/math.sqrt(len(delta)))
            row['p_two_sided']=float(2*student.sf(abs(statistic),len(delta)-1))
        aggregate.append(row)
    tested=sorted((r for r in aggregate if 'p_two_sided' in r),key=lambda r:r['p_two_sided'])
    adjusted=0.
    for i,row in enumerate(tested):
        adjusted=max(adjusted,min(1.,row['p_two_sided']*(len(tested)-i)));row['holm_p']=adjusted
    return {'matchups':results,'field_aggregate':aggregate}


def main():
    p=argparse.ArgumentParser();p.add_argument('--pairs',type=int,default=2500);p.add_argument('--round-robin-pairs',type=int,default=1000)
    p.add_argument('--multiway-deals',type=int,default=250);p.add_argument('--workers',type=int,default=8)
    p.add_argument('--output',type=Path,default=Path('research_results'))
    a=p.parse_args()
    if a.pairs<2 or min(a.round_robin_pairs,a.multiway_deals)<0:p.error('Need at least two field pairs; other stages can be zero')
    a.output.mkdir(parents=True,exist_ok=True);jobs=[];block=250
    def add(protocol,candidate,opponent,total,base):
        for start in range(0,total,block):jobs.append((protocol,candidate,opponent,start,min(block,total-start),base))
    for j,opponent in enumerate(OPPONENTS):
        for candidate in CANDIDATES:add('field',candidate,opponent,a.pairs,771000000+j*10000000)
    for candidate,opponent in combinations(CANDIDATES,2):add('round_robin',candidate,opponent,a.round_robin_pairs,881000000)
    for candidate in CANDIDATES:add('six_max',candidate,'fixed_five',a.multiway_deals,991000000)
    started=time.perf_counter();rows=[];modes=defaultdict(Counter);timings=defaultdict(lambda:([],[]))
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        pending={pool.submit(job,spec):spec for spec in jobs}
        for index,future in enumerate(as_completed(pending)):
            spec=pending[future];data,counts,timing,research=future.result();key=tuple(spec[:3]);rows.extend(data)
            modes[key].update(counts);timings[key][0].extend(timing);timings[key][1].extend(research)
            if index%12==0:print(f'{index+1}/{len(jobs)} blocks complete; {len(rows):,} hands',flush=True)
    rows.sort();raw=a.output/'hands.csv.gz'
    with gzip.open(raw,'wt',newline='') as out:
        writer=csv.writer(out);writer.writerow(('protocol','candidate','opponent','deal','seat','seed','hero_net_bb'));writer.writerows(rows)
    result=summarize(rows,modes,timings)
    result.update(total_hands=len(rows),chip_conservation_errors=0,illegal_actions=0,wall_seconds=round(time.perf_counter()-started,2),
        protocol={'field_pairs_per_opponent':a.pairs,'round_robin_pairs':a.round_robin_pairs,'six_max_deals':a.multiway_deals,
                  'heads_up_seat_repeats':2,'six_max_seat_repeats':6,'starting_stack_bb':100,'rake':0,
                  'confidence_unit':'One shuffled deal, averaged across all seat repetitions. Field opponents use distinct seed blocks.',
                  'inference':'Frozen blueprint plus shared 48-sample equity estimator; timing excludes capture, UI and agent initialization.',
                  'multiple_comparisons':'Holm adjustment for six aggregate paired differences against S55; other intervals exploratory.'},
        blueprint_sha256=hashlib.sha256(ASSET.read_bytes()).hexdigest(),raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    (a.output/'benchmark.json').write_text(json.dumps(result,indent=2)+'\n')
    for row in sorted(result['field_aggregate'],key=lambda r:r['bb100'],reverse=True):print(row,flush=True)
    print(f"Completed {len(rows):,} hands in {result['wall_seconds']} s",flush=True)

if __name__=='__main__':main()
