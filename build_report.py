#!/usr/bin/env python3
"""
build_report.py — PDF report generator for prestressed slab calculations.

Organization: ARME Engineers (ארמה מהנדסים)
Email: trom@arme.co.il
Engineer: Shimon Donen (שמעון דונן)

Usage:
  python build_report.py 1382                     # → interactive floor selection
  python build_report.py 1382 --floor "+14"        # → specific floor
  python build_report.py 26-09 --floor "+14"       # → Haifa project
  python build_report.py                           # → list all projects
"""

import argparse, io, os, sys, re, unicodedata
from pathlib import Path
from datetime import date

# ── Dependencies ──────────────────────────────────────────────────────────────
try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (
        ArrayObject, DictionaryObject, FloatObject,
        NameObject, NumberObject,
    )
except ImportError:
    print("ERROR: pip install pypdf"); sys.exit(1)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as rl_canvas
except ImportError:
    print("ERROR: pip install reportlab"); sys.exit(1)

# ── Config ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
try:
    import config as cfg
except ImportError:
    print("ERROR: config.py not found next to script"); sys.exit(1)

LOGOS_DIR = SCRIPT_DIR / "logos"
PROJECTS_ROOT = Path(getattr(cfg, 'PROJECTS_ROOT', SCRIPT_DIR))

# ── Loading annotations ────────────────────────────────────────────────────────
try:
    from annotate_loading import annotate_pdf_loading
    HAS_ANNOTATE = True
except ImportError:
    print("WARNING: annotate_loading.py not found — Loading annotations will be skipped")
    HAS_ANNOTATE = False

# ── Bidi (RTL) ─────────────────────────────────────────────────────────────────────
try:
    from bidi.algorithm import get_display
    def heb(text):
        return get_display(str(text))
except ImportError:
    print("WARNING: python-bidi not installed — Hebrew text may appear mirrored.")
    print("    pip install python-bidi")
    def heb(text):
        # Simple fallback: reverse RTL runs
        text = str(text)
        if not any(unicodedata.bidirectional(c) in ('R', 'AL', 'AN') for c in text):
            return text
        runs = []
        cur, cur_d = [], None
        for ch in text:
            bd = unicodedata.bidirectional(ch)
            d = 'rtl' if bd in ('R','AL','AN') else 'ltr' if bd == 'L' or ch.isdigit() else 'n'
            if d == 'n':
                cur.append(ch); continue
            if cur_d is None: cur_d = d
            if d == cur_d: cur.append(ch)
            else: runs.append((cur_d, ''.join(cur))); cur, cur_d = [ch], d
        if cur: runs.append((cur_d or 'n', ''.join(cur)))
        runs.reverse()
        return ''.join(c[::-1] if d=='rtl' else c for d,c in runs)

# ── Fonts ───────────────────────────────────────────────────────────────────
def _setup_fonts():
    candidates = [
        ("C:/Windows/Fonts/arial.ttf",   "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/david.ttf",   "C:/Windows/Fonts/davidbd.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for d in [LOGOS_DIR, SCRIPT_DIR]:
        if d.exists():
            for ttf in sorted(d.glob("*.ttf")):
                bold = str(ttf).replace("Regular","Bold").replace("Sans.","Sans-Bold.")
                candidates.append((str(ttf), bold))
    for reg, bold in candidates:
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont("F", reg))
                if os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont("FB", bold))
                    return "F", "FB"
                return "F", "F"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"

FN, FB = _setup_fonts()

# ── Utilities ──────────────────────────────────────────────────────────────────
def accent():
    r,g,b = cfg.ACCENT_COLOR
    return colors.Color(r,g,b)

def parse_project_folder(folder_path):
    """Parse folder name: '1382 - אולם אירועים' → ('1382', 'אולם אירועים')"""
    name = Path(folder_path).name
    m = re.match(r"([\d-]+)\s*-\s*(.+)", name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", name

def find_project_folder(project_id):
    """Find project folder by number (name prefix)."""
    if not PROJECTS_ROOT.exists():
        print(f"ERROR: Projects folder not found: {PROJECTS_ROOT}")
        sys.exit(1)
    matches = []
    for d in PROJECTS_ROOT.iterdir():
        if d.is_dir() and d.name.startswith(project_id):
            # check that after number comes " - " or end
            rest = d.name[len(project_id):]
            if not rest or rest.startswith(" -") or rest.startswith("-"):
                matches.append(d)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"\n  Multiple projects found for {project_id}:")
        for i, m in enumerate(matches, 1):
            print(f"    {i}. {m.name}")
        choice = input(f"  Choose (1-{len(matches)}): ").strip()
        try:
            return matches[int(choice)-1]
        except (ValueError, IndexError):
            print("ERROR: Invalid choice"); sys.exit(1)
    return None

