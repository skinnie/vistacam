"""Render the main window off-screen to PNG (for docs and layout checks).

  QT_QPA_PLATFORM=offscreen python tools/screenshot.py out.png [--light] [--frame f.jpg] [--ab stock.jpg]

With --frame, the live picture is replaced by a JPEG so it works while
another app holds the camera. Controls still come from the real driver.
"""
import os
import sys
import tempfile

# never touch the user's real settings
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="vistacam-shot-")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vistacam.qt import QTimer  # noqa: E402
from vistacam.qt import QImage  # noqa: E402
from vistacam.qt import QApplication  # noqa: E402

from vistacam import camera, style, window  # noqa: E402

args = sys.argv[1:]
out = args[0]
frame = args[args.index("--frame") + 1] if "--frame" in args else None

if frame:
    camera.Camera.start = lambda self, *a, **k: None
    jpeg = open(frame, "rb").read()

app = QApplication([])
app.setFont(style.ui_font(10))
w = window.MainWindow()
w.resize(1440, 920)
if "--light" in args:
    w.dark = True
    w.toggle_theme()
w.show()


def feed():
    if frame and w.cam:
        w.cam._on_frame(jpeg)
        w.cam.times[:] = [0.0, 1.0 / 30 * 29, 1.0]
        w.cam.measured_fps = lambda: 29.8


def shoot():
    feed()
    w.update_stats()
    app.processEvents()
    if "--ab" in args and frame:
        other = open(args[args.index("--ab") + 1], "rb").read()
        sa = camera.stats(QImage.fromData(other, "JPG"))
        sb = camera.stats(QImage.fromData(jpeg, "JPG"))
        d = window.CompareDialog(w, other, jpeg, sa, sb, "~/Pictures/VistaCam/ab-creative.jpg")
        d.resize(1080, 620)
        d.show()
        app.processEvents()
        d.grab().save(out)
    else:
        w.grab().save(out)
    app.quit()


QTimer.singleShot(300, feed)
QTimer.singleShot(1200, shoot)
app.exec()
