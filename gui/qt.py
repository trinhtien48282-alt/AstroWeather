"""PySide6 widgets, layout helpers, and canvas drawing for AstroWeather pages.

Tk-compat layer. Semantics kept from Tk/CustomTkinter:
  * pack/grid padx/pady are OUTER margins (each placed widget sits in a margin box).
  * CTkFont sizes are PIXELS (Font.setPixelSize); raw canvas font tuples are points.
  * width= on Entry/ComboBox/Label/Slider is exact; Button/Frame width= is a minimum.
  * Unplaced widgets are invisible; placed ones keep natural size unless fill/expand/sticky say otherwise.
"""
from __future__ import annotations

import itertools
import re
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QBrush, QIcon, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QScrollBar,
    QSizePolicy, QSlider, QTabWidget, QVBoxLayout, QWidget, QMessageBox)
from PySide6.QtWidgets import QStackedWidget

_name_ids = itertools.count(1)
NO_ALIGN = Qt.AlignmentFlag(0)
_EXP, _MAX, _PREF = QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred


def _host(master):
    return master.content if isinstance(master, ScrollableWidget) else master


def _font(value):
    """Canvas-style tuples (name, size, 'bold') are Tk POINTS; CTkFont objects are QFont already (pixels)."""
    if isinstance(value, QFont):
        return value
    if isinstance(value, (tuple, list)):
        name, size, *style = value
        result = QFont(str(name))
        result.setPointSize(int(size))
        result.setBold("bold" in style)
        return result
    return QFont(QApplication.font())


_ANCH_W, _ANCH_E = frozenset(("w", "nw", "sw")), frozenset(("e", "ne", "se"))
_FONT_CACHE = {}


def _cached_font(value):
    """(QFont, QFontMetricsF) for a font option; tuple fonts are built once per distinct tuple."""
    if isinstance(value, (tuple, list)):
        key = tuple(value)
        hit = _FONT_CACHE.get(key)
        if hit is None:
            f = _font(value)
            hit = _FONT_CACHE[key] = (f, QFontMetricsF(f))
        return hit
    f = _font(value)
    return f, QFontMetricsF(f)


def _alignment(anchor="center", justify=None):
    anchor = (anchor or "center").lower()
    h = Qt.AlignmentFlag.AlignLeft if anchor.endswith("w") or anchor == "w" else Qt.AlignmentFlag.AlignRight if anchor.endswith("e") or anchor == "e" else Qt.AlignmentFlag.AlignHCenter
    v = Qt.AlignmentFlag.AlignTop if anchor.startswith("n") else Qt.AlignmentFlag.AlignBottom if anchor.startswith("s") else Qt.AlignmentFlag.AlignVCenter
    if justify == "left": h = Qt.AlignmentFlag.AlignLeft
    elif justify == "right": h = Qt.AlignmentFlag.AlignRight
    return h | v


def _grid_alignment(sticky):
    """Tk sticky: opposite edges stretch that axis, otherwise the widget keeps natural size and is pinned/centred."""
    sticky = sticky.lower()
    f = NO_ALIGN
    if not ("e" in sticky and "w" in sticky):
        f |= Qt.AlignmentFlag.AlignLeft if "w" in sticky else Qt.AlignmentFlag.AlignRight if "e" in sticky else Qt.AlignmentFlag.AlignHCenter
    if not ("n" in sticky and "s" in sticky):
        f |= Qt.AlignmentFlag.AlignTop if "n" in sticky else Qt.AlignmentFlag.AlignBottom if "s" in sticky else Qt.AlignmentFlag.AlignVCenter
    return f


def _pack_align(anchor, horiz_parent):
    """Only the cross-axis matters for pack: horizontal in a vertical parent, vertical in a horizontal one."""
    anchor = (anchor or "").lower()
    if not anchor:
        return NO_ALIGN
    if not horiz_parent:
        return (Qt.AlignmentFlag.AlignLeft if anchor in ("w", "nw", "sw") else
                Qt.AlignmentFlag.AlignRight if anchor in ("e", "ne", "se") else Qt.AlignmentFlag.AlignHCenter)
    return (Qt.AlignmentFlag.AlignTop if anchor.startswith("n") else
            Qt.AlignmentFlag.AlignBottom if anchor.startswith("s") else Qt.AlignmentFlag.AlignVCenter)


