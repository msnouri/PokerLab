#!/usr/bin/env bash
# Install isolated Python dependencies once, then run Studio (--screen / --lab).
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
POKERLAB_INTERPRETER=''
for candidate in "${POKERLAB_PYTHON:-python3.12}" python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info[:2] == (3,12)' 2>/dev/null; then
    POKERLAB_INTERPRETER="$candidate"
    break
  fi
done
if [ -z "$POKERLAB_INTERPRETER" ]; then
  echo 'Python 3.12 is required. See docs/LINUX.md; set POKERLAB_PYTHON to its executable if needed.' >&2
  exit 1
fi
if ! command -v tesseract >/dev/null 2>&1; then
  echo 'Install Linux system dependencies first; see docs/LINUX.md (tesseract-ocr and English language data).' >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  "$POKERLAB_INTERPRETER" -m venv .venv
fi
if ! .venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3,12)' 2>/dev/null; then
  echo 'The existing .venv uses another Python version. Rename it and run this launcher again.' >&2
  exit 1
fi
if ! .venv/bin/python -c 'import PySide6.QtMultimedia, cv2, PIL, pytesseract, tesserocr, pokerkit, eval7' 2>/dev/null || ! cmp -s requirements-gui.txt .venv/gui-requirements.txt; then
  .venv/bin/python -m pip install -r requirements-gui.txt
  cp requirements-gui.txt .venv/gui-requirements.txt
fi
export QT_MEDIA_BACKEND="${QT_MEDIA_BACKEND:-ffmpeg}"
if { [ "${XDG_SESSION_TYPE:-}" = wayland ] || [ -n "${WAYLAND_DISPLAY:-}" ]; } && [ -z "${QT_QPA_PLATFORM:-}" ]; then
  export QT_QPA_PLATFORM=wayland
fi
exec .venv/bin/python -m desktop "$@"