def list_projects():
    """Print list of all projects."""
    if not PROJECTS_ROOT.exists():
        print(f"ERROR: Projects folder not found: {PROJECTS_ROOT}")
        return
    dirs = sorted([d for d in PROJECTS_ROOT.iterdir() if d.is_dir()
                   and not d.name.startswith(('.', '_'))
                   and d.name != 'logos'])
    if not dirs:
        print("  No project folders found.")
        return
    print(f"\n  Projects in {PROJECTS_ROOT}:\n")
    for d in dirs:
        num, name = parse_project_folder(d)
        factory_key = cfg.detect_factory(num) if num else ""
        factory_name = cfg.FACTORIES.get(factory_key, {}).get('name', '?')
        # count subfolders (floors)
        floors = [f for f in d.iterdir() if f.is_dir() and not f.name.startswith('.')]
        # count pdfs directly
        pdfs = list(d.glob("*.pdf"))
        if floors:
            print(f"    {num:10s}  {name:40s}  [{factory_name}]  {len(floors)} floors")
        elif pdfs:
            print(f"    {num:10s}  {name:40s}  [{factory_name}]  {len(pdfs)} PDF")
        else:
            print(f"    {num:10s}  {name:40s}  [{factory_name}]")

def list_floors(project_folder):
    """Return list of floor subfolders. None if PDFs are in root."""
    subs = sorted([d for d in project_folder.iterdir()
                   if d.is_dir() and not d.name.startswith(('.', '_'))])
    if subs:
        return subs
    return None

def collect_pdfs(folder, exclude_name=""):
    pdfs = sorted(Path(folder).glob("*.pdf"), key=lambda p: p.name.lower())
    # Exclude output reports
    pdfs = [p for p in pdfs if "Static_Calculations_Report" not in p.name
            and not p.stem.endswith("_report")]
    if exclude_name:
        pdfs = [p for p in pdfs if p.name.lower() != exclude_name.lower()]
    return pdfs

def calc_name_from_file(path):
    return Path(path).stem

HE_MONTHS = {
    1:"ינואר",2:"פברואר",3:"מרץ",4:"אפריל",
    5:"מאי",6:"יוני",7:"יולי",8:"אוגוסט",
    9:"ספטמבר",10:"אוקטובר",11:"נובמבר",12:"דצמבר",
}

def date_he(d=None):
    d = d or date.today()
    return f"{d.day} {HE_MONTHS[d.month]} {d.year}"


