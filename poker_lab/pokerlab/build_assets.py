"""Build a seeded 169-class preflop equity table against 1..7 random opponents."""
import argparse,json,random
from .agent import CARD_TEXT,ECARDS,ASSET

def build(samples=3000):
    ranks='AKQJT98765432'; records={}
    for ai,a in enumerate(ranks):
        for bi,b in enumerate(ranks[ai:],ai):
            for suffix in ([''] if a==b else ['s','o']):
                key=a+b+suffix
                hole=(a+'s',b+('h' if suffix!='s' else 's'))
                known=set(hole); deck=[c for c in CARD_TEXT if c not in known]
                h=[ECARDS[c] for c in hole]
                rng=random.Random(1009+sum((i+1)*ord(c) for i,c in enumerate(key)))
                wins=[0.]*7
                for _ in range(samples):
                    cards=rng.sample(deck,19)
                    board=[ECARDS[c] for c in cards[:5]]
                    my=__import__('eval7').evaluate(h+board)
                    best=0;ties=0
                    for n in range(7):
                        rank=__import__('eval7').evaluate(board+[ECARDS[cards[5+2*n]],ECARDS[cards[6+2*n]]])
                        if rank>best:best=rank;ties=1
                        elif rank==best:ties+=1
                        if my>best:wins[n]+=1
                        elif my==best:wins[n]+=1/(ties+1)
                records[key]={'key':key,'equity':[w/samples for w in wins],
                              'combos':6 if a==b else 4 if suffix=='s' else 12}
    total=0
    for key in sorted(records,key=lambda k:records[k]['equity'][0],reverse=True):
        records[key]['top_fraction']=(total+records[key]['combos']/2)/1326
        total+=records[key]['combos']
    assert total==1326
    ASSET.write_text(json.dumps(records,indent=2)+'\n')
    print(f'Wrote {len(records)} classes, {samples} samples per class')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--samples',type=int,default=3000)
    build(p.parse_args().samples)
