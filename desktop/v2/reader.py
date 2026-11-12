"""Incremental field recognition with exact-pixel invalidation and abstention."""
import hashlib,time
from pathlib import Path
import numpy as np
from PIL import Image
from ..vision import Reader,Profile,crop
from .layout import Registration
from .state import Field,Snapshot,validate_snapshot
from .ocr import make_engine,prepare,decode_text


def digest(image): return hashlib.blake2b(image.tobytes(),digest_size=16).hexdigest()


def visual_feature(image):
    a=np.asarray(image.convert('RGB').resize((48,32)),dtype=np.float32)/255
    shape=(a-a.mean(axis=(0,1))).ravel()
    norm=float(np.linalg.norm(shape))
    shape=shape/norm if norm>.01 else np.zeros_like(shape)
    # Retain absolute appearance: an absent marker can be uniform felt, and
    # enabled/disabled controls can differ in brightness or color alone.
    appearance=np.concatenate([a.ravel(),(1-a).ravel()])
    appearance/=max(float(np.linalg.norm(appearance)),1e-8)
    feature=np.concatenate([shape,appearance])
    return feature/max(float(np.linalg.norm(feature)),1e-8)


class IncrementalReader:
    def __init__(self,layout,folder,backend='auto',engine=None):
        import cv2
        # These are small ROI kernels. Large OpenCV thread pools add latency
        # and compete with capture/OCR, especially during worker startup.
        cv2.setNumThreads(1)
        self.layout=layout;self.folder=Path(folder)
        self.engine=engine or make_engine(backend)
        self.cards=Reader(Profile(templates=layout.templates.get('cards',{})),self.folder)
        self.registration=Registration(layout,self.folder)
        self.cache={};self.ttl=30.;self.unknown_ttl=2.;self.hashes={}
        self.attempts=0
        self.batch={}
        self.visual={}
        for key,bank in layout.templates.items():
            if key=='cards':continue
            self.visual[key]={label:visual_feature(Image.open(self.folder/rel)) for label,rel in bank.items()}
        self.empty_board={k:Image.open(self.folder/p).convert('RGB') for k,p in layout.blank_board.items()}

    def cache_fresh(self,cache,signature,now):
        return bool(cache and cache[0]==signature and now-cache[1]<(self.ttl if cache[2].known else self.unknown_ttl))

    def classify(self,key,image,kind):
        bank=self.visual.get(key)
        if not bank:return None
        f=visual_feature(image)
        scores=sorted(((float(f@v),label) for label,v in bank.items()),reverse=True)
        score,label=scores[0];second=scores[1][0] if len(scores)>1 else 0.
        if kind in ('money','integer','bound'):
            # Numeric banks may contain only a few taught values. An unmatched
            # amount must fall through to OCR, never become the nearest zero.
            if score<.999 or score-second<.002:return None
            if label=='none' and kind=='bound':return None,min(1.,score)
            if not label.startswith('n_'):raise ValueError('Invalid numeric example label')
            value=int(label[2:])
            if not 0<=value<=1_000_000_000:raise ValueError('Numeric example is out of range')
            return value,min(1.,score)
        if score<.94 or score-second<.04: raise ValueError('Visual indicator is ambiguous')
        if kind=='status':
            if label not in ('active','folded','all-in','empty'):raise ValueError('Unrecognized status label')
            value=label
        else:
            if label not in ('true','false'):raise ValueError('Indicator labels must be true or false')
            value=label=='true'
        return value,min(1.,score)

    def read_one(self,spec,image,deadline):
        key,kind=spec['key'],spec['kind']
        if kind in ('card','board'):
            if kind=='board' and key in self.empty_board:
                blank=self.empty_board[key].resize(image.size)
                if float(np.abs(np.asarray(blank,dtype=float)-np.asarray(image,dtype=float)).mean())<1.0:
                    return None,1.,0
            value,score=self.cards.read_card(image,allow_blank=kind=='board')
            return value,score,0
        visual=self.classify(key,image,kind)
        if visual:return *visual,0
        if key in self.batch:
            value,score,reason=self.batch[key]
            if reason:raise ValueError(reason)
            return value,score,0
        im=prepare(image);calls=0;reason='Uncertain text'
        for accurate in (False,True):
            if time.monotonic()>=deadline:raise TimeoutError('Recognition deadline reached')
            self.attempts+=1
            read=self.engine.recognize(im,numeric=kind in ('money','integer'),accurate=accurate);calls+=1
            if read.score<.60:
                reason=f'Low OCR score ({read.score:.2f})';continue
            try:return decode_text(read.text,kind,self.layout.scale),read.score,calls
            except ValueError as exc:reason=str(exc)
        raise ValueError(reason)

    def batch_text(self,image,start,deadline):
        self.batch={}
        if not hasattr(self.engine,'recognize_fields'):return
        pending={}
        for spec in self.layout.specs:
            key=spec['key']
            if spec['kind'] in ('card','board') or key not in self.layout.confirmed or key not in self.layout.regions:continue
            if key in self.visual and spec['kind'] not in ('money','integer','bound'):continue
            try:im=crop(image,self.layout.regions[key]);signature=digest(im)
            except ValueError:continue
            cache=self.cache.get(key)
            if self.cache_fresh(cache,signature,start):continue
            if key in self.visual and self.classify(key,im,spec['kind']) is not None:continue
            pending[key]=spec;self.batch[key]=(None,0.,'Text not recognized')
        previous_count=0
        for pass_index,accurate in enumerate((False,True,True)):
            if pass_index==2:
                # A focused fallback adds information after a shared pass.
                # Do not repeat an already focused request with identical input.
                if previous_count<=8:break
                pending={k:s for k,s in pending.items() if s['kind'] not in ('turn','control','status','dealer')}
                if len(pending)>8:break
            if not pending or time.monotonic()>=deadline:break
            previous_count=len(pending)
            request_before=getattr(self.engine,'request_count',None)
            if request_before is None:self.attempts+=1
            try:reads=self.engine.recognize_fields(image,{k:self.layout.regions[k] for k in pending},accurate)
            except (RuntimeError,ValueError,OSError) as exc:
                for key in pending:self.batch[key]=(None,0.,str(exc))
                continue
            finally:
                if request_before is not None:self.attempts+=self.engine.request_count-request_before
            for key in list(pending):
                read=reads.get(key)
                if not read or read.score<.60:
                    self.batch[key]=(None,0.,'Uncertain or missing text in calibrated region');continue
                try:value=decode_text(read.text,pending[key]['kind'],self.layout.scale)
                except ValueError as exc:self.batch[key]=(None,read.score,str(exc));continue
                self.batch[key]=(value,read.score,'');pending.pop(key)

    def read(self,image,frame_id,captured_at,source='image',budget=3.5):
        start=time.monotonic();deadline=start+budget;fields={};calls=hits=0;attempts_before=self.attempts
        try:image,_,_=self.registration.align(image)
        except ValueError as exc:
            return Snapshot(frame_id,captured_at,source,{},[str(exc)]),{}
        self.batch_text(image,start,deadline)
        hashes={}
        for spec in self.layout.specs:
            key=spec['key']
            f=Field(key,reason='Region not calibrated',observed_at=captured_at)
            fields[key]=f
            if key not in self.layout.regions:continue
            if key not in self.layout.confirmed:
                f.reason='Suggested region needs confirmation';continue
            try:
                im=crop(image,self.layout.regions[key]);signature=digest(im);hashes[key]=signature
                cache=self.cache.get(key)
                if self.cache_fresh(cache,signature,start):
                    cached=cache[2]
                    fields[key]=Field(key,cached.value,cached.quality,cached.score,cached.reason,captured_at,True)
                    hits+=1;continue
                value,score,n=self.read_one(spec,im,deadline);calls+=n
                f.value=value;f.score=score;f.quality='read';f.reason=''
                self.cache[key]=(signature,time.monotonic(),f)
            except (ValueError,RuntimeError,OSError,TimeoutError) as exc:
                f.reason=str(exc)
                # Abstention is cached as UNKNOWN, never converted into a read.
                # Unchanged unreadable artwork must not force full OCR every tick.
                if key in hashes:self.cache[key]=(hashes[key],time.monotonic(),f)
                else:self.cache.pop(key,None)
        snap=Snapshot(frame_id,captured_at,source,fields,read_ms=(time.monotonic()-start)*1000,
                      ocr_calls=self.attempts-attempts_before,cache_hits=hits,table_context={'seats':self.layout.seats,'hero':self.layout.hero,'chip_scale':self.layout.scale})
        validate_snapshot(snap,self.layout.seats,self.layout.hero)
        return snap,hashes

    def close(self):
        if hasattr(self.engine,'close'):self.engine.close()


def critical_keys(layout):
    return [s['key'] for s in layout.specs if s['required']]


def readiness(snap,layout):
    missing=[k for k in critical_keys(layout) if k not in snap.fields or not snap.fields[k].known]
    if snap.issues:return 'Conflict',missing
    if missing:return 'Needs review',missing
    return ('Verified snapshot' if snap.stable else 'Confirming'),missing