class _LayoutMixin:
    # shortcut: preserve page layout calls during the Qt port; replace with direct Qt layouts when redesigning a page.
    def _init_layout(self):
        self._layout_kind = None
        self._grid_col_cfg = {}
        self._grid_row_cfg = {}
        self._pad_box = None     # margin box holding this widget inside the parent's layout
        self._pad_slot = None    # "start" | "end" | "grid"
        if self.parentWidget() is not None:
            self.hide()          # Tk: a widget is invisible until pack/grid places it

    def _wrap(self, padx, pady, align):
        l, r = (padx, padx) if isinstance(padx, (int, float)) else (padx[0], padx[-1])
        t, b = (pady, pady) if isinstance(pady, (int, float)) else (pady[0], pady[-1])
        box = QHBoxLayout()
        box.setContentsMargins(int(l), int(t), int(r), int(b))  # OUTER padding, like Tk
        box.setSpacing(0)
        box.addWidget(self, 0, align)
        self._pad_box = box
        return box

    def grid(self, row=0, column=0, rowspan=1, columnspan=1, sticky="", padx=0, pady=0, **_):
        parent = self.parentWidget()
        if parent is None: return
        if self._pad_box is not None:
            self.show(); return
        layout = _ensure_layout(parent, "grid")
        if not isinstance(layout, QGridLayout):
            raise RuntimeError("Grid child requires a grid parent")
        box = self._wrap(padx, pady, _grid_alignment(sticky) if sticky else NO_ALIGN)
        layout.addLayout(box, row, column, rowspan, columnspan)
        self._pad_slot = "grid"
        self.show()

    def pack(self, side="top", fill="none", expand=False, anchor="", padx=0, pady=0, **_):
        parent = self.parentWidget()
        if parent is None: return
        if self._pad_box is not None:
            self.show(); return
        horiz = side in ("left", "right")
        layout = _ensure_layout(parent, "horizontal" if horiz else "vertical")
        if not isinstance(layout, (QHBoxLayout, QVBoxLayout)):
            raise RuntimeError("Packed child requires a box parent")
        if getattr(parent, "_n_start", None) is None:
            layout.addStretch(1)       # keeps start-packed items at natural size; end-packed ones go after it
            parent._n_start = 0
        wrapped = isinstance(self, QLabel) and self.wordWrap()
        if horiz:
            self.setSizePolicy(_EXP if expand else _MAX, _EXP if fill in ("y", "both") else _MAX)
        else:
            self.setSizePolicy(_EXP if fill in ("x", "both") else (_PREF if wrapped else _MAX), _EXP if expand else _PREF)
        box = self._wrap(padx, pady, _pack_align(anchor, horiz))
        stretch = 1 if expand else 0
        if side in ("right", "bottom"):
            layout.insertLayout(parent._n_start + 1, box, stretch)
            self._pad_slot = "end"
        else:
            layout.insertLayout(parent._n_start, box, stretch)
            parent._n_start += 1
            self._pad_slot = "start"
            if expand:
                layout.setStretch(parent._n_start, 0)  # the tail spacer must not compete with an expanding child
        self.show()

    def pack_forget(self): self.hide()

    def grid_columnconfigure(self, column, weight=0, minsize=0, **_):
        self._grid_col_cfg[column] = (weight, minsize)
        layout = self.layout()
        if isinstance(layout, QGridLayout):
            layout.setColumnStretch(column, weight)
            layout.setColumnMinimumWidth(column, minsize)

    def grid_rowconfigure(self, row, weight=0, minsize=0, **_):
        self._grid_row_cfg[row] = (weight, minsize)
        layout = self.layout()
        if isinstance(layout, QGridLayout):
            layout.setRowStretch(row, weight)
            layout.setRowMinimumHeight(row, minsize)

    def grid_propagate(self, propagate):
        if not propagate:  # Tk: keep the requested width/height instead of shrink-wrapping the children
            if self.minimumWidth(): self.setFixedWidth(self.minimumWidth())
            if self.minimumHeight(): self.setFixedHeight(self.minimumHeight())

    def tkraise(self): self.raise_(); self.show()
    def winfo_children(self): return [c for c in self.children() if isinstance(c, QWidget)]
    def winfo_width(self): return self.width()
    def winfo_height(self): return self.height()

    def destroy(self):
        parent, box = self.parentWidget(), self._pad_box
        if box is not None:
            box.removeWidget(self)
            layout = parent.layout() if parent is not None else None
            if layout is not None:
                layout.removeItem(box)   # drop the margin box too, or its padding stays behind as a ghost gap
                layout.invalidate()
            box.deleteLater()
            if self._pad_slot == "start" and parent is not None and getattr(parent, "_n_start", 0):
                parent._n_start -= 1
            self._pad_box = self._pad_slot = None
        self.setParent(None)  # immediate detach so winfo_children() reflects removal synchronously
        self.deleteLater()


