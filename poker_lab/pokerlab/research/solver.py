"""Tabular CFR family on a perfect-recall, two-player private-bucket game.

Regret/average/prediction equations follow the original papers and the authors'
MIT reference implementation (rpSebastian/PDCFRPlus); traversal here is an
independent vectorized implementation. See research/THIRD_PARTY_NOTICES.md.
An information set contains public history and ONLY the acting player's bucket.
"""
from dataclasses import dataclass,field
import numpy as np

ALGORITHMS=('cfr','mccfr','cfr_plus','dcfr','pcfr_plus','pdcfr_plus')


@dataclass
class Node:
    player:int=-1
    actions:list=field(default_factory=list)
    children:list=field(default_factory=list)
    payoff:object=None
    name:str=''
    commitments:tuple=()


class BucketGame:
    """One street, configurable pot-fraction bets, one re-raise, equal caps.

    pot is the pot already visible; facing is the outstanding call cost, which
    is already included in pot. Payoffs are net of future contributions, minus
    a constant half of the dead pot, so this model is exactly zero-sum.
    Independent uniform private strengths are an assumption, not Hold'em ranges.
    """
    def __init__(self,buckets=12,pot=1.,stack=4.,facing=0.,bet_fractions=(.5,1.),max_bets=2,kuhn=False):
        self.buckets=buckets;self.pot=pot;self.stack=stack;self.facing=facing;self.nodes=[]
        self.chance=np.full((buckets,buckets),1/buckets**2)
        if kuhn:
            self.chance=(np.ones((3,3))-np.eye(3))/6
        strength=np.sign(np.arange(buckets)[:,None]-np.arange(buckets)[None,:])
        dead=pot-facing
        if dead<0 or facing>stack or stack<=0:raise ValueError('Inconsistent pot, call, or cap')
        def terminal(c,fold=None):
            if fold==0:u=np.full((buckets,buckets),-dead/2-c[0])
            elif fold==1:u=np.full((buckets,buckets),dead/2+c[1])
            else:u=strength*(dead+sum(c))/2+(c[1]-c[0])/2
            return Node(payoff=u)
        def build(p,c,checks,bets,last_raise,name):
            node=Node(player=p,name=name,commitments=tuple(c));self.nodes.append(node)
            other=1-p;cost=max(c)-c[p]
            if cost>1e-9:
                node.actions=[('fold',0.),('call',cost)]
                node.children=[terminal(c,p),terminal([max(c),max(c)])]
            else:
                node.actions=[('call',0.)]
                node.children=[terminal(c) if checks else build(other,list(c),1,bets,last_raise,name+'k')]
            if bets<max_bets:
                targets=[]
                for fraction in bet_fractions:
                    target=min(stack,max(max(c)+max(last_raise,.05),max(c)+fraction*(dead+2*max(c))))
                    if target<=max(c)+1e-9 or any(abs(target-x)<1e-8 for x in targets):continue
                    targets.append(target);next_c=list(c);next_c[p]=target
                    node.actions.append(('raise',target-c[p]))
                    node.children.append(build(other,next_c,0,bets+1,target-max(c),name+f'b{len(targets)}'))
            return node
        self.root=build(0,[0.,facing],0,int(facing>0),facing,'r')

    @classmethod
    def kuhn(cls):return cls(3,2.,1.,0.,(.5,),1,True)


def normalize(positive):
    total=positive.sum(axis=-1,keepdims=True)
    return np.divide(positive,total,out=np.full_like(positive,1/positive.shape[-1]),where=total>1e-15)


