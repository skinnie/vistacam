# VistaCam

A desktop app and an improved Linux driver for the **Creative Live! Cam Vista IM**:

| Model | USB ID | Status |
|---|---|---|
| VF0260 | `041e:4052` | developed and tested on this camera |
| VF0420 | `041e:4064` | same chips and same Creative tuning; should work, untested |

Linux has supported this 2007 webcam for years through the `gspca_ov519` driver, but only
with generic sensor settings: a washed-out picture, a cool cast, 15 fps, and five controls.
The Windows driver ships Creative's own tuning for the OV7670 sensor. This project brings
that tuning to Linux, exposes it as standard camera controls, and gives you an app to compare
the two live.

![VistaCam main window](docs/screenshot-dark.png)

## What you get

**Driver** (`driver/`, installed with DKMS)

- 30 fps at 640×480 (stock: 15). Apps can pick 30, 20 or 15 fps.
- Creative's sensor setup: their gamma curve, colour matrix, white-balance and
  low-light settings, taken from the Windows driver's INF file.
- New controls, usable from any V4L2 app (VistaCam, `v4l2-ctl`, OBS, guvcview):
  saturation, sharpness (auto or manual), gamma, white-balance presets
  (auto, tungsten, fluorescent, daylight), backlight compensation, and manual
  exposure and gain.
- A **Creative Tuning** switch that flips between Creative's settings and the stock
  Linux ones while the camera streams, so you can compare the same scene.
- Raw OV7670 register read/write for experiments.

**App** (`src/vistacam/`, Qt 6)

- Live view with measured fps, RGB histogram, colour-cast meters and clipping meters.
- **Hold for stock** (or hold <kbd>B</kbd>): shows the stock tuning while held.
- **Compare A/B**: takes one frame with each tuning, after auto-exposure settles,
  and shows them in a drag-to-compare view with the numbers side by side.
- Every driver control, grouped and labelled. Dark and light themes.
- Snapshots go to `~/Pictures/VistaCam/`.
- Only ever opens the Vista IM, never your other cameras. Reconnects when you replug it.

![Compare A/B](docs/screenshot-compare.png)

## Install

### Ubuntu, Linux Mint, Debian (.deb)

