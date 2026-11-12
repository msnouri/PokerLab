"""T02: raise-first-in frequencies by seat, taken from published solver output.

Only the *frequencies* come from the references. Which hands fill each range
is this repository's own playability ordering (multiway equity plus small
suited and connected bonuses), so a seat's range matches a solver chart in
width, not hand for hand. Limped and raised pots go to the fallback.
"""
from functools import lru_cache
from . import Policy,register
from .positions import seats_off_button

# 6-max, 100 bb, no ante. UTG/MP/CO/BTN 17.2/22.9/28.1/43.3 % are solver open
# frequencies as published (see docs/STRATEGY_REFERENCES.md).
# Earlier full-ring seats and the small blind are tighter/looser assumptions.
RFI={0:.433,1:.281,2:.229,3:.172,4:.14,5:.12,6:.11}
SB_RFI=.40
HU_BUTTON_RFI=.80
RANKS='23456789TJQKA'


@lru_cache(maxsize=1)
def ordering():
    """169 classes, best first, with the cumulative combo fraction of each."""
    from ..agent import preflop_table
    rows=[]
    for key,row in preflop_table().items():
        gap=abs(RANKS.index(key[0])-RANKS.index(key[1]))
        suited=key.endswith('s');pair=len(key)==2
        score=row['equity'][2]+(.025 if suited else .03 if pair else 0.)+(.012 if not pair and gap==1 else .006 if not pair and gap==2 else 0.)
        rows.append((score,key,row['combos']))
    rows.sort(reverse=True)
    out={};seen=0
    for _,key,combos in rows:
        seen+=combos;out[key]=seen/1326
    return out


def open_frequency(seat,players):
    off=seats_off_button(seat,players)
    if players==2:return HU_BUTTON_RFI if off==0 else None
    if seat==0:return SB_RFI
    return None if off is None else RFI[min(off,6)]


@register('T02','Solver-frequency opening by position',
          'Published 6-max 100 bb solver RFI frequencies; hand ordering is this repository\'s',
          'Unopened preflop pots; every other spot S55')
class PositionalOpen(Policy):
    def decide(self,o,draw):
        from ..agent import hand_key
        bb=o.big_blind
        unopened=not o.board and o.street_raises==0 and o.pot<=bb+bb//2 and o.to_call>0
        target=open_frequency(o.seat,o.players) if unopened else None
        if target is None or o.min_raise_to is None:return self.defer(o,draw,'not_first_in')
        rank=ordering()[hand_key(o.hole)]
        size=3. if o.seat==0 and o.players>2 else 2.5
        self.details={'policy_path':'rfi_chart','scope':f'First in: open the top {target:.0%} from this seat',
                      'range_fraction':target,'hand_rank':rank}
        if rank<=target:
            return 'raise',min(o.max_raise_to,max(o.min_raise_to,int(size*bb)))
        return 'fold',0
