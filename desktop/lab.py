"""Agent Lab: play, get coached, compare policies and see their ranges.

The window is drawn with vector painters, so it stays sharp at any size, and
every number comes from `labmodel` (engine state, policy calls, simple facts).
Nothing here reads a screen or touches another application.
"""
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, Signal
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QFontDatabase, QPainterPath, QLinearGradient,
                           QRadialGradient, QKeySequence, QShortcut, QBrush)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
                               QHBoxLayout, QGridLayout, QFrame, QComboBox, QSpinBox, QSlider, QPlainTextEdit,
                               QSizePolicy, QToolTip, QButtonGroup, QScrollArea, QCheckBox, QDialog, QDialogButtonBox)

from .labmodel import (LabTable, Coach, STRATEGIES, DEPTHS, STREETS, RANDOM, PRESETS, DEFAULT_LINEUP,
                       bet_presets, strategy_title)

BG, PANEL, LINE = "#0b1319", "#111d25", "#263843"
TEXT, MUTED, FAINT = "#dfe9ec", "#8ea6b1", "#5c7480"
MINT, GOLD, RED, BLUE = "#7fd1b5", "#efce8b", "#ef6b6b", "#6fb1ef"
FELT_A, FELT_B = "#1b5a50", "#0f3a36"
KIND = {"raise": "#e9b04c", "call": "#57b894", "fold": "#31424d"}
SUIT_GLYPH = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
TWO_COLOR = {"s": "#17232a", "c": "#17232a", "h": "#d21f2b", "d": "#d21f2b"}
FOUR_COLOR = {"s": "#17232a", "h": "#d21f2b", "d": "#1f6fd2", "c": "#1d8a4a"}

STYLE = f"""
QMainWindow, QDialog, QWidget#root {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}
QLabel#brand {{ font-size: 19px; font-weight: 700; letter-spacing: 2px; }}
QLabel#tag {{ color: {MINT}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#faint {{ color: {FAINT}; font-size: 11px; }}
QLabel#action {{ color: {GOLD}; font-size: 26px; font-weight: 700; }}
QLabel#stat {{ font-size: 19px; font-weight: 600; }}
QLabel#verdict {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 8px; padding: 7px 12px; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 12px; }}
QPushButton {{ background: #1c2d38; border: 1px solid #334a58; border-radius: 8px; padding: 9px 14px; font-weight: 600; }}
QPushButton:hover {{ background: #263d4b; }}
QPushButton:disabled {{ color: #566b76; background: #131f27; border-color: #223039; }}
QPushButton#fold {{ border-color: #6b3a3f; }} QPushButton#fold:hover {{ background: #4a2a2f; }}
QPushButton#call {{ border-color: #2f6d5a; }} QPushButton#call:hover {{ background: #214a3e; }}
QPushButton#raise {{ border-color: #8a6a2c; }} QPushButton#raise:hover {{ background: #5a4520; }}
QPushButton#primary {{ background: {MINT}; color: #0c231c; border-color: {MINT}; }}
QPushButton#primary:hover {{ background: #a2e3cc; }}
QPushButton#primary:disabled {{ background: #17272b; color: #5d7a78; border-color: #27393d; }}
QPushButton#chip {{ padding: 5px 10px; border-radius: 12px; font-size: 12px; }}
QPushButton#seg {{ border-radius: 0; padding: 7px 14px; border-right: 0; }}
QPushButton#seg:checked {{ background: #24463f; color: #c8f0e0; border-color: #3b7566; }}
QPushButton#x {{ padding: 0 6px; border: 0; background: transparent; color: {FAINT}; }}
QPushButton#x:hover {{ color: {RED}; }}
QComboBox, QSpinBox, QPlainTextEdit {{ background: #0d1820; border: 1px solid #2c404d; border-radius: 7px; padding: 6px 8px; }}
QComboBox QAbstractItemView {{ background: #0f1b23; selection-background-color: #24463f; border: 1px solid #2c404d; }}
QSlider::groove:horizontal {{ height: 4px; background: #24343f; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {GOLD}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; border-radius: 8px; background: {GOLD}; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: #2f4552; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: #1c2f3a; color: white; padding: 5px; border: 1px solid #47636f; }}
"""


def ui_font(size, bold=False):
    f = QFont(QApplication.font())
    f.setPixelSize(max(1, int(size)))
    f.setBold(bold)
    return f


def suit_font(size):
    f = QFont("DejaVu Sans")
    f.setPixelSize(max(1, int(size)))
    return f


