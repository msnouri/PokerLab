"""T03: minimum defence frequency, geometric value sizing, priced river bluffs.

Three textbook results applied as heuristics, not a solved strategy:
  * facing a bet b into pot p, continue with the top p/(p+b) of the range so a
    bluff with any two cards cannot profit (Chen & Ankenman 2006; Janda 2013);
  * size value bets as the same pot fraction on each remaining street so the
    last bet is all-in ("geometric growth of the pot", Chen & Ankenman ch. 14);
  * a river bet of b into p supports bluffs as b/(p+2b) of the betting range.
"Top of the range" needs a range. The policy assumes the hands that reach each
street are the top RANGE_WIDTH share of all hands by equity against random
hands, and measures the hero's percentile inside it. That is a modelling
assumption; against opponents who rarely bluff, defending at MDF over-calls.
"""
from . import Policy,register

RANGE_WIDTH={3:.55,4:.45,5:.38}
VALUE_PERCENTILE=.62


def percentile(eq,cards):
    width=RANGE_WIDTH[cards]
    return max(0.,min(1.,(eq-(1-width))/width))


def geometric_fraction(spr,streets):
    """Pot fraction per street that gets a stack of `spr` pots in by the river."""
    return ((1+2*spr)**(1/streets)-1)/2


@register('T03','MDF defence and geometric sizing',
          'Chen & Ankenman 2006, ch. 11-14; Janda 2013, Applications of No-Limit Hold\'em',
          'Postflop, at most three players; preflop and bigger fields S55')
class MdfGeometric(Policy):
    def decide(self,o,draw):
        from ..agent import equity,draw_strength
        if not o.board or o.active>3:return self.defer(o,draw,'preflop' if not o.board else 'multiway')
        eq=equity(tuple(sorted(o.hole)),o.board,o.active-1)
        q=percentile(eq,len(o.board));can_raise=o.min_raise_to is not None
        streets=6-len(o.board);pot=max(o.pot,o.big_blind)
        def bet(fraction):
            target=o.bet+o.to_call+fraction*(pot+o.to_call)
            return 'raise',min(o.max_raise_to,max(o.min_raise_to,int(target)))
        if o.to_call==0:
            if not can_raise:return 'call',0
            g=max(.33,min(1.25,geometric_fraction(o.stack/pot,streets)))
            bluff_share=g/(1+2*g) if len(o.board)==5 else min(.5,g/(1+2*g)*1.5)
            # Bluffs come from the bottom of the range; draws first before the river.
            draws=draw_strength(o.hole,o.board)>.4
            bluff_band=(1-VALUE_PERCENTILE)*bluff_share/(1-bluff_share)
            self.details={'policy_path':'mdf_bet','scope':f'Range percentile {q:.0%}; geometric size {g:.0%} pot',
                          'percentile':q,'geometric_fraction':g}
            if q>=VALUE_PERCENTILE or (draws and draw<.6) or (q<=bluff_band and o.active==2):
                return bet(g)
            return 'call',0
        before=max(1,o.pot-o.to_call)
        mdf=before/(before+o.to_call)
        # Share defence between the players still to act behind a bet.
        mdf=mdf**(1/max(1,o.active-1))
        odds=o.to_call/(o.pot+o.to_call)
        self.details={'policy_path':'mdf_defend','scope':f'Defend top {mdf:.0%}; range percentile {q:.0%}',
                      'percentile':q,'mdf':mdf}
        if can_raise and q>=.9 and o.street_raises<3:
            return bet(max(.5,min(1.,geometric_fraction(o.stack/pot,streets))))
        if q>=1-mdf and eq>odds:return 'call',0
        if draw_strength(o.hole,o.board)>.4 and eq>odds:return 'call',0
        return 'fold',0
