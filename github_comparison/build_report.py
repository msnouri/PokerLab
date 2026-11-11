from pathlib import Path
import csv,json,base64,html,io,sys
import numpy as np
from scipy.stats import t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
def read(name):return list(csv.DictReader((ROOT/name).open()))
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def main():
    cash=read('cash_results.csv');tour=read('tournament_results.csv')
    handrows=read('cash_hands.csv');tablerows=read('tournament_tables.csv')
    ids=[f'neuron_equity_{i}_{i+1}' for i in range(1,7)]+['neuron_random']
    label={sid:(f'Equity {int(sid.split("_")[-2])/10:.1f} / {int(sid.split("_")[-1])/10:.1f}' if sid!='neuron_random' else 'Random') for sid in ids}
    simultaneous=[]
    for row in cash+tour:
        n=int(row.get('independent_deals',row.get('tables')))
        mean=float(row.get('s55_bb100',row.get('s55_points_per_bot')))
        se=(float(row['ci95_high'])-mean)/t.ppf(.975,n-1)
        err=t.ppf(1-.05/(2*21),n-1)*se
        simultaneous.append({'opponent':row['opponent'],'protocol':row['protocol'],
                             'estimate':mean,'simultaneous95_low':mean-err,'simultaneous95_high':mean+err,
                             'reference':12.5 if row['protocol']=='eight_player_tournament' else 0.})
    with (ROOT/'simultaneous_intervals.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(simultaneous[0]));w.writeheader();w.writerows(simultaneous)
    lookup={(r['opponent'],r['protocol']):r for r in cash}
    tr={r['opponent']:r for r in tour}
    def score(r,key):return f"{float(r[key]):+.2f}" if key=='s55_bb100' else f"{float(r[key]):.2f}"
    rows=[[label[sid],score(lookup[sid,'heads_up'],'s55_bb100'),score(lookup[sid,'eight_player_cash'],'s55_bb100'),score(tr[sid],'s55_points_per_bot')] for sid in ids]
    fig,axes=plt.subplots(1,2,figsize=(13,5.2),layout='constrained')
    y=np.arange(len(ids))
    for ax,protocol,title,reference in [(axes[0],'heads_up','Heads-up reset-stack play',0),(axes[1],'eight_player_tournament','Eight-player sit-and-gos',12.5)]:
        rs=[next(r for r in simultaneous if r['opponent']==sid and r['protocol']==protocol) for sid in ids]
        vals=np.array([r['estimate'] for r in rs]);low=np.array([r['simultaneous95_low'] for r in rs]);high=np.array([r['simultaneous95_high'] for r in rs])
        ax.errorbar(vals,y,xerr=[vals-low,high-vals],fmt='o',capsize=3,color='#176b78')
        ax.axvline(reference,color='#c27b30',ls='--');ax.set_yticks(y,[label[sid] for sid in ids]);ax.invert_yaxis();ax.set_title(title,loc='left',fontweight='bold');ax.grid(axis='x',alpha=.15)
        ax.set_xlabel('S55 big blinds / 100 hands' if reference==0 else 'S55 mean points per bot (parity = 12.5)')
    fig.savefig(ROOT/'external_comparison.png',dpi=160);plt.close(fig)
    encoded=base64.b64encode((ROOT/'external_comparison.png').read_bytes()).decode()
    repositories=[
     ['uoftcprg','Organization: PokerKit, NoRegret, data and other tools','Our simulator already uses PokerKit. NoRegret is a solver framework; its examples include Kuhn/Leduc. Neither is a single trained eight-player opponent. No win/loss ranking applies to an organization.','https://github.com/uoftcprg'],
     ['apehex/awesome-poker','Curated resource list','Useful for finding candidates, not itself a runnable poker policy. Listed projects span different games and access conditions.','https://github.com/apehex/awesome-poker'],
     ['HarperJonesGPT/PokerGPT','Six-player cash-game assistant using GPT-4 API and screen/OCR interaction','Source confirms a live chat-completions call. It cannot run as written in the offline event sandbox. No match played; playing strength versus S55 remains unknown.','https://github.com/HarperJonesGPT/PokerGPT/blob/master/poker_assistant.py'],
     ['masterai-top/cfr-poker-ai-masterai','Heads-up no-limit CFR/ReBeL-style research stack','Inspected source and configuration, not benchmarked. Deploy configuration points to ./weights/value_net.net, absent in the inspected complete tree. Two regret files exist, but their presence does not provide a verified ready-to-play policy. Its benchmark documentation marks headline win rates as unreproduced project reports.','https://github.com/masterai-top/cfr-poker-ai-masterai/blob/main/BENCHMARKS.md'],
     ['dickreuter/neuron_poker','Training environment, example equity policies, DQN implementation','Tested random and six equity settings through an adapter. The DQN loader expects architecture JSON and .h5 weights; no trained weight files were found in the inspected repository tree. No trained DQN was tested.','https://github.com/dickreuter/neuron_poker/blob/master/agents/agent_keras_rl_dqn.py'],
     ['GitHub topics/poker-game','Discovery page containing many projects','Not a model or a reproducible opponent selection. The listed repositories include engines and user interfaces as well as AI projects. No single win/loss ranking applies.','https://github.com/topics/poker-game'],
    ]
    inv=json.loads((ROOT/'review_inventory.json').read_text())
    pinned=[[name,item['branch'],item['tree_sha'],len(item['files'])] for name,item in inv.items()]
    total_tour_hands=sum(int(r['hands']) for r in tablerows)
    corrected_tour=[r for r in simultaneous if r['protocol']=='eight_player_tournament']
    summary={'s55_frozen':True,'external_pretrained_models_tested':0,
             'upstream_example_policy_configurations_tested':7,
             'heads_up_table_hands':70000,'eight_player_cash_table_hands':35000,
             'eight_player_tournament_tables':len(tablerows),'tournament_table_hands':total_tour_hands,
             'all_tournament_simultaneous_intervals_above_parity':all(r['simultaneous95_low']>12.5 for r in corrected_tour),
             'conclusion':'S55 beats these adapted policies in the tested eight-player tournaments, but loses to aggressive examples in heads-up cash; no evidence of superiority over trained DQN/CFR models.'}
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    repo_html=''.join(f'<tr><td><a href="{r[3]}">{html.escape(r[0])}</a></td><td>{html.escape(r[1])}</td><td>{html.escape(r[2])}</td></tr>' for r in repositories)
    content=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Poker agent: GitHub comparison</title>
<style>body{{margin:0;background:#eef3f5;color:#18313c;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:52px 60px;background:#fff}}h1{{font-size:40px;line-height:1.15;letter-spacing:-1px}}h2{{font-size:25px;border-top:1px solid #dbe5e9;padding-top:24px;margin-top:38px}}.tag{{font-size:12px;letter-spacing:2px;color:#176b78;text-transform:uppercase;font-weight:700}}.lead{{font-size:21px}}.callout{{background:#eaf4f3;padding:20px;border-left:4px solid #176b78}}.warning{{background:#fff4e5;padding:20px;border-left:4px solid #bf8137}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:11px;border-bottom:1px solid #dbe5e9;text-align:left;vertical-align:top}}th{{background:#edf3f5}}.scroll{{overflow:auto;margin:22px 0}}a{{color:#176b78}}img{{width:100%;height:auto}}pre{{overflow:auto;background:#f1f5f7;padding:18px;font:13px/1.6 monospace}}code{{font:13px monospace}}li{{margin:9px 0}}.small{{font-size:13px;color:#58717e}}@media(max-width:700px){{main{{padding:24px 18px}}h1{{font-size:31px}}}}</style>
<main><div class="tag">Source review + new matches / November 11, 2026</div>
<h1>Does S55 beat the GitHub models?</h1><p class="lead"><strong>There is no general evidence that it does.</strong> New tests support an advantage over specific example policies in our eight-player tournament format, and expose a substantial weakness in heads-up play.</p>
<div class="callout"><strong>What actually ran:</strong> 70,000 heads-up hands, 35,000 eight-player reset-stack hands, and 896 eight-player tournaments ({total_tour_hands:,} tournament table-hands). S55 was frozen before testing. Seven external example-policy configurations were tested. <strong>Zero pretrained DQN/CFR models were tested.</strong></div>
<h2>Assessment of every supplied link</h2><div class="scroll"><table><thead><tr><th>Link</th><th>What it is</th><th>What can be concluded</th></tr></thead><tbody>{repo_html}</tbody></table></div>
<p>For the Toronto organization I inspected its profile, <a href="https://github.com/uoftcprg/pokerkit">PokerKit</a> and <a href="https://github.com/uoftcprg/noregret">NoRegret</a> descriptions and examples. For the two directories I reviewed their visible listings; I did not benchmark every linked project. Algorithms, libraries, resource lists and trained playing policies are different comparison targets.</p>
<h2>New results against Neuron Poker example policies</h2>
<p>The equity labels mean <strong>minimum call equity / minimum bet equity</strong>. The six pairs are taken from the upstream genetic-improvement initialization: (0.1,0.2) through (0.6,0.7). They were not optimized against S55. The random policy and equity action methods execute as retrieved from the inspected source.</p>
{table(['Upstream example policy','Heads-up: S55 bb/100','8-player cash: S55 bb/100','8-player tournaments: S55 points/bot'],rows)}
<p>Positive chip return favors S55. Tournament parity is 12.5 points per bot, since 100 total points are split among eight bots. In eight-player tests there are four independent S55 copies and four independent external copies; each cohort's total is divided by four. Cohort averaging is an evaluation metric only: the agents never cooperate or see one another's cards.</p>
<img alt="S55 comparison with corrected uncertainty intervals" src="data:image/png;base64,{encoded}">
<p class="small">Intervals in this figure simultaneously correct across all 21 metric/configuration comparisons using Bonferroni-adjusted Student-t bounds. Cash estimates use independent duplicate-deal averages (heads-up) or table-hand cohort means (eight-player). Tournament estimates use one cohort mean per table, not four falsely independent player samples.</p>
<div class="warning"><strong>Interpretation:</strong> S55's tournament advantage does not carry over to heads-up chip profit. Against the most aggressive threshold policy it loses about 164 big blinds per 100 heads-up hands. Its original success against our related heuristic opponents was not proof of broad strength.</div>
<h2>Why the results differ</h2><p>By code inspection, a plausible contributor is S55's narrow all-in calling rules and random-opponent equity assumption. It does not fully update its calling range when an opponent repeatedly shoves weak holdings. That can be costly heads-up, where folding repeatedly surrenders blinds. In a top-three payout tournament, survival and avoiding other players' confrontations have value. These are interpretations of code and outcomes, not a causal ablation study.</p>
<p>S55 is a book-inspired rule policy with sampled equity. It is not a learned game-theoretic strategy, and no exploitability guarantee was established. A working CFR implementation or a neural-network architecture does not by itself establish an opponent's strength either; game match, trained artifact and reproducible evaluation matter.</p>
<h2>Exactly what the adapter changes</h2><ul>
<li><strong>Preserved:</strong> upstream policy method bodies, threshold comparisons, action priority and the discrete action choices; original source blob hashes are pinned.</li>
<li><strong>Replaced:</strong> the Gym engine with PokerKit legal actions/settlement, and native equity calculations with the same equity feature used by S55 (our preflop asset plus 48 postflop samples).</li>
<li><strong>Bet mapping:</strong> upstream half-pot/pot/twice-pot actions mean an additional contribution of that size. Only targets legal under standard no-limit rules are offered; fractional chips are rounded down. All-in uses the maximum legal target. The original Gym per-player raise cap is not imposed.</li>
<li><strong>Not compared:</strong> the repositories' complete equity pipelines, the native Gym game implementation, trained neural policies, CFR strategy quality, external API latency or the official competition variant.</li></ul>
<p>Consequently these are <strong>adapted example-policy results</strong>. Calling them a victory over the full Neuron Poker neural model would be inaccurate.</p>
<h2>Game and statistical controls</h2><ul>
<li>Heads-up: 5,000 independent shuffled deals per opponent, each played from both seats, totaling 10,000 hands. Start stack 2,000 each hand, blinds 10/20, no rake.</li>
<li>Eight-player cash: 5,000 independent table-hands per opponent, seats rotated, stacks reset to 2,000 each hand, blinds 10/20.</li>
<li>Eight-player tournaments: 128 independent tables per opponent. Starts 2,000, 25-hand levels with big blinds 20/30/40/60/100/150/200/300, cap 200 hands. Assumed payouts 50/30/20; exact ICM for remaining payouts at the cap.</li>
<li>S55 parameters were not tuned after seeing these results. Seeds are distinct from the earlier experiments. No deadline folds are imposed. All hands check chip conservation and policy actions must be legal.</li>
<li>Ordinary 95% intervals are in the primary CSV files; simultaneous 95% bounds across all 21 comparisons are in <code>simultaneous_intervals.csv</code>. All seven tested tournament configurations remain above parity under those adjusted bounds.</li></ul>
<h2>Artifact and source audit</h2>
{table(['Repository','Branch','Inspected Git tree SHA','Files in complete tree'],pinned)}
<p>Tree hashes are Git <strong>tree</strong> identifiers, not claimed commit hashes. The cached recursive API inventories were not truncated. The Neuron tree contains 53 files and no trained weight artifact. Its loader expects a JSON architecture and H5 weights generated by training. A web search also found forks advertising weight files; those are different repositories and were not evaluated here.</p>
<p>MasterAI's configuration points to <code>./weights/value_net.net</code>, which is absent in its inspected tree. The two included <code>regrets.*.i</code> files are recorded in the inventory; they were not discarded or assumed to be a complete compatible model. Its source targets two-player play. Its <a href="https://github.com/masterai-top/cfr-poker-ai-masterai/blob/main/BENCHMARKS.md">benchmark protocol</a> explicitly identifies the old headline win rates as unverified project reports. No playing-strength result against that project is claimed.</p>
<h2>Practical judgment</h2><p>Keep S55 as a measured baseline for our assumed eight-player tournament, rather than treating it as a superior general poker model. The most useful immediate improvements are stronger conditioning on observed opponent aggression, format-specific preflop/all-in ranges and evaluation against independently trained policies. PokerKit remains useful as infrastructure; NoRegret is relevant for solving tractable games or abstractions, not a plug-in eight-player opponent.</p>
<p>A fair next trained-model comparison requires its exact checkpoint, compatible input encoding/action mapping and its intended game. Heads-up and eight-player outcomes must remain separate. No recommendation here depends on stars or repository names.</p>
<h2>Files and reproduction</h2><p>The accompanying archive contains the benchmark, pinned source downloader, raw hand/table outcomes, settings, inventories and this report. It requires the original <code>poker_lab</code> package next to <code>github_comparison</code>, or an explicit <code>POKER_LAB_PATH</code>.</p>
<pre>python download_sources.py
PYTHONHASHSEED=0 python benchmark.py --deals 5000 --tables 128 --workers 8
python build_report.py</pre>
<p>The downloader verifies Git blob hashes. Upstream sources are downloaded separately and are not redistributed in the archive. No poker client is automated, no game service is contacted, and no submission is made.</p>
<p class="small">Evidence boundary: source review establishes architecture and artifact availability; only the reported matches establish performance in this specific adapter and game configuration.</p></main></html>'''
    (ROOT/'Poker_GitHub_Comparison.html').write_text(content)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