Download both `.deb` files from the [latest release](https://github.com/skinnie/vistacam/releases/latest)
and install them together:

```sh
sudo apt install ./gspca-ov519-vistacam-dkms_*_all.deb ./vistacam_*_amd64.deb
```

Then start **VistaCam** from the menu. Replug the camera if it was in use during the install.

- `gspca-ov519-vistacam-dkms` is the driver. DKMS compiles it for your kernel and rebuilds
  it after every kernel update. It needs your kernel's headers, which Mint and Ubuntu
  install by default (otherwise: `sudo apt install linux-headers-$(uname -r)`).
- `vistacam` is the app. It brings its own copy of Qt, so nothing else needs installing,
  and it runs on CPUs back to the Core 2 (see [Older PCs](#older-pcs-32-bit-arm-and-other-setups)).
- Tested in CI on Ubuntu 22.04 and 24.04, Linux Mint 21.3 and 22.2, LMDE 6 and Debian 12
  (x86_64).
- With Secure Boot on, DKMS asks you to set a password the first time and enroll its
  signing key at the next boot (the blue "MOK management" screen). Otherwise the kernel
  refuses to load the driver.
- Remove with `sudo apt remove vistacam gspca-ov519-vistacam-dkms`. The stock driver
  comes back.

### Other distributions (install script)

Needs `dkms`, the headers for your running kernel, and Python 3.10+ with `venv`:

```sh
git clone https://github.com/skinnie/vistacam.git
cd vistacam
./install.sh
```

`install.sh` builds the driver with DKMS (it asks for sudo and rebuilds itself on kernel
updates), then installs the app for your user in `~/.local/share/vistacam` with a menu
entry. Options: `--driver`, `--app`, `--system-qt`, `--uninstall`.

### Older PCs, 32-bit, ARM and other setups

VistaCam is meant to run on hardware as old as the camera.

- **Old x86 CPUs** (Core 2, Pentium Dual-Core, Athlon 64, Phenom: anything without SSE4.2).
  The .deb bundles PySide6 6.9, the last release whose Qt runs on these CPUs, and CI
  starts the app on an emulated Core 2 for every change. `install.sh` picks 6.9
  by itself when your CPU lacks SSE4.2.
- **Use your distro's Qt instead.** The app runs on PyQt6 as well as PySide6. Distro Qt
  packages are built for the oldest CPUs the distro supports, and exist for 32-bit and ARM:

  ```sh
  sudo apt install python3-pyqt6 python3-pyqt6.qtsvg python3-numpy python3-venv
  ./install.sh --driver      # if you want the tuned driver
  ./install.sh --system-qt
  ```

  Or run it straight from the source tree: `VISTACAM_QT=pyqt6 python3 -m vistacam`
  (with `src` on `PYTHONPATH`). Debian 12, Ubuntu 24.04 and Mint 22 ship PyQt6;
  Ubuntu 22.04 / Mint 21 do not, so use the .deb there.
- **Adapting it.** The driver is plain kernel C with no CPU-specific code and builds on any
  architecture DKMS supports. The app is pure Python; `src/vistacam/qt.py` is the only
  place that knows which Qt binding is in use, and `v4l2.py` talks to the camera with
  plain ioctls (no OpenCV, no GStreamer). It assumes a 64-bit kernel ABI for the
  capture structs, so 32-bit systems need the struct formats in `v4l2.py` adjusted.

### Build the .deb files yourself

```sh
packaging/deb/build.sh        # writes dist/*.deb
```

The app also works with the stock driver. It then shows the basic controls and tells you
the patched driver is missing.

### Run from the source tree

```sh
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/vistacam
```

### Try the driver without installing it

```sh
cd driver && make
sudo rmmod gspca_ov519 && sudo insmod ./gspca_ov519.ko   # until reboot
```

## How it works

The camera is an OmniVision **OV519** USB bridge with an **OV7670** sensor. The bridge
sends JPEG frames.

Creative's Windows driver (`LCVA_PCDrv_US_1_11_02.exe`, 2007) is a Wise installer. Its
`V0260Vid.inf` holds the complete sensor init sequence and a register table for every
property the Windows driver offers. `driver/gen_tables.py` turns those tables into
`driver/creative_tables.h`, so every register value in the driver traces back to
Creative's file. No values are hand-tuned.

Changes to the upstream driver:

| | Stock `gspca_ov519` | This driver |
|---|---|---|
| Frame rate at 640×480 | 15 fps, hard-coded | 30 fps default, selectable |
| Sensor init | OmniVision reference values | Creative's Vista IM values |
| Controls | brightness, contrast, flips, mains flicker | plus saturation, sharpness, gamma, white balance, exposure, gain, backlight, tuning switch, register access |

`driver/ov519-vistacam.patch` is the diff against Linux 7.0's `ov519.c`. The new code
lives in `driver/ov7670_creative.c`, and only applies to the OV7670 sensor, so other OV519
cameras behave as before. The sources build against Linux 7.0. Older or newer kernels may
need small changes in `gspca.h`.

The VF0420's Windows driver (`V0420Vid.inf`, May 2007) contains the same sensor setup and
the same register table for every property as the VF0260's (`V0260Vid.inf`, July 2007).
The two differ only in LED polarity, which the kernel driver already handles, and in a
setup for the 352×288 and 176×144 modes that is close to OmniVision's reference values.
If you own a VF0420, please report whether it works.

### What the tuning does

Creative's settings give a more neutral colour balance and keep highlights from clipping.
In dim indoor light they come out slightly darker than stock, and raising **Gamma** to 3 or
4 brightens them. Switching tuning resets the sensor's exposure, so allow a second for
auto-exposure to settle. Compare A/B waits for that itself.

## Repository layout

```
driver/            patched gspca_ov519, DKMS config, register-table generator
src/vistacam/      the Qt app (v4l2.py: camera access, window.py: UI)
packaging/         desktop entry, icon
packaging/deb/     .deb builder (also run by GitHub Actions)
tools/             off-screen screenshot renderer for the docs
install.sh         driver + app installer
```

## Legal

The driver is derived from the Linux kernel's `gspca_ov519` and is GPL-2.0-or-later, as is
the app. The register values in `creative_tables.h` were extracted from Creative's
publicly distributed Windows driver. Creative's files themselves are not included.
Inter font: SIL Open Font License (`src/vistacam/fonts/Inter-LICENSE.txt`).

Not affiliated with Creative Technology.
