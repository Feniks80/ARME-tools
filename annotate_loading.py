"""
annotate_loading.py — auto-annotations for Loading page in PRET PDF calcs

For each PDF file:
1. Parse filename → nn, h, L, ST, DL, LL
2. Find page with "L o a d i n g" header
3. Extract top from Geometry page (pg 1)
4. Compute loads using pret_loads formulas
5. Create overlay with annotations and merge on top of page

Usage (from build_report.py):
    from annotate_loading import annotate_pdf_loading
    annotated_bytes = annotate_pdf_loading(pdf_path_or_bytes)
    # Then use annotated_bytes instead of original PDF

Filename format:
    01-40-1385+ST25 (350+500).pdf
    nn-h-L+STxx (DL+LL).pdf
"""

import io
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple

# ── Constants (from pret_loads.py) ──────────────────────────────────────────────
BAND  = 1.20   # strip width, m
RHO   = 2.50   # concrete density, t/m³
KSPR  = 0.96   # Kspr coefficient
TOP_DEFAULT = 5  # fallback top, cm

# ── Colors ─────────────────────────────────────────────────────────────────────
COLOR_BLUE = (0.10, 0.25, 0.70)   # ST annotations (left)
COLOR_RED  = (0.75, 0.10, 0.10)   # strip annotations (right)
COLOR_GRAY = (0.40, 0.40, 0.40)   # auxiliary


# ── Font with Hebrew support ─────────────────────────────────────────────────
def _setup_heb_font():
    """
    Register a TTF font with Hebrew support in ReportLab.
    Returns (font_reg, font_bold) names for setFont().
    Falls back to Helvetica if no Hebrew font found.
    """
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return "Helvetica", "Helvetica-Bold"

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
    for reg, bold in candidates:
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont("AL_F",  reg))
                if os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont("AL_FB", bold))
                    return "AL_F", "AL_FB"
                return "AL_F", "AL_F"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"

# Register on import
_HEB_FONT_REG, _HEB_FONT_BOLD = _setup_heb_font()


# ── Bidi / RTL for Hebrew ──────────────────────────────────────────────────────
try:
    from bidi.algorithm import get_display as _bidi_get_display
    def heb(text: str) -> str:
        return _bidi_get_display(str(text))
except ImportError:
    def heb(text: str) -> str:
        """Fallback without python-bidi: reverse RTL-runs manually."""
        text = str(text)
        if not any(unicodedata.bidirectional(c) in ('R', 'AL', 'AN') for c in text):
            return text
        runs, cur, cur_d = [], [], None
        for ch in text:
            bd = unicodedata.bidirectional(ch)
            d = 'rtl' if bd in ('R', 'AL', 'AN') else 'ltr' if (bd == 'L' or ch.isdigit()) else 'n'
            if d == 'n':
                cur.append(ch); continue
            if cur_d is None: cur_d = d
            if d == cur_d: cur.append(ch)
            else: runs.append((cur_d, ''.join(cur))); cur, cur_d = [ch], d
        if cur: runs.append((cur_d or 'n', ''.join(cur)))
        runs.reverse()
        return ''.join(c[::-1] if d == 'rtl' else c for d, c in runs)


