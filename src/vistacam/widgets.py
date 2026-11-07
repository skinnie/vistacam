"""Custom widgets: toggle, segmented control, slider rows, meters, viewer."""
from .qt import (Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF,
                            QSize, Qt, Signal)
from .qt import QColor, QImage, QPainter, QPainterPath, QPen
from .qt import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from .style import T, c, ui_font


def label(text, name=None, parent=None):
    lab = QLabel(text, parent)
    if name:
        lab.setObjectName(name)
    return lab


class Toggle(QAbstractButton):
    """Pill switch with an animated knob."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(36, 22)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on):
        block = self.blockSignals(True)
        super().setChecked(on)
        self.blockSignals(block)
        self._pos = 1.0 if on else 0.0
        self.update()

    def _get_knob(self):
        return self._pos

    def _set_knob(self, v):
        self._pos = v
        self.update()

    # not "pos": that would shadow QWidget.pos and animate the widget's position
    knob = Property(float, _get_knob, _set_knob)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 2, 34, 18)
        on = self._pos
        track = c("text") if on > .5 else c("surface3")
        if not self.isEnabled():
            track.setAlphaF(.4)
        p.setPen(QPen(c("accent") if self.hasFocus() else c("line_strong"), 1))
        p.setBrush(track)
        p.drawRoundedRect(r, 9, 9)
        knob = c("bg") if on > .5 else c("muted")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(knob)
        x = r.left() + 2 + on * 16
        p.drawEllipse(QRectF(x, r.top() + 2, 14, 14))


class Segmented(QFrame):
    """Exclusive pill buttons. Emits the chosen value."""

    changed = Signal(int)

    def __init__(self, items, big=False, accent_value=None, parent=None):
        super().__init__(parent)
        self.setObjectName("seg")
        self.setProperty("big", big)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for value, text in items:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            if value == accent_value:
                b.setObjectName("accentChoice")
            self.group.addButton(b, value)
            lay.addWidget(b, 1)
            self.buttons[value] = b
        self.group.idClicked.connect(self.changed)

    def set_value(self, v):
        b = self.buttons.get(v)
        if b:
            b.setChecked(True)


class FlatSlider(QSlider):
    """Thin track + round knob, painted directly (QSS sliders render unevenly)."""

    KNOB = 14

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFixedHeight(22)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def _x(self, value):
        span = self.maximum() - self.minimum() or 1
        usable = self.width() - self.KNOB
        return self.KNOB / 2 + usable * (value - self.minimum()) / span

    def mousePressEvent(self, e):
        self._jump(e.position().x())
        self.setSliderDown(True)

    def mouseMoveEvent(self, e):
        if self.isSliderDown():
            self._jump(e.position().x())

    def mouseReleaseEvent(self, e):
        self.setSliderDown(False)

    def _jump(self, x):
        span = self.maximum() - self.minimum()
        usable = max(1, self.width() - self.KNOB)
        frac = max(0.0, min(1.0, (x - self.KNOB / 2) / usable))
        self.setValue(self.minimum() + round(frac * span))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self.height() / 2
        x = self._x(self.value())
        on = self.isEnabled()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c("surface3"))
        p.drawRoundedRect(QRectF(0, cy - 2, self.width(), 4), 2, 2)
        fill = c("text") if on else c("faint")
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(0, cy - 2, x, 4), 2, 2)
        n = self.maximum() - self.minimum()
        if 0 < n <= 16:
            p.setBrush(c("line_strong"))
            for i in range(n + 1):
                tx = self._x(self.minimum() + i)
                p.drawRect(QRectF(tx - .5, cy + 6, 1, 3))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(c("accent"), 2))
            p.drawEllipse(QPointF(x, cy), self.KNOB / 2 + 2, self.KNOB / 2 + 2)
        p.setPen(QPen(c("surface"), 2))
        p.setBrush(fill)
        p.drawEllipse(QPointF(x, cy), self.KNOB / 2, self.KNOB / 2)


class SliderRow(QWidget):
    """Label + value + reset, with a slider underneath."""

    changed = Signal(int)

    def __init__(self, title, ctl, parent=None):
        super().__init__(parent)
        self.default = ctl.default
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(4)
        self.title = label(title)
        head.addWidget(self.title)
        head.addStretch(1)
        self.reset = QPushButton("Reset")
        self.reset.setObjectName("reset")
        self.reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset.setToolTip(f"Back to {ctl.default}")
        self.reset.clicked.connect(lambda: self._user(self.default))
        head.addWidget(self.reset)
        self.value = label("", "value")
        self.value.setMinimumWidth(26)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.value)
        v.addLayout(head)
        self.slider = FlatSlider()
        self.slider.setRange(ctl.min, ctl.max)
        self.slider.setSingleStep(max(ctl.step, 1))
        self.slider.setPageStep(max((ctl.max - ctl.min) // 8, 1))
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.valueChanged.connect(self._moved)
        v.addWidget(self.slider)
        self.set_value(ctl.default)

    def _moved(self, val):
        self._show(val)
        self.changed.emit(val)

    def _user(self, val):
        self.slider.setValue(val)

    def _show(self, val):
        self.value.setText(str(val))
        self.reset.setVisible(val != self.default)

    def set_value(self, val):
        if self.slider.isSliderDown():
            return
        block = self.slider.blockSignals(True)
        self.slider.setValue(val)
        self.slider.blockSignals(block)
        self._show(val)

    def set_active(self, on):
        self.slider.setEnabled(on)
        self.title.setEnabled(on)
        self.value.setEnabled(on)
        self.reset.setEnabled(on)


class SwitchRow(QWidget):
    toggled = Signal(bool)

    def __init__(self, title, hint="", parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = label(title)
        col.addWidget(self.title)
        if hint:
            col.addWidget(label(hint, "hint"))
        h.addLayout(col, 1)
        self.toggle = Toggle()
        self.toggle.toggled.connect(self.toggled)
        h.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, e):
        if self.toggle.isEnabled():
            self.toggle.click()

    def set_value(self, on):
        self.toggle.setChecked(bool(on))

    def set_active(self, on):
        self.toggle.setEnabled(on)
        self.title.setEnabled(on)


class Section(QWidget):
    def __init__(self, title, tag=None, parent=None):
        super().__init__(parent)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(18, 14, 18, 16)
        self.v.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(label(title.upper(), "sectionTitle"))
        head.addStretch(1)
        if tag:
            head.addWidget(label(tag, "tag"))
        self.v.addLayout(head)

    def add(self, w):
        self.v.addWidget(w)
        return w


class Tile(QFrame):
    def __init__(self, title, note="", parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(16, 13, 16, 14)
        self.v.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(label(title.upper(), "tileTitle"))
        head.addStretch(1)
        self.note = label(note, "tileNote")
        head.addWidget(self.note)
        self.v.addLayout(head)


class Histogram(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hist = None
        self.setMinimumHeight(92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_hist(self, h):
        self.hist = h
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(c("line"), 1))
        for i in (1, 2, 3):
            x = w * i / 4
            p.drawLine(QPointF(x, 0), QPointF(x, h))
        if not self.hist:
            return
        peak = max(max(ch) for ch in self.hist) or 1
        mode = (QPainter.CompositionMode.CompositionMode_Screen if T["dark"]
                else QPainter.CompositionMode.CompositionMode_Multiply)
        p.setCompositionMode(mode)
        cols = [QColor(255, 90, 90, 170), QColor(80, 220, 130, 170), QColor(90, 160, 255, 170)]
        n = len(self.hist[0])
        for ch, col in zip(self.hist, cols):
            path = QPainterPath(QPointF(0, h))
            for i, val in enumerate(ch):
                y = h - min(1.0, (val / peak) ** .5) * (h - 2)
                path.lineTo(w * i / n, y)
                path.lineTo(w * (i + 1) / n, y)
            path.lineTo(w, h)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawPath(path)


class Track(QWidget):
    """Thin meter. mode 'cast': dot around a centre line; 'fill': bar."""

    def __init__(self, mode="cast", color="text", parent=None):
        super().__init__(parent)
        self.mode, self.color, self.v = mode, color, None
        self.setFixedHeight(14)

    def set(self, v):
        self.v = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        r = QRectF(0, 4, w, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c("surface3"))
        p.drawRoundedRect(r, 3, 3)
        if self.v is None:
            return
        if self.mode == "cast":
            p.setPen(QPen(c("line_strong"), 1))
            p.drawLine(QPointF(w / 2, 0), QPointF(w / 2, 14))
            pos = max(0.0, min(1.0, .5 + (self.v - 1) * 1.25))
            x = 6 + pos * (w - 12)
            p.setPen(QPen(c("surface"), 2))
            p.setBrush(c(self.color))
            p.drawEllipse(QPointF(x, 7), 6, 6)
        else:
            frac = max(0.0, min(1.0, self.v / 20))
            p.setBrush(c("red") if self.v > 5 else c("text"))
            p.drawRoundedRect(QRectF(0, 4, max(6, w * frac), 6), 3, 3)


class Meter(QWidget):
    def __init__(self, title, mode="cast", color="text", parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        head = QHBoxLayout()
        t = label(title, "value")
        head.addWidget(t)
        head.addStretch(1)
        self.num = label("–")
        f = self.num.font()
        f.setWeight(f.Weight.DemiBold)
        self.num.setFont(f)
        head.addWidget(self.num)
        v.addLayout(head)
        self.track = Track(mode, color)
        v.addWidget(self.track)

    def set(self, value, text):
        self.num.setText(text)
        self.track.set(value)


def _pill(p, rect_right_or_left, y, text, solid=False, align_right=False, dot=True):
    f = ui_font(9.0, ui_font().Weight.DemiBold if solid else ui_font().Weight.Normal)
    p.setFont(f)
    fm = p.fontMetrics()
    show_dot = dot and not solid
    dot = 13 if show_dot else 0
    w = fm.horizontalAdvance(text) + 20 + dot
    x = rect_right_or_left - w if align_right else rect_right_or_left
    r = QRectF(x, y, w, 26)
    p.setPen(Qt.PenStyle.NoPen)
    if solid:
        p.setBrush(c("accent"))
    else:
        p.setBrush(QColor(10, 10, 11, 170))
    p.drawRoundedRect(r, 8, 8)
    if show_dot:
        p.setBrush(c("live"))
        p.drawEllipse(QPointF(x + 13, y + 13), 3.5, 3.5)
    p.setPen(c("accent_ink") if solid else QColor("#f2f2f3"))
    p.drawText(QRectF(x + 10 + dot, y, w - 20 - dot, 26), Qt.AlignmentFlag.AlignVCenter, text)


class Viewer(QWidget):
    """Live picture with overlay badges; keeps 4:3."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.img = None
        self.info = ""
        self.tuning = None  # None = no tuning control (stock driver)
        self.empty = "Looking for the camera…"
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, img: QImage):
        self.img = img
        self.update()

    def area(self):
        w, h = self.width(), self.height()
        if w * 3 > h * 4:
            vw, vh = h * 4 / 3, h
        else:
            vw, vh = w, w * 3 / 4
        return QRectF((w - vw) / 2, (h - vh) / 2, vw, vh)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.area()
        clip = QPainterPath()
        clip.addRoundedRect(r, 14, 14)
        p.setClipPath(clip)
        p.fillRect(r, QColor("#000"))
        if self.img is not None and not self.img.isNull():
            p.drawImage(r, self.img)
        else:
            p.setPen(QColor("#8d8d93"))
            p.setFont(ui_font(10))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.empty)
        p.setClipping(False)
        p.setPen(QPen(c("line"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 14, 14)
        if self.img is not None and self.info:
            _pill(p, r.left() + 12, r.top() + 12, self.info)
        if self.tuning is not None and self.img is not None:
            _pill(p, r.right() - 12, r.top() + 12, "Creative" if self.tuning else "Stock Linux",
                  solid=bool(self.tuning), align_right=True)


class CompareView(QWidget):
    """Before/after with a draggable divider. Left = a, right = b."""

    def __init__(self, a: QImage, b: QImage, la="Stock Linux", lb="Creative", parent=None):
        super().__init__(parent)
        self.a, self.b, self.la, self.lb = a, b, la, lb
        self.x = .5
        self.setMinimumSize(560, 420)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def area(self):
        w, h = self.width(), self.height()
        vw, vh = (h * 4 / 3, h) if w * 3 > h * 4 else (w, w * 3 / 4)
        return QRectF((w - vw) / 2, (h - vh) / 2, vw, vh)

    def _drag(self, e):
        r = self.area()
        self.x = max(0.0, min(1.0, (e.position().x() - r.left()) / r.width()))
        self.update()

    mousePressEvent = _drag
    mouseMoveEvent = _drag

    def keyPressEvent(self, e):
        step = {Qt.Key.Key_Left: -.05, Qt.Key.Key_Right: .05}.get(e.key())
        if step:
            self.x = max(0.0, min(1.0, self.x + step))
            self.update()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.area()
        clip = QPainterPath()
        clip.addRoundedRect(r, 12, 12)
        p.setClipPath(clip)
        p.drawImage(r, self.b)
        split = r.left() + r.width() * self.x
        p.setClipRect(QRectF(r.left(), r.top(), split - r.left(), r.height()),
                      Qt.ClipOperation.IntersectClip)
        p.drawImage(r, self.a)
        p.setClipping(False)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(QPointF(split, r.top()), QPointF(split, r.bottom()))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(split, r.center().y()), 17, 17)
        p.setPen(QPen(QColor("#111111"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        cy = r.center().y()
        for d in (-1, 1):
            p.drawPolyline([QPointF(split + d * 4, cy - 5), QPointF(split + d * 9, cy),
                            QPointF(split + d * 4, cy + 5)])
        _pill(p, r.left() + 12, r.bottom() - 38, self.la, dot=False)
        _pill(p, r.right() - 12, r.bottom() - 38, self.lb, solid=True, align_right=True)
