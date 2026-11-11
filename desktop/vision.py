"""Calibrated screen reader. Match scores are diagnostics, not probabilities."""
from dataclasses import dataclass, field, asdict
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
import shutil
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .model import CARD_TEXT

CARD_KEYS = ["hole_1", "hole_2"] + [f"board_{i}" for i in range(1, 6)]
NUMBER_KEYS = ["pot", "stack", "to_call", "bet", "min_raise_to", "max_raise_to"]
FIELDS = CARD_KEYS + NUMBER_KEYS


def font(size):
    return ImageFont.load_default(size=size)


def card_image(card, size=(64, 88)):
    """Original practice card art, also used by the bundled template bank."""
    im = Image.new("RGB", (64, 88), "#f7f8f6")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 63, 87), 5, fill="#f7f8f6", outline="#c8cecd", width=2)
    if card is None:
        d.rounded_rectangle((5, 5, 58, 82), 3, fill="#203c47")
        for y in range(12, 80, 10):
            d.line((9, y, 54, y), fill="#345862", width=2)
    else:
        rank, suit = card
        color = "#cb4556" if suit in "dh" else "#15242b"
        d.text((7, 4), rank, fill=color, font=font(27))
        cx, cy = 32, 58
        if suit == "d":
            d.polygon([(cx, cy-14), (cx+12, cy), (cx, cy+14), (cx-12, cy)], fill=color)
        elif suit == "h":
            d.ellipse((cx-13,cy-11,cx+1,cy+3),fill=color)
            d.ellipse((cx-1,cy-11,cx+13,cy+3),fill=color)
            d.polygon([(cx-13,cy-3),(cx+13,cy-3),(cx,cy+14)],fill=color)
        elif suit == "s":
            d.polygon([(cx,cy-14),(cx-13,cy+2),(cx+13,cy+2)],fill=color)
            d.ellipse((cx-13,cy-3,cx+1,cy+11),fill=color)
            d.ellipse((cx-1,cy-3,cx+13,cy+11),fill=color)
            d.polygon([(cx,cy+3),(cx-6,cy+16),(cx+6,cy+16)],fill=color)
        else:
            for x,y in ((cx,cy-8),(cx-8,cy+3),(cx+8,cy+3)):
                d.ellipse((x-7,y-7,x+7,y+7),fill=color)
            d.polygon([(cx,cy),(cx-6,cy+16),(cx+6,cy+16)],fill=color)
    return im.resize(size, Image.Resampling.LANCZOS)


def crop(image, rect):
    if len(rect) != 4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in rect):
        raise ValueError("Regions need four finite normalized coordinates.")
    x,y,w,h = rect
    if min(x,y) < 0 or min(w,h) <= 0 or x+w > 1.000001 or y+h > 1.000001:
        raise ValueError("A region lies outside the image.")
    iw,ih=image.size
    box=(round(x*iw),round(y*ih),round((x+w)*iw),round((y+h)*ih))
    if box[2]-box[0] < 3 or box[3]-box[1] < 3:
        raise ValueError("Region is too small to read.")
    return image.crop(box)


@dataclass
class Profile:
    name: str = "My table"
    version: int = 1
    monitor: int = 1
    capture: list | None = None
    chip_scale: int = 1
    regions: dict = field(default_factory=dict)
    templates: dict = field(default_factory=dict)  # card -> relative PNG path

    def save(self,path):
        Path(path).write_text(json.dumps(asdict(self),indent=2)+"\n")

    @classmethod
    def load(cls,path):
        raw=json.loads(Path(path).read_text())
        obj=cls(**raw)
        if not isinstance(obj.regions,dict) or not isinstance(obj.templates,dict):
            raise ValueError("Layout regions and templates must be objects.")
        if obj.version != 1 or not isinstance(obj.monitor,int) or obj.monitor < 1:
            raise ValueError("Unsupported layout profile.")
        if not isinstance(obj.chip_scale,int) or not 1 <= obj.chip_scale <= 10000:
            raise ValueError("Chip scale must be an integer from 1 to 10,000.")
        dummy=Image.new("RGB",(1200,730))
        for key,rect in obj.regions.items():
            if key not in FIELDS:
                raise ValueError("Unknown layout field: "+key)
            crop(dummy,rect)
        if obj.capture:
            crop(dummy,obj.capture)
        if any(c not in CARD_TEXT for c in obj.templates):
            raise ValueError("Invalid card template label.")
        for rel in obj.templates.values():
            target=(Path(path).parent/rel).resolve()
            if not target.is_relative_to(Path(path).parent.resolve()):
                raise ValueError("Templates must be inside the profile folder.")
        return obj


def parse_amount(text, scale=1):
    """Strict decimal dot / comma thousands; reject ambiguous OCR and decimals."""
    value=text.strip().replace("$", "").replace("€", "").replace("£", "")
    value=re.sub(r"\s+", "", value)
    match=re.fullmatch(r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)([kKmM]?)",value)
    if not match:
        raise ValueError("Unreadable amount: "+repr(text))
    try:
        amount=Decimal(match[1].replace(",", ""))*scale
        if match[2]:
            amount*=1000 if match[2].lower()=="k" else 1000000
        if amount != amount.to_integral_value() or not 0 <= amount <= 1000000000:
            raise ValueError("Use a chip scale that preserves the displayed decimals.")
        return int(amount)
    except InvalidOperation as exc:
        raise ValueError("Unreadable amount.") from exc


def tesseract_path():
    return shutil.which("tesseract") or next((p for p in ("/opt/homebrew/bin/tesseract","/usr/local/bin/tesseract") if Path(p).exists()),None)


