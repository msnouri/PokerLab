# Algorithm references and licensing

The vectorized game-tree traversal in `poker_lab/pokerlab/research/solver.py`
was independently written for this project. Regret discounting, predictive
updates and averaging schedules were checked against the papers and the
authors' reference implementation:

- <https://github.com/rpSebastian/PDCFRPlus>
- Reviewed commit: `d81089530a2a14dc3318984c828393ebcea139ee`
- Files consulted: `pdcfrplus/cfr/{cfr,cfr_plus,dcfr,pcfr_plus,pdcfr_plus,cfr_base}.py`
- No reference training weights, poker tables, or datasets are redistributed.

The reference implementation's license is reproduced below. PokerKit, eval7,
NumPy, SciPy and the desktop dependencies keep their respective upstream
licenses; see also the repository's existing notices and pinned requirements.

```text
MIT License

Copyright (c) 2024 Hang Xu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
