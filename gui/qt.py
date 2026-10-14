"""PySide6 widgets, layout helpers, and canvas drawing for AstroWeather pages."""
from __future__ import annotations

import itertools
import re
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QIcon, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QScrollBar,
    QSizePolicy, QSlider, QTabWidget, QVBoxLayout, QWidget, QMessageBox)
from PySide6.QtWidgets import QStackedWidget


def _font(value):
    if isinstance(value, QFont):
        return value
    if isinstance(value, (tuple, list)):
        name, size, *style = value
        result = QFont(str(name), int(size))
        result.setBold("bold" in style)
        return result
    return QFont("Segoe UI", 10)


def _margins(value):
    if isinstance(value, (tuple, list)):
        if len(value) == 2:
            return (value[0], value[1], value[0], value[1])
        if len(value) == 4:
            return tuple(value)
    return (int(value or 0),) * 4


def _alignment(anchor="center", justify=None):
    anchor = (anchor or "center").lower()
    h = Qt.AlignmentFlag.AlignLeft if anchor.endswith("w") or anchor == "w" else Qt.AlignmentFlag.AlignRight if anchor.endswith("e") or anchor == "e" else Qt.AlignmentFlag.AlignHCenter
    v = Qt.AlignmentFlag.AlignTop if anchor.startswith("n") else Qt.AlignmentFlag.AlignBottom if anchor.startswith("s") else Qt.AlignmentFlag.AlignVCenter
    if justify == "left": h = Qt.AlignmentFlag.AlignLeft
    elif justify == "right": h = Qt.AlignmentFlag.AlignRight
    return h | v


def _grid_alignment(sticky):
    if ("e" in sticky and "w" in sticky) or ("n" in sticky and "s" in sticky): return Qt.AlignmentFlag(0)
    return _alignment(sticky)


class _LayoutMixin:
    # shortcut: preserve page layout calls during the Qt port; replace with direct Qt layouts when redesigning a page.
    def _init_layout(self):
        self._layout_kind = None
        self._grid_col_cfg = {}
        self._grid_row_cfg = {}

    def _layout(self, kind):
        current = self.layout()
        if current:
            if self._layout_kind != kind:
                raise RuntimeError(f"Cannot mix {self._layout_kind} and {kind} layouts on one widget")
            return current
        current = QGridLayout() if kind == "grid" else (QHBoxLayout() if kind == "horizontal" else QVBoxLayout())
        current.setContentsMargins(0, 0, 0, 0)
        current.setSpacing(6)
        self.setLayout(current)
        self._layout_kind = kind
        return current

    def grid(self, row=0, column=0, rowspan=1, columnspan=1, sticky="", padx=0, pady=0, **_):
        parent = self.parentWidget()
        if parent is None: return
        layout = _ensure_layout(parent, "grid")
        if not isinstance(layout, QGridLayout):
            raise RuntimeError("Grid child requires a grid parent")
        if self not in [layout.itemAt(i).widget() for i in range(layout.count())]:
            layout.addWidget(self, row, column, rowspan, columnspan, _grid_alignment(sticky) if sticky else Qt.AlignmentFlag(0))
        self._apply_padding(padx, pady)
        self.show()

    def pack(self, side="top", fill="none", expand=False, anchor="", padx=0, pady=0, **_):
        parent = self.parentWidget()
        if parent is None: return
        kind = "horizontal" if side in ("left", "right") else "vertical"
        layout = _ensure_layout(parent, kind)
        if not isinstance(layout, (QHBoxLayout, QVBoxLayout)):
            raise RuntimeError("Packed child requires a box parent")
        if side in ("right", "bottom"):
            index=getattr(parent,"_side_end_index",layout.count())
            layout.insertWidget(index, self, 1 if expand else 0, _alignment(anchor) if anchor else Qt.AlignmentFlag(0))
            parent._side_end_index=index
        else:
            layout.addWidget(self, 1 if expand else 0, _alignment(anchor) if anchor else Qt.AlignmentFlag(0))
        if fill in ("x", "both"):
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding if fill == "both" else QSizePolicy.Policy.Preferred)
        elif fill == "y":
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._apply_padding(padx, pady)
        self.show()

    def _apply_padding(self, padx, pady):
        left, right = (padx, padx) if isinstance(padx, int) else (padx[0], padx[-1])
        top, bottom = (pady, pady) if isinstance(pady, int) else (pady[0], pady[-1])
        self.setContentsMargins(int(left), int(top), int(right), int(bottom))

    def pack_forget(self): self.hide()
    def grid_columnconfigure(self, column, weight=0, minsize=0, **_):
        self._grid_col_cfg[column] = (weight, minsize)
        layout = self.layout()
        if isinstance(layout, QGridLayout): layout.setColumnStretch(column, weight)
        if minsize: self.setMinimumWidth(max(self.minimumWidth(), minsize))
    def grid_rowconfigure(self, row, weight=0, minsize=0, **_):
        self._grid_row_cfg[row] = (weight, minsize)
        layout = self.layout()
        if isinstance(layout, QGridLayout): layout.setRowStretch(row, weight)
        if minsize: self.setMinimumHeight(max(self.minimumHeight(), minsize))
    def grid_propagate(self, propagate):
        if not propagate: self.setMinimumSize(self.size())
    def tkraise(self): self.raise_(); self.show()
    def winfo_children(self): return [c for c in self.children() if isinstance(c, QWidget)]
    def winfo_width(self): return self.width()
    def winfo_height(self): return self.height()
    def destroy(self):
        if self.parentWidget() and self.parentWidget().layout(): self.parentWidget().layout().removeWidget(self)
        self.setParent(None)  # immediate detach so winfo_children() reflects removal synchronously
        self.deleteLater()


