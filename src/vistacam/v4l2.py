"""Minimal V4L2 access for the Creative Live! Cam Vista IM (041e:4052).

Pure Python (ioctl + mmap), x86_64/aarch64 struct layouts. Only the camera
with USB ID 041e:4052 is ever opened.
"""
import errno
import fcntl
import glob
import mmap
import os
import select
import struct
from dataclasses import dataclass, field

USB_ID = "041e:4052"

# ioctl numbers (64-bit layouts)
VIDIOC_QUERYCAP = 0x80685600
VIDIOC_S_FMT = 0xC0D05605
VIDIOC_REQBUFS = 0xC0145608
VIDIOC_QUERYBUF = 0xC0585609
VIDIOC_QBUF = 0xC058560F
VIDIOC_DQBUF = 0xC0585611
VIDIOC_STREAMON = 0x40045612
VIDIOC_STREAMOFF = 0x40045613
VIDIOC_G_PARM = 0xC0CC5615
VIDIOC_S_PARM = 0xC0CC5616
VIDIOC_QUERYCTRL = 0xC0445624
VIDIOC_QUERYMENU = 0xC02C5625
VIDIOC_G_CTRL = 0xC008561B
VIDIOC_S_CTRL = 0xC008561C

BUF_TYPE_CAPTURE = 1
MEMORY_MMAP = 1
PIX_JPEG = 0x4745504A  # 'JPEG'
NEXT_CTRL = 0x80000000

T_INT, T_BOOL, T_MENU, T_BUTTON, T_CLASS, T_INTMENU = 1, 2, 3, 4, 6, 9
F_DISABLED, F_READ_ONLY, F_INACTIVE = 0x1, 0x4, 0x10

# Controls of the patched driver (see driver/ov7670_creative.c)
CID_BRIGHTNESS = 0x980900
CID_CONTRAST = 0x980901
CID_SATURATION = 0x980902
CID_GAMMA = 0x980910
CID_EXPOSURE = 0x980911
CID_GAIN = 0x980913
CID_HFLIP = 0x980914
CID_VFLIP = 0x980915
CID_POWER_LINE = 0x980918
CID_SHARPNESS = 0x98091B
CID_BACKLIGHT = 0x98091C
CID_EXPOSURE_AUTO = 0x9A0901
CID_WB_PRESET = 0x9A0914
CID_CREATIVE_TUNING = 0x98F900
CID_SHARPNESS_AUTO = 0x98F901
CID_SENSOR_REG = 0x98F902
CID_SENSOR_VAL = 0x98F903
CID_SENSOR_WRITE = 0x98F904
CID_SENSOR_READ = 0x98F905

QCTRL = "<II32siiiiI8x"
BUF = struct.Struct("<IIIII4x16x16xIIQII4x")  # index,type,bytesused,flags,field,seq,memory,m,length,reserved2


@dataclass
class Control:
    id: int
    type: int
    name: str
    min: int
    max: int
    step: int
    default: int
    flags: int
    menu: list = field(default_factory=list)  # [(value, label)]


def find_device():
    """Return /dev/videoN for the Vista IM, or None."""
    for v in sorted(glob.glob("/sys/class/video4linux/video*")):
        usb = os.path.realpath(os.path.join(v, "device", ".."))
        try:
            vid = open(os.path.join(usb, "idVendor")).read().strip()
            pid = open(os.path.join(usb, "idProduct")).read().strip()
            idx = open(os.path.join(v, "index")).read().strip()
        except OSError:
            continue
        if f"{vid}:{pid}" == USB_ID and idx == "0":
            return "/dev/" + os.path.basename(v)
    return None


def driver_info():
    """(module loaded, patched?) for gspca_ov519."""
    base = "/sys/module/gspca_ov519"
    return os.path.isdir(base), os.path.exists(os.path.join(base, "parameters", "creative_tuning"))


