# Poker Strategy Lab

A working offline, eight-player no-limit Texas Hold'em research agent and
reproducible benchmark. Created for Sadegh Nouri on November 11, 2026.

**Start with `Poker_Strategy_Report.html`.** It is self-contained and opens in a
browser without a server. Full parameters are in `strategies.csv`.

The current research candidate is **S55: equity realization and pot control,
variant 5**. It led fresh chip validation and all three tournament fields. Its
equally weighted tournament mean was 16.30 points/table. Corrected paired
intervals do **not** separate it from every finalist; do not interpret the rank
as proof of universal superiority.

## Completed experiment

| Phase | Completed |
|---|---:|
| Direct self-play | 80 candidates x 500 hands = 40,000 player-hands / 5,000 table-hands |
| Matched-opponent screening | 80 candidates x 500 hands = 40,000 table-hands |
| Fresh chip validation | 25 candidates x 2,000 hands = 50,000 table-hands |
| Tournament evaluation | 8 finalists x 128 tables x 3 fields = 3,072 tables |
| Tournament play | 529,966 table-hands |

The direct self-play leader was S65, the matched 500-hand leader was S40,
and the fresh validation and tournament leader was S55. This disagreement is
why selecting the largest profit over only 500 hands is unreliable.

## Install and reproduce

Tested on Python 3.12.14. Use Python 3.12 or newer. Dependencies are pinned to
the versions used here. Runtime package wheels must be available for your OS.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m pokerlab.experiment --stage all --hands 500 --validation-hands 2000 --tables 128 --workers 8
python -m pokerlab.analyze
```

Run from this directory. `--workers 2` reduces CPU and memory use. Seeds and
policy decisions are deterministic. Wall time and latency vary with the host.
The full run here took about two minutes; this is not a performance guarantee.
The preflop asset is already included; to regenerate it:

```bash
python -m pokerlab.build_assets --samples 4000
```

Individual stages are `league`, `screen`, `validate`, and `tournament`.
Validation requires the screening output; tournament requires validation.
`all` runs all four phases in order. Output names are stable and rerunning
overwrites the corresponding previous results.

## Use the bot

```bash
python -m pokerlab.bot < example_observation.jsonl
python -m pokerlab.bot --strategy S65 < example_observation.jsonl
```

One observation per JSON line; one decision per output line. The default is
read from `best_strategy.json`. Input fields are defined in the frozen
`Observation` dataclass in `pokerlab/agent.py`. A raise is expressed as the
total street contribution (`raise_to`), not an additional increment. Cards use
rank/suit notation such as `As`, `Td`, `7c`; only the acting player's two hole
cards and the exposed board belong in the observation.

Programmatic usage:

```python
from pokerlab.agent import Agent, Observation
from pokerlab.strategies import all_strategies

strategy = next(s for s in all_strategies() if s.id == "S55")
agent = Agent(strategy)  # Loads the preflop asset during initialization.
# observation = Observation(... public state plus your own hole cards ...)
# action, raise_to = agent.decide(observation, draw=0.51)
```

Supply an independent uniform random number as `draw` for mixed decisions.
Passing the same constant every time makes the bot deterministic and changes
its mixed-action frequencies. The JSON wrapper supplies a seeded random stream.
Its generic error fallback checks if free and otherwise folds; errors are also
reported to stderr. The research simulator instead fails on policy errors.

## Source structure

- `strategies.py`: 16 original mechanism families, five variants each.
- `agent.py`: information-limited policy, equity estimator and observation.
- `build_assets.py`: seeded 169-class preflop equity asset generator.
- `engine.py`: PokerKit game wrapper, legal observations, timing and invariants.
- `experiment.py`: seat-balanced self-play, common-deal gauntlet, validation,
  persistent-stack tournaments and exact cap ICM.
- `analyze.py`: report, figures, paired uncertainty, latency and default config.
- `bot.py`: SDK-neutral JSON-lines interface.
- `tests/test_core.py`: eight meaningful checks, including 400 independently
  evaluated showdown comparisons and 80 unequal-stack strategy tests.

## Interpreting the output

Big blinds / 100 is a chip-profit rate in a reset-stack simulated environment.
It is not an event score or a forecast of real-world winnings. Tournament
points are based on an **assumed 50/30/20 payout**, with exact ICM of remaining
places at the 200-hand cap. The assumed blind schedule is
20/30/40/60/100/150/200/300 (big blinds, 25 hands per level), with no antes.

The mixed baseline has premium/tight, positional, aggressive, passive-calling,
bluff-catching and adaptive behaviors. Tight and aggressive fields use
different fixed subsets. Full baseline parameters are in `baseline_fields.json`.
These opponents are intentionally simple and related to the candidate policy
architecture; this is a restricted, synthetic opponent population.

The first eight from each initial test plus each family's best gauntlet
representative are validated on fresh seed 71261111. Eight finalists are chosen
from that validation, then evaluated on tournament seed 91001111. Initial
rankings are subject to winner's curse. Tournament mean intervals are based on
128 matched seeds, averaging the three fields at each seed. Paired difference
intervals apply a Bonferroni correction across all 28 finalist pairs. Outcomes
outside this opponent population remain untested.

`wins` and `top3` in `tournaments.csv` count assigned finishing positions;
surviving capped players are not assigned a finish and are excluded from these
counts. Their ICM points are included in all score statistics. The primary
metric is average points, not those counts. `*_hands.csv` stores outcomes,
seeds and seats; `tournament_tables.csv` stores table outcomes. Latency in cash
summary rows covers all decisions at the table, not just the candidate's.

The preflop table simulates uniformly random opponents. Postflop equity uses
48 deterministic samples of legal unknown hands/runouts and a weak smoothing
prior. Betting pressure adds a heuristic adjustment; there is no full Bayesian
range reconstruction, CFR training, equilibrium solver or multi-street search.
ICM is exact for scoring; action decisions only use an approximate risk margin.

Cold and warm latency measurements exclude initialization and observation
conversion. The completed research matches record but do not enforce a 1 ms
deadline. Timing therefore does not certify compatibility with an event sandbox.

## Books and competition

Instructional concepts came from selected relevant sections of Hellmuth's
*Play Poker Like the Pros*, Brokos's *Play Optimal Poker 2*, and Dangel's
*Poker Poker*. Parameter values and all policy code are original experiment
choices. The fourth attachment, Carol Lynne's *Slow-Play (Poker Night 2)*,
is fiction and was excluded. The report maps families to chapters/pages.

The Sequoia event's official rules specify a confidential variant revealed at
the event, a supplied Agent SDK, a 60-minute build phase and sandbox deadlines.
This project's ordinary two-card Hold'em rules are a research assumption.
It is not an official submission and has not been tested against the official
SDK or event-specific variant. The report distinguishes confirmed format
details from assumed payouts and blind levels. This package connects to no
poker service and submits nothing to the competition.

Official rules: https://pokerbot.sequoiacap.com/rules.html

General-purpose dependencies:

- PokerKit: https://github.com/uoftcprg/pokerkit (MIT)
- eval7: https://github.com/JulianAndrews/pyeval7 (MIT)
- Treys: https://github.com/ihendley/treys (MIT; independent tests only)

No participant repository was copied. Uploaded books and extracted full text
are deliberately absent from this deliverable. See `THIRD_PARTY_NOTICES.txt`
for dependency licenses, and `results/manifest.json` for run configuration.
