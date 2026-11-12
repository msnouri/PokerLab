# References behind the library policies (T-series)

| Policy | Idea | Source | What is taken from it |
|---|---|---|---|
| T01 | Heads-up jam-or-fold equilibrium | Chen & Ankenman, *The Mathematics of Poker* (ConJelCo, 2006), ch. 12–13 | The game definition only. The ranges are solved here by `library/build_pushfold.py` (fictitious play on a Monte Carlo 169 × 169 equity matrix) and stored with their exploitability. At 10 bb the solution jams 58 % and calls 38 %. |
| T02 | Raise-first-in frequency by seat | Solver output for 6-max, 100 bb, no ante as published at [quintace-internals: format transitions](https://quintace-internals.pages.dev/format-transitions): UTG 17.2 %, MP 22.9 %, CO 28.1 %, BTN 43.3 % | The four frequencies. The small-blind (40 %), heads-up button (80 %) and full-ring early-seat values are this repository's assumptions. The hand ordering is this repository's, so ranges match the source in width, not hand for hand. |
| T03 | Minimum defence frequency | Chen & Ankenman 2006, ch. 11; Janda, *Applications of No-Limit Hold'em* (Two Plus Two, 2013) | Continue with pot / (pot + bet) of the range. |
| T03 | Geometric bet sizing | Chen & Ankenman 2006, ch. 14 | Equal pot fractions per street that end all-in on the river. |
| T03 | Bluff share of a betting range | Same | A river bet of b into p supports b / (p + 2b) bluffs. |

Further reading that is not implemented yet (see [ROADMAP.md](ROADMAP.md)):

- Brown & Sandholm, "Superhuman AI for multiplayer poker", *Science* 365 (2019):
  blueprint plus depth-limited search in six-player games. Already in
  [`research/READING_LIST.md`](../research/READING_LIST.md).
- Malmuth–Harville independent chip model for tournament payouts (Malmuth,
  *Gambling Theory and Other Topics*, 1987).
- Sklansky–Chubukov rankings for open-jamming against a caller who sees your hand.

These are textbook results applied as heuristics. None of them makes a policy
"game-theory optimal" here; the measured results are in
[`poker_lab/library_results/README.md`](../poker_lab/library_results/README.md).