def draw_card(p, rect, card, colors, dim=False):
    """A face-up card, or a back when `card` is None."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if dim:
        p.setOpacity(.45)
    r = min(rect.width(), rect.height()) * .1
    if card is None:
        p.setPen(QPen(QColor("#3b6a72"), 1.2))
        p.setBrush(QColor("#1d3f49"))
        p.drawRoundedRect(rect, r, r)
        inner = rect.adjusted(rect.width() * .14, rect.height() * .1, -rect.width() * .14, -rect.height() * .1)
        p.setPen(QPen(QColor("#2f5a63"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(inner, r * .6, r * .6)
    else:
        p.setPen(QPen(QColor("#c9d1d0"), 1))
        p.setBrush(QColor("#fbfbf8"))
        p.drawRoundedRect(rect, r, r)
        color = QColor(colors[card[1]])
        p.setPen(color)
        p.setFont(ui_font(rect.height() * .40, True))
        p.drawText(QRectF(rect.x(), rect.y() + rect.height() * .02, rect.width(), rect.height() * .5),
                   Qt.AlignmentFlag.AlignCenter, "10" if card[0] == "T" else card[0])
        p.setFont(suit_font(rect.height() * .42))
        p.drawText(QRectF(rect.x(), rect.y() + rect.height() * .46, rect.width(), rect.height() * .5),
                   Qt.AlignmentFlag.AlignCenter, SUIT_GLYPH[card[1]])
    p.restore()


class TableView(QWidget):
    """The felt. Logical canvas 1000 x 600, scaled to fit."""
    SEATS6 = [(500, 548), (118, 420), (118, 176), (500, 62), (882, 176), (882, 420)]
    SEATS2 = [(500, 548), (500, 62)]
    # Per seat: centre of the opponent's cards, chip position, action-pill top-left.
    CARDS6 = [None, (246, 404), (246, 200), (446, 128), (754, 200), (754, 404)]
    BETS6 = [(628, 462), (262, 352), (262, 250), (540, 128), (700, 250), (700, 352)]
    PILLS6 = [(300, 538), (66, 454), (66, 124), (600, 52), (830, 124), (830, 454)]

    def __init__(self):
        super().__init__()
        self.setMinimumSize(560, 340)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.view = None
        self.colors = TWO_COLOR
        self.reveal = True

    def set_view(self, view):
        self.view = view
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        scale = min(self.width() / 1000, self.height() / 600)
        p.translate((self.width() - 1000 * scale) / 2, (self.height() - 600 * scale) / 2)
        p.scale(scale, scale)
        self.paint_felt(p)
        if self.view:
            self.paint_hand(p, self.view)

    def paint_felt(self, p):
        rail = QRectF(96, 84, 808, 420)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#17252d"))
        p.drawRoundedRect(rail, 205, 205)
        felt = rail.adjusted(16, 16, -16, -16)
        g = QRadialGradient(felt.center(), 420)
        g.setColorAt(0, QColor(FELT_A))
        g.setColorAt(1, QColor(FELT_B))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor("#2a6b60"), 1.5))
        p.drawRoundedRect(felt, 190, 190)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(felt.adjusted(18, 18, -18, -18), 172, 172)

    def paint_hand(self, p, v):
        n = v["players"]
        spots = self.SEATS6 if n == 6 else self.SEATS2
        pick = (lambda table, k: table[k]) if n == 6 else (lambda table, k: table[0 if k == 0 else 3])
        bb = v["bb"]
        units = lambda chips: f"{chips / bb:.1f}".rstrip("0").rstrip(".")
        # Pot and board
        p.setPen(QColor(255, 255, 255, 120))
        p.setFont(ui_font(11, True))
        street = STREETS[v["street"]].upper() if not v["done"] else "HAND COMPLETE"
        p.drawText(QRectF(300, 158, 400, 16), Qt.AlignmentFlag.AlignCenter, f"{street}  ·  POT")
        p.setPen(QColor(GOLD))
        p.setFont(ui_font(30, True))
        p.drawText(QRectF(300, 174, 400, 40), Qt.AlignmentFlag.AlignCenter, f"{units(v['pot'])} bb")
        for j in range(5):
            rect = QRectF(336 + j * 67, 226, 60, 84)
            if j < len(v["board"]):
                draw_card(p, rect, v["board"][j], self.colors)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 26), 1, Qt.PenStyle.DashLine))
                p.setBrush(QColor(0, 0, 0, 22))
                p.drawRoundedRect(rect, 6, 6)
        # Seats
        for offset, (x, y) in enumerate(spots):
            seat = v["order"][offset]
            mine, live = seat == v["hero"], v["active"][seat]
            toward = QPointF(*(pick(self.CARDS6, offset) or (x, y)))
            plate = QRectF(x - 88, y - 28, 176, 56)
            turn = mine and v["pending"]
            p.setOpacity(1 if live or v["done"] else .5)
            p.setPen(QPen(QColor(GOLD if turn else "#35505c"), 2.2 if turn else 1.2))
            p.setBrush(QColor("#1f3642" if mine else "#132129"))
            p.drawRoundedRect(plate, 14, 14)
            badge = QRectF(plate.x() + 10, plate.y() + 9, 44, 18)
            button = v["positions"][seat].startswith("BTN")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(GOLD if button else "#2b4450"))
            p.drawRoundedRect(badge, 9, 9)
            p.setPen(QColor("#1b1a12" if button else "#b9cdd4"))
            p.setFont(ui_font(10, True))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, v["positions"][seat].replace("BTN/SB", "BTN"))
            p.setPen(QColor(TEXT if mine else "#b7c9d0"))
            p.setFont(ui_font(12, True))
            p.drawText(QRectF(badge.right() + 8, plate.y() + 8, 66, 20),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "YOU" if mine else v["names"][seat])
            if not mine:
                p.setPen(QColor(MINT if self.reveal else FAINT))
                p.setFont(ui_font(10, True))
                p.drawText(QRectF(plate.right() - 46, plate.y() + 8, 38, 20),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                           v["strategies"][seat] if self.reveal else "???")
            p.setPen(QColor("#ffffff"))
            p.setFont(ui_font(17, True))
            p.drawText(QRectF(plate.x() + 12, plate.y() + 28, 110, 24),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"{units(v['stacks'][seat])} bb")
            if v["done"] and v["deltas"][seat]:
                d = v["deltas"][seat]
                p.setPen(QColor(MINT if d > 0 else RED))
                p.setFont(ui_font(13, True))
                p.drawText(QRectF(plate.right() - 82, plate.y() + 28, 72, 24),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{d:+.1f}")
            p.setOpacity(1)
            # Cards
            if mine:
                for k, card in enumerate(v["hole"]):
                    draw_card(p, QRectF(x - 74 + k * 76, y - 132, 72, 100), card, self.colors, dim=not live)
            elif seat in v["shown"]:
                for k, card in enumerate(v["shown"][seat]):
                    draw_card(p, QRectF(toward.x() - 45 + k * 46, toward.y() - 30, 42, 59), card, self.colors)
            elif live and not v["done"]:
                for k in range(2):
                    draw_card(p, QRectF(toward.x() - 30 + k * 22, toward.y() - 24, 30, 42), None, self.colors)
            # Chips committed this street
            if v["bets"][seat]:
                pos = QPointF(*pick(self.BETS6, offset))
                p.setPen(QPen(QColor("#6b5320"), 1))
                p.setBrush(QColor(GOLD))
                p.drawEllipse(pos, 7, 7)
                p.setPen(QColor("#f4e3b8"))
                p.setFont(ui_font(13, True))
                p.drawText(QRectF(pos.x() + 12, pos.y() - 10, 90, 20),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, units(v["bets"][seat]))
            # Last action on this street
            last = v["last_action"].get(seat)
            if last and (last["street"] == v["street"] or last["kind"] == "fold") and not v["done"]:
                pill = QRectF(*pick(self.PILLS6, offset), 104, 20)
                p.setPen(Qt.PenStyle.NoPen)
                c = QColor(KIND[last["kind"]])
                c.setAlpha(60 if last["kind"] == "fold" else 215)
                p.setBrush(c)
                p.drawRoundedRect(pill, 10, 10)
                p.setPen(QColor("#10181c" if last["kind"] != "fold" else MUTED))
                p.setFont(ui_font(11, True))
                p.drawText(pill, Qt.AlignmentFlag.AlignCenter, last["text"])


class RangeGrid(QWidget):
    """13 x 13 starting-hand matrix; each cell is split raise / call / fold."""
    ROW = 19

    def __init__(self):
        super().__init__()
        self.matrix = None
        self.hero = None
        self.stale = False
        self.empty = ""
        self.setMouseTracking(True)
        self.setFixedHeight(13 * self.ROW)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_matrix(self, matrix, hero=None, stale=False, empty="Ranges appear on your first\npreflop decision."):
        self.matrix, self.hero, self.stale, self.empty = matrix, hero, stale, empty
        self.update()

    def cell(self):
        return self.width() / 13

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        size, high, x0 = self.cell(), self.ROW, 0
        if not self.matrix:
            p.setPen(QColor(FAINT))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty)
            return
        if self.stale:
            p.setOpacity(.55)
        p.setFont(ui_font(10, True))
        for i, row in enumerate(self.matrix["cells"]):
            for j, c in enumerate(row):
                r = QRectF(x0 + j * size + .5, i * high + .5, size - 1, high - 1)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#17242c"))
                p.drawRect(r)
                w = r.width() * c["raise"]
                if w:
                    p.setBrush(QColor(KIND["raise"]))
                    p.drawRect(QRectF(r.x(), r.y(), w, r.height()))
                w2 = r.width() * c["call"]
                if w2:
                    p.setBrush(QColor(KIND["call"]))
                    p.drawRect(QRectF(r.x() + w, r.y(), w2, r.height()))
                played = c["raise"] + c["call"] > .5
                p.setPen(QColor("#10181c" if played else "#6d8590"))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, c["hand"])
                if c["hand"] == self.hero:
                    p.setPen(QPen(QColor("#ffffff"), 2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(r.adjusted(.5, .5, -.5, -.5))

    def mouseMoveEvent(self, event):
        if not self.matrix:
            return
        j = int(event.position().x() // self.cell())
        i = int(event.position().y() // self.ROW)
        if 0 <= i < 13 and 0 <= j < 13:
            c = self.matrix["cells"][i][j]
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"{c['hand']}   raise {c['raise']:.0%} · call {c['call']:.0%} · fold {c['fold']:.0%}", self)


class EquityGauge(QWidget):
    """Equity bar with a marker at the equity the price requires."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(40)
        self.equity = self.need = None

    def set_values(self, equity, need):
        self.equity, self.need = equity, need
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        bar = QRectF(0, 18, self.width(), 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#1d2c36"))
        p.drawRoundedRect(bar, 4, 4)
        p.setFont(ui_font(11))
        if self.equity is None:
            return
        good = self.equity >= (self.need or 0)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0, QColor("#3f8f79" if good else "#8a4a4a"))
        g.setColorAt(1, QColor(MINT if good else RED))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(0, 18, self.width() * self.equity, 8), 4, 4)
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(0, 0, self.width(), 16), Qt.AlignmentFlag.AlignLeft, f"Equity {self.equity:.0%}")
        if self.need:
            x = self.width() * self.need
            p.setPen(QPen(QColor(GOLD), 2))
            p.drawLine(QPointF(x, 13), QPointF(x, 31))
            p.setPen(QColor(GOLD))
            p.drawText(QRectF(0, 0, self.width(), 16), Qt.AlignmentFlag.AlignRight, f"needs {self.need:.0%}")