class FrameWidget(_LayoutMixin, QFrame):
    def __init__(self, master=None, fg_color=None, corner_radius=0, width=0, height=0, **_):
        super().__init__(_host(master))
        self._init_layout()
        self.setFrameShape(QFrame.Shape.NoFrame)
        if width: self.setMinimumWidth(width)
        if height: self.setMinimumHeight(height)
        if fg_color and fg_color != "transparent":
            name = f"aw{next(_name_ids)}"  # object-name selector: the card colour must not leak onto child labels/text boxes
            self.setObjectName(name)
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.setStyleSheet(f"QFrame#{name}{{background:{fg_color};border-radius:{corner_radius}px;}}")


class LabelWidget(_LayoutMixin, QLabel):
    def __init__(self, master=None, text="", font=None, text_color=None, anchor="center", justify=None, width=0, wraplength=0, **_):
        super().__init__(str(text), _host(master))
        self._init_layout(); self.setFont(_font(font)); self.setAlignment(_alignment(anchor, justify)); self.setWordWrap(bool(wraplength))
        if wraplength: self.setMaximumWidth(int(wraplength))  # Tk wraps at wraplength px, never wider
        if width: self.setFixedWidth(width)
        if text_color: self.setStyleSheet(f"color:{text_color}; background:transparent;")
    def configure(self, **kwargs):
        if "text" in kwargs: self.setText(str(kwargs.pop("text")))
        if "text_color" in kwargs: self.setStyleSheet(f"color:{kwargs.pop('text_color')}; background:transparent;")
        if "font" in kwargs: self.setFont(_font(kwargs.pop("font")))
        if "state" in kwargs: self.setEnabled(kwargs.pop("state") != "disabled")
    config = configure
    def cget(self, key): return self.text() if key == "text" else None


class ButtonWidget(_LayoutMixin, QPushButton):
    def __init__(self, master=None, text="", command=None, font=None, width=0, height=0, fg_color=None, hover_color=None,
                 text_color=None, anchor="center", state="normal", **_):
        super().__init__(str(text), _host(master))
        self._init_layout(); self._command = command; self.clicked.connect(lambda: self._command and self._command())
        self.setFont(_font(font)); self.setEnabled(state != "disabled")
        if width: self.setMinimumWidth(width)
        if height: self.setMinimumHeight(height)
        self._anchor = anchor
        self._bg, self._fg, self._hover = fg_color, text_color or "#d0d4dc", hover_color
        self._style()
    def _style(self):
        bg = self._bg; hover = self._hover or (bg if bg and bg != "transparent" else "#232830")
        align = "left" if self._anchor == "w" else "center"
        self.setStyleSheet(f"QPushButton{{background:{bg if bg and bg != 'transparent' else 'transparent'};color:{self._fg};border:0;border-radius:6px;padding:5px 9px;text-align:{align}}} "
                           f"QPushButton:hover{{background:{hover}}} QPushButton:disabled{{color:#6b7390}}")
    def configure(self, **kwargs):
        if "text" in kwargs: self.setText(str(kwargs.pop("text")))
        if "state" in kwargs: self.setEnabled(kwargs.pop("state") != "disabled")
        if "command" in kwargs: self._command = kwargs.pop("command")
        if "fg_color" in kwargs: self._bg = kwargs.pop("fg_color")
        if "text_color" in kwargs: self._fg = kwargs.pop("text_color")
        if "hover_color" in kwargs: self._hover = kwargs.pop("hover_color")
        self._style()
        if "font" in kwargs: self.setFont(_font(kwargs.pop("font")))
    config = configure
    def cget(self, key): return self.text() if key == "text" else None


