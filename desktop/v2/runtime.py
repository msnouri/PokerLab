"""One persistent vision process, one pending frame, bounded deadlines."""
from dataclasses import asdict
import multiprocessing as mp
import queue,time
from PIL import Image
from .layout import Layout
from .reader import IncrementalReader,critical_keys,digest
from ..vision import crop


def worker(inputs,outputs,layout_data,folder,backend):
    reader=None
    try:
        reader=IncrementalReader(Layout(**layout_data),folder,backend)
        outputs.put({'engine':reader.engine.name})
        while True:
            job=inputs.get()
            if job is None:break
            outputs.put({'started':job['id'],'at':time.monotonic()})
            image=Image.frombytes('RGB',tuple(job['size']),job['pixels'])
            raw_hashes={k:digest(crop(image,reader.layout.regions[k])) for k in critical_keys(reader.layout) if k in reader.layout.regions}
            snap,hashes=reader.read(image,job['id'],job['at'],job['source'])
            outputs.put({'snapshot':snap,'hashes':hashes,'raw_hashes':raw_hashes,'epoch':job['epoch']})
    except Exception as exc:outputs.put({'error':f'{type(exc).__name__}: {exc}'})
    finally:
        if reader:reader.close()


class VisionProcess:
    def __init__(self,layout,folder,backend='auto',epoch=0):
        self.layout=layout;self.folder=str(folder);self.backend=backend;self.epoch=epoch
        self.ctx=mp.get_context('spawn');self.process=None
        self.replaced=0;self.restarts=0;self.active_at=None;self.pending=None;self.busy=False;self.ready=False;self.failed=False;self.boot_at=0;self.engine='Starting OCR'
        self._start()

    def _start(self):
        self.inputs=self.ctx.Queue(maxsize=1);self.outputs=self.ctx.Queue()
        self.process=self.ctx.Process(target=worker,args=(self.inputs,self.outputs,asdict(self.layout),self.folder,self.backend),daemon=True)
        self.process.start();self.boot_at=time.monotonic();self.active_at=None;self.ready=False;self.busy=False;self.failed=False

    def submit(self,image,frame_id,captured_at,source):
        job={'id':frame_id,'at':captured_at,'source':source,'size':image.size,'pixels':image.convert('RGB').tobytes(),'epoch':self.epoch}
        if self.pending is not None:self.replaced+=1
        self.pending=job
        self.flush_pending()

    def flush_pending(self):
        if self.pending is not None and not self.busy and self.ready and self.process:
            try:self.inputs.put_nowait(self.pending)
            except queue.Full:return
            self.pending=None;self.busy=True

    def poll(self):
        messages=[]
        while True:
            try:msg=self.outputs.get_nowait()
            except queue.Empty:break
            if 'engine' in msg:self.engine=msg['engine'];self.boot_at=0;self.ready=True
            if 'started' in msg:self.active_at=msg['at']
            if 'snapshot' in msg or 'error' in msg:self.active_at=None;self.busy=False
            if 'error' in msg:self.ready=False;self.failed=True
            messages.append(msg)
        now=time.monotonic()
        expired=(self.active_at and now-self.active_at>2.2) or (self.boot_at and now-self.boot_at>30)
        if expired:
            self.stop();self.restarts+=1
            messages.append({'error':'Vision deadline exceeded; old result discarded'})
            if self.restarts<3:self._start()
        elif self.process and not self.process.is_alive() and not self.failed and not any('error' in m for m in messages):
            self.failed=True
            messages.append({'error':'Vision worker stopped. Restart the session.'})
        self.flush_pending()
        return messages

    def stop(self):
        self.ready=False;self.busy=False
        if self.process:
            try:self.inputs.put_nowait(None)
            except (queue.Full,ValueError):pass
            self.process.join(.15)
            if self.process.is_alive():self.process.terminate();self.process.join(.5)
            for q in (self.inputs,self.outputs):
                q.cancel_join_thread();q.close()
            self.process=None
