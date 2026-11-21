"""Qt/FFmpeg capture: X11 windows or a user-approved Wayland portal stream.

All Qt capture objects belong to the GUI thread. One replaceable video frame
is converted at the requested rate; OCR and MP4 encoding remain independent.
"""
import os
import threading
import time

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, QThread, QTimer, Qt
from PySide6.QtGui import QGuiApplication, QImage

GUI_THREAD = True
PORTAL = 'wayland-portal'


def create_capture(window_id,on_frame,on_error):
    return LinuxWindowCapture(window_id,on_frame,on_error)


def is_wayland():
    return (os.environ.get('XDG_SESSION_TYPE', '').lower() == 'wayland' or
            bool(os.environ.get('WAYLAND_DISPLAY')) or
            bool(QGuiApplication.instance() and QGuiApplication.platformName().startswith('wayland')))


def _gui_thread():
    app = QGuiApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError('Linux capture must start on the GUI thread')


def _multimedia():
    os.environ.setdefault('QT_MEDIA_BACKEND', 'ffmpeg')
    # Qt 6.8 probes XDG_SESSION_TYPE rather than the actual Qt platform when
    # enabling X11 capture. Xvfb, VNC and manually started X sessions may omit
    # it. Infer it from the active connection, without bypassing Wayland.
    if (QGuiApplication.instance() and QGuiApplication.platformName() == 'xcb'
            and not is_wayland()):
        os.environ['XDG_SESSION_TYPE'] = 'x11'
    try:
        from PySide6 import QtMultimedia
        return QtMultimedia
    except ImportError as exc:
        raise RuntimeError('Install requirements-gui.txt for Linux capture (PySide6-Addons).') from exc


def permission(grant=False):
    _gui_thread()
    _multimedia()
    if is_wayland() and not QGuiApplication.platformName().startswith('wayland'):
        raise RuntimeError('Wayland sharing requires the Qt Wayland backend. Relaunch with QT_QPA_PLATFORM=wayland (use launch-linux.sh).')
    if not is_wayland() and QGuiApplication.platformName() != 'xcb':
        raise RuntimeError('No X11 desktop is available. Launch inside your Linux desktop session.')
    # A Wayland grant is made only in the OS picker when capture starts.
    return not is_wayland()


def list_windows():
    _gui_thread()
    media = _multimedia()
    permission()
    if is_wayland():
        return [dict(id=PORTAL, app='Wayland', title='Choose window / screen in desktop picker')]
    # QCapturableWindow is an opaque, registered Qt value, not a list index or
    # a title. Keeping the value preserves identity across moves and refreshes.
    return [dict(id=window, app='X11', title=window.description() or 'Untitled window')
            for window in media.QWindowCapture.capturableWindows() if window.isValid()]


def qimage_image(image):
    """Copy RGB bytes with Qt's row padding, independent of the video's lifetime."""
    if image.isNull():
        raise ValueError('Captured frame has no image')
    if image.width() > 1920 or image.height() > 1300:
        image = image.scaled(1920, 1300, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.FastTransformation)
    rgb = image.convertToFormat(QImage.Format.Format_RGB888)
    rows = np.frombuffer(rgb.constBits(), dtype=np.uint8, count=rgb.sizeInBytes()).reshape(rgb.height(), rgb.bytesPerLine())
    pixels = rows[:, :rgb.width()*3].reshape(rgb.height(), rgb.width(), 3).copy()
    return Image.fromarray(pixels)


class LinuxWindowCapture(QObject):
    def __init__(self, window_id, on_frame, on_error, fps=20):
        _gui_thread()
        super().__init__()
        media = _multimedia()
        permission()
        self.callback, self.on_error = on_frame, on_error
        self.running = False
        self.stopped = False
        self._latest = None
        self._frame_lock = threading.Lock()
        self._size = None
        self._resized = False
        self.portal = is_wayland()
        self.session = media.QMediaCaptureSession(self)
        self.sink = media.QVideoSink(self)
        self.session.setVideoSink(self.sink)
        if self.portal:
            if window_id != PORTAL:
                raise RuntimeError('Refresh sources and choose the Wayland desktop picker')
            self.capture = media.QScreenCapture(self)
            self.session.setScreenCapture(self.capture)
        else:
            if not isinstance(window_id, media.QCapturableWindow) or not window_id.isValid():
                raise RuntimeError('The selected X11 window is no longer available; refresh windows')
            self.capture = media.QWindowCapture(self)
            self.capture.setWindow(window_id)
            self.session.setWindowCapture(self.capture)
        self.capture.errorOccurred.connect(self._error, Qt.ConnectionType.QueuedConnection)
        self.capture.activeChanged.connect(self._active, Qt.ConnectionType.QueuedConnection)
        # Replace a Qt value in the producer thread instead of queuing one GUI
        # event (and retaining a full video frame) for every screen refresh.
        self.sink.videoFrameChanged.connect(self._frame, Qt.ConnectionType.DirectConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(max(1, round(1000/max(1, min(30, fps)))))
        self.timer.timeout.connect(self._drain)
        self.timer.start()
        self.start_timer = QTimer(self)
        self.start_timer.setSingleShot(True)
        self.start_timer.timeout.connect(lambda: self._error(None, 'No capture frame received. Check the sharing picker, PipeWire and your desktop portal, or refresh the X11 window.'))
        self.start_timer.start(60000)
        self.capture.start()

    def _active(self, active):
        if not active and self.running and not self.stopped:
            self._error(None, 'Desktop sharing ended. Start capture again to choose a source.')

    def _error(self, error, message):
        if self.stopped:
            return
        self.stop()
        self.on_error(f'Linux capture: {message}')

    def _frame(self, frame):
        from PySide6.QtMultimedia import QVideoFrame
        with self._frame_lock:
            if not self.stopped and frame.isValid():
                self._latest = (QVideoFrame(frame), time.monotonic())

    def _drain(self):
        with self._frame_lock:
            if self.stopped or self._latest is None:
                return
            frame, stamp = self._latest
            self._latest = None
        try:
            image = qimage_image(frame.toImage())
            self._resized |= self._size is not None and image.size != self._size
            self._size = image.size
            self.running = True
            self.start_timer.stop()
            self.callback(image, stamp)
        except Exception as exc:
            self._error(None, str(exc))

    def refresh_geometry(self):
        # Frame dimensions come from the stream; no desktop coordinates or
        # GUI objects are read by Studio's background geometry poll.
        changed, self._resized = self._resized, False
        return changed

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.running = False
        self.timer.stop()
        self.start_timer.stop()
        with self._frame_lock:
            self._latest = None
        self.capture.stop()
        self.session.setVideoSink(None)
        if self.portal:
            self.session.setScreenCapture(None)
        else:
            self.session.setWindowCapture(None)
        self.deleteLater()
