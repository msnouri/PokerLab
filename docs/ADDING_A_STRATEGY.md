# Adding a strategy

A strategy is one class in `poker_lab/pokerlab/library/`. Once registered it
appears in the Agent Lab selector, the JSON bot (`--strategy T05`) and the
benchmarks, with no other file to edit.

```python
# poker_lab/pokerlab/library/tight_button.py
from . import Policy, register

@register('T05', 'Button-only opener', 'Your source here', 'Unopened pots on the button; otherwise S55')
class ButtonOnly(Policy):
    def decide(self, o, draw):
        first_in = not o.board and o.street_raises == 0 and o.pot <= 1.5 * o.big_blind
        if not first_in or o.min_raise_to is None:
            return self.defer(o, draw, 'not_first_in')        # S55 decides
        self.details = {'policy_path': 'button_only', 'scope': 'Open any button, fold elsewhere'}
        if o.seat == o.players - 1:
            return 'raise', max(o.min_raise_to, int(2.5 * o.big_blind))
        return 'fold', 0
```

Then add the module name to the tuple in `library/__init__.py::load`.

## The contract

- **Input:** an `Observation` (`pokerlab/agent.py`): your cards, the board, pot,
  price, legal raise bounds, seat, table size, players still in, raises this
  street. Nothing about other players' cards or the deck.
- **`draw`:** a uniform number in [0, 1) supplied by the runner. Use it for
  mixed actions instead of creating your own random generator, so paired-deal
  benchmarks stay paired.
- **Output:** `('fold' | 'call' | 'raise', raise_to)`. `call` with nothing to
  call is a check. `raise_to` includes chips already bet this street and must lie
  in `[o.min_raise_to, o.max_raise_to]`; both are `None` when raising is unavailable.
- **`self.details`:** set `policy_path` (shown in the lab and counted by the
  engine) and a one-line `scope`. Add `distribution` (a list of
  `{action, raise_to, probability}`) to get the action-mix bar.
- **Out of scope?** `return self.defer(o, draw, 'reason')`.

Seat convention: with three or more players seat 0 is the small blind, seat 1
the big blind and the last seat the button; heads-up, seat 1 is the button.
`library/positions.py` turns that into names.

## Before you open a pull request

```bash
cd poker_lab && python -m unittest discover -s tests -v          # legality at five depths, registry
python -m pokerlab.library.benchmark --deals 4000 --workers 4     # add your id to CANDIDATES first
```

State the source of the idea and what the benchmark showed, including when it
loses. `poker_lab/library_results/README.md` is the format to follow.