class Solver:
    def __init__(self,game,algorithm='cfr_plus',seed=0):
        if algorithm not in ALGORITHMS:raise ValueError(algorithm)
        self.game=game;self.algorithm=algorithm;self.iteration=0;self.rng=np.random.default_rng(seed)
        b=game.buckets
        self.regret={id(n):np.zeros((b,len(n.actions))) for n in game.nodes}
        self.average={k:np.zeros_like(v) for k,v in self.regret.items()}
        self.policy={k:normalize(np.maximum(v,0)) for k,v in self.regret.items()}
        self.by_id={id(n):n for n in game.nodes}

    def update(self,k,delta,reach):
        t=self.iteration;a=self.algorithm;r=self.regret[k]
        gamma={'cfr':0,'cfr_plus':1,'dcfr':2,'pcfr_plus':2,'pdcfr_plus':5}[a]
        self.average[k]*=((t-1)/t)**gamma
        self.average[k]+=reach[:,None]*self.policy[k]
        if a=='dcfr':
            x=(t-1)**1.5;factor=np.where(r>0,x/(x+1),.5)
            r[:]=r*factor+delta
        elif a=='pdcfr_plus':
            x=(t-1)**2.3;r[:]=np.maximum(r*x/(x+1)+delta,0)
        elif a in ('cfr_plus','pcfr_plus'):r[:]=np.maximum(r+delta,0)
        else:r+=delta
        predicted=np.maximum(r,0)
        if a=='pcfr_plus':predicted=np.maximum(r+delta,0)
        elif a=='pdcfr_plus':
            x=t**2.3;predicted=np.maximum(r*x/(x+1)+delta,0)
        self.policy[k]=normalize(predicted)

    def step(self):
        self.iteration+=1
        if self.algorithm=='mccfr':
            for player in (0,1):
                pair=self.rng.choice(self.game.buckets**2,p=self.game.chance.ravel())
                cards=(pair//self.game.buckets,pair%self.game.buckets)
                self._sample(self.game.root,player,cards)
            return
        b=self.game.buckets
        for player in (0,1):
            updates={}
            def walk(n,r0,r1):
                if n.payoff is not None:return n.payoff
                k=id(n);s=self.policy[k];p=n.player
                values=[]
                for j,child in enumerate(n.children):
                    values.append(walk(child,r0*s[:,j] if p==0 else r0,r1*s[:,j] if p==1 else r1))
                values=np.asarray(values)
                out=np.sum(values*(s.T[:,:,None] if p==0 else s.T[:,None,:]),axis=0)
                if p==player:
                    if p==0:cf=np.sum(values*(self.game.chance*r1[None,:])[None,:,:],axis=2).T
                    else:cf=-np.sum(values*(self.game.chance*r0[:,None])[None,:,:],axis=1).T
                    updates[k]=(cf-np.sum(cf*s,axis=1,keepdims=True),r0 if p==0 else r1)
                return out
            walk(self.game.root,np.ones(b),np.ones(b))
            for k,(delta,reach) in updates.items():self.update(k,delta,reach)

    def _sample(self,n,traverser,cards):
        if n.payoff is not None:return float(n.payoff[cards])* (1 if traverser==0 else -1)
        k=id(n);bucket=cards[n.player];s=self.policy[k][bucket]
        if n.player!=traverser:
            # External sampling: opponent reach is induced by visitation.
            self.average[k][bucket]+=s
            action=self.rng.choice(len(s),p=s)
            return self._sample(n.children[action],traverser,cards)
        values=np.array([self._sample(child,traverser,cards) for child in n.children])
        value=float(s@values);self.regret[k][bucket]+=values-value
        self.policy[k][bucket]=normalize(np.maximum(self.regret[k][bucket],0)[None,:])[0]
        return value

    def train(self,iterations):
        for _ in range(iterations):self.step()
        return self

    def averaged(self):return {k:normalize(v) for k,v in self.average.items()}

    def evaluate(self,policies=None):
        policies=self.averaged() if policies is None else policies
        def walk(n):
            if n.payoff is not None:return n.payoff
            s=policies[id(n)].T;v=np.array([walk(c) for c in n.children])
            return np.sum(v*(s[:,:,None] if n.player==0 else s[:,None,:]),axis=0)
        value=float(np.sum(self.game.chance*walk(self.game.root)))
        def br(n,player,opp_reach):
            if n.payoff is not None:return n.payoff
            s=policies[id(n)];p=n.player
            v=np.array([br(c,player,opp_reach*s[:,j] if p!=player else opp_reach) for j,c in enumerate(n.children)])
            if p!=player:return np.sum(v*(s.T[:,:,None] if p==0 else s.T[:,None,:]),axis=0)
            if p==0:
                cf=np.sum(v*(self.game.chance*opp_reach[None,:])[None,:,:],axis=2)
                choice=cf.argmax(axis=0);return v[choice,np.arange(self.game.buckets),:]
            cf=-np.sum(v*(self.game.chance*opp_reach[:,None])[None,:,:],axis=1)
            choice=cf.argmax(axis=0);return v[choice,:,np.arange(self.game.buckets)].T
        b0=float(np.sum(self.game.chance*br(self.game.root,0,np.ones(self.game.buckets))))
        b1=-float(np.sum(self.game.chance*br(self.game.root,1,np.ones(self.game.buckets))))
        return {'value_p0':value,'best_response_p0':b0,'best_response_p1':b1,'nash_conv':max(0.,b0+b1),'exploitability':max(0.,(b0+b1)/2)}
