"""Persistent native OCR. Each worker owns its engine and mutable settings."""
from dataclasses import dataclass
from pathlib import Path
import os,re,sys,time
import numpy as np
from PIL import Image,ImageOps
from ..vision import parse_amount,tesseract_path


@dataclass
class TextRead:
    text:str
    score:float


def map_text_boxes(boxes,regions):
    """Map OCR boxes to single-value regions; crossing boxes stay unknown."""
    grouped={key:[] for key in regions}
    for x,y,w,h,text,score in boxes:
        matches=[]
        for key,(rx,ry,rw,rh) in regions.items():
            overlap=max(0,min(x+w,rx+rw)-max(x,rx))*max(0,min(y+h,ry+rh)-max(y,ry))
            if rx<=x+w/2<=rx+rw and ry<=y+h/2<=ry+rh and overlap>=.8*w*h:
                matches.append(key)
        if len(matches)==1:grouped[matches[0]].append((y,x,text,score))
    return {key:TextRead(' '.join(b[2] for b in sorted(rows,key=lambda b:b[1])),min((b[3] for b in rows),default=0.))
            for key,rows in grouped.items()}


class AppleVision:
    name='Apple Vision · on device'
    def __init__(self):
        if sys.platform!='darwin': raise RuntimeError('Apple Vision requires macOS')
        import Vision,Foundation
        self.Vision=Vision;self.Foundation=Foundation
        # Pay one-time model initialization before accepting a timed frame.
        from PIL import ImageDraw
        warm=Image.new('RGB',(320,90),'white');ImageDraw.Draw(warm).text((12,12),'READY 100',fill='black',font_size=40)
        self._boxes(warm,False);self._boxes(warm,True)

    def _boxes(self,image,accurate=False):
        import objc
        with objc.autorelease_pool():
            import io
            data=io.BytesIO();image.save(data,format='PNG')
            nsdata=self.Foundation.NSData.dataWithBytes_length_(data.getvalue(),len(data.getvalue()))
            V=self.Vision
            req=V.VNRecognizeTextRequest.alloc().init()
            req.setRecognitionLevel_(V.VNRequestTextRecognitionLevelAccurate if accurate else V.VNRequestTextRecognitionLevelFast)
            req.setUsesLanguageCorrection_(False)
            req.setRecognitionLanguages_(['en-US'])
            req.setMinimumTextHeight_(0.)
            handler=V.VNImageRequestHandler.alloc().initWithData_options_(nsdata,{})
            ok,error=handler.performRequests_error_([req],None)
            if not ok: raise RuntimeError(str(error))
            boxes=[]
            for obs in req.results() or []:
                choices=obs.topCandidates_(1)
                if choices:
                    candidate=choices[0];value=str(candidate.string());score=float(candidate.confidence())
                    # A line may contain both adjacent stack/bet or status/dealer
                    # values. Use word geometry instead of assigning the line to
                    # one field. NSRange offsets are UTF-16 code units.
                    for match in re.finditer(r'\S+',value):
                        offset=len(value[:match.start()].encode('utf-16-le'))//2
                        length=len(match[0].encode('utf-16-le'))//2
                        word,error=candidate.boundingBoxForRange_error_((offset,length),None)
                        if word is None:continue
                        box=word.boundingBox();x,y=box.origin.x,box.origin.y;w,h=box.size.width,box.size.height
                        boxes.append((float(x),float(1-y-h),float(w),float(h),match[0],score))
            return boxes

    def recognize_fields(self,image,regions,accurate=False):
        return map_text_boxes(self._boxes(image,accurate),regions)

    def recognize(self,image,numeric=False,accurate=False):
        boxes=self._boxes(image,accurate)
        return TextRead(' '.join(b[4] for b in sorted(boxes,key=lambda b:(b[1],b[0]))),min((b[5] for b in boxes),default=0.))


class NativeTesseract:
    name='Tesseract · persistent native API'
    def __init__(self):
        import tesserocr
        paths=[os.environ.get('TESSDATA_PREFIX',''),'/usr/share/tesseract-ocr/5/tessdata',
               '/opt/homebrew/share/tessdata','/usr/local/share/tessdata']
        path=next((p for p in paths if p and (Path(p)/'eng.traineddata').exists()),None)
        if path is None: raise RuntimeError('English Tesseract language data was not found')
        self.api=tesserocr.PyTessBaseAPI(path=path,lang='eng',psm=7)

    def recognize(self,image,numeric=False,accurate=False):
        self.api.Clear()
        self.api.SetPageSegMode(8 if accurate else 7)
        self.api.SetVariable('tessedit_char_whitelist','0123456789.,kKmM$' if numeric else '')
        self.api.SetImage(image)
        value=self.api.GetUTF8Text().strip();scores=self.api.AllWordConfidences()
        return TextRead(value,min(scores)/100 if value and scores else 0.)

    def close(self): self.api.End()


class SubprocessOCR:
    name='Tesseract · subprocess fallback'
    def recognize(self,image,numeric=False,accurate=False):
        import pytesseract
        from pytesseract import Output
        if tesseract_path(): pytesseract.pytesseract.tesseract_cmd=tesseract_path()
        config='--psm '+('8' if accurate else '7')
        if numeric: config+=' -c tessedit_char_whitelist=0123456789.,kKmM$'
        raw=pytesseract.image_to_data(image,config=config,output_type=Output.DICT,timeout=.5)
        parts=[(t,float(c)/100) for t,c in zip(raw['text'],raw['conf']) if t.strip()]
        return TextRead(' '.join(t for t,_ in parts),min((c for _,c in parts),default=0))


def make_engine(name='auto'):
    if name in ('auto','vision') and sys.platform=='darwin': return AppleVision()
    if name=='vision': raise RuntimeError('Apple Vision requires macOS')
    if name in ('auto','native'):
        try:return NativeTesseract()
        except (ImportError,RuntimeError):
            if name=='native':raise
    return SubprocessOCR()


def prepare(image):
    im=image.convert('L')
    factor=max(2,min(4,round(100/max(1,im.height))))
    if factor>1: im=im.resize((im.width*factor,im.height*factor),Image.Resampling.LANCZOS)
    if np.asarray(im).mean()<128: im=ImageOps.invert(im)
    import cv2
    _,binary=cv2.threshold(np.asarray(im),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    return ImageOps.expand(Image.fromarray(binary),10,fill=255)


def decode_text(text,kind,scale):
    value=text.strip();token=re.sub(r'[^A-Z0-9]','',value.upper())
    if kind in ('money','integer','bound'):
        if kind=='bound' and token in ('NONE','NA','UNAVAILABLE'):return None
        return parse_amount(value,1 if kind=='integer' else scale)
    if kind=='status':
        labels={'ACTIVE':'active','FOLDED':'folded','FOLD':'folded','ALLIN':'all-in','EMPTY':'empty','OUT':'empty'}
        if token not in labels: raise ValueError('Status needs a labelled visual example or readable status text')
        return labels[token]
    if kind in ('control','turn','dealer'):
        if token in ('ON','YES','YOURTURN','TURN','DEALER','D'):return True
        if token in ('OFF','NO','WAIT','NONE'):return False
        raise ValueError('Indicator needs a labelled visual example')
    if not value:raise ValueError('No text recognized')
    return value