class EntryWidget(_LayoutMixin, QLineEdit):
    def __init__(self, master=None, width=0, font=None, placeholder_text=None, **_):
        super().__init__(_host(master)); self._init_layout()
        if width: self.setFixedWidth(width)
        if font: self.setFont(_font(font))
        if placeholder_text: self.setPlaceholderText(placeholder_text)
    def get(self): return self.text()
    def insert(self, index, text): self.setCursorPosition(min(int(index), len(self.text()))); super().insert(str(text))
    def delete(self, start, end=None):
        if end == "end" or start == 0: self.clear()
        else: self.setSelection(int(start), max(1, int(end or start) - int(start))); self.backspace()
    def bind(self, sequence, callback):
        if sequence == "<KeyRelease>": self.textChanged.connect(lambda: callback(SimpleNamespace(widget=self)))


class TextBoxWidget(_LayoutMixin, QPlainTextEdit):
    def __init__(self, master=None, height=0, font=None, fg_color=None, state="normal", wrap="word", **_):
        super().__init__(_host(master)); self._init_layout()
        if height: self.setMinimumHeight(height)
        if font: self.setFont(_font(font))
        self.setReadOnly(state == "disabled")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap if wrap == "none" else QPlainTextEdit.LineWrapMode.WidgetWidth)
        if fg_color: self.setStyleSheet(f"QPlainTextEdit{{background:{fg_color};color:#d0d4dc;border:0;}}")  # selector: keep scrollbars unstyled
    def configure(self, **kwargs):
        if "state" in kwargs: self.setReadOnly(kwargs.pop("state") == "disabled")
        if "font" in kwargs: self.setFont(_font(kwargs.pop("font")))
    config = configure
    def delete(self, *_): self.clear()
    def insert(self, index, text): self.setPlainText(str(text))
    def get(self, *_): return self.toPlainText()


class ComboBoxWidget(_LayoutMixin, QComboBox):
    def __init__(self, master=None, values=(), width=0, command=None, **_):
        super().__init__(_host(master)); self._init_layout()
        self.addItems([str(v) for v in values]); self._command = command
        if width: self.setFixedWidth(width)
        if command: self.currentTextChanged.connect(command)
    def set(self, value):
        blocked = self.blockSignals(True); self.setCurrentText(str(value)); self.blockSignals(blocked)
    def get(self): return self.currentText()


class BooleanVar:
    def __init__(self, value=False): self._value = bool(value)
    def get(self): return self._value
    def set(self, value): self._value = bool(value)


class SwitchWidget(_LayoutMixin, QCheckBox):
    def __init__(self, master=None, text="", variable=None, command=None, font=None, state="normal", **_):
        super().__init__(str(text), _host(master)); self._init_layout()
        self.variable = variable or BooleanVar(); self.setChecked(self.variable.get()); self.setEnabled(state != "disabled")
        if font: self.setFont(_font(font))
        self.toggled.connect(self.variable.set)
        if command: self.toggled.connect(lambda _checked: command())
    def configure(self, **kwargs):
        if "state" in kwargs: self.setEnabled(kwargs.pop("state") != "disabled")
        if "text" in kwargs: self.setText(str(kwargs.pop("text")))
    config = configure


