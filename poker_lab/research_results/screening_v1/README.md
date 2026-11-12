# Unfavorable initial screen, retained for transparency

The first implementation used 168 independent contexts, including separate
facing-bet roots. Those roots did not condition the bettor's range on the
observed bet. All six hybrids lost to S55 in a 192,500-hand screen. The main
report retains these results, rather than replacing or hiding them.

The revision uses policies at the corresponding learned public betting-history
nodes. Its final confirmation run used new deck seed blocks (offset
300,000,000); the first screen used offset zero. Both runs used the same
opponent styles, 100-BB fresh stacks and no rake. The revision's score is not
a paired estimate of improvement over this screen because the deals differ.

`adapter.py`, `benchmark.py` and `blueprints.json` preserve the exact initial
adapter, harness and frozen model. `benchmark.json` and `hands.csv.gz` preserve
the outputs. The solver and engine behavior used by the initial screen is
unchanged by the revision. To rerun it in a **separate checkout**, copy
`adapter.py` over `poker_lab/pokerlab/research/policy.py`, and copy the two other
archived source/model files over the matching filenames in that package, then
run the archived benchmark command. That harness already uses the original
offset-zero constants and does not accept `--seed-offset`.

Original blueprint SHA256:
`1f7839e565ac0396a3e9ae68c74b9bed7736bcf8698521d83dcdd52ef8568c37`.
