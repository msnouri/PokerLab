"""Small-game correctness curves, separate from the Hold'em playing benchmark."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

from .solver import ALGORITHMS, BucketGame, Solver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('research_results/convergence.json'))
    args = parser.parse_args()
    rows = []
    for algorithm in ALGORITHMS:
        solver = Solver(BucketGame.kuhn(), algorithm, seed=17)
        checkpoints = [10, 30, 100, 300, 1000, 3000]
        if algorithm == 'mccfr':
            checkpoints = [v*10 for v in checkpoints]
        started = time.perf_counter()
        for target in checkpoints:
            solver.train(target-solver.iteration)
            elapsed = time.perf_counter()-started
            rows.append(dict(algorithm=algorithm, iterations=target,
                training_seconds=elapsed, **solver.evaluate()))
        print(algorithm, rows[-1], flush=True)
    result = {'game': 'Standard three-card Kuhn poker; exact chance without replacement',
        'known_value_p0': -1/18, 'seed': 17,
        'note': 'MCCFR uses 10x as many iterations. Timings are sequential local Python wall time; no equal-work or full-Holdem speed claim.',
        'environment': {'platform': platform.platform(), 'python': sys.version.split()[0],
            'packages': {p: importlib.metadata.version(p) for p in ('numpy', 'pokerkit', 'eval7', 'scipy')}},
        'rows': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
