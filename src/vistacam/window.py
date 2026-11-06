"""Main window and A/B compare dialog."""
import os
import threading
import time

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QImage
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import __version__, style, v4l2
from .camera import Camera, stats
from .widgets import (CompareView, Histogram, Meter, Section, Segmented, SliderRow, SwitchRow,
                      Tile, Viewer, label)

SNAPDIR = os.path.join(os.path.expanduser("~"), "Pictures", "VistaCam")
CREATIVE_ONLY = {v4l2.CID_SATURATION, v4l2.CID_GAMMA, v4l2.CID_SHARPNESS, v4l2.CID_SHARPNESS_AUTO,
                 v4l2.CID_WB_PRESET, v4l2.CID_EXPOSURE_AUTO, v4l2.CID_EXPOSURE, v4l2.CID_GAIN,
                 v4l2.CID_BACKLIGHT}
AB_SETTLE_FRAMES = 45  # switching tuning resets exposure; give auto-exposure ~1.5 s


def sep():
    f = QFrame()
    f.setObjectName("sep")
    return f


class CompareDialog(QDialog):
    def __init__(self, parent, a_jpeg, b_jpeg, sa, sb, path):
        super().__init__(parent)
        self.setWindowTitle("Stock Linux vs Creative tuning")
        self.resize(1080, 620)
        a, b = QImage.fromData(a_jpeg, "JPG"), QImage.fromData(b_jpeg, "JPG")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(14)
        head = QVBoxLayout()
        head.setSpacing(2)
        t = label("Stock Linux vs Creative tuning", "title")
        head.addWidget(t)
        head.addWidget(label("Two frames, each taken after auto-exposure settled. "
                             "Drag across the picture to compare.", "subtitle"))
        root.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(20)
        self.view = CompareView(a, b)
        body.addWidget(self.view, 1)
        side = QVBoxLayout()
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        for col, text in ((1, "Stock"), (2, "Creative")):
            h = label(text, "cmpHead")
            h.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(h, 0, col)
        rows = [("Red / Green", "rg", "{:.2f}", lambda v: -abs(v - 1)),
                ("Blue / Green", "bg", "{:.2f}", lambda v: -abs(v - 1)),
                ("Contrast", "contrast", "{:.0f}", lambda v: v),
                ("Mean level", "luma", "{:.0f}", None),
                ("Clipped white", "hi", "{:.1f}%", lambda v: -v),
                ("Crushed black", "lo", "{:.1f}%", lambda v: -v)]
        for r, (name, k, fmt, score) in enumerate(rows, 1):
            grid.addWidget(label(name), r, 0)
            win = None
            if score and abs(score(sa[k]) - score(sb[k])) > 1e-3:
                win = 1 if score(sa[k]) > score(sb[k]) else 2
            for col, s in ((1, sa), (2, sb)):
                v = label(fmt.format(s[k]), "cmpWin" if win == col else None)
                v.setAlignment(Qt.AlignmentFlag.AlignRight)
                grid.addWidget(v, r, col)
        side.addLayout(grid)
        note = label("Highlighted values are closer to the target: casts nearer 1.00, "
                     "more contrast, less clipping.", "hint")
        note.setWordWrap(True)
        side.addSpacing(6)
        side.addWidget(note)
        side.addStretch(1)
        p = label(path, "mono")
        p.setWordWrap(True)
        p.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side.addWidget(p)
        btn = QPushButton(style.icon("folder"), "  Open folder")
        btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))
        side.addWidget(btn)
        sidew = QWidget()
        sidew.setLayout(side)
        sidew.setFixedWidth(270)
        body.addWidget(sidew)
        root.addLayout(body, 1)


