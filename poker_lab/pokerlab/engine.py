"""PokerKit owns dealing legality, all-ins, side pots, ties and settlement.

Each hand gets an independent local shuffled deck. Policies receive only
Observation objects; engine state and deal RNG are never passed to them.
"""
from collections import deque,Counter
from dataclasses import asdict
from time import perf_counter_ns
import random
from pokerkit import Automation,Card,NoLimitTexasHoldem
from .agent import Agent,Observation,CARD_TEXT

AUTOMATIONS=tuple(a for a in Automation if a!=Automation.HOLE_DEALING)
PK_CARDS={text:next(Card.parse(text)) for text in CARD_TEXT}


def play_hand(strategies,stacks,bb,seed,stats=None,tournament=False,trace=False):
    """Seats 0/1 are SB/BB for 3+; in heads-up seat 1 is button/SB.

    PokerKit reverses heads-up raw blinds per its documented convention.
    The caller rotates the physical seat ordering between hands.
    """
    n=len(strategies)
    before=list(stacks)
    state=NoLimitTexasHoldem.create_state(AUTOMATIONS,True,0,(bb//2,bb),bb,before,n)
    order=list(CARD_TEXT);random.Random(seed).shuffle(order)
    state.deck_cards=deque(PK_CARDS[c] for c in order)
    for i in range(n): state.deal_hole(2,i)
    agents=[Agent(s) for s in strategies]
    decision_rng=[random.Random(seed*104729+i*15485863+271) for i in range(n)]
    stats=stats if stats is not None else [[3.,10.,2.,8.] for _ in range(n)]
    raiser=None;street=-1;raises=0;checked=set();voluntary=set()
    counts=[Counter() for _ in range(n)];times=[];log=[];observations=[]
    seat_times=[[] for _ in range(n)];seat_modes=[[] for _ in range(n)]
    decisions=0
    board=()
    holes=[tuple(repr(c) for c in state.hole_cards[i]) for i in range(n)]
    while state.status:
        i=state.actor_index
        if i is None: raise RuntimeError('Unresolved non-player action in automated engine')
        if street!=state.street_index:
            street=state.street_index;raises=0;checked=set()
            board=tuple(repr(c) for cards in state.board_cards for c in cards)
        others=[j for j in range(n) if j!=i and state.statuses[j]]
        can_raise=state.can_complete_bet_or_raise_to()
        minraise=state.min_completion_betting_or_raising_to_amount if can_raise else None
        maxraise=state.max_completion_betting_or_raising_to_amount if can_raise else None
        # 0=earliest; 1=button, using postflop order. HU button is index 1.
        pos=(i/(n-1)) if n>2 else float(i==1)
        o=Observation(holes[i],board,i,n,sum(state.statuses),state.stacks[i],bb,
                      state.total_pot_amount,state.checking_or_calling_amount,state.bets[i],
                      minraise,maxraise,pos,raises,raiser==i,i in checked,
                      sum(stats[j][0]/stats[j][1] for j in others)/max(1,len(others)),
                      sum(stats[j][2]/stats[j][3] for j in others)/max(1,len(others)),
                      tournament,n,heads_up_in_position=(i>others[0] if len(others)==1 else None))
        t=perf_counter_ns()
        action,amount=agents[i].decide(o,decision_rng[i].random())
        details=getattr(agents[i],'last_details',{})
        if details.get('policy_path'):counts[i]['mode_'+details['policy_path']]+=1
        elapsed=perf_counter_ns()-t
        seat_times[i].append(elapsed);seat_modes[i].append(details.get('policy_path','external'))
        times.append(elapsed);decisions+=1
        if trace: observations.append(asdict(o))
        if action=='raise':
            if not state.can_complete_bet_or_raise_to(amount):
                raise AssertionError(f'Illegal raise: {amount}, legal [{minraise},{maxraise}]')
            state.complete_bet_or_raise_to(amount)
            counts[i]['raise']+=1;stats[i][2]+=1;stats[i][3]+=1
            raises+=1
            if street==0:raiser=i
        elif action=='fold':
            if not state.can_fold(): raise AssertionError('Illegal fold')
            state.fold();counts[i]['fold']+=1;stats[i][3]+=1
        elif action=='call':
            state.check_or_call()
            counts[i]['call' if o.to_call else 'check']+=1
            stats[i][3]+=1
            if o.to_call==0:checked.add(i)
        else:raise AssertionError(f'Unknown action {action}')
        if street==0 and action!='fold' and (o.to_call or action=='raise'):voluntary.add(i)
        if trace: log.append(dict(seat=i,street=street,action=action,amount=amount,pot_before=o.pot))
        if decisions>500:raise RuntimeError('Hand action limit exceeded')
    for i in range(n):
        stats[i][1]+=1
        if i in voluntary:stats[i][0]+=1
    after=list(state.stacks)
    assert sum(after)==sum(before), (before,after)
    assert all(x>=0 for x in after)
    return {'after':after,'net':[a-b for a,b in zip(after,before)],'counts':counts,
            'times_ns':times,'actions':log,'observations':observations,
            'board':list(board),'holes':holes if trace else [],'decisions':decisions,
            'seat_times_ns':seat_times,'seat_modes':seat_modes}
