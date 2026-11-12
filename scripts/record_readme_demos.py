"""Record actual Qt windows into captioned README GIFs; never inject OCR values.

Run from the repo root with requirements-gui.txt and, on Linux, Tesseract.
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software python scripts/record_readme_demos.py
Captions identify the generated replay and development platform. The clips are
edited walkthroughs, not recordings of a commercial client or speed benchmarks.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from desktop.studio import Studio, ImageProvider
from desktop.app import Window, STYLE
from desktop.practice import PracticeTable
from desktop.model import Advisor

OUT = ROOT/'docs'/'media'
FONT = ROOT/'desktop/assets/DejaVuSans.ttf'


def pixels(qimage):
    data = QByteArray(); stream = QBuffer(data); stream.open(QIODevice.WriteOnly)
    qimage.save(stream, 'PNG')
    return Image.open(io.BytesIO(bytes(data))).convert('RGB')


def caption(frame, title, detail, stage):
    frame = frame.resize((1100, round(frame.height*1100/frame.width)), Image.Resampling.LANCZOS)
    image = Image.new('RGB', (1140, frame.height+150), '#091318')
    draw = ImageDraw.Draw(image)
    draw.text((24,16),'POKERLAB  /  '+stage, font=ImageFont.truetype(str(FONT),12),fill='#a5d5be')
    draw.text((24,39), title, font=ImageFont.truetype(str(FONT),24), fill='#eef3eb')
    draw.text((24,73), detail, font=ImageFont.truetype(str(FONT),13), fill='#95abae')
    image.paste(frame,(20,105))
    draw.rounded_rectangle((20,105,1120,105+frame.height),8,outline='#34534d',width=1)
    draw.text((24,frame.height+119),'Actual Qt interface · generated practice replay · '+platform.system()+' / offscreen · edited walkthrough',
        font=ImageFont.truetype(str(FONT),11),fill='#91a6a9')
    return image


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app=QApplication([]); app.setApplicationName('PokerLab README recording')
    QQuickStyle.setStyle('Basic')
    engine=QQmlApplicationEngine(); provider=ImageProvider();engine.addImageProvider('table',provider)
    studio=Studio(provider,backend='auto')
    engine.rootContext().setContextProperty('studio',studio)
    engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
    assert engine.rootObjects(), 'QML window failed to load'
    window=engine.rootObjects()[0];window.setWidth(1580);window.setHeight(1020)
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:app.processEvents();time.sleep(.005)
    def ready():
        until=time.monotonic()+35
        while time.monotonic()<until:
            pump(.025)
            if studio.snapshot and not studio.pending and studio.snapshot.stable:return
        raise RuntimeError('Reader did not produce a stable observation: '+str(studio.info))
    clips={}; evidence=[]; frames=[]
    def hold(win,title,detail,stage,seconds=1.5,widget=False):
        for _ in range(round(seconds*4)):
            pump(.25)
            image=pixels(win.grab().toImage() if widget else win.grabWindow())
            frames.append(caption(image,title,detail,stage))
    try:
        ready()
        hold(window,'Read the table. Inspect every value.','Cards, pot, stacks and controls in one observation workspace.','01 / VISION',2)
        for index in (1,2,3):
            studio.seek(index);ready()
            evidence.append({'frame':studio.frame_id,'replay_index':index,'fields_read':studio.info['read'],
                             'ocr_engine':studio.engine,'stable':studio.snapshot.stable})
            hold(window,'Follow the hand through the pixels.','Generated replay advances; the actual worker reads the changed image.','01 / VISION',1)
        window.grabWindow().save(str(ROOT/'desktop/previews/studio-overview.png'))
        window.setProperty('page',1);window.setProperty('overlays',True)
        studio.selectField('hole_1')
        hold(window,'Calibrate once. Keep the evidence.','Inspect field regions and teach labelled visual examples.','02 / TABLE SETUP',1.5)
        studio.selectField('pot');window.setProperty('filterGroup','Table')
        hold(window,'Every field has a visible source.','The highlighted region connects a reading to its table pixels.','02 / TABLE SETUP',1.5)
        window.grabWindow().save(str(ROOT/'desktop/previews/studio-setup.png'))
        window.setProperty('page',2);window.setProperty('overlays',False)
        for index in (4,5):
            studio.seek(index);ready()
            hold(window,'Replay a decision. Review what changed.','Step through observations before building a stronger policy.','03 / REPLAY LAB',1)
        window.grabWindow().save(str(ROOT/'desktop/previews/studio-replay.png'))
        window.setProperty('page',3)
        hold(window,'Measure responsiveness and reading coverage.','Diagnostics distinguish recognition, source age and queued UI dispatch.','04 / DIAGNOSTICS',2)
        window.grabWindow().save(str(ROOT/'desktop/previews/studio-diagnostics.png'))
        clips['vision-tour.gif']=frames;frames=[]
    finally:
        studio.close();window.close();app.processEvents()
    app.setStyle('Fusion');app.setStyleSheet(STYLE)
    workbench=Window();workbench.resize(1560,1040);workbench.show()
    try:
        table=PracticeTable(seed=38021,players=2);advisor=Advisor()
        for _ in range(100):
            view=table.view()
            if not view['pending']:table.new_hand();continue
            if view['board']:break
            result=advisor.recommend(view['observation'],'R06');table.act(result['action'],result['raise_to'] or 0)
        assert table.view()['board'], 'No postflop practice hand'
        workbench.player_count.blockSignals(True)
        workbench.player_count.setCurrentIndex(workbench.player_count.findData(2))
        workbench.player_count.blockSignals(False);workbench.table=table;workbench.refresh_practice()
        hold(workbench,'One workbench. 86 selectable policies.','80 original heuristics plus six experimental CFR-family options.','05 / AGENT LAB',1.5,True)
        for sid in ('S55','R03','R06'):
            workbench.strategy.setCurrentIndex(workbench.strategy.findData(sid));workbench.analyze()
            until=time.monotonic()+10
            while workbench.advising and time.monotonic()<until:pump(.025)
            assert workbench.latest is not None
            evidence.append({'strategy':sid,'action':workbench.latest['action'],
                             'policy_details':workbench.latest['policy_details']})
            hold(workbench,'Compare policies on the same public state.','S55 stays the default; research options show their actual policy path.','05 / AGENT LAB',1.75,True)
        workbench.grab().save(str(ROOT/'desktop/preview.png'))
        workbench.grab().save(str(ROOT/'research/figures/research-agent-gui.png'))
        workbench.use_suggestion()
        until=time.monotonic()+10
        while workbench.practice_busy and time.monotonic()<until:pump(.025)
        hold(workbench,'Play the suggestion in the local simulator.','PokerKit enforces legal moves and settles the practice hand.','06 / PRACTICE',2,True)
        clips['agent-lab.gif']=frames
    finally:
        workbench.close();app.processEvents()
    outputs=[]
    for name,images in clips.items():
        path=OUT/name
        # Edited walkthrough progress, outside the unmodified app capture.
        for index,image in enumerate(images):
            draw=ImageDraw.Draw(image)
            draw.line((24,image.height-8,image.width-24,image.height-8),fill='#233f3b',width=3)
            draw.line((24,image.height-8,24+(image.width-48)*(index+1)/len(images),image.height-8),fill='#b6e2c9',width=3)
        encoded=[]
        for image in images:
            # Adaptive GIF palettes can drop tiny red suit marks among a large
            # green UI. Reserve exact foreground/face colors before quantizing.
            palette=image.quantize(colors=253,method=Image.Quantize.MEDIANCUT)
            colors=palette.getpalette();colors.extend([0]*(768-len(colors)))
            colors[759:768]=[208,0,0,250,250,250,21,36,43]
            palette.putpalette(colors)
            encoded.append(image.quantize(palette=palette,dither=Image.Dither.NONE))
        images=encoded
        images[0].save(path,save_all=True,append_images=images[1:],duration=250,loop=0,optimize=True,disposal=1)
        outputs.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'bytes':path.stat().st_size,'duration_ms':len(images)*250,'size':images[0].size})
        print(name,path.stat().st_size,flush=True)
    (OUT/'manifest.json').write_text(json.dumps({'scope':'Actual app windows; generated table replay; edited walkthroughs, not speed benchmarks.',
        'platform':platform.platform(),'renderer':'Qt offscreen / software','outputs':outputs,'observations':evidence},indent=2)+'\n')


if __name__=='__main__':main()