# ═══════════════════════════════════════════════════════════════════════════════
#  FILENAME PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def parse_filename(filename: str) -> Optional[dict]:
    """
    Parse PDF filename and return calculation parameters.

    Supported formats:
        01-40-1385+ST25 (350+500).pdf    → with ST topping
        01-20-530 (100+250).pdf           → without ST topping
        19-A30-898+ST30 (750+500).pdf     → with letter prefix in h

    Returns dict or None if format not recognized.
    """
    stem = Path(filename).stem
    pattern = r"(\d+[A-Za-z]?)-([A-Za-z]?\d+)-(\d+)(?:\+ST(\d+))?.*?\((\d+)\+(\d+)\)"
    m = re.search(pattern, stem)
    if not m:
        return None

    nn_str, h_str, L_str, st_str, dl_str, ll_str = m.groups()

    # Remove letter prefix from h (A30 → 30)
    h_digits = re.sub(r'[A-Za-z]', '', h_str)
    h_cm  = int(h_digits)
    L_cm  = int(L_str)
    L_m   = L_cm / 100.0
    dl    = int(dl_str) / 1000.0   # kg/m² → t/m²
    ll    = int(ll_str) / 1000.0

    result = {
        "nn":   nn_str,
        "h_cm": h_cm,
        "L_m":  L_m,
        "dl":   dl,
        "ll":   ll,
        "st_cm": int(st_str) if st_str else None,
    }
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  EXTRACT top FROM GEOMETRY PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_top_from_page(page_text: str) -> Optional[int]:
    """
    Extract topping thickness (top, cm) from Geometry page text.

    PDF structure:
        Composite - service: (n=Et/Eb=0.87)
        120.  A = 1987 cm2  yt = 12. cm     ← 120 = bf (flange width)
        6.    I = 1403*10^2 cm4 yb = 14.    ← 6 = top (topping thickness)
        Composite- ult: ...

    top is the number at start of line after first "Composite",
    which contains "I =" (moment of inertia).
    """
    lines = page_text.splitlines()
    in_composite = False

    for line in lines:
        stripped = line.strip()

        if "Composite" in stripped and not in_composite:
            in_composite = True
            continue

        if in_composite:
            # Line like "6. I = 1403..." or "6.\n" standalone
            m = re.match(r'^(\d{1,2})\.?\s+I\s*=', stripped)
            if m:
                val = int(m.group(1))
                if 5 <= val <= 20:
                    return val
            # Standalone line with number only (some PDF formats)
            m2 = re.match(r'^(\d{1,2})\.?\s*$', stripped)
            if m2:
                val = int(m2.group(1))
                if 5 <= val <= 20:
                    return val
            # Stop after several lines if not found
            if "Composite" in stripped or "Precast" in stripped:
                break

    return None


def extract_top_from_pdf_bytes(pdf_bytes: bytes) -> int:
    """
    Try to extract top from first PDF page (Geometry).
    Returns top in cm or TOP_DEFAULT if failed.
    """
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return TOP_DEFAULT
            page0 = pdf.pages[0]
            text = page0.extract_text() or ""
            top = _extract_top_from_page(text)
            if top is not None:
                return top
    except Exception:
        pass
    return TOP_DEFAULT


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPUTE LOADS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_loads(dl: float, ll: float, h_cm: int, top_cm: int,
                  st_cm: Optional[int]) -> dict:
    """
    Compute loads for annotations.

    Returns dict with keys:
        sdl          - topping load on strip (t/m)
        dl_band      - dead load on strip (t/m)
        ll_band      - live load on strip (t/m)
        dl_st        - DL from ST topping (t/m) or None
        ll_st        - LL from ST topping (t/m) or None
        conc_st      - concrete weight of ST (t/m) or None
        half         - half = ST/2 (m) or None
    """
    sdl     = (top_cm / 100.0) * RHO * BAND
    dl_band = dl * BAND
    ll_band = ll * BAND

    if st_cm:
        half    = (st_cm / 100.0) / 2.0
        dl_st   = dl * half
        ll_st   = ll * half
        conc_st = half * ((h_cm + top_cm) / 100.0) * RHO
    else:
        half = dl_st = ll_st = conc_st = None

    return {
        "sdl":     sdl,
        "dl_band": dl_band,
        "ll_band": ll_band,
        "dl_st":   dl_st,
        "ll_st":   ll_st,
        "conc_st": conc_st,
        "half":    half,
    }


def _fmt(x: float) -> str:
    return f"{round(x, 3):.3f}"