class SliderWidget(_LayoutMixin, QSlider):
    def __init__(self, master=None, from_=0, to=1, number_of_steps=100, command=None, width=0, **_):
        super().__init__(Qt.Orientation.Horizontal, _host(master)); self._init_layout()
        self._lo, self._hi = float(from_), float(to); self._steps = max(1, int(number_of_steps)); self._command = command
        self.setRange(0, self._steps); self.valueChanged.connect(lambda n: command(self._lo + n * (self._hi - self._lo) / self._steps) if command else None)
        if width: self.setFixedWidth(width)
    def set(self, value):
        blocked = self.blockSignals(True)  # Tk's set() never fires the command; sky_now() redraws itself
        self.setValue(round((float(value) - self._lo) / (self._hi - self._lo) * self._steps))
        self.blockSignals(blocked)
    def get(self): return self._lo + self.value() * (self._hi - self._lo) / self._steps


class ScrollableWidget(_LayoutMixin, QScrollArea):
    def __init__(self, master=None, fg_color=None, width=0, **_):
        super().__init__(master); self._init_layout(); self.content = QWidget(); self.content._layout_kind = None
        self.content._grid_col_cfg = {}; self.content._grid_row_cfg = {}
        self.setWidget(self.content); self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        if width: self.setMinimumWidth(width)
        if fg_color and fg_color != "transparent":
            name = f"aw{next(_name_ids)}"
            self.content.setObjectName(name)
            self.content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.content.setStyleSheet(f"#{name}{{background:{fg_color}}}")
    def grid_columnconfigure(self, column, weight=0, minsize=0, **_):
        self.content._grid_col_cfg[column] = (weight, minsize)
        layout = self.content.layout()
        if isinstance(layout, QGridLayout):
            layout.setColumnStretch(column, weight); layout.setColumnMinimumWidth(column, minsize)
    def grid_rowconfigure(self, row, weight=0, minsize=0, **_):
        self.content._grid_row_cfg[row] = (weight, minsize)
        layout = self.content.layout()
        if isinstance(layout, QGridLayout):
            layout.setRowStretch(row, weight); layout.setRowMinimumHeight(row, minsize)
    def winfo_children(self): return [c for c in self.content.children() if isinstance(c, QWidget)]


class TabViewWidget(_LayoutMixin, QTabWidget):
    def __init__(self, master=None, **_): super().__init__(_host(master)); self._init_layout(); self._tabs = {}
    def add(self, name):
        page = QWidget(); page._layout_kind = None; self._tabs[name] = page; self.addTab(page, name)
    def tab(self, name): return self._tabs[name]


class PageStack(_LayoutMixin, QStackedWidget):
    def __init__(self, master=None): super().__init__(master); self._init_layout()


class ScrollBarWidget(_LayoutMixin, QScrollBar):
    def __init__(self, master=None, orientation="vertical", command=None, **_):
        super().__init__(Qt.Orientation.Horizontal if orientation == "horizontal" else Qt.Orientation.Vertical, _host(master)); self._init_layout()
        if command: self.valueChanged.connect(lambda value: command("moveto", value / max(1, self.maximum())))
    def set(self, first, last):
        first = float(first); last = float(last); self.setRange(0, 10000); self.setPageStep(max(1, int((last - first) * 10000)))
        blocked = self.blockSignals(True); self.setValue(int(first * 10000)); self.blockSignals(blocked)


