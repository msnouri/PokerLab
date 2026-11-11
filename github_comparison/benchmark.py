"""S55 vs pinned Neuron Poker example POLICIES, not a pretrained DQN.

The upstream action functions are executed unmodified. PokerKit legal actions
and our shared equity estimator replace the upstream Gym environment and equity
pipeline. This is an adapted policy comparison, never a full-model ranking.
Run from the prior poker_lab directory with its dependencies installed.
"""
from pathlib import Path
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor,as_completed
from collections import Counter
import ast,csv,json,sys,hashlib,random,time,math,argparse,os
import numpy as np
from scipy.stats import t

HERE=Path(__file__).resolve().parent
LAB=Path(os.environ.get('POKER_LAB_PATH',str(HERE.parent/'poker_lab')))
sys.path.insert(0,str(LAB))
from pokerlab import engine
from pokerlab.agent import Agent as OriginalAgent,equity
from pokerlab.strategies import all_strategies
from pokerlab.experiment import icm,BLINDS,PAYOUTS

SOURCE=Path(os.environ.get('NEURON_SOURCE_PATH',str(HERE/'upstream/neuron_poker')))


def load_policy(path,Action):
    module=ast.parse(path.read_text())
    # Only remove the Gym enum import; class and method ASTs are unchanged.
    module.body=[node for node in module.body if not (isinstance(node,ast.ImportFrom) and node.module=='gym_env.enums')]
    namespace={'Action':Action}
    exec(compile(module,str(path),'exec'),namespace)
    return namespace['Player']


@dataclass(frozen=True)
class External:
    id:str
    call:float=0.
    bet:float=0.


def initialize():
    namespace={};exec(compile((SOURCE/'gym_env/enums.py').read_text(),'upstream_enums','exec'),namespace)
    Action=namespace['Action']
    EquityPlayer=load_policy(SOURCE/'agents/agent_consider_equity.py',Action)
    RandomPlayer=load_policy(SOURCE/'agents/agent_random.py',Action)
    class Dispatch:
        def __init__(self,s):
            self.spec=s
            self.policy=(RandomPlayer() if s.id=='neuron_random' else EquityPlayer(min_call_equity=s.call,min_bet_equity=s.bet)) if isinstance(s,External) else OriginalAgent(s)
        def decide(self,o,draw):
            if not isinstance(self.spec,External):return self.policy.decide(o,draw)
            moves=[Action.CHECK] if o.to_call==0 else [Action.FOLD,Action.CALL]
            targets={}
            if o.min_raise_to is not None:
                # Upstream env.py treats these as ADDITIONAL contributions,
                # rather than conventional pot-limit raise-to calculations.
                for action,factor in [(Action.RAISE_HALF_POT,.5),(Action.RAISE_POT,1.),(Action.RAISE_2POT,2.)]:
                    amount=o.bet+int(o.pot*factor)
                    if o.min_raise_to<=amount<=o.max_raise_to:
                        moves.append(action);targets[action]=amount
                moves.append(Action.ALL_IN);targets[Action.ALL_IN]=o.max_raise_to
            info={'player_data':{'equity_to_river_alive':equity(tuple(sorted(o.hole)),o.board,o.active-1)}}
            # Seed global random used by the upstream random policy. No hidden
            # information is passed; enum set iteration uses fixed hash seed.
            random.seed(int(draw*(2**53)))
            action=self.policy.action(moves,None,info)
            if action not in moves:raise AssertionError('Upstream policy chose an unavailable action')
            if action in targets:return 'raise',targets[action]
            if action==Action.FOLD:return 'fold',0
            return 'call',0
    engine.Agent=Dispatch


def specs():
    return [External('neuron_random')]+[External(f'neuron_equity_{i}_{i+1}',i/10,(i+1)/10) for i in range(1,7)]


def ci(vals):
    a=np.asarray(vals,dtype=float);m=float(a.mean());e=float(t.ppf(.975,len(a)-1)*a.std(ddof=1)/np.sqrt(len(a)))
    return m,m-e,m+e


def cash_job(payload):
    opponent,protocol,pairs=payload
    initialize();s=next(s for s in all_strategies() if s.id=='S55')
    rows=[];zero_sum=0
    for k in range(pairs):
        if protocol=='heads_up':
            seed=110261111+k*1009
            for seat in range(2):
                lineup=[s,opponent] if seat==0 else [opponent,s]
                r=engine.play_hand(lineup,[2000]*2,20,seed)
                rows.append(dict(opponent=opponent.id,protocol=protocol,unit=k,seat=seat,seed=seed,hero_bb=r['net'][seat]/20))
                zero_sum+=sum(r['net'])
        else:
            seed=120261111+k*1009;rotation=k%8
            lineup=[s]*4+[opponent]*4
            lineup=lineup[rotation:]+lineup[:rotation]
            r=engine.play_hand(lineup,[2000]*8,20,seed)
            net=sum(r['net'][j] for j,x in enumerate(lineup) if not isinstance(x,External))
            rows.append(dict(opponent=opponent.id,protocol=protocol,unit=k,seat=rotation,seed=seed,hero_bb=net/(20*4)))
            zero_sum+=sum(r['net'])
    assert zero_sum==0
    if protocol=='heads_up':
        vals=np.array([(rows[2*k]['hero_bb']+rows[2*k+1]['hero_bb'])/2 for k in range(pairs)])*100
    else:vals=np.array([r['hero_bb'] for r in rows])*100
    m,lo,hi=ci(vals)
    return dict(opponent=opponent.id,protocol=protocol,table_hands=len(rows),independent_deals=pairs,
                s55_bb100=m,ci95_low=lo,ci95_high=hi,chip_conservation_errors=0),rows


