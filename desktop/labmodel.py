"""Agent Lab logic with no Qt in it: table session, coach, ranges, grading.

Everything the window shows is computed here so it can be tested headless.
Opponent cards stay inside `LabTable`; a view exposes them only after a hand
that ended in a showdown, and only for the players who reached it.
"""
from collections import deque
from dataclasses import asdict, replace
import random
import time

from pokerkit import Automation, Card, NoLimitTexasHoldem

from .model import Agent, Observation, STRATEGIES, CARD_TEXT, Advisor, validate
from pokerlab.agent import equity, hand_key, draw_strength, board_wetness
from pokerlab.library.positions import position_name

RANKS = "AKQJT98765432"
STREETS = ("Preflop", "Flop", "Turn", "River")
DEPTHS = (12, 25, 50, 100, 200)
DEFAULT_LINEUP = ("S08", "S18", "S23", "S33", "S53", "S78")
BB = 20
MATRIX_DRAWS = (.1, .3, .5, .7, .9)


def strategy_title(sid):
    s = STRATEGIES[sid]
    return f"{sid} · {s.label}"


class LabTable:
    """Cash-style practice: every hand starts with `depth_bb` big blinds each."""

    def __init__(self, seed=None, players=6, depth_bb=100, lineup=DEFAULT_LINEUP):
        if players not in (2, 6):
            raise ValueError("The lab table seats two or six players.")
        if depth_bb not in DEPTHS:
            raise ValueError(f"Stack depth must be one of {DEPTHS} big blinds.")
        if any(s not in STRATEGIES for s in lineup):
            raise ValueError("Unknown opponent strategy.")
        self.rng = random.Random(seed)
        self.players, self.depth_bb, self.bb = players, depth_bb, BB
        self.lineup = tuple(lineup)
        self.bots = [Agent(STRATEGIES[s]) for s in self.lineup]
        self.hand_no = 0
        self.results = []          # hero net in big blinds, one entry per finished hand
        self.new_hand()

    # ----- dealing and engine bookkeeping -------------------------------
    def new_hand(self):
        if self.hand_no and self.state.status:
            raise ValueError("Finish the current hand first.")
        self.hand_no += 1
        self.hero = (self.hand_no + 3) % self.players
        self.street, self.raises, self.raiser = -1, 0, None
        self.checked = set()
        self.history = []
        self.last_action = {}
        self.recorded = False
        start = self.depth_bb * self.bb
        auto = tuple(a for a in Automation if a != Automation.HOLE_DEALING)
        self.state = NoLimitTexasHoldem.create_state(
            auto, True, 0, (self.bb // 2, self.bb), self.bb, [start] * self.players, self.players)
        deck = list(CARD_TEXT)
        self.rng.shuffle(deck)
        self.state.deck_cards = deque(next(Card.parse(c)) for c in deck)
        for i in range(self.players):
            self.state.deal_hole(2, i)
        self._holes = [tuple(repr(c) for c in self.state.hole_cards[i]) for i in range(self.players)]
        self._advance()

    @property
    def board(self):
        return tuple(repr(c) for row in self.state.board_cards for c in row)

    def _sync_street(self):
        if self.state.street_index is not None and self.state.street_index != self.street:
            self.street = self.state.street_index
            self.raises = 0
            self.checked = set()

    def observation(self, seat=None):
        self._sync_street()
        i = self.hero if seat is None else seat
        s = self.state
        if not s.status or s.actor_index != i:
            raise ValueError("There is no decision for this player.")
        can_raise = s.can_complete_bet_or_raise_to()
        live = sum(s.statuses)
        in_position = None
        if live == 2:
            in_position = i > next(j for j in range(self.players) if j != i and s.statuses[j])
        return Observation(
            self._holes[i], self.board, i, self.players, live, s.stacks[i], self.bb,
            s.total_pot_amount, s.checking_or_calling_amount, s.bets[i],
            s.min_completion_betting_or_raising_to_amount if can_raise else None,
            s.max_completion_betting_or_raising_to_amount if can_raise else None,
            i / (self.players - 1), self.raises, self.raiser == i, i in self.checked,
            remaining=self.players, heads_up_in_position=in_position)

    def _act(self, i, action, amount=0):
        self._sync_street()
        s = self.state
        street = self.street
        if action == "raise":
            if not s.can_complete_bet_or_raise_to(amount):
                raise ValueError("That raise is outside the legal raise-to bounds.")
            verb = "raises to" if s.checking_or_calling_amount or (street == 0) else "bets"
            s.complete_bet_or_raise_to(amount)
            self.raises += 1
            if street == 0:
                self.raiser = i
            label = f"{verb} {self.in_bb(amount)}"
            short = ("Raise " if verb != "bets" else "Bet ") + self.in_bb(amount)
        elif action == "fold":
            if not s.can_fold():
                raise ValueError("Folding is unavailable; check instead.")
            s.fold()
            label, short = "folds", "Fold"
        elif action in ("call", "check"):
            cost = s.checking_or_calling_amount
            s.check_or_call()
            if not cost:
                self.checked.add(i)
            label = f"calls {self.in_bb(cost)}" if cost else "checks"
            short = f"Call {self.in_bb(cost)}" if cost else "Check"
        else:
            raise ValueError("Unknown action.")
        self.last_action[i] = {"text": short, "kind": action if action != "check" else "call", "street": street}
        self.history.append({"seat": i, "hero": i == self.hero, "street": street,
                             "who": "You" if i == self.hero else position_name(i, self.players),
                             "text": label})

    def in_bb(self, chips):
        value = chips / self.bb
        return f"{value:.0f} bb" if value == int(value) else f"{value:.1f} bb"

    def _advance(self):
        for _ in range(400):
            s = self.state
            if not s.status:
                self._record()
                return
            if s.actor_index == self.hero:
                return
            i = s.actor_index
            if i is None:
                raise RuntimeError("The engine has an unresolved action.")
            action, amount = self.bots[i].decide(self.observation(i), self.rng.random())
            self._act(i, action, amount)
        raise RuntimeError("Practice action limit exceeded.")

    def _record(self):
        if not self.recorded:
            self.recorded = True
            self.results.append((self.state.stacks[self.hero] - self.depth_bb * self.bb) / self.bb)

    def act(self, action, amount=0):
        if not self.state.status or self.state.actor_index != self.hero:
            raise ValueError("Deal a new hand.")
        self._act(self.hero, action, amount)
        self._advance()

    # ----- what the window may show --------------------------------------
    def view(self):
        s = self.state
        pending = bool(s.status and s.actor_index == self.hero)
        done = not s.status
        start = self.depth_bb * self.bb
        live = [bool(x) for x in s.statuses]
        shown = {}
        if done and sum(live) >= 2:
            shown = {i: self._holes[i] for i in range(self.players) if live[i] and i != self.hero}
        return {
            "hole": self._holes[self.hero], "board": self.board, "hero": self.hero,
            "players": self.players, "bb": self.bb, "depth_bb": self.depth_bb,
            "stacks": list(s.stacks), "bets": list(s.bets), "active": live,
            "pot": s.total_pot_amount, "hand_no": self.hand_no, "pending": pending, "done": done,
            "net_bb": (s.stacks[self.hero] - start) / self.bb if done else None,
            "deltas": [(x - start) / self.bb for x in s.stacks] if done else None,
            "positions": [position_name(i, self.players) for i in range(self.players)],
            "names": ["You" if i == self.hero else self.lineup[i] for i in range(self.players)],
            "history": list(self.history), "last_action": dict(self.last_action),
            "street": max(0, self.street), "shown": shown,
            "observation": asdict(self.observation()) if pending else None,
        }

    def session(self):
        hands = len(self.results)
        total = sum(self.results)
        running, series = 0., [0.]
        for value in self.results:
            running += value
            series.append(running)
        return {"hands": hands, "net_bb": total, "bb_per_100": 100 * total / hands if hands else 0.,
                "series": series, "best": max(self.results, default=0.), "worst": min(self.results, default=0.)}


# ----- coach -------------------------------------------------------------
def action_title(result, bb=BB):
    def units(chips):
        value = chips / bb
        return f"{value:.0f}" if value == int(value) else f"{value:.1f}"
    action = result["action"]
    if action == "raise":
        if result.get("all_in"):
            return f"All-in · {units(result['raise_to'])} bb"
        return f"Raise to {units(result['raise_to'])} bb"
    if action == "call":
        return f"Call {units(result['call_cost'])} bb"
    return action.capitalize()


def explain(data):
    """Plain facts about a spot. None of these is an EV estimate."""
    o = validate(data)
    eq = equity(tuple(sorted(o.hole)), o.board, o.active - 1)
    need = o.to_call / (o.pot + o.to_call) if o.to_call else 0.
    before = max(1, o.pot - o.to_call)
    facts = {
        "hand": hand_key(o.hole), "position": position_name(o.seat, o.players),
        "street": STREETS[(0, 0, 0, 1, 2, 3)[len(o.board)]],
        "equity": eq, "required_equity": need, "opponents": o.active - 1,
        "spr": o.stack / max(o.pot, o.big_blind),
        "stack_bb": o.stack / o.big_blind, "pot_bb": o.pot / o.big_blind,
        "to_call_bb": o.to_call / o.big_blind,
        "mdf": before / (before + o.to_call) if o.to_call else None,
        "bet_fraction": o.to_call / before if o.to_call else None,
        "draw": draw_strength(o.hole, o.board) if o.board else 0.,
        "wetness": board_wetness(o.board) if o.board else 0.,
    }
    return facts


def reasons(facts, result):
    """Short sentences for the coach card, built only from the facts above."""
    out = []
    eq, need = facts["equity"], facts["required_equity"]
    rivals = facts["opponents"]
    versus = "one random hand" if rivals == 1 else f"{rivals} random hands"
    if need:
        gap = eq - need
        out.append(f"{eq:.0%} equity against {versus}; the price needs {need:.0%} "
                   f"({'+' if gap >= 0 else '−'}{abs(gap):.0%}).")
    else:
        out.append(f"{eq:.0%} equity against {versus}; checking is free.")
    if facts["mdf"] is not None and facts["street"] != "Preflop":
        out.append(f"Bet is {facts['bet_fraction']:.0%} of the pot, so a balanced range continues about {facts['mdf']:.0%}.")
    if facts["street"] != "Preflop":
        if facts["draw"] >= .4:
            out.append("You hold a draw: " + ("flush and straight outs." if facts["draw"] > 1.1 else "outs to a straight or flush."))
        out.append(f"Stack-to-pot ratio {facts['spr']:.1f}" + (" — committed territory." if facts["spr"] < 1.5 else "."))
    else:
        out.append(f"{facts['hand']} from {facts['position']}, {facts['stack_bb']:.0f} bb behind.")
    path = result.get("policy_details", {}).get("policy_path", "heuristic")
    if result["action"] == "raise" and need and eq < need:
        out.append("Raising does not need the calling price: it can also win the pot when everyone folds.")
    if result["action"] == "fold" and need and eq > need and (path == "heuristic" or path.startswith("fallback")):
        out.append("It folds anyway: raw equity is discounted for the betting still to come and for the raises already made.")
    scope = result.get("policy_details", {}).get("scope")
    if scope:
        out.append(scope + ".")
    return out


def grade(action, amount, result):
    """Compare what the player did with the coach. Sizes within 35 % count as the same."""
    mine = "call" if action in ("call", "check") else action
    theirs = "call" if result["action"] in ("call", "check") else result["action"]
    if mine != theirs:
        return "differs"
    if mine == "raise" and result["raise_to"]:
        ratio = amount / result["raise_to"]
        if not .65 <= ratio <= 1.35:
            return "size"
    return "match"


class Coach:
    """Recommendations, side-by-side comparisons and preflop range matrices."""

    def __init__(self, seed=None):
        self.advisor = Advisor()
        if seed is not None:
            self.advisor.rng = random.Random(seed)
        self.agents = {}
        self.matrix_cache = {}
        self.agreed = self.sized = self.graded = 0

    def agent(self, sid):
        if sid not in self.agents:
            self.agents[sid] = Agent(STRATEGIES[sid])
        return self.agents[sid]

    def advise(self, data, sid):
        result = self.advisor.recommend(data, sid)
        result["all_in"] = result["action"] == "raise" and result["raise_to"] == data["max_raise_to"]
        facts = explain(data)
        result.update(title=action_title(result, data["big_blind"]), facts=facts, reasons=reasons(facts, result))
        return result

    def compare(self, data, sids, draw=.5):
        """Each policy's action on the same spot with the same random variate."""
        o = validate(data)
        rows = []
        for sid in sids:
            action, amount = self.agent(sid).decide(o, draw)
            if action == "call" and not o.to_call:
                action = "check"
            rows.append({"id": sid, "action": action, "kind": "call" if action == "check" else action,
                         "title": action_title({"action": action, "raise_to": amount, "call_cost": o.to_call,
                                                "all_in": action == "raise" and amount == o.max_raise_to}, o.big_blind)})
        return rows

    def record(self, action, amount, result):
        verdict = grade(action, amount, result)
        self.graded += 1
        self.agreed += verdict == "match"
        self.sized += verdict == "size"
        return verdict

    def agreement(self):
        return (self.agreed + self.sized) / self.graded if self.graded else None

    def matrix(self, data, sid):
        """13x13 preflop action frequencies for the hero's current spot.

        Row/column order is AKQJT98765432; suited hands sit above the diagonal.
        Each cell is (raise, call, fold) over five fixed variates, so a mixed
        policy shows as a split cell. Returns None after the flop.
        """
        if data["board"]:
            return None
        key = (sid, data["seat"], data["players"], data["active"], data["stack"], data["pot"],
               data["to_call"], data["bet"], data["street_raises"], data["min_raise_to"], data["max_raise_to"])
        if key in self.matrix_cache:
            return self.matrix_cache[key]
        base = validate(data)
        agent = self.agent(sid)
        cells, totals, combos = [], [0., 0., 0.], 0
        for i, a in enumerate(RANKS):
            row = []
            for j, b in enumerate(RANKS):
                if i == j:
                    hole, weight, name = (a + "s", b + "h"), 6, a + b
                elif i < j:
                    hole, weight, name = (a + "s", b + "s"), 4, a + b + "s"
                else:
                    hole, weight, name = (b + "s", a + "h"), 12, b + a + "o"
                o = replace(base, hole=hole)
                counts = [0, 0, 0]
                for draw in MATRIX_DRAWS:
                    action, _ = agent.decide(o, draw)
                    counts[0 if action == "raise" else 2 if action == "fold" else 1] += 1
                share = [c / len(MATRIX_DRAWS) for c in counts]
                for k in range(3):
                    totals[k] += share[k] * weight
                combos += weight
                row.append({"hand": name, "raise": share[0], "call": share[1], "fold": share[2]})
            cells.append(row)
        result = {"cells": cells, "raise": totals[0] / combos, "call": totals[1] / combos,
                  "fold": totals[2] / combos, "position": position_name(data["seat"], data["players"]),
                  "facing": "unopened pot" if not data["street_raises"] else
                            f"{data['street_raises']} raise{'s' if data['street_raises'] > 1 else ''}"}
        if len(self.matrix_cache) > 400:
            self.matrix_cache.clear()
        self.matrix_cache[key] = result
        return result


def bet_presets(o):
    """Raise-to amounts for the size buttons; pot-fraction sizes postflop, bb multiples preflop."""
    lo, hi = o["min_raise_to"], o["max_raise_to"]
    if lo is None:
        return []
    clamp = lambda v: int(min(hi, max(lo, v)))
    if not o["board"]:
        base = o["bet"] + o["to_call"]
        if o["street_raises"] == 0:
            sizes = [("2.2×", 2.2 * o["big_blind"]), ("2.5×", 2.5 * o["big_blind"]), ("3×", 3 * o["big_blind"])]
        else:
            sizes = [("2.5×", 2.5 * base), ("3×", 3 * base), ("4×", 4 * base)]
    else:
        after_call = o["pot"] + o["to_call"]
        sizes = [(label, o["bet"] + o["to_call"] + f * after_call)
                 for label, f in (("⅓", 1 / 3), ("½", .5), ("¾", .75), ("Pot", 1.))]
    out, seen = [], set()
    for label, value in sizes + [("All-in", hi)]:
        value = clamp(value)
        if value not in seen:
            seen.add(value)
            out.append((label, value))
    return out


def autoplay(table, coach, sid, hands, on_decision=None):
    """Let one policy play the hero seat; used by the demo mode and by tests."""
    start = time.perf_counter()
    for n in range(hands):
        if n or not table.state.status:
            if not table.state.status:
                table.new_hand()
        while table.state.status and table.state.actor_index == table.hero:
            data = table.view()["observation"]
            result = coach.advisor.recommend(data, sid)
            if on_decision:
                on_decision(data, result)
            table.act(result["action"], result["raise_to"] or 0)
    return time.perf_counter() - start
