"""Bot policy with a deliberately narrow, public-information-only interface.

Equity estimates sample uniformly random unknown hands. Public betting pressure
is handled by a heuristic penalty, NOT by a solved posterior range model.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from collections import Counter
import json
import random
import eval7
from .strategies import Strategy

CARD_TEXT = tuple(r+s for r in '23456789TJQKA' for s in 'cdhs')
ECARDS = {s:eval7.Card(s) for s in CARD_TEXT}
INDEX = {s:i for i,s in enumerate(CARD_TEXT)}
ASSET = Path(__file__).with_name('preflop.json')


def hand_key(hole):
    a,b=sorted(hole,key=lambda c:'23456789TJQKA'.index(c[0]),reverse=True)
    return a[0]+b[0]+('' if a[0]==b[0] else 's' if a[1]==b[1] else 'o')


@lru_cache(maxsize=1)
def preflop_table():
    return json.loads(ASSET.read_text())


@dataclass(frozen=True)
class Observation:
    hole: tuple[str,str]
    board: tuple[str,...]
    seat: int
    players: int
    active: int
    stack: int
    big_blind: int
    pot: int
    to_call: int
    bet: int
    min_raise_to: int | None
    max_raise_to: int | None
    position: float
    street_raises: int
    preflop_raiser: bool
    checked_before: bool
    opponent_looseness: float = .3
    opponent_aggression: float = .25
    tournament: bool = False
    remaining: int = 8
    heads_up_in_position: bool | None = None


def stable_seed(hole,board,opponents):
    value = 7919 + opponents
    for c in sorted(hole)+list(board):
        value=(value*67+INDEX[c]+1)&0xffffffffffffffff
    return value


@lru_cache(maxsize=180_000)
def equity(hole,board,opponents,samples=48):
    """Monte Carlo with no access to actual opponent cards or future board.

    Stable per-information-set seed; common equity noise across candidates.
    A weak two-sample 50% prior prevents exact 0/1 estimates from small samples.
    """
    opponents=max(1,min(7,opponents))
    if not board:
        return preflop_table()[hand_key(hole)]['equity'][opponents-1]
    known=set(hole+board)
    deck=[c for c in CARD_TEXT if c not in known]
    rng=random.Random(stable_seed(hole,board,opponents))
    base=[ECARDS[c] for c in hole+board]
    board_cards=[ECARDS[c] for c in board]
    missing=5-len(board)
    win=0.
    for _ in range(samples):
        picked=rng.sample(deck,missing+2*opponents)
        runout=[ECARDS[c] for c in picked[:missing]]
        my_rank=eval7.evaluate(base+runout)
        ranks=[eval7.evaluate(board_cards+runout+[ECARDS[picked[missing+2*j]],ECARDS[picked[missing+2*j+1]]])
               for j in range(opponents)]
        best=max(ranks)
        if my_rank>best: win+=1
        elif my_rank==best: win+=1/(1+ranks.count(my_rank))
    return (win+1)/(samples+2)


def draw_strength(hole,board):
    if len(board)>=5: return 0.
    cards=hole+board
    counts=Counter(c[1] for c in cards)
    flush=any(n==4 and any(c[1]==s for c in hole) for s,n in counts.items())
    ranks={2+'23456789TJQKA'.index(c[0]) for c in cards}
    if 14 in ranks: ranks.add(1)
    hole_ranks={2+'23456789TJQKA'.index(c[0]) for c in hole}
    straight=any(len(ranks.intersection(range(lo,lo+5)))==4 and hole_ranks.intersection(range(lo,lo+5))
                 for lo in range(1,11))
    return min(1.,(.65 if flush else 0.)+(.5 if straight else 0.))


def board_wetness(board):
    if not board: return 0.
    ranks=sorted(set('23456789TJQKA'.index(c[0]) for c in board))
    suits=Counter(c[1] for c in board)
    return min(1.,.35*(max(suits.values())>=2)+.35*(any(b-a<=2 for a,b in zip(ranks,ranks[1:])))
               +.3*(max(suits.values())>=3))


class Agent:
    def __init__(self,strategy:Strategy):
        self.strategy=strategy
        preflop_table() # Asset loading belongs to initialization, not decisions.
        self.last_details={'policy_path':'heuristic'}
        self.research_policy=None
        if strategy.research:
            from .research.policy import PaperPolicy
            self.research_policy=PaperPolicy(strategy.research)

    def decide(self,o:Observation,draw:float=.5):
        """Return ('fold'|'call'|'raise', raise_to). Zero cost call is check.

        `draw` is a uniform variate supplied by the runner, independent of the
        deal and hidden information. Raising amounts include prior street bets.
        """
        if self.research_policy is not None:
            action=self.research_policy.decide(o,draw)
            self.last_details=self.research_policy.details
            return action
        s=self.strategy
        can_raise=o.min_raise_to is not None and o.max_raise_to is not None
        def raise_to(amount):
            if not can_raise: return ('call',0)
            return ('raise',min(o.max_raise_to,max(o.min_raise_to,int(amount))))
        def passive(ok=True):
            return ('call',0) if o.to_call==0 or ok else ('fold',0)

        table=preflop_table()[hand_key(o.hole)]
        pot=max(o.big_blind,o.pot)
        # At most chips the hero can put in; pot already includes the bet faced.
        odds=o.to_call/(pot+o.to_call) if o.to_call else 0.
        eq=equity(tuple(sorted(o.hole)),o.board,o.active-1)
        pressure=min(.18,.035*o.street_raises+.06*o.to_call/max(pot,1))
        margin=s.call_margin+pressure
        value=s.value_equity
        bluff=s.bluff
        if s.adapt:
            # Smoothed public action frequencies only; no opponent identities.
            if o.opponent_looseness>.42:
                value-=.04; bluff*=.25
            if o.opponent_aggression>.4:
                margin-=.055
        if o.tournament and o.remaining<=4:
            margin+=s.risk # A risk margin, NOT a full ICM decision solver.

        if not o.board:
            fraction=min(.9,s.open_fraction+s.late_bonus*o.position)
            # Wider short-handed ranges; smoothly adjust as seats disappear.
            fraction=min(.95,fraction*(8/o.players)**.38)
            if s.premium_only:
                # An explicit adaptation of Hellmuth's beginner limit selection.
                playable=table['key'] in {'AA','KK','QQ','JJ','TT','99','88','77','AKs','AKo','AQs','AQo'}
            else:
                playable=table['top_fraction']<=fraction
            premium=table['top_fraction']<.035
            depth=(o.stack+o.bet)/o.big_blind
            if can_raise and s.push_bb and depth<=s.push_bb:
                if playable and (o.street_raises==0 or premium or eq>odds+margin+.12):
                    return raise_to(o.max_raise_to)
            if o.street_raises==0:
                if playable:
                    if premium and draw<s.trap: return passive()
                    return raise_to(o.big_blind*(2.2+.4*s.bet_pot))
                return passive(False)
            # Tighten against repeated raises and prohibit large loose calls.
            reraising = premium or (table['top_fraction']<fraction*.26 and eq>.58)
            if reraising and can_raise and o.street_raises<3 and not (premium and draw<s.trap):
                return raise_to(max(o.bet+o.to_call, o.big_blind)* (2.7 if o.position>.5 else 3.2))
            threshold=fraction/(1+.65*o.street_raises)
            ok=playable and (table['top_fraction']<threshold or o.to_call<=o.big_blind)
            if o.to_call>4*o.big_blind:
                # Future betting makes bare pot odds insufficient with deep stacks.
                ok=ok and eq*s.realization>odds+margin+.05
            if o.to_call>.35*(o.stack+o.bet):
                ok=ok and (premium or table['top_fraction']<.075) and eq>odds+margin+.08
            return passive(ok)

        wet=board_wetness(o.board)
        draw_quality=draw_strength(o.hole,o.board)
        # Future betting and stronger selected opponent ranges reduce realization.
        realized=eq*(1. if len(o.board)==5 else s.realization)-pressure
        spr=o.stack/pot
        value_threshold=value+.025*max(0,o.active-2)+.035*o.street_raises
        if s.polar: value_threshold+=.03*(len(o.board)<5)
        strong=eq>min(.95,value_threshold)
        nutty=eq>.89
        semibluff=draw_quality>.4 and draw<s.semi_bluff and eq>.20
        # Keep bluff frequency down in multiway pots and after repeated raises.
        bluff_chance=bluff/(max(1,o.active-1)**1.5)/(1+o.street_raises*3)
        # Polarized river bluffs prefer an ace blocker; no equilibrium claim.
        if s.polar and len(o.board)==5:
            bluff_chance*=1.4 if any(c[0]=='A' for c in o.hole) else .5
        pure_bluff=eq<.35 and draw<bluff_chance

        if o.to_call==0:
            if can_raise and o.street_raises==0:
                if nutty and wet<.5 and len(o.board)<5 and draw<s.trap:
                    return passive()
                # Defenders sometimes check strong/drawing hands for a later raise.
                if not o.preflop_raiser and o.position<.6 and draw<s.check_raise and (strong or draw_quality>.4):
                    return passive()
                protection=s.protect>draw and .42<eq<.72 and wet>.3 and o.active<=3
                cbet=(o.preflop_raiser and len(o.board)==3 and o.active<=3
                      and draw<s.cbet and (eq>.3 or wet<.4))
                control=s.pot_control>draw and .45<eq<.75 and not nutty
                if (strong and not control) or semibluff or pure_bluff or protection or cbet:
                    size=pot*s.bet_pot
                    if s.polar and len(o.board)==5: size*=1.25
                    if spr<1.4 and strong: size=o.stack
                    return raise_to(o.bet+max(o.big_blind,size))
            return passive()

        if can_raise and o.street_raises<3:
            checkraise=o.checked_before and draw<s.check_raise and (strong or semibluff)
            if (nutty or (strong and eq>.75+pressure) or checkraise
                or (semibluff and o.street_raises<1 and o.active<=3)):
                target=max(o.bet+o.to_call+pot*s.bet_pot, (o.bet+o.to_call)*2.6)
                if spr<1.4 and strong: target=o.max_raise_to
                return raise_to(target)
        return passive(realized>odds+margin)
