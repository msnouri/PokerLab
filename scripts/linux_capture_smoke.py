"""Capture a real X11 fixture window, resize/move it, and decode its MP4.

Run in Xvfb + a window manager in Linux CI. No external game or account is used.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QLabel
import cv2
from desktop.studio import Studio,ImageProvider


def main():
    app=QApplication([])
    if app.platformName()!='xcb': raise RuntimeError('Run with QT_QPA_PLATFORM=xcb under X11/Xvfb')
    fixture=QLabel('PokerLab native Linux capture fixture')
    fixture.setWindowTitle('PokerLab X11 capture test')
    fixture.setStyleSheet('background:#e02028;color:white;font-size:18px;')
    fixture.resize(640,420);fixture.move(80,80);fixture.show()
    studio=Studio(ImageProvider(),start_worker=False)
    def wait(predicate,seconds=15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            app.processEvents()
            if predicate(): return
            time.sleep(.01)
        raise AssertionError(f'Capture timeout: {studio.note}')
    def color(expected):
        if studio.last_image is None:return False
        image=studio.last_image
        pixel=image.getpixel((image.width//10,image.height//4))
        return max(abs(a-b) for a,b in zip(pixel,expected))<15
    output=Path(os.environ.get('LINUX_CAPTURE_REPORT','linux-capture-smoke.json'))
    try:
        wait(lambda: fixture.windowHandle() is not None and fixture.windowHandle().isExposed())
        def discover():
            studio.refreshWindows()
            return any('PokerLab X11 capture test' in r['title'] for r in studio.windows)
        wait(discover)
        print('Discovered visible X11 fixture',flush=True)
        index=next(i for i,r in enumerate(studio.windows) if 'PokerLab X11 capture test' in r['title'])
        studio.useWindow(index)
        wait(lambda: studio.screen['canRecord'] and color((224,32,40)))
        print('Captured correct source pixels',flush=True)
        initial_size=studio.last_image.size
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'x11.mp4';studio.start_video(path)
            recorder=studio.video
            wait(lambda: recorder.frames>=2)
            fixture.resize(480,320);fixture.setStyleSheet('background:#2030e0;color:white;font-size:18px;')
            wait(lambda: studio.last_image.size!=initial_size and color((32,48,224)))
            print('Captured resized window',flush=True)
            fixture.move(180,100);fixture.setStyleSheet('background:#20c050;color:white;font-size:18px;')
            wait(lambda: color((32,192,80)))
            print('Captured moved window',flush=True)
            wait(lambda: recorder.frames>=4)
            studio.pause();wait(lambda: studio.video is None)
            cap=cv2.VideoCapture(str(path));decoded=0
            try:
                while True:
                    ok,_=cap.read()
                    if not ok:break
                    decoded+=1
            finally:cap.release()
            metadata=json.loads(path.with_suffix('.capture.json').read_text())
            assert decoded==metadata['frames'] and decoded>=4
            assert not metadata['error'],metadata['error']
            assert not studio.screen['canRecord']
            studio.togglePlay();wait(lambda: studio.screen['canRecord'])
            fixture.close()
            wait(lambda: not studio.playing)
            report=dict(passed=True,backend='Qt FFmpeg / X11',initial_size=initial_size,
                        video_frames=decoded,resize=True,move=True,resume=True,closed_window_stops=True,
                        scope='Real local X11 fixture window; no Wayland portal or external table validation.')
            output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    finally:
        studio.close();fixture.close();app.processEvents()


if __name__=='__main__':main()
