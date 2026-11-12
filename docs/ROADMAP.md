# What is missing, in priority order

Compared with [dickreuter/Poker](https://github.com/dickreuter/Poker) (GPL-3.0),
PokerLab has stronger evidence (seeded benchmarks, paired intervals, CI on two
Mac architectures) and a cleaner engine boundary (PokerKit owns the rules). It
lacks several things that project has had for years, and a few neither has.

## Policy quality

1. **Opponent ranges.** Every equity number is against uniformly random hands.
   A range model conditioned on position and action (even a coarse one: open,
   3-bet, call, check-raise buckets) would change more decisions than any new
   heuristic. The T03 result shows why: a range-blind MDF over-calls.
2. **Opponent stacks in `Observation`.** Policies see only the hero's stack, so
   effective-stack decisions (T01, SPR, commitment) use an upper bound.
3. **Multi-street search.** The R-series solves one street of a reduced
   heads-up game. Depth-limited re-solving from the current public state
   (DeepStack, Pluribus) is the step that made research agents strong.
4. **Tournament maths.** `risk` is a scalar margin. An ICM model
   (Malmuth–Harville) for the final-table and bubble spots is a contained project.
5. **Bet-size abstraction.** Policies choose one size per spot. Two or three
   sizes with frequencies would let the range matrix show sizing splits.

## Tooling

6. **Hand-history import and review.** Parse the text hand histories that
   poker sites export, replay each decision through any policy, and list the
   largest disagreements. This is the main thing users of the reference project
   get from its "strategy analyzer", and it works on finished sessions.
7. **Strategy editor.** The 80 heuristics are parameter sets; a form that edits
   a copy, shows the range matrix changing live, and saves to a JSON file.
8. **Session persistence.** The lab session is in memory. A local SQLite log
   (spot, action, coach action, result) would enable leak reports per street
   and per position.
9. **Parameter search.** The reference project ships a genetic algorithm. Here
   the paired-deal benchmark is already the fitness function; add a
   successive-halving or Bayesian search over `Strategy` fields.
10. **Windows and Linux capture.** Vision Studio is macOS-only.

## Distribution

11. **Signed, notarized Mac app.** `packaging/` builds an unsigned bundle; see
    [`packaging/README.md`](../packaging/README.md) for the signing step.
12. **A project licence**, then topics on the GitHub page.

## Scope note on real-money sites

PokerStars, GGPoker and partypoker prohibit bots and real-time assistance,
including charts and solvers consulted during a hand, and enforce it with
permanent bans and confiscated balances
([overview](https://www.pokernews.com/news/2020/10/what-is-meant-by-real-time-assistance-rta-38054.htm));
GGPoker additionally bans third-party poker software while its client runs
([report](https://www.pokerlistings.com/news/ggpoker-has-tightened-its-policy-on-third-party-software)).
The other players at those tables have not agreed to play against software.
PokerLab therefore stays a study tool: practice tables, benchmarks, and review
of finished hands. It does not click in, hide from, or advise during play on a
poker client, and those features are not on this roadmap.
