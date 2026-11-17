"""Process lifecycle contracts independent of native OCR speed and availability."""
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PIL import Image

from desktop.v2.layout import Layout
from desktop.v2.runtime import VisionProcess
from desktop.v2.state import Snapshot


def waiting_worker(inputs, outputs, layout_data, folder, backend):
    """A stalled worker for deterministic watchdog tests, also under spawn."""
    while inputs.get() is not None:
        pass


def echo_worker(inputs, outputs, layout_data, folder, backend):
    """Exercise the actual process and queues without an OCR model."""
    outputs.put({'engine': 'Process contract fixture'})
    while True:
        job = inputs.get()
        if job is None:
            return
        outputs.put({'started': job['id'], 'at': time.monotonic()})
        outputs.put({'snapshot': Snapshot(job['id'], job['at'], job['source'], {}),
                     'hashes': {}, 'raw_hashes': {}, 'epoch': job['epoch']})


class VisionProcessTests(unittest.TestCase):
    def start_worker(self, target=waiting_worker):
        replacement = patch('desktop.v2.runtime.worker', target)
        replacement.start()
        self.addCleanup(replacement.stop)
        process = VisionProcess(Layout(), Path('.'), epoch=17)
        self.addCleanup(process.stop)
        return process

    def test_latest_pending_frame_is_delivered(self):
        v = self.start_worker(echo_worker)
        image = Image.new('RGB', (8, 8))
        for frame in range(1, 8):
            v.submit(image, frame, time.monotonic(), 'queue contract')
        ids, errors, epochs = [], [], []
        end = time.monotonic() + 15
        while time.monotonic() < end and 7 not in ids:
            for message in v.poll():
                if 'snapshot' in message:
                    ids.append(message['snapshot'].frame_id)
                    epochs.append(message['epoch'])
                if 'error' in message:
                    errors.append(message['error'])
            time.sleep(.01)
        self.assertEqual(errors, [])
        self.assertEqual(ids, [7])
        self.assertEqual(epochs, [17])
        self.assertEqual(v.replaced, 6)

    def test_frame_timeout_kills_worker_and_retries_newest_frame(self):
        v = self.start_worker()
        image = Image.new('RGB', (8, 8))
        v.submit(image, 1, time.monotonic(), 'old')
        v.submit(image, 2, time.monotonic(), 'new')
        old = v.process
        v.active_at = time.monotonic() - 6
        v.boot_at = 0
        messages = v.poll()
        self.assertFalse(old.is_alive())
        self.assertIsNot(v.process, old)
        self.assertEqual(v.restarts, 1)
        self.assertEqual(v.pending['id'], 2)
        self.assertTrue(any('frame deadline' in m.get('error', '') for m in messages))

    def test_initialization_timeout_restarts_worker(self):
        v = self.start_worker()
        old = v.process
        v.boot_at = time.monotonic() - 31
        messages = v.poll()
        self.assertFalse(old.is_alive())
        self.assertEqual(v.restarts, 1)
        self.assertTrue(any('initialization deadline' in m.get('error', '') for m in messages))

    def test_exhausted_watchdog_can_still_be_polled_and_stopped(self):
        v = self.start_worker()
        for _ in range(3):
            v.active_at = time.monotonic() - 6
            v.boot_at = 0
            v.poll()
        self.assertIsNone(v.process)
        self.assertTrue(v.failed)
        self.assertFalse(v.ready)
        for _ in range(4):
            self.assertEqual(v.poll(), [])
        v.stop()
        self.assertEqual(v.poll(), [])

    def test_explicit_stop_is_idempotent_and_does_not_accept_more_frames(self):
        v = self.start_worker()
        v.submit(Image.new('RGB', (8, 8)), 1, time.monotonic(), 'test')
        v.stop()
        v.stop()
        self.assertEqual(v.poll(), [])
        v.submit(Image.new('RGB', (8, 8)), 2, time.monotonic(), 'stopped')
        self.assertIsNone(v.pending)
        self.assertIsNone(v.latest_job)
        self.assertIsNone(v.active_at)
        self.assertEqual(v.boot_at, 0)


if __name__ == '__main__':
    unittest.main()