def tournament_one(opponent,seed):
    s=next(s for s in all_strategies() if s.id=='S55')
    lineup=[s]*4+[opponent]*4
    ids=list(range(8));rotation=seed%8;ids=ids[rotation:]+ids[:rotation]
    stacks={i:2000 for i in ids};stats={i:[3.,10.,2.,8.] for i in ids};points={i:0. for i in ids}
    played=0
    for h in range(200):
        if len(ids)==1:break
        played+=1;n=len(ids);before={i:stacks[i] for i in ids}
        r=engine.play_hand([lineup[i] for i in ids],[stacks[i] for i in ids],BLINDS[min(h//25,7)],seed*100003+h*1009,
                           stats=[stats[i] for i in ids],tournament=True)
        for i,st in zip(ids,r['after']):stacks[i]=st
        busted=sorted([i for i in ids if not stacks[i]],key=lambda i:before[i])
        rank=n;k=0
        while k<len(busted):
            j=k+1
            while j<len(busted) and before[busted[j]]==before[busted[k]]:j+=1
            prize=sum(PAYOUTS[r-1] for r in range(rank-(j-k)+1,rank+1))/(j-k)
            for i in busted[k:j]:points[i]=prize
            rank-=j-k;k=j
        ids=[i for i in ids if stacks[i]]
        ids=ids[1:]+ids[:1]
        assert sum(stacks.values())==16000
    if len(ids)==1:points[ids[0]]=PAYOUTS[0]
    else:
        for i,v in zip(ids,icm(tuple(stacks[i] for i in ids),PAYOUTS[:len(ids)])):points[i]=v
    assert abs(sum(points.values())-100)<1e-6
    ours=sum(points[i] for i in range(4))/4
    return dict(opponent=opponent.id,seed=seed,hands=played,s55_points_per_bot=ours,
                opponent_points_per_bot=(100-4*ours)/4,capped=int(len(ids)>1))


def tournament_job(payload):
    opponent,count=payload;initialize()
    rows=[tournament_one(opponent,130261111+k) for k in range(count)]
    mean,lo,hi=ci([r['s55_points_per_bot'] for r in rows])
    return dict(opponent=opponent.id,protocol='eight_player_tournament',tables=count,
                s55_points_per_bot=mean,ci95_low=lo,ci95_high=hi,parity_points=12.5,
                table_hands=sum(r['hands'] for r in rows)),rows


def write(name,rows):
    with (HERE/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--deals',type=int,default=5000);p.add_argument('--tables',type=int,default=128);p.add_argument('--workers',type=int,default=8)
    args=p.parse_args();start=time.time()
    summaries=[];raw=[];tours=[];tourrows=[]
    jobs=[(op,mode,args.deals) for op in specs() for mode in ['heads_up','eight_player_cash']]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for k,f in enumerate(as_completed([pool.submit(cash_job,j) for j in jobs]),1):
            summary,rows=f.result();summaries.append(summary);raw.extend(rows)
            print('cash',k,'/',len(jobs),summary,flush=True)
    write('cash_results.csv',sorted(summaries,key=lambda r:(r['protocol'],r['opponent'])))
    write('cash_hands.csv',sorted(raw,key=lambda r:(r['protocol'],r['opponent'],r['unit'],r['seat'])))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for k,f in enumerate(as_completed([pool.submit(tournament_job,(op,args.tables)) for op in specs()]),1):
            summary,rows=f.result();tours.append(summary);tourrows.extend(rows)
            print('tournament',k,'/',7,summary,flush=True)
    write('tournament_results.csv',sorted(tours,key=lambda r:r['opponent']))
    write('tournament_tables.csv',sorted(tourrows,key=lambda r:(r['opponent'],r['seed'])))
    manifest={'experiment':'Adapted upstream example policy comparison; NOT pretrained DQN or full Neuron stack',
              'args':vars(args),'equity_input':'Shared S55 estimator (48 postflop samples, preflop asset)',
              'cash_stacks':2000,'cash_bb':20,'tournament_blinds':BLINDS,'payouts':PAYOUTS,
              'upstream_tree_sha':'242741ca6bcbdbebccacef1caee2bbb7273355f7',
              'source_sha256':{str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.rglob('*.py')},
              's55_policy_sha256':hashlib.sha256((LAB/'pokerlab/agent.py').read_bytes()).hexdigest(),
              'elapsed_seconds':time.time()-start,'deadline_enforced':False}
    (HERE/'benchmark_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Finished',time.time()-start,flush=True)


if __name__=='__main__':main()