def _fmtv(x: float) -> str:
    """Format value cleanly: 0.100 → '0.1', 2.500 → '2.5', 0.060 → '0.06'"""
    if x == int(x) and x >= 1:
        return str(int(x))
    s = f"{x:.4f}".rstrip('0').rstrip('.')
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  FIND LOADING PAGE AND SECTION POSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

LOADING_MARKER = "L o a d i n g"
SECTION_MARKERS = [
    "Superimposed dead load",
    "Dead load",
    "Live load",
]


def find_loading_page_and_sections(pdf_bytes: bytes) -> Optional[Tuple]:
    """
    Find Loading page and Y-coordinates of three load sections.

    Returns (page_index, sections_y, W, H) or None.
    sections_y: {"sdl": y_rl, "dl": y_rl, "ll": y_rl}
      — Y in pt from page BOTTOM (ReportLab coordinate system)
    """
    try:
        import pdfplumber
    except ImportError:
        print("⚠️  pip install pdfplumber")
        return None

    # Section headers and their keys
    SECTION_MAP = {
        "Superimposed": "sdl",   # Superimposed dead load
        "Dead":         "dl",    # Dead load
        "Live":         "ll",    # Live load
    }

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for pg_idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if LOADING_MARKER not in text:
                    continue

                W = float(page.width)
                H = float(page.height)
                words = page.extract_words(x_tolerance=3, y_tolerance=3)

                # Group words by lines (Y with 2pt tolerance)
                lines_by_y: dict = {}
                for w in words:
                    y_key = round(w["top"] / 2) * 2
                    lines_by_y.setdefault(y_key, []).append(w)

                sections_y: dict = {}
                seen_sdl = False
                loading_title_y = None  # Y of "Loading" header (ReportLab coords)

                for y_top in sorted(lines_by_y.keys()):
                    tokens = [w["text"] for w in lines_by_y[y_top]]
                    line = " ".join(tokens)

                    # "L o a d i n g" header
                    if "L" in tokens and "o" in tokens and "a" in tokens and "d" in tokens:
                        if loading_title_y is None:
                            loading_title_y = H - y_top

                    # SDL: line contains "Superimposed" and "dead"
                    if "Superimposed" in tokens and "dead" in tokens and not seen_sdl:
                        sections_y["sdl"] = H - y_top
                        seen_sdl = True

                    # Dead load: line has "Dead" and "load" but NOT "Superimposed"
                    elif ("Dead" in tokens or "dead" in tokens) and "load" in tokens \
                         and "Superimposed" not in tokens and "dl" not in sections_y:
                        sections_y["dl"] = H - y_top

                    # Live load
                    elif ("Live" in tokens or "live" in tokens) and "load" in tokens \
                         and "ll" not in sections_y:
                        sections_y["ll"] = H - y_top

                if len(sections_y) >= 3:
                    if loading_title_y is not None:
                        sections_y["_loading_title"] = loading_title_y
                        # Detect partial page: Loading starts below top 35% of page
                        # In pdfplumber coords, loading_title_y_pdf = H - loading_title_y
                        loading_title_y_pdf = H - loading_title_y
                        sections_y["_is_partial"] = (loading_title_y_pdf > H * 0.35)
                    else:
                        sections_y["_is_partial"] = False
                    return pg_idx, sections_y, W, H

    except Exception as e:
        print(f"WARNING: annotate_loading error finding Loading: {e}")

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  CREATE OVERLAY
# ═══════════════════════════════════════════════════════════════════════════════

