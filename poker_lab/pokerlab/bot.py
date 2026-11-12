"""SDK-neutral JSON-lines bot. This is not Sequoia's undisclosed Agent SDK.

Usage: python -m pokerlab.bot --strategy S55 < observations.jsonl
Each input line must contain fields of Observation (see agent.py).
"""
import argparse,json,sys
from pathlib import Path
from .agent import Agent,Observation
from .strategies import selectable_strategies


def main():
    p=argparse.ArgumentParser();p.add_argument('--strategy',default=None)
    a=p.parse_args()
    config=Path(__file__).resolve().parents[1]/'best_strategy.json'
    sid=a.strategy or (json.loads(config.read_text())['strategy'] if config.exists() else 'S78')
    choices={s.id:s for s in selectable_strategies()}
    if sid not in choices:p.error('Unknown strategy '+sid)
    agent=Agent(choices[sid])
    import random
    rng=random.Random(20261111)
    for line in sys.stdin:
        if not line.strip():continue
        data={}
        try:
            data=json.loads(line)
            data['hole']=tuple(data['hole']);data['board']=tuple(data['board'])
            o=Observation(**data)
            action,amount=agent.decide(o,rng.random())
            out={'action':('check' if o.to_call==0 else 'call') if action=='call' else action}
            if agent.strategy.research:out['research']=agent.last_details
            if action=='raise':out['raise_to']=amount
        except Exception as error:
            print(type(error).__name__+': '+str(error),file=sys.stderr)
            out={'action':'check' if isinstance(data,dict) and data.get('to_call')==0 else 'fold','error':True}
        print(json.dumps(out),flush=True)


if __name__=='__main__':main()