class Device:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.buffers = []
        self.streaming = False

    def close(self):
        self.stop()
        os.close(self.fd)

    # ---------------------------------------------------------------- info
    def card(self):
        b = bytearray(104)
        fcntl.ioctl(self.fd, VIDIOC_QUERYCAP, b)
        return b[16:48].rstrip(b"\0").decode(), b[:16].rstrip(b"\0").decode()

    # ------------------------------------------------------------ controls
    def controls(self):
        out, cid = [], 0
        while True:
            b = bytearray(struct.pack(QCTRL, cid | NEXT_CTRL, 0, b"", 0, 0, 0, 0, 0))
            try:
                fcntl.ioctl(self.fd, VIDIOC_QUERYCTRL, b)
            except OSError:
                break
            cid, typ, name, mn, mx, step, default, flags = struct.unpack(QCTRL, b)
            if typ == T_CLASS or flags & F_DISABLED:
                continue
            c = Control(cid, typ, name.rstrip(b"\0").decode(), mn, mx, step, default, flags)
            if typ in (T_MENU, T_INTMENU):
                c.menu = self._menu(cid, mn, mx, typ)
            out.append(c)
        return out

    def _menu(self, cid, mn, mx, typ):
        items = []
        for i in range(mn, mx + 1):
            b = bytearray(struct.pack("<II32sI", cid, i, b"", 0))
            try:
                fcntl.ioctl(self.fd, VIDIOC_QUERYMENU, b)
            except OSError:
                continue
            label = (str(struct.unpack_from("<q", b, 8)[0]) if typ == T_INTMENU
                     else b[8:40].rstrip(b"\0").decode())
            items.append((i, label))
        return items

    def get(self, cid):
        b = bytearray(struct.pack("<Ii", cid, 0))
        fcntl.ioctl(self.fd, VIDIOC_G_CTRL, b)
        return struct.unpack("<Ii", b)[1]

    def set(self, cid, value):
        fcntl.ioctl(self.fd, VIDIOC_S_CTRL, bytearray(struct.pack("<Ii", cid, int(value))))

    # ------------------------------------------------------------- capture
    def start(self, width=640, height=480, fps=30, nbuf=4):
        fmt = bytearray(208)
        struct.pack_into("<I", fmt, 0, BUF_TYPE_CAPTURE)
        struct.pack_into("<IIII", fmt, 8, width, height, PIX_JPEG, 0)
        fcntl.ioctl(self.fd, VIDIOC_S_FMT, fmt)
        self.width, self.height = struct.unpack_from("<II", fmt, 8)

        parm = bytearray(204)
        struct.pack_into("<I", parm, 0, BUF_TYPE_CAPTURE)
        struct.pack_into("<II", parm, 12, 1, fps)
        try:
            fcntl.ioctl(self.fd, VIDIOC_S_PARM, parm)
        except OSError:
            pass  # stock driver: no frame-rate control

        req = bytearray(struct.pack("<IIII4x", nbuf, BUF_TYPE_CAPTURE, MEMORY_MMAP, 0))
        fcntl.ioctl(self.fd, VIDIOC_REQBUFS, req)
        count = struct.unpack_from("<I", req)[0]
        self.buffers = []
        for i in range(count):
            b = bytearray(BUF.pack(i, BUF_TYPE_CAPTURE, 0, 0, 0, 0, MEMORY_MMAP, 0, 0, 0))
            fcntl.ioctl(self.fd, VIDIOC_QUERYBUF, b)
            f = BUF.unpack(b)
            offset, length = f[7] & 0xFFFFFFFF, f[8]
            self.buffers.append(mmap.mmap(self.fd, length, mmap.MAP_SHARED,
                                          mmap.PROT_READ | mmap.PROT_WRITE, offset=offset))
            fcntl.ioctl(self.fd, VIDIOC_QBUF, b)
        fcntl.ioctl(self.fd, VIDIOC_STREAMON, struct.pack("<I", BUF_TYPE_CAPTURE))
        self.streaming = True

    def read(self, timeout=1.0):
        """Return one JPEG frame (bytes), or None on timeout."""
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        b = bytearray(BUF.pack(0, BUF_TYPE_CAPTURE, 0, 0, 0, 0, MEMORY_MMAP, 0, 0, 0))
        try:
            fcntl.ioctl(self.fd, VIDIOC_DQBUF, b)
        except OSError as e:
            if e.errno == errno.EAGAIN:
                return None
            raise
        index, used = BUF.unpack(b)[0], BUF.unpack(b)[2]
        data = bytes(self.buffers[index][:used])
        fcntl.ioctl(self.fd, VIDIOC_QBUF, b)
        return data

    def stop(self):
        if self.streaming:
            try:
                fcntl.ioctl(self.fd, VIDIOC_STREAMOFF, struct.pack("<I", BUF_TYPE_CAPTURE))
            except OSError:
                pass
            self.streaming = False
        for m in self.buffers:
            m.close()
        self.buffers = []
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, VIDIOC_REQBUFS,
                            bytearray(struct.pack("<IIII4x", 0, BUF_TYPE_CAPTURE, MEMORY_MMAP, 0)))
            except OSError:
                pass