class FrameWidget(_LayoutMixin, QFrame):
    def __init__(self, master=None, fg_color=None, corner_radius=0, width=0, height=0, **_):
        super().__init__(master.content if isinstance(master, ScrollableWidget) else master)
        self._init_layout()
        self.setFrameShape(QFrame.Shape.NoFrame)
        if width: self.setMinimumWidth(width)
        if height: self.setMinimumHeight(height)
        if fg_color and fg_color != "transparent":
            self.setStyleSheet(f"QFrame{{background:{fg_color};border-radius:{corner_radius}px;}}")


class LabelWidget(_LayoutMixin, QLabel):
    def __init__(self, master=None, text="", font=None, text_color=None, anchor="center", justify=None, width=0, wraplength=0, **_):
        super().__init__(str(text), master.content if isinstance(master, ScrollableWidget) else master)
        self._init_layout(); self.setFont(_font(font)); self.setAlignment(_alignment(anchor, justify)); self.setWordWrap(bool(wraplength))
        if width: self.setMinimumWidth(width)
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
        super().__init__(str(text), master.content if isinstance(master, ScrollableWidget) else master)
        self._init_layout(); self._command = command; self.clicked.connect(lambda: self._command and self._command())
        self.setFont(_font(font)); self.setEnabled(state != "disabled")
        if width: self.setMinimumWidth(width)
        if height: self.setMinimumHeight(height)
        self._anchor = anchor
        self._bg, self._fg, self._hover = fg_color, text_color or "#d0d4dc", hover_color
        self._style()
    def _style(self):
        bg=self._bg; hover=self._hover or (bg if bg and bg!="transparent" else "#232830")
        align="left" if self._anchor=="w" else "center"
        self.setStyleSheet(f"QPushButton{{background:{bg if bg and bg!='transparent' else 'transparent'};color:{self._fg};border:0;border-radius:6px;padding:5px 9px;text-align:{align}}} QPushButton:hover{{background:{hover}}}")
    def configure(self, **kwargs):
        if "text" in kwargs: self.setText(str(kwargs.pop("text")))
        if "state" in kwargs: self.setEnabled(kwargs.pop("state") != "disabled")
        if "command" in kwargs: self._command = kwargs.pop("command")
        if "fg_color" in kwargs: self._bg=kwargs.pop("fg_color")
        if "text_color" in kwargs: self._fg=kwargs.pop("text_color")
        if "hover_color" in kwargs: self._hover=kwargs.pop("hover_color")
        self._style()
        if "font" in kwargs: self.setFont(_font(kwargs.pop("font")))
    config = configure
    def cget(self, key): return self.text() if key == "text" else None


