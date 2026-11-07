"""Qt binding switch: PySide6 or PyQt6, whichever is installed.

PySide6 is tried first. Set VISTACAM_QT=pyqt6 (or pyside6) to choose.
PyQt6 lets the app run on the distro's own Qt (`apt install python3-pyqt6
python3-pyqt6.qtsvg`), which matters on CPUs the PyPI Qt builds no longer
support, 32-bit systems and other architectures.
"""
import os

# Plugin paths meant for another Qt install (e.g. a system-wide QT_PLUGIN_PATH)
# load mismatched plugins and can crash. Clear them before Qt starts.
for _var in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
    os.environ.pop(_var, None)

_order = ["PySide6", "PyQt6"]
if os.environ.get("VISTACAM_QT", "").lower() == "pyqt6":
    _order.reverse()

API = None
for _name in _order:
    try:
        __import__(_name + ".QtWidgets")
        __import__(_name + ".QtSvg")
        API = _name
        break
    except ImportError:
        continue
if API is None:
    raise ImportError("VistaCam needs PySide6 or PyQt6 (with QtSvg). On Debian/Ubuntu/Mint: "
                      "sudo apt install python3-pyqt6 python3-pyqt6.qtsvg")

if API == "PySide6":
    from PySide6.QtCore import *  # noqa: F401,F403
    from PySide6.QtGui import *  # noqa: F401,F403
    from PySide6.QtWidgets import *  # noqa: F401,F403
    from PySide6.QtSvg import *  # noqa: F401,F403
    from PySide6.QtCore import Property, Signal  # noqa: F401
    from PySide6 import __version__ as BINDING_VERSION  # noqa: F401
else:
    from PyQt6.QtCore import *  # noqa: F401,F403
    from PyQt6.QtGui import *  # noqa: F401,F403
    from PyQt6.QtWidgets import *  # noqa: F401,F403
    from PyQt6.QtSvg import *  # noqa: F401,F403
    from PyQt6.QtCore import pyqtProperty as Property, pyqtSignal as Signal  # noqa: F401
    from PyQt6.QtCore import PYQT_VERSION_STR as BINDING_VERSION  # noqa: F401

from importlib import import_module as _imp  # noqa: E402

QtCore = _imp(API + ".QtCore")


def image_bytes(img):
    """The pixel buffer of a QImage as a bytes-like object."""
    b = img.constBits()
    if API == "PyQt6":
        b.setsize(img.sizeInBytes())
    return b


def module(name):
    """Another Qt module from the active binding, e.g. module("QtTest")."""
    return _imp(f"{API}.{name}")
