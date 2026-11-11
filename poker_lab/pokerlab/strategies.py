"""Original heuristics inspired by the supplied books, not transcribed systems.

Five variants of each of sixteen mechanisms. Parameter values are experiment
design choices, not numbers claimed to be recommended by the authors.
"""
from dataclasses import dataclass, asdict, replace


@dataclass(frozen=True)
class Strategy:
    id: str
    family: str
    label: str
    source: str
    open_fraction: float = .22
    late_bonus: float = .14
    value_equity: float = .62
    call_margin: float = .07
    bet_pot: float = .65
    bluff: float = .05
    semi_bluff: float = .2
    cbet: float = .3
    trap: float = 0.
    check_raise: float = 0.
    protect: float = 0.
    pot_control: float = 0.
    polar: bool = False
    push_bb: float = 0.
    realization: float = .9
    premium_only: bool = False
    adapt: bool = False
    risk: float = 0.


# Sources use printed page numbers for Brokos and Dangel, EPUB chapters for
# Hellmuth. Different variants implement different numerical hypotheses.
FAMILIES = [
 ('premium', 'Premium-hand patience', 'Hellmuth ch.3,6; limit advice adapted',
  dict(open_fraction=.09,late_bonus=.02,value_equity=.68,bluff=0.,cbet=.1,premium_only=True)),
 ('tag', 'Tight aggressive', 'Hellmuth ch.4,6',
  dict(open_fraction=.17,late_bonus=.14,value_equity=.63,bluff=.035,cbet=.45)),
 ('steal', 'Position and blind stealing', 'Hellmuth ch.6; Brokos ch.1',
  dict(open_fraction=.19,late_bonus=.32,bluff=.1,cbet=.5,bet_pot=.45)),
 ('lag', 'Loose aggressive pressure', 'Hellmuth ch.6, opponent archetypes',
  dict(open_fraction=.35,late_bonus=.23,value_equity=.57,bluff=.14,semi_bluff=.5,cbet=.7,call_margin=.06)),
 ('value', 'Low-bluff value extraction', 'Dangel ch.6 pp.132-134; Hellmuth ch.3',
  dict(open_fraction=.22,value_equity=.55,bet_pot=.9,bluff=0.,semi_bluff=.05,cbet=.05)),
 ('station_exploit', 'Observed caller exploitation', 'Hellmuth ch.3-4, elephant; Dangel ch.5',
  dict(open_fraction=.23,value_equity=.58,bet_pot=.8,bluff=.04,adapt=True)),
 ('bluffcatch', 'Aggression-aware bluff catching', 'Hellmuth ch.3-4, jackal; Dangel ch.5',
  dict(open_fraction=.24,value_equity=.7,call_margin=.01,bluff=.01,pot_control=.5,adapt=True)),
 ('odds', 'Pot odds and disciplined folds', 'Dangel ch.6-8; Brokos ch.1 pp.36-38',
  dict(open_fraction=.25,value_equity=.65,call_margin=.03,realization=.96,bluff=.01,cbet=.1)),
 ('semibluff', 'Draw-based semi-bluffing', 'Brokos ch.2 pp.57-59; ch.3 pp.84-86',
  dict(open_fraction=.26,semi_bluff=.72,bluff=.01,bet_pot=.65)),
 ('protection', 'Equity denial and protection', 'Brokos ch.2 pp.57-59; Dangel ch.6',
  dict(open_fraction=.25,value_equity=.61,protect=.75,bet_pot=.45,cbet=.25)),
 ('control', 'Equity realization and pot control', 'Brokos ch.1 pp.36-38; ch.6 p.187',
  dict(open_fraction=.23,pot_control=.85,realization=.82,bluff=.025,value_equity=.69,bet_pot=.45)),
 ('polar', 'Polarized value and bluff pressure', 'Brokos ch.3 pp.84-88; ch.4',
  dict(open_fraction=.24,polar=True,value_equity=.74,bluff=.12,bet_pot=1.1,semi_bluff=.4)),
 ('checkraise', 'Mixed check-raise defense', 'Brokos ch.3 pp.84-86; ch.5',
  dict(open_fraction=.24,check_raise=.65,semi_bluff=.55,trap=.2,value_equity=.68)),
 ('trap', 'Selective trapping', 'Hellmuth ch.6; Dangel ch.6 pp.132-134',
  dict(open_fraction=.18,trap=.65,value_equity=.7,bluff=.01,cbet=.1,bet_pot=.9)),
 ('shortstack', 'Shallow-stack commitment', 'Brokos ch.5 pp.160-170; Hellmuth ch.6',
  dict(open_fraction=.23,push_bb=15.,call_margin=.08,semi_bluff=.4,value_equity=.63)),
 ('hybrid', 'Position, draws and public-action adaptation', 'Original combination: Hellmuth ch.6; Brokos ch.1-6; Dangel ch.5-8',
  dict(open_fraction=.23,late_bonus=.23,semi_bluff=.48,check_raise=.2,pot_control=.35,protect=.3,adapt=True,push_bb=12.)),
]


def all_strategies():
    result = []
    for fi, (family, label, source, params) in enumerate(FAMILIES):
        base = Strategy('',family,label,source,**params)
        for variant in range(5):
            d = variant - 2
            result.append(replace(base,
                id=f'S{fi*5+variant+1:02d}', label=f'{label} / {variant+1}',
                open_fraction=max(.05,min(.65,base.open_fraction+.025*d)),
                value_equity=max(.4,min(.88,base.value_equity+.025*d)),
                call_margin=max(-.02,base.call_margin+.012*d),
                bet_pot=max(.25,base.bet_pot+.12*d),
                bluff=max(0.,min(.35,base.bluff+.015*d)) if base.bluff else 0.,
                risk=max(0.,.015*d)))
    return result


def baseline_strategies(field='mixed'):
    """Fixed, original opponents; never read the candidate's id or cards."""
    all_s = {s.id:s for s in all_strategies()}
    if field == 'tight':
        ids=['S03','S08','S38','S53','S63','S68','S73']
    elif field == 'aggressive':
        ids=['S15','S18','S20','S43','S48','S58','S78']
    else:
        ids=['S03','S08','S13','S18','S23','S33','S78']
    result=[replace(all_s[x],id=f'B{i}',label='Baseline '+all_s[x].label) for i,x in enumerate(ids)]
    # An intentionally passive, loose opponent tests value extraction.
    if field=='mixed':
        result[4]=replace(result[4],open_fraction=.65,value_equity=.9,call_margin=-.035,
                          realization=1.,bluff=0.,cbet=0.,semi_bluff=0.,bet_pot=.4)
    return result


def registry_rows():
    return [asdict(s) for s in all_strategies()]
