"""Mac-friendly Qt workbench; capture/recognition/policy run in workers."""
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys
import time

from PIL import Image
from PySide6.QtCore import Qt, QRectF, QPointF, QThreadPool, QRunnable, QObject, Signal, QTimer, QStandardPaths
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QImage
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget, QFrame, QScrollArea,
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QCheckBox, QGroupBox,
    QFileDialog, QMessageBox, QPlainTextEdit, QSizePolicy, QSplitter)

from .model import Advisor, STRATEGIES, example
from .practice import PracticeTable
from .render import render_table, standard_profile
from .vision import Profile, Reader, StableReadings, FIELDS, CARD_KEYS, crop, tesseract_path


STYLE="""
QMainWindow, QWidget#root { background: #0c141c; color: #dce7eb; }
QWidget { font-family: -apple-system, 'Helvetica Neue', sans-serif; font-size: 13px; color: #dce7eb; }
QLabel#brand { font-size: 25px; font-weight: 700; letter-spacing: 2px; }
QLabel#muted { color: #8fa7b2; }
QLabel#action { color: #efd295; font-size: 29px; font-weight: 700; }
QLabel#eyebrow { color: #82cbb7; font-size: 11px; font-weight: 600; letter-spacing: 2px; }
QFrame#panel, QGroupBox { background: #131f29; border: 1px solid #2a3c48; border-radius: 12px; }
QGroupBox { margin-top: 12px; padding-top: 16px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #9eb8c2; }
QPushButton { background: #233745; border: 1px solid #3a5262; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #304c5d; }
QPushButton:disabled { color: #637783; background: #16232d; border-color: #273943; }
QPushButton#primary { background: #bcdcca; color: #10251d; border-color: #bcdcca; }
QPushButton#primary:hover { background: #d1ecdd; }
QPushButton#primary:disabled { background: #1b2c32; color: #70878e; border-color: #34454b; }
QPushButton#gold { background: #dfc48a; color: #242014; border-color: #dfc48a; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit { background: #0d1821; border: 1px solid #344a59; border-radius: 6px; padding: 6px; selection-background-color: #365e66; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #8cc7b4; }
QTabWidget::pane { border: 0; padding-top: 10px; }
QTabBar::tab { background: #15232d; padding: 11px 20px; margin-right: 6px; border-radius: 6px; color: #94acb8; }
QTabBar::tab:selected { background: #28413f; color: #c9e5d8; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #111c25; width: 8px; }
QScrollBar::handle:vertical { background: #3a5261; border-radius: 4px; min-height: 24px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QToolTip { background: #213642; color: white; padding: 5px; border: 1px solid #53707b; }
"""


def text(value, muted=False):
    label=QLabel(value)
    label.setWordWrap(True)
    if muted:
        label.setObjectName("muted")
    return label


def button(label, slot, primary=False):
    b=QPushButton(label)
    if primary:
        b.setObjectName("primary")
    b.clicked.connect(slot)
    return b


class Work(QRunnable):
    def __init__(self,fn,job_id,emit):
        super().__init__()
        self.fn=fn
        self.job_id=job_id
        self.emit=emit

    def run(self):
        try:
            self.emit(self.job_id,self.fn(),None)
        except Exception as exc:
            self.emit(self.job_id,None,f"{type(exc).__name__}: {exc}")


