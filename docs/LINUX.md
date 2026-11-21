# PokerLab on Linux

Agent Lab, all 90 policies, Vision Studio, calibrated table reading, replays,
and local MP4 recording run on Linux. The initial Linux CI target is Ubuntu
24.04 x86_64 with Python 3.12. Other distributions need equivalent libraries;
they are not all validated. macOS keeps ScreenCaptureKit and Apple Vision.

## Install and launch

On Ubuntu 24.04, install the system libraries once:

```bash
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv tesseract-ocr tesseract-ocr-eng \
  libtesseract-dev libleptonica-dev libegl1 libgl1 libpulse0 \
  libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-xinerama0 \
  libxcb-render-util0 libxcb-xinput0 libxcb-shape0 libxcb-xfixes0 libxcb-randr0 \
  libxcb-sync1 libx11-xcb1 libxkbcommon-x11-0 libwayland-client0 libwayland-cursor0 libwayland-egl1
bash launch-linux.sh
```

Run from the repository folder. The launcher creates `.venv`, installs the
pinned GUI requirements on first use, and forwards CLI options:

```bash
bash launch-linux.sh --lab       # Practice, coach, quiz, policy comparison
bash launch-linux.sh --screen    # Live capture and local video
```

It uses Python 3.12; set `POKERLAB_PYTHON=/path/to/python3.12` if it is not on
PATH. The first install requires internet. Capture, OCR, recording and policies
run locally. The launcher does not install system packages or change your
desktop session. Alternatively create a Python 3.12 venv, install
`requirements-gui.txt`, and run `python -m desktop` or `python -m desktop --lab`.

Linux uses **persistent native Tesseract** by default, with English language
data. `TESSDATA_PREFIX` can point to a folder containing `eng.traineddata`.
`--backend subprocess` retains the slower command-line fallback; `--backend
vision` is Mac-only. The Linux-only `PySide6-Addons` dependency supplies Qt
Multimedia, using its FFmpeg capture backend.

## Choose a source

The **Linux screen** view in Studio, or **Screen recording ↗** in Agent Lab,
opens the capture controls. Captured pixels feed the same calibrated reader
and independent MP4 recorder as on Mac.

| Desktop session | Workflow |
|---|---|
| X11 / Xorg | **Refresh X11 windows**, choose the title, then **Start selected window**. Qt keeps an opaque window handle, so matching titles and window movement do not redirect capture. A closed window ends capture. |
| Wayland | **Find sharing source**, then **Choose in desktop picker**. The compositor asks what to share and for permission. Available choices depend on the desktop/portal; a window choice is not guaranteed. |

Wayland needs PipeWire, `xdg-desktop-portal`, and the portal backend matching
your desktop. These are normally supplied by a modern desktop installation.
For Ubuntu GNOME, if missing:

```bash
sudo apt-get install pipewire xdg-desktop-portal xdg-desktop-portal-gnome
```

KDE uses `xdg-desktop-portal-kde`; other compositors require their own backend.
Do not replace a working desktop backend with GNOME's solely for this app.
The launcher selects `QT_QPA_PLATFORM=wayland` in a Wayland session unless you
already set it. A forced `xcb`/XWayland app is rejected for Wayland sharing;
use the launcher or `QT_QPA_PLATFORM=wayland python -m desktop --screen`.
Capture does not silently fall back to an unapproved desktop screenshot.

**Check capture access** does not grant Wayland permission in advance. The
actual grant happens in the sharing picker. Until the first frame arrives,
the preview remains unready and recording stays disabled. Cancellation,
capture errors and a 60-second first-frame timeout stop the stream. Pause,
stop and app shutdown release sharing; resuming Wayland can prompt again.

Prefer sharing only the table window, where offered. If only a screen can be
selected, keep unrelated windows off it and place Studio elsewhere to avoid
capturing its own preview. Images are capped at 1920 × 1300 with their aspect
ratio preserved. High-resolution desktops can make cards/text too small;
use a suitably sized table and calibrate against the actual preview.
Keep an X11 source visible, unobscured and completely inside the display;
minimized, covered or partly offscreen windows may fail or produce unusable
pixels with the native backend. A capture error stops the stream.

## Read and record

Use **Table setup** to draw and confirm regions, teach unfamiliar card and
indicator examples, set seats/chip scale, and save the layout. Pause freezes
the image for calibration; resume to read fresh pixels. Each external table
design still needs representative labelled examples.

**Record MP4 video** writes silent video at a 10 fps target plus a
`.capture.json` timing sidecar. It uses the newest frame independently of OCR;
resizing is letterboxed, and pause/stop ends the clip. Existing files are
preserved. The same 30-minute / approximately 500 MB limits apply. **Record
readings** instead saves lossless frames and observation JSON for replay.
See [recording details](MAC_SCREEN_RECORDING.md#save-video) and the
[calibration guide](../desktop/VISION_STUDIO.md#read-your-own-table).

Studio observes table state. Policy coaching remains in Agent Lab and the
reviewed classic workbench; this extension does not create live betting
automation or a universal table-to-advice bridge.

## Checks and limits

The **Linux Vision Studio** workflow runs desktop/recorder/worker tests,
research solver tests, and the native Tesseract labelled replay with the same
98% field / 85% critical-frame coverage gates and zero accepted wrong values.
It also opens a real X11 fixture under Xvfb/Openbox, captures its pixels,
changes its size and position, writes/decodes MP4, resumes capture, and checks
that closing the window stops sharing. Reports are uploaded as CI artifacts.

Wayland routing, permission state, cancellation/error handling, frame bounds,
and GUI-thread ownership have automated tests. A real GNOME/KDE/compositor
portal grant remains a device check; Xvfb does not establish that. Qt 6.8
documents Wayland screen capture as experimental:
[Qt screen capture limitations](https://doc.qt.io/qt-6.8/qscreencapture.html#screen-capture-limitations).
Neither fixture checks nor OCR replay certify arbitrary table artwork or
full capture-to-decision latency. The live snapshot expires after five seconds;
on streams that emit only changes, an unchanged image can become stale.

If Qt cannot load `xcb`/`wayland`, check the listed system libraries and run
`QT_DEBUG_PLUGINS=1 bash launch-linux.sh --screen` for details. A headless or
SSH-only shell cannot capture a local desktop without a display session.
For empty X11 lists, check that the target is a normal visible window and a
window manager is running. For an unavailable Wayland picker, check PipeWire,
the session D-Bus and the compositor's portal service.
