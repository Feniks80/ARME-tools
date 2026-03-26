"""
PRET Loads Calculator — GUI
Requires: pret_loads.py in the same folder.

Organization: ARME Engineers (ארמה מהנדסים)
Email: trom@arme.co.il
Engineer: Shimon Donen (שמעון דונן)

Generated reports (.txt) contain project metadata:
    Project / Engineer / Date / Calculation parameters
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import re
import threading
import subprocess
import platform
from pathlib import Path

# ── PyInstaller: resolve base path for bundled files ──────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE_DIR))

# ── Import the calculation engine ──────────────────────────────────────────────
try:
    import pret_loads as engine
except ImportError:
    messagebox.showerror("Error", "pret_loads.py not found!\nPlace it in the same folder as this program.")
    sys.exit(1)

# ── App metadata ──────────────────────────────────────────────────────────────
APP_VERSION  = "2.1"
APP_ORG      = "ARME Engineers"
APP_EMAIL    = "trom@arme.co.il"
APP_ENGINEER = "שמעון דונן"

# ── Logo path ─────────────────────────────────────────────────────────────────
LOGOS_DIR = BASE_DIR / "logos"
if not LOGOS_DIR.exists():
    LOGOS_DIR = BASE_DIR  # fallback: logos in same folder as script
ARME_LOGO = LOGOS_DIR / "Arme.jpg"


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


# ── Fonts & Colors ─────────────────────────────────────────────────────────────
FONT_MONO   = ("Consolas", 10)
FONT_LABEL  = ("Segoe UI", 10)
FONT_TITLE  = ("Segoe UI", 13, "bold")
FONT_BTN    = ("Segoe UI", 10, "bold")

C_BG        = "#1e1e2e"   # dark background
C_PANEL     = "#2a2a3e"   # panel background
C_BORDER    = "#44475a"   # border
C_TEXT      = "#cdd6f4"   # main text
C_MUTED     = "#6272a4"   # muted text
C_INPUT_BG  = "#181825"   # input background
C_OUTPUT_BG = "#11111b"   # output background
C_BTN       = "#89b4fa"   # blue button
C_BTN_TEXT  = "#1e1e2e"
C_BTN2      = "#313244"   # secondary button
C_BTN2_TEXT = "#cdd6f4"
C_SUCCESS   = "#a6e3a1"   # green
C_ACCENT    = "#cba6f7"   # purple accent
C_WARNING   = "#f38ba8"   # red warning

EXAMPLE_INPUT = """2309 -2
100+250
20+5
L=720, 735, 575
ST40,50,60