# ═════════════════════════════════════════════════════════════════════════════
#  TITLE PAGE
# ═════════════════════════════════════════════════════════════════════════════
def make_title_page(project_num, project_name, floor, factory_cfg,
                    calc_names, calc_start_pages, engineer):
    buf = io.BytesIO()
    W, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)
    acc = accent()
    mx = 40

    # Logos
    logo_y, logo_h, logo_w = H-80, 55, 160
    arme_logo = LOGOS_DIR / cfg.ORG_LOGO
    if arme_logo.exists():
        try: c.drawImage(str(arme_logo), mx, logo_y, width=logo_w, height=logo_h,
                         preserveAspectRatio=True, anchor='sw', mask='auto')
        except Exception as e: print(f"  WARNING: ARME logo: {e}")
    factory_logo = LOGOS_DIR / factory_cfg.get("logo","")
    if factory_logo.exists():
        try: c.drawImage(str(factory_logo), W-mx-logo_w, logo_y, width=logo_w, height=logo_h,
                         preserveAspectRatio=True, anchor='se', mask='auto')
        except Exception as e: print(f"  WARNING: Factory logo: {e}")

    c.setStrokeColor(colors.HexColor("#dddddd")); c.setLineWidth(0.5)
    c.line(mx, logo_y-10, W-mx, logo_y-10)

    # Title
    title_y = H - 200
    c.setFont(FB, 30); c.setFillColor(acc)
    title_text = heb('דו"ח חישובים סטטיים')
    c.drawCentredString(W/2, title_y, title_text)
    tw = c.stringWidth(title_text, FB, 30)
    c.setStrokeColor(acc); c.setLineWidth(2)
    c.line(W/2 - tw/2, title_y-8, W/2 + tw/2, title_y-8)

    # Date
    c.setFont(FN, 12); c.setFillColor(colors.HexColor("#555555"))
    c.drawCentredString(W/2, title_y-40, heb(f"תאריך : {date_he()}"))

    # Metadata
    meta_right = W - mx - 10
    meta_y = title_y - 95
    line_h = 28
    meta_items = [
        ("מספר פרויקט", project_num),
        ("שם פרויקט", project_name),
        ("שם תוכנית", f"מפלס {floor}"),
        ("חישובים", factory_cfg.get("calc_type", "")),
        ("תכנן", engineer),
        ("דוא\"ל", factory_cfg.get('email', getattr(cfg, 'DEFAULT_EMAIL', ''))),
    ]
    for i, (label, value) in enumerate(meta_items):
        y = meta_y - i * line_h
        c.setFont(FB, 12); c.setFillColor(acc)
        label_vis = heb(label)
        c.drawRightString(meta_right, y, label_vis)
        label_w = c.stringWidth(label_vis, FB, 12)
        c.setFont(FN, 12); c.setFillColor(colors.HexColor("#333333"))
        c.drawRightString(meta_right - label_w - 12, y, heb(str(value)))
        c.drawRightString(meta_right - label_w - 4, y, ":")

    # Table of contents
    toc_top = meta_y - len(meta_items)*line_h - 30
    c.setFont(FB, 15); c.setFillColor(acc)
    c.drawRightString(meta_right, toc_top, heb(": תוכן"))
    c.setStrokeColor(acc); c.setLineWidth(1.5)
    c.line(mx+30, toc_top-8, meta_right, toc_top-8)

    toc_regions = []

    # Dynamic font size based on number of calculations
    if len(calc_names) <= 12:
        font_sz, entry_h = 11, 26
    elif len(calc_names) <= 20:
        font_sz, entry_h = 10, 22
    elif len(calc_names) <= 30:
        font_sz, entry_h = 9, 18
    else:
        font_sz, entry_h = 8, 16

    entry_y = toc_top - 30
    page_bottom = 50  # min from page bottom
    current_page = 0

    for idx, (name, pg) in enumerate(zip(calc_names, calc_start_pages)):
        y = entry_y - (idx - current_page * 0) * 0  # recalc below

        # Check if fits on current page
        y = entry_y
        if y < page_bottom:
            # New page
            c.showPage()
            entry_y = H - 60
            y = entry_y
            # Continuation title
            c.setFont(FB, 12); c.setFillColor(acc)
            c.drawRightString(meta_right, H - 40, heb("תוכן - המשך"))
            c.setStrokeColor(acc); c.setLineWidth(1)
            c.line(mx+30, H - 48, meta_right, H - 48)

        # Page number (left)
        c.setFont(FB, font_sz); c.setFillColor(colors.HexColor("#555555"))
        pg_text = str(pg)
        c.drawString(mx+40, y, pg_text)

        # Calc name (right, blue bold = link)
        c.setFont(FB, font_sz); c.setFillColor(acc)
        c.drawRightString(meta_right, y, name)

        # Dot leaders
        pg_w = c.stringWidth(pg_text, FB, font_sz)
        name_w = c.stringWidth(name, FB, font_sz)
        dots_x0 = mx+40+pg_w+8
        dots_x1 = meta_right - name_w - 8
        if dots_x1 > dots_x0:
            c.setFont(FN, font_sz); c.setFillColor(colors.HexColor("#cccccc"))
            dot_str = " . " * 60
            c.drawString(dots_x0, y, dot_str[:int((dots_x1-dots_x0)/3.0)])

        # Thin separator line
        c.setStrokeColor(colors.HexColor("#eeeeee")); c.setLineWidth(0.3)
        c.line(mx+35, y-6, meta_right, y-6)

        # Clickable link region
        toc_regions.append({
            "rect": (mx+30, y-6, meta_right+5, y + font_sz + 2),
            "target_page": pg-1,
            "toc_page": c.getPageNumber() - 1,  # which title page this link is on
        })
        entry_y -= entry_h

    c.save()
    return buf.getvalue(), toc_regions


