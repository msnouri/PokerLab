"""Readable report, plots, paired uncertainty, latency, and default bot config."""
from pathlib import Path
from dataclasses import asdict
import base64,csv,json,html,io,random,time,itertools
import numpy as np
from scipy.stats import t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .strategies import all_strategies,baseline_strategies,FAMILIES
from .experiment import ROOT,RESULTS,ci,write_csv
from .engine import play_hand
from .agent import Agent,Observation,equity


def read(name):return list(csv.DictReader((RESULTS/name).open()))
def f(x):return float(x)
def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'


def latency_test(strategy):
    observations=[]
    for h in range(100):
        r=play_hand([strategy]+baseline_strategies(),[2000]*8,20,63001111+h,trace=True)
        observations.extend(Observation(**o) for o in r['observations'])
    a=Agent(strategy);warm=[];cold=[]
    # Initialization and legal-state conversion excluded. No process workers.
    for o in observations:
        equity.cache_clear()
        start=time.perf_counter_ns();a.decide(o,.51);cold.append(time.perf_counter_ns()-start)
        start=time.perf_counter_ns();a.decide(o,.51);warm.append(time.perf_counter_ns()-start)
    result={}
    for name,values in [('cold_equity_cache',cold),('warm_equity_cache',warm)]:
        result[name]={'decisions':len(values),'p50_ms':float(np.percentile(values,50)/1e6),
                      'p99_ms':float(np.percentile(values,99)/1e6),
                      'p999_ms':float(np.percentile(values,99.9)/1e6),
                      'max_ms':max(values)/1e6,'over_1ms':sum(v>1000000 for v in values)}
    result['postflop_decisions']=sum(bool(o.board) for o in observations)
    (RESULTS/'latency.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    strategies={s.id:s for s in all_strategies()}
    screen=read('screening.csv');league=read('selfplay.csv');valid=read('validation.csv')
    tour=read('tournaments.csv');detail=read('tournament_tables.csv')
    ids=sorted(set(r['strategy'] for r in tour))
    seeds=sorted(set(int(r['seed']) for r in detail))
    lookup={(r['strategy'],r['field'],int(r['seed'])):float(r['points']) for r in detail}
    matrix={sid:np.array([np.mean([lookup[sid,field,seed] for field in ['mixed','tight','aggressive']]) for seed in seeds]) for sid in ids}
    ranked=sorted(ids,key=lambda sid:-matrix[sid].mean());winner=ranked[0]
    combined=[]
    for sid in ranked:
        lo,hi=ci(matrix[sid])
        combined.append(dict(strategy=sid,family=strategies[sid].family,
                             average_points=float(matrix[sid].mean()),ci95_low=lo,ci95_high=hi,
                             tables_per_field=len(seeds),fields=3))
    write_csv(RESULTS/'tournament_overall.csv',combined)
    pair=[];comparisons=len(ids)*(len(ids)-1)//2
    for sid in ranked[1:]:
        diff=matrix[winner]-matrix[sid];se=diff.std(ddof=1)/np.sqrt(len(diff))
        bound=t.ppf(1-.05/(2*comparisons),len(diff)-1)*se
        pair.append(dict(leader=winner,challenger=sid,mean_difference=float(diff.mean()),
                         simultaneous95_low=float(diff.mean()-bound),
                         simultaneous95_high=float(diff.mean()+bound),
                         comparisons_corrected=comparisons))
    write_csv(RESULTS/'paired_tournament_comparisons.csv',pair)
    winner_s=strategies[winner]
    latency=latency_test(winner_s)
    config={'strategy':winner,'family':winner_s.family,'label':winner_s.label,
            'selection':'highest equally weighted mean tournament points across three synthetic opponent fields',
            'status':'research candidate; not an official event submission',
            'parameters':asdict(winner_s)}
    (ROOT/'best_strategy.json').write_text(json.dumps(config,indent=2)+'\n')
    (ROOT/'baseline_fields.json').write_text(json.dumps({field:[asdict(s) for s in baseline_strategies(field)] for field in ['mixed','tight','aggressive']},indent=2)+'\n')
    # Example input is an observation that really occurred, with no hidden cards.
    sample=play_hand([winner_s]+baseline_strategies(),[2000]*8,20,2009,trace=True)['observations'][0]
    (ROOT/'example_observation.jsonl').write_text(json.dumps(sample)+'\n')

    # Scientific plot; show uncertainty rather than a decorative ranking alone.
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(13.6,5.2),layout='constrained')
    for ax,rows,title in [(axes[0],screen[:8],'Initial 500-hand gauntlet'),(axes[1],valid[:8],'Fresh 2,000-hand validation')]:
        vals=np.array([f(r['bb_per_100']) for r in rows]);low=np.array([f(r['ci95_low']) for r in rows]);high=np.array([f(r['ci95_high']) for r in rows])
        ax.errorbar(vals,np.arange(len(rows)),xerr=[vals-low,high-vals],fmt='o',color='#176b78',capsize=3)
        ax.set_yticks(np.arange(len(rows)),[r['strategy']+' '+strategies[r['strategy']].family for r in rows])
        ax.invert_yaxis();ax.axvline(0,color='#aeb7be',lw=1);ax.set_xlabel('Big blinds / 100 hands (95% intervals)');ax.set_title(title,loc='left',fontweight='bold');ax.grid(axis='x',alpha=.15)
    fig.savefig(RESULTS/'chip_comparison.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,5.4),layout='constrained')
    colors=['#176b78','#d69637','#9377ad']
    for fi,field in enumerate(['mixed','tight','aggressive']):
        rs=[next(r for r in tour if r['strategy']==sid and r['field']==field) for sid in ranked]
        vals=np.array([f(r['mean_points']) for r in rs]);lows=np.array([f(r['ci95_low']) for r in rs]);highs=np.array([f(r['ci95_high']) for r in rs])
        ax.errorbar(vals,np.arange(len(rs))+(fi-1)*.20,xerr=[vals-lows,highs-vals],fmt='o',label=field,color=colors[fi],capsize=2,markersize=4)
    ax.set_yticks(range(len(ranked)),[sid+' '+strategies[sid].family for sid in ranked]);ax.invert_yaxis();ax.axvline(12.5,color='#9ba4ad',ls='--',label='Equal share of 100 points')
    ax.set_xlabel(f'Mean simulated points / table ({len(seeds)} tables per field; 95% intervals)');ax.set_title('Tournament results depend on the opponent field',loc='left',fontweight='bold');ax.legend(loc='lower right',fontsize=8);ax.grid(axis='x',alpha=.15)
    fig.savefig(RESULTS/'tournament_comparison.png',dpi=160);plt.close(fig)

    sv={r['strategy']:r for r in valid};screenleader=screen[0]['strategy']
    total_screen=sum(int(r['hands']) for r in screen)
    total_league=sum(int(r['hands']) for r in league)
    total_valid=sum(int(r['hands']) for r in valid)
    total_tables=len(detail);total_tour_hands=sum(int(r['hands']) for r in detail)
    proven=all(r['simultaneous95_low']>0 for r in pair)
    summary={'screening_player_hands':total_screen,'selfplay_player_hands':total_league,
             'selfplay_table_hands':total_league//8,'validation_player_hands':total_valid,
             'validation_candidates':len(valid),'tournament_tables':total_tables,
             'tournament_table_hands':total_tour_hands,'screening_leader':screenleader,
             'selfplay_leader':league[0]['strategy'],'validation_leader':valid[0]['strategy'],
             'tournament_leader':winner,'tournament_leader_mean_points':combined[0]['average_points'],
             'clearly_above_all_finalists_on_simultaneous_intervals':proven}
    (RESULTS/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

    def image_tag(name):
        data=base64.b64encode((RESULTS/name).read_bytes()).decode()
        return f'<img alt="{name.replace("_"," ")}" src="data:image/png;base64,{data}">'
    families=[]
    for i,(name,label,source,params) in enumerate(FAMILIES):
        families.append([f'S{i*5+1:02d}-S{i*5+5:02d}',label,source])
    rows=[]
    for r in combined:
        sid=r['strategy'];fieldrows={a['field']:a for a in tour if a['strategy']==sid}
        rows.append([sid,strategies[sid].family,f"{r['average_points']:.2f}",
                    f"{r['ci95_low']:.2f} to {r['ci95_high']:.2f}"]+
                    [f"{f(fieldrows[field]['mean_points']):.2f}" for field in ['mixed','tight','aggressive']])
    source_rows=[
      ['Phil Hellmuth Jr., Play Poker Like the Pros','EPUB ch.3-4 and 6; ch.7 for tournament context','Starting-hand discipline, opponent tendencies, selective aggression and traps. Limit advice is explicitly adapted, not transferred verbatim.'],
      ['Andrew Brokos, Play Optimal Poker 2: Range Construction','Ch.1-6; ch.11 pp.304,315-318 (PDF pp.313,324-327)','Equity realization, mixed ranges, protection, semi-bluffs, pot control, leverage, shallow stacks and nonlinear tournament chip value.'],
      ['Philip N. Dangel, Poker Poker','Ch.5-8, especially printed pp.132-134,163-164,192-193 (PDF pp.130-132,161-162,190-191)','General expected-value and betting concepts adapted from predominantly high-low/limit examples. Historical variant-specific odds were not reused.'],
      ['Carol Lynne, Slow-Play (Poker Night 2)','PDF pp.3-7','Fiction, not a poker instruction manual. Excluded from strategy generation.']]
    text=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Poker Strategy Lab - Results</title>
<style>body{{margin:0;background:#edf2f4;color:#182a35;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;background:white;padding:54px 64px}}h1{{font-size:42px;line-height:1.12;letter-spacing:-1px;margin:12px 0 22px}}h2{{margin-top:42px;font-size:25px;border-top:1px solid #dce5e9;padding-top:25px}}h3{{font-size:19px}}.eyebrow{{color:#176b78;letter-spacing:2px;text-transform:uppercase;font-weight:700;font-size:12px}}.lead{{font-size:21px;max-width:900px}}.callout{{background:#eaf4f3;border-left:4px solid #176b78;padding:18px 24px;margin:24px 0}}.note{{background:#fff6e6;border-left:4px solid #d69637;padding:16px 22px}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.stat{{background:#f2f6f8;padding:16px;font-size:13px}}.stat b{{display:block;font-size:27px;color:#176b78}}table{{border-collapse:collapse;width:100%;font-size:13px;margin:20px 0}}th{{background:#eaf0f3;text-align:left}}td,th{{padding:10px 12px;border-bottom:1px solid #dce5e9;vertical-align:top}}img{{width:100%;height:auto}}code,pre{{background:#f1f4f6;font:13px/1.6 ui-monospace,monospace}}pre{{padding:18px;overflow:auto}}a{{color:#176b78}}.muted{{font-size:13px;color:#5c707c}}li{{margin:8px 0}}@media(max-width:720px){{main{{padding:24px 18px}}h1{{font-size:32px}}.stats{{grid-template-columns:repeat(2,1fr)}}table{{font-size:11px}}td,th{{padding:6px}}}}</style>
<main><div class="eyebrow">Offline simulation / November 11, 2026</div><h1>80 poker policies.<br>Tested, not assumed.</h1>
<p class="lead">A working Python poker agent laboratory built from selected concepts in your books, with reproducible hands, fresh validation and tournament evaluation.</p>
<div class="stats"><div class="stat"><b>80</b>policies in 16 families</div><div class="stat"><b>500</b>hands each in direct self-play</div><div class="stat"><b>500</b>matched gauntlet hands each</div><div class="stat"><b>{total_tables:,}</b>eight-player tournaments</div></div>
<div class="callout"><strong>Research candidate: {winner} - {html.escape(winner_s.label)}.</strong> It has the highest average tournament score across three synthetic fields: {combined[0]['average_points']:.2f} points per table. {'The corrected paired intervals separate it from every tested finalist in this experiment.' if proven else 'The corrected paired intervals do not establish that it is stronger than every tested finalist.'} This is a candidate for further testing, not a universal best strategy.</div>
<p>The initial matched-opponent leader, <strong>{screenleader}</strong>, earned {f(screen[0]['bb_per_100']):.2f} big blinds per 100 hands over 500 hands. On fresh deals it earned {f(sv[screenleader]['bb_per_100']):.2f}. Direct self-play instead favored {league[0]['strategy']}; fresh validation favored {valid[0]['strategy']}. Ranking by one short run is unreliable.</p>
<h2>What the books actually supplied</h2><p>I extracted the text from all four attachments, identified their contents and reviewed the relevant instructional sections. The numerical policies are original experimental approximations inspired by those concepts. They are not 80 complete author-prescribed strategies, and no claim is made that these implementations reproduce the authors' full play.</p>
{table(['Attachment','Reviewed sections','Use in this project'],source_rows)}
<h2>The 80 candidates</h2><p>Each family has five variants. Relative to its central variant, the variants change preflop opening width, value thresholds, calling margin and bet size; eligible bluff frequencies and tournament risk margins also change. This structured sweep tests packages of parameters, so it cannot attribute a result to a single parameter. All numerical settings are in <code>strategies.csv</code>.</p>
{table(['IDs','Mechanism','Concept attribution'],families)}
<h2>Chip results and uncertainty</h2>{image_tag('chip_comparison.png')}
<p>Units are big blinds won per 100 hands. A positive result against these original heuristic opponents is not a prediction of profit elsewhere. Error bars are ordinary two-sided Student-t intervals for the mean. They do not adjust the 80-way initial ranking for selection, so initial leaders are especially vulnerable to winner's curse.</p>
<h2>Tournament evaluation</h2>{table(['ID','Family','Average points','95% interval','Mixed','Tight','Aggressive'],rows)}
{image_tag('tournament_comparison.png')}
<p>Every finalist played {len(seeds)} tables per field. The overall average weights fields equally. Its interval treats each matched seed's average across the three fields as one observation, retaining cross-field dependence. The paired comparisons use matched seeds and a Bonferroni correction covering all {comparisons} finalist pairs. The 12.5-point line is an equal share of the 100 available points, not the expected performance of any particular baseline.</p>
{table(['Leader vs.','Mean point difference','Simultaneous 95% interval'],[[r['challenger'],f"{r['mean_difference']:.2f}",f"{r['simultaneous95_low']:.2f} to {r['simultaneous95_high']:.2f}"] for r in pair])}
<h2>Experimental design</h2><ol>
<li><strong>Direct self-play:</strong> all 80 candidates play 500 hands each ({total_league:,} player-hands; {total_league//8:,} table-hands). Random groups of eight are redrawn every eight hands; seats rotate across the block. Stacks reset to 2,000 each hand, with blinds 10/20.</li>
<li><strong>Matched gauntlet:</strong> each candidate plays 500 hands against the same seven baseline policies ({total_screen:,} table-hands). All candidates use the same 500 shuffled deals. The candidate rotates seats; each seat occurs 62 or 63 times. Opponents cannot see the candidate's identity or cards.</li>
<li><strong>Fresh validation:</strong> the top eight from each initial test plus the best representative of each family produce {len(valid)} unique candidates. Each plays 2,000 new matched gauntlet hands ({total_valid:,} table-hands). These results select eight tournament finalists, so this phase is model selection, not untouched final confirmation.</li>
<li><strong>Tournaments:</strong> finalists play persistent-stack sit-and-gos against three baseline fields, for {total_tables:,} tables and {total_tour_hands:,} table-hands. Starts: 2,000 chips, blinds 10/20. Big blinds: 20,30,40,60,100,150,200,300; levels last 25 hands; cap 200 hands. Assumed points: 50/30/20 for the top three. Survivors at the cap receive exact ICM expected points for the remaining finishing places. Simultaneous eliminations use starting-hand stacks, splitting exact ties.</li>
</ol><p>Deck, policy randomization and equity-sampling seeds are separate. Only hole cards belonging to the acting player, exposed board cards, legal bet bounds and public action statistics enter the policy. PokerKit handles game legality and settlement. Every simulated hand checks chip conservation. Invalid agent actions raise errors rather than silently becoming valid actions.</p>
<h2>What the agent computes</h2><p>Preflop: a 169-class table, generated with 4,000 seeded deals per class against one through seven uniformly random opponents. Opening percentiles weight the 1,326 distinct two-card combinations. Postflop: 48 sampled runouts and opponent holdings, excluding the player's cards and public board, with a weak smoothing prior. Draw, board texture, position, pot odds, stack depth and public betting pressure modify decisions.</p>
<p>This is a family of heuristic agents. The postflop estimator does not infer full conditional opponent ranges, and the polarized policy is not a GTO solution. Continuation betting, semi-bluffing and trapping are simple rules rather than multi-street search. ICM is exact for cap scoring; decisions use a small risk-margin approximation rather than full ICM action optimization. Opponent models see within-hand actions in reset-stack tests, and accumulate only within a table in tournament tests.</p>
<h2>Competition fit and remaining work</h2><div class="note"><strong>This is a working research bot, not a verified event submission.</strong> The official event reveals its variant and Agent interface at the build phase. Ordinary two-card no-limit Hold'em, the full blind schedule and the 50/30/20 payout are our stated research assumptions.</div>
<p>The official rules describe eight-bot sit-and-gos, a 200-hand cap, 2,000-chip starts, 10/20 starting blinds and 25-hand levels. They require isolated offline bots and decisions within 1 ms. They score finishing position and ICM, rather than cash-style chip profit. The event has a 60-minute build phase. See the <a href="https://pokerbot.sequoiacap.com/rules.html">official rules, sections 3-4</a>. The <a href="https://pokerbot.sequoiacap.com/">homepage</a> currently marks applications closed.</p>
<p>Before entering a similar event: plug in its actual rules, payout schedule and SDK; adapt card evaluation if the variant changes; measure latency inside its sandbox; replace random-hand equity with a stronger public-action-conditioned range model; and confirm the chosen policy on untouched seeds and unfamiliar opponents. No participant repository was copied. The project uses general-purpose open-source PokerKit and eval7 dependencies.</p>
<h3>Measured decision time</h3><p>Isolated measurements of {latency['cold_equity_cache']['decisions']:,} decisions ({latency['postflop_decisions']} postflop), with asset initialization and observation conversion excluded:</p>
{table(['Equity cache','Median ms','99th percentile ms','99.9th percentile ms','Maximum ms','Over 1 ms'],[[name,f"{v['p50_ms']:.4f}",f"{v['p99_ms']:.4f}",f"{v['p999_ms']:.4f}",f"{v['max_ms']:.4f}",v['over_1ms']] for name,v in latency.items() if isinstance(v,dict)])}
<p>Research matches record time but do not enforce deadline folds. Cached repeated states are faster, so the cold-cache column is the more useful one. Host scheduling, SDK conversion, imports, Python runtime and sandbox limits can change these times; these measurements do not certify the event's deadline.</p>
<h2>Run it yourself</h2><pre>python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m pokerlab.experiment --stage all --hands 500 --validation-hands 2000 --tables 128 --workers 8
python -m pokerlab.analyze
python -m pokerlab.bot &lt; example_observation.jsonl</pre>
<p>The JSON-lines bot defaults to {winner}. Choose any candidate with <code>--strategy S01</code> through <code>--strategy S80</code>. Its input schema is the <code>Observation</code> dataclass in <code>pokerlab/agent.py</code>. This neutral interface must be mapped to the competition SDK.</p>
<h2>Deliverables and audit trail</h2><ul><li><code>strategies.csv</code>: all 80 policies and exact parameters.</li><li><code>pokerlab/</code>: source, simulation runner, equity asset generator, analysis and JSON bot.</li><li><code>results/*_hands.csv</code> and <code>tournament_tables.csv</code>: per-hand or per-table outcomes, seeds and seats.</li><li><code>results/tournament_overall.csv</code> and <code>paired_tournament_comparisons.csv</code>: rankings and uncertainty.</li><li><code>tests/test_core.py</code>: eight tests covering registry uniqueness, equity sanity, determinism, privacy, independent evaluator agreement, exact side pots/ties, ICM and all strategies on unequal short stacks.</li><li><code>results/manifest.json</code>: configuration, software versions and source hashes. Absolute wall times and latency are host dependent; decision outcomes are seeded.</li></ul>
<p>General-purpose repositories: <a href="https://github.com/uoftcprg/pokerkit">PokerKit</a>, <a href="https://github.com/JulianAndrews/pyeval7">eval7</a>, and <a href="https://github.com/ihendley/treys">Treys</a> (independent evaluator tests only). Dependency licenses are recorded in <code>THIRD_PARTY_NOTICES.txt</code>. The package does not include the uploaded books or their extracted full text.</p>
<p class="muted">Interpretation: these tests compare our implementations in a documented synthetic environment. They cannot establish which book is best, whether a strategy is unexploitable, or whether it will win a competition.</p></main></html>'''
    (ROOT/'Poker_Strategy_Report.html').write_text(text)
    print(json.dumps(summary,indent=2));print('Latency:',json.dumps(latency))


if __name__=='__main__':main()
