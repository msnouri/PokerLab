#!/bin/bash
# Run from Finder or with: bash "Launch Poker Lab.command"   (add --lab to open the Agent Lab directly)
set -euo pipefail
cd -- "$(dirname -- "$0")"
POKER_PYTHON=''
for candidate in python3.12 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info[:2] == (3,12)' 2>/dev/null; then
    POKER_PYTHON="$candidate"
    break
  fi
done
if [ -z "$POKER_PYTHON" ]; then
  echo 'Install Python 3.12 from https://www.python.org/downloads/macos/ and run this again.'
  echo 'The evaluator has prebuilt Intel and Apple Silicon wheels for this Python version.'
  read -r -p 'Press Return to close.'
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  "$POKER_PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3,12)' 2>/dev/null; then
  echo 'The existing .venv uses another Python version. Rename that folder and run this launcher again.'
  read -r -p 'Press Return to close.'
  exit 1
fi
if ! .venv/bin/python -c "import PySide6, cv2, mss, PIL, pytesseract, pokerkit, eval7; import sys; exec('import ScreenCaptureKit, Vision, Quartz, CoreMedia, dispatch' if sys.platform == 'darwin' else '')" 2>/dev/null || ! cmp -s requirements-gui.txt .venv/gui-requirements.txt; then
  .venv/bin/python -m pip install -r requirements-gui.txt
  cp requirements-gui.txt .venv/gui-requirements.txt
fi
exec .venv/bin/python -m desktop "$@"