# ═════════════════════════════════════════════════════════════════════════════
#  LEGEND PAGE (filename decoding + parameters)
# ═════════════════════════════════════════════════════════════════════════════
def _find_example_with_st(calc_names):
    """Find first filename with +ST in calc list (for legend example)."""
    for name in calc_names:
        if "+ST" in name or "_ST" in name:
            return name
    return calc_names[0] if calc_names else "01-40-1385+ST25 (350+500)"


def make_legend_page(calc_names, factory_cfg=None):
    """
    Creates a legend page with:
    1. ARME + factory logos (top)
    2. Filename decoding diagram (Hebrew, RTL)
    3. Calculation parameters (B, ρ, Kspr)
    """
    buf = io.BytesIO()
    W, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)
    acc = accent()
    mx = 40

    # ── Logos (same as title page) ───────────────────────────────
    logo_y, logo_h, logo_w = H-80, 55, 160
    arme_logo = LOGOS_DIR / cfg.ORG_LOGO
    if arme_logo.exists():
        try: c.drawImage(str(arme_logo), mx, logo_y, width=logo_w, height=logo_h,
                         preserveAspectRatio=True, anchor='sw', mask='auto')
        except Exception as e: print(f"  WARNING: ARME logo: {e}")
    if factory_cfg:
        factory_logo = LOGOS_DIR / factory_cfg.get("logo","")
        if factory_logo.exists():
            try: c.drawImage(str(factory_logo), W-mx-logo_w, logo_y, width=logo_w, height=logo_h,
                             preserveAspectRatio=True, anchor='se', mask='auto')
            except Exception as e: print(f"  WARNING: Factory logo: {e}")

    c.setStrokeColor(colors.HexColor("#dddddd")); c.setLineWidth(0.5)
    c.line(mx, logo_y-10, W-mx, logo_y-10)

    # ── Title ──────────────────────────────────────────────────────────
    top_y = logo_y - 30
    c.setFont(FB, 14); c.setFillColor(acc)
    title_txt = heb("שם הקובץ מכיל את כל הפרמטרים לחישוב העומסים:")
    c.drawCentredString(W/2, top_y, title_txt)

    # ── Choose example with ST ──────────────────────────────────────────────
    example_name = _find_example_with_st(calc_names)

    # ── Draw filename large ───────────────────────────────────────────
    file_y = top_y - 45
    c.setFont(FB, 13); c.setFillColor(colors.HexColor("#222222"))
    example_display = f"{example_name}.pdf"
    # Draw left (LTR), leaving space for lines on right
    file_x = mx + 30
    c.drawString(file_x, file_y, example_display)
    file_w = c.stringWidth(example_display, FB, 13)

    # ── Parse name for decoding ────────────────────────────────────────
    clean = example_name.replace("_ST", "+ST")
    clean = re.sub(r'__(\d+)_(\d+)_$', r' (\1+\2)', clean)
    clean = re.sub(r'__(\d+)_(\d+)_', r' (\1+\2)', clean)
    pat = r"(\d+[A-Za-z]?)-([A-Za-z]?\d+)-(\d+)(?:\+ST(\d+))?\s*\((\d+)\+(\d+)\)"
    m = re.search(pat, clean)

    if m:
        nn_s, h_s, L_s, st_s, dl_s, ll_s = m.groups()
        h_digits = re.sub(r'[A-Za-z]', '', h_s)
        L_cm = int(L_s)
        L_m = L_cm / 100.0
    else:
        nn_s, h_digits, L_s, st_s, dl_s, ll_s = "01", "40", "1385", "25", "350", "500"
        L_cm = 1385
        L_m = 13.85

    # ── Compute X positions of each component in filename string ────────
    # Format: nn-h-L+STxx (DL+LL).pdf
    # Compute char positions for drawing lines
    parts_text = example_display
    font_name, font_sz_file = FB, 13

    def _char_x(substr_end_idx):
        """X coordinate of substring end in filename."""
        return file_x + c.stringWidth(parts_text[:substr_end_idx], font_name, font_sz_file)

    # Find indices of key components in string
    # nn: first digits before first '-'
    idx_nn_end = parts_text.index('-')
    # h: between first and second '-'
    idx_h_start = idx_nn_end + 1
    idx_h_end = parts_text.index('-', idx_h_start)
    # L: between second '-' and '+ST' or ' ('
    idx_L_start = idx_h_end + 1
    st_pos = parts_text.find('+ST')
    paren_pos = parts_text.find('(')
    if st_pos > 0:
        idx_L_end = st_pos
    elif paren_pos > 0:
        idx_L_end = paren_pos
    else:
        idx_L_end = idx_L_start + len(L_s)
    # ST: from '+ST' to ' (' or '('
    idx_ST_start = st_pos if st_pos >= 0 else -1
    idx_ST_end = paren_pos if paren_pos > 0 else -1
    # DL+LL: inside parentheses
    if paren_pos >= 0:
        plus_in_paren = parts_text.index('+', paren_pos)
        close_paren = parts_text.index(')')
        idx_DL_start = paren_pos + 1
        idx_DL_end = plus_in_paren
        idx_LL_start = plus_in_paren + 1
        idx_LL_end = close_paren
    else:
        idx_DL_start = idx_DL_end = idx_LL_start = idx_LL_end = 0

    # X coordinates of each component center
    x_nn = (_char_x(0) + _char_x(idx_nn_end)) / 2
    x_h  = (_char_x(idx_h_start) + _char_x(idx_h_end)) / 2
    x_L  = (_char_x(idx_L_start) + _char_x(idx_L_end)) / 2
    x_DL = (_char_x(idx_DL_start) + _char_x(idx_DL_end)) / 2
    x_LL = (_char_x(idx_LL_start) + _char_x(idx_LL_end)) / 2
    x_ST = (_char_x(idx_ST_start) + _char_x(idx_ST_end)) / 2 if idx_ST_start >= 0 else 0

    # ── Descriptions (bottom → top, as in diagram) ─────────────────────────
    descriptions = []
    descriptions.append(("LL",  x_LL, heb(f'עומס שימושי = {ll_s} ק"ג/מ"ר')))
    descriptions.append(("DL",  x_DL, heb(f'עומס קבוע = {dl_s} ק"ג/מ"ר')))
    if st_s:
        half_val = int(st_s) / 100 / 2
        descriptions.append(("ST", x_ST, heb(f'רוחב השלמה = {st_s} ס"מ ,  half = {half_val:.3f} מ\'')))
    descriptions.append(("L",   x_L,  heb(f'אורך לוח"ד = {L_s} ס"מ \u2192 {L_m:.2f} מ\'')))
    descriptions.append(("h",   x_h,  heb(f'עובי לוח"ד = {h_digits} ס"מ')))
    descriptions.append(("nn",  x_nn, heb(f"מספר סידורי")))

    desc_y_start = file_y - 35
    line_h = 26
    line_color = colors.Color(0.75, 0.10, 0.10)  # red like lines
    label_color = acc
    desc_color = colors.HexColor("#444444")
    text_x = file_x + file_w + 20  # description text starts right of filename

    for i, (key, x_comp, desc_text) in enumerate(descriptions):
        y = desc_y_start - i * line_h

        # Vertical line from filename down to this row
        c.setStrokeColor(line_color)
        c.setLineWidth(0.8)
        c.setDash(6, 3)  # dashed
        c.line(x_comp, file_y - 5, x_comp, y + 10)  # vertical
        c.line(x_comp, y + 10, text_x - 8, y + 10)  # horizontal to text
        c.setDash()  # reset dash

        # Dot at end
        c.setFillColor(line_color)
        c.circle(text_x - 8, y + 10, 2, fill=1, stroke=0)

        # Key (bold, blue) + description
        c.setFont(FB, 10); c.setFillColor(label_color)
        c.drawString(text_x, y + 5, f"{key}  =  ")
        key_w = c.stringWidth(f"{key}  =  ", FB, 10)

        c.setFont(FN, 9); c.setFillColor(desc_color)
        c.drawString(text_x + key_w, y + 5, desc_text)

    # ── Separator ───────────────────────────────────────────────────────
    sep_y = desc_y_start - len(descriptions) * line_h - 15
    c.setStrokeColor(colors.HexColor("#cccccc")); c.setLineWidth(0.5)
    c.line(mx + 40, sep_y, W - mx - 40, sep_y)

    # ── Calculation parameters ─────────────────────────────────────────────────
    labels_x = W - mx - 10  # right edge for parameters
    value_color = colors.HexColor("#333333")
    params_y = sep_y - 30
    c.setFont(FB, 14); c.setFillColor(acc)
    c.drawCentredString(W/2, params_y, heb("פרמטרי חישוב"))

    # RTL layout: description (Hebrew) right → dash → symbol = value left
    # (sym, value_str, hebrew_description)
    params_data = [
        ("B",     "1.20 m",          heb('רוחב לוח"ד')),
        ("\u03c1",  "2.50 t/m\u00b3",  heb("צפיפות בטון")),
        ("top",   "",                 heb("עובי של טופינג")),
    ]

    param_y = params_y - 35
    param_line_h = 30
    for i, (sym, val, desc) in enumerate(params_data):
        y = param_y - i * param_line_h

        # Hebrew description (right, gray)
        c.setFont(FN, 10); c.setFillColor(colors.HexColor("#555555"))
        c.drawRightString(labels_x, y, desc)
        desc_w = c.stringWidth(desc, FN, 10)

        # Dash separator
        dash_x = labels_x - desc_w - 10
        c.setFont(FN, 10); c.setFillColor(colors.HexColor("#555555"))
        c.drawRightString(dash_x, y, "-")
        dash_w = c.stringWidth("-", FN, 10)

        # Symbol (bold, blue) + value
        sym_x = dash_x - dash_w - 8
        if val:
            # "B = 1.20 m" or "ρ = 2.50 t/m³"
            sym_val_text = f"{sym} = {val}"
            c.setFont(FB, 12); c.setFillColor(label_color)
            c.drawRightString(sym_x, y, sym_val_text)
        else:
            # Symbol only (no value — like top)
            c.setFont(FB, 12); c.setFillColor(label_color)
            c.drawRightString(sym_x, y, sym)

    c.save()
    return buf.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE NUMBERS / LINKS