class MixBar(QWidget):
    """A policy's action mix when it reports one."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(10)
        self.parts = []

    def set_parts(self, parts):
        self.parts = parts
        self.setVisible(bool(parts))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 5, 5)
        p.setClipPath(path)
        x = 0.
        for kind, share in self.parts:
            w = self.width() * share
            p.fillRect(QRectF(x, 0, w, self.height()), QColor(KIND[kind] if kind != "fold" else "#3b4d58"))
            x += w


class Sparkline(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(40)
        self.series = [0.]

    def set_series(self, series):
        self.series = series
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        lo, hi = min(self.series), max(self.series)
        span = max(1., hi - lo)
        y = lambda v: 4 + (h - 8) * (1 - (v - lo) / span)
        p.setPen(QPen(QColor("#2a3b46"), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(0, y(0)), QPointF(w, y(0)))
        if len(self.series) < 2:
            return
        step = w / (len(self.series) - 1)
        path = QPainterPath(QPointF(0, y(self.series[0])))
        for k, v in enumerate(self.series[1:], 1):
            path.lineTo(k * step, y(v))
        p.setPen(QPen(QColor(MINT if self.series[-1] >= 0 else RED), 2))
        p.drawPath(path)


def label(text="", name=None, wrap=True):
    w = QLabel(text)
    w.setWordWrap(wrap)
    if name:
        w.setObjectName(name)
    return w


def card(*widgets, spacing=8):
    frame = QFrame()
    frame.setObjectName("card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(16, 10, 16, 10)
    box.setSpacing(spacing)
    for w in widgets:
        box.addLayout(w) if not isinstance(w, QWidget) else box.addWidget(w)
    return frame


class OpponentsDialog(QDialog):
    """Choose who sits at the table: a policy per seat, or a random one."""

    def __init__(self, parent, spec, reveal, carry):
        super().__init__(parent)
        self.setWindowTitle("Opponents")
        self.setMinimumWidth(520)
        box = QVBoxLayout(self)
        box.setSpacing(10)
        box.addWidget(label("WHO SITS AT THE TABLE", "tag", wrap=False))
        note = label("Pick a policy for each seat, or Random to draw one when the table opens.\n"
                     "Heads-up uses seat 2 only.", "muted")
        note.setMinimumHeight(38)
        box.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(label("Preset", "muted", wrap=False))
        self.preset = QComboBox()
        self.preset.addItem("Custom", None)
        for name in PRESETS:
            self.preset.addItem(name, name)
        self.preset.activated.connect(self.apply_preset)
        row.addWidget(self.preset, 1)
        box.addLayout(row)
        order = sorted(STRATEGIES, key=lambda k: ("STR".index(k[0]), k))
        self.seats = []
        for k in range(5):
            combo = QComboBox()
            combo.setMaxVisibleItems(22)
            combo.addItem("Random — drawn when the table opens", RANDOM)
            for sid in order:
                combo.addItem(strategy_title(sid), sid)
            combo.activated.connect(lambda *_: self.preset.setCurrentIndex(0))
            line = QHBoxLayout()
            line.addWidget(label(f"Seat {k + 2}", "muted", wrap=False))
            line.addWidget(combo, 1)
            box.addLayout(line)
            self.seats.append(combo)
        self.set_spec(spec)
        self.reveal = QCheckBox("Show each opponent's policy on the table")
        self.reveal.setChecked(reveal)
        self.carry = QCheckBox("Stacks carry over between hands (a busted player rebuys)")
        self.carry.setChecked(carry)
        box.addWidget(self.reveal)
        box.addWidget(self.carry)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start new table")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def set_spec(self, spec):
        for combo, sid in zip(self.seats, spec):
            combo.setCurrentIndex(combo.findData(sid))

    def apply_preset(self, *_):
        name = self.preset.currentData()
        if name:
            self.set_spec(PRESETS[name])

    def spec(self):
        return [combo.currentData() for combo in self.seats]


class LabWindow(QMainWindow):
    MODES = (("coach", "Coach"), ("quiz", "Quiz"), ("watch", "Watch"))

    def __init__(self, seed=None):
        super().__init__()
        self.setWindowTitle("PokerLab — Agent Lab")
        self.resize(1480, 940)
        self.seed = seed
        self.coach = Coach(seed)
        self.opponents = list(DEFAULT_LINEUP)      # five entries; heads-up uses the first
        self.carry = True
        self.table = LabTable(seed)
        self.mode = "coach"
        self.advice = None
        self.pinned = ["S55", "T04", "S18", "R03"]
        self.last_matrix = None
        self.timer = QTimer(self)
        self.timer.setInterval(260)
        self.timer.timeout.connect(self.watch_step)
        for sid in self.pinned:          # load policy assets before the first decision is timed
            self.coach.agent(sid)
        self.build()
        self.shortcuts()
        self.refresh()

    # ----- construction ---------------------------------------------------
    def build(self):
        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 14, 20, 12)
        outer.setSpacing(12)
        outer.addLayout(self.top_bar())
        body = QHBoxLayout()
        body.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(10)
        self.felt = TableView()
        left.addWidget(self.felt, 1)
        self.verdict = label("", "verdict")
        self.verdict.setVisible(False)
        left.addWidget(self.verdict)
        left.addLayout(self.action_bar())
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(96)
        left.addWidget(self.log)
        body.addLayout(left, 1)
        body.addWidget(self.side_panel())
        outer.addLayout(body, 1)
        self.status = label("", "faint", wrap=False)
        outer.addWidget(self.status)
        self.setCentralWidget(root)

    def top_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(10)
        brand = label("POKERLAB", "brand", wrap=False)
        bar.addWidget(brand)
        bar.addWidget(label("AGENT LAB", "tag", wrap=False))
        bar.addSpacing(14)
        self.segments = QButtonGroup(self)
        for k, (key, title) in enumerate(self.MODES):
            b = QPushButton(title)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(key == self.mode)
            b.setToolTip({"coach": "See the policy's move before you act",
                          "quiz": "Act first; the policy's move is revealed afterwards",
                          "watch": "The policy plays your seat"}[key])
            b.clicked.connect(lambda _, key=key: self.set_mode(key))
            self.segments.addButton(b, k)
            bar.addWidget(b)
            if k:
                bar.setSpacing(0)
        bar.setSpacing(10)
        bar.addStretch()
        self.players = QComboBox()
        self.players.addItem("6-max", 6)
        self.players.addItem("Heads-up", 2)
        self.depth = QComboBox()
        for d in DEPTHS:
            self.depth.addItem(f"{d} bb deep", d)
        self.depth.setCurrentIndex(self.depth.findData(100))
        self.players.currentIndexChanged.connect(self.new_table)
        self.depth.currentIndexChanged.connect(self.new_table)
        self.strategy = QComboBox()
        self.strategy.setMinimumWidth(300)
        self.strategy.setMaxVisibleItems(24)
        order = sorted(STRATEGIES, key=lambda k: ("STR".index(k[0]), k))
        for sid in ["S55"] + [s for s in order if s != "S55"]:
            self.strategy.addItem(strategy_title(sid), sid)
            self.strategy.setItemData(self.strategy.count() - 1, STRATEGIES[sid].source, Qt.ItemDataRole.ToolTipRole)
        self.strategy.currentIndexChanged.connect(self.strategy_changed)
        self.four = QCheckBox("4-colour deck")
        self.four.toggled.connect(self.deck_changed)
        self.rivals = QPushButton("Opponents…")
        self.rivals.setToolTip("Choose each opponent's policy, or seat random ones")
        self.rivals.clicked.connect(self.choose_opponents)
        for w in (self.four, self.rivals, self.players, self.depth, label("My policy", "muted", wrap=False), self.strategy):
            bar.addWidget(w)
        return bar

    def action_bar(self):
        col = QVBoxLayout()
        col.setSpacing(8)
        sizes = QHBoxLayout()
        sizes.setSpacing(6)
        self.size_row = sizes
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.amount = QSpinBox()
        self.amount.setMaximum(10 ** 9)
        self.amount.setFixedWidth(104)
        self.amount.setSuffix(" chips")
        self.slider.valueChanged.connect(self.amount.setValue)
        self.amount.valueChanged.connect(self.slider.setValue)
        self.amount.valueChanged.connect(self.update_raise_text)
        self.preset_box = QHBoxLayout()
        self.preset_box.setSpacing(6)
        sizes.addLayout(self.preset_box)
        sizes.addWidget(self.slider, 1)
        sizes.addWidget(self.amount)
        col.addLayout(sizes)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.fold = QPushButton("Fold   F")
        self.fold.setObjectName("fold")
        self.call = QPushButton("Check   C")
        self.call.setObjectName("call")
        self.raise_ = QPushButton("Raise   R")
        self.raise_.setObjectName("raise")
        self.follow = QPushButton("Play coach move   ↵")
        self.follow.setObjectName("primary")
        self.deal = QPushButton("Next hand   Space")
        self.fold.clicked.connect(lambda: self.play("fold"))
        self.call.clicked.connect(lambda: self.play("call"))
        self.raise_.clicked.connect(lambda: self.play("raise", self.amount.value()))
        self.follow.clicked.connect(self.play_coach)
        self.deal.clicked.connect(self.next_hand)
        for b in (self.fold, self.call, self.raise_, self.follow, self.deal):
            b.setMinimumHeight(40)
            row.addWidget(b, 1)
        col.addLayout(row)
        return col

    def side_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(404)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel = QWidget()
        panel.setObjectName("root")
        box = QVBoxLayout(panel)
        box.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinAndMaxSize)
        box.setContentsMargins(0, 0, 8, 0)
        box.setSpacing(10)
        # Coach
        self.coach_tag = label("COACH", "tag", wrap=False)
        self.action = label("—", "action")
        self.mix = MixBar()
        self.gauge = EquityGauge()
        self.why = label("", "muted")
        self.timing = label("", "faint")
        self.why.setFixedHeight(104)
        self.why.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        box.addWidget(card(self.coach_tag, self.action, self.mix, self.gauge, self.why, self.timing))
        # Compare
        head = QHBoxLayout()
        head.addWidget(label("SAME SPOT, OTHER POLICIES", "tag", wrap=False))
        head.addStretch()
        pin = QPushButton("Pin current")
        pin.setObjectName("chip")
        pin.setToolTip("Add the selected policy to this comparison")
        pin.clicked.connect(self.pin_current)
        head.addWidget(pin)
        self.compare_box = QVBoxLayout()
        self.compare_box.setSpacing(4)
        box.addWidget(card(head, self.compare_box))
        # Range
        self.range_tag = label("PREFLOP RANGE", "tag", wrap=False)
        self.range_note = label("", "faint", wrap=False)
        self.grid = RangeGrid()
        box.addWidget(card(self.range_tag, self.grid, self.range_note))
        # Session
        stats = QGridLayout()
        stats.setHorizontalSpacing(18)
        self.stat = {}
        for k, (key, title) in enumerate((("hands", "Hands"), ("net", "Net"), ("rate", "bb / 100"), ("agree", "With coach"))):
            self.stat[key] = label("0", "stat", wrap=False)
            stats.addWidget(self.stat[key], 0, k)
            stats.addWidget(label(title, "faint", wrap=False), 1, k)
        self.spark = Sparkline()
        head2 = QHBoxLayout()
        head2.addWidget(label("SESSION", "tag", wrap=False))
        head2.addStretch()
        reset = QPushButton("Reset")
        reset.setObjectName("chip")
        reset.clicked.connect(self.new_table)
        head2.addWidget(reset)
        box.addWidget(card(head2, stats, self.spark))
        box.addStretch()
        for k in range(box.count()):
            if box.itemAt(k).widget():
                box.itemAt(k).widget().setFixedWidth(384)
        scroll.setWidget(panel)
        return scroll

    def shortcuts(self):
        for key, slot in (("F", lambda: self.fold.click()), ("C", lambda: self.call.click()),
                          ("R", lambda: self.raise_.click()), ("Space", lambda: self.deal.click()),
                          ("Return", lambda: self.follow.click()), ("Enter", lambda: self.follow.click()),
                          ("A", self.all_in), ("Q", lambda: self.set_mode("quiz" if self.mode != "quiz" else "coach")),
                          ("W", lambda: self.set_mode("watch" if self.mode != "watch" else "coach"))):
            QShortcut(QKeySequence(key), self, activated=slot)
        for k in range(1, 6):
            QShortcut(QKeySequence(str(k)), self, activated=lambda k=k: self.preset(k - 1))

    # ----- state changes --------------------------------------------------
    def sid(self):
        return self.strategy.currentData()

    def set_mode(self, mode):
        self.mode = mode
        for k, (key, _) in enumerate(self.MODES):
            self.segments.button(k).setChecked(key == mode)
        self.timer.start() if mode == "watch" else self.timer.stop()
        self.verdict.setVisible(False)
        self.refresh()

    def choose_opponents(self):
        dialog = OpponentsDialog(self, self.opponents, self.felt.reveal, self.carry)
        if dialog.exec():
            self.set_opponents(dialog.spec(), dialog.reveal.isChecked(), dialog.carry.isChecked())

    def set_opponents(self, spec, reveal=None, carry=None):
        """Seat new opponents (policy ids or RANDOM, five entries) and start a fresh table."""
        self.opponents = list(spec)
        if reveal is not None:
            self.felt.reveal = reveal
        if carry is not None:
            self.carry = carry
        self.new_table()

    def new_table(self, *_):
        n = self.players.currentData()
        self.table = LabTable(self.seed, n, self.depth.currentData(), self.opponents[:n - 1], self.carry)
        self.coach.agreed = self.coach.sized = self.coach.graded = 0
        self.last_matrix = None
        self.verdict.setVisible(False)
        self.refresh()

    def strategy_changed(self, *_):
        self.last_matrix = None
        self.refresh()

    def deck_changed(self, on):
        self.felt.colors = FOUR_COLOR if on else TWO_COLOR
        self.felt.update()

    def pin_current(self):
        sid = self.sid()
        if sid not in self.pinned:
            self.pinned = (self.pinned + [sid])[-5:]
            self.refresh()

    def unpin(self, sid):
        self.pinned = [s for s in self.pinned if s != sid]
        self.refresh()

    def next_hand(self):
        if self.table.state.status:
            return
        self.table.new_hand()
        self.refresh()

    def all_in(self):
        o = self.view["observation"]
        if o and o["max_raise_to"] is not None:
            self.amount.setValue(o["max_raise_to"])

    def preset(self, index):
        if index < len(self.presets) and self.view["pending"]:
            self.amount.setValue(self.presets[index][1])

    def play(self, action, amount=0):
        view = self.view
        if not view["pending"]:
            return
        o = view["observation"]
        if action == "fold" and not o["to_call"]:
            return
        if action == "raise" and o["min_raise_to"] is None:
            return
        advice = self.advice
        try:
            self.table.act(action, amount)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        if advice and self.mode != "watch":
            verdict = self.coach.record(action, amount, advice)
            did = ("Raise to " + self.table.in_bb(amount)) if action == "raise" else \
                  (("Call " + self.table.in_bb(o["to_call"])) if o["to_call"] else "Check") if action == "call" else "Fold"
            mark = {"match": f"<span style='color:{MINT}'>✓ Same as {advice['strategy']}</span>",
                    "size": f"<span style='color:{GOLD}'>≈ Same action, different size</span>",
                    "differs": f"<span style='color:{RED}'>≠ Different from {advice['strategy']}</span>"}[verdict]
            self.verdict.setText(f"{mark} &nbsp;·&nbsp; You: <b>{did}</b> &nbsp;·&nbsp; {advice['strategy']}: <b>{advice['title']}</b>"
                                 f" &nbsp;·&nbsp; <span style='color:{MUTED}'>{advice['reasons'][0]}</span>")
            self.verdict.setVisible(True)
        self.refresh()

    def play_coach(self):
        if self.advice and self.view["pending"]:
            self.play(self.advice["action"], self.advice["raise_to"] or 0)

    def watch_step(self):
        if self.mode != "watch":
            return
        if self.view["pending"]:
            self.play(self.advice["action"], self.advice["raise_to"] or 0)
        elif self.view["done"]:
            self.table.new_hand()
            self.refresh()

    # ----- rendering ------------------------------------------------------
    def refresh(self):
        self.view = view = self.table.view()
        self.felt.set_view(view)
        o = view["observation"]
        pending = view["pending"]
        self.advice = None
        if pending:
            started = time.perf_counter()
            self.advice = self.coach.advise(o, self.sid())
            matrix = self.coach.matrix(o, self.sid())
            if matrix:
                self.last_matrix = (matrix, self.advice["facts"]["hand"])
            rows = self.coach.compare(o, self.pinned)
            self.elapsed = (time.perf_counter() - started) * 1000
        else:
            rows = [{"id": s, "kind": None, "title": "—"} for s in self.pinned]
        self.render_coach(view)
        self.render_compare(rows)
        self.render_range(o)
        self.render_actions(view)
        self.render_log(view)
        self.render_session()
        if view["done"]:
            net = view["net_bb"]
            self.status.setText(f"Hand {view['hand_no']} finished · {net:+.1f} bb · Space deals the next hand")
        else:
            self.status.setText("F fold · C check/call · R raise · 1–5 sizes · A all-in · ↵ coach move · Space next hand · Q quiz · W watch"
                                "      Practice chips. Equity is against random hands, not an EV estimate.")

    def render_coach(self, view):
        sid = self.sid()
        self.coach_tag.setText(f"COACH · {sid}")
        hidden = self.mode == "quiz" and view["pending"]
        if not self.advice:
            self.action.setText("Hand complete" if view["done"] else "—")
            self.why.setText(f"Result {view['net_bb']:+.1f} bb." if view["done"] else "")
            self.gauge.set_values(None, None)
            self.mix.set_parts([])
            self.timing.setText("")
            return
        a = self.advice
        if hidden:
            self.action.setText("Your move first")
            self.why.setText("Quiz mode: act, then compare with the policy. Facts about the spot stay visible.")
            self.mix.set_parts([])
        else:
            self.action.setText(a["title"])
            self.why.setText("\n".join("•  " + r for r in a["reasons"]))
            parts = {}
            for d in a.get("policy_details", {}).get("distribution", []):
                kind = "call" if d["action"] in ("call", "check") else d["action"]
                parts[kind] = parts.get(kind, 0) + d["probability"]
            self.mix.set_parts([(k, parts[k]) for k in ("raise", "call", "fold") if parts.get(k)])
        self.gauge.set_values(a["facts"]["equity"], a["facts"]["required_equity"])
        path = a.get("policy_details", {}).get("policy_path", "heuristic").replace("_", " ")
        self.timing.setText(f"{path[:34]} · computed in {self.elapsed:.1f} ms")

    def render_compare(self, rows):
        while self.compare_box.count():
            item = self.compare_box.takeAt(0)
            if item.layout():
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w:
                        w.setParent(None)
                        w.deleteLater()
        hidden = self.mode == "quiz" and self.view["pending"]
        for r in rows:
            line = QHBoxLayout()
            line.setSpacing(8)
            name = label(f"<b>{r['id']}</b> &nbsp;<span style='color:{MUTED}'>{STRATEGIES[r['id']].label.split(' / ')[0][:30]}</span>", wrap=False)
            name.setToolTip(strategy_title(r["id"]))
            name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            pill = label("?" if hidden else r["title"], wrap=False)
            color = KIND.get(r["kind"], "#22323c") if not hidden else "#22323c"
            dark = r["kind"] in ("raise", "call") and not hidden
            pill.setStyleSheet(f"background:{color}; color:{'#10181c' if dark else MUTED}; border-radius:9px; padding:2px 9px; font-weight:600; font-size:12px;")
            x = QPushButton("×")
            x.setObjectName("x")
            x.setFixedWidth(20)
            x.clicked.connect(lambda _, sid=r["id"]: self.unpin(sid))
            line.addWidget(name, 1)
            line.addWidget(pill)
            line.addWidget(x)
            self.compare_box.addLayout(line)

    def render_range(self, o):
        sid = self.sid()
        if not self.last_matrix:
            self.grid.set_matrix(None)
            self.range_tag.setText("PREFLOP RANGE")
            self.range_note.setText("")
            return
        m, hand = self.last_matrix
        live = bool(o and not o["board"])
        if live and self.mode == "quiz":
            self.grid.set_matrix(None, empty="Hidden in quiz mode\nuntil you act.")
            self.range_tag.setText("PREFLOP RANGE")
            self.range_note.setText("")
            return
        self.grid.set_matrix(m, hand, stale=not live)
        self.range_tag.setText(f"PREFLOP RANGE · {sid} · {m['position']}" + ("" if live else " · THIS HAND"))
        self.range_note.setText(f"<span style='color:{KIND['raise']}'>■</span> raise {m['raise']:.0%} &nbsp; "
                                f"<span style='color:{KIND['call']}'>■</span> call {m['call']:.0%} &nbsp; fold {m['fold']:.0%}"
                                f" &nbsp;·&nbsp; facing {m['facing']}")

    def render_actions(self, view):
        o = view["observation"]
        pending = view["pending"] and self.mode != "watch"
        while self.preset_box.count():
            w = self.preset_box.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.presets = bet_presets(o) if o else []
        can_raise = bool(o and o["min_raise_to"] is not None)
        if can_raise:
            lo, hi = o["min_raise_to"], o["max_raise_to"]
            for w in (self.slider, self.amount):
                w.blockSignals(True)
                w.setRange(lo, hi)
                w.blockSignals(False)
            start = self.advice["raise_to"] if self.advice and self.advice["raise_to"] and self.mode != "quiz" else self.presets[0][1]
            self.amount.setValue(start)
            self.slider.setValue(start)
            for k, (text, value) in enumerate(self.presets):
                b = QPushButton(text)
                b.setObjectName("chip")
                b.setToolTip(f"Key {k + 1} · raise to {self.table.in_bb(value)}")
                b.clicked.connect(lambda _, v=value: self.amount.setValue(v))
                b.setEnabled(pending)
                self.preset_box.addWidget(b)
        for w in (self.slider, self.amount, self.raise_):
            w.setEnabled(pending and can_raise)
        self.fold.setEnabled(bool(pending and o["to_call"]))
        self.call.setEnabled(pending)
        self.call.setText(f"Call {self.table.in_bb(o['to_call'])}   C" if o and o["to_call"] else "Check   C")
        self.follow.setEnabled(pending and self.mode == "coach")
        self.deal.setEnabled(view["done"] and self.mode != "watch")
        self.update_raise_text()

    def update_raise_text(self, *_):
        o = self.view["observation"] if hasattr(self, "view") else None
        if o and o["min_raise_to"] is not None:
            verb = "Bet" if not o["to_call"] and o["board"] else "Raise to"
            self.raise_.setText(f"{verb} {self.table.in_bb(self.amount.value())}   R")
        else:
            self.raise_.setText("Raise   R")

    def render_log(self, view):
        lines, street = [f"· {note}" for note in view["notes"]], None
        for h in view["history"]:
            if h["street"] != street:
                street = h["street"]
                board = " ".join(view["board"][:(0, 3, 4, 5)[street]])
                lines.append(f"— {STREETS[street]}{'  ' + board if board else ''} —")
            lines.append(f"   {h['who']:<6} {h['text']}")
        if view["done"]:
            shown = "   ".join(f"{view['names'][s]} shows {' '.join(c)}" for s, c in view["shown"].items())
            lines.append(f"— Result {view['net_bb']:+.1f} bb{'   ·   ' + shown if shown else ''} —")
        self.log.setPlainText("\n".join(lines) or "Waiting for the first action")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def render_session(self):
        s = self.table.session()
        self.stat["hands"].setText(str(s["hands"]))
        self.stat["net"].setText(f"{s['net_bb']:+.1f}")
        self.stat["net"].setStyleSheet(f"color:{MINT if s['net_bb'] >= 0 else RED}")
        self.stat["rate"].setText(f"{s['bb_per_100']:+.0f}" if s["hands"] else "—")
        agree = self.coach.agreement()
        self.stat["agree"].setText("—" if agree is None else f"{agree:.0%}")
        self.spark.set_series(s["series"])

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()


def prepare(app):
    path = Path(__file__).with_name("assets") / "DejaVuSans.ttf"
    families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(path)))
    if sys.platform != "darwin" and families:
        app.setFont(QFont(families[0]))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)


def main(screenshot=None, seed=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PokerLab Agent Lab")
    app.setOrganizationName("PokerLab")
    prepare(app)
    window = LabWindow(seed)
    window.show()
    if screenshot:
        app.processEvents()
        window.grab().save(screenshot)
        return
    sys.exit(app.exec())