class EntryWidget(_LayoutMixin, QLineEdit):
    def __init__(self, master=None, width=0, font=None, placeholder_text=None, **_):
        super().__init__(master.content if isinstance(master, ScrollableWidget) else master); self._init_layout()
        if width: self.setMinimumWidth(width)
        if font: self.setFont(_font(font))
        if placeholder_text: self.setPlaceholderText(placeholder_text)
    def get(self): return self.text()
    def insert(self, index, text): self.setCursorPosition(min(int(index), len(self.text()))); super().insert(str(text))
    def delete(self, start, end=None):
        if end == "end" or start == 0: self.clear()
        else: self.setSelection(int(start), max(1, int(end or start)-int(start))); self.backspace()
    def bind(self, sequence, callback):
        if sequence == "<KeyRelease>": self.textChanged.connect(lambda: callback(SimpleNamespace(widget=self)))


class TextBoxWidget(_LayoutMixin, QPlainTextEdit):
    def __init__(self, master=None, height=0, font=None, fg_color=None, state="normal", wrap="word", **_):
        super().__init__(master.content if isinstance(master, ScrollableWidget) else master); self._init_layout()
        if height: self.setMinimumHeight(height)
        if font: self.setFont(_font(font))
        self.setReadOnly(state == "disabled")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap if wrap == "none" else QPlainTextEdit.LineWrapMode.WidgetWidth)
        if fg_color: self.setStyleSheet(f"background:{fg_color};color:#d0d4dc;border:0;")
    def configure(self, **kwargs):
        if "state" in kwargs: self.setReadOnly(kwargs.pop("state") == "disabled")
        if "font" in kwargs: self.setFont(_font(kwargs.pop("font")))
    config = configure
    def delete(self, *_): self.clear()
    def insert(self, index, text): self.setPlainText(str(text))
    def get(self, *_): return self.toPlainText()


class ComboBoxWidget(_LayoutMixin, QComboBox):
    def __init__(self, master=None, values=(), width=0, command=None, **_):
        super().__init__(master.content if isinstance(master, ScrollableWidget) else master); self._init_layout()
        self.addItems([str(v) for v in values]); self._command = command
        if width: self.setMinimumWidth(width)
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
        super().__init__(str(text), master.content if isinstance(master, ScrollableWidget) else master); self._init_layout()
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
        super().__init__(Qt.Orientation.Horizontal, master.content if isinstance(master, ScrollableWidget) else master); self._init_layout()
        self._lo, self._hi = float(from_), float(to); self._steps = max(1, int(number_of_steps)); self._command = command
        self.setRange(0, self._steps); self.valueChanged.connect(lambda n: command(self._lo + n * (self._hi-self._lo) / self._steps) if command else None)
        if width: self.setMinimumWidth(width)
    def set(self, value): self.setValue(round((float(value)-self._lo)/(self._hi-self._lo)*self._steps))
    def get(self): return self._lo + self.value() * (self._hi-self._lo) / self._steps


class ScrollableWidget(_LayoutMixin, QScrollArea):
    def __init__(self, master=None, fg_color=None, width=0, **_):
        super().__init__(master); self._init_layout(); self.content = QWidget(); self.content._layout_kind=None
        self.content._grid_col_cfg={}; self.content._grid_row_cfg={}
        self.setWidget(self.content); self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        if width: self.setMinimumWidth(width)
        if fg_color and fg_color != "transparent": self.content.setStyleSheet(f"background:{fg_color}")
    def grid_columnconfigure(self, column, weight=0, minsize=0, **_):
        self.content._grid_col_cfg[column]=(weight,minsize)
        layout=self.content.layout()
        if isinstance(layout,QGridLayout): layout.setColumnStretch(column,weight)
        if minsize: self.content.setMinimumWidth(minsize)
    def grid_rowconfigure(self, row, weight=0, **_):
        self.content._grid_row_cfg[row]=(weight,0)
        layout=self.content.layout()
        if isinstance(layout,QGridLayout): layout.setRowStretch(row,weight)
    def winfo_children(self): return [c for c in self.content.children() if isinstance(c, QWidget)]