class Canvas(QWidget):
    selected=Signal(object)

    def __init__(self,editable=False):
        super().__init__()
        self.setMinimumSize(450,300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.image=None
        self.pixmap=None
        self.editable=editable
        self.regions={}
        self.start=None
        self.drag=None
        self.highlight=None

    def set_image(self,image):
        self.image=image.copy().convert("RGB")
        rgb=self.image.tobytes()
        q=QImage(rgb,self.image.width,self.image.height,self.image.width*3,QImage.Format.Format_RGB888).copy()
        self.pixmap=QPixmap.fromImage(q)
        self.update()

    def area(self):
        if not self.image:
            return QRectF()
        scale=min(self.width()/self.image.width,self.height()/self.image.height)
        w,h=self.image.width*scale,self.image.height*scale
        return QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)

    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),QColor("#0d171f"))
        if not self.pixmap:
            p.setPen(QColor("#8ba4b0"))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"Load an image or capture a display\nthen draw the card and number regions.")
            return
        area=self.area()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(area,self.pixmap,QRectF(self.pixmap.rect()))
        if self.editable:
            p.setPen(QPen(QColor("#8dd6bf"),1.5))
            for name,(x,y,w,h) in self.regions.items():
                rect=QRectF(area.x()+x*area.width(),area.y()+y*area.height(),w*area.width(),h*area.height())
                p.drawRect(rect)
                p.drawText(rect.topLeft()+QPointF(2,-3),name)
            if self.drag:
                p.setPen(QPen(QColor("#efd295"),2))
                p.drawRect(self.drag)

    def mousePressEvent(self,event):
        if self.editable and self.area().contains(event.position()):
            self.start=event.position()

    def mouseMoveEvent(self,event):
        if self.start is not None:
            self.drag=QRectF(self.start,event.position()).normalized().intersected(self.area())
            self.update()

    def mouseReleaseEvent(self,event):
        if self.start is None:
            return
        self.drag=QRectF(self.start,event.position()).normalized().intersected(self.area())
        area=self.area()
        rect=self.drag
        self.start=None
        self.drag=None
        if rect.width()>4 and rect.height()>4:
            self.selected.emit([(rect.x()-area.x())/area.width(),(rect.y()-area.y())/area.height(),rect.width()/area.width(),rect.height()/area.height()])
        self.update()


