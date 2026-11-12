"""T01: heads-up Nash jam-or-fold for short stacks.

The ranges are solved in this repository (build_pushfold.py), not copied from
a chart. Scope: preflop, blind against blind, effective stack at most 20 bb.
The observation carries only the hero's stack, so the hero's own depth stands
in for the effective stack when jamming; when calling, the bet faced bounds it.
"""
from functools import lru_cache
import json
from pathlib import Path
from . import Policy,register

ASSET=Path(__file__).with_name('pushfold.json')
MAX_BB=20


@lru_cache(maxsize=1)
def table():
    data=json.loads(ASSET.read_text())
    if data.get('schema_version')!=1:raise RuntimeError('Push/fold asset schema 1 is required')
    index={k:i for i,k in enumerate(data['classes'])}
    return data,index


def frequency(kind,hand,depth_bb):
    """Jam or call frequency for a 169-class key, interpolated between solved depths."""
    data,index=table()
    depth=min(MAX_BB,max(2.,depth_bb))
    lo=int(depth);hi=min(MAX_BB,lo+1);w=depth-lo
    a=data['depths'][str(lo)][kind][index[hand]];b=data['depths'][str(hi)][kind][index[hand]]
    return (1-w)*a+w*b


@register('T01','Nash jam-or-fold · short-stack blind battle',
          'Chen & Ankenman 2006, The Mathematics of Poker, ch. 12-13 (game); equilibrium solved in-repo',
          'Preflop, blind vs blind, at most 20 bb; otherwise S55')
class NashPushFold(Policy):
    def decide(self,o,draw):
        from ..agent import hand_key
        if o.board or o.active!=2:return self.defer(o,draw,'not_blind_vs_blind')
        bb=o.big_blind;hand=hand_key(o.hole);total=(o.stack+o.bet)/bb
        unopened=o.street_raises==0 and o.bet<bb and o.to_call==bb-o.bet
        if unopened:
            if total>MAX_BB or o.max_raise_to is None:return self.defer(o,draw,'deeper_than_20bb')
            p=frequency('push',hand,total)
            self.details={'policy_path':'nash_jam','scope':f'Nash jam-or-fold at {total:.1f} bb',
                'distribution':[{'action':'raise','raise_to':o.max_raise_to,'probability':p},
                                {'action':'fold','raise_to':0,'probability':1-p}]}
            return ('raise',o.max_raise_to) if draw<p else ('fold',0)
        faced=(o.bet+o.to_call)/bb
        # A jam: one raise that puts the hero (or nearly all of the raiser's stack) at risk.
        jam=o.street_raises==1 and o.bet==bb and (o.to_call>=o.stack or o.min_raise_to is None)
        if jam and min(faced,total)<=MAX_BB:
            depth=min(faced,total);p=frequency('call',hand,depth)
            self.details={'policy_path':'nash_call','scope':f'Nash call against a {depth:.1f} bb jam',
                'distribution':[{'action':'call','raise_to':0,'probability':p},
                                {'action':'fold','raise_to':0,'probability':1-p}]}
            return ('call',0) if draw<p else ('fold',0)
        return self.defer(o,draw,'not_a_jam_or_fold_spot')
