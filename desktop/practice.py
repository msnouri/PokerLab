"""Interactive six-player PokerKit table. Other players' cards stay private."""
from collections import deque
from dataclasses import asdict
import random

from .model import Agent, Observation, STRATEGIES, CARD_TEXT
from pokerkit import Automation, Card, NoLimitTexasHoldem


class PracticeTable:
    def __init__(self, seed=None, players=6):
        if players not in (2,6):raise ValueError('Practice supports two or six players')
        self.rng = random.Random(seed)
        self.hand_no = 0
        self.players = players
        self.bb = 20
        self.bots = [Agent(STRATEGIES[s]) for s in ("S08", "S18", "S23", "S33", "S53", "S78")]
        self.new_hand()

    def new_hand(self):
        self.hand_no += 1
        self.hero = (self.hand_no + 3) % self.players
        self.street = -1
        self.raises = 0
        self.raiser = None
        self.checked = set()
        self.history = []
        auto = tuple(a for a in Automation if a != Automation.HOLE_DEALING)
        self.state = NoLimitTexasHoldem.create_state(auto, True, 0, (10, 20), 20, [2000] * self.players, self.players)
        deck = list(CARD_TEXT)
        self.rng.shuffle(deck)
        self.state.deck_cards = deque(next(Card.parse(c)) for c in deck)
        for i in range(self.players):
            self.state.deal_hole(2, i)
        # Keep only hero's initial cards for display after automated mucking.
        self.hero_cards = tuple(repr(c) for c in self.state.hole_cards[self.hero])
        self._advance()

    @property
    def board(self):
        return tuple(repr(c) for row in self.state.board_cards for c in row)

    def _sync_street(self):
        if self.state.street_index != self.street:
            self.street = self.state.street_index
            self.raises = 0
            self.checked = set()

    def observation(self, seat=None):
        self._sync_street()
        i = self.hero if seat is None else seat
        if not self.state.status or self.state.actor_index != i:
            raise ValueError("There is no decision for this player.")
        s = self.state
        can_raise = s.can_complete_bet_or_raise_to()
        return Observation(tuple(repr(c) for c in s.hole_cards[i]), self.board, i, self.players,
                           sum(s.statuses), s.stacks[i], self.bb, s.total_pot_amount,
                           s.checking_or_calling_amount, s.bets[i],
                           s.min_completion_betting_or_raising_to_amount if can_raise else None,
                           s.max_completion_betting_or_raising_to_amount if can_raise else None,
                           i / (self.players - 1), self.raises, self.raiser == i, i in self.checked,
                           remaining=self.players,heads_up_in_position=(i>next(j for j in range(self.players) if j!=i and s.statuses[j]) if sum(s.statuses)==2 else None))

    def _act(self, i, action, amount=0):
        self._sync_street()
        s = self.state
        if action == "raise":
            if not s.can_complete_bet_or_raise_to(amount):
                raise ValueError("That raise is outside the engine's legal raise-to bounds.")
            s.complete_bet_or_raise_to(amount)
            self.raises += 1
            if self.street == 0:
                self.raiser = i
            label = f"raises to {amount}"
        elif action == "fold":
            if not s.can_fold():
                raise ValueError("Folding is unavailable; check instead.")
            s.fold()
            label = "folds"
        elif action in ("call", "check"):
            cost = s.checking_or_calling_amount
            s.check_or_call()
            if not cost:
                self.checked.add(i)
            label = f"calls {cost}" if cost else "checks"
        else:
            raise ValueError("Unknown action.")
        who = "You" if i == self.hero else f"Seat {i + 1}"
        self.history.append(f"{who} · {label}")

    def _advance(self):
        for _ in range(300):
            if not self.state.status or self.state.actor_index == self.hero:
                return
            i = self.state.actor_index
            if i is None:
                raise RuntimeError("The engine has an unresolved action.")
            action, amount = self.bots[i].decide(self.observation(i), self.rng.random())
            self._act(i, action, amount)
        raise RuntimeError("Practice action limit exceeded.")

    def act(self, action, amount=0):
        if not self.state.status or self.state.actor_index != self.hero:
            raise ValueError("Start a new hand.")
        self._act(self.hero, action, amount)
        self._advance()

    def view(self):
        s = self.state
        pending = bool(s.status and s.actor_index == self.hero)
        return {"hole": self.hero_cards, "board": self.board, "hero": self.hero,
                "stacks": list(s.stacks), "bets": list(s.bets), "active": list(s.statuses),
                "pot": s.total_pot_amount, "hand_no": self.hand_no, "pending": pending,
                "net": s.stacks[self.hero] - 2000, "history": list(self.history),
                "observation": asdict(self.observation()) if pending else None}
