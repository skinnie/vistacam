"""Camera session: capture thread, control access, frame statistics."""
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage

from . import v4l2


class CaptureThread(QThread):
    frame = Signal(bytes)
    failed = Signal(str)

    def __init__(self, dev, width, height, fps):
        super().__init__()
        self.dev, self.size, self.fps = dev, (width, height), fps
        self._run = True

    def run(self):
        try:
            self.dev.start(self.size[0], self.size[1], self.fps)
            while self._run:
                f = self.dev.read(0.5)
                if f:
                    self.frame.emit(f)
        except OSError as e:
            self.failed.emit(e.strerror or str(e))
        finally:
            self.dev.stop()

    def stop(self):
        self._run = False
        self.wait(2000)


class Camera(QObject):
    """One open Vista IM. Emits decoded frames on the GUI thread."""

    image = Signal(QImage, bytes)
    status = Signal(str)
    lost = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.dev = v4l2.Device(path)
        self.card, self.driver = self.dev.card()
        self.thread = None
        self.width, self.height, self.fps = 640, 480, 30
        self.times = []
        self.latest = None
        self.count = 0
        self.lock = threading.Lock()

    # -- streaming
    def start(self, width=None, height=None, fps=None):
        self.stop()
        self.width = width or self.width
        self.height = height or self.height
        self.fps = fps or self.fps
        self.times.clear()
        self.thread = CaptureThread(self.dev, self.width, self.height, self.fps)
        self.thread.frame.connect(self._on_frame)
        self.thread.failed.connect(self.lost)
        self.thread.start()

    def stop(self):
        if self.thread:
            self.thread.stop()
            self.thread = None

    def close(self):
        self.stop()
        try:
            self.dev.close()
        except OSError:
            pass

    def _on_frame(self, jpeg):
        now = time.monotonic()
        self.times.append(now)
        while self.times and now - self.times[0] > 2.0:
            self.times.pop(0)
        with self.lock:
            self.latest = jpeg
            self.count += 1
        img = QImage.fromData(jpeg, "JPG")
        if not img.isNull():
            self.image.emit(img, jpeg)

    def measured_fps(self):
        t = self.times
        return (len(t) - 1) / (t[-1] - t[0]) if len(t) > 2 and t[-1] > t[0] else 0.0

    def frame_after(self, n, timeout=6.0):
        """Wait until n more frames arrived; return the latest JPEG."""
        with self.lock:
            target = self.count + n
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                if self.count >= target and self.latest:
                    return self.latest
            time.sleep(0.01)
        return None

    # -- controls
    def controls(self):
        return self.dev.controls()

    def get(self, cid):
        return self.dev.get(cid)

    def set(self, cid, value):
        self.dev.set(cid, value)


def to_array(img: QImage, w=None, h=None):
    if w:
        img = img.scaled(w, h)
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    bpl = img.bytesPerLine()
    # copy: the buffer belongs to the temporary QImage
    a = np.frombuffer(img.constBits(), dtype=np.uint8, count=bpl * img.height()).copy()
    return a.reshape(img.height(), bpl)[:, : img.width() * 3].reshape(img.height(), img.width(), 3)


def stats(img: QImage):
    """Mean level, contrast, gray-world casts, clipping, RGB histogram."""
    a = to_array(img, 320, 240).astype(np.float32)
    m = a.reshape(-1, 3).mean(0)
    luma = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    hist = [np.histogram(a[..., c], bins=64, range=(0, 256))[0] for c in range(3)]
    return dict(luma=float(luma.mean()), contrast=float(luma.std()),
                rg=float(m[0] / max(m[1], 1)), bg=float(m[2] / max(m[1], 1)),
                hi=float((luma >= 250).mean() * 100), lo=float((luma <= 5).mean() * 100),
                hist=hist)
