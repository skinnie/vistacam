"""Off-screen UI sweep: click every control, hold B, change formats, and
check that no widget jumps or disappears. Uses a fake camera, so it runs
without hardware.  QT_QPA_PLATFORM=offscreen python tests/ui_sweep.py [shots_dir]
"""
import os
import sys
import tempfile

os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vistacam.qt import QPoint, Qt  # noqa: E402
from vistacam.qt import module  # noqa: E402

QTest = module("QtTest").QTest
from vistacam.qt import QApplication, QPushButton  # noqa: E402

from vistacam import v4l2, window, widgets  # noqa: E402
from vistacam.v4l2 import Control  # noqa: E402

C = Control
FAKE = [
    C(v4l2.CID_BRIGHTNESS, 1, "Brightness", 0, 255, 1, 127, 0),
    C(v4l2.CID_CONTRAST, 1, "Contrast", 0, 255, 1, 127, 0),
    C(v4l2.CID_SATURATION, 1, "Saturation", 0, 6, 1, 3, 0),
    C(v4l2.CID_GAMMA, 1, "Gamma", 0, 4, 1, 2, 0),
    C(v4l2.CID_EXPOSURE, 1, "Exposure", 0, 15, 1, 9, 0),
    C(v4l2.CID_GAIN, 1, "Gain", 0, 7, 1, 0, 0),
    C(v4l2.CID_HFLIP, 2, "Horizontal Flip", 0, 1, 1, 0, 0),
    C(v4l2.CID_VFLIP, 2, "Vertical Flip", 0, 1, 1, 0, 0),
    C(v4l2.CID_POWER_LINE, 3, "Power Line Frequency", 0, 3, 1, 3, 0,
      [(0, "Disabled"), (1, "50 Hz"), (2, "60 Hz"), (3, "Auto")]),
    C(v4l2.CID_SHARPNESS, 1, "Sharpness", 0, 9, 1, 4, 0),
    C(v4l2.CID_BACKLIGHT, 1, "Backlight Compensation", 0, 1, 1, 0, 0),
    C(v4l2.CID_CREATIVE_TUNING, 2, "Creative Tuning", 0, 1, 1, 1, 0),
    C(v4l2.CID_SHARPNESS_AUTO, 2, "Sharpness, Auto", 0, 1, 1, 1, 0),
    C(v4l2.CID_SENSOR_REG, 1, "Sensor Register", 0, 255, 1, 0, 0),
    C(v4l2.CID_SENSOR_VAL, 1, "Sensor Value", 0, 255, 1, 0, 0),
    C(v4l2.CID_SENSOR_WRITE, 4, "Write Sensor Register", 0, 0, 0, 0, 0),
    C(v4l2.CID_SENSOR_READ, 4, "Read Sensor Register", 0, 0, 0, 0, 0),
    C(v4l2.CID_EXPOSURE_AUTO, 3, "Auto Exposure", 0, 1, 1, 0, 0, [(0, "Auto Mode"), (1, "Manual Mode")]),
    C(v4l2.CID_WB_PRESET, 3, "White Balance, Auto & Preset", 1, 6, 1, 1, 0,
      [(1, "Auto"), (2, "Incandescent"), (3, "Fluorescent"), (6, "Daylight")]),
]


class FakeCam(window.Camera.__base__):
    from vistacam.qt import Signal
    from vistacam.qt import QImage
    image = Signal(QImage, bytes)
    lost = Signal(str)
    status = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.vals = {c.id: c.default for c in FAKE}
        self.latest, self.count, self.starts = None, 0, []

    def start(self, w=None, h=None, fps=None):
        self.starts.append((w, h, fps))

    def stop(self):
        pass

    def close(self):
        pass

    def controls(self):
        return [Control(**{**c.__dict__}) for c in FAKE]

    def get(self, cid):
        return self.vals[cid]

    def set(self, cid, v):
        self.vals[cid] = v

    def measured_fps(self):
        return 30.0


window.Camera = FakeCam
window.v4l2.find_device = lambda: "/dev/videoX"
window.v4l2.driver_info = lambda: (True, True)

app = QApplication([])
w = window.MainWindow()
w.resize(1440, 920)
w.show()
QTest.qWait(300)
shots = sys.argv[1] if len(sys.argv) > 1 else None
problems = []


def geometry():
    return {id(x): (type(x).__name__, x.mapTo(w, QPoint(0, 0)), x.size())
            for x in w.rail_scroll.widget().findChildren(widgets.QWidget) if x.isVisible()}


def check(step):
    QTest.qWait(350)
    now = geometry()
    moved = [f"{n} {p0}->{p1}" for k, (n, p0, s0) in base.items()
             if k in now and (now[k][1] != p0 or now[k][2] != s0)]
    if moved:
        problems.append(f"{step}: {len(moved)} widgets moved, e.g. {moved[:3]}")
    if shots:
        w.grab().save(os.path.join(shots, f"{len(steps):02d}-{step}.png"))
    steps.append(step)


steps = []
base = geometry()
for cid, row in list(w.rows.items()):
    if isinstance(row, widgets.SwitchRow):
        for _ in range(2):
            QTest.mouseClick(row.toggle, Qt.MouseButton.LeftButton)
            check(f"switch-{cid:x}")
    elif isinstance(row, widgets.Segmented):
        for b in list(row.buttons.values()) + [list(row.buttons.values())[0]]:
            QTest.mouseClick(b, Qt.MouseButton.LeftButton)
        check(f"seg-{cid:x}")
    elif isinstance(row, widgets.SliderRow):
        s = row.slider
        if s.isEnabled():
            QTest.mousePress(s, Qt.MouseButton.LeftButton, pos=QPoint(s.width() - 3, 11))
            QTest.mouseMove(s, QPoint(s.width() // 3, 11))
            QTest.mouseRelease(s, Qt.MouseButton.LeftButton, pos=QPoint(s.width() // 3, 11))
            check(f"slider-{cid:x}")
            QTest.mouseClick(row.reset, Qt.MouseButton.LeftButton)
            check(f"reset-{cid:x}")

# tuning segment, hold B, format switches
for v in (0, 1):
    QTest.mouseClick(w.tuning.buttons[v], Qt.MouseButton.LeftButton)
    check(f"tuning-{v}")
QTest.keyPress(w, Qt.Key.Key_B)
held = w.cam.vals[v4l2.CID_CREATIVE_TUNING]
QTest.keyRelease(w, Qt.Key.Key_B)
after = w.cam.vals[v4l2.CID_CREATIVE_TUNING]
if (held, after) != (0, 1):
    problems.append(f"hold B: tuning while held={held}, after={after} (want 0, 1)")
QTest.mousePress(w.hold, Qt.MouseButton.LeftButton)
held = w.cam.vals[v4l2.CID_CREATIVE_TUNING]
QTest.mouseRelease(w.hold, Qt.MouseButton.LeftButton)
if (held, w.cam.vals[v4l2.CID_CREATIVE_TUNING]) != (0, 1):
    problems.append("hold button did not switch and restore")
check("hold")
for b in w.size_seg.buttons.values():
    QTest.mouseClick(b, Qt.MouseButton.LeftButton)
for b in w.fps_seg.buttons.values():
    QTest.mouseClick(b, Qt.MouseButton.LeftButton)
check("formats")
print("starts:", w.cam.starts)
print(f"{len(steps)} steps")
print("\n".join(problems) if problems else "no layout jumps, hold works")
