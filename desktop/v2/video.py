"""Bounded local MP4 recording, independent of OCR and its observation queue."""
from pathlib import Path
import json
import threading
import time

import cv2
import numpy as np
from PIL import Image, ImageOps


class VideoRecorder:
    """Sample the latest capture at a fixed rate; never queue old video frames.

    The input PIL images are immutable capture buffers owned by the caller.
    Actual capture/encode timestamps are retained beside the constant-rate MP4.
    This is silent local video, not a labelled replay or a latency benchmark.
    """
    def __init__(self, path, source='', fps=10, max_bytes=500_000_000,
                 max_seconds=1800, on_finished=None):
        self.path = Path(path)
        if self.path.suffix.lower() != '.mp4':
            raise ValueError('Choose an .mp4 recording file')
        if self.path.exists() or self.path.with_suffix('.capture.json').exists():
            raise ValueError('Choose a new filename; existing recordings are preserved')
        if not 1 <= fps <= 30 or max_bytes <= 0 or max_seconds <= 0:
            raise ValueError('Invalid video recording limits')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.source, self.fps = source, fps
        self.max_bytes, self.max_seconds = max_bytes, max_seconds
        self.on_finished = on_finished
        self.condition = threading.Condition()
        self.latest = None
        self.stopping = False
        self.frames = 0
        self.error = ''
        self.replaced = 0
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self._run, name='PokerLab video recorder', daemon=True)
        self.thread.start()

    def offer(self, image, captured_at):
        with self.condition:
            if self.stopping or self.finished.is_set():
                return
            if self.latest is not None:
                self.replaced += 1
            self.latest = (image, captured_at)
            self.condition.notify()

    def request_stop(self):
        with self.condition:
            self.stopping = True
            self.condition.notify()

    def close(self, timeout=5):
        self.request_stop()
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise TimeoutError('Video is still saving; leave the application open')

    def _run(self):
        writer = None
        started = time.monotonic()
        rows = []
        size = None
        last_frame = None
        next_frame = started
        result = {'version': 1, 'source': self.source, 'video': self.path.name,
                  'fps': self.fps, 'codec': 'mp4v', 'audio': False,
                  'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'note': 'Sampled local video. Timestamps describe capture/encoding; reader output is not ground truth.'}
        try:
            while True:
                with self.condition:
                    while not self.stopping:
                        delay = next_frame - time.monotonic()
                        if (self.latest is not None or last_frame is not None) and delay <= 0:
                            break
                        self.condition.wait(max(.001, delay) if delay > 0 else None)
                    if self.stopping:
                        break
                    current = self.latest or last_frame
                    self.latest = None
                image, captured_at = current
                if writer is None:
                    size = (max(2, image.width // 2 * 2), max(2, image.height // 2 * 2))
                    writer = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*'mp4v'), self.fps, size)
                    if not writer.isOpened():
                        raise RuntimeError('MP4 encoder could not open. Check the output folder and OpenCV installation.')
                # Keep one video size if the captured window is resized.
                canvas = ImageOps.pad(image.convert('RGB'), size, method=Image.Resampling.BILINEAR, color='black')
                writer.write(cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR))
                now = time.monotonic()
                rows.append({'frame': self.frames, 'captured_ms': round((captured_at-started)*1000, 3),
                             'encoded_ms': round((now-started)*1000, 3),
                             'repeated': last_frame is not None and captured_at == last_frame[1]})
                self.frames += 1
                last_frame = current
                # No catch-up loop: overload must not build a backlog.
                next_frame = max(next_frame + 1/self.fps, now)
                if now-started >= self.max_seconds:
                    raise RuntimeError('Recording reached its 30-minute limit')
                if self.path.stat().st_size >= self.max_bytes:
                    raise RuntimeError('Recording reached its approximate 500 MB limit')
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'
        finally:
            if writer is not None:
                try:
                    writer.release()
                except Exception as exc:
                    self.error = f'Could not finish MP4: {exc}'
            result.update(frames=self.frames, size=size, samples=rows, error=self.error,
                          replaced_pending_frames=self.replaced,
                          wall_seconds=round(time.monotonic()-started, 3),
                          playback_seconds=round(self.frames/self.fps, 3))
            try:
                self.path.with_suffix('.capture.json').write_text(json.dumps(result, indent=2)+'\n')
            except OSError as exc:
                self.error = result['error'] = f'Could not save recording metadata: {exc}'
            with self.condition:
                self.stopping = True
                self.latest = None
            self.finished.set()
            if self.on_finished:
                self.on_finished(result)