class Canvas(_LayoutMixin, QWidget):
    _ids = itertools.count(1)
    def __init__(self, master=None, width=0, height=0, bg="#0b1020", xscrollincrement=1, **_):
        super().__init__(_host(master)); self._init_layout()
        self.setMinimumSize(width or 120, height or 100); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._hint = QSize(width or 120, height or 100)  # pack without fill/expand keeps the requested size, like Tk
        self.setMouseTracking(True)                      # Tk <Motion> fires without a button held (altitude-graph crosshair)
        self.bg = bg; self.items = []; self.scroll_width = 0; self.xoff = 0; self._scroll_cb = None; self._bindings = {}; self._increment = xscrollincrement
    def sizeHint(self): return self._hint
    def bind(self, sequence, callback):
        self._bindings.setdefault(sequence, []).append(callback)
        if sequence == "<Configure>": self._fire(sequence, SimpleNamespace(width=self.width(), height=self.height()))
    def _fire(self, sequence, event):
        for callback in self._bindings.get(sequence, []): callback(event)
    def resizeEvent(self, e): super().resizeEvent(e); self._fire("<Configure>", SimpleNamespace(width=self.width(), height=self.height()))
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            x, y = int(e.position().x()) + self.xoff, int(e.position().y()); self._fire("<Button-1>", SimpleNamespace(x=x, y=y, delta=0)); self._fire("<ButtonPress-1>", SimpleNamespace(x=x, y=y, delta=0)); self._last = (x, y); e.accept()
    def mouseDoubleClickEvent(self, e): self._fire("<Double-Button-1>", SimpleNamespace(x=int(e.position().x()) + self.xoff, y=int(e.position().y()), delta=0))
    def mouseMoveEvent(self, e):
        x, y = int(e.position().x()) + self.xoff, int(e.position().y()); self._fire("<Motion>", SimpleNamespace(x=x, y=y, delta=0))
        if e.buttons() & Qt.MouseButton.LeftButton: self._fire("<B1-Motion>", SimpleNamespace(x=x, y=y, delta=0))
    def mouseReleaseEvent(self, e): self._fire("<ButtonRelease-1>", SimpleNamespace(x=int(e.position().x()) + self.xoff, y=int(e.position().y()), delta=0))
    def wheelEvent(self, e):
        delta = e.angleDelta().y(); self._fire("<MouseWheel>", SimpleNamespace(x=int(e.position().x()) + self.xoff, y=int(e.position().y()), delta=delta)); e.accept()
    def configure(self, **kwargs):
        if "scrollregion" in kwargs:
            region = kwargs["scrollregion"]; self.scroll_width = max(0, int(region[2])); self._scroll_update()
        if "xscrollcommand" in kwargs: self._scroll_cb = kwargs["xscrollcommand"]; self._scroll_update()
        if "bg" in kwargs: self.bg = kwargs["bg"]
    config = configure
    def _scroll_update(self):
        if self._scroll_cb:
            full = max(1, self.scroll_width); self._scroll_cb(self.xoff / full, min(1, (self.xoff + self.width()) / full))
    def xview(self, *args):
        if not args: return (self.xoff / max(1, self.scroll_width), min(1, (self.xoff + self.width()) / max(1, self.scroll_width)))
        if args[0] == "moveto": self.xoff = int(float(args[1]) * self.scroll_width)
        elif args[0] == "scroll": self.xoff += int(args[1]) * self._increment
        self.xoff = max(0, min(self.xoff, max(0, self.scroll_width - self.width()))); self._scroll_update(); self.update()
    def xview_moveto(self, f): self.xview("moveto", f)
    def xview_scroll(self, n, unit): self.xview("scroll", n, unit)
    def canvasx(self, x): return x + self.xoff
    def delete(self, tag):
        self.items = [] if tag == "all" else [i for i in self.items if i["tag"] != tag]; self.update()
    def _add(self, kind, coords, **opts):
        tag = opts.pop("tags", ""); item = {"id": next(self._ids), "kind": kind, "coords": coords, "tag": tag, "opts": opts}; self.items.append(item); self.update(); return item["id"]
    def create_oval(self, *xy, **opts): return self._add("oval", xy, **opts)
    def create_rectangle(self, *xy, **opts): return self._add("rect", xy, **opts)
    def create_line(self, *xy, **opts): return self._add("line", xy, **opts)
    def create_text(self, x, y, **opts): return self._add("text", (x, y), **opts)
    def create_arc(self, *xy, **opts): return self._add("arc", xy, **opts)
    @staticmethod
    def _text_rect(x, y, anchor, txt, fm):
        """Rect the text is aligned inside. Anchors are matched exactly: the old substring test found the 'e' in
        "center", so every default (centred) text was right-anchored and drawn half its width to the left."""
        a = (anchor or "center").lower()
        rect = QRectF(x, y - fm.height() / 2, max(2, fm.horizontalAdvance(txt) + 4), fm.height())
        if a in _ANCH_W: rect.moveLeft(x)
        elif a in _ANCH_E: rect.moveRight(x)
        else: rect.moveCenter(QPointF(x, y))
        if a.startswith("n"): rect.moveTop(y)
        elif a.startswith("s"): rect.moveBottom(y)
        return rect
    def _item_box(self, item):
        """Padded bounding box in item coordinates (False = nothing to draw). Computed once per item: items never
        change after creation, so scrolling only compares numbers instead of rebuilding fonts and metrics."""
        o, c, kind = item["opts"], item["coords"], item["kind"]
        pad = float(o.get("width", 1)) / 2 + 1
        if kind == "text":
            font, fm = _cached_font(o.get("font")); txt = str(o.get("text", ""))
            a = (o.get("anchor") or "center").lower()
            rect = self._text_rect(c[0], c[1], a, txt, fm)
            h = Qt.AlignmentFlag.AlignLeft if a in _ANCH_W else Qt.AlignmentFlag.AlignRight if a in _ANCH_E else Qt.AlignmentFlag.AlignHCenter
            item["font"], item["rect"], item["txt"], item["flags"] = font, rect, txt, h | Qt.AlignmentFlag.AlignVCenter
            box = (rect.left() - pad, rect.top() - pad, rect.right() + pad, rect.bottom() + pad)
        elif kind == "line":
            box = (min(c[0::2]) - pad, min(c[1::2]) - pad, max(c[0::2]) + pad, max(c[1::2]) + pad) if len(c) >= 2 else False
        else:
            box = (min(c[0], c[2]) - pad, min(c[1], c[3]) - pad, max(c[0], c[2]) + pad, max(c[1], c[3]) + pad)
        item["box"] = box
        return box
    def paintEvent(self, event):
        p = QPainter(self)
        drawn = 0
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing); p.fillRect(self.rect(), QColor(self.bg))
            ev = event.rect()
            vl, vr, vt, vb = ev.left() + self.xoff, ev.right() + 1 + self.xoff, ev.top(), ev.bottom() + 1  # exposed area, xoff included
            p.translate(-self.xoff, 0)
            cur_font = None
            for item in self.items:
                box = item.get("box")
                if box is None: box = self._item_box(item)
                if not box or box[2] < vl or box[0] > vr or box[3] < vt or box[1] > vb:
                    continue  # cannot touch the visible area
                drawn += 1
                o, c, kind = item["opts"], item["coords"], item["kind"]
                pen = QPen(QColor(o.get("outline") or o.get("fill") or "#d0d4dc")); pen.setWidthF(float(o.get("width", 1)))
                if o.get("dash"): pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen); p.setBrush(QBrush(QColor(o["fill"])) if o.get("fill") else Qt.BrushStyle.NoBrush)
                if kind in ("oval", "rect", "arc"):
                    r = QRectF(min(c[0], c[2]), min(c[1], c[3]), abs(c[2] - c[0]), abs(c[3] - c[1]))
                    if kind == "oval": p.drawEllipse(r)
                    elif kind == "rect": p.drawRect(r)
                    else: p.drawArc(r, int(o.get("start", 0) * 16), int(o.get("extent", 0) * 16))
                elif kind == "line":
                    pts = [QPointF(c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)]
                    for a, b in zip(pts, pts[1:]): p.drawLine(a, b)
                else:
                    if item["font"] is not cur_font:
                        cur_font = item["font"]; p.setFont(cur_font)
                    p.setPen(QColor(o.get("fill", "#d0d4dc"))); p.drawText(item["rect"], item["flags"], item["txt"])
        finally:
            self.last_paint_count = drawn  # items actually drawn in the last paint (tests)
            p.end()


