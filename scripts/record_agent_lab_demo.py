"""Record the README walkthrough of the Agent Lab from the running window.

Every frame is a grab of the real Qt window driven through its own buttons;
only the caption strip under it is added afterwards. Deterministic for a seed.

    QT_QPA_PLATFORM=offscreen python scripts/record_agent_lab_demo.py
"""
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from PIL import Image,ImageDraw,ImageFont
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QBuffer,QIODevice
import io

OUT=ROOT/'docs/media'
WIDTH=1140
FRAME_MS=250
FONT=str(ROOT/'desktop/assets/DejaVuSans.ttf')


def grab(widget):
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    widget.grab().save(buffer,'PNG')
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGB')


def main():
    from desktop.lab import LabWindow,OpponentsDialog,prepare
    from desktop.labmodel import RANDOM
    app=QApplication.instance() or QApplication([]);prepare(app)
    window=LabWindow(seed=120);window.show();app.processEvents()
    frames=[]

    def hold(title,detail,seconds,widget=None,source=None):
        for _ in range(3):app.processEvents()
        shot=grab(source or window)
        if widget is not None:
            top=grab(widget)
            shot=Image.blend(shot,Image.new('RGB',shot.size,'#0b1319'),.55)
            shot.paste(top,((shot.width-top.width)//2,(shot.height-top.height)//2))
        height=round(shot.height*WIDTH/shot.width)
        frame=Image.new('RGB',(WIDTH,height+62),'#0b1319')
        frame.paste(shot.resize((WIDTH,height),Image.Resampling.LANCZOS),(0,0))
        draw=ImageDraw.Draw(frame)
        draw.text((24,height+10),title,fill='#efce8b',font=ImageFont.truetype(FONT,17))
        draw.text((24,height+34),detail,fill='#8ea6b1',font=ImageFont.truetype(FONT,13))
        frames.extend([frame]*max(1,round(seconds*1000/FRAME_MS)))

    def play_until(test,limit=400,window=window):
        for _ in range(limit):
            view=window.view
            if test(view):return True
            if view['done']:window.next_hand()
            elif view['pending']:window.follow.click()
        raise RuntimeError('Scene not reached')

    hold('Sit down at a table.','Named opponents, a moving button and stacks that carry over. Your policy coaches; you decide.',2.25)
    hold('See where policies disagree.','S55 opens A9o from the hijack; the chart-based T04 folds it. The grid is S55 asked about all 169 hands.',2.5)
    window.follow.click()
    play_until(lambda v:v['pending'] and len(v['board'])>=3)
    hold('Every decision comes with its reasons.','Equity against the price you are offered, and what the other pinned policies would do here.',2.5)
    # A second table whose opening hand reaches a showdown when the coach is followed.
    second=LabWindow(seed=23);second.show();app.processEvents()
    play_until(lambda v:v['done'] and v['shown'] and v['active'][v['hero']],limit=40,window=second)
    hold('Showdowns reveal what they held.','Net result, session line and how often you agreed with the coach update after each hand.',2.25,source=second)
    second.close()
    dialog=OpponentsDialog(window,[RANDOM,'T04',RANDOM,'S18',RANDOM],False,True)
    dialog.setStyleSheet(app.styleSheet());dialog.show()
    hold('Choose who you play against.','Any of the 90 policies per seat, or Random. Hide their policies and read them from their play.',2.75,dialog)
    window.set_opponents(dialog.spec(),reveal=False,carry=True);dialog.close()
    play_until(lambda v:v['pending'] and not v['board'] and v['observation']['street_raises']>=1)
    hold('New table: who are these players?','Policies show as ??? until you choose to reveal them.',2.25)
    window.set_mode('quiz')
    hold('Quiz mode hides the answer.','Act first. The coach, the comparison and the range stay hidden until you do.',2)
    window.call.click() if window.view['pending'] else None
    hold('Then it grades the decision.','Same action, same action with a different size, or different, with the reason.',2.25)
    window.set_mode('watch')
    for _ in range(70):window.watch_step()
    hold('Or watch a policy play your seat.','Hands run by themselves and the session line fills in.',2.25)
    window.set_mode('coach')
    window.players.setCurrentIndex(window.players.findData(2))
    window.depth.setCurrentIndex(window.depth.findData(12))
    window.strategy.setCurrentIndex(window.strategy.findData('T01'))
    window.four.setChecked(True)
    play_until(lambda v:v['pending'] and window.advice['policy_details'].get('policy_path')=='nash_jam')
    hold('Heads-up, 12 big blinds: the Nash jam range.','T01 was solved in this repository; split cells are mixed actions.',2.75)
    window.close();app.processEvents()

    for index,image in enumerate(frames):
        frames[index]=image=image.copy()
        draw=ImageDraw.Draw(image)
        draw.line((24,image.height-4,image.width-24,image.height-4),fill='#1c2d38',width=3)
        draw.line((24,image.height-4,24+(image.width-48)*(index+1)/len(frames),image.height-4),fill='#7fd1b5',width=3)
    encoded=[]
    for image in frames:
        # Keep the exact suit and card-face colours through palette reduction.
        palette=image.quantize(colors=250,method=Image.Quantize.MEDIANCUT)
        colors=palette.getpalette();colors.extend([0]*(768-len(colors)))
        colors[750:768]=[210,31,43, 251,251,248, 23,35,42, 31,111,210, 29,138,74, 239,206,139]
        palette.putpalette(colors)
        encoded.append(image.quantize(palette=palette,dither=Image.Dither.NONE))
    path=OUT/'agent-lab.gif'
    encoded[0].save(path,save_all=True,append_images=encoded[1:],duration=FRAME_MS,loop=0,optimize=True,disposal=1)
    entry={'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
           'bytes':path.stat().st_size,'duration_ms':len(encoded)*FRAME_MS,'size':list(encoded[0].size),
           'recorded_by':'scripts/record_agent_lab_demo.py','platform':platform.platform()}
    manifest_path=OUT/'manifest.json';manifest=json.loads(manifest_path.read_text())
    manifest['outputs']=[o for o in manifest['outputs'] if o['path']!=entry['path']]+[entry]
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(path.name,entry['bytes'],entry['duration_ms'],entry['size'])


if __name__=='__main__':main()
