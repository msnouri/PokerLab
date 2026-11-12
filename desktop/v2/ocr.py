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


class AppleVision:
    name='Apple Vision · on device'
    def __init__(self):
        if sys.platform!='darwin': raise RuntimeError('Apple Vision requires macOS')
        import Vision,Foundation
        self.Vision=Vision;self.Foundation=Foundation

    def recognize(self,image,numeric=False,accurate=False):
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
            handler=V.VNImageRequestHandler.alloc().initWithData_options_(nsdata,{})
            ok,error=handler.performRequests_error_([req],None)
            if not ok: raise RuntimeError(str(error))
            lines=[];scores=[]
            for obs in req.results() or []:
                choices=obs.topCandidates_(1)
                if choices:
                    lines.append(str(choices[0].string()));scores.append(float(choices[0].confidence()))
            return TextRead(' '.join(lines),min(scores) if scores else 0.)


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