class FontWidget(QFont):
    """CTkFont sizes are pixels, not points."""
    def __init__(self, family="Segoe UI", size=10, weight=None, **_):
        super().__init__(family); self.setPixelSize(max(1, int(size))); self.setBold(weight == "bold")


class AppWindowWidget(_LayoutMixin, QWidget):
    def __init__(self):
        self._app = QApplication.instance() or QApplication([])
        base = QFont("Segoe UI"); base.setPixelSize(13)  # CTk default 13 px; NOT in the stylesheet, or it would override every setFont()
        self._app.setFont(base)
        palette = self._app.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0b1020"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#d0d4dc"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#10182a"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#d0d4dc"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#182338"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#d0d4dc"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#1f6aa5"))
        self._app.setPalette(palette)
        self._app.setStyleSheet("QWidget{color:#d0d4dc} QLineEdit,QComboBox,QPlainTextEdit{background:#10182a;border:1px solid #29334a;border-radius:5px;padding:5px} QTabWidget::pane{border:1px solid #29334a} QTabBar::tab{padding:8px 14px;background:#111a2d} QTabBar::tab:selected{background:#1d2c46} QScrollBar:horizontal{height:12px} QScrollBar:vertical{width:12px}")
        super().__init__(); self._init_layout(); self._timers = {}; self._timer_ids = itertools.count(1)
    def title(self, text): self.setWindowTitle(text)
    def geometry(self, s):
        m = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)?([+-]\d+)?", s)
        if m: self.resize(int(m[1]), int(m[2]))
    def minsize(self, w, h): self.setMinimumSize(w, h)
    def iconbitmap(self, path): self.setWindowIcon(QIcon(path))
    def after(self, ms, callback):
        ident = next(self._timer_ids); timer = QTimer(self); timer.setSingleShot(True); timer.timeout.connect(callback); self._timers[ident] = timer; timer.timeout.connect(lambda: self._timers.pop(ident, None)); timer.start(ms); return ident
    def after_cancel(self, ident):
        timer = self._timers.pop(ident, None)
        if timer: timer.stop(); timer.deleteLater()