def _make_overlay(W: float, H: float, sections_y: dict, loads: dict,
                  params: dict) -> bytes:
    """
    Create a PDF page with load annotations via ReportLab.

    Layout:
        Left  (blue)  — ST topping loads with formula breakdown
        Right (red)   — strip loads with formula breakdown

    sections_y: {"sdl": y_rl, "dl": y_rl, "ll": y_rl}
      — Y in pt from BOTTOM (ReportLab coords)
    """
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib import colors
    except ImportError:
        raise ImportError("pip install reportlab")

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(W, H))

    # Fonts
    font_lat  = "Helvetica"
    font_latB = "Helvetica-Bold"
    font_heb  = _HEB_FONT_REG
    font_hebB = _HEB_FONT_BOLD

    fsz    = 7.0   # slightly smaller — text is longer with formulas
    DY     = 22    # offset down from section header (pt) — at diagram level

    # Partial page: Loading starts mid-page (after Geometry)
    # Use more compact layout — smaller offset, skip self-weight note
    is_partial = sections_y.get("_is_partial", False)
    if is_partial:
        DY = 16   # tighter spacing for partial pages
        fsz = 6.5

    # Frame boundaries (from params or fallback)
    frame_left  = params.get("frame_left", 20.0)
    frame_right = params.get("frame_right", W - 34.0)
    X_LEFT  = frame_left + 28   # blue text: frame + 1cm right, left-aligned
    X_RIGHT = frame_right - 5   # red text: frame - 5pt, right-aligned

    Y_MIN  = 25    # min from page bottom (pt)
    Y_MAX  = H - 25  # max from page top (pt)

    col_blue = colors.Color(*COLOR_BLUE)
    col_red  = colors.Color(*COLOR_RED)

    has_st = params.get("st_cm") is not None

    # ── Extract source values for formula breakdown ──
    dl      = params.get("dl", 0)
    ll      = params.get("ll", 0)
    h_cm    = params.get("h_cm", 0)
    top_cm  = params.get("top_cm", TOP_DEFAULT)
    st_cm   = params.get("st_cm")

    top_m   = top_cm / 100.0
    h_m     = h_cm / 100.0
    st_m    = st_cm / 100.0 if st_cm else 0
    half    = st_m / 2.0 if st_cm else 0

    v = _fmtv  # short alias

    def _clamp_y(y):
        """Clamp Y within printable area."""
        return max(Y_MIN, min(y, Y_MAX))

    def rgt(text, x, y, font=font_latB, sz=fsz, color=col_red):
        """Draw right-aligned text inside frame."""
        y = _clamp_y(y)
        c.setFont(font, sz)
        c.setFillColor(color)
        # Text must not extend left of page center
        tw = c.stringWidth(text, font, sz)
        max_w = x - W * 0.45
        if tw > max_w > 0:
            sz2 = sz * max_w / tw * 0.95
            c.setFont(font, max(sz2, 5.0))
        c.drawRightString(x, y, text)

    def lft_split(heb_label, formula, x, y, color=col_blue):
        """
        Draw Hebrew label and Latin formula as separate drawString calls,
        so bidi does not break parentheses in the formula.
        Hebrew is drawn right (drawRightString from junction point),
        formula — left (drawString from junction point).
        """
        y = _clamp_y(y)
        c.setFillColor(color)
        # First formula (LTR) — drawString from X_LEFT
        c.setFont(font_latB, fsz)
        formula_w = c.stringWidth(formula, font_latB, fsz)
        # Then Hebrew label right of formula
        heb_text = heb(heb_label)
        c.setFont(font_hebB, fsz)
        heb_w = c.stringWidth(heb_text, font_hebB, fsz)
        # Check everything fits
        total_w = formula_w + heb_w + 4  # 4pt gap
        max_w = W * 0.55 - x
        scale = 1.0
        if total_w > max_w > 0:
            scale = max_w / total_w * 0.95
        sz_f = max(fsz * scale, 5.0)
        sz_h = max(fsz * scale, 5.0)
        # Draw formula (LTR, left)
        c.setFont(font_latB, sz_f)
        c.drawString(x, y, formula)
        formula_w_actual = c.stringWidth(formula, font_latB, sz_f)
        # Draw Hebrew label (RTL, after formula)
        c.setFont(font_hebB, sz_h)
        c.drawString(x + formula_w_actual + 4, y, heb_text)

    # ── Self-weight note (between "Loading" header and frame) ────────
    # Skip for partial pages — not enough space
    loading_title_y = sections_y.get("_loading_title")
    sdl_y = sections_y.get("sdl")
    if loading_title_y and sdl_y and not is_partial:
        # Position: between Loading header and first SDL section
        # Shift ~1cm right from center and ~0.5cm below midpoint
        note_y = (loading_title_y + sdl_y) / 2 - 4 - 14  # -14pt ≈ 0.5cm below
        note_x = W / 2 + 28  # +28pt ≈ 1cm right
        note_text = heb('משקל עצמי של הלוח"ד נלקח בחשבון ע"י התוכנה')
        note_sz = fsz * 2  # 2x larger
        c.setFont(font_hebB, note_sz)
        c.setFillColor(col_red)
        c.drawCentredString(note_x, note_y, note_text)

    # ── SDL section (Superimposed dead load) ───────────────────────────────────
    if "sdl" in sections_y:
        y = sections_y["sdl"] - DY
        # Right (red): top × B × ρ = breakdown = result
        rgt(f"top\u00d7B\u00d7\u03c1 = {v(top_m)}\u00d7{v(BAND)}\u00d7{v(RHO)} = {_fmt(loads['sdl'])} t/m",
            X_RIGHT, y)
        # Left (blue): ST concrete weight (h+top) × ST/2 × ρ
        if has_st and loads["conc_st"] is not None:
            lft_split(
                "השלמה - ",
                f"(h+top)\u00d7ST\u00d7\u03c1/2 = ({v(h_m)}+{v(top_m)})\u00d7{v(st_m)}\u00d7{v(RHO)}/2 = {_fmt(loads['conc_st'])} t/m",
                X_LEFT, y)

    # ── Dead load section ──────────────────────────────────────────────────────
    if "dl" in sections_y:
        y = sections_y["dl"] - DY
        # Right: DL × B = breakdown = result
        rgt(f"DL\u00d7B = {v(dl)}\u00d7{v(BAND)} = {_fmt(loads['dl_band'])} t/m",
            X_RIGHT, y)
        # Left: ST × DL / 2
        if has_st and loads["dl_st"] is not None:
            lft_split(
                "השלמה - ",
                f"ST\u00d7DL/2 = {v(st_m)}\u00d7{v(dl)}/2 = {_fmt(loads['dl_st'])} t/m",
                X_LEFT, y)

    # ── Live load section ──────────────────────────────────────────────────────
    if "ll" in sections_y:
        y = sections_y["ll"] - DY
        # Right: LL × B = breakdown = result
        rgt(f"LL\u00d7B = {v(ll)}\u00d7{v(BAND)} = {_fmt(loads['ll_band'])} t/m",
            X_RIGHT, y)
        # Left: ST × LL / 2
        if has_st and loads["ll_st"] is not None:
            lft_split(
                "השלמה - ",
                f"ST\u00d7LL/2 = {v(st_m)}\u00d7{v(ll)}/2 = {_fmt(loads['ll_st'])} t/m",
                X_LEFT, y)

    c.save()
    return buf.getvalue()


