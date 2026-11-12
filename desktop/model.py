"""Validated boundary between editable/screen-derived data and the policy."""
from dataclasses import asdict
import math
import random
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parents[1] / "poker_lab"
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

from pokerlab.agent import Agent, Observation, CARD_TEXT, equity
from pokerlab.strategies import selectable_strategies

STRATEGIES = {s.id: s for s in selectable_strategies()}


def cards(text):
    """Accept As Kh, As,Kh, or AsKh; reject unknown and repeated cards."""
    value = "".join(text.replace(",", " ").replace("10", "T").split())
    if len(value) % 2:
        raise ValueError("Cards use rank + suit, for example As Kh or 10h 9h.")
    result = tuple(value[i].upper() + value[i + 1].lower() for i in range(0, len(value), 2))
    if any(c not in CARD_TEXT for c in result):
        raise ValueError("Use ranks 2–9,T,J,Q,K,A and suits c,d,h,s.")
    if len(set(result)) != len(result):
        raise ValueError("A card appears more than once.")
    return result


def validate(data):
    """No policy call until cards, integer chip units, and bounds are valid."""
    data = dict(data)
    for key in ("hole", "board"):
        data[key] = cards(data[key]) if isinstance(data[key], str) else tuple(data[key])
    if len(data["hole"]) != 2 or len(data["board"]) not in (0, 3, 4, 5):
        raise ValueError("Enter two hole cards and 0, 3, 4, or 5 board cards.")
    known = data["hole"] + data["board"]
    if any(c not in CARD_TEXT for c in known) or len(set(known)) != len(known):
        raise ValueError("Cards must be valid and unique across your hand and board.")
    for key in ("seat", "players", "active", "stack", "big_blind", "pot", "to_call", "bet", "street_raises", "remaining"):
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key.replace('_', ' ')} must be a non-negative integer.")
    if not 2 <= data["players"] <= 8 or not 2 <= data["active"] <= data["players"]:
        raise ValueError("Use 2–8 seats, with at least two active players.")
    if not 0 <= data["seat"] < data["players"] or not data["players"] <= data["remaining"] <= 10000:
        raise ValueError("Seat or tournament player count is inconsistent.")
    if data["big_blind"] <= 0 or data["stack"] <= 0:
        raise ValueError("Big blind and remaining stack must be positive.")
    if data["to_call"] > data["stack"]:
        raise ValueError("Call cost must be capped at your remaining stack.")
    if data["pot"] < data["bet"] + data["to_call"]:
        raise ValueError("Pot must include the bets already on the table, including the bet you face.")
    for key in ("position", "opponent_looseness", "opponent_aggression"):
        value = data[key]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{key.replace('_', ' ')} must be between 0 and 1.")
    for key in ("preflop_raiser", "checked_before", "tournament"):
        if not isinstance(data[key], bool):
            raise ValueError(f"{key.replace('_', ' ')} must be true or false.")
    if data.get('heads_up_in_position') is not None and type(data['heads_up_in_position']) is not bool:
        raise ValueError('Heads-up position must be a boolean or unknown')
    lo, hi = data["min_raise_to"], data["max_raise_to"]
    if (lo is None) != (hi is None):
        raise ValueError("Both raise bounds must be supplied, or both left unavailable.")
    if lo is not None:
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (lo, hi)):
            raise ValueError("Raise bounds must be integer chip amounts.")
        if not data["bet"] + data["to_call"] < lo <= hi <= data["bet"] + data["stack"]:
            raise ValueError("Raise-to bounds conflict with your current bet, call cost, or stack.")
    return Observation(**data)


class Advisor:
    def __init__(self):
        self.agents = {}
        self.rng = random.Random()

    def recommend(self, data, strategy="S55"):
        start = time.perf_counter()
        obs = validate(data)
        if strategy not in STRATEGIES:
            raise ValueError("Unknown strategy.")
        if strategy not in self.agents:
            self.agents[strategy] = Agent(STRATEGIES[strategy])
        agent = self.agents[strategy]
        action, amount = agent.decide(obs, self.rng.random())
        if action == "call":
            action = "call" if obs.to_call else "check"
        return {"action": action, "raise_to": amount if action == "raise" else None,
                "call_cost": obs.to_call, "equity": equity(tuple(sorted(obs.hole)), obs.board, obs.active - 1),
                "pot_odds": obs.to_call / (obs.pot + obs.to_call) if obs.to_call else 0,
                "policy_ms": (time.perf_counter() - start) * 1000, "strategy": strategy,
                "policy_details":dict(agent.last_details)}


def example():
    return asdict(Observation(("As", "Qs"), ("Js", "Ts", "2d"), 5, 6, 3, 1800, 20,
                              300, 100, 0, 200, 1800, 1., 1, True, False, remaining=6))
