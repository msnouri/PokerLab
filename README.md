# Poker Agent Lab

Book-inspired poker policies, reproducible simulation experiments, and an
evaluation against selected open-source example policies. This repository
combines both stages of the project, their raw results, and one LaTeX report.

**New: [macOS Vision Studio](desktop/VISION_STUDIO.md)** — a Qt Quick interface
with selected-window capture, on-device Apple Vision OCR, guided calibration,
53 table fields for six seats, local replay, and measured diagnostics.
Strategies remain in the [classic practice workbench](desktop/README.md).

![Vision Studio](desktop/previews/studio-overview.png)

**Read the [compiled report](report/poker_agent_report.pdf) or its
[LaTeX source](report/poker_agent_report.tex).**

## Findings

- 80 original heuristic policies: 16 families with five parameter variants.
- Every candidate completed 500 direct self-play hands and 500 common-opponent
  hands; 25 shortlisted candidates received 2,000 fresh validation hands each.
- Eight finalists were evaluated in 3,072 eight-player sit-and-gos. S55
  (equity realization and pot control) had the highest mean across the three
  tested fields, without statistically separating from every finalist.
- External comparison: 70,000 heads-up hands, 35,000 eight-player cash hands,
  and 896 tournaments against seven adapted Neuron Poker example policies.
- S55 led those tournament comparisons but lost heavily to aggressive
  example policies in heads-up cash play. **No pretrained DQN or CFR policy
  was benchmarked. No general superiority claim is supported.**

The simulations assume ordinary two-card no-limit Texas Hold'em. Tournament
payouts and the full blind schedule are research assumptions, not a verified
event submission. Read the report's methodology and adapter limitations.

## Repository contents

| Location | Contents |
|---|---|
| [`report/`](report/) | Combined LaTeX report, PDF, figures, and data-driven tables |
| [`poker_lab/pokerlab/`](poker_lab/pokerlab/) | Agent, 80-policy registry, PokerKit wrapper, experiments and analysis |
| [`poker_lab/results/`](poker_lab/results/) | Initial screening, validation and tournament raw/summary results |
| [`poker_lab/strategies.csv`](poker_lab/strategies.csv) | All 80 numerical configurations and conceptual attribution |
| [`github_comparison/`](github_comparison/) | External-policy adapter, source downloader, results and source inventory |
| [`poker_lab/tests/`](poker_lab/tests/) | Legality, determinism, information boundaries, equity and settlement checks |
| [`desktop/`](desktop/) | Qt desktop GUI, practice table, calibrated vision, tests, and Mac setup guide |

## Run the desktop GUI on Mac

Requires macOS 13+ and Python 3.12, on Intel or Apple Silicon. Download this
repository, extract it, and double-click **Launch Poker Lab.command**. The
launcher installs the GUI dependencies in a local virtual environment on its
first run. If Finder does not launch it, open Terminal in the extracted folder:

```bash
bash "Launch Poker Lab.command"
```

Vision Studio starts with a generated replay that the reader actually analyzes.
On Mac, number/text OCR uses Apple Vision; no Tesseract installation is needed
for Studio. Live capture requires Screen Recording permission. Each external
table design needs its own calibrated regions and labelled visual examples.
This is a source application, not a signed standalone `.app`.

See the [Vision Studio guide](desktop/VISION_STUDIO.md) for setup, the complete
feature table, data fields, benchmarks, and remaining native-device checks.
Use `python -m desktop --classic` for the previous practice-and-strategy GUI.

## Install and test

Python 3.12+ is recommended; the recorded experiments used Python 3.12.14.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
make test
```

## Reproduce the original experiment

```bash
cd poker_lab
python -m pokerlab.experiment --stage all --hands 500 --validation-hands 2000 --tables 128 --workers 8
python -m pokerlab.analyze
python -m pokerlab.bot < example_observation.jsonl
```

The bot defaults to S55. Choose a different candidate with `--strategy S01`
through `--strategy S80`. The JSON interface is neutral and requires mapping
to a competition's actual SDK.

## Reproduce the external-policy comparison

From the repository root:

```bash
python github_comparison/download_sources.py
PYTHONHASHSEED=0 python github_comparison/benchmark.py --deals 5000 --tables 128 --workers 8
python github_comparison/build_report.py
```

The downloader obtains only the pinned, reviewed example source files and
license. Those files are ignored by Git. Both policies use our shared equity
feature; the native Neuron Poker environment and its full equity pipeline
are not reproduced. Read [`github_comparison/README.md`](github_comparison/README.md).

## Compile the LaTeX report

Use a normal TeX Live installation containing `pdflatex`, `geometry`,
`graphicx`, `booktabs`, `tabularx`, `longtable`, `xcolor`, `hyperref`,
`microtype`, `enumitem`, `fancyhdr`, and Latin Modern fonts (`lmodern`).

```bash
make report
```

`report/build_tables.py` regenerates numerical tables from the tracked CSVs.
It does not rerun any poker matches. The included PDF corresponds to the
included source and recorded results. Raw simulation outcomes are seeded;
timing and floating-point presentation can vary by platform.

## Attribution and scope

The report attributes concepts to the reviewed instructional books and names
the inspected GitHub projects. Parameter values and the heuristic policy
implementations are experimental choices, not author-prescribed systems.
The uploaded books and their extracted text are not part of this repository.

The project uses PokerKit and eval7; Treys is used for independent evaluator
tests. See [`THIRD_PARTY_NOTICES.txt`](poker_lab/THIRD_PARTY_NOTICES.txt).
The source downloader preserves the external project's license. No external
API is used during gameplay, and no poker client is automated.