def _make_overlay_pdfplumber(pdf_bytes: bytes, pg_idx: int,
                              sections_y: dict, W: float, H: float,
                              loads: dict, params: dict) -> bytes:
    """
    More precise overlay version — uses real coordinates from pdfplumber
    to align annotations with load diagrams.
    """
    try:
        import pdfplumber
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib import colors
    except ImportError as e:
        raise ImportError(str(e))

    # Get X coordinates of load numbers for precise alignment
    load_x_positions = {}  # key → (x_left_annotation, x_right_annotation)

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[pg_idx]
            words = page.extract_words(x_tolerance=3, y_tolerance=3)

            # Find load numbers near sections
            # For each section take X coordinate of rightmost number
            section_tops = {}
            for key, y_rl in sections_y.items():
                y_pdf = H - y_rl  # back to pdfplumber coords
                section_tops[key] = y_pdf

    except Exception:
        pass

    return _make_overlay(W, H, sections_y, loads, params)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def annotate_pdf_loading(pdf_input, filename: str = "") -> bytes:
    """
    Add load annotations to the Loading page in a PDF.

    Args:
        pdf_input: file path (str/Path) or PDF content bytes
        filename:  file name (needed for parsing if pdf_input is bytes)

    Returns:
        bytes — annotated PDF (or original if annotation not applicable)
    """
    # ── Read PDF ────────────────────────────────────────────────────────────
    if isinstance(pdf_input, (str, Path)):
        path = Path(pdf_input)
        filename = filename or path.name
        with open(path, "rb") as f:
            pdf_bytes = f.read()
    else:
        pdf_bytes = bytes(pdf_input)

    # ── Parse filename ──────────────────────────────────────────────────────
    params = parse_filename(filename)
    if params is None:
        # No (DL+LL) in name — skip silently
        return pdf_bytes

    # ── Extract top ─────────────────────────────────────────────────────────
    top_cm = extract_top_from_pdf_bytes(pdf_bytes)
    params["top_cm"] = top_cm  # for formula breakdown in overlay

    # ── Compute loads ────────────────────────────────────────────────────
    loads = compute_loads(
        dl=params["dl"],
        ll=params["ll"],
        h_cm=params["h_cm"],
        top_cm=top_cm,
        st_cm=params["st_cm"],
    )

    # ── Find Loading page ─────────────────────────────────────────────────
    result = find_loading_page_and_sections(pdf_bytes)
    if result is None:
        # Loading page not found — skip silently
        return pdf_bytes

    pg_idx, sections_y, W, H = result

    if len(sections_y) < 3:
        return pdf_bytes

    # ── Determine frame boundaries on Loading page ──────────────────────────
    frame_left, frame_right = 20.0, W - 34.0  # defaults
    try:
        import pdfplumber
        from collections import Counter
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[pg_idx]
            plines = page.lines or []
            # Find horizontal lines wider than 85% of page (frame, not diagrams)
            wide = [l for l in plines if abs(l['x1'] - l['x0']) > W * 0.85]
            if wide:
                # Take most common right edge value (mode) — this is the content frame
                r_counts = Counter(round(max(l['x0'], l['x1']), 0) for l in wide)
                l_counts = Counter(round(min(l['x0'], l['x1']), 0) for l in wide)
                frame_right = r_counts.most_common(1)[0][0]
                frame_left  = l_counts.most_common(1)[0][0]
    except Exception:
        pass
    params["frame_left"]  = frame_left
    params["frame_right"] = frame_right

    # ── Create overlay ───────────────────────────────────────────────────────
    try:
        overlay_bytes = _make_overlay(W, H, sections_y, loads, params)
    except Exception as e:
        print(f"  WARNING: annotate_loading overlay error for {filename}: {e}")
        return pdf_bytes

    # ── Merge overlay on top of Loading page ────────────────────────────────
    try:
        from pypdf import PdfReader, PdfWriter
        reader  = PdfReader(io.BytesIO(pdf_bytes))
        overlay = PdfReader(io.BytesIO(overlay_bytes))
        writer  = PdfWriter()

        for i, page in enumerate(reader.pages):
            if i == pg_idx:
                page.merge_page(overlay.pages[0])
            writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    except Exception as e:
        print(f"  WARNING: annotate_loading merge error for {filename}: {e}")
        return pdf_bytes


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST
# ═══════════════════════════════════════════════════════════════════════════════

