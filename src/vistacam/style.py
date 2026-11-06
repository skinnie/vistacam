"""Design tokens, stylesheet and icons.

Surfaces are zero-chroma greys on purpose: a tinted UI biases how you judge
the camera's colour.
"""
import os

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

DARK = dict(
    bg="#0c0c0d", surface="#141415", surface2="#1c1c1e", surface3="#29292c",
    line="#232325", line_strong="#38383b", text="#ededee", muted="#9b9ba1",
    faint="#6c6c72", accent="#f2b544", accent_ink="#1a1405", accent_soft="#2c2414",
    live="#ff4d4f", red="#ff6b6b", green="#5ee08a", blue="#5fa8ff", dark=True,
)
LIGHT = dict(
    bg="#ececed", surface="#f8f8f8", surface2="#ffffff", surface3="#e3e3e5",
    line="#dedee0", line_strong="#c9c9cc", text="#161617", muted="#5d5d63",
    faint="#8a8a90", accent="#b9770e", accent_ink="#ffffff", accent_soft="#f3e6cf",
    live="#e5383b", red="#e5484d", green="#2f9e55", blue="#2d7ff0", dark=False,
)

T = dict(DARK)  # current theme, mutated in place by apply_theme()


def c(name):
    return QColor(T[name])


_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_loaded = False


def load_fonts():
    """Register the bundled Inter (OFL) so the app looks the same everywhere."""
    global _loaded
    if not _loaded:
        QFontDatabase.addApplicationFont(os.path.join(_FONT_DIR, "InterVariable.ttf"))
        _loaded = True


def ui_font(size=10.0, weight=QFont.Weight.Normal):
    load_fonts()
    families = set(QFontDatabase.families())
    fam = next((f for f in ("Inter", "Inter Variable", "Cantarell", "Ubuntu", "Noto Sans")
                if f in families), None)
    f = QFont(fam) if fam else QFont()
    f.setPointSizeF(size)
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def stylesheet():
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {T['text']}; font-size: 10pt; }}
QMainWindow, #root {{ background: {T['bg']}; }}
QToolTip {{ background: {T['surface2']}; color: {T['text']}; border: 1px solid {T['line_strong']};
           padding: 5px 8px; border-radius: 6px; }}

#title {{ font-size: 13pt; font-weight: 600; }}
#subtitle {{ color: {T['muted']}; }}
#chip {{ color: {T['muted']}; background: {T['surface']}; border: 1px solid {T['line']};
        border-radius: 13px; padding: 3px 11px; font-size: 9pt; }}
#banner {{ background: {T['accent_soft']}; color: {T['text']}; border-radius: 10px; padding: 9px 14px; }}

#tile, #rail {{ background: {T['surface']}; border: 1px solid {T['line']}; border-radius: 14px; }}
#tileTitle, #sectionTitle {{ color: {T['muted']}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
#tileNote {{ color: {T['faint']}; font-size: 8.5pt; }}
#tag {{ color: {T['accent']}; background: {T['accent_soft']}; border-radius: 8px; padding: 1px 7px;
       font-size: 8pt; font-weight: 500; }}
#sep {{ background: {T['line']}; max-height: 1px; min-height: 1px; border: 0; }}
#hint {{ color: {T['faint']}; font-size: 8.5pt; }}
#value {{ color: {T['muted']}; }}
#bigNum {{ font-size: 20pt; font-weight: 600; }}

QPushButton {{
  background: {T['surface2']}; border: 1px solid {T['line']}; border-radius: 10px;
  padding: 0 14px; min-height: 36px; font-weight: 500;
}}
QPushButton:hover {{ border-color: {T['line_strong']}; }}
QPushButton:pressed, QPushButton[held="true"] {{ background: {T['surface3']}; border-color: {T['line_strong']}; }}
QPushButton:disabled {{ color: {T['faint']}; }}
QPushButton:focus {{ border-color: {T['accent']}; }}
QPushButton#primary {{ background: {T['text']}; color: {T['bg']}; border-color: {T['text']}; }}
QPushButton#primary:hover {{ background: {T['muted']}; border-color: {T['muted']}; }}
QPushButton#small {{ min-height: 28px; border-radius: 8px; padding: 0 11px; font-size: 9pt; }}
QPushButton#reset {{ background: transparent; border: 0; color: {T['faint']}; min-height: 0;
                     padding: 0 4px; font-size: 8.5pt; }}
QPushButton#reset:hover {{ color: {T['accent']}; }}
QPushButton#iconBtn {{ min-height: 32px; max-height: 32px; min-width: 32px; max-width: 32px;
                       padding: 0; border-radius: 9px; background: {T['surface']}; }}

#seg {{ background: {T['surface2']}; border: 1px solid {T['line']}; border-radius: 11px; }}
#seg QPushButton {{ background: transparent; border: 0; border-radius: 8px; min-height: 28px;
                   padding: 0 12px; color: {T['muted']}; }}
#seg QPushButton:hover {{ color: {T['text']}; }}
#seg QPushButton:checked {{ background: {T['surface3']}; color: {T['text']}; }}
#seg QPushButton:focus {{ border: 1px solid {T['accent']}; }}
#seg[big="true"] QPushButton {{ min-height: 32px; padding: 0 16px; }}
#seg QPushButton:disabled {{ color: {T['faint']}; }}
#seg QPushButton:checked:disabled {{ background: {T['surface3']}; color: {T['faint']}; }}
QLabel:disabled {{ color: {T['faint']}; }}
#seg QPushButton#accentChoice:checked {{ background: {T['accent']}; color: {T['accent_ink']}; font-weight: 600; }}

QLineEdit {{ background: {T['surface2']}; border: 1px solid {T['line']}; border-radius: 8px;
            padding: 0 9px; min-height: 30px; font-family: monospace; }}
QLineEdit:focus {{ border-color: {T['accent']}; }}

QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {T['line_strong']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QDialog {{ background: {T['surface']}; }}
#cmpHead {{ color: {T['muted']}; font-size: 8.5pt; }}
#cmpWin {{ color: {T['accent']}; font-weight: 600; }}
#mono {{ font-family: monospace; color: {T['faint']}; font-size: 8.5pt; }}
"""


# Lucide-style 24x24 outline icons
_ICONS = {
    "camera": '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3"/>',
    "split": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "folder": '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.6 3.9A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
    "arrows": '<path d="m9 18-6-6 6-6M15 6l6 6-6 6"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "lens": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 3v5M20.2 8l-4.3 2.5M20.2 16l-4.3-2.5M12 21v-5M3.8 16l4.3-2.5M3.8 8l4.3 2.5"/>',
}


def icon(name, color=None, size=18):
    col = color or T["text"]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{col}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
           f'{_ICONS[name]}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        r.render(p)
        p.end()
        pm.setDevicePixelRatio(scale)
        ic.addPixmap(pm)
    return ic


def apply_theme(app, dark):
    T.clear()
    T.update(DARK if dark else LIGHT)
    app.setStyleSheet(stylesheet())
