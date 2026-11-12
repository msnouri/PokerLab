"""Plug-in policies: one class per strategy, registered with a decorator.

Adding a strategy is one file. Subclass `Policy`, implement `decide`, and
decorate the class with `@register(...)`; it then appears in the bot CLI, the
benchmarks and the desktop Agent Lab. See docs/ADDING_A_STRATEGY.md.

A policy sees only the public `Observation`. It returns the same tuple as the
built-in agent, ('fold'|'call'|'raise', raise_to), and may delegate any spot
outside its scope to `self.fallback` (S55 by default). `self.details` is shown
in the GUI, so say which path produced the action.
"""
from dataclasses import dataclass
from importlib import import_module

REGISTRY={}


@dataclass(frozen=True)
class Entry:
    id: str
    key: str
    label: str
    source: str
    scope: str
    factory: type


def register(id,label,source,scope):
    def wrap(cls):
        key=cls.__name__
        if any(e.id==id for e in REGISTRY.values()) and key not in REGISTRY:
            raise ValueError(f'Duplicate library id {id}')
        REGISTRY[key]=Entry(id,key,label,source,scope,cls)
        return cls
    return wrap


class Policy:
    """Base class. `fallback` is a ready built-in Agent for out-of-scope spots."""
    fallback_id='S55'

    def __init__(self):
        from ..agent import Agent
        from ..strategies import all_strategies
        self.fallback=Agent(next(s for s in all_strategies() if s.id==self.fallback_id))
        self.details={}

    def defer(self,o,draw,reason):
        self.details={'policy_path':'fallback_'+reason,'fallback':self.fallback_id,
                      'scope':f'Outside this policy ({reason.replace("_"," ")}); {self.fallback_id} decided'}
        return self.fallback.decide(o,draw)

    def decide(self,o,draw):
        raise NotImplementedError


def load():
    """Import the bundled policy modules once; third-party modules may register too."""
    for name in ('pushfold','positional','mdf','combined'):
        import_module(f'{__name__}.{name}')
    return REGISTRY


def build(key):
    return load()[key].factory()


def entries():
    return sorted(load().values(),key=lambda e:e.id)
