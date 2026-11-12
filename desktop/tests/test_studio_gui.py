import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
import time,unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl,QCoreApplication,QEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from desktop.studio import Studio,ImageProvider


class StudioGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        QQuickStyle.setStyle('Basic')

    def setUp(self):
        self.engine=QQmlApplicationEngine();self.provider=ImageProvider()
        self.engine.addImageProvider('table',self.provider)
        self.studio=Studio(self.provider,start_worker=False)
        self.engine.rootContext().setContextProperty('studio',self.studio)
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'qml'/'Studio.qml')))
        self.assertEqual(len(self.engine.rootObjects()),1)
        self.window=self.engine.rootObjects()[0]
        self.window.setWidth(1580);self.window.setHeight(1020)
        for _ in range(5):self.app.processEvents()

    def tearDown(self):
        self.studio.close();self.window.close()
        self.engine.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def test_every_view_renders(self):
        for page in range(4):
            self.window.setProperty('page',page)
            for _ in range(4):self.app.processEvents()
            image=self.window.grabWindow()
            self.assertFalse(image.isNull())
            self.assertGreater(image.width(),1200)

    def test_proposal_requires_confirmation(self):
        self.studio.propose()
        self.assertIn('hole_1',self.studio.layout.regions)
        self.assertNotIn('hole_1',self.studio.layout.confirmed)
        self.studio.selectField('hole_1');self.studio.confirmRegion()
        self.assertIn('hole_1',self.studio.layout.confirmed)

    def test_old_native_source_is_ignored(self):
        image=self.studio.last_image
        old=self.studio.frame_id
        self.studio.live=True;self.studio.capture_generation=10
        self.studio.receive_native_frame(image,time.monotonic(),9)
        self.assertEqual(self.studio.frame_id,old)

    def test_capture_burst_delivers_only_newest_frame(self):
        old=self.studio.frame_id;self.studio.live=True;self.studio.capture_generation=10
        stamp=time.monotonic()
        for i in range(8):self.studio.enqueue_native_frame(self.studio.last_image,stamp+i*.001,10)
        self.app.processEvents()
        self.assertEqual(self.studio.frame_id,old+1)
        self.assertAlmostEqual(self.studio.last_stamp,stamp+.007)
        self.assertIsNone(self.studio.capture_latest)

    def test_changed_pixels_invalidate_visible_values(self):
        from desktop.v2.state import Snapshot,Field
        self.studio.snapshot=Snapshot(0,time.monotonic(),'test',{'pot':Field('pot',100,'read',1)})
        self.studio.pending=False
        self.assertEqual(self.studio.values['pot'],100)
        self.studio.receive_frame(self.studio.last_image,time.monotonic())
        self.assertTrue(self.studio.pending);self.assertEqual(self.studio.values,{})

    def test_live_expiry_withholds_values_and_export_marks_age(self):
        from desktop.v2.state import Snapshot,Field
        self.studio.snapshot=Snapshot(1,time.monotonic()-6,'test',{'pot':Field('pot',100,'read',1)})
        self.studio.pending=False;self.studio.live=True;self.studio.playing=True
        self.assertEqual(self.studio.values,{})
        self.assertFalse(self.studio.observation_export()['validity']['current'])

    def test_paused_capture_can_be_read_without_claiming_freshness(self):
        from desktop.v2.state import Snapshot,Field
        snap=Snapshot(self.studio.frame_id,time.monotonic()-10,'paused',{'pot':Field('pot',100,'read',1)})
        message={'snapshot':snap,'epoch':self.studio.epoch,'raw_hashes':self.studio.latest_hashes,'hashes':{}}
        class FakeWorker:
            def poll(self):return [message]
            def stop(self):pass
        self.studio.worker=FakeWorker();self.studio.live=True;self.studio.playing=False
        self.studio.poll()
        self.assertIs(self.studio.snapshot,snap)
        self.assertFalse(self.studio.observation_export()['validity']['current'])
        self.assertIn('Paused',self.studio.info['status'])


if __name__=='__main__':unittest.main()
