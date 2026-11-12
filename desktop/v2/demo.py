"""Original six-seat fixture renderer with labelled public table information."""
from pathlib import Path
import json,time
from PIL import Image,ImageDraw,ImageFont
from ..practice import PracticeTable
from ..vision import card_image
from .layout import Layout

W,H=1440,1000
FONT=Path(__file__).resolve().parents[1]/'assets'/'DejaVuSans.ttf'


def font(size):return ImageFont.truetype(str(FONT),size)


def write_examples(folder):
    """Labelled fixture artwork, independent of any generated hand or labels."""
    folder=Path(folder);assets=folder/'demo-examples';assets.mkdir(parents=True,exist_ok=True)
    banks={}
    groups=[('control',100,30,14,'#101e26',{'true':'ON','false':'OFF'}),
            ('turn',120,30,17,'#101e26',{'true':'ON','false':'OFF'}),
            ('dealer',52,24,13,'#152a33',{'true':'ON','false':'OFF'}),
            ('status',110,24,13,'#152a33',{s:s.upper() for s in ('active','folded','all-in','empty')})]
    for group,w,h,size,outside,labels in groups:
        banks[group]={}
        for label,text in labels.items():
            image=Image.new('RGB',(w,h),outside);draw=ImageDraw.Draw(image)
            draw.rounded_rectangle((0,0,w,h),5,fill='#192e37')
            draw.text((w/2,h/2),text,font=font(size),fill='#f0f1e6',anchor='mm')
            rel=f'demo-examples/{group}_{label}.png';image.save(folder/rel);banks[group][label]=rel
    return {'turn':banks['turn'],**{'button_'+a:banks['control'] for a in ('fold','check','call','bet','raise','all_in')},
            **{f'seat_{i}_dealer':banks['dealer'] for i in range(6)},**{f'seat_{i}_status':banks['status'] for i in range(6)}}


def fixture(view):
    o=view['observation'] or {}
    v={'hole_1':view['hole'][0],'hole_2':view['hole'][1],
       **{f'board_{i+1}':view['board'][i] if i<len(view['board']) else None for i in range(5)},
       'pot':view['pot'],'big_blind':20,'small_blind':10,'ante':0,
       'to_call':o.get('to_call',0),'min_raise_to':o.get('min_raise_to'),'max_raise_to':o.get('max_raise_to'),
       'hand_number':str(70000+view['hand_no']),'turn':view['pending'],'timer':20}
    for physical in range(6):
        i=(view['hero']+physical)%6
        status='all-in' if view['active'][i] and view['stacks'][i]==0 else 'active' if view['active'][i] else 'folded'
        v.update({f'seat_{physical}_name':['Nova','Atlas','Cedar','River','Orion','Aspen'][physical],f'seat_{physical}_stack':view['stacks'][i],
                  f'seat_{physical}_bet':view['bets'][i],f'seat_{physical}_status':status,f'seat_{physical}_dealer':i==5})
    for action in ('fold','check','call','bet','raise','all_in'):
        v['button_'+action]=bool(view['pending'] and ((action=='check' and not o.get('to_call')) or
            (action in ('call','fold') and o.get('to_call',0)>0) or
            (action in ('bet','raise','all_in') and o.get('min_raise_to') is not None)))
    return v


def render(view):
    values=fixture(view);regions={};im=Image.new('RGB',(W,H),'#101e26');d=ImageDraw.Draw(im)
    d.rounded_rectangle((90,140,1350,758),270,fill='#203b40',outline='#567268',width=3)
    d.rounded_rectangle((112,162,1328,736),250,fill='#133f3a',outline='#2c5b4e',width=3)
    d.text((720,282),'POKER / LAB',font=font(22),fill='#719b87',anchor='mm')
    d.text((720,315),'VISION TEST TABLE · PUBLIC INFORMATION ONLY',font=font(12),fill='#658c7b',anchor='mm')
    def value(key,box,size=22,label=None):
        x,y,w,h=box;regions[key]=[x/W,y/H,w/W,h/H]
        if label:d.text((x,y-8),label.upper(),font=font(10),fill='#91a9aa',anchor='ls')
        d.rounded_rectangle((x,y,x+w,y+h),5,fill='#192e37')
        val=values[key]
        if isinstance(val,bool):val='ON' if val else 'OFF'
        if val is None:val='NONE'
        d.text((x+w/2,y+h/2),str(val).upper() if key.endswith('status') else str(val),font=font(size),fill='#f0f1e6',anchor='mm')
    value('hand_number',(46,50,130,38),21,'Hand')
    value('small_blind',(220,50,80,38),21,'Small blind')
    value('big_blind',(326,50,80,38),21,'Big blind')
    value('ante',(432,50,80,38),21,'Ante')
    value('timer',(1260,50,85,38),21,'Clock')
    value('pot',(620,362,200,52),32,'Total pot')
    for i in range(5):
        x,y=510+i*86,445;key=f'board_{i+1}'
        regions[key]=[x/W,y/H,64/W,88/H]
        if values[key]:im.paste(card_image(values[key]),(x,y))
        else:d.rounded_rectangle((x,y,x+63,y+87),6,fill='#184740',outline='#396252')
    for i in range(2):
        x,y=636+i*84,650;im.paste(card_image(values[f'hole_{i+1}']),(x,y))
        regions[f'hole_{i+1}']=[x/W,y/H,64/W,88/H]
    positions=[(650,780),(140,585),(140,240),(650,145),(1120,240),(1120,585)]
    hero=view['hero']
    for offset,(x,y) in enumerate(positions):
        seat=offset
        d.rounded_rectangle((x-12,y-28,x+182,y+115),16,fill='#152a33',outline='#557765' if seat==0 else '#3a5058',width=2)
        value(f'seat_{seat}_name',(x,y-12,160,24),17)
        value(f'seat_{seat}_stack',(x,y+38,100,28),20,'Stack')
        value(f'seat_{seat}_bet',(x+108,y+38,64,28),17,'Bet')
        value(f'seat_{seat}_status',(x,y+78,110,24),13)
        value(f'seat_{seat}_dealer',(x+120,y+78,52,24),13)
    # Controls are deliberately separate from the seat and card regions.
    for j,a in enumerate(('fold','check','call','bet','raise','all_in')):
        value('button_'+a,(45+j*112,949,100,30),14,a.replace('_',' '))
    value('to_call',(810,949,95,30),18,'Call cost')
    value('min_raise_to',(936,949,110,30),18,'Min raise to')
    value('max_raise_to',(1076,949,110,30),18,'Max raise to')
    value('turn',(1220,949,120,30),17,'Your turn')
    layout=Layout(name='Poker Lab · six-max',hero=0,regions=regions,confirmed=list(regions),reference_size=[W,H])
    return im,layout,values


def sample_frames(count=12,example_folder=None):
    table=PracticeTable(seed=20261111);rows=[]
    examples=write_examples(example_folder) if example_folder is not None else {}
    while len(rows)<count:
        while table.view()['pending'] and len(rows)<count:
            image,layout,truth=render(table.view());layout.templates.update(examples)
            rows.append((image,layout,truth));table.act('call')
        if len(rows)<count:table.new_hand()
    return rows
