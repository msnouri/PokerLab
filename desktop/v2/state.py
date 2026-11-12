"""Versioned observation schema. Unknown values are never converted to zeros."""
from dataclasses import dataclass, field, asdict
import hashlib
import json
import time
from typing import Any

SCHEMA_VERSION = 2
STATUSES = {'active', 'folded', 'all-in', 'empty', 'unknown'}


@dataclass
class Field:
    key: str
    value: Any = None
    quality: str = 'unknown'
    score: float = 0.
    reason: str = ''
    observed_at: float = 0.
    cached: bool = False

    @property
    def known(self):
        return self.quality in ('read', 'confirmed')


@dataclass
class Snapshot:
    frame_id: int
    captured_at: float
    source: str
    fields: dict[str, Field]
    issues: list[str] = field(default_factory=list)
    stable: bool = False
    read_ms: float = 0.
    ocr_calls: int = 0
    cache_hits: int = 0
    hand_id: str = ''
    history_complete: bool = False
    schema_version: int = SCHEMA_VERSION
    table_context: dict = field(default_factory=dict)

    def value(self, key, default=None):
        f = self.fields.get(key)
        return f.value if f and f.known else default

    def fingerprint(self):
        values = {k: (f.value, f.quality) for k, f in self.fields.items()}
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def to_dict(self):
        result=asdict(self)
        seats=self.table_context.get('seats',6)
        statuses=[self.value(f'seat_{i}_status') for i in range(seats)]
        board_known=all(self.fields.get(f'board_{i}') and self.fields[f'board_{i}'].known for i in range(1,6))
        street={0:'preflop',3:'flop',4:'turn',5:'river'}.get(sum(self.value(f'board_{i}') is not None for i in range(1,6)),'unknown') if board_known else 'unknown'
        result['summary']={'street':street,
            'active_players':sum(s in ('active','all-in') for s in statuses) if all(s is not None for s in statuses) else None,
            'occupied_seats':sum(s!='empty' for s in statuses) if all(s is not None for s in statuses) else None,
            'visible_controls':{a:self.value('button_'+a) for a in ('fold','check','call','bet','raise','all_in')},
            'your_turn':self.value('turn')}
        return result


def field_specs(seats=6):
    rows = [
        ('hole_1','Your first card','card','Cards',True),
        ('hole_2','Your second card','card','Cards',True),
        *[(f'board_{i}',f'Board card {i}','board','Cards',True) for i in range(1,6)],
        ('pot','Total pot','money','Table',True),
        ('to_call','Your call cost','money','Table',True),
        ('big_blind','Big blind','money','Table',True),
        ('small_blind','Small blind','money','Table',False),
        ('ante','Ante','money','Table',False),
        ('min_raise_to','Minimum raise to','bound','Table',False),
        ('max_raise_to','Maximum raise to','bound','Table',False),
        ('hand_number','Hand identifier','text','Table',False),
        ('turn','Your turn indicator','turn','Controls',True),
        ('timer','Time remaining (seconds)','integer','Controls',False),
        *[(f'button_{a}',f'{a.title()} control','control','Controls',True)
          for a in ('fold','check','call','bet','raise','all_in')],
    ]
    for seat in range(seats):
        rows += [(f'seat_{seat}_{key}',f'Seat {seat+1} · {label}',kind,'Seats',key in ('stack','bet','status','dealer'))
                 for key,label,kind in [('name','Name','text'),('stack','Stack','money'),('bet','Bet this street','money'),
                                        ('status','Status','status'),('dealer','Dealer marker','dealer')]]
    return [{'key':k,'label':label,'kind':kind,'group':group,'required':req} for k,label,kind,group,req in rows]


