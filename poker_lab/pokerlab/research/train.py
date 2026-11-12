"""Freeze deterministic abstract blueprints; no benchmark hands enter training."""
import argparse,json,time,hashlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from .solver import BucketGame,Solver,ALGORITHMS

ASSET=Path(__file__).with_name('blueprints.json')
SPRS=(.5,1.,2.,4.,8.,16.)
CALLS=(0.,)


def task(args):
    algorithm,spr,call,iterations,buckets=args
    start=time.perf_counter();game=BucketGame(buckets,stack=spr,bet_fractions=(.25,.5,1.,2.,4.))
    solver=Solver(game,algorithm,seed=17011).train(iterations)
    avg=solver.averaged();root=game.root
    ip=root.children[0] if not call else None
    def entry(n):return {'actions':n.actions,'commitments':n.commitments,'player':n.player,
        'children':[c.name if c.payoff is None else None for c in n.children],
        'probabilities':avg[id(n)].round(10).tolist()}
    return f'{algorithm}:{spr:g}:{call:g}',{'nodes':{n.name:entry(n) for n in game.nodes},
        'iterations':iterations,'training_seconds':round(time.perf_counter()-start,4),'abstract_metrics':solver.evaluate(avg)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--iterations',type=int,default=2000);p.add_argument('--mc-iterations',type=int,default=20000)
    p.add_argument('--buckets',type=int,default=12);p.add_argument('--workers',type=int,default=6);p.add_argument('--output',type=Path,default=ASSET)
    a=p.parse_args();start=time.perf_counter()
    jobs=[(algo,spr,call,a.mc_iterations if algo=='mccfr' else a.iterations,a.buckets)
          for algo in ALGORITHMS for spr in SPRS for call in CALLS if call<=spr]
    rows={}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for i,(key,result) in enumerate(pool.map(task,jobs)):
            rows[key]=result
            if i%12==0:print(f'{i+1}/{len(jobs)} blueprints frozen',flush=True)
    data={'schema_version':2,'buckets':a.buckets,'sprs':SPRS,'calls':CALLS,'algorithms':ALGORITHMS,
          'seed':17011,'iterations':a.iterations,'mc_iterations':a.mc_iterations,'training_seconds':round(time.perf_counter()-start,2),
          'scope':'One-street two-player private-strength abstraction. Quarter/half/full/double/quadruple-pot actions, one re-raise, equal effective caps. Betting responses use learned public-history nodes. Initial independent uniform buckets; no full Holdem range or future-street model.',
          'blueprints':rows}
    a.output.write_text(json.dumps(data,separators=(',',':'))+'\n')
    print(f'Saved {len(rows)} blueprints; SHA256 {hashlib.sha256(a.output.read_bytes()).hexdigest()}',flush=True)

if __name__=='__main__':main()
