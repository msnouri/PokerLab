"""Solve the heads-up jam-or-fold game and freeze the result as an asset.

Game (Chen & Ankenman, The Mathematics of Poker, 2006, ch. 12-13): the small
blind posts 0.5 bb, the big blind 1 bb, effective stacks are S bb. The small
blind jams or folds; the big blind calls or folds. Equities are Monte Carlo
estimates between the 169 starting-hand classes, so borderline hands carry
sampling noise; see `samples` and `exploitability_bb` in the written asset.

    python -m pokerlab.library.build_pushfold --samples 1500 --workers 4
"""
import argparse
import json
import random
from multiprocessing import Pool
from pathlib import Path

import eval7
import numpy as np

RANKS='AKQJT98765432'
SUITS='cdhs'
ASSET=Path(__file__).with_name('pushfold.json')
DEPTHS=list(range(2,21))


def classes():
    out=[]
    for i,a in enumerate(RANKS):
        for j,b in enumerate(RANKS):
            if i==j:out.append(a+b)
            elif i<j:out.append(a+b+'s')
            else:out.append(b+a+'o')
    return out


def combos(key):
    a,b=key[0],key[1]
    if a==b:return [(a+s,b+t) for i,s in enumerate(SUITS) for t in SUITS[i+1:]]
    if key[2]=='s':return [(a+s,b+s) for s in SUITS]
    return [(a+s,b+t) for s in SUITS for t in SUITS if s!=t]


CLASSES=classes()
COMBOS={k:combos(k) for k in CLASSES}
DECK=[r+s for r in RANKS for s in SUITS]
CARD={c:eval7.Card(c) for c in DECK}


def row(args):
    """Equity of class i against every class j>=i, plus valid combo-pair counts."""
    i,samples,seed=args
    rng=random.Random(seed*1009+i)
    result=[]
    for j in range(i,len(CLASSES)):
        pairs=[(x,y) for x in COMBOS[CLASSES[i]] for y in COMBOS[CLASSES[j]] if not set(x)&set(y)]
        if not pairs:
            result.append((j,.5,0));continue
        win=0.
        for _ in range(samples):
            x,y=pairs[rng.randrange(len(pairs))]
            dead=set(x)|set(y)
            board=[]
            while len(board)<5:
                c=DECK[rng.randrange(52)]
                if c not in dead:dead.add(c);board.append(CARD[c])
            a=eval7.evaluate([CARD[x[0]],CARD[x[1]]]+board)
            b=eval7.evaluate([CARD[y[0]],CARD[y[1]]]+board)
            win+=1. if a>b else .5 if a==b else 0.
        result.append((j,win/samples,len(pairs)))
    return i,result


def matrices(samples,workers,seed=20261112):
    n=len(CLASSES)
    E=[[.5]*n for _ in range(n)];W=[[0]*n for _ in range(n)]
    with Pool(workers) as pool:
        for i,result in pool.imap_unordered(row,[(i,samples,seed) for i in range(n)]):
            for j,eq,weight in result:
                E[i][j]=eq;E[j][i]=1-eq;W[i][j]=W[j][i]=weight
    return np.array(E),np.array(W,dtype=float)


def best_responses(E,W,S,push,call):
    """EV in bb measured from before the blinds are posted; returns pure best responses."""
    P=W/W.sum(axis=1,keepdims=True)
    push_ev=(P*(call[None,:]*(E*2*S-S)+(1-call[None,:]))).sum(axis=1)
    reach=W*push[:,None]
    mass=reach.sum(axis=0)
    call_ev=(reach*((1-E)*2*S-S)).sum(axis=0)/np.maximum(mass,1e-12)
    return (push_ev>-.5).astype(float),(call_ev>-1.).astype(float),push_ev,call_ev,mass


def solve(E,W,S,iterations=4000):
    n=len(CLASSES)
    push=np.ones(n);call=np.full(n,.5)
    for t in range(1,iterations+1):
        bp,bc,_,_,_=best_responses(E,W,S,push,call)
        step=1/(t+1)
        push=(1-step)*push+step*bp;call=(1-step)*call+step*bc
    # Exploitability: what each side gains by switching to a best response.
    bp,bc,pev,cev,mass=best_responses(E,W,S,push,call)
    weight=np.array([len(COMBOS[k]) for k in CLASSES])
    gain_sb=(weight*(np.maximum(pev,-.5)-(push*pev+(1-push)*-.5))).sum()/1326
    gain_bb=(mass*(np.maximum(cev,-1.)-(call*cev+(1-call)*-1.))).sum()/mass.sum()
    return push.tolist(),call.tolist(),float(gain_sb+gain_bb)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples',type=int,default=1500)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--iterations',type=int,default=4000)
    args=parser.parse_args()
    E,W=matrices(args.samples,args.workers)
    total=1326
    out={'schema_version':1,'game':'HU jam-or-fold, SB 0.5 / BB 1, no ante, effective stack in bb',
         'method':'fictitious play on a 169x169 Monte Carlo class-equity matrix','samples':args.samples,
         'iterations':args.iterations,'classes':CLASSES,'depths':{}}
    for S in DEPTHS:
        push,call,gap=solve(E,W,S,args.iterations)
        weight=[len(COMBOS[k]) for k in CLASSES]
        out['depths'][str(S)]={'push':[round(x,3) for x in push],'call':[round(x,3) for x in call],
            'push_fraction':round(sum(w*p for w,p in zip(weight,push))/total,4),
            'call_fraction':round(sum(w*p for w,p in zip(weight,call))/total,4),
            'exploitability_bb':round(gap,5)}
        print(S,out['depths'][str(S)]['push_fraction'],out['depths'][str(S)]['call_fraction'],round(gap,5),flush=True)
    ASSET.write_text(json.dumps(out,separators=(',',':'))+'\n')


if __name__=='__main__':main()