def _test_parse():
    cases = [
        ("01-40-1385+ST25 (350+500).pdf",
         {"nn": "01", "h_cm": 40, "L_m": 13.85, "dl": 0.35, "ll": 0.5, "st_cm": 25}),
        ("01-20-530 (100+250).pdf",
         {"nn": "01", "h_cm": 20, "L_m": 5.3,  "dl": 0.1,  "ll": 0.25, "st_cm": None}),
        ("03-20-810+ST40 (100+250).pdf",
         {"nn": "03", "h_cm": 20, "L_m": 8.1,  "dl": 0.1,  "ll": 0.25, "st_cm": 40}),
        ("19-A30-898+ST30",  None),  # no parentheses → None
        ("19-A30-898+ST30 (750+500).pdf",
         {"nn": "19", "h_cm": 30, "L_m": 8.98, "dl": 0.75, "ll": 0.5, "st_cm": 30}),
        # Filenames with notes (extra text between params and DL+LL)
        ("02-A50-1700 +1t.m L=5m (0+500).pdf",
         {"nn": "02", "h_cm": 50, "L_m": 17.0, "dl": 0.0, "ll": 0.5, "st_cm": None}),
        ("03-A50-1700 +2P=1t (0+500).pdf",
         {"nn": "03", "h_cm": 50, "L_m": 17.0, "dl": 0.0, "ll": 0.5, "st_cm": None}),
        ("05-30-650+ST40 extra note (1650+500).pdf",
         {"nn": "05", "h_cm": 30, "L_m": 6.5, "dl": 1.65, "ll": 0.5, "st_cm": 40}),
    ]
    ok = True
    for fname, expected in cases:
        got = parse_filename(fname)
        if expected is None:
            if got is not None:
                print(f"FAIL {fname}: expected None, got {got}"); ok=False
            continue
        if got is None:
            print(f"FAIL {fname}: got None"); ok=False; continue
        for k, v in expected.items():
            if abs((got[k] or 0) - (v or 0)) > 1e-9 if isinstance(v, float) else got[k] != v:
                print(f"FAIL {fname}[{k}]: {got[k]} != {v}"); ok=False
    if ok:
        print("OK: parse_filename all tests passed")

