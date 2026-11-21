# What has been verified

Reviewed 17 November 2026. Evidence is tied to a commit and a run; a green check
does not certify arbitrary table artwork, a live poker client, or profitability.

## The commit that was reported

`5ffb5f5f21391aadc0581b8fa9c4017dd110f640` has a real historical failure:
[run 43159407253](https://github.com/msnouri/PokerLab/actions/runs/43159407253).
The Intel `test_process_latest_frame_contract` did not receive frame 7 before
the vision watchdog discarded two late results. Its replay accepted no wrong
values, but read only 1,124/1,272 fields and had no fully correct critical-field
frames. At that time the benchmark step did not enforce useful coverage.

The later numeric-example calibration and matching process-test fixture in
`9fd7893` resolved that failure in subsequent runs. `0f0c0c1` added minimum
coverage and critical-frame gates, plus checks against wrong repeated reads.
The historical red run remains red; newer passing runs are the relevant
evidence for the current code. No watchdog or accuracy gate was disabled here.

There is also a **separate signature status**. GitHub's commit API reports
`verified: false, reason: unsigned` for `5ffb5f5`. This concerns cryptographic
authorship, not code testing. Test success cannot turn an unsigned commit into
a signed one. No signing identity was fabricated and no history was rewritten.

## Recorded native Mac evidence

At `e5536de8fea5de5e5abc35c932d463159616885a`, both jobs in
[run 43248833720](https://github.com/msnouri/PokerLab/actions/runs/43248833720)
passed: 64 desktop tests (62 passed, two optional legacy Tesseract tests skipped)
and 13 research tests on each architecture, followed by native Apple Vision.
The checked-in JSON snapshots were refreshed from those job logs.

| Check | Apple Silicon | Intel |
|---|---:|---:|
| Labelled replay frames | 24 | 24 |
| Fields read / total | 1,270 / 1,272 | 1,268 / 1,272 |
| Wrong accepted values, fresh and repeated | 0 | 0 |
| All critical fields correct | 24 / 24 | 22 / 24 |
| All 53 fields correct | 22 / 24 | 20 / 24 |
| Changed-frame recognition p95 | 1.36 s | 3.54 s |

[ARM snapshot](../desktop/validation-v2-macos-arm64.json) ·
[Intel snapshot](../desktop/validation-v2-macos-intel.json).
These are generated, calibrated image replays, not live capture measurements.
Timing excludes capture, display, review and one-time startup. A withheld value
is unknown, not correct. The original 250 ms recognition target remains unmet.

## Verification that runs on new commits

### Cancelled before a Mac runner started

At `2d46b68`, the first attempt of
[run 44114065844](https://github.com/msnouri/PokerLab/actions/runs/44114065844/attempts/1)
passed on Intel. The `macos-15` Apple Silicon job was cancelled after roughly
15 minutes with runner ID 0 and no steps: neither setup nor application tests
ran. This matches the hosted ARM provisioning incident described by the
[runner-images maintainer](https://github.com/actions/runner-images/issues/15291#issuecomment-6828064085).
Increasing the test timeout does not repair host provisioning.

`Recover unassigned Mac runner` checks completed default-branch Mac runs on an
Ubuntu host. It requests a rerun only for a cancelled native Mac job with
explicitly empty steps and runner ID 0, within an otherwise failed workflow.
It allows at most three total attempts (two retries, including manual retries),
requests one job per completion, and skips superseded commits, PRs, forks,
active runs, and whole-workflow cancellations. Its write permission is scoped
to Actions; the helper executes trusted default-branch code without persisted
checkout credentials or downloaded artifacts. Policy tests run in repository CI.

Both `macos-15` (ARM) and `macos-15-intel` coverage remain enabled, with an
explicit CPU architecture assertion. Test failures, started jobs, watchdogs,
and OCR accuracy gates are unchanged. A recovery summary is not a passing Mac
check: only the original native job's rerun establishes that result. Hosting
availability is outside this repository's control; after the retry limit,
inspect the original Actions run and use **Re-run jobs** if appropriate.

### Vision worker lifecycle repair

The latest failure at `6f97ad8` was an Apple Silicon process-test error:
after three watchdog expirations, polling attempted to read a closed queue.
Stopped workers now ignore polling and submissions, clear retained frames and
deadline clocks, and report a terminal failure when their retry limit is
reached. The 5-second frame watchdog, 30-second startup deadline and three-attempt
limit are unchanged.

`desktop/tests/test_vision_process.py` checks coalescing to the newest frame,
startup and frame timeouts, retry exhaustion, and repeated polling/shutdown
with real spawned processes and deterministic test workers. Native OCR has a
separate process integration check for calibrated cards and a numeric field;
the rich-frame test and 24-frame Apple Vision benchmark still check the full
table, with the same wrong-read and coverage gates. Recorded native results above remain
tied to their stated historical commits; consult the new commit's checks for
the repair's native Mac results.

- **Native Mac CI:** GUI, observation validity, selected-window protocol imports,
  buffer stride conversion, process deadlines, latest-frame behavior, CFR
  correctness, legality and native OCR replay, on ARM and Intel.
- **Repository verification:** original engine tests, raw research outcome and
  confidence-interval audits, frozen-model hashes, paired-deal completeness,
  benchmark manifests, README links and animation integrity.
- **Evidence downloads:** each Mac job uploads its native replay JSON; the
  repository check uploads a machine-readable audit summary. Read the exact
  commit's checks, rather than assuming an older green badge applies to it.

## Remaining gaps, kept explicit

### Linux extension

`Linux Vision Studio` adds Ubuntu 24.04 / Python 3.12 coverage for the desktop,
native Tesseract replay, research solvers, and a real X11 fixture window under
Xvfb/Openbox. `scripts/linux_capture_smoke.py` checks source pixels, resizing,
movement, MP4 write/decode, pause/resume, and stopping after window closure.
`desktop/tests/test_linux_capture.py` checks Qt GUI-thread ownership, window
identity, pixel stride/copy/size bounds, bounded frame replacement, the Wayland
picker route, permission state, cancellation/error handling and stale callbacks.
CI uploads the replay and capture reports. As with the Mac checks, consult the
exact commit's run for its result.

The real Wayland portal/compositor grant is not established by these tests;
that requires a GNOME/KDE or other supported desktop session with PipeWire and
the matching portal. Linux support and setup are detailed in [LINUX.md](LINUX.md).

The screen view and background MP4 recorder are covered by
`desktop/tests/test_screen_recording.py`: actual MP4 write/decode, resize handling,
bounded latest-frame behavior during slow encoding, error/limit finalization,
permissions and selected-window routing, stale errors, and pause/stop behavior.
The GUI renders all five Studio views and tests the Agent Lab launch button.
These tests use generated frames and mocked capture for workflow checks; they
do not establish successful capture of an external game on the user's Mac.

| Area | Status / what would establish it |
|---|---|
| Live capture on the user's Mac | Requires a selected real window, Screen Recording permission, and move/resize/display-change checks on that device. CI cannot grant the user's permissions. |
| External table artwork | Requires independent labelled screenshots and calibration for that design. The generated fixture does not validate an arbitrary client. |
| Complete capture-to-decision latency | Requires one instrumented end-to-end session; OCR, policy and UI measurements cannot simply be substituted for it. |
| Native display smoothness | Offscreen rendering and queued heartbeat measure narrower properties; physical input/display latency is not established. |
| macOS 13/14 compatibility | Product target is macOS 13+; recorded native CI currently runs macOS 15. |
| Signed/notarized `.app` | Source launcher only; no signed distributable is supplied. |
| Reconstructed action history | `history_complete` stays false; missing actions are not invented. |
| Stronger or profitable play | Current paper proxies lost to S55; champion systems, real opponents and real-money performance were not reproduced. |
| Commit signing | GitHub “Verified” is a signing property, independent of these checks. Historical unsigned objects remain unsigned. |

## README demo provenance

The GIFs are recorded from the actual Qt windows with generated practice tables.
The vision worker reads pixels; fixture ground-truth labels are not injected.
Strategy advice comes from the selected policy and actions use the local legal
engine. Captions identify Linux/offscreen recording and the edited walkthrough.
They do not present this as live Mac capture or demonstrate real-time speed.
See [media manifest](media/manifest.json), the
[Vision Studio recording script](../scripts/record_readme_demos.py) and the
[Agent Lab recording script](../scripts/record_agent_lab_demo.py); the Agent Lab
walkthrough's showdown scene comes from a second table (seed 23). No footage or assets from
the reference Poker repository were copied.

## Agent Lab and library policies

| Claim | Check | Not covered |
|---|---|---|
| Agent Lab deals legal hands, conserves chips, keeps players in their seats while the button moves, and keeps opponents' cards private until a showdown they reached | `desktop/tests/test_lab.py`, two table sizes × five depths, chosen and random opponents | Opponents are this repository's policies |
| Window opens on a live decision; Coach, Quiz and Watch behave as documented | Same file, Qt offscreen on Linux | Not yet run on a Mac display; the macOS CI job runs these tests headless |
| T01 ranges are an equilibrium of the jam-or-fold game | `library/build_pushfold.py` stores exploitability (< 0.002 bb at every depth); `tests/test_library.py` | Equities are Monte Carlo (1,500 samples per class pair); hands at the range border carry noise |
| T01–T04 take only legal actions | `tests/test_library.py`, 1,000 hands across five formats | — |
| Library results | `poker_lab/library_results/benchmark.json`, 64,000 paired hands per policy | In-repo opponents only; one seed set |
| App bundle recipe | Built and started headless on Linux | Never built, signed or opened on macOS |

The Agent Lab screenshots were taken from the running window with `--seed 120`
(`python -m desktop --lab --seed 120 --screenshot out.png`) and a scripted
heads-up 12 bb session; they are unedited.