# ═════════════════════════════════════════════════════════════════════════════
def make_page_numbers(total, skip_first=True):
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    for i in range(total):
        if not (skip_first and i == 0):
            c.setFont(FN, 8); c.setFillColor(colors.HexColor("#888888"))
            c.drawCentredString(A4[0]/2, 7*mm, f"{i+1} / {total}")
        c.showPage()
    c.save()
    return buf.getvalue()

def add_toc_links(writer, page_index, toc_regions):
    page = writer.pages[page_index]
    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()
    for region in toc_regions:
        r, tp = region["rect"], region["target_page"]
        if tp < 0 or tp >= len(writer.pages): continue
        link = DictionaryObject()
        link[NameObject("/Type")]    = NameObject("/Annot")
        link[NameObject("/Subtype")] = NameObject("/Link")
        link[NameObject("/Rect")]    = ArrayObject([FloatObject(r[0]),FloatObject(r[1]),FloatObject(r[2]),FloatObject(r[3])])
        link[NameObject("/Border")]  = ArrayObject([NumberObject(0),NumberObject(0),NumberObject(0)])
        link[NameObject("/Dest")]    = ArrayObject([writer.pages[tp].indirect_reference, NameObject("/Fit")])
        page[NameObject("/Annots")].append(writer._add_object(link))


