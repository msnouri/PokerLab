# Poker AI reading list

Snapshot: 2026-11-12. OpenAlex cited_by_count, one matched work per paper. Counts differ from Google Scholar; duplicates/preprints are not summed. Rank is within this curated list, not all poker literature.

Citation counts measure indexed impact, not playing strength. Missing counts are not zero.

| Paper | Year | Citations | In PokerLab |
|---|---:|---:|---|
| [DeepStack: Expert-level artificial intelligence in heads-up no-limit poker](https://doi.org/10.1126/science.aam6960) | 2017 | 882 | Reading only |
| [Superhuman AI for multiplayer poker](https://doi.org/10.1126/science.aay2400) | 2019 | 680 | Reading only |
| [Superhuman AI for heads-up no-limit poker: Libratus beats top professionals](https://doi.org/10.1126/science.aao1733) | 2018 | 606 | Reading only |
| [Regret Minimization in Games with Incomplete Information](https://poker.cs.ualberta.ca/publications/NIPS07-cfr.pdf) | 2007 | 523 | R01 |
| [Deep Reinforcement Learning from Self-Play in Imperfect-Information Games](https://arxiv.org/abs/1603.01121) | 2016 | 443 | Reading only |
| [Heads-up limit hold’em poker is solved](https://doi.org/10.1126/science.1259433) | 2015 | 380 | Reading only |
| [Monte Carlo Sampling for Regret Minimization in Extensive Games](https://papers.nips.cc/paper/2009/hash/00411460f7c92d2124a67ea0f4cb5f85-Abstract.html) | 2009 | 207 | R02 |
| [Solving Large Imperfect Information Games Using CFR+](https://arxiv.org/abs/1407.5042) | 2014 | 164 | R03 |
| [Deep Counterfactual Regret Minimization](https://proceedings.mlr.press/v97/brown19b.html) | 2019 | 105 | Reading only |
| [Combining Deep Reinforcement Learning and Search for Imperfect-Information Games](https://arxiv.org/abs/2007.13544) | 2020 | 89 | Reading only |
| [Student of Games: A unified learning algorithm for both perfect and imperfect information games](https://doi.org/10.1126/sciadv.adg3256) | 2023 | 62 | Reading only |
| [Faster Game Solving via Predictive Blackwell Approachability: Connecting Regret Matching and Mirror Descent](https://doi.org/10.1609/aaai.v35i6.16676) | 2021 | 32 | R05 |
| [Solving Imperfect-Information Games via Discounted Regret Minimization](https://doi.org/10.1609/aaai.v33i01.33011829) | 2019 | 27 | R04 |
| [Real-Time Parallel Counterfactual Regret Minimization](https://arxiv.org/abs/2605.19928) | 2026 | 10 | Reading only |
| [Minimizing Weighted Counterfactual Regret with Optimistic Online Mirror Descent](https://www.ijcai.org/proceedings/2024/583) | 2024 | 7 | R06 |
| [SpinGPT: A Large-Language-Model Approach to Playing Poker Correctly](https://arxiv.org/abs/2509.22387) | 2025 | 2 | Reading only |
| [Deep (Predictive) Discounted Counterfactual Regret Minimization](https://ojs.aaai.org/index.php/AAAI/article/view/38780) | 2026 | 0 | Reading only |
| [Dynamic Discounted Counterfactual Regret Minimization](https://proceedings.iclr.cc/paper_files/paper/2024/hash/a89331e2ecbbd9d9618bc94717a91155-Abstract-Conference.html) | 2024 | Unavailable | Reading only |

## What to read first

Start with CFR → CFR+ → discounted/predictive CFR. These teach the trainable algorithms implemented here. Read DeepStack and Libratus for heads-up search and range handling; read Pluribus for six-player play. Read Deep CFR/ReBeL/Student of Games for larger learned value and search systems.

For recent developments, PDCFR+ (IJCAI 2024) is already available as R06 in the reduced game. DDCFR (ICLR 2024), SpinGPT (2025 preprint), Deep (Predictive) DCFR (AAAI 2026) and Parallel CFR (2026 preprint) are research leads, not reproduced agents. SpinGPT also has a 2026 indexed proceedings record; the catalog uses its 2025 preprint date.

OpenAlex can split proceedings, repositories and preprints. Counts here use one verified record per paper and are not a complete citation audit. CFR and MCCFR matched institutional records; their counts may especially understate total impact. DDCFR is unavailable because a fuzzy match returned an unrelated paper and was rejected. The Libratus issue year is 2018 although its online record is 2017.

The implementation notes and evaluation are in [README.md](README.md).