class MainWindow(QMainWindow):
    ab_done = Signal(object)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("vistacam", "vistacam")
        self.setWindowTitle("Vista IM")
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "icons", "vistacam.svg")))
        self.resize(1360, 900)
        self.cam = None
        self.ctls = {}
        self.rows = {}
        self.last_img = None
        self.held_from = None
        self.pending = {}
        self.size = self.settings.value("size", "640x480")
        self.fps = int(self.settings.value("fps", 30))

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        grid = QHBoxLayout(root)
        grid.setContentsMargins(24, 18, 24, 22)
        grid.setSpacing(22)

        # ---------------- left column
        left = QVBoxLayout()
        left.setSpacing(14)
        grid.addLayout(left, 1)

        head = QHBoxLayout()
        head.setSpacing(12)
        title = label("Vista IM", "title")
        title.setFont(style.ui_font(13, style.QFont.Weight.DemiBold))
        head.addWidget(title)
        head.addWidget(label("Creative Live! Cam VF0260", "subtitle"))
        head.addSpacing(6)
        self.dev_chip = label("No camera", "chip")
        head.addWidget(self.dev_chip)
        self.live_chip = label("Starting", "chip")
        head.addWidget(self.live_chip)
        head.addStretch(1)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("iconBtn")
        self.theme_btn.setToolTip("Light or dark")
        self.theme_btn.clicked.connect(self.toggle_theme)
        head.addWidget(self.theme_btn)
        left.addLayout(head)

        self.banner = label("", "banner")
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.banner.hide()
        left.addWidget(self.banner)

        self.viewer = Viewer()
        left.addWidget(self.viewer, 1)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.tuning = Segmented([(0, "Stock Linux"), (1, "Creative")], big=True, accent_value=1)
        self.tuning.changed.connect(lambda v: self.set_ctl(v4l2.CID_CREATIVE_TUNING, v, now=True))
        bar.addWidget(self.tuning)
        self.hold = QPushButton(style.icon("eye"), "  Hold for stock   B")
        self.hold.setToolTip("Hold to see stock Linux tuning, release to go back (or hold B)")
        self.hold.pressed.connect(self.hold_start)
        self.hold.released.connect(self.hold_end)
        bar.addWidget(self.hold)
        bar.addStretch(1)
        self.snap_btn = QPushButton(style.icon("camera"), "  Snapshot")
        self.snap_btn.clicked.connect(self.snapshot)
        bar.addWidget(self.snap_btn)
        self.ab_btn = QPushButton("  Compare A/B")
        self.ab_btn.setObjectName("primary")
        self.ab_btn.clicked.connect(self.compare)
        bar.addWidget(self.ab_btn)
        left.addLayout(bar)

        bento = QHBoxLayout()
        bento.setSpacing(12)
        self.hist_tile = Tile("Histogram")
        self.hist = Histogram()
        self.hist_tile.v.addWidget(self.hist, 1)
        bento.addWidget(self.hist_tile, 16)
        cast = Tile("Colour cast", "1.00 is neutral")
        self.rg = Meter("Red / Green", "cast", "red")
        self.bg = Meter("Blue / Green", "cast", "blue")
        cast.v.addWidget(self.rg)
        cast.v.addWidget(self.bg)
        self.cast_note = label("", "value")
        cast.v.addWidget(self.cast_note)
        bento.addWidget(cast, 10)
        expo = Tile("Exposure")
        self.contrast_num = label("–", "bigNum")
        expo.v.addWidget(self.contrast_num)
        self.hi = Meter("Clipped white", "fill")
        self.lo = Meter("Crushed black", "fill")
        expo.v.addWidget(self.hi)
        expo.v.addWidget(self.lo)
        bento.addWidget(expo, 10)
        bw = QWidget()
        bw.setLayout(bento)
        bw.setFixedHeight(170)
        left.addWidget(bw)

        # ---------------- right rail
        self.rail_scroll = QScrollArea()
        self.rail_scroll.setWidgetResizable(True)
        self.rail_scroll.setFixedWidth(372)
        self.rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        grid.addWidget(self.rail_scroll)

        # ---------------- timers, keys
        self.stats_timer = QTimer(self, interval=400, timeout=self.update_stats)
        self.stats_timer.start()
        self.scan_timer = QTimer(self, interval=2000, timeout=self.scan)
        self.scan_timer.start()
        self.ab_done.connect(self._ab_show)

        self.dark = self.settings.value("dark", True, type=bool)
        self.apply_theme()
        QTimer.singleShot(0, self.scan)
        self.viewer.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.viewer.setFocus()

    # ------------------------------------------------------------ device
    def scan(self):
        if self.cam:
            return
        path = v4l2.find_device()
        loaded, patched = v4l2.driver_info()
        if not path:
            self.viewer.empty = "Plug in the Creative Live! Cam Vista IM (USB 041e:4052)"
            self.viewer.img = None
            self.viewer.update()
            self.dev_chip.setText("No camera")
            self.live_chip.setText("Waiting")
            return
        try:
            self.cam = Camera(path)
        except OSError as e:
            self.viewer.empty = f"Can't open {path}: {e.strerror}"
            self.viewer.update()
            return
        self.dev_chip.setText(f"{path}  ·  {v4l2.USB_ID}")
        if not patched:
            self.banner.setText("The patched driver isn't loaded, so Creative tuning and the extra "
                                "controls are unavailable. Install it with: sudo ./install.sh")
            self.banner.show()
        else:
            self.banner.hide()
        self.cam.image.connect(self.on_image)
        self.cam.lost.connect(self.on_lost)
        self.reload_controls(rebuild=True)
        w, h = map(int, self.size.split("x"))
        self.cam.start(w, h, self.fps)

    def on_lost(self, why):
        self.cam.close()
        self.cam = None
        self.viewer.img = None
        if "busy" in why.lower():
            self.viewer.empty = "Another app is using the camera. Close it and VistaCam reconnects."
        else:
            self.viewer.empty = f"Camera lost: {why}"
        self.viewer.update()
        self.live_chip.setText("Disconnected")

    def on_image(self, img, _jpeg):
        self.last_img = img
        self.viewer.set_image(img)

    # ---------------------------------------------------------- controls
    def reload_controls(self, rebuild=False):
        if not self.cam:
            return
        try:
            ctls = self.cam.controls()
        except OSError:
            return
        self.ctls = {c.id: c for c in ctls}
        for c in ctls:
            if c.type != v4l2.T_BUTTON:
                try:
                    c.value = self.cam.get(c.id)
                except OSError:
                    c.value = c.default
        if rebuild:
            self.build_rail()
        self.sync()

    def set_ctl(self, cid, value, now=False):
        if not self.cam or cid not in self.ctls:
            return
        self.ctls[cid].value = value
        timer = self.pending.pop(cid, None)
        if timer:
            timer.stop()

        def send():
            try:
                self.cam.set(cid, value)
            except OSError as e:
                self.toast(f"Could not set {self.ctls[cid].name}: {e.strerror}")
            self.reload_controls()

        if now:
            send()
        else:
            t = QTimer(self, singleShot=True, interval=60, timeout=send)
            self.pending[cid] = t
            t.start()
        self.sync()

    def build_rail(self):
        rail = QFrame()
        rail.setObjectName("rail")
        v = QVBoxLayout(rail)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(0)
        self.rows = {}
        has = self.ctls.__contains__
        tag = "Creative" if has(v4l2.CID_CREATIVE_TUNING) else None

        def slider(sec, cid, title):
            if has(cid):
                row = sec.add(SliderRow(title, self.ctls[cid]))
                row.changed.connect(lambda val, cid=cid: self.set_ctl(cid, val))
                self.rows[cid] = row

        def switch(sec, cid, title, hint=""):
            if has(cid):
                row = sec.add(SwitchRow(title, hint))
                row.toggled.connect(lambda on, cid=cid: self.set_ctl(cid, int(on), now=True))
                self.rows[cid] = row

        def seg(sec, cid, title, names):
            if has(cid):
                items = [(val, names.get(l, l)) for val, l in self.ctls[cid].menu]
                sec.add(label(title))
                row = sec.add(Segmented(items))
                row.changed.connect(lambda val, cid=cid: self.set_ctl(cid, val, now=True))
                self.rows[cid] = row

        sec = Section("Image")
        slider(sec, v4l2.CID_BRIGHTNESS, "Brightness")
        slider(sec, v4l2.CID_CONTRAST, "Contrast")
        slider(sec, v4l2.CID_SATURATION, "Saturation")
        slider(sec, v4l2.CID_GAMMA, "Gamma")
        switch(sec, v4l2.CID_SHARPNESS_AUTO, "Auto sharpness")
        slider(sec, v4l2.CID_SHARPNESS, "Sharpness")
        v.addWidget(sec)

        if has(v4l2.CID_EXPOSURE_AUTO):
            v.addWidget(sep())
            sec = Section("Exposure", tag)
            seg(sec, v4l2.CID_EXPOSURE_AUTO, "Mode", {"Auto Mode": "Auto", "Manual Mode": "Manual"})
            slider(sec, v4l2.CID_EXPOSURE, "Exposure")
            slider(sec, v4l2.CID_GAIN, "Gain")
            switch(sec, v4l2.CID_BACKLIGHT, "Backlight compensation",
                   "Brighter subject against a bright window")
            v.addWidget(sec)
        if has(v4l2.CID_WB_PRESET):
            v.addWidget(sep())
            sec = Section("White balance", tag)
            seg(sec, v4l2.CID_WB_PRESET, "Preset",
                {"Incandescent": "Tungsten", "Fluorescent": "Fluor.", "Daylight": "Daylight"})
            v.addWidget(sec)

        v.addWidget(sep())
        sec = Section("Stream")
        sec.add(label("Resolution"))
        self.size_seg = sec.add(Segmented([(0, "640 × 480"), (1, "320 × 240")]))
        self.size_seg.changed.connect(self.on_size)
        if has(v4l2.CID_CREATIVE_TUNING):
            sec.add(label("Frame rate"))
            self.fps_seg = sec.add(Segmented([(30, "30 fps"), (20, "20 fps"), (15, "15 fps")]))
            self.fps_seg.changed.connect(self.on_fps)
        else:
            self.fps_seg = None
        seg(sec, v4l2.CID_POWER_LINE, "Mains flicker",
            {"Disabled": "Off", "50 Hz": "50 Hz", "60 Hz": "60 Hz", "Auto": "Auto"})
        v.addWidget(sec)

        v.addWidget(sep())
        sec = Section("Orientation")
        switch(sec, v4l2.CID_HFLIP, "Mirror")
        switch(sec, v4l2.CID_VFLIP, "Flip vertically")
        v.addWidget(sec)

        if has(v4l2.CID_SENSOR_REG):
            v.addWidget(sep())
            v.addWidget(self.register_section())

        v.addStretch(1)
        self.rail_scroll.setWidget(rail)

    def register_section(self):
        sec = Section("Sensor registers")
        hint = label("Direct OV7670 register access, in hex. Writes are lost when tuning "
                     "switches or the camera restarts.", "hint")
        hint.setWordWrap(True)
        sec.add(hint)
        g = QGridLayout()
        g.setSpacing(8)
        g.addWidget(label("Register", "hint"), 0, 0)
        g.addWidget(label("Value", "hint"), 0, 1)
        self.reg_addr = QLineEdit("13")
        self.reg_val = QLineEdit()
        g.addWidget(self.reg_addr, 1, 0)
        g.addWidget(self.reg_val, 1, 1)
        rd = QPushButton("Read")
        wr = QPushButton("Write")
        for b in (rd, wr):
            b.setObjectName("small")
        rd.clicked.connect(self.reg_read)
        wr.clicked.connect(self.reg_write)
        g.addWidget(rd, 2, 0)
        g.addWidget(wr, 2, 1)
        w = QWidget()
        w.setLayout(g)
        sec.add(w)
        return sec

    def _hex(self, edit):
        try:
            v = int(edit.text().strip(), 16)
        except ValueError:
            return None
        return v if 0 <= v <= 255 else None

    def reg_read(self):
        a = self._hex(self.reg_addr)
        if a is None:
            return self.toast("Register must be hex 00 to FF")
        try:
            self.cam.set(v4l2.CID_SENSOR_REG, a)
            self.cam.set(v4l2.CID_SENSOR_READ, 0)
            v = self.cam.get(v4l2.CID_SENSOR_VAL)
        except OSError as e:
            return self.toast(f"Read failed: {e.strerror}")
        self.reg_val.setText(f"{v:02x}")
        self.toast(f"0x{a:02x} = 0x{v:02x}")

    def reg_write(self):
        a, v = self._hex(self.reg_addr), self._hex(self.reg_val)
        if a is None or v is None:
            return self.toast("Register and value must be hex 00 to FF")
        try:
            self.cam.set(v4l2.CID_SENSOR_REG, a)
            self.cam.set(v4l2.CID_SENSOR_VAL, v)
            self.cam.set(v4l2.CID_SENSOR_WRITE, 0)
        except OSError as e:
            return self.toast(f"Write failed: {e.strerror}")
        self.toast(f"Wrote 0x{v:02x} to 0x{a:02x}")

    def sync(self):
        get = lambda cid: getattr(self.ctls.get(cid), "value", None)  # noqa: E731
        tuning = get(v4l2.CID_CREATIVE_TUNING)
        creative = tuning is None or tuning == 1
        auto_exp = get(v4l2.CID_EXPOSURE_AUTO) == 0
        auto_sharp = get(v4l2.CID_SHARPNESS_AUTO) == 1
        for cid, row in self.rows.items():
            val = get(cid)
            if val is not None:
                row.set_value(val)
            on = not (tuning is not None and not creative and cid in CREATIVE_ONLY)
            if cid in (v4l2.CID_EXPOSURE, v4l2.CID_GAIN) and auto_exp:
                on = False
            if cid == v4l2.CID_SHARPNESS and auto_sharp:
                on = False
            if hasattr(row, "set_active"):
                row.set_active(on)
            else:
                row.setEnabled(on)
        has_t = tuning is not None
        for w in (self.tuning, self.hold, self.ab_btn):
            w.setVisible(has_t)
        if has_t:
            self.tuning.set_value(1 if creative else 0)
        self.viewer.tuning = (1 if creative else 0) if has_t else None
        if hasattr(self, "size_seg"):
            self.size_seg.set_value(0 if self.size == "640x480" else 1)
        if getattr(self, "fps_seg", None):
            self.fps_seg.set_value(self.fps)
        self.viewer.update()

    def on_size(self, idx):
        self.size = "640x480" if idx == 0 else "320x240"
        self.settings.setValue("size", self.size)
        self.restart_stream()

    def on_fps(self, fps):
        self.fps = fps
        self.settings.setValue("fps", fps)
        self.restart_stream()

    def restart_stream(self):
        if self.cam:
            w, h = map(int, self.size.split("x"))
            self.cam.start(w, h, self.fps)
        self.sync()

    # ------------------------------------------------------------- stats
    def update_stats(self):
        if not self.cam or self.last_img is None:
            return
        fps = self.cam.measured_fps()
        self.live_chip.setText(f"<span style='color:{style.T['live']}'>●</span>&nbsp; {fps:.1f} fps")
        self.viewer.info = f"{self.last_img.width()}×{self.last_img.height()}  ·  {fps:.1f} fps"
        s = stats(self.last_img)
        self.hist.set_hist(s["hist"])
        self.hist_tile.note.setText(f"mean {s['luma']:.0f}")
        self.rg.set(s["rg"], f"{s['rg']:.2f}")
        self.bg.set(s["bg"], f"{s['bg']:.2f}")
        warm = s["rg"] - s["bg"]
        if abs(warm) < .06 and abs(s["rg"] - 1) < .08:
            self.cast_note.setText("Close to neutral")
        else:
            self.cast_note.setText("Leans warm" if warm > 0 else "Leans cool (blue)")
        self.contrast_num.setText(f"{s['contrast']:.0f} <span style='font-size:10pt; "
                                  f"color:{style.T['muted']}; font-weight:500'>contrast</span>")
        self.hi.set(s["hi"], f"{s['hi']:.1f}%")
        self.lo.set(s["lo"], f"{s['lo']:.1f}%")

    # ----------------------------------------------- tuning hold / A/B
    def hold_start(self):
        t = self.ctls.get(v4l2.CID_CREATIVE_TUNING)
        if not t or self.held_from is not None:
            return
        self.held_from = t.value
        self.hold.setProperty("held", True)
        self.hold.style().polish(self.hold)
        if t.value != 0:
            self.set_ctl(v4l2.CID_CREATIVE_TUNING, 0, now=True)

    def hold_end(self):
        if self.held_from is None:
            return
        back, self.held_from = self.held_from, None
        self.hold.setProperty("held", False)
        self.hold.style().polish(self.hold)
        if back != 0:
            self.set_ctl(v4l2.CID_CREATIVE_TUNING, back, now=True)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_B and not e.isAutoRepeat() and not isinstance(
                QApplication.focusWidget(), QLineEdit):
            self.hold_start()
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_B and not e.isAutoRepeat():
            self.hold_end()
        else:
            super().keyReleaseEvent(e)

    def snapshot(self):
        if not self.cam or not self.cam.latest:
            return
        os.makedirs(SNAPDIR, exist_ok=True)
        path = os.path.join(SNAPDIR, time.strftime("vistacam-%Y%m%d-%H%M%S.jpg"))
        open(path, "wb").write(self.cam.latest)
        self.toast(f"Saved {path}")

    def compare(self):
        if not self.cam:
            return
        self.ab_btn.setEnabled(False)
        self.ab_btn.setText("  Capturing…")
        cam = self.cam

        def work():
            try:
                before = cam.get(v4l2.CID_CREATIVE_TUNING)
                shots = {}
                for val in (0, 1):
                    cam.set(v4l2.CID_CREATIVE_TUNING, val)
                    shots[val] = cam.frame_after(AB_SETTLE_FRAMES)
                cam.set(v4l2.CID_CREATIVE_TUNING, before)
                self.ab_done.emit(shots)
            except OSError as e:
                self.ab_done.emit(e)

        threading.Thread(target=work, daemon=True).start()

    def _ab_show(self, result):
        self.ab_btn.setEnabled(True)
        self.ab_btn.setText("  Compare A/B")
        self.reload_controls()
        if isinstance(result, Exception) or not result.get(0) or not result.get(1):
            return self.toast("Compare failed: no frames")
        a, b = result[0], result[1]
        os.makedirs(SNAPDIR, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        pa = os.path.join(SNAPDIR, f"ab-{ts}-stock.jpg")
        pb = os.path.join(SNAPDIR, f"ab-{ts}-creative.jpg")
        open(pa, "wb").write(a)
        open(pb, "wb").write(b)
        sa = stats(QImage.fromData(a, "JPG"))
        sb = stats(QImage.fromData(b, "JPG"))
        CompareDialog(self, a, b, sa, sb, pb).exec()

    # ------------------------------------------------------------- misc
    def toast(self, msg):
        self.statusBar().showMessage(msg, 4000)

    def toggle_theme(self):
        self.dark = not self.dark
        self.settings.setValue("dark", self.dark)
        self.apply_theme()

    def apply_theme(self):
        style.apply_theme(QApplication.instance(), self.dark)
        self.theme_btn.setIcon(style.icon("sun" if self.dark else "moon", style.T["muted"]))
        self.hold.setIcon(style.icon("eye"))
        self.snap_btn.setIcon(style.icon("camera"))
        self.ab_btn.setIcon(style.icon("split", style.T["bg"]))
        self.statusBar().setStyleSheet(f"color: {style.T['muted']}; padding: 0 20px;")
        self.update_stats()
        for w in self.findChildren(QWidget):
            w.update()

    def closeEvent(self, e):
        if self.cam:
            self.cam.close()
        super().closeEvent(e)


def main(argv=None):
    import sys
    from PySide6.QtCore import QLoggingCategory
    # PySide6 ships its own Qt; plugin paths meant for another Qt install
    # (e.g. a system-wide QT_PLUGIN_PATH) load mismatched plugins and crash.
    for var in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        os.environ.pop(var, None)
    # the OV519 pads some frames; Qt decodes them fine but warns each time
    QLoggingCategory.setFilterRules("qt.gui.imageio.jpeg=false")
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("VistaCam")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("vistacam")
    app.setFont(style.ui_font(10))
    w = MainWindow()
    w.show()
    return app.exec()