class TabViewWidget(_LayoutMixin, QTabWidget):
    def __init__(self, master=None, **_): super().__init__(master.content if isinstance(master, ScrollableWidget) else master); self._init_layout(); self._tabs={}
    def add(self, name):
        page=QWidget(); page._layout_kind=None; self._tabs[name]=page; self.addTab(page,name)
    def tab(self, name): return self._tabs[name]


class PageStack(_LayoutMixin, QStackedWidget):
    def __init__(self, master=None): super().__init__(master); self._init_layout()


class ScrollBarWidget(_LayoutMixin, QScrollBar):
    def __init__(self, master=None, orientation="vertical", command=None, **_):
        super().__init__(Qt.Orientation.Horizontal if orientation == "horizontal" else Qt.Orientation.Vertical,
                         master.content if isinstance(master, ScrollableWidget) else master); self._init_layout()
        if command: self.valueChanged.connect(lambda value: command("moveto", value/max(1,self.maximum())))
    def set(self, first, last):
        first=float(first); last=float(last); self.setRange(0, 10000); self.setPageStep(max(1,int((last-first)*10000)))
        blocked=self.blockSignals(True); self.setValue(int(first*10000)); self.blockSignals(blocked)


class Canvas(_LayoutMixin, QWidget):
    _ids = itertools.count(1)
    def __init__(self, master=None, width=0, height=0, bg="#0b1020", xscrollincrement=1, **_):
        super().__init__(master.content if isinstance(master, ScrollableWidget) else master); self._init_layout()
        self.setMinimumSize(width or 120, height or 100); self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.bg=bg; self.items=[]; self.scroll_width=0; self.xoff=0; self._scroll_cb=None; self._bindings={}; self._increment=xscrollincrement
    def bind(self, sequence, callback):
        self._bindings.setdefault(sequence,[]).append(callback)
        if sequence == "<Configure>": self._fire(sequence, SimpleNamespace(width=self.width(),height=self.height()))
    def _fire(self, sequence, event):
        for callback in self._bindings.get(sequence,[]): callback(event)
    def resizeEvent(self,e): super().resizeEvent(e); self._fire("<Configure>",SimpleNamespace(width=self.width(),height=self.height()))
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            x,y=int(e.position().x())+self.xoff,int(e.position().y()); self._fire("<Button-1>",SimpleNamespace(x=x,y=y,delta=0)); self._fire("<ButtonPress-1>",SimpleNamespace(x=x,y=y,delta=0)); self._last=(x,y); e.accept()
    def mouseDoubleClickEvent(self,e): self._fire("<Double-Button-1>",SimpleNamespace(x=int(e.position().x())+self.xoff,y=int(e.position().y()),delta=0))
    def mouseMoveEvent(self,e):
        x,y=int(e.position().x())+self.xoff,int(e.position().y()); self._fire("<Motion>",SimpleNamespace(x=x,y=y,delta=0))
        if e.buttons() & Qt.MouseButton.LeftButton: self._fire("<B1-Motion>",SimpleNamespace(x=x,y=y,delta=0))
    def mouseReleaseEvent(self,e): self._fire("<ButtonRelease-1>",SimpleNamespace(x=int(e.position().x())+self.xoff,y=int(e.position().y()),delta=0))
    def wheelEvent(self,e):
        delta=e.angleDelta().y(); self._fire("<MouseWheel>",SimpleNamespace(x=int(e.position().x())+self.xoff,y=int(e.position().y()),delta=delta)); e.accept()
    def configure(self, **kwargs):
        if "scrollregion" in kwargs:
            region=kwargs["scrollregion"]; self.scroll_width=max(0,int(region[2])); self._scroll_update()
        if "xscrollcommand" in kwargs: self._scroll_cb=kwargs["xscrollcommand"]; self._scroll_update()
        if "bg" in kwargs: self.bg=kwargs["bg"]
    config=configure
    def _scroll_update(self):
        if self._scroll_cb:
            full=max(1,self.scroll_width); self._scroll_cb(self.xoff/full,min(1,(self.xoff+self.width())/full))
    def xview(self,*args):
        if not args: return (self.xoff/max(1,self.scroll_width), min(1,(self.xoff+self.width())/max(1,self.scroll_width)))
        if args[0]=="moveto": self.xoff=int(float(args[1])*self.scroll_width)
        elif args[0]=="scroll": self.xoff+=int(args[1])*self._increment
        self.xoff=max(0,min(self.xoff,max(0,self.scroll_width-self.width()))); self._scroll_update(); self.update()
    def xview_moveto(self,f): self.xview("moveto",f)
    def xview_scroll(self,n,unit): self.xview("scroll",n,unit)
    def canvasx(self,x): return x+self.xoff
    def delete(self, tag):
        self.items=[] if tag=="all" else [i for i in self.items if i["tag"]!=tag]; self.update()
    def _add(self,kind,coords,**opts):
        tag=opts.pop("tags", ""); item={"id":next(self._ids),"kind":kind,"coords":coords,"tag":tag,"opts":opts}; self.items.append(item); self.update(); return item["id"]
    def create_oval(self,*xy,**opts): return self._add("oval",xy,**opts)
    def create_rectangle(self,*xy,**opts): return self._add("rect",xy,**opts)
    def create_line(self,*xy,**opts): return self._add("line",xy,**opts)
    def create_text(self,x,y,**opts): return self._add("text",(x,y),**opts)
    def create_arc(self,*xy,**opts): return self._add("arc",xy,**opts)
    def paintEvent(self,_):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.fillRect(self.rect(),QColor(self.bg)); p.translate(-self.xoff,0)
        for item in self.items:
            o=item["opts"]; p.setFont(_font(o.get("font"))); pen=QPen(QColor(o.get("outline") or o.get("fill") or o.get("fill") or "#d0d4dc")); pen.setWidthF(float(o.get("width",1)))
            if o.get("dash"): pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen); p.setBrush(QBrush(QColor(o["fill"])) if o.get("fill") else Qt.BrushStyle.NoBrush)
            c=item["coords"]
            if item["kind"] in ("oval","rect","arc"):
                r=QRectF(min(c[0],c[2]),min(c[1],c[3]),abs(c[2]-c[0]),abs(c[3]-c[1]))
                if item["kind"]=="oval": p.drawEllipse(r)
                elif item["kind"]=="rect": p.drawRect(r)
                else: p.drawArc(r,int(o.get("start",0)*16),int(o.get("extent",0)*16))
            elif item["kind"]=="line":
                pts=[QPointF(c[i],c[i+1]) for i in range(0,len(c)-1,2)]
                for a,b in zip(pts,pts[1:]): p.drawLine(a,b)
            elif item["kind"]=="text":
                txt=str(o.get("text","")); fm=p.fontMetrics(); x,y=c; anchor=o.get("anchor","center"); rect=QRectF(x,y-fm.height()/2,max(2,fm.horizontalAdvance(txt)+4),fm.height())
                if "w" in anchor: rect.moveLeft(x)
                elif "e" in anchor: rect.moveRight(x)
                else: rect.moveCenter(QPointF(x,y))
                if anchor.startswith("n"): rect.moveTop(y)
                elif anchor.startswith("s"): rect.moveBottom(y)
                p.setPen(QColor(o.get("fill","#d0d4dc"))); p.drawText(rect,Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,txt)
        p.end()


