"""Qt Quick macOS Vision Studio. Recognition runs in a bounded worker process."""
from dataclasses import asdict
from pathlib import Path
import json,sys,time,threading,shutil
from collections import deque
import numpy as np
from PIL import Image
from PySide6.QtCore import QObject,Signal,Slot,Property,QTimer,QStandardPaths,QUrl,Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication,QFileDialog
from .vision import crop
from .v2.layout import Layout,propose_cards,Registration
from .v2.reader import critical_keys,readiness,digest
from .v2.state import Tracker,Field
from .v2.ocr import decode_text
from .v2.runtime import VisionProcess
from .v2.metrics import Metrics
from .v2.replay import Recorder,load_session
from .v2.demo import sample_frames


class ImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.image=QImage();self.lock=threading.Lock()
    def set(self,image):
        rgb=image.convert('RGB');data=rgb.tobytes()
        q=QImage(data,rgb.width,rgb.height,rgb.width*3,QImage.Format.Format_RGB888).copy()
        with self.lock:self.image=q
    def requestImage(self,id,size,requestedSize):
        with self.lock:q=self.image
        if size is not None:size.setWidth(q.width());size.setHeight(q.height())
        return q


class Studio(QObject):
    changed=Signal()
    pictureChanged=Signal()
    frameSignal=Signal(object,float,int)
    errorSignal=Signal(str)
    asyncSignal=Signal(object)
    heartbeat=Signal(float)

    def __init__(self,provider,backend='auto',start_worker=True):
        super().__init__();self.provider=provider;self.backend=backend;self.start_worker=start_worker
        base=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))/'VisionStudio'
        self.base=base;self.folder=base/'layouts'/'current';self.folder.mkdir(parents=True,exist_ok=True)
        self.frame_ring={}
        self.layout=Layout();self.tracker=Tracker();self.metrics=Metrics();self.snapshot=None
        self.worker=None;self.capture=None;self.capture_generation=0;self.selected_window=None;self.last_image=None;self.frame_id=0;self.picture_id=0;self.epoch=0;self.static_confirmed=False
        self.source='Practice replay';self.live=False;self.playing=False;self.recording=False
        self.note='Preparing the six-max vision demo';self.engine='Preparing OCR';self.selected='hole_1'
        self.windows=[];self.replay_rows=[];self.replay_folder=None;self.replay_index=0;self.demo=[]
        self.pending=True;self.latest_hashes={};self.accepted_hashes={}
        self.recorder=None;self.record_pending=False;self.last_record_signature='';self.overrides={}
        self.frameSignal.connect(self.receive_native_frame,Qt.ConnectionType.QueuedConnection)
        self.errorSignal.connect(self.set_error,Qt.ConnectionType.QueuedConnection)
        self.asyncSignal.connect(self.finish_async,Qt.ConnectionType.QueuedConnection)
        self.heartbeat.connect(self.ui_pulse,Qt.ConnectionType.QueuedConnection)
        self.ui_epoch=time.monotonic()+1.
        self.stop_event=threading.Event()
        def pulse():
            while not self.stop_event.wait(.1):self.heartbeat.emit(time.monotonic())
        threading.Thread(target=pulse,daemon=True).start()
        self.poll_timer=QTimer(self);self.poll_timer.setInterval(25);self.poll_timer.timeout.connect(self.poll);self.poll_timer.start()
        self.age_timer=QTimer(self);self.age_timer.setInterval(200);self.age_timer.timeout.connect(self.changed);self.age_timer.start()
        self.play_timer=QTimer(self);self.play_timer.setInterval(1600);self.play_timer.timeout.connect(self.stepForward)
        self.geometry_timer=QTimer(self);self.geometry_timer.setInterval(1000);self.geometry_timer.timeout.connect(self.refresh_geometry)
        self.geometry_busy=False
        self.loadDemo()

    @Property(str,notify=pictureChanged)
    def imageSource(self):return f'image://table/frame/{self.picture_id}'

    @Property('QVariantMap',notify=changed)
    def info(self):
        snap=self.snapshot;metrics=self.metrics.summary()
        label,missing=readiness(snap,self.layout) if snap else ('Waiting for a frame',critical_keys(self.layout))
        if self.pending and snap:label='Table changed · reading'
        if self.live and snap and time.monotonic()-snap.captured_at>2:
            label='Snapshot expired'
        if self.worker is None and self.start_worker:label='Vision paused'
        age=(time.monotonic()-snap.captured_at)*1000 if snap else None
        return {'source':self.source,'live':self.live,'playing':self.playing,'recording':self.recording,
                'status':label,'note':self.note,'engine':self.engine,'frame':self.frame_id,
                'age':round(age) if age is not None else -1,'readMs':round(snap.read_ms,1) if snap else -1,
                'required':len(critical_keys(self.layout)),'missing':len(missing),'fields':len(self.layout.specs),
                'read':sum(f.known for f in snap.fields.values()) if snap else 0,
                'calibrated':len(self.layout.confirmed),'seats':self.layout.seats,'hero':self.layout.hero,
                'historyComplete':False,'stable':bool(snap and snap.stable),'metrics':metrics,
                'replayCount':len(self.demo or self.replay_rows),'replayIndex':self.replay_index,
                'layout':self.layout.name,'selected':self.selected,'platformMac':sys.platform=='darwin'}

    @Property('QVariantList',notify=changed)
    def fields(self):
        rows=[]
        for s in self.layout.specs:
            f=self.snapshot.fields.get(s['key']) if self.snapshot else None
            value=f.value if f and f.known else None
            shown=('ON' if value else 'OFF') if isinstance(value,bool) else ('—' if value is None else str(value))
            rows.append({**s,'display':shown,'quality':('stale' if not self.observation_current() else f.quality) if f else 'unknown',
                         'score':round(f.score,2) if f else 0,'reason':('Reading changed or expired; awaiting recognition' if not self.observation_current() else f.reason) if f else 'Not read yet',
                         'cached':bool(f and f.cached),'region':s['key'] in self.layout.regions,
                         'confirmed':s['key'] in self.layout.confirmed})
        return rows

    @Property('QVariantList',notify=changed)
    def regions(self):
        return [{'key':k,'x':r[0],'y':r[1],'w':r[2],'h':r[3],
                 'confirmed':k in self.layout.confirmed,'known':bool(self.snapshot and k in self.snapshot.fields and self.snapshot.fields[k].known)}
                for k,r in self.layout.regions.items()]

    @Property('QVariantList',notify=changed)
    def players(self):
        rows=[]
        for i in range(self.layout.seats):
            def val(k,default='—'):return self.snapshot.value(f'seat_{i}_{k}',default) if self.observation_current() else default
            rows.append({'seat':i+1,'name':str(val('name',f'Seat {i+1}')),'stack':str(val('stack')),
                         'bet':str(val('bet')),'status':str(val('status','unknown')),
                         'dealer':val('dealer',False) is True,'hero':i==self.layout.hero})
        return rows

    @Property('QVariantList',notify=changed)
    def events(self):return list(reversed(self.tracker.events[-40:]))

    @Property('QVariantList',notify=changed)
    def windowRows(self):return self.windows

    @Property('QVariantMap',notify=changed)
    def values(self):
        return {k:f.value for k,f in self.snapshot.fields.items() if f.known} if self.observation_current() else {}

    def observation_current(self):
        return bool(self.snapshot and not self.pending and (not self.live or time.monotonic()-self.snapshot.captured_at<=2))

    def observation_export(self):
        if not self.snapshot:return None
        label,missing=readiness(self.snapshot,self.layout)
        return {'snapshot':self.snapshot.to_dict(),'events':self.tracker.events,'metrics':self.metrics.summary(),
                'validity':{'current':self.observation_current(),'pixels_changed':self.pending,
                            'source_age_ms':round((time.monotonic()-self.snapshot.captured_at)*1000),
                            'readiness':label,'missing_critical_fields':missing},
                'exported_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

    @Slot(float)
    def ui_pulse(self,stamp):
        if stamp>=self.ui_epoch:self.metrics.dispatch.append((time.monotonic()-stamp)*1000)

    def async_job(self,fn,done):
        def run():
            try:result,error=fn(),None
            except Exception as exc:result,error=None,f'{type(exc).__name__}: {exc}'
            self.asyncSignal.emit((done,result,error))
        threading.Thread(target=run,daemon=True).start()

    @Slot(object)
    def finish_async(self,payload):
        callback,result,error=payload;callback(result,error)

    def restart_reader(self):
        if self.recording:self.recording=False;self.recorder=None;self.note="Recording saved; layout changed"
        if self.worker:self.worker.stop()
        self.epoch+=1;self.snapshot=None;self.pending=True;self.accepted_hashes={};self.tracker.reset();self.overrides={}
        self.worker=VisionProcess(self.layout,self.folder,self.backend,self.epoch) if self.start_worker else None
        if self.last_image is not None:self.submit()
        self.changed.emit()

    def submit(self):
        if self.worker and self.last_image is not None:
            self.worker.submit(self.last_image,self.frame_id,self.last_stamp,self.source)

    @Slot(object,float,int)
    def receive_native_frame(self,image,stamp,generation):
        if generation==self.capture_generation and self.live:self.receive_frame(image,stamp)

    @Slot(object,float)
    def receive_frame(self,image,stamp):
        self.frame_id+=1;self.last_stamp=stamp;self.last_image=image
        self.frame_ring[self.frame_id]=image
        while len(self.frame_ring)>12:self.frame_ring.pop(next(iter(self.frame_ring)))
        try:self.latest_hashes={k:digest(crop(image,self.layout.regions[k])) for k in critical_keys(self.layout) if k in self.layout.regions}
        except ValueError:self.latest_hashes={}
        self.pending=self.latest_hashes!=self.accepted_hashes or self.snapshot is None
        self.provider.set(image);self.picture_id+=1;self.pictureChanged.emit();self.metrics.frames+=1
        self.changed.emit()
        self.static_confirmed=False;self.submit()

    @Slot()
    def poll(self):
        if not self.worker:return
        for msg in self.worker.poll():
            if 'engine' in msg:self.engine=msg['engine'];self.changed.emit()
            if 'error' in msg:
                self.metrics.timeouts+=1;self.snapshot=None;self.note=msg['error'];self.changed.emit()
            snap=msg.get('snapshot')
            if snap is None:continue
            if msg['epoch']!=self.epoch or (self.snapshot and snap.frame_id<=self.snapshot.frame_id):continue
            age=(time.monotonic()-snap.captured_at)*1000
            if self.live and age>2000:self.metrics.stale+=1;continue
            if self.latest_hashes!=msg.get('raw_hashes',{}):
                self.metrics.stale+=1;continue
            self.accepted_hashes=msg.get('raw_hashes',{});self.pending=False
            for key,(signature,value) in list(self.overrides.items()):
                if msg['hashes'].get(key)==signature:snap.fields[key]=Field(key,value,'confirmed',1.,'Manually corrected',snap.captured_at)
                else:self.overrides.pop(key,None)
            self.tracker.accept(snap,self.layout.seats,self.layout.hero);self.snapshot=snap
            if not self.live and not self.static_confirmed:
                self.static_confirmed=True
                QTimer.singleShot(70,self.confirm_static)
            self.metrics.processing.append(snap.read_ms);self.metrics.age.append(age)
            self.metrics.ocr_calls+=snap.ocr_calls;self.metrics.cache_hits+=snap.cache_hits
            label,missing=readiness(snap,self.layout)
            if missing or snap.issues:self.metrics.incomplete+=1
            else:self.metrics.accepted+=1
            if self.recorder and not self.record_pending and snap.frame_id in self.frame_ring and snap.fingerprint()!=self.last_record_signature:
                self.record_pending=True;self.last_record_signature=snap.fingerprint();rec=self.recorder;im=self.frame_ring[snap.frame_id]
                def done(result,error):
                    self.record_pending=False
                    if error:self.recording=False;self.recorder=None;self.note=error
                    self.changed.emit()
                self.async_job(lambda rec=rec,im=im,snap=snap:rec.add(im,snap),done)
            self.changed.emit()

    def confirm_static(self):
        if self.last_image is not None and not self.live:
            self.frame_id+=1;self.last_stamp=time.monotonic();self.frame_ring[self.frame_id]=self.last_image;self.submit()

    @Slot(str)
    def selectField(self,key):self.selected=key;self.changed.emit()

    @Slot(float,float,float,float)
    def drawRegion(self,x,y,w,h):
        from .v2.layout import validate_rect
        try:
            rect=[x,y,w,h];validate_rect(rect)
            if self.selected=='__anchor__':
                if self.last_image is None:return
                path=self.folder/'anchor.png';crop(self.last_image,rect).save(path)
                self.layout.anchor='anchor.png';self.layout.anchor_rect=rect;self.layout.reference_size=list(self.last_image.size)
                self.note='Anchor saved. Uniform resizing is checked; unsupported layouts pause recognition.'
            else:
                self.layout.regions[self.selected]=rect
                if self.selected not in self.layout.confirmed:self.layout.confirmed.append(self.selected)
                self.note=f'{self.selected.replace("_"," ")} calibrated'
            self.restart_reader()
        except (ValueError,OSError) as exc:self.set_error(str(exc))

    @Slot()
    def propose(self):
        if self.last_image is None:return
        regions=propose_cards(self.last_image)
        self.layout.regions.update(regions)
        self.layout.confirmed=[k for k in self.layout.confirmed if k not in regions]
        self.note=f'{len(regions)} card regions proposed. Confirm or adjust each; other fields need calibration.'
        self.restart_reader()

    @Slot()
    def confirmRegion(self):
        if self.selected in self.layout.regions and self.selected not in self.layout.confirmed:self.layout.confirmed.append(self.selected)
        self.restart_reader()

    @Slot()
    def removeRegion(self):
        self.layout.regions.pop(self.selected,None)
        self.layout.confirmed=[k for k in self.layout.confirmed if k!=self.selected]
        self.restart_reader()

    @Slot(str)
    def teach(self,label):
        if self.last_image is None or self.selected not in self.layout.regions:
            self.set_error('Select a calibrated region first');return
        try:
            spec=next(s for s in self.layout.specs if s['key']==self.selected)
            kind=spec['kind'];key=self.selected
            if kind in ('card','board'):
                from .model import cards
                parsed=cards(label)
                if len(parsed)!=1:raise ValueError('Enter one card, such as As')
                label=parsed[0];key='cards'
            elif kind=='status':
                if label not in ('active','folded','all-in','empty'):raise ValueError('Use active, folded, all-in, or empty')
            elif kind in ('turn','dealer','control'):
                if label not in ('true','false'):raise ValueError('Use true or false')
            else:raise ValueError('Teach is for cards or visual indicators; correct numeric fields directly')
            assets=self.folder/'templates';assets.mkdir(exist_ok=True)
            rel=f'templates/{key}_{label}.png'
            crop(self.last_image,self.layout.regions[self.selected]).save(self.folder/rel)
            self.layout.templates.setdefault(key,{})[label]=rel
            self.note='Visual example saved locally';self.restart_reader()
        except (ValueError,OSError,StopIteration) as exc:self.set_error(str(exc))

    @Slot()
    def teachBlank(self):
        if not self.selected.startswith('board_') or self.selected not in self.layout.regions or self.last_image is None:
            self.set_error('Select an empty board slot first');return
        rel=f'{self.selected}_blank.png';crop(self.last_image,self.layout.regions[self.selected]).save(self.folder/rel)
        self.layout.blank_board[self.selected]=rel;self.note='Empty-slot appearance learned';self.restart_reader()

    @Slot(str)
    def correct(self,value):
        if not self.observation_current() or self.selected not in self.layout.regions:
            self.set_error('Wait for a current reading before correcting it');return
        try:
            spec=next(s for s in self.layout.specs if s['key']==self.selected)
            if spec['kind'] in ('card','board'):
                from .model import cards
                parsed=cards(value)
                decoded=parsed[0] if len(parsed)==1 else None if not parsed and spec['kind']=='board' else (_ for _ in ()).throw(ValueError('Enter one card'))
            elif spec['kind'] in ('turn','dealer','control'):
                if value.lower() not in ('true','false'):raise ValueError('Enter true or false')
                decoded=value.lower()=='true'
            else:decoded=decode_text(value,spec['kind'],self.layout.scale)
            im,_,_=Registration(self.layout,self.folder).align(self.last_image)
            signature=digest(crop(im,self.layout.regions[self.selected]))
            self.overrides[self.selected]=(signature,decoded)
            self.snapshot.fields[self.selected]=Field(self.selected,decoded,'confirmed',1.,'Manual correction',time.monotonic())
            from .v2.state import validate_snapshot
            validate_snapshot(self.snapshot,self.layout.seats,self.layout.hero)
            self.note='Correction applies only while those pixels remain unchanged';self.changed.emit()
        except (ValueError,OSError) as exc:self.set_error(str(exc))

    @Slot(int,int,int)
    def configure(self,seats,hero,scale):
        if not 2<=seats<=9 or not 0<=hero<seats or not 1<=scale<=10000:return
        self.layout.seats=seats;self.layout.hero=hero;self.layout.scale=scale
        allowed={s['key'] for s in self.layout.specs}
        self.layout.regions={k:v for k,v in self.layout.regions.items() if k in allowed}
        self.layout.confirmed=[k for k in self.layout.confirmed if k in allowed]
        self.restart_reader()

    def stop_source(self):
        self.capture_generation+=1
        self.play_timer.stop();self.playing=False;self.geometry_timer.stop()
        if self.capture:self.capture.stop();self.capture=None

    @Slot()
    def pause(self):self.stop_source();self.changed.emit()

    @Slot()
    def loadDemo(self):
        self.stop_source();self.live=False;self.source='Practice replay';self.replay_index=0
        self.folder=self.base/'layouts'/'current';self.folder.mkdir(parents=True,exist_ok=True)
        self.demo=sample_frames(12);self.replay_rows=[]
        image,self.layout,_=self.demo[0]
        self.last_image=image;self.last_stamp=time.monotonic();self.frame_id+=1
        self.frame_ring[self.frame_id]=image;self.static_confirmed=False
        self.metrics.frames+=1
        self.latest_hashes={k:digest(crop(image,self.layout.regions[k])) for k in critical_keys(self.layout)}
        self.provider.set(image);self.picture_id+=1;self.pictureChanged.emit()
        self.note='Actual image recognition of a generated table. No strategy runs in this view.'
        self.restart_reader()

    @Slot()
    def stepForward(self):self.seek((self.replay_index+1)%max(1,len(self.demo or self.replay_rows)))

    @Slot(int)
    def seek(self,index):
        rows=self.demo or self.replay_rows
        if not rows:return
        index=max(0,min(len(rows)-1,index));backwards=index<self.replay_index;self.replay_index=index
        if backwards:self.tracker.reset()
        image=rows[index][0] if self.demo else Image.open(self.replay_folder/rows[index]['image']).convert('RGB')
        self.receive_frame(image,time.monotonic());self.changed.emit()

    @Slot()
    def togglePlay(self):
        if self.live:
            if self.capture:self.pause()
            else:self.resume_capture()
            return
        if self.play_timer.isActive():self.play_timer.stop();self.playing=False
        else:self.play_timer.start();self.playing=True
        self.changed.emit()

    @Slot()
    def openImage(self):
        name,_=QFileDialog.getOpenFileName(None,'Open a table image','','Images (*.png *.jpg *.jpeg *.webp)')
        if name:
            try:
                image=Image.open(name).convert('RGB')
                if image.width*image.height>40_000_000:raise ValueError('Image is too large')
                self.stop_source();self.live=False;self.source='Image review';self.demo=[];self.replay_rows=[]
                self.recorder=None;self.recording=False;self.tracker.reset();self.snapshot=None
                self.receive_frame(image,time.monotonic());self.note='Image loaded. Calibrate the layout before trusting readings.';self.changed.emit()
            except (ValueError,OSError) as exc:self.set_error(str(exc))

    @Slot()
    def openReplay(self):
        name,_=QFileDialog.getOpenFileName(None,'Open a replay session','','Session JSON (*.json)')
        if not name:return
        try:
            data=load_session(name);self.stop_source();self.live=False;self.source='Recorded replay'
            self.demo=[];self.replay_rows=data['frames'];self.replay_folder=Path(name).parent
            self.layout=Layout(**data['layout']);self.layout.validate(self.replay_folder)
            self.folder=self.replay_folder;self.last_image=None;self.restart_reader();self.seek(0)
            self.note='Recorded observations are not benchmark ground truth';self.changed.emit()
        except (ValueError,OSError,TypeError) as exc:self.set_error(str(exc))

    @Slot()
    def saveLayout(self):
        name,_=QFileDialog.getSaveFileName(None,'Save table layout',str(self.folder/'layout.json'),'Layout JSON (*.json)')
        if not name:return
        try:
            dest=Path(name);dest.parent.mkdir(parents=True,exist_ok=True)
            paths=[p for bank in self.layout.templates.values() for p in bank.values()]+list(self.layout.blank_board.values())+([self.layout.anchor] if self.layout.anchor else [])
            for rel in paths:
                target=dest.parent/rel
                if target.resolve()!=(self.folder/rel).resolve():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(self.folder/rel,target)
            self.layout.save(dest);self.folder=dest.parent;self.note='Layout and visual examples saved';self.changed.emit()
        except OSError as exc:self.set_error(str(exc))

    @Slot()
    def loadLayout(self):
        name,_=QFileDialog.getOpenFileName(None,'Load table layout','','Layout JSON (*.json)')
        if not name:return
        try:
            self.layout=Layout.load(name);self.folder=Path(name).parent
            self.note='Layout loaded. Check the overlay against the chosen window.';self.restart_reader()
        except (ValueError,OSError,TypeError) as exc:self.set_error(str(exc))

    @Slot()
    def refreshWindows(self):
        from .v2.mac_capture import list_windows
        def done(rows,error):
            if error:self.set_error(error)
            else:self.windows=rows;self.note=f'{len(rows)} Mac windows available';self.changed.emit()
        self.async_job(list_windows,done)

    @Slot()
    def requestPermission(self):
        try:
            from .v2.mac_capture import permission
            granted=permission(True);self.note='Permission granted; refresh windows' if granted else 'Allow Screen Recording in System Settings, then relaunch'
            self.changed.emit()
        except RuntimeError as exc:self.set_error(str(exc))

    @Slot(int)
    def useWindow(self,index):
        if not 0<=index<len(self.windows):return
        self.stop_source();self.demo=[];self.replay_rows=[];self.live=True
        selected=self.windows[index];self.selected_window=selected;self.source=selected['app']+' · '+selected['title']
        self.layout=Layout(name=selected['app']+' table');self.folder=self.base/'layouts'/'current';self.folder.mkdir(parents=True,exist_ok=True)
        self.last_image=None;self.restart_reader()
        self.resume_capture()

    def resume_capture(self):
        if not self.selected_window:return
        selected=self.selected_window
        generation=self.capture_generation
        def start():
            from .v2.mac_capture import MacWindowCapture
            return MacWindowCapture(selected['id'],lambda image,stamp:self.frameSignal.emit(image,stamp,generation),self.errorSignal.emit)
        def done(capture,error):
            if generation!=self.capture_generation:
                if capture:capture.stop()
                return
            if error:self.set_error(error)
            else:self.capture=capture;self.playing=True;self.geometry_timer.start();self.note='Window capture active. Check your layout overlay.';self.changed.emit()
        self.async_job(start,done)

    def refresh_geometry(self):
        if not self.capture or self.geometry_busy:return
        capture=self.capture;self.geometry_busy=True
        def done(changed,error):
            self.geometry_busy=False
            if self.capture is not capture:return
            if error:self.pause();self.set_error(error)
            elif changed:self.snapshot=None;self.note='Window resized; verifying the registered layout';self.changed.emit()
        self.async_job(capture.refresh_geometry,done)

    @Slot()
    def toggleRecord(self):
        if self.recording:self.recorder=None;self.recording=False;self.note='Recording saved locally'
        else:
            folder=self.base/'sessions'/time.strftime('%Y%m%d-%H%M%S')
            self.recorder=Recorder(folder,self.layout);self.recording=True;self.last_record_signature=''
            # Copy all visual assets alongside the session's versioned layout.
            paths=[p for bank in self.layout.templates.values() for p in bank.values()]+list(self.layout.blank_board.values())+([self.layout.anchor] if self.layout.anchor else [])
            for rel in paths:
                target=folder/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(self.folder/rel,target)
            self.note='Recording locally. Exported reader output is not ground truth.'
        self.changed.emit()

    @Slot()
    def exportState(self):
        if not self.snapshot:return
        name,_=QFileDialog.getSaveFileName(None,'Export observed table state','table_state.json','JSON (*.json)')
        if name:
            Path(name).write_text(json.dumps(self.observation_export(),indent=2)+'\n')
            self.note='Versioned table state exported';self.changed.emit()

    @Slot()
    def exportMetrics(self):
        name,_=QFileDialog.getSaveFileName(None,'Export measured timings','vision_timings.json','JSON (*.json)')
        if name:Path(name).write_text(json.dumps(self.metrics.summary(),indent=2)+'\n');self.note='Timing report exported';self.changed.emit()

    @Slot(str)
    def set_error(self,message):self.note=message;self.changed.emit()

    def close(self):
        self.stop_source();self.stop_event.set();self.poll_timer.stop();self.age_timer.stop()
        if self.worker:self.worker.stop();self.worker=None


def main(backend='auto'):
    from PySide6.QtQuickControls2 import QQuickStyle
    QQuickStyle.setStyle('Basic')
    import multiprocessing
    multiprocessing.freeze_support()
    app=QApplication(sys.argv);app.setApplicationName('PokerLab Vision Studio');app.setOrganizationName('PokerLab')
    engine=QQmlApplicationEngine();provider=ImageProvider();engine.addImageProvider('table',provider)
    controller=Studio(provider,backend)
    engine.rootContext().setContextProperty('studio',controller)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('qml')/'Studio.qml')))
    if not engine.rootObjects():controller.close();raise SystemExit('The Studio interface could not be loaded')
    app.aboutToQuit.connect(controller.close)
    app.exec()
