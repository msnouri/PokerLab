"""Normalized regions, versioned layouts, anchor registration, setup proposals."""
from dataclasses import dataclass,field,asdict
import json,math
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from ..vision import crop
from .state import field_specs


@dataclass
class Layout:
    name:str='Untitled table'
    seats:int=6
    hero:int=0
    scale:int=1
    version:int=2
    regions:dict=field(default_factory=dict)
    templates:dict=field(default_factory=dict) # key -> label -> PNG relative path
    anchor:str=''
    anchor_rect:list=field(default_factory=list)
    reference_size:list=field(default_factory=list)
    confirmed:list=field(default_factory=list)
    blank_board:dict=field(default_factory=dict)

    @property
    def specs(self): return field_specs(self.seats)

    def save(self,path):
        Path(path).write_text(json.dumps(asdict(self),indent=2)+'\n')

    @classmethod
    def load(cls,path):
        raw=json.loads(Path(path).read_text());obj=cls(**raw)
        obj.validate(Path(path).parent)
        return obj

    def validate(self,folder):
        folder=Path(folder)
        if self.version!=2 or type(self.seats) is not int or type(self.hero) is not int or not 2<=self.seats<=9 or not 0<=self.hero<self.seats: raise ValueError('Unsupported layout or seat configuration')
        if type(self.scale) is not int or not 1<=self.scale<=10000: raise ValueError('Invalid chip scale')
        if not isinstance(self.regions,dict) or not isinstance(self.templates,dict) or not isinstance(self.blank_board,dict):raise ValueError('Invalid region or template map')
        if not isinstance(self.confirmed,list) or any(not isinstance(b,dict) for b in self.templates.values()):raise ValueError('Invalid confirmations or template bank')
        if self.anchor and (len(self.reference_size)!=2 or any(type(v) is not int or v<=0 for v in self.reference_size) or not self.anchor_rect):raise ValueError('Anchor needs valid reference dimensions and a region')
        allowed={s['key'] for s in self.specs}
        for key,rect in self.regions.items():
            if key not in allowed: raise ValueError('Unknown region '+key)
            validate_rect(rect)
        if self.anchor_rect: validate_rect(self.anchor_rect)
        if any(k not in self.regions for k in self.confirmed): raise ValueError('Confirmation refers to a missing region')
        paths=[p for bank in self.templates.values() for p in bank.values()]+([self.anchor] if self.anchor else [])+list(self.blank_board.values())
        for rel in paths:
            if not isinstance(rel,str) or not (folder/rel).resolve().is_relative_to(folder.resolve()):
                raise ValueError('Assets must stay inside the layout folder')


def validate_rect(rect):
    if not isinstance(rect,(list,tuple)) or len(rect)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in rect):
        raise ValueError('Expected four finite normalized coordinates')
    x,y,w,h=rect
    if min(x,y)<0 or min(w,h)<=0 or x+w>1.000001 or y+h>1.000001: raise ValueError('Region outside the table')


def rect_pixels(rect,size):
    validate_rect(rect);x,y,w,h=rect;iw,ih=size
    return round(x*iw),round(y*ih),round((x+w)*iw),round((y+h)*ih)


class Registration:
    """Find one calibrated visual anchor across supported uniform scales."""
    def __init__(self,layout,folder):
        self.layout=layout
        self.anchor=Image.open(folder/layout.anchor).convert('L') if layout.anchor else None

    def align(self,image):
        if self.anchor is None: return image,1.,'normalized'
        gray=cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2GRAY)
        base=np.asarray(self.anchor)
        matches=[]
        rw,rh=self.layout.reference_size
        # Normalized coordinates handle moving/resizing; the anchor detects
        # reflow or drift instead of trusting the old coordinates silently.
        expected=image.width/rw
        for factor in (.90,1.,1.10):
            scale=expected*factor
            tw,th=round(base.shape[1]*scale),round(base.shape[0]*scale)
            if min(tw,th)<6 or tw>gray.shape[1] or th>gray.shape[0]: continue
            template=cv2.resize(base,(tw,th))
            scores=cv2.matchTemplate(gray,template,cv2.TM_CCOEFF_NORMED)
            _,score,_,point=cv2.minMaxLoc(scores)
            matches.append((score,point,scale))
        if not matches: raise ValueError('Anchor no longer fits; recalibrate this window size')
        score,(x,y),scale=max(matches)
        if score<.90: raise ValueError('Table anchor lost; recognition paused')
        ar=self.layout.anchor_rect
        origin_x=x-ar[0]*rw*scale;origin_y=y-ar[1]*rh*scale
        matrix=np.array([[scale,0,origin_x],[0,scale,origin_y]],dtype=float)
        aligned=cv2.warpAffine(np.asarray(image),matrix,(rw,rh),flags=cv2.INTER_LINEAR|cv2.WARP_INVERSE_MAP,borderValue=(0,0,0))
        # Reject a viewport whose registered content is clipped.
        if origin_x < -3 or origin_y < -3 or origin_x+rw*scale>image.width+3 or origin_y+rh*scale>image.height+3:
            raise ValueError('Table is cropped or partly unavailable; choose the complete window')
        return Image.fromarray(aligned),float(score),'anchor'


def propose_cards(image):
    """White-card proposals, not an arbitrary-theme detector. User confirms."""
    arr=np.asarray(image.convert('RGB'));gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    mask=((gray>200)&((arr.max(axis=2)-arr.min(axis=2))<55)).astype('uint8')*255
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for c in contours:
        x,y,w,h=cv2.boundingRect(c)
        if .5<w/h<.85 and image.width*.025<w<image.width*.13 and h>image.height*.06:
            boxes.append((x,y,w,h))
    groups=[]
    for box in sorted(boxes,key=lambda b:b[1]):
        group=next((g for g in groups if abs(g[0][1]-box[1])<box[3]*.25),None)
        if group is None: groups.append([box])
        else: group.append(box)
    regions={}
    for group in groups:
        group.sort()
        if 3<=len(group)<=5:
            dx=float(np.median([b[0]-a[0] for a,b in zip(group,group[1:])]))
            x,y,w,h=group[0]
            for i in range(5):
                if x+i*dx+w<=image.width: regions[f'board_{i+1}']=[(x+i*dx)/image.width,y/image.height,w/image.width,h/image.height]
        elif len(group)==2 and group[0][1]>image.height*.5:
            for i,(x,y,w,h) in enumerate(group): regions[f'hole_{i+1}']=[x/image.width,y/image.height,w/image.width,h/image.height]
    return regions