class Window(QMainWindow):
    job_done=Signal(int,object,object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Poker Lab — Desktop Workbench")
        self.resize(1460,990)
        self.pool=QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.jobs={}
        self.job_counter=0
        self.job_done.connect(self.finish_work,Qt.ConnectionType.QueuedConnection)
        self.advisor=Advisor()
        self.revision=0
        self.scan_revision=0
        self.advising=False
        self.scanning=False
        self.practice_busy=False
        self.loading=True
        self.latest=None
        self.last_view=None
        self.source_time=None
        self.source_is_live=False
        self.reader_result=None
        self.stable=StableReadings()
        data=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        data.mkdir(parents=True,exist_ok=True)
        self.profile_path=data/"layouts"/"default.json"
        self.profile_path.parent.mkdir(parents=True,exist_ok=True)
        self.profile=Profile()
        if self.profile_path.exists():
            try:
                self.profile=Profile.load(self.profile_path)
            except (ValueError,OSError,TypeError):
                pass
        self.table=PracticeTable()
        self.timer=QTimer(self)
        self.timer.setInterval(1100)
        self.timer.timeout.connect(self.scan_screen)
        self.age_timer=QTimer(self)
        self.age_timer.setInterval(250)
        self.age_timer.timeout.connect(self.update_age)
        self.build()
        self.loading=False
        self.refresh_practice()
        self.age_timer.start()

    def run(self,fn,done):
        self.job_counter+=1
        work=Work(fn,self.job_counter,self.job_done.emit)
        self.jobs[self.job_counter]=(work,done)
        self.pool.start(work)

    def finish_work(self,job_id,result,error):
        job=self.jobs.pop(job_id,None)
        if job:
            job[1](result,error)

    def build(self):
        root=QWidget();root.setObjectName("root")
        outer=QVBoxLayout(root);outer.setContentsMargins(24,20,24,16);outer.setSpacing(16)
        heading=QHBoxLayout()
        brand=QLabel("POKER / LAB");brand.setObjectName("brand")
        heading.addWidget(brand)
        heading.addWidget(text("Desktop workbench\nPractice. Read. Review.",True))
        heading.addStretch()
        heading.addWidget(text("STRATEGY",True))
        self.strategy=QComboBox()
        for sid in sorted(STRATEGIES,key=lambda k:(not k.startswith('R'),k)):
            s=STRATEGIES[sid]
            self.strategy.addItem(f"{sid} · {s.label}",sid)
            self.strategy.setItemData(self.strategy.count()-1,s.source,Qt.ItemDataRole.ToolTipRole)
        self.strategy.setCurrentIndex(self.strategy.findData("S55"))
        self.strategy.setMaximumWidth(340)
        self.strategy.currentIndexChanged.connect(self.invalidate)
        heading.addWidget(self.strategy)
        outer.addLayout(heading)
        split=QSplitter(Qt.Orientation.Horizontal)
        self.tabs=QTabWidget()
        self.tabs.addTab(self.practice_tab(),"Practice table")
        self.tabs.addTab(self.reader_tab(),"Table reader")
        self.tabs.currentChanged.connect(self.mode_changed)
        split.addWidget(self.tabs)
        aside=self.aside()
        split.addWidget(aside)
        split.setStretchFactor(0,1);split.setStretchFactor(1,0)
        split.setSizes([1000,350])
        outer.addWidget(split,1)
        self.status=text("Ready",True)
        outer.addWidget(self.status)
        outer.addWidget(text("Research prototype · Equity assumes random opponent hands · Use live assistance only where expressly permitted",True))
        self.setCentralWidget(root)

    def practice_tab(self):
        widget=QWidget();layout=QVBoxLayout(widget);layout.setContentsMargins(0,0,8,0)
        row=QHBoxLayout()
        row.addWidget(text("NO-LIMIT HOLD’EM",True))
        self.player_count=QComboBox();self.player_count.addItem('Six players',6);self.player_count.addItem('Heads-up · two players',2)
        self.player_count.currentIndexChanged.connect(self.change_practice_players);row.addWidget(self.player_count);row.addStretch()
        self.new_button=button("New hand",self.new_hand)
        row.addWidget(self.new_button)
        row.addWidget(button("Send frame to reader",self.practice_frame))
        layout.addLayout(row)
        self.table_canvas=Canvas();layout.addWidget(self.table_canvas,1)
        actions=QHBoxLayout()
        self.fold=button("Fold",lambda:self.play("fold"))
        self.call=button("Check / Call",lambda:self.play("call"))
        self.raise_amount=QSpinBox();self.raise_amount.setMaximum(1000000000)
        self.raise_button=button("Raise to",lambda:self.play("raise",self.raise_amount.value()))
        self.use_advice=button("Use suggested action",self.use_suggestion,True)
        for item in (self.fold,self.call,self.raise_button,self.raise_amount,self.use_advice):
            actions.addWidget(item)
        layout.addLayout(actions)
        layout.addWidget(text("Practice chips only. Each hand starts at 100 big blinds; your position rotates.",True))
        self.history=QPlainTextEdit();self.history.setReadOnly(True);self.history.setMaximumHeight(145)
        layout.addWidget(self.history)
        return widget

    def reader_tab(self):
        widget=QWidget();layout=QVBoxLayout(widget);layout.setContentsMargins(0,0,8,0)
        row=QHBoxLayout()
        row.addWidget(button("Load image",self.load_image))
        self.monitor=QSpinBox();self.monitor.setRange(1,16);self.monitor.setValue(self.profile.monitor)
        self.monitor.setPrefix("Display ")
        self.monitor.valueChanged.connect(self.layout_changed)
        row.addWidget(self.monitor)
        row.addWidget(button("Capture",lambda:self.scan_screen(read=False)))
        self.live_button=button("Scan until stable",self.toggle_live,True)
        row.addWidget(self.live_button)
        row.addWidget(button("Full display",self.full_display))
        layout.addLayout(row)
        self.screen_canvas=Canvas(True)
        self.screen_canvas.regions=self.profile.regions
        self.screen_canvas.selected.connect(self.select_region)
        layout.addWidget(self.screen_canvas,1)
        row=QHBoxLayout()
        self.field=QComboBox();self.field.addItem("Table bounds (crop display)","capture")
        for name in FIELDS:
            self.field.addItem(name.replace("_"," "),name)
        self.field.setCurrentIndex(1)
        row.addWidget(self.field,1)
        row.addWidget(button("Remove region",self.remove_region))
        self.teach_card=QComboBox()
        from .model import CARD_TEXT
        self.teach_card.addItems(CARD_TEXT)
        row.addWidget(self.teach_card)
        row.addWidget(button("Teach card",self.teach))
        layout.addLayout(row)
        row=QHBoxLayout()
        row.addWidget(button("Read this frame",self.read_frame,True))
        row.addWidget(button("Save layout",self.save_profile))
        row.addWidget(button("Load layout",self.load_profile))
        self.scale=QSpinBox();self.scale.setRange(1,10000);self.scale.setValue(self.profile.chip_scale)
        self.scale.setPrefix("Chip scale × ");self.scale.valueChanged.connect(self.layout_changed)
        self.scale.setToolTip("Use 100 for dollar displays with cents; enter every state amount in the same scaled units.")
        row.addWidget(self.scale)
        layout.addLayout(row)
        self.reader_note=text("Draw a tight box around each whole card and each amount. New card art needs labelled examples. Action history and table context need manual review.",True)
        layout.addWidget(self.reader_note)
        self.diagnostics=QPlainTextEdit();self.diagnostics.setReadOnly(True);self.diagnostics.setMaximumHeight(120)
        layout.addWidget(self.diagnostics)
        return widget

    def aside(self):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(330);scroll.setMaximumWidth(470)
        panel=QWidget();panel.setObjectName("root")
        layout=QVBoxLayout(panel);layout.setContentsMargins(12,0,0,0);layout.setSpacing(10)
        advice=QFrame();advice.setObjectName("panel")
        box=QVBoxLayout(advice);box.setContentsMargins(18,17,18,17)
        eyebrow=QLabel("NEXT DECISION");eyebrow.setObjectName("eyebrow");box.addWidget(eyebrow)
        self.action=text("Ready to review");self.action.setObjectName("action");box.addWidget(self.action)
        self.detail=text("Choose Get recommendation.",True);box.addWidget(self.detail)
        self.metrics=text("Equity —     Pot odds —",True);box.addWidget(self.metrics)
        self.time_label=text("Policy —     Frame —",True);box.addWidget(self.time_label)
        self.analyze_button=button("Get recommendation",self.analyze,True);box.addWidget(self.analyze_button)
        layout.addWidget(advice)
        self.state_mode=text("Practice · engine-verified state",True);layout.addWidget(self.state_mode)
        self.confirm=QCheckBox("I checked cards, amounts and action history")
        self.confirm.setToolTip("Screen reading does not infer the complete action history. Review every field before requesting advice.")
        self.confirm.toggled.connect(self.confirm_changed)
        self.confirm.setVisible(False);layout.addWidget(self.confirm)
        form_group=QGroupBox("Hand state")
        form=QFormLayout(form_group);form.setContentsMargins(12,18,12,12)
        self.edit={}
        labels=[("hole","Your cards"),("board","Board"),("pot","Pot"),("stack","Your stack"),
                ("to_call","Call cost"),("bet","Your bet this street"),("big_blind","Big blind"),
                ("players","Seats at table"),("active","Active in hand"),("seat","Seat index (0–7)"),
                ("position","Position (early → late)"),("street_raises","Raises this street"),
                ("min_raise_to","Minimum raise TO"),("max_raise_to","Maximum raise TO"),
                ("preflop_raiser","You raised preflop"),("checked_before","You checked this street"),
                ("opponent_looseness","Opponent looseness"),("opponent_aggression","Opponent aggression"),
                ("tournament","Tournament"),("remaining","Players remaining")]
        for name,label in labels:
            if name in ("hole","board"):
                w=QLineEdit();w.textChanged.connect(self.invalidate)
            elif name in ("preflop_raiser","checked_before","tournament"):
                w=QCheckBox();w.toggled.connect(self.invalidate)
            elif name in ("position","opponent_looseness","opponent_aggression"):
                w=QDoubleSpinBox();w.setRange(0,1);w.setSingleStep(.05);w.setDecimals(2);w.valueChanged.connect(self.invalidate)
            else:
                w=QSpinBox();w.setRange(-1 if "raise_to" in name else 0,1000000000)
                if "raise_to" in name:
                    w.setSpecialValueText("Unavailable")
                if name in ("players","active","remaining"):
                    w.setMaximum(10000 if name=="remaining" else 8)
                if name=="seat":
                    w.setMaximum(7)
                w.valueChanged.connect(self.invalidate)
            self.edit[name]=w;form.addRow(label,w)
        layout.addWidget(form_group)
        layout.addWidget(text("Raise amounts include chips already bet this street. Unavailable bounds disable raising. Equity is a heuristic estimate, not action EV or a profitability forecast.",True))
        layout.addWidget(button("Load example state",self.load_example))
        layout.addWidget(button("Export current state",self.export_state))
        layout.addStretch()
        scroll.setWidget(panel)
        return scroll

    def set_state(self,data):
        self.loading=True
        for name,w in self.edit.items():
            value=data[name]
            w.setStyleSheet("")
            if isinstance(w,QLineEdit):
                w.setText(" ".join(value) if not isinstance(value,str) else value)
            elif isinstance(w,QCheckBox):
                w.setChecked(value)
            else:
                w.setValue(-1 if value is None else value)
        self.loading=False
        self.invalidate()

    def state_data(self):
        data={}
        for name,w in self.edit.items():
            value=w.text() if isinstance(w,QLineEdit) else w.isChecked() if isinstance(w,QCheckBox) else w.value()
            data[name]=None if "raise_to" in name and value==-1 else value
        return data

    def invalidate(self,*args):
        if self.loading:
            return
        self.revision+=1;self.latest=None
        self.action.setText("Ready to review" if self.tabs.currentIndex()==0 else "Needs review")
        self.detail.setText("Request a fresh recommendation for this state.")
        self.metrics.setText("Equity —     Pot odds —")
        self.use_advice.setEnabled(False)
        if self.tabs.currentIndex()!=0:
            self.confirm.blockSignals(True);self.confirm.setChecked(False);self.confirm.blockSignals(False)
        self.update_controls()

    def confirm_changed(self,checked):
        if not checked:
            self.invalidate()
        self.update_controls()

    def update_controls(self):
        if not hasattr(self,"edit"):
            return
        practice=self.tabs.currentIndex()==0
        pending=bool(self.last_view and self.last_view["pending"])
        self.analyze_button.setEnabled(not self.advising and not self.practice_busy and ((practice and pending) or (not practice and self.confirm.isChecked() and not self.timer.isActive())))
        for w in self.edit.values():
            w.setEnabled(not practice)
        self.confirm.setVisible(not practice)

    def refresh_practice(self):
        view=self.table.view();self.last_view=view
        self.table_canvas.set_image(render_table(view))
        self.history.setPlainText("\n".join(view["history"]) or "New hand · waiting for action")
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())
        self.invalidate()
        pending=view["pending"]
        if view["observation"]:
            self.set_state(view["observation"])
            o=view["observation"]
            lo,hi=o["min_raise_to"],o["max_raise_to"]
            self.raise_amount.setRange(lo or 0,hi or 0)
            self.raise_amount.setValue(lo or 0)
            self.call.setText(f"Call {o['to_call']}" if o["to_call"] else "Check")
            self.raise_button.setEnabled(lo is not None)
            self.fold.setEnabled(bool(o["to_call"]))
        else:
            self.raise_button.setEnabled(False);self.fold.setEnabled(False)
            self.action.setText("Hand complete")
            self.detail.setText(f"Result: {view['net']:+d} practice chips. Start another hand.")
        self.call.setEnabled(pending)
        self.new_button.setEnabled(True)
        self.status.setText(f"Hand {view['hand_no']} · {'Your decision' if pending else 'Complete'} · exact engine state")
        self.update_controls()

    def play(self,action,amount=0):
        if self.practice_busy:
            return
        self.invalidate();self.practice_busy=True;self.tabs.setEnabled(False)
        for b in (self.fold,self.call,self.raise_button,self.use_advice,self.new_button):
            b.setEnabled(False)
        self.update_controls()
        def done(result,error):
            self.practice_busy=False;self.tabs.setEnabled(True)
            if error:
                self.message(error)
            self.refresh_practice()
        self.run(lambda:self.table.act(action,amount),done)

    def new_hand(self):
        if self.practice_busy:
            return
        self.invalidate();self.practice_busy=True;self.tabs.setEnabled(False);self.update_controls()
        for b in (self.fold,self.call,self.raise_button,self.use_advice,self.new_button):
            b.setEnabled(False)
        def done(result,error):
            self.practice_busy=False;self.tabs.setEnabled(True)
            if error:
                self.message(error)
            self.refresh_practice()
        self.run(self.table.new_hand,done)

    def change_practice_players(self):
        if self.practice_busy:return
        players=self.player_count.currentData()
        self.invalidate();self.practice_busy=True;self.player_count.setEnabled(False);self.tabs.setEnabled(False)
        self.update_controls()
        def done(result,error):
            self.practice_busy=False;self.player_count.setEnabled(True);self.tabs.setEnabled(True)
            if error:self.message(error)
            else:self.table=result
            self.refresh_practice()
        self.run(lambda:PracticeTable(players=players),done)

    def use_suggestion(self):
        if self.latest and self.latest["revision"]==self.revision and self.tabs.currentIndex()==0:
            result=self.latest
            self.play(result["action"],result["raise_to"] or 0)

    def mode_changed(self,index):
        self.scan_revision+=1
        self.stop_live();self.invalidate()
        self.state_mode.setText("Practice · engine-verified state" if index==0 else "Table reader · confirm the complete hand state")
        if index==0:
            self.refresh_practice()
        else:
            self.set_state({**example(),"hole":(),"board":(),"pot":0,"stack":2000,
                            "to_call":0,"bet":0,"seat":0,"active":6,"position":.5,
                            "street_raises":0,"preflop_raiser":False,
                            "min_raise_to":None,"max_raise_to":None})
        self.update_controls()

    def analyze(self):
        if not self.analyze_button.isEnabled() or self.advising:
            return
        self.advising=True;self.update_controls()
        revision=self.revision
        data=self.state_data();strategy=self.strategy.currentData()
        if self.tabs.currentIndex()==0 and self.last_view and self.last_view.get('observation'):
            data['heads_up_in_position']=self.last_view['observation'].get('heads_up_in_position')
        start=time.monotonic()
        self.action.setText("Thinking…")
        def done(result,error):
            self.advising=False;self.update_controls()
            if revision!=self.revision:
                return
            if error:
                self.action.setText("Needs review");self.detail.setText(error);return
            if time.monotonic()-start>5:
                self.action.setText("Deadline reached");self.detail.setText("No recommendation retained. Request a fresh decision.");return
            if self.source_is_live and self.tabs.currentIndex()==1 and self.source_time and time.monotonic()-self.source_time>10:
                self.action.setText("Frame expired");self.detail.setText("Capture a fresh table state before requesting advice.");return
            self.latest={**result,"revision":revision}
            action=result["action"]
            title=f"RAISE TO {result['raise_to']}" if action=="raise" else f"CALL {result['call_cost']}" if action=="call" else action.upper()
            self.action.setText(title)
            scope=result.get('policy_details',{}).get('scope','Heuristic recommendation; no action EV estimate.')
            self.detail.setText(f"{strategy} · {STRATEGIES[strategy].family.replace('_',' ')}\n{scope}")
            self.metrics.setText(f"Random-range equity {result['equity']:.0%}   ·   Pot odds {result['pot_odds']:.0%}")
            self.use_advice.setEnabled(self.tabs.currentIndex()==0)
            self.update_age()
        self.run(lambda:self.advisor.recommend(data,strategy),done)

    def update_age(self):
        if not hasattr(self,"time_label"):
            return
        policy=f"{self.latest['policy_ms']:.1f} ms" if self.latest else "—"
        frame="engine" if self.tabs.currentIndex()==0 else "image / manual"
        if self.source_is_live and self.source_time and self.tabs.currentIndex()==1:
            age=time.monotonic()-self.source_time;frame=f"{age:.1f} s old"
            if age>10 and self.latest:
                self.latest=None;self.action.setText("Frame expired")
                self.detail.setText("Capture again; the last recommendation has expired.")
        self.time_label.setText(f"Policy {policy}   ·   Frame {frame}")

    def load_example(self):
        self.tabs.setCurrentIndex(1);self.stop_live()
        self.source_is_live=False;self.source_time=None
        self.set_state(example())
        self.state_mode.setText("Manual example · editable state")

    def export_state(self):
        name,_=QFileDialog.getSaveFileName(self,"Export current state","hand_state.json","JSON (*.json)")
        if name:
            try:
                Path(name).write_text(json.dumps(self.state_data(),indent=2)+"\n")
                self.status.setText("Current hand state exported.")
            except OSError as exc:
                self.message(str(exc))

    def set_source(self,image,live=False,stamp=None):
        self.screen_canvas.set_image(image)
        self.source_is_live=live;self.source_time=stamp
        self.invalidate()

    def load_image(self):
        name,_=QFileDialog.getOpenFileName(self,"Load table image","","Images (*.png *.jpg *.jpeg *.webp)")
        if name:
            self.stop_live();self.scan_revision+=1;self.stable=StableReadings()
            try:
                with Image.open(name) as im:
                    self.set_source(im.convert("RGB"))
                self.reader_note.setText("Image loaded. Draw regions or load a matching layout, then read the frame.")
            except (OSError,ValueError) as exc:
                self.message(str(exc))

    def practice_frame(self):
        if self.practice_busy:
            return
        view=self.table.view()
        self.tabs.setCurrentIndex(1)
        self.profile=standard_profile()
        self.screen_canvas.regions=self.profile.regions
        self.set_source(render_table(view))
        if view["observation"]:
            self.set_state(view["observation"])
        self.reader_note.setText("Bundled layout loaded. Cards, board, pot and stack can be read; other values came from the practice engine and still need review.")
        self.read_frame()

    def layout_changed(self,*args):
        if not hasattr(self,"scale") or self.loading:
            return
        self.profile.monitor=self.monitor.value();self.profile.chip_scale=self.scale.value()
        self.scan_revision+=1;self.stable=StableReadings();self.stop_live();self.invalidate()

    def select_region(self,rect):
        if not self.screen_canvas.image:
            return
        self.stop_live();key=self.field.currentData()
        try:
            image=crop(self.screen_canvas.image,rect)
        except ValueError as exc:
            self.message(str(exc));return
        if key=="capture":
            base=self.profile.capture or [0,0,1,1]
            self.profile.capture=[base[0]+rect[0]*base[2],base[1]+rect[1]*base[3],rect[2]*base[2],rect[3]*base[3]]
            self.profile.regions={};self.screen_canvas.regions=self.profile.regions
            self.set_source(image,self.source_is_live,self.source_time)
            self.field.setCurrentIndex(1)
        else:
            self.profile.regions[key]=rect
            self.screen_canvas.update()
            self.reader_note.setText(f"Saved {key.replace('_',' ')} region. Draw the next field or read this frame.")
        self.layout_changed()

    def remove_region(self):
        self.profile.regions.pop(self.field.currentData(),None)
        self.screen_canvas.update();self.layout_changed()

    def full_display(self):
        self.profile.capture=None;self.profile.regions={}
        self.screen_canvas.regions=self.profile.regions
        self.layout_changed();self.scan_screen(read=False)

    def teach(self):
        key=self.field.currentData()
        if key not in CARD_KEYS or key not in self.profile.regions or not self.screen_canvas.image:
            self.message("Select a calibrated card region with a visible face-up card first.");return
        try:
            card=self.teach_card.currentText()
            folder=self.profile_path.parent/"templates";folder.mkdir(parents=True,exist_ok=True)
            crop(self.screen_canvas.image,self.profile.regions[key]).save(folder/f"{card}.png")
            self.profile.templates[card]=f"templates/{card}.png"
            self.reader_note.setText(f"Learned {card} from {key}. Save the layout to keep it. Each new card design needs its own labelled template.")
            self.layout_changed()
        except (OSError,ValueError) as exc:
            self.message(str(exc))

    def save_profile(self):
        name,_=QFileDialog.getSaveFileName(self,"Save table layout",str(self.profile_path),"JSON (*.json)")
        if name:
            try:
                dest=Path(name);dest.parent.mkdir(parents=True,exist_ok=True)
                for rel in self.profile.templates.values():
                    source=self.profile_path.parent/rel;target=dest.parent/rel
                    if source.resolve()!=target.resolve():
                        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
                self.profile.save(dest);self.profile_path=dest
                self.status.setText("Table layout saved.")
            except (OSError,ValueError) as exc:
                self.message(str(exc))

    def load_profile(self):
        name,_=QFileDialog.getOpenFileName(self,"Load table layout",str(self.profile_path.parent),"JSON (*.json)")
        if name:
            try:
                self.stop_live();self.profile=Profile.load(name);self.profile_path=Path(name)
                self.screen_canvas.regions=self.profile.regions
                self.loading=True
                self.monitor.setValue(self.profile.monitor);self.scale.setValue(self.profile.chip_scale)
                self.loading=False
                self.screen_canvas.update();self.layout_changed()
                self.status.setText("Layout loaded. Capture a matching table or load an image.")
            except (OSError,ValueError,TypeError) as exc:
                self.message(str(exc))

    def toggle_live(self):
        if self.timer.isActive():
            self.stop_live();return
        self.stable=StableReadings();self.invalidate()
        self.timer.start();self.live_button.setText("Stop scan")
        self.scan_screen()
        self.update_controls()

    def stop_live(self):
        self.timer.stop()
        if hasattr(self,"live_button"):
            self.live_button.setText("Scan until stable")
        self.update_controls()

    def scan_screen(self,read=True):
        if self.scanning:
            return
        self.scanning=True
        generation=self.scan_revision
        profile=Profile(**asdict(self.profile));folder=self.profile_path.parent
        def job():
            import mss
            with mss.mss() as sct:
                if profile.monitor>=len(sct.monitors):
                    raise ValueError(f"Display {profile.monitor} does not exist; available: 1–{len(sct.monitors)-1}.")
                region=dict(sct.monitors[profile.monitor])
                if profile.capture:
                    x,y,w,h=profile.capture
                    left,top,width,height=region["left"],region["top"],region["width"],region["height"]
                    region={"left":left+round(x*width),"top":top+round(y*height),"width":round(w*width),"height":round(h*height)}
                shot=sct.grab(region)
                image=Image.frombytes("RGB",shot.size,shot.rgb)
            stamp=time.monotonic()
            result=Reader(profile,folder).read(image) if read else None
            return image,stamp,result
        def done(result,error):
            self.scanning=False
            if generation!=self.scan_revision:
                return
            if error:
                self.stop_live()
                self.reader_note.setText(error+"\nOn Mac, allow Screen Recording for the launching Terminal/Python application in System Settings → Privacy & Security, then relaunch.")
                return
            image,stamp,reading=result
            self.set_source(image,True,stamp)
            if reading:
                self.apply_reading(reading)
                if self.stable.add(reading) and self.timer.isActive():
                    self.stop_live()
                    self.reader_note.setText("Two matching reads captured. Review all fields, especially history, position and active players, before requesting advice.")
        self.run(job,done)

    def read_frame(self):
        if self.scanning or not self.screen_canvas.image:
            if not self.screen_canvas.image:
                self.message("Load an image or capture a table first.")
            return
        self.scanning=True;generation=self.scan_revision
        image=self.screen_canvas.image.copy();profile=Profile(**asdict(self.profile));folder=self.profile_path.parent
        def done(result,error):
            self.scanning=False
            if generation!=self.scan_revision:
                return
            if error:
                self.reader_note.setText(error);return
            self.apply_reading(result)
        self.run(lambda:Reader(profile,folder).read(image),done)

    def apply_reading(self,result):
        self.reader_result=result;self.loading=True
        values=result["values"]
        if all(k in values and values[k] for k in CARD_KEYS[:2]):
            self.edit["hole"].setText(" ".join(values[k] for k in CARD_KEYS[:2]))
        if all(k in values for k in CARD_KEYS[2:]):
            board=[values[k] for k in CARD_KEYS[2:]]
            # Do not silently accept a missing middle card followed by a card.
            present=[c for c in board if c]
            if board[:len(present)]==present:
                self.edit["board"].setText(" ".join(present))
            else:
                result["errors"]["board"]="Non-contiguous board slots; review manually."
        for key in ("pot","stack","to_call","bet","min_raise_to","max_raise_to"):
            if key in values:
                self.edit[key].setValue(-1 if values[key] is None else values[key])
        uncertain=set(result["errors"])
        if any(k in uncertain for k in CARD_KEYS[:2]):
            uncertain.add("hole")
        if any(k in uncertain for k in CARD_KEYS[2:]):
            uncertain.add("board")
        for key,w in self.edit.items():
            w.setStyleSheet("border: 1px solid #dfb876;" if key in uncertain else "")
        self.loading=False;self.invalidate()
        lines=[f"Reader {result['reader_ms']:.0f} ms · scores are not calibrated probabilities"]
        lines += [f"{k}: {v if v is not None else 'empty'}   [{result['scores'][k]:.2f}]" for k,v in values.items()]
        lines += [f"REVIEW {k}: {v}" for k,v in result["errors"].items()]
        self.diagnostics.setPlainText("\n".join(lines))
        self.reader_note.setText("Review required: unread fields retain their prior values. Check the entire state and action history before confirming.")

    def message(self,value):
        QMessageBox.information(self,"Poker Lab",value)

    def closeEvent(self,event):
        self.timer.stop();self.age_timer.stop()
        self.pool.waitForDone(6000)
        event.accept()


def main():
    app=QApplication(sys.argv)
    app.setApplicationName("PokerAgentLab")
    app.setOrganizationName("PokerAgentLab")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window=Window();window.show()
    sys.exit(app.exec())
