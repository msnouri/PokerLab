# S55 vs GitHub poker projects

Read `Poker_GitHub_Comparison.html` for the conclusions and all comparisons.

The runnable benchmark compares **unmodified action methods** from Neuron
Poker's random and equity-threshold example policies with S55. It replaces
their Gym state/legality layer with PokerKit and supplies a shared equity
estimate. This is not a test of a pretrained DQN, not the full native Neuron
Poker stack, and not a test against MasterAI or PokerGPT.

## Results

- 7 external policies (one random and six equity settings).
- 10,000 heads-up hands per policy, using 5,000 deals played from both seats.
- 5,000 eight-player reset-stack hands per policy, four independent S55 copies
  and four independent external copies. Seats rotate; no agent shares cards
  or policy state with its copies.
- 128 eight-player tournaments per policy: 896 tables in total.
- S55 wins against some and loses against others in heads-up chip play. It
  has higher cohort-average tournament points in each tested configuration.
- This does not support a claim of superiority over trained CFR/DQN models.

The six threshold pairs `(call, bet)` are `(0.1,0.2)` through `(0.6,0.7)`, as
used in the upstream genetic-improvement initialization. There was no tuning
against S55 and no training in this comparison. S55 was frozen before testing.

## Reproduce

Extract the original `Poker_Agent_Lab.zip` so that `poker_lab` is adjacent to
this `github_comparison` directory. Install that project's requirements.
Set `POKER_LAB_PATH` to override its location.

```bash
python download_sources.py
PYTHONHASHSEED=0 python benchmark.py --deals 5000 --tables 128 --workers 8
python build_report.py
```

The source downloader pins individual Git blob hashes from repository tree
`242741ca6bcbdbebccacef1caee2bbb7273355f7`. It downloads only three small source
files and the root license; no weights, clients, credentials or services are
loaded. Upstream files are not redistributed in this archive. Set
`NEURON_SOURCE_PATH` to use an already downloaded matching source directory.

`build_report.py` additionally uses the packaged `review_inventory.json` for
the static repository review. Its results and reference URLs describe the
inspection on November 11, 2026. The upstream repositories may change later.

## Adapter choices and limitations

- The policy class and action methods execute as retrieved; only the Gym
  import is removed and its original Enum injected.
- Half-pot, pot and twice-pot actions retain the upstream environment's
  **additional chip contribution** interpretation. They are offered only when
  valid under PokerKit's standard no-limit rules. Integer chip sizes are used.
- All-in targets the maximum legal raise. Checks/calls/folds use PokerKit rules.
- Both policies use our existing preflop asset and 48-sample postflop random-hand
  equity estimator. This isolates much of the policy logic but does not compare
  the repositories' full equity pipelines. Results could change with more
  precise or opponent-conditioned equity.
- The original Gym environment's per-player raise cap is not imposed. These
  results concern the documented adapter, not native-environment replication.
- No 1 ms deadline is enforced. No API calls occur during play.
- Cash stacks reset to 2,000, blinds 10/20. Tournament starts are 2,000 chips,
  25-hand blind levels, a 200-hand cap, assumed 50/30/20 payouts and exact ICM
  of remaining payouts at the cap, matching our earlier research environment.
- Cash confidence intervals use independent duplicate-deal averages for heads-up
  and one cohort-average return per eight-player table-hand. Tournament intervals
  use one cohort-average point return per table. Copies are never treated as
  independent statistical samples from the same table.
- Raw outputs, exact settings and source hashes are included. Additional
  simultaneous intervals correct across all 21 reported metric/configuration
  comparisons; ordinary 95% intervals remain in the initial summary CSVs.

Our existing policy and equity code was not changed. `benchmark.py` patches
the engine's agent constructor only within benchmark processes, to dispatch
between S55 and the upstream policies. The prior project remains unchanged.