# ═════════════════════════════════════════════════════════════════════════════
#  ASSEMBLY
# ═════════════════════════════════════════════════════════════════════════════
def build_report(project_folder, floor_folder, factory_key, engineer=None, output=None, no_nums=False, floor_name=None, no_annotate=False):
    project_folder = Path(project_folder).resolve()
    project_num, project_name = parse_project_folder(project_folder)
    floor_folder = Path(floor_folder).resolve()
    if floor_name is None:
        floor_name = floor_folder.name  # "+14", "גג", etc.

    if factory_key not in cfg.FACTORIES:
        raise ValueError(f"Factory '{factory_key}' not found")
    factory = cfg.FACTORIES[factory_key]
    engineer = engineer or cfg.DEFAULT_ENGINEER
    output_name = output or f"{project_num}_{floor_name}_Static_Calculations_Report.pdf"
    output_path = floor_folder / output_name

    pdfs = collect_pdfs(floor_folder, output_name)
    if not pdfs:
        raise FileNotFoundError(f"No PDF files in {floor_folder}")
    calc_names = [calc_name_from_file(p) for p in pdfs]

    print(f"\n{'═'*60}")
    print(f"  📐  Project : {project_num} — {project_name}")
    print(f"  📍  Floor   : {floor_name}")
    print(f"  🏭  Factory : {factory['name']}")
    print(f"  👷  Engineer: {engineer}")
    print(f"  📄  Files   : {len(pdfs)}")
    print(f"{'═'*60}\n")

    readers, pages_per = [], []
    annotated_count = 0
    for p in pdfs:
        try:
            # Annotate Loading page (if annotate_loading available)
            if HAS_ANNOTATE and not no_annotate:
                pdf_bytes = annotate_pdf_loading(p, filename=p.name)
                r = PdfReader(io.BytesIO(pdf_bytes))
                # Check if annotation was applied (size changed)
                if len(pdf_bytes) != p.stat().st_size:
                    annotated_count += 1
            else:
                r = PdfReader(str(p))
            readers.append(r); pages_per.append(len(r.pages))
        except Exception as e:
            raise RuntimeError(f"Error reading {p.name}: {e}") from e

    if HAS_ANNOTATE and not no_annotate:
        print(f"  📝  Loading annotations: {annotated_count}/{len(pdfs)} files")

    calc_start = []
    # First pass: generate title to know how many title pages there are
    print("  ⚙️   Title page...")
    # Generate legend page
    legend_bytes = make_legend_page(calc_names, factory_cfg=factory)
    legend_reader = PdfReader(io.BytesIO(legend_bytes))
    n_legend_pages = len(legend_reader.pages)  # always 1

    # Temporary calc_start assuming 1 title page + legend (will recalc)
    tmp_start = []; cur = 2 + n_legend_pages
    for n in pages_per:
        tmp_start.append(cur); cur += n

    title_bytes, toc_regions = make_title_page(
        project_num, project_name, floor_name, factory, calc_names, tmp_start, engineer)
    title_reader = PdfReader(io.BytesIO(title_bytes))
    n_title_pages = len(title_reader.pages)

    # Recalculate start pages if title has more than 1 page
    n_front_pages = n_title_pages + n_legend_pages
    if n_title_pages > 1:
        calc_start = []; cur = n_front_pages + 1
        for n in pages_per:
            calc_start.append(cur); cur += n
        # Regenerate title with correct page numbers
        title_bytes, toc_regions = make_title_page(
            project_num, project_name, floor_name, factory, calc_names, calc_start, engineer)
        title_reader = PdfReader(io.BytesIO(title_bytes))
        print(f"  📄  Title: {n_title_pages} pg + legend: {n_legend_pages} pg")
    else:
        calc_start = tmp_start

    total_pages = n_front_pages + sum(pages_per)

    print(f"  {'File':45s}  {'Pgs':>4}  {'Start':>6}")
    print(f"  {'─'*45}  {'─'*4}  {'─'*6}")
    for name, n, s in zip(calc_names, pages_per, calc_start):
        print(f"  {name:45s}  {n:4d}  pg.{s}")
    print(f"\n  Total: {total_pages} pages\n")

    writer = PdfWriter()
    # Add all title pages
    for tp in title_reader.pages:
        writer.add_page(tp)
    # Add legend page(s)
    for lp in legend_reader.pages:
        writer.add_page(lp)
    # Add all calculation pages
    for reader in readers:
        for page in reader.pages:
            writer.add_page(page)
    assert len(writer.pages) == total_pages

    if not no_nums:
        print(f"  ⚙️   Page numbers ({total_pages} pg)...")
        num_bytes = make_page_numbers(total_pages, skip_first=True)
        num_reader = PdfReader(io.BytesIO(num_bytes))
        for i in range(total_pages):
            writer.pages[i].merge_page(num_reader.pages[i])

    print("  ⚙️   Links & bookmarks...")
    # Add clickable links on each title page
    for region in toc_regions:
        toc_pg = region.get("toc_page", 0)
        tp = region["target_page"]
        if tp < 0 or tp >= len(writer.pages): continue
        page = writer.pages[toc_pg]
        if "/Annots" not in page:
            page[NameObject("/Annots")] = ArrayObject()
        r = region["rect"]
        link = DictionaryObject()
        link[NameObject("/Type")]    = NameObject("/Annot")
        link[NameObject("/Subtype")] = NameObject("/Link")
        link[NameObject("/Rect")]    = ArrayObject([FloatObject(r[0]),FloatObject(r[1]),FloatObject(r[2]),FloatObject(r[3])])
        link[NameObject("/Border")]  = ArrayObject([NumberObject(0),NumberObject(0),NumberObject(0)])
        link[NameObject("/Dest")]    = ArrayObject([writer.pages[tp].indirect_reference, NameObject("/Fit")])
        page[NameObject("/Annots")].append(writer._add_object(link))

    for name, sp in zip(calc_names, calc_start):
        writer.add_outline_item(name, sp-1)

    writer.add_metadata({
        "/Title": f"{project_num} - {project_name} - {floor_name}",
        "/Author": f"{cfg.ORG_NAME} / {engineer}",
        "/Subject": factory['name'],
        "/Creator": f"build_report.py — {cfg.ORG_NAME} ({factory.get('email', getattr(cfg, 'DEFAULT_EMAIL', ''))})",
        "/Producer": f"{cfg.ORG_NAME} Build Report Generator v2.0",
    })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)
    size_kb = output_path.stat().st_size // 1024
    print(f"\n  🎉  Done!  {total_pages} pg → {output_path}  ({size_kb} KB)\n")
    return output_path


