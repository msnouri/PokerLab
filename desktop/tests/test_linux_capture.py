"""Linux capture lifecycle and portal routing, without opening a game."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QThread
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from desktop.v2 import capture, linux_capture
from desktop.studio import Studio, ImageProvider


class Signal:
    def __init__(self): self.slots=[]
    def connect(self, fn, *args): self.slots.append(fn)
    def emit(self, *args):
        for fn in self.slots: fn(*args)


class Handle:
    def isValid(self): return True
    def description(self): return 'Same title'


class Stream:
    def __init__(self, parent=None):
        self.errorOccurred=Signal();self.activeChanged=Signal();self.stopped=False
    def setWindow(self, window): self.window=window
    def start(self): pass
    def stop(self): self.stopped=True


class Session:
    def __init__(self, parent=None): pass
    def setVideoSink(self, sink): self.sink=sink
    def setWindowCapture(self, stream): self.window=stream
    def setScreenCapture(self, stream): self.screen=stream


class Sink:
    def __init__(self, parent=None): self.videoFrameChanged=Signal()


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux backend')
class LinuxCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def media(self):
        return SimpleNamespace(QMediaCaptureSession=Session, QVideoSink=Sink,
                               QScreenCapture=Stream, QWindowCapture=Stream, QCapturableWindow=Handle)

    def test_backend_dispatch_preserves_mac_and_rejects_unsupported_platforms(self):
        with patch('sys.platform','linux'): self.assertIs(capture.backend(),linux_capture)
        with patch('sys.platform','darwin'):
            self.assertEqual(capture.backend().__name__,'desktop.v2.mac_capture')
        with patch('sys.platform','win32'):
            self.assertFalse(capture.controls()['supported'])
            with self.assertRaisesRegex(RuntimeError,'macOS and Linux'): capture.backend()

    def test_wayland_is_detected_even_when_qt_was_forced_to_xwayland(self):
        with patch.dict(os.environ, {'XDG_SESSION_TYPE':'wayland','WAYLAND_DISPLAY':''}):
            self.assertTrue(linux_capture.is_wayland())
            with patch.object(linux_capture,'_multimedia',return_value=self.media()), patch.object(linux_capture.QGuiApplication,'platformName',return_value='xcb'):
                with self.assertRaisesRegex(RuntimeError,'QT_QPA_PLATFORM=wayland'): linux_capture.permission()

    def test_x11_capture_is_enabled_when_the_session_variable_is_missing(self):
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'','WAYLAND_DISPLAY':''}), patch.object(linux_capture.QGuiApplication,'platformName',return_value='xcb'):
            linux_capture._multimedia()
            self.assertEqual(os.environ['XDG_SESSION_TYPE'],'x11')

    def test_rgb_padding_is_copied_and_large_frames_are_bounded(self):
        image=QImage(3,2,QImage.Format.Format_RGB888);image.fill(QColor('red'))
        copied=linux_capture.qimage_image(image)
        image.fill(QColor('blue'))
        self.assertEqual(copied.getpixel((2,1)),(255,0,0))
        large=QImage(3840,2160,QImage.Format.Format_RGB888);large.fill(QColor('green'))
        scaled=linux_capture.qimage_image(large)
        self.assertEqual(scaled.size,(1920,1080))
        with self.assertRaises(ValueError): linux_capture.qimage_image(QImage())

    def test_qt_operations_reject_a_worker_thread(self):
        errors=[]
        def run():
            try: linux_capture.list_windows()
            except RuntimeError as exc: errors.append(str(exc))
        worker=threading.Thread(target=run);worker.start();worker.join(3)
        self.assertEqual(len(errors),1);self.assertIn('GUI thread',errors[0])

    def test_x11_discovery_preserves_identity_for_duplicate_titles(self):
        a,b=Handle(),Handle()
        media=self.media()
        media.QWindowCapture=SimpleNamespace(capturableWindows=lambda:[a,b])
        with patch.object(linux_capture,'_multimedia',return_value=media), patch.object(linux_capture,'permission'), patch.object(linux_capture,'is_wayland',return_value=False):
            rows=linux_capture.list_windows()
        self.assertIs(rows[0]['id'],a);self.assertIs(rows[1]['id'],b)

    def test_wayland_discovers_only_a_picker_and_does_not_claim_a_permission_grant(self):
        with patch.object(linux_capture,'_multimedia',return_value=self.media()), patch.object(linux_capture,'is_wayland',return_value=True), patch.object(linux_capture.QGuiApplication,'platformName',return_value='wayland'):
            self.assertFalse(linux_capture.permission(True))
            rows=linux_capture.list_windows()
        self.assertEqual(rows[0]['id'],linux_capture.PORTAL)

    def test_portal_stream_coalesces_frames_reports_resize_and_stops_once(self):
        from PySide6.QtMultimedia import QVideoFrame
        frames=[];errors=[]
        with patch.object(linux_capture,'_multimedia',return_value=self.media()), patch.object(linux_capture,'permission'), patch.object(linux_capture,'is_wayland',return_value=True):
            c=linux_capture.LinuxWindowCapture(linux_capture.PORTAL,lambda im,stamp:frames.append(im),errors.append)
        try:
            self.assertIs(c.session.screen,c.capture)
            self.assertFalse(c.running)
            for color in ('red','blue'):
                im=QImage(80,40,QImage.Format.Format_RGB888);im.fill(QColor(color));c._frame(QVideoFrame(im))
            c._drain()
            self.assertEqual(len(frames),1);self.assertEqual(frames[0].getpixel((0,0)),(0,0,255))
            self.assertTrue(c.running);self.assertFalse(c.refresh_geometry())
            im=QImage(40,80,QImage.Format.Format_RGB888);im.fill(QColor('red'))
            c._frame(QVideoFrame(im));c._drain()
            self.assertTrue(c.refresh_geometry());self.assertFalse(c.refresh_geometry())
            c.capture.activeChanged.emit(False)
            self.assertEqual(len(errors),1);self.assertTrue(c.stopped)
            c._error(None,'late error');c._frame(QVideoFrame(im));c._drain()
            self.assertEqual(len(errors),1);self.assertEqual(len(frames),2)
        finally: c.stop()

    def test_portal_denial_or_start_timeout_finalizes_capture(self):
        for message in ('Permission denied','No capture frame received'):
            with self.subTest(message=message):
                errors=[]
                with patch.object(linux_capture,'_multimedia',return_value=self.media()), patch.object(linux_capture,'permission'), patch.object(linux_capture,'is_wayland',return_value=True):
                    c=linux_capture.LinuxWindowCapture(linux_capture.PORTAL,lambda *_:None,errors.append)
                c._error(None,message)
                self.assertTrue(c.stopped);self.assertFalse(c.timer.isActive())
                self.assertEqual(errors,[f'Linux capture: {message}'])
                c.stop()

    def test_studio_creates_linux_capture_on_gui_thread_and_waits_for_pixels(self):
        studio=Studio(ImageProvider(),start_worker=False)
        handles=[]
        class Capture:
            running=False
            def stop(self): pass
        def start(selection,on_frame,on_error):
            self.assertEqual(QThread.currentThread(),self.app.thread())
            handles.append(selection)
            return Capture()
        adapter=SimpleNamespace(GUI_THREAD=True,list_windows=lambda:[dict(id='opaque',app='Linux',title='Fixture')],create_capture=start)
        try:
            with patch('desktop.v2.capture.backend',return_value=adapter):
                studio.refreshWindows();studio.useWindow(0)
            self.assertEqual(handles,['opaque'])
            self.assertFalse(studio.screen['capturing']);self.assertFalse(studio.screen['canRecord'])
            studio.capture.running=True
            from PIL import Image
            import time
            studio.receive_native_frame(Image.new('RGB',(80,40)),time.monotonic(),studio.capture_generation)
            self.assertTrue(studio.screen['canRecord'])
            studio.stopCapture();self.assertFalse(studio.screen['canRecord'])
        finally: studio.close();self.app.processEvents()


if __name__=='__main__': unittest.main()
