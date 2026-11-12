"""Audit recorded deal units, then rebuild tables/figures/bibliography, not matches."""
import csv
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import unicodedata

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import t as student

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'research'
RESULTS = ROOT/'poker_lab'/'research_results'
TABLES = HERE/'tables'
FIGURES = HERE/'figures'
NAMES = {'S55': 'S55 baseline', 'R01': 'CFR', 'R02': 'MCCFR', 'R03': 'CFR+',
         'R04': 'DCFR', 'R05': 'PCFR+', 'R06': 'PDCFR+'}
ALGO_IDS = dict(zip(('cfr', 'mccfr', 'cfr_plus', 'dcfr', 'pcfr_plus', 'pdcfr_plus'),
                   ('R01', 'R02', 'R03', 'R04', 'R05', 'R06')))


def tex(text):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode()
    return ''.join({'&': r'\&', '%': r'\%', '_': r'\_', '#': r'\#', '$': r'\$'}.get(c, c) for c in text)


def ci(row):
    return f"{row['bb100']:+.2f} [{row['ci95_low']:+.2f}, {row['ci95_high']:+.2f}]"


def table(name, header, rows, columns):
    text = '\\begin{tabular}{'+columns+'}\n\\toprule\n'+header+' \\\\\n\\midrule\n'
    text += ''.join(' & '.join(str(v) for v in row)+' \\\\\n' for row in rows)
    text += '\\bottomrule\n\\end{tabular}\n'
    (TABLES/name).write_text(text)


def audit(data):
    raw = RESULTS/'hands.csv.gz'
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == data['raw_sha256']
    model = ROOT/'poker_lab/pokerlab/research/blueprints.json'
    assert hashlib.sha256(model.read_bytes()).hexdigest() == data['blueprint_sha256']
    units = defaultdict(lambda: defaultdict(dict)); seen = set(); count = 0
    with gzip.open(raw, 'rt') as stream:
        for row in csv.DictReader(stream):
            key = (row['protocol'], row['candidate'], row['opponent'])
            deal, seat = int(row['deal']), int(row['seat'])
            identity = (*key, deal, seat)
            assert identity not in seen; seen.add(identity)
            units[key][deal][seat] = float(row['hero_net_bb'])*100
            count += 1
    assert count == data['total_hands'] == 192500
    averaged = {}
    for key, deals in units.items():
        expected = 6 if key[0] == 'six_max' else 2
        assert all(len(seats) == expected for seats in deals.values())
        averaged[key] = {d: float(np.mean(list(seats.values()))) for d, seats in deals.items()}
    def check_interval(values, row):
        a = np.asarray(values); mean = a.mean()
        error = student.ppf(.975, len(a)-1)*a.std(ddof=1)/np.sqrt(len(a))
        np.testing.assert_allclose([mean, mean-error, mean+error],
            [row['bb100'], row['ci95_low'], row['ci95_high']], atol=1e-9)
        assert len(a) == row['independent_deals']
    for row in data['matchups']:
        key = (row['protocol'], row['candidate'], row['opponent'])
        check_interval(list(averaged[key].values()), row)
    for row in data['field_aggregate']:
        values, differences = [], []
        for opponent in ('S08', 'S18', 'S23', 'S33'):
            current = averaged[('field', row['candidate'], opponent)]
            baseline = averaged[('field', 'S55', opponent)]
            values.extend(current.values())
            differences.extend(current[d]-baseline[d] for d in current)
        check_interval(values, row)
        check_interval(differences, row['paired_difference_vs_s55'])
    return averaged