class FontWidget(QFont):
    def __init__(self,family="Segoe UI",size=10,weight=None,**_):
        super().__init__(family,size); self.setBold(weight=="bold")


class AppWindowWidget(_LayoutMixin, QWidget):
    def __init__(self):
        self._app=QApplication.instance() or QApplication([])
        palette=self._app.palette()
        palette.setColor(QPalette.ColorRole.Window,QColor("#0b1020"))
        palette.setColor(QPalette.ColorRole.WindowText,QColor("#d0d4dc"))
        palette.setColor(QPalette.ColorRole.Base,QColor("#10182a"))
        palette.setColor(QPalette.ColorRole.Text,QColor("#d0d4dc"))
        palette.setColor(QPalette.ColorRole.Button,QColor("#182338"))
        palette.setColor(QPalette.ColorRole.ButtonText,QColor("#d0d4dc"))
        palette.setColor(QPalette.ColorRole.Highlight,QColor("#1f6aa5"))
        self._app.setPalette(palette)
        self._app.setStyleSheet("QWidget{color:#d0d4dc;font-family:'Segoe UI';font-size:13px} QLineEdit,QComboBox,QPlainTextEdit{background:#10182a;border:1px solid #29334a;border-radius:5px;padding:5px} QTabWidget::pane{border:1px solid #29334a} QTabBar::tab{padding:8px 14px;background:#111a2d} QTabBar::tab:selected{background:#1d2c46} QScrollBar:horizontal{height:12px} QScrollBar:vertical{width:12px}")
        super().__init__(); self._init_layout(); self._timers={}; self._timer_ids=itertools.count(1)
    def title(self,text): self.setWindowTitle(text)
    def geometry(self,s):
        m=re.fullmatch(r"(\d+)x(\d+)([+-]\d+)?([+-]\d+)?",s)
        if m: self.resize(int(m[1]),int(m[2]))
    def minsize(self,w,h): self.setMinimumSize(w,h)
    def iconbitmap(self,path): self.setWindowIcon(QIcon(path))
    def after(self,ms,callback):
        ident=next(self._timer_ids); timer=QTimer(self); timer.setSingleShot(True); timer.timeout.connect(callback); self._timers[ident]=timer; timer.timeout.connect(lambda:self._timers.pop(ident,None)); timer.start(ms); return ident
    def after_cancel(self,ident):
        timer=self._timers.pop(ident,None)
        if timer: timer.stop(); timer.deleteLater()


