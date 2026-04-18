"""
gui.py
------
Desktop GUI for the QTM Inflation Dashboard.
Two tabs:
  1. Raw Data    — the five fetched FRED series, quarterly
  2. QTM Analysis — M2 growth, Real GDP growth, QTM inflation vs actual CPI, gap

Design: Bloomberg-terminal aesthetic. Dark, monospaced, amber accents.
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent  # project root, one level up from src/
sys.path.insert(0, str(ROOT))

try:
    from src.data_source import load_data, SERIES
    from src.qtm import compute as compute_qtm
except ImportError:
    from data_source import load_data, SERIES
    from qtm import compute as compute_qtm

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
BG         = "#0d0d0d"
BG2        = "#161616"
BG3        = "#1f1f1f"
BG4        = "#252525"
BORDER     = "#2e2e2e"
AMBER      = "#f0a500"
GREEN      = "#39d353"
RED        = "#ff5f5f"
BLUE       = "#4a9eff"
WHITE      = "#e8e8e8"
MUTED      = "#666666"

# Scrollbar colours
SB_TROUGH  = "#1a1a1a"
SB_THUMB   = "#3a3a3a"
SB_THUMB_H = "#555555"

MONO       = ("Courier New", 10)
MONO_SM    = ("Courier New", 9)
MONO_HD    = ("Courier New", 9, "bold")
SANS_TITLE = ("Georgia", 15, "bold")

QUARTERS     = ["Q1", "Q2", "Q3", "Q4"]
CURRENT_YEAR = datetime.now().year
YEARS        = [str(y) for y in range(1990, CURRENT_YEAR + 1)]

# Raw data tab column labels
RAW_COL_LABELS = {
    "M2SL":     "M2 Money Supply\n(Billions $)",
    "GDP":      "Nominal GDP\n(Billions $, SAAR)",
    "GDPDEF":   "GDP Deflator\n(Index 2017=100)",
    "CPIAUCSL": "CPI\n(Index 1982-84=100)",
    "GDPC1":    "Real GDP\n(Billions $, Chained 2017$)",
}

# QTM tab column labels
QTM_COLS = ["M2_growth", "RGDP_growth", "QTM_inflation", "CPI_inflation", "gap"]
QTM_COL_LABELS = {
    "M2_growth":     "M2 Growth\n(QoQ %)",
    "RGDP_growth":   "Real GDP Growth\n(QoQ %)",
    "QTM_inflation": "QTM Inflation\n(M2 - RealGDP, %)",
    "CPI_inflation": "Actual CPI\n(QoQ %)",
    "gap":           "Gap\n(QTM minus CPI, pp)",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def quarter_to_dates(start_year, start_q, end_year, end_q):
    q_start = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}
    q_end   = {"Q1": "03", "Q2": "06", "Q3": "09", "Q4": "12"}
    q_days  = {"03": "31", "06": "30", "09": "30", "12": "31"}
    start = f"{start_year}-{q_start[start_q]}-01"
    em    = q_end[end_q]
    end   = f"{end_year}-{em}-{q_days[em]}"
    return start, end


def to_quarter_label(ts):
    try:
        q = (ts.month - 1) // 3 + 1
        return f"{ts.year}-Q{q}"
    except Exception:
        return str(ts)[:7]


# ---------------------------------------------------------------------------
# Custom dark scrollbar (Canvas-based)
# ---------------------------------------------------------------------------
class DarkScrollbar(tk.Canvas):
    """
    A minimal Canvas-based scrollbar that respects the dark theme.
    Replaces ttk.Scrollbar which ignores most style overrides.
    """

    def __init__(self, parent, orient=tk.VERTICAL, command=None, **kwargs):
        self._orient  = orient
        self._command = command

        if orient == tk.VERTICAL:
            kwargs.setdefault("width", 10)
        else:
            kwargs.setdefault("height", 10)

        super().__init__(
            parent,
            bg=SB_TROUGH,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )

        self._thumb_start = 0.0
        self._thumb_end   = 1.0
        self._dragging    = False
        self._drag_offset = 0

        self.bind("<Configure>",        self._redraw)
        self.bind("<ButtonPress-1>",    self._on_press)
        self.bind("<B1-Motion>",        self._on_drag)
        self.bind("<ButtonRelease-1>",  self._on_release)
        self.bind("<Enter>",            lambda e: self._set_thumb_color(SB_THUMB_H))
        self.bind("<Leave>",            lambda e: self._set_thumb_color(SB_THUMB))

        self._thumb_id = None
        self._thumb_color = SB_THUMB

    # ---- public set / get (mirrors ttk.Scrollbar interface) ----

    def set(self, lo, hi):
        lo, hi = float(lo), float(hi)
        if lo == self._thumb_start and hi == self._thumb_end:
            return
        self._thumb_start = lo
        self._thumb_end   = hi
        self._redraw()

    def get(self):
        return self._thumb_start, self._thumb_end

    # ---- drawing ----

    def _track_size(self):
        if self._orient == tk.VERTICAL:
            return max(self.winfo_height(), 1)
        return max(self.winfo_width(), 1)

    def _thumb_coords(self):
        size = self._track_size()
        lo   = self._thumb_start * size
        hi   = self._thumb_end   * size
        if hi - lo < 20:
            mid  = (lo + hi) / 2
            lo   = max(0, mid - 10)
            hi   = min(size, lo + 20)
        return lo, hi

    def _redraw(self, _event=None):
        self.delete("thumb")
        lo, hi = self._thumb_coords()
        r = 4

        if self._orient == tk.VERTICAL:
            w = self.winfo_width() or 10
            coords = (r, lo + r, w - r, hi - r)
        else:
            h = self.winfo_height() or 10
            coords = (lo + r, r, hi - r, h - r)

        self._thumb_id = self.create_rectangle(
            *coords,
            fill=self._thumb_color,
            outline="",
            tags="thumb",
        )

    def _set_thumb_color(self, color):
        self._thumb_color = color
        if self._thumb_id:
            self.itemconfig(self._thumb_id, fill=color)

    # ---- interaction ----

    def _on_press(self, event):
        lo, hi = self._thumb_coords()
        pos = event.y if self._orient == tk.VERTICAL else event.x

        if lo <= pos <= hi:
            self._dragging    = True
            self._drag_offset = pos - lo
            self._set_thumb_color(SB_THUMB_H)
        else:
            size = self._track_size()
            frac = pos / size
            if self._command:
                if frac < self._thumb_start:
                    self._command("scroll", -1, "pages")
                else:
                    self._command("scroll",  1, "pages")

    def _on_drag(self, event):
        if not self._dragging or not self._command:
            return
        size  = self._track_size()
        pos   = event.y if self._orient == tk.VERTICAL else event.x
        frac  = (pos - self._drag_offset) / size
        frac  = max(0.0, min(frac, 1.0 - (self._thumb_end - self._thumb_start)))
        self._command("moveto", frac)

    def _on_release(self, _event):
        self._dragging = False
        self._set_thumb_color(SB_THUMB)


# ---------------------------------------------------------------------------
# Reusable Treeview builder  (uses DarkScrollbar)
# ---------------------------------------------------------------------------
def build_treeview(parent, columns, headings, col_width=160, date_width=110):
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill=tk.BOTH, expand=True)

    all_cols = ["date"] + columns
    tree = ttk.Treeview(frame, columns=all_cols, show="headings", selectmode="browse")

    tree.column("date", width=date_width, anchor=tk.CENTER, stretch=False)
    tree.heading("date", text="Quarter")

    for col in columns:
        tree.column(col, width=col_width, anchor=tk.E, stretch=True)
        tree.heading(col, text=headings.get(col, col))

    vsb = DarkScrollbar(frame, orient=tk.VERTICAL,   command=tree.yview)
    hsb = DarkScrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    vsb.pack(side=tk.RIGHT,  fill=tk.Y)
    hsb.pack(side=tk.BOTTOM, fill=tk.X)
    tree.pack(fill=tk.BOTH, expand=True)

    return tree


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class QTMDashboard(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("QTM Inflation Dashboard")
        self.geometry("1150x740")
        self.minsize(920, 600)
        self.configure(bg=BG)
        self.resizable(True, True)

        self._raw_df = None
        self._qtm_df = None
        self._fetch_thread = None

        self._build_ui()
        self._apply_styles()

    # -----------------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------------
    def _build_ui(self):
        self._build_header()
        self._build_controls()
        self._build_notebook()
        self._build_statusbar()

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG, pady=16)
        hdr.pack(fill=tk.X, padx=24)

        tk.Label(hdr, text="QTM INFLATION DASHBOARD",
                 font=SANS_TITLE, fg=AMBER, bg=BG).pack(side=tk.LEFT)
        tk.Label(hdr, text="FRED · Quarterly  |  MV = PY  |  V constant",
                 font=MONO_SM, fg=MUTED, bg=BG).pack(side=tk.LEFT, padx=(14, 0), pady=(5, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill=tk.X, padx=24)

    def _build_controls(self):
        ctrl = tk.Frame(self, bg=BG2, pady=14, padx=20)
        ctrl.pack(fill=tk.X, padx=24, pady=(10, 0))

        tk.Label(ctrl, text="START", font=MONO_SM, fg=MUTED, bg=BG2).grid(
            row=0, column=0, sticky=tk.W)
        tk.Label(ctrl, text="END", font=MONO_SM, fg=MUTED, bg=BG2).grid(
            row=0, column=3, sticky=tk.W, padx=(24, 0))

        self._start_year = self._combo(ctrl, YEARS,    "2010",            width=7)
        self._start_q    = self._combo(ctrl, QUARTERS, "Q1",              width=5)
        self._start_year.grid(row=1, column=0, padx=(0, 4))
        self._start_q.grid(   row=1, column=1, padx=(0, 8))

        self._end_year = self._combo(ctrl, YEARS,    str(CURRENT_YEAR), width=7)
        self._end_q    = self._combo(ctrl, QUARTERS, "Q4",              width=5)
        self._end_year.grid(row=1, column=3, padx=(24, 4))
        self._end_q.grid(   row=1, column=4, padx=(0, 28))

        self._btn_fetch  = self._button(ctrl, "▶  FETCH DATA", self._on_fetch, accent=True)
        self._btn_export = self._button(ctrl, "⬇  EXPORT CSV", self._on_export)

        self._btn_fetch.grid( row=1, column=5, padx=(0, 8))
        self._btn_export.grid(row=1, column=6)

        tk.Frame(self, bg=BORDER, height=1).pack(fill=tk.X, padx=24, pady=(10, 0))

    def _build_notebook(self):
        nb_frame = tk.Frame(self, bg=BG)
        nb_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=(10, 0))

        self._nb = ttk.Notebook(nb_frame)
        self._nb.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Raw Data
        tab_raw = tk.Frame(self._nb, bg=BG)
        self._nb.add(tab_raw, text="  Raw Data  ")

        raw_cols = list(SERIES.keys())
        self._tree_raw = build_treeview(tab_raw, raw_cols, RAW_COL_LABELS, col_width=170)
        self._show_placeholder(self._tree_raw, raw_cols)

        # Tab 2: QTM Analysis
        tab_qtm = tk.Frame(self._nb, bg=BG)
        self._nb.add(tab_qtm, text="  QTM Analysis  ")

        # Summary strip
        self._qtm_summary_var = tk.StringVar(value="Run a fetch to see QTM results.")
        summary_bar = tk.Frame(tab_qtm, bg=BG4, pady=8, padx=14)
        summary_bar.pack(fill=tk.X)
        tk.Label(summary_bar, textvariable=self._qtm_summary_var,
                 font=MONO_SM, fg=AMBER, bg=BG4, anchor=tk.W).pack(side=tk.LEFT)

        self._tree_qtm = build_treeview(tab_qtm, QTM_COLS, QTM_COL_LABELS, col_width=175)
        self._show_placeholder(self._tree_qtm, QTM_COLS)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=BG2, pady=7)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_var = tk.StringVar(value="Ready — select a date range and click FETCH DATA.")
        self._status_label = tk.Label(
            bar, textvariable=self._status_var,
            font=MONO_SM, fg=MUTED, bg=BG2, anchor=tk.W, padx=16)
        self._status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._rowcount_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._rowcount_var,
                 font=MONO_SM, fg=AMBER, bg=BG2, padx=16).pack(side=tk.RIGHT)

    # -----------------------------------------------------------------------
    # Styles
    # -----------------------------------------------------------------------
    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("Treeview",
            background=BG, foreground=WHITE, fieldbackground=BG,
            rowheight=26, font=MONO, borderwidth=0)
        style.configure("Treeview.Heading",
            background=BG2, foreground=AMBER,
            font=MONO_HD, relief=tk.FLAT, borderwidth=0)
        style.map("Treeview",
            background=[("selected", BG4)],
            foreground=[("selected", AMBER)])

        style.configure("TNotebook",
            background=BG, borderwidth=0, tabmargins=0)
        style.configure("TNotebook.Tab",
            background=BG2, foreground=MUTED,
            font=MONO_SM, padding=(12, 6), borderwidth=0)
        style.map("TNotebook.Tab",
            background=[("selected", BG)],
            foreground=[("selected", AMBER)])

        self.option_add("*OptionMenu*Background",       BG3)
        self.option_add("*OptionMenu*Foreground",       WHITE)
        self.option_add("*OptionMenu*activeBackground", AMBER)
        self.option_add("*OptionMenu*activeForeground", BG)
        self.option_add("*OptionMenu*Font",             MONO_SM)

    # -----------------------------------------------------------------------
    # Widget factories
    # -----------------------------------------------------------------------
    def _combo(self, parent, values, default, width=8):
        var = tk.StringVar(value=default)
        menu = tk.OptionMenu(parent, var, *values)
        menu.config(
            bg=BG3, fg=WHITE,
            activebackground=AMBER, activeforeground=BG,
            highlightbackground=BORDER, highlightthickness=1,
            relief=tk.FLAT, font=MONO_SM,
            width=width - 2, cursor="hand2",
        )
        menu["menu"].config(
            bg=BG3, fg=WHITE,
            activebackground=AMBER, activeforeground=BG,
            font=MONO_SM, relief=tk.FLAT, bd=0,
        )
        menu.var = var
        return menu

    def _button(self, parent, text, command, accent=False):
        fg  = BG    if accent else WHITE
        bg  = AMBER if accent else BG3
        abg = "#c48400" if accent else BORDER
        return tk.Button(
            parent, text=text, command=command,
            font=MONO_SM, fg=fg, bg=bg,
            activeforeground=fg, activebackground=abg,
            relief=tk.FLAT, padx=12, pady=6,
            cursor="hand2", bd=0,
        )

    # -----------------------------------------------------------------------
    # Table helpers
    # -----------------------------------------------------------------------
    def _show_placeholder(self, tree, cols):
        tree.delete(*tree.get_children())
        tree.insert("", tk.END,
                    values=["— fetch data to populate —"] + ["" for _ in cols],
                    tags=("placeholder",))
        tree.tag_configure("placeholder", foreground=MUTED)

    def _populate_raw(self, df):
        tree = self._tree_raw
        tree.delete(*tree.get_children())
        raw_cols = list(SERIES.keys())

        for i, (ts, row) in enumerate(df.iterrows()):
            vals = [to_quarter_label(ts)]
            for code in raw_cols:
                v = row.get(code)
                vals.append(f"{v:>14,.2f}" if v is not None and pd.notna(v) else "N/A")
            tag = "even" if i % 2 == 0 else "odd"
            tree.insert("", tk.END, values=vals, tags=(tag,))

        tree.tag_configure("even", background=BG)
        tree.tag_configure("odd",  background=BG3)
        children = tree.get_children()
        if children:
            tree.see(children[-1])

    def _populate_qtm(self, df):
        tree = self._tree_qtm
        tree.delete(*tree.get_children())

        for i, (ts, row) in enumerate(df.iterrows()):
            vals = [to_quarter_label(ts)]
            for col in QTM_COLS:
                v = row.get(col, float("nan"))
                if pd.notna(v):
                    vals.append(f"{v:>+8.2f} pp" if col == "gap" else f"{v:>+8.2f}%")
                else:
                    vals.append("N/A")

            base_bg = BG if i % 2 == 0 else BG3

            gap = row.get("gap", float("nan"))
            if pd.notna(gap):
                if abs(gap) < 0.5:
                    fg = GREEN
                elif abs(gap) < 1.5:
                    fg = AMBER
                else:
                    fg = RED
            else:
                fg = WHITE

            tag = f"row_{i}"
            tree.insert("", tk.END, values=vals, tags=(tag,))
            tree.tag_configure(tag, background=base_bg, foreground=fg)

        children = tree.get_children()
        if children:
            tree.see(children[-1])

        valid = df.dropna(subset=["QTM_inflation", "CPI_inflation", "gap"])
        if not valid.empty:
            avg_qtm = valid["QTM_inflation"].mean()
            avg_cpi = valid["CPI_inflation"].mean()
            avg_gap = valid["gap"].mean()
            corr    = valid["QTM_inflation"].corr(valid["CPI_inflation"])
            self._qtm_summary_var.set(
                f"Avg QTM: {avg_qtm:+.2f}%   "
                f"Avg CPI: {avg_cpi:+.2f}%   "
                f"Avg Gap: {avg_gap:+.2f} pp   "
                f"Correlation QTM vs CPI: {corr:.3f}   "
                f"({len(valid)} quarters)"
            )

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------
    def _on_fetch(self):
        if self._fetch_thread and self._fetch_thread.is_alive():
            self._set_status("⏳ Fetch already in progress…", MUTED)
            return

        try:
            start, end = quarter_to_dates(
                self._start_year.var.get(), self._start_q.var.get(),
                self._end_year.var.get(),   self._end_q.var.get(),
            )
        except Exception as exc:
            messagebox.showerror("Date Error", str(exc))
            return

        if start >= end:
            messagebox.showerror("Date Error", "Start must be before End.")
            return

        self._btn_fetch.config(state=tk.DISABLED, text="⏳  FETCHING…")
        self._set_status(f"Fetching FRED data  {start}  →  {end} …", AMBER)
        self._show_placeholder(self._tree_raw, list(SERIES.keys()))
        self._show_placeholder(self._tree_qtm, QTM_COLS)
        self._qtm_summary_var.set("Calculating…")

        def _worker():
            try:
                raw = load_data(start=start, end=end)
                qtm = compute_qtm(raw)
                self.after(0, lambda: self._on_success(raw, qtm, start, end))
            except Exception as exc:
                self.after(0, lambda: self._on_error(str(exc)))

        self._fetch_thread = threading.Thread(target=_worker, daemon=True)
        self._fetch_thread.start()

    def _on_success(self, raw, qtm, start, end):
        self._raw_df = raw
        self._qtm_df = qtm
        self._populate_raw(raw)
        self._populate_qtm(qtm)
        self._rowcount_var.set(f"{len(raw)} quarters raw  ·  {len(qtm)} QTM")
        self._set_status(
            f"✓  {start} → {end}  ·  {len(raw)} quarters fetched  ·  "
            f"QTM computed over {len(qtm)} quarters",
            GREEN,
        )
        self._btn_fetch.config(state=tk.NORMAL, text="▶  FETCH DATA")

    def _on_error(self, msg):
        self._set_status(f"✗  {msg}", RED)
        self._btn_fetch.config(state=tk.NORMAL, text="▶  FETCH DATA")
        self._qtm_summary_var.set("Error — see status bar.")
        messagebox.showerror("Error", msg)

    def _on_export(self):
        if self._raw_df is None:
            messagebox.showwarning("No Data", "Fetch data first.")
            return

        choice = _ExportDialog(self).result
        if choice is None:
            return

        df_out = self._raw_df if choice == "raw" else self._qtm_df
        if df_out is None or df_out.empty:
            messagebox.showwarning("No Data", "No data available for that tab.")
            return

        default_name = "qtm_raw_data.csv" if choice == "raw" else "qtm_analysis.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            df_out.to_csv(path)
            self._set_status(f"✓  Exported to {path}", GREEN)
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def _set_status(self, msg, color=WHITE):
        self._status_var.set(msg)
        self._status_label.config(fg=color)


# ---------------------------------------------------------------------------
# Export choice dialog
# ---------------------------------------------------------------------------
class _ExportDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("Export")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()

        tk.Label(self, text="Export which dataset?",
                 font=MONO_SM, fg=WHITE, bg=BG, pady=14, padx=20).pack()

        btn_frame = tk.Frame(self, bg=BG, pady=10, padx=20)
        btn_frame.pack()

        def pick(val):
            self.result = val
            self.destroy()

        tk.Button(btn_frame, text="Raw Data",
                  font=MONO_SM, fg=BG, bg=AMBER,
                  activebackground="#c48400", relief=tk.FLAT,
                  padx=14, pady=6, cursor="hand2",
                  command=lambda: pick("raw")).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(btn_frame, text="QTM Analysis",
                  font=MONO_SM, fg=WHITE, bg=BG3,
                  activebackground=BORDER, relief=tk.FLAT,
                  padx=14, pady=6, cursor="hand2",
                  command=lambda: pick("qtm")).pack(side=tk.LEFT)

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        self.wait_window()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run():
    app = QTMDashboard()
    app.update_idletasks()
    w, h = 1150, 740
    x = (app.winfo_screenwidth()  - w) // 2
    y = (app.winfo_screenheight() - h) // 2
    app.geometry(f"{w}x{h}+{x}+{y}")

    def _on_close():
        if messagebox.askokcancel("Quit", "Close the dashboard?"):
            app.destroy()

    app.protocol("WM_DELETE_WINDOW", _on_close)
    app.mainloop()


if __name__ == "__main__":
    run()