# ═════════════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════════════
def main():
    p = argparse.ArgumentParser(
        description="PDF report generator — ARME Engineers",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("project", nargs="?", help="Project number (1382, 26-09, ...)")
    p.add_argument("--floor",    "-f", help="Floor (subfolder name)")
    p.add_argument("--factory",  "-F", help="Factory key (auto if omitted)")
    p.add_argument("--engineer", "-e", help=f"Engineer (default: {cfg.DEFAULT_ENGINEER})")
    p.add_argument("--output",   "-o", help="Output filename")
    p.add_argument("--no-page-numbers", action="store_true")
    p.add_argument("--no-annotate", action="store_true", help="Skip Loading annotations")
    p.add_argument("--all-floors", action="store_true", help="Build report for each floor")
    args = p.parse_args()

    # ── Project selection ────────────────────────────────────────────────────
    if not args.project:
        list_projects()
        args.project = input("\n  Project number: ").strip()
        if not args.project:
            p.error("Project number required")

    project_folder = find_project_folder(args.project)
    if not project_folder:
        print(f"ERROR: Project '{args.project}' not found in {PROJECTS_ROOT}")
        list_projects()
        sys.exit(1)

    project_num, project_name = parse_project_folder(project_folder)
    print(f"\n  📂  {project_folder.name}")

    # ── Auto-detect factory ─────────────────────────────────────────────────
    if not args.factory:
        args.factory = cfg.detect_factory(project_num)
        if args.factory:
            print(f"  🏭  Factory: {args.factory} ({cfg.FACTORIES[args.factory]['name']})")
        else:
            print("  Available factories:")
            for k, v in cfg.FACTORIES.items():
                print(f"    {k:12s}  {v['name']}")
            args.factory = input("  Factory: ").strip()
            if not args.factory:
                p.error("Factory is required")

    # ── Floor selection ────────────────────────────────────────────────────
    floors = list_floors(project_folder)

    if floors:
        # Has subfolders = floors
        if args.all_floors:
            # Build for each floor
            for ff in floors:
                pdfs = collect_pdfs(ff)
                if pdfs:
                    build_report(project_folder, ff, args.factory, args.engineer,
                                 args.output, args.no_page_numbers,
                                 no_annotate=args.no_annotate)
                else:
                    print(f"  WARNING: No PDF in {ff.name}, skipping")
            return

        if args.floor:
            # Find subfolder by name
            match = [f for f in floors if f.name == args.floor]
            if not match:
                match = [f for f in floors if args.floor in f.name]
            if match:
                floor_folder = match[0]
            else:
                print(f"  ERROR: Floor '{args.floor}' not found")
                print(f"  Available: {', '.join(f.name for f in floors)}")
                sys.exit(1)
        else:
            print(f"\n  Floors:")
            for i, f in enumerate(floors, 1):
                n_pdfs = len(collect_pdfs(f))
                print(f"    {i}. {f.name:15s}  ({n_pdfs} PDF)")
            print(f"    *  All floors")
            choice = input(f"\n  Choose (1-{len(floors)} or *): ").strip()
            if choice == '*':
                for ff in floors:
                    pdfs = collect_pdfs(ff)
                    if pdfs:
                        build_report(project_folder, ff, args.factory, args.engineer,
                                     args.output, args.no_page_numbers,
                                     no_annotate=args.no_annotate)
                return
            try:
                floor_folder = floors[int(choice)-1]
            except (ValueError, IndexError):
                print("ERROR: Invalid choice"); sys.exit(1)
    else:
        # PDFs are in project root (no subfolders)
        floor_folder = project_folder
        if not args.floor:
            args.floor = input("  Floor / level: ").strip()
            if not args.floor:
                p.error("Floor is required")

    build_report(project_folder, floor_folder, args.factory, args.engineer,
                 args.output, args.no_page_numbers,
                 floor_name=args.floor if not floors else None,
                 no_annotate=args.no_annotate)


if __name__ == "__main__":
    main()