class _MessageBox:
    @staticmethod
    def showerror(title, text, parent=None): QMessageBox.critical(parent, title, text)
messagebox = _MessageBox()


def _ensure_layout(parent, kind):
    layout = parent.layout()
    if layout:
        existing = getattr(parent, "_layout_kind", None)
        if existing is None:
            existing = "grid" if isinstance(layout, QGridLayout) else "horizontal" if isinstance(layout, QHBoxLayout) else "vertical"
            parent._layout_kind = existing
        if existing != kind: raise RuntimeError(f"Cannot mix {existing} and {kind} layouts on one widget")
        return layout
    layout = QGridLayout() if kind == "grid" else QHBoxLayout() if kind == "horizontal" else QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0); parent.setLayout(layout); parent._layout_kind = kind  # Tk has no implicit gaps
    if isinstance(layout, QGridLayout):
        for col, (weight, size) in getattr(parent, "_grid_col_cfg", {}).items():
            layout.setColumnStretch(col, weight); layout.setColumnMinimumWidth(col, size)
        for row, (weight, size) in getattr(parent, "_grid_row_cfg", {}).items():
            layout.setRowStretch(row, weight); layout.setRowMinimumHeight(row, size)
    return layout


# Names used by the migrated pages.
AppWindow = AppWindowWidget
Frame = FrameWidget
Label = LabelWidget
Button = ButtonWidget
Entry = EntryWidget
TextBox = TextBoxWidget
ComboBox = ComboBoxWidget
Switch = SwitchWidget
Slider = SliderWidget
ScrollableFrame = ScrollableWidget
TabView = TabViewWidget
PageStack = PageStack
ScrollBar = ScrollBarWidget
Font = FontWidget
BoolVar = BooleanVar
