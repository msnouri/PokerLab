"""Local video files and the Mac capture workflow; no external game is opened."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import sys
from unittest.mock import patch

import cv2
from PIL import Image
from PySide6.QtWidgets import QApplication

from desktop.studio import Studio, ImageProvider
from desktop.v2.video import VideoRecorder


def wait_for(predicate, timeout=5, events=None):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        if events:
            events()
        time.sleep(.01)
    return predicate()


class VideoTests(unittest.TestCase):
    def test_video_decodes_after_resize_and_records_capture_timing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'table.mp4'
            v = VideoRecorder(path, 'Test window', fps=20)
            try:
                v.offer(Image.new('RGB', (80, 48), 'red'), time.monotonic())
                self.assertTrue(wait_for(lambda: v.frames >= 2), v.error)
                v.offer(Image.new('RGB', (40, 100), 'blue'), time.monotonic())
                self.assertTrue(wait_for(lambda: v.frames >= 4), v.error)
            finally:
                v.close()
            data = json.loads(path.with_suffix('.capture.json').read_text())
            self.assertEqual(data['error'], '')
            self.assertFalse(data['audio'])
            self.assertEqual(data['size'], [80, 48])
            self.assertEqual(len(data['samples']), data['frames'])
            self.assertTrue(any(r['repeated'] for r in data['samples']))
            cap = cv2.VideoCapture(str(path))
            decoded = 0
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    self.assertEqual(frame.shape[:2], (48, 80))
                    decoded += 1
            finally:
                cap.release()
            self.assertEqual(decoded, data['frames'])

    def test_slow_encoder_does_not_queue_a_capture_burst(self):
        entered, release = threading.Event(), threading.Event()
        colors = []
        class SlowWriter:
            def isOpened(self): return True
            def write(self, frame):
                colors.append(tuple(int(c) for c in frame[0, 0]))
                entered.set()
                release.wait(3)
            def release(self): pass
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'burst.mp4'
            with patch('cv2.VideoWriter', return_value=SlowWriter()):
                v = VideoRecorder(path, fps=30)
                path.touch()
                try:
                    v.offer(Image.new('RGB', (8, 8), 'blue'), time.monotonic())
                    self.assertTrue(entered.wait(3))
                    for _ in range(100):
                        v.offer(Image.new('RGB', (8, 8), 'green'), time.monotonic())
                    v.offer(Image.new('RGB', (8, 8), 'red'), time.monotonic())
                    release.set()
                    self.assertTrue(wait_for(lambda: len(colors) >= 2), v.error)
                    self.assertEqual(colors[1], (0, 0, 255))
                    self.assertGreaterEqual(v.replaced, 100)
                finally:
                    release.set()
                    v.close()

    def test_encoder_failure_is_reported_and_thread_finishes(self):
        class ClosedWriter:
            def isOpened(self): return False
            def release(self): pass
        with tempfile.TemporaryDirectory() as folder, patch('cv2.VideoWriter', return_value=ClosedWriter()):
            path = Path(folder)/'failed.mp4'
            v = VideoRecorder(path)
            v.offer(Image.new('RGB', (8, 8)), time.monotonic())
            self.assertTrue(v.finished.wait(3))
            v.close()
            self.assertIn('encoder', v.error)
            self.assertIn('encoder', json.loads(path.with_suffix('.capture.json').read_text())['error'])

    def test_idle_close_and_recording_limits_finish_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            idle = VideoRecorder(Path(folder)/'idle.mp4')
            idle.close();idle.close()
            self.assertTrue(idle.finished.is_set())
            limited = VideoRecorder(Path(folder)/'limited.mp4', max_seconds=.1)
            limited.offer(Image.new('RGB', (80, 48)), time.monotonic())
            self.assertTrue(limited.finished.wait(5))
            limited.close()
            self.assertIn('limit', limited.error)

    def test_existing_files_and_invalid_formats_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'existing.mp4'
            path.write_bytes(b'keep me')
            with self.assertRaises(ValueError): VideoRecorder(path)
            self.assertEqual(path.read_bytes(), b'keep me')
            with self.assertRaises(ValueError): VideoRecorder(Path(folder)/'wrong.mov')


class CaptureWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.studio = Studio(ImageProvider(), start_worker=False)

    def tearDown(self):
        self.studio.close()
        self.app.processEvents()

    def wait(self, predicate):
        self.assertTrue(wait_for(predicate, events=self.app.processEvents))

    def test_permission_denial_and_grant_are_visible(self):
        with patch('desktop.v2.mac_capture.permission', return_value=False):
            self.studio.requestPermission()
        self.assertEqual(self.studio.screen['permission'], 'Permission required')
        with patch('desktop.v2.mac_capture.permission', return_value=True):
            self.studio.requestPermission()
        self.assertEqual(self.studio.screen['permission'], 'Granted')

    def test_window_discovery_selection_and_stop_use_window_identity(self):
        rows = [{'id': 42, 'app': 'Browser', 'title': 'Practice table'}]
        with patch('desktop.v2.mac_capture.list_windows', return_value=rows):
            self.studio.refreshWindows()
            self.wait(lambda: not self.studio.discovery_busy)
        self.assertEqual(self.studio.windows[0]['label'], 'Browser — Practice table')
        class Capture:
            def __init__(self, window_id, on_frame, on_error):
                self.window_id=window_id;self.stopped=False
                on_frame(Image.new('RGB', (80, 48)), time.monotonic())
            def stop(self): self.stopped=True
        with patch('desktop.v2.mac_capture.MacWindowCapture', Capture):
            self.studio.useWindow(0)
            self.wait(lambda: self.studio.capture is not None)
        capture=self.studio.capture
        self.assertEqual(capture.window_id, 42)
        self.assertTrue(self.studio.screen['capturing'])
        self.wait(lambda: self.studio.last_image is not None)
        self.assertTrue(self.studio.screen['canRecord'])
        self.studio.stopCapture()
        self.assertTrue(capture.stopped)
        self.assertFalse(self.studio.screen['canRecord'])
        self.assertIsNone(self.studio.selected_window)

    def test_failed_capture_start_does_not_claim_to_be_capturing(self):
        self.studio.windows=[{'id':42,'app':'Browser','title':'Practice'}]
        with patch('desktop.v2.mac_capture.MacWindowCapture', side_effect=PermissionError('Permission denied')):
            self.studio.useWindow(0)
            self.wait(lambda: 'Permission denied' in self.studio.note)
        self.assertFalse(self.studio.playing)
        self.assertFalse(self.studio.screen['canRecord'])

    def test_video_records_before_ocr_and_finishes_when_capture_pauses(self):
        class Capture:
            def stop(self): pass
        with tempfile.TemporaryDirectory() as folder:
            self.studio.live=True;self.studio.playing=True;self.studio.capture=Capture()
            self.studio.last_image=Image.new('RGB', (80, 48), 'green')
            self.studio.last_stamp=time.monotonic()
            self.assertIsNone(self.studio.snapshot)
            path=Path(folder)/'screen.mp4'
            self.studio.start_video(path)
            v=self.studio.video
            self.assertIsNotNone(v)
            self.wait(lambda: v.frames >= 1)
            self.studio.pause()
            self.wait(lambda: self.studio.video is None)
            self.assertTrue(v.finished.is_set())
            self.assertFalse(self.studio.video_saving)
            self.assertTrue(path.is_file())
            self.assertTrue(path.with_suffix('.capture.json').is_file())

    def test_old_capture_error_cannot_stop_new_source(self):
        self.studio.capture_generation=10
        self.studio.playing=True
        self.studio.capture_error(9, 'old stream ended')
        self.assertTrue(self.studio.playing)
        self.assertNotIn('old stream', self.studio.note)
        self.studio.capture_error(10, 'current stream ended')
        self.assertFalse(self.studio.playing)
        self.assertIn('current stream', self.studio.note)

    def test_recording_requires_an_active_window_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'not-started.mp4'
            self.studio.start_video(path)
            self.assertIsNone(self.studio.video)
            self.assertFalse(path.exists())
            self.assertIn('Start Mac window capture', self.studio.note)

    def test_screen_cli_opens_the_capture_view(self):
        from desktop.__main__ import main
        with patch.object(sys, 'argv', ['pokerlab', '--screen']), patch('desktop.studio.main') as launch:
            main()
        launch.assert_called_once_with('auto', start_page=4)


if __name__ == '__main__':
    unittest.main()
