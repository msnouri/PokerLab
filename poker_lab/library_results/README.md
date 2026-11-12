# Library policies against S55

`python -m pokerlab.library.benchmark --deals 4000 --workers 2` (seeded;
[`benchmark.json`](benchmark.json) holds the output). Every candidate plays the
same deals from every seat against the same opponents, with stacks reset each
hand. "Paired" is the candidate's result minus S55's on identical deals, in big
blinds per 100 hands, with a 95 % interval.

| Format | Hands | T01 Nash jam/fold | T02 positional opens | T03 MDF + geometric | T04 all three |
|---|---|---|---|---|---|
| 6-max, 100 bb, mixed baseline field | 24,000 | 0.0 (never in scope) | −6.9 ± 6.0 | **−98.3 ± 21.3** | **−76.4 ± 19.8** |
| 6-max, 15 bb, mixed baseline field | 24,000 | +0.06 ± 0.04 | −1.3 ± 2.3 | −12.2 ± 3.9 | −6.6 ± 4.1 |
| Heads-up, 100 bb, against S55 | 8,000 | 0.0 (never in scope) | +5.5 ± 5.0 | −4.8 ± 17.3 | +0.8 ± 17.6 |
| Heads-up, 12 bb, against S55 | 8,000 | +2.3 ± 3.9 | +2.5 ± 1.1 | −1.4 ± 3.9 | +0.7 ± 4.9 |

## Reading

- **S55 stays the default.** No library policy beats it in the six-max field.
- **T03 loses heavily at 100 bb six-max.** The baseline opponents bluff rarely,
  and defending at the minimum defence frequency pays off their value bets.
  That is the known weakness of MDF against under-bluffing opponents; it is
  included as a reference implementation, not as a recommendation.
- **T02** gains a little heads-up and loses a little six-max. Both effects are
  near their intervals.
- **T01** only acts blind against blind at 20 bb or less, so it rarely matters
  six-max. Heads-up at 12 bb its gain is not separated from zero in 8,000 hands.

Scope: simulated chips against this repository's own heuristics. Nothing here
is evidence about human opponents, solver opponents or real-money games.
