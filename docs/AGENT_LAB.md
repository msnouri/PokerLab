# Agent Lab

![Agent Lab: table, coach, policy comparison, preflop range and session](media/agent-lab.png)

```bash
python -m desktop --lab            # or: bash "Launch Poker Lab.command" --lab
python -m desktop --lab --seed 86  # same deals every time
```

The lab opens on a hand that is already waiting for you. Everything on screen
is computed locally from the practice engine (PokerKit) and the selected
policy; it does not read the screen or talk to another program.

## What is on screen

| Area | What it shows |
|---|---|
| Table | Seats with position badges, stacks and bets in big blinds, last action per seat, the board, and opponents' cards only after a showdown they reached |
| Coach | The selected policy's action, its action mix when it reports one, equity against random hands next to the equity the price requires, and the facts behind the spot |
| Same spot, other policies | What up to five pinned policies do with the same cards and the same random variate |
| Preflop range | A 13 × 13 matrix built by asking the policy about all 169 starting hands in your current spot; split cells are mixed actions, your hand is outlined |
| Session | Hands, net big blinds, bb/100, how often your action matched the coach, and a running-result line |

## Modes

- **Coach** shows the policy's move before you act. `↵` plays it.
- **Quiz** hides the move, the comparison and the preflop range until you act, then
  grades the decision: same action, same action with a different size, or different.
- **Watch** lets the policy play your seat, hand after hand.

## Keys

| Key | Action | Key | Action |
|---|---|---|---|
| `F` | Fold | `1`–`5` | Size presets |
| `C` | Check / call | `A` | Set the raise to all-in |
| `R` | Raise the shown amount | `↵` | Play the coach's move |
| `Space` | Next hand | `Q` / `W` | Quiz / Watch on and off |

## Table options

Six-max or heads-up; 12, 25, 50, 100 or 200 big blinds, reset every hand. The
short depths are where T01 (Nash jam-or-fold) is in scope:

![Heads-up at 12 bb with the Nash jam range](media/agent-lab-shortstack.png)

## What the numbers are not

Equity is a Monte Carlo estimate against uniformly random hands. It is not an
EV estimate and not a range-versus-range calculation. "Balanced range continues
about N %" is the minimum-defence-frequency formula, shown as context. Session
results are practice chips against this repository's heuristic opponents.

The lab code is `desktop/lab.py` (window) and `desktop/labmodel.py` (everything
it displays; no Qt, tested headless in `desktop/tests/test_lab.py`).
