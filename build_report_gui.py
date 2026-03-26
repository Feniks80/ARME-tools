"""
Build Report — GUI
Graphical interface for PDF report generation.

Organization: ARME Engineers (ארמה מהנדסים)
Email: trom@arme.co.il
Engineer: Shimon Donen (שמעון דונן)

Requires: build_report.py, config.py, annotate_loading.py in the same folder.
Organization: ARME Engineers | trom@arme.co.il | Shimon Donen

Metadata embedded in generated PDFs:
    /Author   : ARME ENGINEERS / <engineer_name>
    /Creator  : build_report.py — ARME Engineers (trom@arme.co.il)
    /Producer : ARME Engineers Build Report Generator v2.0
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import re
import shutil
import threading
import io
import subprocess
import platform
from pathlib import Path
from datetime import datetime

# ── PyInstaller: resolve base path for bundled files ──────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE_DIR))

# ── Import the build engine ───────────────────────────────────────────────────
try:
    import config as cfg
except ImportError:
    try:
        root = tk.Tk(); root.withdraw()
    except Exception:
        pass
    messagebox.showerror("Error",
        "config.py not found!\nPlace it in the same folder as this program.")
    sys.exit(1)

try:
    import build_report as engine
except ImportError:
    try:
        root = tk.Tk(); root.withdraw()
    except Exception:
        pass
    messagebox.showerror("Error",
        "build_report.py not found!\nPlace it in the same folder as this program.")
    sys.exit(1)

# ── Patch LOGOS_DIR for PyInstaller if needed ─────────────────────────────────
_logos_bundled = BASE_DIR / "logos"
if _logos_bundled.exists() and not engine.LOGOS_DIR.exists():
    engine.LOGOS_DIR = _logos_bundled


# ── Fonts & Colors (matching pret_loads_gui.py style) ─────────────────────────
FONT_MONO     = ("Consolas", 10)
FONT_LABEL    = ("Segoe UI", 10)
FONT_LABEL_SM = ("Segoe UI", 9)
FONT_TITLE    = ("Segoe UI", 13, "bold")
FONT_BTN      = ("Segoe UI", 10, "bold")
FONT_ENTRY    = ("Segoe UI", 10)

C_BG        = "#1e1e2e"
C_PANEL     = "#2a2a3e"
C_BORDER    = "#44475a"
C_TEXT      = "#cdd6f4"
C_MUTED     = "#6272a4"
C_INPUT_BG  = "#181825"
C_OUTPUT_BG = "#11111b"
C_BTN       = "#89b4fa"
C_BTN_TEXT  = "#1e1e2e"
C_BTN2      = "#313244"
C_BTN2_TEXT = "#cdd6f4"
C_SUCCESS   = "#a6e3a1"
C_ACCENT    = "#cba6f7"
C_WARNING   = "#f38ba8"
C_ORANGE    = "#fab387"

# ── App metadata ──────────────────────────────────────────────────────────────
APP_VERSION  = "2.0"
APP_ORG      = "ARME Engineers"
APP_EMAIL    = "trom@arme.co.il"
APP_ENGINEER = "שמעון דונן"


# ── Utility ───────────────────────────────────────────────────────────────────

def _open_file(filepath):
    """Cross-platform open file with default application."""
    filepath = str(filepath)
    try:
        if platform.system() == "Windows":
            os.startfile(filepath)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", filepath])
        else:
            subprocess.Popen(["xdg-open", filepath])
    except Exception as e:
        messagebox.showerror("Error", f"Cannot open file:\n{e}")


def _parse_folder_name(folder_path: str):
    """
    Try to extract project number and name from folder path.
    Walks up parent folders to find 'NUMBER - NAME' pattern.

    Typical paths:
        J:\\10296 - RAMET\\2278 - קרית ביאליק\\DESIGN
        M:\\_PLATOT SELA-BEN ARI\\1380 - מפעל טרמודן\\design
        J:\\10299 - HAIFA\\26-09 - קיסריה מרלוג\\design\\+24

    Returns (project_num, project_name) or (None, None).
    """
    p = Path(folder_path).resolve()
    # Walk up through current folder and parents (up to 4 levels)
    for part in [p] + list(p.parents)[:4]:
        name = part.name
        # Skip generic folder names
        if name.lower() in ('design', 'designs', 'pdf', 'pdfs', ''):
            continue
        # Try to match "NUMBER - NAME" pattern
        m = re.match(r"([\d][\d\-]*\d?)\s+-\s+(.+)", name)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        # Try number-only folder
        m2 = re.match(r"^(\d[\d\-]*\d?)(?:\s|$)", name)
        if m2:
            return m2.group(1).strip(), ""
    return None, None


def _list_subfolders(folder: Path):
    """List subdirectories (potential floors), excluding hidden/system."""
    if not folder.is_dir():
        return []
    return sorted([d for d in folder.iterdir()
                   if d.is_dir() and not d.name.startswith(('.', '_'))])


def _count_pdfs(folder: Path) -> int:
    """Count calculation PDFs in folder (excluding report outputs)."""
    return len([p for p in folder.glob("*.pdf")
                if "Static_Calculations_Report" not in p.name
                and not p.stem.endswith("_report")])


# ══════════════════════════════════════════════════════════════════════════════
#  PROJECT INFO DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class ProjectInfoDialog(tk.Toplevel):
    """
    Modal dialog for entering project info when folder name doesn't contain it.
    Fields: project number, project name, floor/level, factory, engineer.
    """
    def __init__(self, parent, folder_name="", detected_factory="",
                 initial_num="", initial_name="", initial_floor="",
                 initial_engineer=""):
        super().__init__(parent)
        self.title("Project Info — פרטי פרויקט")
        self.configure(bg=C_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None

        self.geometry("+%d+%d" % (parent.winfo_x() + 120, parent.winfo_y() + 100))

        # ── Title ──
        tk.Label(self, text="Enter Project Details",
                 font=FONT_TITLE, bg=C_BG, fg=C_ACCENT).pack(padx=20, pady=(16, 4))
        tk.Label(self, text=f"Folder: {folder_name}",
                 font=("Segoe UI", 8), bg=C_BG, fg=C_MUTED).pack(padx=20, pady=(0, 12))

        form = tk.Frame(self, bg=C_BG)
        form.pack(padx=20, pady=(0, 10), fill="x")

        fields = [
            ("Project Number:", "proj_num",  initial_num),
            ("Project Name:",   "proj_name", initial_name),
            ("Floor / Level:",  "floor",     initial_floor),
            ("Engineer:",       "engineer",  initial_engineer or APP_ENGINEER),
        ]
        self._entries = {}
        for i, (label, key, default) in enumerate(fields):
            tk.Label(form, text=label, font=FONT_LABEL, bg=C_BG, fg=C_TEXT,
                     anchor="w", width=16).grid(row=i, column=0, sticky="w", pady=4)
            e = tk.Entry(form, font=FONT_ENTRY, bg=C_INPUT_BG, fg=C_TEXT,
                         insertbackground=C_TEXT, relief="flat", bd=4, width=30)
            e.insert(0, default)
            e.grid(row=i, column=1, sticky="ew", pady=4, padx=(4, 0))
            self._entries[key] = e

        # ── Factory selector ──
        row_f = len(fields)
        tk.Label(form, text="Factory:", font=FONT_LABEL, bg=C_BG, fg=C_TEXT,
                 anchor="w", width=16).grid(row=row_f, column=0, sticky="nw", pady=4)

        factory_names = {k: v["name"] for k, v in cfg.FACTORIES.items()}
        self._factory_var = tk.StringVar(
            value=detected_factory or list(factory_names.keys())[0])

        factory_frame = tk.Frame(form, bg=C_BG)
        factory_frame.grid(row=row_f, column=1, sticky="ew", pady=4, padx=(4, 0))
        for fk, fn in factory_names.items():
            rb = tk.Radiobutton(factory_frame, text=f"{fn} ({fk})",
                                variable=self._factory_var, value=fk,
                                font=("Segoe UI", 9), bg=C_BG, fg=C_TEXT,
                                selectcolor=C_PANEL, activebackground=C_BG,
                                activeforeground=C_ACCENT)
            rb.pack(anchor="w")

        form.columnconfigure(1, weight=1)

        # ── Buttons ──
        btn_frame = tk.Frame(self, bg=C_BG)
        btn_frame.pack(padx=20, pady=(4, 16), fill="x")

        tk.Button(btn_frame, text="OK", font=FONT_BTN,
                  bg=C_BTN, fg=C_BTN_TEXT, relief="flat", bd=0,
                  padx=24, pady=6, cursor="hand2",
                  command=self._on_ok).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="Cancel", font=FONT_BTN,
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat", bd=0,
                  padx=16, pady=6, cursor="hand2",
                  command=self._on_cancel).pack(side="left")

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())

        for key in ["proj_num", "proj_name", "floor"]:
            if not self._entries[key].get().strip():
                self._entries[key].focus_set()
                break

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window()

    def _on_ok(self):
        proj_num = self._entries["proj_num"].get().strip()
        if not proj_num:
            messagebox.showwarning("Missing data", "Project number is required.",
                                   parent=self)
            self._entries["proj_num"].focus_set()
            return
        floor = self._entries["floor"].get().strip()
        if not floor:
            messagebox.showwarning("Missing data", "Floor / level is required.",
                                   parent=self)
            self._entries["floor"].focus_set()
            return

        self.result = {
            "proj_num":  proj_num,
            "proj_name": self._entries["proj_name"].get().strip(),
            "floor":     floor,
            "engineer":  self._entries["engineer"].get().strip() or APP_ENGINEER,
            "factory":   self._factory_var.get(),
        }
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  FLOOR PICKER DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class FloorPickerDialog(tk.Toplevel):
    """Dialog to choose a subfolder (floor) when folder has subfolders."""

    def __init__(self, parent, subfolders):
        super().__init__(parent)
        self.title("Select Floor — בחר מפלס")
        self.configure(bg=C_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None

        self.geometry("+%d+%d" % (parent.winfo_x() + 150, parent.winfo_y() + 120))

        tk.Label(self, text="Select floor / level:",
                 font=FONT_TITLE, bg=C_BG, fg=C_ACCENT).pack(padx=20, pady=(16, 8))

        list_frame = tk.Frame(self, bg=C_BORDER, bd=1, relief="flat")
        list_frame.pack(padx=20, pady=(0, 8), fill="both")

        self._listbox = tk.Listbox(
            list_frame, font=FONT_MONO,
            bg=C_OUTPUT_BG, fg=C_TEXT,
            selectbackground=C_ACCENT, selectforeground=C_BTN_TEXT,
            relief="flat", bd=4, activestyle="none",
            height=min(len(subfolders) + 1, 15), width=40
        )
        self._listbox.pack(fill="both", expand=True)

        self._subfolders = subfolders
        for sf in subfolders:
            n_pdfs = _count_pdfs(sf)
            self._listbox.insert("end", f"  {sf.name:20s}  ({n_pdfs} PDF)")

        if subfolders:
            self._listbox.selection_set(0)

        btn_frame = tk.Frame(self, bg=C_BG)
        btn_frame.pack(padx=20, pady=(4, 16), fill="x")

        tk.Button(btn_frame, text="Select", font=FONT_BTN,
                  bg=C_BTN, fg=C_BTN_TEXT, relief="flat", bd=0,
                  padx=20, pady=6, cursor="hand2",
                  command=self._on_select).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="Use root folder", font=FONT_BTN,
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat", bd=0,
                  padx=12, pady=6, cursor="hand2",
                  command=self._on_root).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="Cancel", font=FONT_BTN,
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat", bd=0,
                  padx=12, pady=6, cursor="hand2",
                  command=self._on_cancel).pack(side="left")

        self._listbox.bind("<Double-1>", lambda e: self._on_select())
        self.bind("<Return>", lambda e: self._on_select())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window()

    def _on_select(self):
        sel = self._listbox.curselection()
        if sel:
            self.result = self._subfolders[sel[0]]
        self.destroy()

    def _on_root(self):
        self.result = "ROOT"
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class BuildReportApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ARME Build Report Generator")
        self.geometry("960x680")
        self.minsize(800, 520)
        self.configure(bg=C_BG)

        self._pdf_folder = tk.StringVar(value="")
        self._floor_var = tk.StringVar(value="")
        self._factory_var = tk.StringVar(value="")
        self._engineer_var = tk.StringVar(value=APP_ENGINEER)
        self._proj_num_var = tk.StringVar(value="")
        self._proj_name_var = tk.StringVar(value="")
        self._annotate_var = tk.BooleanVar(value=True)

        self._pdf_list = []
        self._last_output = None
        self._floor_folder = None

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Title bar ──
        title_frame = tk.Frame(self, bg=C_BG, pady=10)
        title_frame.pack(fill="x", padx=18)
        tk.Label(title_frame, text="Build Report Generator",
                 font=FONT_TITLE, bg=C_BG, fg=C_ACCENT).pack(side="left")
        tk.Label(title_frame, text=f"v{APP_VERSION}  |  {APP_ORG}  |  {APP_EMAIL}",
                 font=("Segoe UI", 9), bg=C_BG, fg=C_MUTED
                 ).pack(side="left", padx=(10, 0), pady=(4, 0))

        # ── Top panel: folder & project settings ──
        settings_frame = tk.Frame(self, bg=C_PANEL, bd=1, relief="flat")
        settings_frame.pack(fill="x", padx=14, pady=(0, 6))

        inner = tk.Frame(settings_frame, bg=C_PANEL, padx=10, pady=8)
        inner.pack(fill="x")

        # Row 1: PDF source folder
        r1 = tk.Frame(inner, bg=C_PANEL)
        r1.pack(fill="x", pady=2)
        tk.Label(r1, text="PDF Folder:", font=FONT_LABEL, bg=C_PANEL,
                 fg=C_MUTED, width=11, anchor="w").pack(side="left")
        tk.Entry(r1, textvariable=self._pdf_folder, font=FONT_LABEL_SM,
                 bg=C_INPUT_BG, fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", bd=3).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(r1, text="Browse...", font=("Segoe UI", 9),
                  bg=C_BTN, fg=C_BTN_TEXT, relief="flat", bd=0,
                  padx=10, pady=2, cursor="hand2",
                  command=self._browse_pdf_folder).pack(side="right")

        # Row 2: Project info display + Edit button
        r2 = tk.Frame(inner, bg=C_PANEL)
        r2.pack(fill="x", pady=2)
        tk.Label(r2, text="Project:", font=FONT_LABEL, bg=C_PANEL,
                 fg=C_MUTED, width=11, anchor="w").pack(side="left")
        self._info_label = tk.Label(r2, text="(select a folder)",
                                     font=FONT_LABEL_SM, bg=C_PANEL, fg=C_MUTED,
                                     anchor="w")
        self._info_label.pack(side="left", fill="x", expand=True)
        tk.Button(r2, text="Edit...", font=("Segoe UI", 9),
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat", bd=0,
                  padx=8, pady=2, cursor="hand2",
                  command=self._edit_project_info).pack(side="right")

        # Row 3: Floor, Factory, Engineer
        r3 = tk.Frame(inner, bg=C_PANEL)
        r3.pack(fill="x", pady=2)

        tk.Label(r3, text="Floor:", font=FONT_LABEL_SM, bg=C_PANEL,
                 fg=C_MUTED).pack(side="left")
        tk.Entry(r3, textvariable=self._floor_var, font=FONT_LABEL_SM,
                 bg=C_INPUT_BG, fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", bd=3, width=10).pack(side="left", padx=(2, 12))

        tk.Label(r3, text="Factory:", font=FONT_LABEL_SM, bg=C_PANEL,
                 fg=C_MUTED).pack(side="left")
        factory_keys = list(cfg.FACTORIES.keys())
        self._factory_combo = ttk.Combobox(r3, textvariable=self._factory_var,
                                            values=factory_keys,
                                            width=8, state="readonly")
        self._factory_combo.pack(side="left", padx=(2, 12))

        tk.Label(r3, text="Engineer:", font=FONT_LABEL_SM, bg=C_PANEL,
                 fg=C_MUTED).pack(side="left")
        tk.Entry(r3, textvariable=self._engineer_var, font=FONT_LABEL_SM,
                 bg=C_INPUT_BG, fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", bd=3, width=18).pack(side="left", padx=(2, 0))

        # Row 4: Annotate checkbox
        r4 = tk.Frame(inner, bg=C_PANEL)
        r4.pack(fill="x", pady=2)
        tk.Checkbutton(r4, text="Annotate Loading pages",
                       variable=self._annotate_var,
                       font=("Segoe UI", 9), bg=C_PANEL, fg=C_TEXT,
                       selectcolor=C_INPUT_BG, activebackground=C_PANEL,
                       activeforeground=C_ACCENT).pack(side="left")

        # ── Middle: file list + log ──
        paned = tk.PanedWindow(self, orient="horizontal", bg=C_BORDER,
                               sashwidth=4, sashrelief="flat", bd=0)
        paned.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        left = self._build_file_list(paned)
        right = self._build_log_panel(paned)
        paned.add(left, minsize=260, width=360)
        paned.add(right, minsize=320)

        # ── Bottom: action buttons ──
        btn_frame = tk.Frame(self, bg=C_BG, pady=6)
        btn_frame.pack(fill="x", padx=14)

        self._build_btn = tk.Button(
            btn_frame, text=">>  Build Report",
            font=FONT_BTN, bg=C_BTN, fg=C_BTN_TEXT,
            relief="flat", bd=0, padx=24, pady=8,
            cursor="hand2", command=self._build_report)
        self._build_btn.pack(side="left", padx=(0, 8))

        self._open_btn = tk.Button(
            btn_frame, text="Open PDF",
            font=FONT_BTN, bg=C_BTN2, fg=C_BTN2_TEXT,
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2", state="disabled",
            command=self._open_last_pdf)
        self._open_btn.pack(side="left", padx=(0, 8))

        self._saveas_btn = tk.Button(
            btn_frame, text="Save As...",
            font=FONT_BTN, bg=C_BTN2, fg=C_BTN2_TEXT,
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2", state="disabled",
            command=self._save_as)
        self._saveas_btn.pack(side="left")

        # ── Status bar ──
        self._status_label = tk.Label(
            self, text="Select a folder with PDF files to begin.",
            font=("Segoe UI", 9), bg=C_PANEL, fg=C_MUTED,
            anchor="w", padx=12, pady=4)
        self._status_label.pack(fill="x", side="bottom")

    def _build_file_list(self, parent):
        frame = tk.Frame(parent, bg=C_BG)
        hdr = tk.Frame(frame, bg=C_BG)
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        tk.Label(hdr, text="PDF FILES", font=("Segoe UI", 9, "bold"),
                 bg=C_BG, fg=C_MUTED).pack(side="left")
        self._count_label = tk.Label(hdr, text="0 files",
                                      font=("Segoe UI", 8), bg=C_BG, fg=C_MUTED)
        self._count_label.pack(side="right")

        list_frame = tk.Frame(frame, bg=C_BORDER, bd=1, relief="flat")
        list_frame.pack(fill="both", expand=True, padx=4)
        self._file_listbox = tk.Listbox(
            list_frame, font=("Consolas", 9),
            bg=C_OUTPUT_BG, fg=C_TEXT,
            selectbackground=C_ACCENT, selectforeground=C_BTN_TEXT,
            relief="flat", bd=4, activestyle="none")
        scroll_lb = ttk.Scrollbar(list_frame, orient="vertical",
                                   command=self._file_listbox.yview)
        self._file_listbox.configure(yscrollcommand=scroll_lb.set)
        scroll_lb.pack(side="right", fill="y")
        self._file_listbox.pack(fill="both", expand=True)
        return frame

    def _build_log_panel(self, parent):
        frame = tk.Frame(parent, bg=C_BG)
        hdr = tk.Frame(frame, bg=C_BG)
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        tk.Label(hdr, text="LOG", font=("Segoe UI", 9, "bold"),
                 bg=C_BG, fg=C_MUTED).pack(side="left")
        tk.Button(hdr, text="Copy log", font=("Segoe UI", 8),
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat", cursor="hand2",
                  bd=0, padx=6, pady=2,
                  command=self._copy_log).pack(side="right")

        log_frame = tk.Frame(frame, bg=C_BORDER, bd=1, relief="flat")
        log_frame.pack(fill="both", expand=True, padx=4)
        self._log_text = tk.Text(
            log_frame, font=FONT_MONO,
            bg=C_OUTPUT_BG, fg=C_TEXT,
            insertbackground=C_TEXT, relief="flat", bd=4,
            wrap="word", state="disabled")
        scroll_log = ttk.Scrollbar(log_frame, orient="vertical",
                                    command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scroll_log.set)
        scroll_log.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True)
        return frame

    # ══════════════════════════════════════════════════════════════════════════
    #  FOLDER LOADING
    # ══════════════════════════════════════════════════════════════════════════

    def _browse_pdf_folder(self):
        initial = self._pdf_folder.get()
        if not initial or not os.path.isdir(initial):
            initial = str(engine.PROJECTS_ROOT) if engine.PROJECTS_ROOT.exists() else ""
        d = filedialog.askdirectory(
            title="Select folder with PDF calculation files",
            initialdir=initial)
        if not d:
            return
        self._pdf_folder.set(os.path.normpath(d))
        self._load_folder(d)

    def _load_folder(self, folder_path):
        """Load PDFs from folder, detect project info, populate list."""
        folder = Path(folder_path).resolve()
        if not folder.is_dir():
            self._log(f"ERROR: Not a directory: {folder_path}")
            return

        # ── Check for subfolders (floors) ──
        subfolders = _list_subfolders(folder)
        pdfs_in_root = _count_pdfs(folder)
        actual_folder = folder

        if subfolders and pdfs_in_root == 0:
            self._log(f"Folder: {folder.name}")
            self._log(f"  Found {len(subfolders)} subfolders (floors), no PDFs in root.")
            dlg = FloorPickerDialog(self, subfolders)
            if dlg.result is None:
                self._log("  Cancelled.")
                return
            elif dlg.result == "ROOT":
                actual_folder = folder
            else:
                actual_folder = dlg.result
                self._floor_var.set(actual_folder.name)
                self._log(f"  Selected floor: {actual_folder.name}")
        elif subfolders and pdfs_in_root > 0:
            self._log(f"Folder: {folder.name}")
            self._log(f"  Found {pdfs_in_root} PDFs in root + {len(subfolders)} subfolders.")
            dlg = FloorPickerDialog(self, subfolders)
            if dlg.result is None:
                self._log("  Using root folder.")
            elif dlg.result == "ROOT":
                actual_folder = folder
            else:
                actual_folder = dlg.result
                self._floor_var.set(actual_folder.name)

        self._floor_folder = actual_folder

        # ── Collect PDFs ──
        pdfs = sorted(actual_folder.glob("*.pdf"), key=lambda p: p.name.lower())
        pdfs = [p for p in pdfs
                if "Static_Calculations_Report" not in p.name
                and not p.stem.endswith("_report")]
        self._pdf_list = pdfs

        self._file_listbox.delete(0, "end")
        for p in pdfs:
            self._file_listbox.insert("end", p.name)
        self._count_label.config(text=f"{len(pdfs)} files")

        # ── Detect project info ──
        proj_num, proj_name = _parse_folder_name(str(folder))

        # Auto-detect floor from actual_folder name if it looks like a floor
        if actual_folder != folder:
            floor_name = actual_folder.name
            if not self._floor_var.get():
                self._floor_var.set(floor_name)
        elif folder.name.lower() not in ('design', 'designs', 'pdf', 'pdfs'):
            # If user selected a folder whose name IS the project, floor needs manual input
            pass

        if proj_num:
            self._proj_num_var.set(proj_num)
            self._proj_name_var.set(proj_name or "")
            factory_key = cfg.detect_factory(proj_num)
            if factory_key:
                self._factory_var.set(factory_key)
            self._update_info_label()
            self._log(f"  Project: {proj_num} — {proj_name}")
            if factory_key:
                fname = cfg.FACTORIES.get(factory_key, {}).get("name", "?")
                self._log(f"  Factory auto-detected: {fname} ({factory_key})")
            self._log(f"  PDF files: {len(pdfs)}")
        else:
            self._log(f"Folder: {folder.name}")
            self._log(f"  Cannot detect project info from folder name.")
            self._log(f"  PDF files: {len(pdfs)}")
            self._show_project_dialog(folder.name)

        self._set_status(f"Loaded {len(pdfs)} PDF files from {actual_folder.name}")

    # ══════════════════════════════════════════════════════════════════════════
    #  DIALOGS
    # ══════════════════════════════════════════════════════════════════════════

    def _show_project_dialog(self, folder_name=""):
        detected = ""
        if self._proj_num_var.get():
            detected = cfg.detect_factory(self._proj_num_var.get())
        dlg = ProjectInfoDialog(
            self,
            folder_name=folder_name,
            detected_factory=self._factory_var.get() or detected,
            initial_num=self._proj_num_var.get(),
            initial_name=self._proj_name_var.get(),
            initial_floor=self._floor_var.get(),
            initial_engineer=self._engineer_var.get(),
        )
        if dlg.result:
            r = dlg.result
            self._proj_num_var.set(r["proj_num"])
            self._proj_name_var.set(r["proj_name"])
            self._floor_var.set(r["floor"])
            self._factory_var.set(r["factory"])
            self._engineer_var.set(r["engineer"])
            self._update_info_label()
            self._log(f"  Project set: {r['proj_num']} — {r['proj_name']}")
            fname = cfg.FACTORIES.get(r["factory"], {}).get("name", "?")
            self._log(f"  Factory: {fname}, Floor: {r['floor']}, Engineer: {r['engineer']}")
        else:
            self._log("  Dialog cancelled.")

    def _edit_project_info(self):
        folder_name = Path(self._pdf_folder.get()).name if self._pdf_folder.get() else ""
        self._show_project_dialog(folder_name)

    def _update_info_label(self):
        num = self._proj_num_var.get()
        name = self._proj_name_var.get()
        factory_key = self._factory_var.get()
        factory_name = cfg.FACTORIES.get(factory_key, {}).get("name", "")

        parts = []
        if num:
            parts.append(num)
        if name:
            parts.append(f"— {name}")
        if factory_name:
            parts.append(f"[{factory_name}]")

        if parts:
            self._info_label.config(text="  ".join(parts), fg=C_TEXT)
        else:
            self._info_label.config(text="(not set — click Edit)", fg=C_MUTED)

    # ══════════════════════════════════════════════════════════════════════════
    #  BUILD REPORT
    # ══════════════════════════════════════════════════════════════════════════

    def _build_report(self):
        """Validate inputs and run build_report in a background thread."""
        folder = self._pdf_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No folder", "Please select a folder with PDF files.")
            return
        if not self._pdf_list:
            messagebox.showwarning("No PDFs", "No PDF files found in the selected folder.")
            return
        proj_num = self._proj_num_var.get().strip()
        if not proj_num:
            messagebox.showwarning("Missing info",
                "Project number is required.\nOpening project details dialog.")
            self._show_project_dialog(Path(folder).name)
            return
        factory_key = self._factory_var.get().strip()
        if not factory_key or factory_key not in cfg.FACTORIES:
            messagebox.showwarning("Missing info", "Please select a factory.")
            return
        floor = self._floor_var.get().strip()
        if not floor:
            messagebox.showwarning("Missing info", "Floor / level is required.")
            return

        self._build_btn.config(state="disabled", text="...  Building")
        self._open_btn.config(state="disabled")
        self._saveas_btn.config(state="disabled")
        self._set_status("Building report...")
        self._log(f"\n{'─'*50}")
        self._log(f"Building report...")

        proj_name = self._proj_name_var.get().strip()
        engineer = self._engineer_var.get().strip() or APP_ENGINEER
        no_annotate = not self._annotate_var.get()
        floor_folder = self._floor_folder or Path(folder)

        project_folder = Path(folder)
        # Walk up parents to find the actual project folder (NUMBER - NAME)
        for candidate in [project_folder] + list(project_folder.parents)[:4]:
            if candidate.name.lower() in ('design', 'designs', 'pdf', 'pdfs', ''):
                continue
            cand_num, _ = _parse_folder_name(str(candidate))
            if cand_num and cand_num == proj_num:
                project_folder = candidate
                break

        def run():
            try:
                old_stdout = sys.stdout
                sys.stdout = log_capture = io.StringIO()

                orig_parse = engine.parse_project_folder

                def patched_parse(fp):
                    fp_name = Path(fp).name
                    m = re.match(r"([\d-]+)\s*-\s*(.+)", fp_name)
                    if m:
                        return m.group(1).strip(), m.group(2).strip()
                    return proj_num, proj_name

                engine.parse_project_folder = patched_parse

                try:
                    output_path = engine.build_report(
                        project_folder=project_folder,
                        floor_folder=floor_folder,
                        factory_key=factory_key,
                        engineer=engineer,
                        floor_name=floor,
                        no_annotate=no_annotate,
                    )
                finally:
                    engine.parse_project_folder = orig_parse

                sys.stdout = old_stdout
                log_output = log_capture.getvalue()
                self._last_output = output_path
                self.after(0, lambda: self._on_build_done(log_output, output_path))

            except SystemExit:
                sys.stdout = old_stdout
                log_output = log_capture.getvalue()
                self.after(0, lambda: self._on_build_error(
                    f"Build process exited unexpectedly.\n\n{log_output}"))
            except Exception as e:
                sys.stdout = old_stdout
                log_output = log_capture.getvalue()
                self.after(0, lambda: self._on_build_error(
                    f"{type(e).__name__}: {e}\n\n{log_output}"))

        threading.Thread(target=run, daemon=True).start()

    def _on_build_done(self, log_output, output_path):
        if log_output.strip():
            self._log(log_output.rstrip())
        self._log(f"\nReport saved: {output_path}")
        self._build_btn.config(state="normal", text=">>  Build Report")
        self._open_btn.config(state="normal")
        self._saveas_btn.config(state="normal")
        try:
            size_kb = output_path.stat().st_size // 1024
        except Exception:
            size_kb = 0
        self._set_status(f"Done!  {output_path.name}  ({size_kb} KB)", success=True)

    def _on_build_error(self, msg):
        self._log(f"\nERROR: {msg}")
        self._build_btn.config(state="normal", text=">>  Build Report")
        self._set_status("Build failed. See log for details.", warning=True)
        messagebox.showerror("Build Error", msg)

    # ══════════════════════════════════════════════════════════════════════════
    #  POST-BUILD ACTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _open_last_pdf(self):
        if self._last_output and self._last_output.exists():
            _open_file(self._last_output)
        else:
            messagebox.showinfo("No file", "No report file found.")

    def _save_as(self):
        if not self._last_output or not self._last_output.exists():
            return
        dest = filedialog.asksaveasfilename(
            title="Save Report As",
            initialfile=self._last_output.name,
            initialdir=str(self._last_output.parent),
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if dest:
            shutil.copy2(str(self._last_output), dest)
            self._log(f"Saved copy: {dest}")
            self._set_status(f"Report saved to: {Path(dest).name}", success=True)

    def _copy_log(self):
        text = self._log_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._set_status("Log copied to clipboard.")

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _log(self, text):
        self._log_text.config(state="normal")
        self._log_text.insert("end", text + "\n")
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def _set_status(self, msg, success=False, warning=False):
        color = C_SUCCESS if success else (C_WARNING if warning else C_MUTED)
        self._status_label.config(text=msg, fg=color)


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = BuildReportApp()
    app.mainloop()
