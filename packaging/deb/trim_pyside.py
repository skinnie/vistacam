#!/usr/bin/env python3
"""Strip a pip-installed PySide6 down to what VistaCam uses.

Keeps the QtCore/QtGui/QtWidgets/QtSvg bindings, the desktop plugins (X11,
Wayland, image formats, input methods, GTK theme) and every Qt library those
need, found by following ELF NEEDED entries. Everything else (QML, Quick,
Designer, WebEngine stubs, dev tools, headers) is deleted.

usage: trim_pyside.py <site-packages dir>
"""
import os
import shutil
import subprocess
import sys

BINDINGS = {"QtCore", "QtGui", "QtWidgets", "QtSvg"}
PLUGIN_DIRS = {
    "platforms", "xcbglintegrations", "imageformats", "iconengines",
    "platformthemes", "platforminputcontexts", "wayland-decoration-client",
    "wayland-graphics-integration-client", "wayland-shell-integration",
}
# offscreen/minimal/vnc/eglfs/linuxfb platform plugins are not needed on a desktop
PLATFORMS = {"libqxcb.so", "libqwayland.so", "libqwayland-egl.so", "libqwayland-generic.so",
             "libqoffscreen.so"}


def needed(path):
    out = subprocess.run(["readelf", "-d", path], capture_output=True, text=True).stdout
    return [l.split("[", 1)[1].split("]", 1)[0] for l in out.splitlines() if "(NEEDED)" in l]


def main(site):
    pyside = os.path.join(site, "PySide6")
    qt = os.path.join(pyside, "Qt")
    libdir = os.path.join(qt, "lib")

    # 1. bindings and loose files in PySide6/
    for name in os.listdir(pyside):
        p = os.path.join(pyside, name)
        mod = name.split(".", 1)[0]
        if name == "Qt" or name.startswith("__") or name.startswith("libpyside6.abi3"):
            continue
        if name.endswith(".abi3.so") or name.endswith(".pyi"):
            if mod in BINDINGS:
                continue
        elif name in ("support", "py.typed", "_config.py", "_git_pyside_version.py"):
            continue
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    # 2. plugins
    plugins = os.path.join(qt, "plugins")
    for d in os.listdir(plugins):
        if d not in PLUGIN_DIRS:
            shutil.rmtree(os.path.join(plugins, d))
    for so in os.listdir(os.path.join(plugins, "platforms")):
        if so not in PLATFORMS:
            os.remove(os.path.join(plugins, "platforms", so))

    # plugins that would drag in QML/Quick/PDF (e.g. the virtual keyboard)
    for dp, _, fs in os.walk(plugins):
        for f in fs:
            if any(HEAVY in dep for dep in needed(os.path.join(dp, f)) for HEAVY in
                   ("Qml", "Quick", "Pdf", "VirtualKeyboard", "Labs", "Compositor", "WlShell")):
                os.remove(os.path.join(dp, f))

    # 3. QML, translations and other data
    for d in os.listdir(qt):
        if d not in ("lib", "plugins"):
            p = os.path.join(qt, d)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for d in os.listdir(site):
        if d.startswith("shiboken6_generator") or d == "bin":
            shutil.rmtree(os.path.join(site, d))

    # 4. Qt libraries: keep the NEEDED closure of what is left
    roots = [os.path.join(dp, f) for dp, _, fs in os.walk(pyside) for f in fs
             if ".so" in f and not dp.startswith(libdir)]
    roots += [os.path.join(site, "shiboken6", f) for f in os.listdir(os.path.join(site, "shiboken6"))
              if ".so" in f]
    present = set(os.listdir(libdir))
    keep, todo = set(), list(roots)
    while todo:
        for dep in needed(todo.pop()):
            if dep in present and dep not in keep:
                keep.add(dep)
                todo.append(os.path.join(libdir, dep))
    for name in present - keep:
        p = os.path.join(libdir, name)
        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)


if __name__ == "__main__":
    main(sys.argv[1])