250+500
20+5
L=7.85
ST50
"""


class PretLoadsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ARME PRET Loads Calculator")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=C_BG)

        self.save_dir = tk.StringVar(value=engine.DEFAULT_SAVE_DIR)
        self._last_saved_path = None
        self._build_ui()
        self._insert_example()

    # ── UI Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Title bar with logo ───────────────────────────────────────────────
        title_frame = tk.Frame(self, bg=C_BG, pady=12)
        title_frame.pack(fill="x", padx=18)

        # Company logo
        self._logo_image = None
        if ARME_LOGO.exists():
            try:
                from PIL import Image, ImageTk
                img = Image.open(str(ARME_LOGO))
                # Scale to ~32px height
                ratio = 32 / img.height
                img = img.resize((int(img.width * ratio), 32), Image.LANCZOS)
                self._logo_image = ImageTk.PhotoImage(img)
                tk.Label(title_frame, image=self._logo_image, bg=C_BG
                         ).pack(side="left", padx=(0, 10))
            except ImportError:
                pass  # PIL not available, skip logo

        tk.Label(title_frame, text="PRET Loads Calculator",
                 font=FONT_TITLE, bg=C_BG, fg=C_ACCENT).pack(side="left")
        tk.Label(title_frame, text=f"v{APP_VERSION}  |  {APP_ORG}  |  {APP_EMAIL}",
                 font=("Segoe UI", 9), bg=C_BG, fg=C_MUTED
                 ).pack(side="left", padx=(10, 0), pady=(4, 0))

        # ── Main paned layout ──────────────────────────────────────────────────
        paned = tk.PanedWindow(self, orient="horizontal", bg=C_BORDER,
                               sashwidth=5, sashrelief="flat", bd=0)
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        left  = self._build_left_panel(paned)
        right = self._build_right_panel(paned)
        paned.add(left,  minsize=320, width=420)
        paned.add(right, minsize=400)

        # ── Status bar ─────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready. Enter data and press Calculate.")
        status_bar = tk.Label(self, textvariable=self.status_var,
                              font=("Segoe UI", 9), bg=C_PANEL, fg=C_MUTED,
                              anchor="w", padx=12, pady=4)
        status_bar.pack(fill="x", side="bottom")

    def _build_left_panel(self, parent):
        frame = tk.Frame(parent, bg=C_BG)

        # ── Label ──
        hdr = tk.Frame(frame, bg=C_BG)
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        tk.Label(hdr, text="INPUT DATA", font=("Segoe UI", 9, "bold"),
                 bg=C_BG, fg=C_MUTED).pack(side="left")
        tk.Button(hdr, text="Load example", font=("Segoe UI", 8),
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat", cursor="hand2",
                  bd=0, padx=6, pady=2,
                  command=self._insert_example).pack(side="right")

        # ── Input text box ──
        inp_frame = tk.Frame(frame, bg=C_BORDER, bd=1, relief="flat")
        inp_frame.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        self.input_text = tk.Text(
            inp_frame, font=FONT_MONO,
            bg=C_INPUT_BG, fg=C_TEXT,
            insertbackground=C_TEXT,
            selectbackground=C_ACCENT, selectforeground=C_BTN_TEXT,
            relief="flat", bd=6, wrap="none",
            undo=True
        )
        inp_scroll_y = ttk.Scrollbar(inp_frame, orient="vertical",
                                     command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=inp_scroll_y.set)
        inp_scroll_y.pack(side="right", fill="y")
        self.input_text.pack(fill="both", expand=True)

        # ── Format hint ──
        hint = (
            "Format:\n"
            "  2309 -2        <- project + level\n"
            "  100+250        <- DL+LL (kg/m2)\n"
            "  20+5           <- h+topping (cm)\n"
            "  L=720, 735     <- lengths (cm or m)\n"
            "  ST40,50        <- topping widths (cm)"
        )
        tk.Label(frame, text=hint, font=("Consolas", 8),
                 bg=C_BG, fg=C_MUTED, justify="left", padx=6).pack(fill="x")

        # ── Save directory ──
        dir_frame = tk.Frame(frame, bg=C_BG, pady=4)
        dir_frame.pack(fill="x", padx=4)
        tk.Label(dir_frame, text="Save to:", font=FONT_LABEL,
                 bg=C_BG, fg=C_MUTED, width=8, anchor="w").pack(side="left")
        tk.Entry(dir_frame, textvariable=self.save_dir,
                 font=("Segoe UI", 9), bg=C_PANEL, fg=C_TEXT,
                 insertbackground=C_TEXT, relief="flat", bd=4).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(dir_frame, text="...", font=FONT_LABEL,
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat",
                  cursor="hand2", bd=0, padx=8, pady=2,
                  command=self._browse_dir).pack(side="right")

        # ── Buttons ──
        btn_frame = tk.Frame(frame, bg=C_BG, pady=6)
        btn_frame.pack(fill="x", padx=4)

        self.calc_btn = tk.Button(
            btn_frame, text=">>  Calculate",
            font=FONT_BTN, bg=C_BTN, fg=C_BTN_TEXT,
            relief="flat", bd=0, padx=20, pady=8,
            cursor="hand2", command=self._calculate
        )
        self.calc_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        tk.Button(
            btn_frame, text="X  Clear",
            font=FONT_BTN, bg=C_BTN2, fg=C_BTN2_TEXT,
            relief="flat", bd=0, padx=12, pady=8,
            cursor="hand2", command=self._clear
        ).pack(side="right")

        return frame

    def _build_right_panel(self, parent):
        frame = tk.Frame(parent, bg=C_BG)

        # ── Label + copy button + clear results ──
        hdr = tk.Frame(frame, bg=C_BG)
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        tk.Label(hdr, text="RESULTS", font=("Segoe UI", 9, "bold"),
                 bg=C_BG, fg=C_MUTED).pack(side="left")
        tk.Button(hdr, text="Copy all", font=("Segoe UI", 8),
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat", cursor="hand2",
                  bd=0, padx=6, pady=2,
                  command=self._copy_result).pack(side="right")
        tk.Button(hdr, text="Clear results", font=("Segoe UI", 8),
                  bg=C_BTN2, fg=C_BTN2_TEXT, relief="flat", cursor="hand2",
                  bd=0, padx=6, pady=2,
                  command=self._clear_results).pack(side="right", padx=(0, 4))

        # ── Output text box ──
        out_frame = tk.Frame(frame, bg=C_BORDER, bd=1, relief="flat")
        out_frame.pack(fill="both", expand=True, padx=4)

        self.output_text = tk.Text(
            out_frame, font=FONT_MONO,
            bg=C_OUTPUT_BG, fg=C_TEXT,
            insertbackground=C_TEXT,
            selectbackground=C_ACCENT, selectforeground=C_BTN_TEXT,
            relief="flat", bd=6, wrap="none",
            state="disabled"
        )
        out_scroll_y = ttk.Scrollbar(out_frame, orient="vertical",
                                     command=self.output_text.yview)
        out_scroll_x = ttk.Scrollbar(out_frame, orient="horizontal",
                                     command=self.output_text.xview)
        self.output_text.configure(yscrollcommand=out_scroll_y.set,
                                   xscrollcommand=out_scroll_x.set)
        out_scroll_y.pack(side="right", fill="y")
        out_scroll_x.pack(side="bottom", fill="x")
        self.output_text.pack(fill="both", expand=True)

        # ── Save + Open report buttons ──
        btn_row = tk.Frame(frame, bg=C_BG)
        btn_row.pack(fill="x", padx=4, pady=6)

        self.save_btn = tk.Button(
            btn_row, text="Save Report (EN .txt)",
            font=FONT_BTN, bg=C_BTN2, fg=C_BTN2_TEXT,
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2", state="disabled",
            command=self._save_report
        )
        self.save_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.open_btn = tk.Button(
            btn_row, text="Open Report",
            font=FONT_BTN, bg=C_BTN2, fg=C_BTN2_TEXT,
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2", state="disabled",
            command=self._open_last_report
        )
        self.open_btn.pack(side="right", fill="x", expand=True)

        return frame

    # ── Actions ───────────────────────────────────────────────────────────────

    def _insert_example(self):
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", EXAMPLE_INPUT.strip())

    def _clear(self):
        self.input_text.delete("1.0", "end")
        self._clear_results()
        self._set_status("Cleared.")

    def _clear_results(self):
        """Clear the results panel only."""
        self._set_output("", disabled=True)
        self.save_btn.config(state="disabled")
        self.open_btn.config(state="disabled")
        self._set_status("Results cleared.")

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.save_dir.get())
        if d:
            self.save_dir.set(os.path.normpath(d))

    def _calculate(self):
        text = self.input_text.get("1.0", "end").strip()
        if not text:
            self._set_status("Input is empty.", warning=True)
            return

        self.calc_btn.config(state="disabled", text="...  Calculating")
        self._set_status("Calculating...")

        def run():
            try:
                projects = engine.parse_text(text)
                if not projects:
                    self.after(0, lambda: self._show_input_error(
                        "No projects found.\n\nPlease enter data correctly.\n"
                        "First line must be a project number (e.g. '2309 -2')."
                    ))
                    return

                # Validate all slabs
                all_errors = []
                for proj_id, mark, slabs in projects:
                    errors = engine._validate_slabs(slabs)
                    if errors:
                        all_errors.extend(errors)

                if all_errors:
                    err_msg = "Please enter data correctly:\n\n"
                    for e in all_errors:
                        err_msg += f"  - {e}\n"
                    self.after(0, lambda: self._show_input_error(err_msg))
                    return

                lines = []
                for proj_id, mark, slabs in projects:
                    lines.append(engine.format_output_gui(proj_id, mark, slabs))
                result = "\n".join(lines)

                self._last_text    = text
                self._last_projects = projects

                self.after(0, lambda: self._show_result(result, len(projects)))
            except Exception as e:
                self.after(0, lambda: self._show_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _show_result(self, result: str, n_projects: int):
        self._set_output(result, disabled=False)
        self.save_btn.config(state="normal")
        # Enable Open only if a file was previously saved
        if self._last_saved_path and os.path.exists(self._last_saved_path):
            self.open_btn.config(state="normal")
        self.calc_btn.config(state="normal", text=">>  Calculate")
        self._set_status(
            f"Done - {n_projects} project(s) calculated. "
            "Press Save Report to write .txt file.",
            success=True
        )

    def _show_input_error(self, msg: str):
        """Show input validation error as a popup + in output."""
        messagebox.showwarning("Input Error", msg)
        self._set_output(f"INPUT ERROR:\n{msg}", disabled=False)
        self.calc_btn.config(state="normal", text=">>  Calculate")
        self._set_status("Input error. Please fix and try again.", warning=True)

    def _show_error(self, msg: str):
        self._set_output(f"ERROR:\n{msg}", disabled=False)
        self.calc_btn.config(state="normal", text=">>  Calculate")
        self._set_status(f"Error: {msg}", warning=True)

    def _save_report(self):
        if not hasattr(self, "_last_projects"):
            return

        save_dir = self.save_dir.get().strip()
        if not save_dir:
            messagebox.showwarning("No folder", "Please specify a save folder.")
            return

        try:
            os.makedirs(save_dir, exist_ok=True)
            saved = []
            last_path = None
            for proj_id, mark, slabs in self._last_projects:
                engine._save_project(proj_id, mark, slabs, self._last_text, save_dir)
                name = f"{proj_id} {mark}".strip() if mark else proj_id
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', name)
                last_path = os.path.join(save_dir, f"{safe_name}_EN.txt")
                saved.append(name)

            self._last_saved_path = last_path
            self.open_btn.config(state="normal")

            msg = f"Saved {len(saved)} project(s) to:\n{save_dir}\n\n" + \
                  "\n".join(f"  {n}_EN.txt" for n in saved)
            messagebox.showinfo("Saved", msg)
            self._set_status(f"Files saved to {save_dir}", success=True)
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            self._set_status(f"Save error: {e}", warning=True)

    def _open_last_report(self):
        """Open the last saved report file with system default application."""
        if self._last_saved_path and os.path.exists(self._last_saved_path):
            _open_file(self._last_saved_path)
        else:
            messagebox.showinfo("No file", "No saved report found.\nSave a report first.")

    def _copy_result(self):
        text = self.output_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._set_status("Results copied to clipboard.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_output(self, text: str, disabled=True):
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        if text:
            self.output_text.insert("1.0", text)
        if disabled:
            self.output_text.config(state="disabled")

    def _set_status(self, msg: str, success=False, warning=False):
        self.status_var.set(msg)
        color = C_SUCCESS if success else (C_WARNING if warning else C_MUTED)
        for w in self.pack_slaves():
            if isinstance(w, tk.Label):
                w.config(fg=color)


if __name__ == "__main__":
    app = PretLoadsApp()
    app.mainloop()