def validate_snapshot(snapshot, seats=6, hero=0):
    issues=[]
    def val(k): return snapshot.value(k)
    cards=[]
    for key in ['hole_1','hole_2']+[f'board_{i}' for i in range(1,6)]:
        f=snapshot.fields.get(key)
        if f and f.known and f.value is not None:
            cards.append(f.value)
    if len(set(cards)) != len(cards): issues.append('Duplicate visible cards')
    board_fields=[snapshot.fields.get(f'board_{i}') for i in range(1,6)]
    if all(f and f.known for f in board_fields):
        board=[f.value for f in board_fields];n=sum(c is not None for c in board)
        if n not in (0,3,4,5) or any(c is None for c in board[:n]): issues.append('Invalid board sequence')
    dealers=[i for i in range(seats) if val(f'seat_{i}_dealer') is True]
    if len(dealers)>1: issues.append('Multiple dealer markers')
    for k,f in snapshot.fields.items():
        if f.known and isinstance(f.value,(int,float)) and not isinstance(f.value,bool) and f.value<0:
            issues.append(f'Negative amount: {k}')
    stack,bet,cost=val(f'seat_{hero}_stack'),val(f'seat_{hero}_bet'),val('to_call')
    if stack is not None and cost is not None and cost>stack: issues.append('Call cost exceeds remaining stack')
    lo,hi=val('min_raise_to'),val('max_raise_to')
    if lo is not None and hi is not None:
        if lo>hi: issues.append('Raise bounds are reversed')
        if stack is not None and bet is not None and hi>stack+bet: issues.append('Raise exceeds available chips')
        if bet is not None and cost is not None and lo<=bet+cost: issues.append('Raise does not exceed a call')
    if val('big_blind') == 0: issues.append('Big blind must be positive')
    for i in range(seats):
        if val(f'seat_{i}_status') == 'all-in' and val(f'seat_{i}_stack') not in (None,0):
            issues.append(f'Seat {i+1}: all-in status conflicts with stack')
    snapshot.issues=issues
    return issues


class Tracker:
    """Conservative observed changes. Missing intermediate actions stay unknown."""
    def __init__(self):
        self.previous=None
        self.repeated=0
        self.events=[]
        self.sequence=0
        self.hand_counter=1

    def reset(self):
        self.__init__()

    def accept(self, snap, seats=6, hero=0):
        validate_snapshot(snap,seats,hero)
        old=self.previous
        if old and snap.frame_id<=old.frame_id: return False
        signature=snap.fingerprint()
        self.repeated=self.repeated+1 if old and signature==old.fingerprint() and not snap.issues else 1
        snap.stable=self.repeated>=2 and not snap.issues
        old_hand=old.value('hand_number') if old else None
        new_hand=snap.value('hand_number')
        new_board=tuple(snap.value(f'board_{i}') for i in range(1,6))
        old_board=tuple(old.value(f'board_{i}') for i in range(1,6)) if old else ()
        board_known=all(snap.fields.get(f'board_{i}') and snap.fields[f'board_{i}'].known for i in range(1,6))
        new_round=bool(old and ((new_hand and old_hand and new_hand!=old_hand) or
                       (any(old_board) and not any(new_board) and all(snap.fields.get(f'board_{i}') and snap.fields[f'board_{i}'].known for i in range(1,6)))))
        if new_round:
            self.hand_counter+=1
            self.add('hand','New hand observed',snap)
        snap.hand_id=str(new_hand or f'observed-{self.hand_counter}')
        # A visual timeline cannot establish completeness of an unseen action log.
        snap.history_complete=False
        if old and not new_round:
            if board_known and new_board!=old_board and not snap.issues:
                count=sum(c is not None for c in new_board)
                if count in (3,4,5): self.add('street',{3:'Flop',4:'Turn',5:'River'}[count]+' observed',snap)
            changed=[]
            for i in range(seats):
                for suffix in ('bet','status','dealer'):
                    k=f'seat_{i}_{suffix}';a=old.fields.get(k);b=snap.fields.get(k)
                    if a and b and a.known and b.known and a.value!=b.value:
                        changed.append((i,suffix,a.value,b.value))
            for i,key,a,b in changed:
                if key=='bet': self.add('contribution',f'Seat {i+1} contribution {a} → {b}',snap)
                elif key=='status': self.add('status',f'Seat {i+1}: {b}',snap)
                elif b is True: self.add('dealer',f'Dealer marker at seat {i+1}',snap)
            if len({i for i,_,_,_ in changed})>1:
                self.add('gap','Multiple seats changed; action order is unknown',snap)
        self.previous=snap
        return True

    def add(self,kind,message,snap):
        self.sequence+=1
        self.events.append({'id':self.sequence,'kind':kind,'message':message,'frame_id':snap.frame_id,'time':snap.captured_at})
        self.events=self.events[-150:]
