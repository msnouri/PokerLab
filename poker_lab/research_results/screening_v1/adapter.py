"""Map public Hold'em observations to frozen, reduced-game mixed strategies.

This is not DeepStack/Libratus/Pluribus, and it has no full-Hold'em equilibrium
guarantee. All preflop, multiway and tournament decisions use the named S55
fallback. No solve or training occurs during a decision.
"""
from functools import lru_cache
import hashlib,json,math
from .train import ASSET


@lru_cache(maxsize=1)
def blueprints():
    if not ASSET.exists():raise RuntimeError('Research blueprints missing; run python -m pokerlab.research.train')
    data=json.loads(ASSET.read_text())
    if data.get('schema_version')!=1:raise RuntimeError('Unsupported research blueprint version')
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
            if name==algorithm:self.contexts.append((key,float(spr),float(call),value))

    def decide(self,o,draw):
        from ..agent import equity
        reason='preflop' if not o.board else 'multiway' if o.active!=2 else 'tournament' if o.tournament else None
        position=o.heads_up_in_position if o.heads_up_in_position is not None else (o.position>.5 if o.players==2 else None)
        if reason is None and position is None:reason='unknown_position'
        if reason:
            self.details={'policy_path':'fallback_'+reason,'fallback':'S55','algorithm':self.algorithm,
                          'scope':'Paper proxy inactive; S55 fallback: '+reason}
            return self.fallback.decide(o,draw)
        eq=equity(tuple(sorted(o.hole)),o.board,1);pot=max(o.pot,o.big_blind)
        if o.min_raise_to is None or o.max_raise_to is None:
            self.details={'policy_path':'research_closed_action','algorithm':self.algorithm,
                          'scope':'No raising available; uniform-range showdown pot odds'}
            return ('call',0) if not o.to_call or eq>o.to_call/(pot+o.to_call) else ('fold',0)
        ratio=o.to_call/pot;spr=o.stack/pot
        candidates=[r for r in self.contexts if bool(r[2])==bool(o.to_call)]
        key,_,_,context=min(candidates,key=lambda r:abs(math.log(max(spr,.01)/r[1]))+3*abs(r[2]-ratio))
        entry=context['ip'] if not o.to_call and position else context['oop']
        bucket=min(self.data['buckets']-1,int(eq*self.data['buckets']))
        distribution={}
        for (action,increment),probability in zip(entry['actions'],entry['probabilities'][bucket]):
            move=(action,0)
            if action=='raise':move=('raise',min(o.max_raise_to,max(o.min_raise_to,int(round(o.bet+increment*pot)))))
            if action=='fold' and not o.to_call:move=('call',0)
            distribution[move]=distribution.get(move,0.)+probability
        total=sum(distribution.values());threshold=min(max(draw,0.),1.-1e-15)*total;running=0.
        result=list(distribution)[-1]
        for move,probability in distribution.items():
            running+=probability
            if threshold<running:result=move;break
        self.details={'policy_path':'research_blueprint','algorithm':self.algorithm,'context':key,'bucket':bucket,
                      'scope':'Heads-up postflop private-equity-bucket abstraction; no full-game guarantee',
                      'distribution':[{'action':a,'raise_to':n,'probability':p/total} for (a,n),p in distribution.items()]}
        return result
