"""Frozen one-street CFR blueprints with learned betting-history responses.

Only public commitments and own-card equity enter inference. S55 is an explicit
fallback for preflop, multiway, tournaments, unknown position and unsupported
histories. This reduced game has no full-Holdem equilibrium guarantee.
"""
from functools import lru_cache
import json,math
from .train import ASSET

@lru_cache(maxsize=1)
def blueprints():
    if not ASSET.exists():raise RuntimeError('Research blueprints missing; run python -m pokerlab.research.train')
    data=json.loads(ASSET.read_text())
    if data.get('schema_version')!=2:raise RuntimeError('Research blueprint schema 2 is required')
    return data

class PaperPolicy:
    def __init__(self,algorithm):
        from ..agent import Agent
        from ..strategies import all_strategies
        self.algorithm=algorithm;self.data=blueprints();self.details={}
        if algorithm not in self.data['algorithms']:raise ValueError('Unknown paper algorithm')
        self.fallback=Agent(next(s for s in all_strategies() if s.id=='S55'))
        self.contexts=[]
        for key,value in self.data['blueprints'].items():
            name,spr,call=key.split(':')
            if name==algorithm:self.contexts.append((key,float(spr),value))

    def default(self,o,draw,reason):
        self.details={'policy_path':'fallback_'+reason,'fallback':'S55','algorithm':self.algorithm,
                      'scope':'Paper proxy inactive; S55 fallback: '+reason}
        return self.fallback.decide(o,draw)

    def decide(self,o,draw):
        from ..agent import equity
        reason='preflop' if not o.board else 'multiway' if o.active!=2 else 'tournament' if o.tournament else None
        position=o.heads_up_in_position if o.heads_up_in_position is not None else (o.position>.5 if o.players==2 else None)
        if reason is None and position is None:reason='unknown_position'
        if reason:return self.default(o,draw,reason)
        if o.to_call==0 and o.min_raise_to is None:
            self.details={'policy_path':'research_forced_check','algorithm':self.algorithm,'scope':'Only a check is available'}
            return 'call',0
        # Reconstruct the pot before this street's surviving-player commitments.
        dead=o.pot-2*o.bet-o.to_call if o.to_call else o.pot
        if dead<=0:return self.default(o,draw,'unrepresented_pot')
        cap=o.stack+o.bet
        if o.min_raise_to is None and o.to_call:cap=min(cap,o.bet+o.to_call)
        spr=cap/dead
        if spr<.25 or spr>32:return self.default(o,draw,'off_grid_depth')
        key,model_spr,context=min(self.contexts,key=lambda r:abs(math.log(spr/r[1])))
        nodes=context['nodes'];node=nodes['r'];hero=1 if position else 0
        def child_for(action,amount=0.):
            choices=[]
            for i,(a,increment) in enumerate(node['actions']):
                if a==action:
                    total=node['commitments'][node['player']]+increment
                    distance=abs(math.log(max(total,1e-9)/max(amount,1e-9))) if action=='raise' else 0.
                    choices.append((distance,i))
            if not choices:raise ValueError('Unrepresented action history')
            child=node['children'][min(choices)[1]]
            if child is None:raise ValueError('Observed decision follows a terminal history')
            return nodes[child]
        try:
            if not o.to_call:
                if position:node=child_for('call')
            elif o.bet==0:
                if not position:node=child_for('call')
                node=child_for('raise',o.to_call/dead)
            else:
                if position:node=child_for('call')
                node=child_for('raise',o.bet/dead)
                node=child_for('raise',(o.bet+o.to_call)/dead)
            if node['player']!=hero:raise ValueError('Inconsistent public position')
        except ValueError:return self.default(o,draw,'unsupported_history')
        eq=equity(tuple(sorted(o.hole)),o.board,1)
        bucket=min(self.data['buckets']-1,int(eq*self.data['buckets']))
        distribution={};commit=node['commitments'];top=max(commit)
        for (action,increment),probability in zip(node['actions'],node['probabilities'][bucket]):
            move=(action,0)
            if action=='raise':
                if o.min_raise_to is None:move=('call',0)
                else:
                    target=commit[hero]+increment
                    fraction=(target-top)/(1+2*top)
                    amount=o.max_raise_to if abs(target-model_spr)<1e-8 else int(round(o.bet+o.to_call+fraction*(o.pot+o.to_call)))
                    move=('raise',min(o.max_raise_to,max(o.min_raise_to,amount)))
            if action=='fold' and not o.to_call:move=('call',0)
            distribution[move]=distribution.get(move,0.)+probability
        total=sum(distribution.values());threshold=min(max(draw,0.),1.-1e-15)*total;running=0.
        result=list(distribution)[-1]
        for move,probability in distribution.items():
            running+=probability
            if threshold<running:result=move;break
        self.details={'policy_path':'research_blueprint','algorithm':self.algorithm,'context':key,'public_node':node['name'] if 'name' in node else next(n for n,v in nodes.items() if v is node),'bucket':bucket,
                      'scope':'Heads-up postflop abstraction; learned betting-history responses; no full-game guarantee',
                      'distribution':[{'action':a,'raise_to':n,'probability':p/total} for (a,n),p in distribution.items()]}
        return result