class Reader:
    def __init__(self,profile,folder=None):
        self.profile=profile
        self.templates={c:card_image(c) for c in CARD_TEXT}
        for c,rel in profile.templates.items():
            if folder is None:
                raise ValueError("Save the profile before reading custom templates.")
            target=(Path(folder)/rel).resolve()
            if not target.is_relative_to(Path(folder).resolve()):
                raise ValueError("A template points outside its profile folder.")
            self.templates[c]=Image.open(target).convert("RGB")
        self.features={c:self._feature(im) for c,im in self.templates.items()}

    @staticmethod
    def _feature(im):
        # Color + edges distinguish similar ranks and red/black suit shapes.
        arr=np.asarray(im.convert("RGB").resize((48,66)),dtype=np.float32)/255
        edges=cv2.Canny((cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)*255).astype("uint8"),60,140)/255
        feature=np.concatenate([(arr-arr.mean(axis=(0,1))).ravel(),edges.ravel()*.7])
        norm=np.linalg.norm(feature)
        feature=feature/max(norm,1e-8)
        # Most poker cards place the rank in the top-left corner. Giving that
        # region its own normalized feature prevents a large identical suit
        # symbol/background from overwhelming small rank differences (3/8).
        corner=arr[3:27,3:29]
        corner=(corner-corner.mean(axis=(0,1))).ravel()
        corner=corner/max(np.linalg.norm(corner),1e-8)
        combined=np.concatenate([feature,corner])
        return combined/max(np.linalg.norm(combined),1e-8)

    def read_card(self,im,allow_blank=False):
        arr=np.asarray(im.convert("RGB"))
        # Empty board slots must be close to a uniform felt color, not an
        # animated, covered, face-down, or simply low-scoring card.
        if allow_blank and float(arr.std(axis=(0,1)).max()) < 9:
            return None,1.0
        f=self._feature(im)
        ranked=sorted(((float(f@v),c) for c,v in self.features.items()),reverse=True)
        score,card=ranked[0]
        if score < .90 or score-ranked[1][0] < .025:
            raise ValueError(f"Uncertain card (best {card}, match {score:.2f}). Teach this table's card art.")
        return card,min(1.0,max(0.0,score))

    def read(self,image,budget=4.):
        started=time.monotonic()
        values={};scores={};errors={}
        for key in CARD_KEYS:
            if key not in self.profile.regions:
                errors[key]="Region not calibrated"
                continue
            try:
                values[key],scores[key]=self.read_card(crop(image,self.profile.regions[key]),key.startswith("board"))
            except (ValueError,OSError) as exc:
                errors[key]=str(exc)
        number_keys=[k for k in NUMBER_KEYS if k in self.profile.regions]
        if number_keys:
            import pytesseract
            from pytesseract import Output
            executable=tesseract_path()
            if executable:
                pytesseract.pytesseract.tesseract_cmd=executable
            for key in number_keys:
                remaining=budget-(time.monotonic()-started)
                if remaining <= .1:
                    errors[key]="Reader deadline reached"
                    continue
                try:
                    im=crop(image,self.profile.regions[key]).convert("L")
                    im=im.resize((im.width*3,im.height*3))
                    # Normalize dark-background numbers to dark text on white.
                    if np.asarray(im).mean() < 128:
                        im=Image.fromarray(255-np.asarray(im))
                    binary=ImageOps.expand(im.point(lambda x:255 if x>160 else 0),border=20,fill=255)
                    allowed="0123456789.,kKmM"
                    if key in ("min_raise_to","max_raise_to"):
                        allowed+="NOEA/"
                    attempts=((im,"--psm 7"),(binary,"--psm 7"),
                              (im,f"--psm 8 -c tessedit_char_whitelist={allowed}"))
                    reason="Unreadable amount."
                    for prepared,config in attempts:
                        remaining=budget-(time.monotonic()-started)
                        if remaining <= .1:
                            reason="Reader deadline reached";break
                        try:
                            result=pytesseract.image_to_data(prepared,config=config,output_type=Output.DICT,timeout=remaining)
                            tokens=[(t,float(c)) for t,c in zip(result["text"],result["conf"]) if t.strip()]
                            if not tokens or min(c for _,c in tokens)<55:
                                raise ValueError("Low OCR confidence; review this amount.")
                            text="".join(t for t,_ in tokens)
                            if key in ("min_raise_to","max_raise_to") and text.upper() in ("NONE","N/A"):
                                amount=None
                            else:
                                amount=parse_amount(text,self.profile.chip_scale)
                            values[key]=amount;scores[key]=min(c for _,c in tokens)/100
                            break
                        except (ValueError,RuntimeError,OSError) as exc:
                            reason=str(exc)
                    else:
                        errors[key]=reason
                    if key not in values:
                        errors[key]=reason
                except (ValueError,RuntimeError,OSError) as exc:
                    errors[key]=str(exc)
        for key in ("pot","stack","to_call","bet"):
            if key not in self.profile.regions:
                errors[key]="Region not calibrated"
        return {"values":values,"scores":scores,"errors":errors,"reader_ms":(time.monotonic()-started)*1000}


class StableReadings:
    """Require repeated matching successful reads; reset on any incomplete read."""
    def __init__(self):
        self.previous=None
        self.count=0

    def add(self,result):
        if result["errors"]:
            self.previous=None;self.count=0
            return False
        fingerprint=json.dumps(result["values"],sort_keys=True)
        self.count=self.count+1 if fingerprint==self.previous else 1
        self.previous=fingerprint
        return self.count>=2
