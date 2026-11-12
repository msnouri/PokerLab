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
    a=(a-a.mean(axis=(0,1))).ravel()
    return a/max(float(np.linalg.norm(a)),1e-8)


class IncrementalReader:
    def __init__(self,layout,folder,backend='auto',engine=None):
        self.layout=layout;self.folder=Path(folder)
        self.engine=engine or make_engine(backend)
        self.cards=Reader(Profile(templates=layout.templates.get('cards',{})),self.folder)
        self.registration=Registration(layout,self.folder)
        self.cache={};self.ttl=2.;self.hashes={}
        self.attempts=0
        self.visual={}
        for key,bank in layout.templates.items():
            if key=='cards':continue
            self.visual[key]={label:visual_feature(Image.open(self.folder/rel)) for label,rel in bank.items()}
        self.empty_board={k:Image.open(self.folder/p).convert('RGB') for k,p in layout.blank_board.items()}

    def classify(self,key,image,kind):
        bank=self.visual.get(key)
        if not bank:return None
        f=visual_feature(image)
        scores=sorted(((float(f@v),label) for label,v in bank.items()),reverse=True)
        score,label=scores[0];second=scores[1][0] if len(scores)>1 else 0.
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

    def read(self,image,frame_id,captured_at,source='image',budget=1.7):
        start=time.monotonic();deadline=start+budget;fields={};calls=hits=0;attempts_before=self.attempts
        try:image,_,_=self.registration.align(image)
        except ValueError as exc:
            return Snapshot(frame_id,captured_at,source,{},[str(exc)]),{}
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
                if cache and cache[0]==signature and start-cache[1]<self.ttl:
                    cached=cache[2]
                    fields[key]=Field(key,cached.value,cached.quality,cached.score,cached.reason,captured_at,True)
                    hits+=1;continue
                value,score,n=self.read_one(spec,im,deadline);calls+=n
                f.value=value;f.score=score;f.quality='read';f.reason=''
                self.cache[key]=(signature,start,f)
            except (ValueError,RuntimeError,OSError,TimeoutError) as exc:
                f.reason=str(exc)
                self.cache.pop(key,None)
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