def main():
    TABLES.mkdir(exist_ok=True); FIGURES.mkdir(exist_ok=True)
    data = json.loads((RESULTS/'benchmark.json').read_text())
    initial = json.loads((RESULTS/'screening_v1/benchmark.json').read_text())
    papers = json.loads((HERE/'papers.json').read_text())
    convergence = json.loads((RESULTS/'convergence.json').read_text())
    model = json.loads((ROOT/'poker_lab/pokerlab/research/blueprints.json').read_text())
    audit(data)
    rows = data['field_aggregate']
    table('field.tex', r'Option & Mean [95\% CI], bb/100 & Paired change vs S55 [95\% CI]',
        [(sid+' '+NAMES[sid], ci(row), '--' if sid == 'S55' else ci(row['paired_difference_vs_s55']))
         for row in rows for sid in [row['candidate']]], 'lrr')
    summaries = []
    for sid, name in NAMES.items():
        matchups = [r for r in data['matchups'] if r['protocol']=='field' and r['candidate']==sid]
        research = sum(r['policy_modes'].get('research_blueprint', 0) for r in matchups)
        decisions = sum(sum(r['policy_modes'].values()) for r in matchups)
        summaries.append({'candidate': sid, 'decisions': decisions, 'blueprint_decisions': research,
            'blueprint_fraction': research/decisions,
            'max_matchup_p95_ms': max(r['decision_p95_ms'] for r in matchups),
            'max_blueprint_p95_ms': max((r['blueprint_p95_ms'] or 0) for r in matchups)})
    (RESULTS/'latency_coverage.json').write_text(json.dumps(summaries, indent=2)+'\n')
    table('latency.tex', r'Option & Paper lookup share & Max. matchup p95 (ms) & Lookup p95 (ms)',
          [(r['candidate'], f"{r['blueprint_fraction']:.1%}".replace('%', r'\%'),
            f"{r['max_matchup_p95_ms']:.3f}", '--' if not r['blueprint_decisions'] else f"{r['max_blueprint_p95_ms']:.3f}")
           for r in summaries], 'lrrr')
    table('sixmax.tex', r'Option & Six-player mean [95\% CI], bb/100 & Paper lookup share',
        [(r['candidate'], ci(r), f"{r['research_lookup_fraction']:.1%}".replace('%',r'\%'))
         for r in data['matchups'] if r['protocol']=='six_max'], 'lrr')
    table('operations.tex', r'Option & Six-player bb/100 [95\% CI] & HU lookup & Policy p95 & Lookup p95',
        [(s['candidate'], ci(next(r for r in data['matchups'] if r['protocol']=='six_max' and r['candidate']==s['candidate'])),
          f"{s['blueprint_fraction']:.1%}".replace('%',r'\%'), f"{s['max_matchup_p95_ms']:.3f}",
          '--' if not s['blueprint_decisions'] else f"{s['max_blueprint_p95_ms']:.3f}") for s in summaries], 'lrrrr')
    last = [r for r in convergence['rows'] if r['iterations']==(30000 if r['algorithm']=='mccfr' else 3000)]
    table('kuhn.tex', r'Option & Iterations & $u_0$ & Exploitability & Seconds',
          [(ALGO_IDS[r['algorithm']], r['iterations'], f"{r['value_p0']:.7f}",
            f"{r['exploitability']:.2e}", f"{r['training_seconds']:.2f}") for r in last], 'lrrrr')
    table('abstract.tex', r'Option & Iterations & Exploitability / initial pot & $u_0$ / initial pot',
        [(ALGO_IDS[a], model['blueprints'][a+':4:0']['iterations'],
          f"{model['blueprints'][a+':4:0']['abstract_metrics']['exploitability']:.3g}",
          f"{model['blueprints'][a+':4:0']['abstract_metrics']['value_p0']:.5f}") for a in ALGO_IDS], 'lrrr')
    table('initial.tex', r'Option & Initial mean & Initial paired change vs S55 & Revised mean',
        [(r['candidate'], f"{r['bb100']:+.2f}",
          f"{r['paired_difference_vs_s55']['bb100']:+.2f}",
          f"{next(v['bb100'] for v in rows if v['candidate']==r['candidate']):+.2f}") for r in initial['field_aggregate']], 'lrrr')

    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'savefig.dpi': 180, 'font.family': 'DejaVu Sans'})
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.6), layout='constrained')
    for index, row in enumerate(rows):
        mean, lo, hi = row['bb100'], row['ci95_low'], row['ci95_high']
        axes[0].errorbar(mean, index, xerr=[[mean-lo],[hi-mean]], fmt='o', capsize=3,
                         color='#147d92' if row['candidate']=='S55' else '#5266ab')
        if index:
            delta = row['paired_difference_vs_s55']; mean=delta['bb100']
            axes[1].errorbar(mean, index, xerr=[[mean-delta['ci95_low']],[delta['ci95_high']-mean]],
                             fmt='o', capsize=3, color='#bb6047')
    for ax in axes:
        ax.axvline(0, color='#8b9199', lw=1); ax.set_yticks(range(7), [f'{k} {v}' for k,v in NAMES.items()])
        ax.invert_yaxis(); ax.grid(axis='x', alpha=.18); ax.set_xlabel('Big blinds per 100 hands')
    axes[0].set_title('Fixed-opponent field: mean ± 95% CI')
    axes[1].set_title('Paired difference from S55')
    fig.savefig(FIGURES/'field.png'); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.7, 3.5), layout='constrained')
    for algorithm in ALGO_IDS:
        curve = [r for r in convergence['rows'] if r['algorithm']==algorithm]
        ax.loglog([r['iterations'] for r in curve], [max(1e-15,r['exploitability']) for r in curve],
            marker='o', markersize=3, label=ALGO_IDS[algorithm]+' '+NAMES[ALGO_IDS[algorithm]])
    ax.set(xlabel='Training iterations (MCCFR uses 10× the final budget)',
        ylabel='Exact Kuhn exploitability', title='Correctness in the solved three-card game')
    ax.grid(alpha=.2); ax.legend(ncol=3, fontsize=8)
    fig.savefig(FIGURES/'convergence.png'); plt.close(fig)
    labels = list(NAMES); matrix = np.full((7, 7), np.nan)
    for row in data['matchups']:
        if row['protocol']=='round_robin':
            i,j=labels.index(row['candidate']),labels.index(row['opponent'])
            matrix[i,j]=row['bb100']; matrix[j,i]=-row['bb100']
    fig, ax = plt.subplots(figsize=(7.4, 4.4), layout='constrained')
    cmap = plt.get_cmap('RdBu').copy(); cmap.set_bad('#eef0f3')
    limit = float(np.nanmax(abs(matrix)))
    im=ax.imshow(np.ma.masked_invalid(matrix), cmap=cmap, vmin=-limit, vmax=limit)
    ax.set_xticks(range(7), labels); ax.set_yticks(range(7), labels)
    ax.set(xlabel='Opponent', ylabel='Candidate', title='Round robin: row player net bb/100 (exploratory)')
    for i,j in product_indices(7):
        ax.text(j,i,'—' if i==j else f'{matrix[i,j]:+.1f}',ha='center',va='center',
                color='white' if i!=j and abs(matrix[i,j])>.7*limit else '#29313f',fontsize=9)
    fig.colorbar(im, ax=ax, label='bb/100'); fig.savefig(FIGURES/'round_robin.png'); plt.close(fig)

    bibliography = ['\\begin{thebibliography}{99}']
    bibtex = []
    catalog = ['# Poker AI reading list', '', 'Snapshot: '+papers['retrieved_at_utc'][:10]+'. '+papers['citation_source'], '',
        'Citation counts measure indexed impact, not playing strength. Missing counts are not zero.', '',
        '| Paper | Year | Citations | In PokerLab |', '|---|---:|---:|---|']
    for paper in papers['papers']:
        authors = ' and '.join(paper.get('authors',[]))
        bibliography.append('\\bibitem{'+paper['id']+'} '+tex(authors)+'. \\emph{'+tex(paper['title'])+'}. '+str(paper['year'])+'. \\url{'+paper['primary_url']+'}.')
        bibtex.append('@misc{'+paper['id']+',\n  title={'+paper['title']+'},\n  author={'+authors+'},\n  year={'+str(paper['year'])+'},\n  url={'+paper['primary_url']+'}\n}\n')
        count = paper['citation_count'] if paper['citation_count'] is not None else 'Unavailable'
        catalog.append(f"| [{paper['title']}]({paper['primary_url']}) | {paper['year']} | {count} | {paper['option'] or 'Reading only'} |")
    bibliography.append('\\end{thebibliography}')
    (HERE/'references.tex').write_text('\n\n'.join(bibliography)+'\n')
    (HERE/'papers.bib').write_text('\n'.join(bibtex))
    catalog += ['', '## What to read first', '',
        'Start with CFR → CFR+ → discounted/predictive CFR. These teach the trainable algorithms implemented here. Read DeepStack and Libratus for heads-up search and range handling; read Pluribus for six-player play. Read Deep CFR/ReBeL/Student of Games for larger learned value and search systems.', '',
        'For recent developments, PDCFR+ (IJCAI 2024) is already available as R06 in the reduced game. DDCFR (ICLR 2024), SpinGPT (2025 preprint), Deep (Predictive) DCFR (AAAI 2026) and Parallel CFR (2026 preprint) are research leads, not reproduced agents. SpinGPT also has a 2026 indexed proceedings record; the catalog uses its 2025 preprint date.', '',
        'OpenAlex can split proceedings, repositories and preprints. Counts here use one verified record per paper and are not a complete citation audit. CFR and MCCFR matched institutional records; their counts may especially understate total impact. DDCFR is unavailable because a fuzzy match returned an unrelated paper and was rejected. The Libratus issue year is 2018 although its online record is 2017.', '',
        'The implementation notes and evaluation are in [README.md](README.md).']
    (HERE/'READING_LIST.md').write_text('\n'.join(catalog)+'\n')
    print('Audited 192,500 raw hands and rebuilt research tables, figures and bibliography.')


def product_indices(n):
    return ((i,j) for i in range(n) for j in range(n))


if __name__ == '__main__':
    main()