def _test_loads():
    # From file 01-20-530+ST80 (100+250): top=6, dl=0.1, ll=0.25, st=80
    loads = compute_loads(dl=0.1, ll=0.25, h_cm=20, top_cm=6, st_cm=80)
    assert abs(loads["sdl"]     - 0.06*2.5*1.2) < 1e-9
    assert abs(loads["dl_band"] - 0.1*1.2)      < 1e-9
    assert abs(loads["ll_band"] - 0.25*1.2)     < 1e-9
    half = 0.40
    assert abs(loads["half"]    - half)          < 1e-9
    assert abs(loads["dl_st"]   - 0.1*half)     < 1e-9
    assert abs(loads["ll_st"]   - 0.25*half)    < 1e-9
    conc = half * (20+6)/100 * 2.5
    assert abs(loads["conc_st"] - conc)          < 1e-9
    print("OK: compute_loads all tests passed")

    # Cross-check with file 19-A30-898+ST30 (top=5, dl=0.75, ll=0.5, st=30)
    loads2 = compute_loads(dl=0.75, ll=0.5, h_cm=30, top_cm=5, st_cm=30)
    assert abs(loads2["sdl"]     - 0.150) < 1e-6, f"SDL={loads2['sdl']}"
    assert abs(loads2["dl_band"] - 0.900) < 1e-6
    assert abs(loads2["ll_band"] - 0.600) < 1e-6
    assert abs(loads2["dl_st"]   - 0.1125) < 1e-6
    assert abs(loads2["ll_st"]   - 0.075)  < 1e-6
    assert abs(loads2["conc_st"] - 0.15*(30+5)/100*2.5) < 1e-6
    print("OK: compute_loads (19-A30 verify) all tests passed")


if __name__ == "__main__":
    _test_parse()
    _test_loads()

    import sys
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        print(f"\n  Annotating: {path.name}")
        result = annotate_pdf_loading(path)
        out = path.parent / (path.stem + "_annotated.pdf")
        out.write_bytes(result)
        print(f"  → {out}")