class _MessageBox:
    @staticmethod
    def showerror(title,text,parent=None): QMessageBox.critical(parent,title,text)
messagebox=_MessageBox()


def _ensure_layout(parent, kind):
    layout=parent.layout()
    if layout:
        existing=getattr(parent,"_layout_kind",None)
        if existing is None:
            existing="grid" if isinstance(layout,QGridLayout) else "horizontal" if isinstance(layout,QHBoxLayout) else "vertical"
            parent._layout_kind=existing
        if existing != kind: raise RuntimeError(f"Cannot mix {existing} and {kind} layouts on one widget")
        return layout
    layout=QGridLayout() if kind=="grid" else QHBoxLayout() if kind=="horizontal" else QVBoxLayout()
    layout.setContentsMargins(0,0,0,0); layout.setSpacing(6); parent.setLayout(layout); parent._layout_kind=kind
    if isinstance(layout,QGridLayout):
        for col,(weight,_size) in getattr(parent,"_grid_col_cfg",{}).items(): layout.setColumnStretch(col,weight)
        for row,(weight,_size) in getattr(parent,"_grid_row_cfg",{}).items(): layout.setRowStretch(row,weight)
    return layout


# Names used by the migrated pages.
AppWindow=AppWindowWidget
Frame=FrameWidget
Label=LabelWidget
Button=ButtonWidget
Entry=EntryWidget
TextBox=TextBoxWidget
ComboBox=ComboBoxWidget
Switch=SwitchWidget
Slider=SliderWidget
ScrollableFrame=ScrollableWidget
TabView=TabViewWidget
PageStack=PageStack
ScrollBar=ScrollBarWidget
Font=FontWidget
BoolVar=BooleanVar
