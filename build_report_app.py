"""
build_report_app.py — ARME Engineers | Build Report Generator (Streamlit web app)
trom@arme.co.il | Shimon Donen

Streamlit Cloud web interface for building PDF reports from prestressed slab calculations.
Combines build_report.py + annotate_loading.py into a single web workflow.

Run:
    streamlit run build_report_app.py

Requires (requirements.txt):
    streamlit, pypdf, reportlab, python-bidi, pdfplumber

System packages (packages.txt):
    fonts-freefont-ttf, fonts-dejavu-core

Metadata embedded in generated PDFs:
    /Author   : ARME ENGINEERS / <engineer_name>
    /Creator  : build_report.py — ARME Engineers (trom@arme.co.il)
    /Producer : ARME Engineers Build Report Generator v2.1-web
"""

import streamlit as st
import os
import io
import re
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Build Report — ARME Engineers",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Resolve base dir ─────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))


# ═══════════════════════════════════════════════════════════════════════════════
#  FONT FIX — pre-register Hebrew font BEFORE engine imports
# ═══════════════════════════════════════════════════════════════════════════════

def _find_hebrew_font():
    """Find a Hebrew-capable TTF font. Returns (regular_path, bold_path|None)."""
    # Search in repo directories first
    for d in [SCRIPT_DIR / "logos", SCRIPT_DIR / "fonts", SCRIPT_DIR]:
        if not d.exists():
            continue
        for ttf in sorted(d.glob("*.ttf")):
            # Look for bold variant
            stem = ttf.stem
            bold_candidates = [
                ttf.parent / f"{stem}Bold{ttf.suffix}",
                ttf.parent / f"{stem}-Bold{ttf.suffix}",
                ttf.parent / f"{stem}bd{ttf.suffix}",
            ]
            bold = next((b for b in bold_candidates if b.exists()), None)
            return str(ttf), str(bold) if bold else None

    # System fonts (Linux / Streamlit Cloud)
    for reg, bold in [
        ("/usr/share/fonts/truetype/freefont/FreeSans.ttf",
         "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]:
        if os.path.exists(reg):
            return reg, bold if os.path.exists(bold) else None
    return None, None


def _pre_register_fonts():
    """Register Hebrew fonts in ReportLab BEFORE engine imports."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return

    reg_path, bold_path = _find_hebrew_font()
    if not reg_path:
        return

    # Register for build_report.py (font names: "F", "FB")
    for name, path in [("F", reg_path), ("FB", bold_path or reg_path)]:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
        except Exception:
            pass

    # Register for annotate_loading.py (font names: "AL_F", "AL_FB")
    for name, path in [("AL_F", reg_path), ("AL_FB", bold_path or reg_path)]:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
        except Exception:
            pass

_pre_register_fonts()


# ── Import engines ───────────────────────────────────────────────────────────
ENGINE_OK = False
CONFIG_OK = False
ANNOTATE_OK = False

try:
    import config as cfg
    CONFIG_OK = True
except ImportError:
    cfg = None

try:
    import build_report as engine
    ENGINE_OK = True
    # Fix font if engine fell back to Helvetica
    if engine.FN == "Helvetica":
        try:
            from reportlab.pdfbase import pdfmetrics
            if "F" in pdfmetrics.getRegisteredFontNames():
                engine.FN, engine.FB = "F", "FB"
        except Exception:
            pass
except ImportError:
    engine = None

try:
    import annotate_loading as ann_mod
    ANNOTATE_OK = True
    # Fix font if annotate fell back to Helvetica
    if getattr(ann_mod, '_HEB_FONT_REG', '') == "Helvetica":
        try:
            from reportlab.pdfbase import pdfmetrics
            if "AL_F" in pdfmetrics.getRegisteredFontNames():
                ann_mod._HEB_FONT_REG = "AL_F"
                ann_mod._HEB_FONT_BOLD = "AL_FB"
        except Exception:
            pass
except ImportError:
    ann_mod = None


# ── Check bidi ───────────────────────────────────────────────────────────────
BIDI_OK = False
try:
    from bidi.algorithm import get_display
    BIDI_OK = True
except ImportError:
    pass


# ── Metadata constants ────────────────────────────────────────────────────────
ORG_NAME   = "ARME Engineers"
ORG_EMAIL  = "trom@arme.co.il"
ENGINEER   = "Shimon Donen"
APP_VER    = "2.1 (web)"


# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* === NUCLEAR: force light theme === */
    .stApp { background-color: #f5f7fa !important; }

    /* ALL text in main area = black */
    .stApp .main * { color: #1a1a2e !important; }

    /* ALL inputs/selects = white bg */
    .stApp .main input,
    .stApp .main textarea,
    .stApp .main select,
    .stApp .main [data-baseweb] * { background-color: #ffffff !important; }

    /* File uploader dropzone = white bg */
    .stApp .main [data-testid="stFileUploaderDropzone"] { background: #ffffff !important; }

    /* Uploaded file rows = light gray bg */
    .stApp .main [data-testid="stFileUploaderFile"] { background: #f0f2f6 !important; }

    /* Browse files button */
    .stApp .main [data-testid="stBaseButton-secondary"] {
        background-color: #e8ecf4 !important;
        border: 1px solid #bbc4d8 !important;
    }

    /* -- Sidebar: dark navy -- */
    [data-testid="stSidebar"] { background-color: #1a2a4a !important; }
    [data-testid="stSidebar"] * { color: #e8ecf4 !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #ffffff !important; }

    /* -- Header -- */
    .app-header { background: linear-gradient(135deg, #1a2a4a 0%, #2d4a8a 100%); padding: 18px 28px; border-radius: 10px; margin-bottom: 20px; }
    .app-header * { color: white !important; }
    .app-header .subtitle { color: #a8b8d8 !important; }

    /* -- Buttons -- */
    .stButton > button { background-color: #1a2a4a !important; border: none !important; border-radius: 6px; padding: 10px 28px; font-size: 1rem; font-weight: 600; }
    .stButton > button * { color: white !important; }
    .stButton > button:hover { background-color: #2d4a8a !important; }
    [data-testid="stDownloadButton"] > button { background-color: #1e6b3a !important; border: none !important; border-radius: 6px; width: 100%; }
    [data-testid="stDownloadButton"] > button * { color: white !important; }

    /* -- Cards -- */
    .info-card { background: #e8f0fe !important; border-left: 4px solid #1a2a4a; padding: 10px 16px; border-radius: 0 6px 6px 0; margin: 8px 0; font-size: 0.88rem; }
    .error-card { background: #fdecea !important; border-left: 4px solid #c0392b; padding: 10px 16px; border-radius: 0 6px 6px 0; margin: 8px 0; font-size: 0.88rem; }
    .success-card { background: #e6f4ea !important; border-left: 4px solid #1e6b3a; padding: 10px 16px; border-radius: 0 6px 6px 0; margin: 8px 0; font-size: 0.88rem; }

    /* -- Log box: dark terminal -- */
    .log-box { background: #0d1117 !important; padding: 14px; border-radius: 8px; white-space: pre-wrap; line-height: 1.5; border: 1px solid #30363d; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 11px; }
    .log-box * { color: #c9d1d9 !important; }

    /* -- File list -- */
    .file-list { background: #ffffff !important; border: 1px solid #dde3ec; border-radius: 8px; padding: 8px 12px; font-family: monospace; font-size: 0.82rem; max-height: 300px; overflow-y: auto; line-height: 1.7; }

    /* -- Folder hint -- */
    .folder-hint { background: #fff8e1 !important; border-left: 4px solid #f9a825; padding: 8px 14px; border-radius: 0 6px 6px 0; margin: 8px 0; font-size: 0.85rem; }
    .folder-hint * { color: #5d4037 !important; }

    /* -- Footer -- */
    .footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #dde3ec; font-size: 0.78rem; text-align: center; }
    .footer * { color: #8a96a8 !important; }
</style>
""", unsafe_allow_html=True)



# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="app-header">
  <div>
    <h1>📐 Build Report Generator</h1>
    <div class="subtitle">{ORG_NAME} &nbsp;|&nbsp; {ORG_EMAIL} &nbsp;|&nbsp; {ENGINEER} &nbsp;|&nbsp; v{APP_VER}</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📋 Instructions")
    st.markdown("""
**Step 1:** Enter the **folder name** of your project  
*(e.g. `1382 - אולם אירועים`)*  
→ number, name & factory auto-detected

**Step 2:** Upload PDF calculation files  
*(all PDFs for one floor/level)*

**Step 3:** Fill in floor/level & verify details

**Step 4:** Click **Build Report**

**Step 5:** Download the generated PDF
""")

    st.markdown("---")
    st.markdown("## 🏭 Factories")
    if CONFIG_OK:
        for key, fdata in cfg.FACTORIES.items():
            st.markdown(f"- **{key}** — {fdata['name']}")

    st.markdown("---")
    st.markdown("## 🔍 Auto-detect")
    st.markdown("""
**From folder name:**
```
1382 - אולם אירועים
26-09 - קיסריה מרלוג
```
**Factory by number:**
- `1000–1999` → sela
- `2200–2999` → ramet
- `YY-MM` → haifa
""")

    st.markdown("---")
    st.markdown("## 📝 Filename Format")
    st.markdown("`nn-h-L+STxx (DL+LL).pdf`")
    st.markdown("Example: `01-40-1385+ST25 (350+500).pdf`")

    # Status indicators
    st.markdown("---")
    st.markdown("## 🔧 Status")
    st.markdown(f"- Font: **{'✅' if engine and engine.FN != 'Helvetica' else '⚠️ Helvetica'}**")
    st.markdown(f"- BiDi: **{'✅ python-bidi' if BIDI_OK else '⚠️ NOT INSTALLED'}**")
    st.markdown(f"- Annotate: **{'✅' if ANNOTATE_OK else '❌'}**")
    _pdfplumber_ok = False
    try:
        import pdfplumber
        _pdfplumber_ok = True
    except ImportError:
        pass
    st.markdown(f"- pdfplumber: **{'✅' if _pdfplumber_ok else '⚠️ NOT INSTALLED'}**")

    st.markdown("---")
    st.caption(f"© {datetime.now().year} {ORG_NAME}")


# ── Engine check ──────────────────────────────────────────────────────────────
missing = []
if not CONFIG_OK:
    missing.append("config.py")
if not ENGINE_OK:
    missing.append("build_report.py")
if missing:
    st.markdown(f'<div class="error-card">⚠️ <b>Missing:</b> {", ".join(missing)}</div>',
                unsafe_allow_html=True)
    st.stop()

# Bidi warning
if not BIDI_OK:
    st.markdown(
        '<div class="error-card">'
        '⚠️ <b>python-bidi not installed!</b> Hebrew text will be mirrored in the PDF.<br>'
        'Add <code>python-bidi</code> to <code>requirements.txt</code> and redeploy.'
        '</div>',
        unsafe_allow_html=True
    )


# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("report_pdf", None), ("report_filename", None),
    ("build_log", None), ("build_success", False),
    ("auto_proj_num", ""), ("auto_proj_name", ""), ("auto_factory", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def parse_folder_name(folder_name: str):
    """Parse project folder name → (project_num, project_name)."""
    name = folder_name.strip()
    m = re.match(r"([\d][\d\-]*\d?)\s+-\s+(.+)", name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m2 = re.match(r"^(\d[\d\-]*\d?)(?:\s|$)", name)
    if m2:
        return m2.group(1).strip(), ""
    return "", ""


def detect_factory_key(proj_num: str) -> str:
    if not proj_num or not CONFIG_OK:
        return ""
    return cfg.detect_factory(proj_num) if hasattr(cfg, 'detect_factory') else ""


def copy_fonts_to_dir(target_dir: Path):
    """Copy Hebrew TTF fonts into target_dir for engine discovery."""
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
    if list(target_dir.glob("*.ttf")):
        return
    for src_dir in [SCRIPT_DIR / "logos", SCRIPT_DIR / "fonts", SCRIPT_DIR]:
        if src_dir.exists():
            for ttf in src_dir.glob("*.ttf"):
                try:
                    shutil.copy2(str(ttf), str(target_dir / ttf.name))
                except Exception:
                    pass
            if list(target_dir.glob("*.ttf")):
                return
    for src in [
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(src):
            try:
                shutil.copy2(src, str(target_dir / Path(src).name))
            except Exception:
                pass


# ── Main layout ───────────────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1.4], gap="large")

# ═══════════════════════════════════════════════════════════════════════════════
#  LEFT — Input & Settings
# ═══════════════════════════════════════════════════════════════════════════════
with col_left:

    # ── Folder name ───────────────────────────────────────────────────────────
    st.markdown("### 📂 Project Folder Name")
    st.markdown(
        '<div class="folder-hint">'
        '💡 Paste the <b>folder name</b> from your project directory to auto-fill '
        'project number, name & factory.'
        '</div>', unsafe_allow_html=True
    )

    folder_name_input = st.text_input(
        "Folder name",
        placeholder="e.g.  1382 - אולם אירועים   or   26-09 - קיסריה מרלוג",
        label_visibility="collapsed",
    )

    if folder_name_input.strip():
        parsed_num, parsed_name = parse_folder_name(folder_name_input)
        if parsed_num:
            st.session_state.auto_proj_num = parsed_num
            st.session_state.auto_proj_name = parsed_name
            st.session_state.auto_factory = detect_factory_key(parsed_num)

            factory_display = ""
            if st.session_state.auto_factory and CONFIG_OK:
                fname = cfg.FACTORIES.get(st.session_state.auto_factory, {}).get("name", "")
                factory_display = f" · 🏭 {fname} ({st.session_state.auto_factory})"

            st.markdown(
                f'<div class="success-card">✅ Detected: <b>{parsed_num}</b>'
                f'{" — " + parsed_name if parsed_name else ""}{factory_display}</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="error-card">⚠️ Could not parse. '
                'Expected: <code>1382 - שם</code> or <code>26-09 - שם</code></div>',
                unsafe_allow_html=True
            )
    else:
        st.session_state.auto_proj_num = ""
        st.session_state.auto_proj_name = ""
        st.session_state.auto_factory = ""

    st.markdown("---")

    # ── Upload PDFs ───────────────────────────────────────────────────────────
    st.markdown("### 📁 Upload PDF Files")
    uploaded_files = st.file_uploader(
        "Upload calculation PDFs", type=["pdf"],
        accept_multiple_files=True, label_visibility="collapsed",
    )

    valid_files = []
    if uploaded_files:
        valid_files = [f for f in uploaded_files
                       if "Static_Calculations_Report" not in f.name
                       and not f.name.replace(".pdf", "").endswith("_report")]
        st.markdown(
            f'<div class="info-card">📄 <b>{len(valid_files)} PDF file(s)</b> uploaded</div>',
            unsafe_allow_html=True
        )
        # File list with guaranteed dark text
        file_names_html = "".join(
            f'<div class="file-item" style="color:#1a1a2e;">{i+1:02d}. {f.name}</div>'
            for i, f in enumerate(valid_files)
        )
        st.markdown(
            f'<div class="file-list" style="color:#1a1a2e;">{file_names_html}</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── Project Settings ──────────────────────────────────────────────────────
    st.markdown("### ⚙️ Project Settings")

    proj_num = st.text_input("Project Number *",
                             value=st.session_state.auto_proj_num,
                             placeholder="e.g. 1382, 26-09, 2501")
    proj_name = st.text_input("Project Name",
                              value=st.session_state.auto_proj_name,
                              placeholder="e.g. אולם אירועים")
    floor_name = st.text_input("Floor / Level *",
                               placeholder="e.g. +0.00, +14, גג, -1")

    # Factory
    factory_options = {k: f"{v['name']} ({k})" for k, v in cfg.FACTORIES.items()} if CONFIG_OK else {}
    factory_keys = list(factory_options.keys())
    default_idx = 0
    auto_fk = st.session_state.auto_factory or detect_factory_key(proj_num)
    if auto_fk and auto_fk in factory_keys:
        default_idx = factory_keys.index(auto_fk)

    factory_selection = st.selectbox(
        "Factory *", options=factory_keys,
        format_func=lambda k: factory_options.get(k, k),
        index=default_idx,
    )
    if auto_fk and auto_fk == factory_selection:
        st.markdown(
            f'<div class="info-card">🏭 Auto: <b>{factory_options.get(auto_fk, auto_fk)}</b></div>',
            unsafe_allow_html=True
        )

    engineer_name = st.text_input(
        "Engineer",
        value=getattr(cfg, 'DEFAULT_ENGINEER', 'שמעון דונן') if CONFIG_OK else 'שמעון דונן',
    )

    st.markdown("---")
    annotate_loading = st.checkbox("✏️ Annotate Loading pages",
                                   value=True, disabled=not ANNOTATE_OK)
    if not ANNOTATE_OK:
        st.caption("⚠️ annotate_loading.py not found")

    st.markdown("---")
    build_clicked = st.button("▶  Build Report", use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  RIGHT — Output & Download
# ═══════════════════════════════════════════════════════════════════════════════
with col_right:
    st.markdown("### 📊 Report Output")

    if build_clicked:
        errors = []
        if not valid_files:
            errors.append("No PDF files uploaded")
        if not proj_num.strip():
            errors.append("Project number is required")
        if not floor_name.strip():
            errors.append("Floor / level is required")
        if not factory_selection:
            errors.append("Factory is required")

        if errors:
            err_html = "<br>".join(f"• {e}" for e in errors)
            st.markdown(
                f'<div class="error-card">⚠️ <b>Cannot build:</b><br>{err_html}</div>',
                unsafe_allow_html=True
            )
        else:
            with st.spinner("Building report..."):
                tmpdir = None
                old_stdout = sys.stdout
                log_capture = io.StringIO()

                try:
                    tmpdir = tempfile.mkdtemp(prefix="arme_report_")
                    p_num = proj_num.strip()
                    p_name = proj_name.strip()
                    fl_name = floor_name.strip()

                    project_dir = Path(tmpdir) / (f"{p_num} - {p_name}" if p_name else p_num)
                    floor_dir = project_dir / fl_name
                    floor_dir.mkdir(parents=True, exist_ok=True)

                    # Prepare logos + fonts
                    logos_dst = Path(tmpdir) / "logos"
                    logos_src = SCRIPT_DIR / "logos"
                    if logos_src.exists():
                        shutil.copytree(str(logos_src), str(logos_dst))
                    else:
                        logos_dst.mkdir(exist_ok=True)
                        for ext in ["*.jpg", "*.jpeg", "*.png", "*.gif"]:
                            for img in SCRIPT_DIR.glob(ext):
                                shutil.copy2(str(img), str(logos_dst / img.name))
                    copy_fonts_to_dir(logos_dst)

                    # Point engine to temp logos
                    old_logos_dir = engine.LOGOS_DIR
                    engine.LOGOS_DIR = logos_dst

                    # Re-setup fonts
                    try:
                        new_fn, new_fb = engine._setup_fonts()
                        engine.FN = new_fn
                        engine.FB = new_fb
                    except Exception:
                        pass

                    # Save PDFs
                    for uf in valid_files:
                        (floor_dir / uf.name).write_bytes(uf.getbuffer())

                    sys.stdout = log_capture

                    # Patch parse_project_folder
                    orig_parse = engine.parse_project_folder
                    def patched_parse(fp):
                        n = Path(fp).name
                        m = re.match(r"([\d][\d\-]*\d?)\s*-\s*(.+)", n)
                        return (m.group(1).strip(), m.group(2).strip()) if m else (p_num, p_name)
                    engine.parse_project_folder = patched_parse

                    try:
                        output_path = engine.build_report(
                            project_folder=project_dir,
                            floor_folder=floor_dir,
                            factory_key=factory_selection,
                            engineer=engineer_name.strip() or getattr(cfg, 'DEFAULT_ENGINEER', ''),
                            floor_name=fl_name,
                            no_annotate=not annotate_loading,
                        )
                    finally:
                        engine.parse_project_folder = orig_parse
                        engine.LOGOS_DIR = old_logos_dir

                    sys.stdout = old_stdout
                    log_output = log_capture.getvalue()

                    if output_path and Path(output_path).exists():
                        st.session_state.report_pdf = Path(output_path).read_bytes()
                        st.session_state.report_filename = Path(output_path).name
                        st.session_state.build_log = log_output
                        st.session_state.build_success = True
                    else:
                        st.session_state.report_pdf = None
                        st.session_state.build_log = log_output + "\n\nERROR: Output not created."
                        st.session_state.build_success = False

                except Exception as e:
                    sys.stdout = old_stdout
                    st.session_state.report_pdf = None
                    st.session_state.build_log = f"{log_capture.getvalue()}\n\nERROR: {type(e).__name__}: {e}"
                    st.session_state.build_success = False

                finally:
                    sys.stdout = old_stdout
                    if tmpdir and os.path.exists(tmpdir):
                        try:
                            shutil.rmtree(tmpdir)
                        except Exception:
                            pass

    # ── Results ───────────────────────────────────────────────────────────────
    if st.session_state.build_success and st.session_state.report_pdf:
        size_kb = len(st.session_state.report_pdf) // 1024
        st.markdown(
            f'<div class="success-card">✅ <b>Report ready!</b> ({size_kb} KB)</div>',
            unsafe_allow_html=True
        )
        st.download_button(
            label=f"⬇️  Download {st.session_state.report_filename}",
            data=st.session_state.report_pdf,
            file_name=st.session_state.report_filename,
            mime="application/pdf", use_container_width=True,
        )
        st.caption(f"📄 `{st.session_state.report_filename}`")

    elif st.session_state.build_log and not st.session_state.build_success:
        st.markdown(
            '<div class="error-card">⚠️ <b>Build failed.</b> See log below.</div>',
            unsafe_allow_html=True
        )

    if st.session_state.build_log:
        st.markdown("---")
        st.markdown("#### 📋 Build Log")
        log_html = (st.session_state.build_log
                    .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        st.markdown(f'<div class="log-box">{log_html}</div>', unsafe_allow_html=True)

    if not st.session_state.build_log:
        st.markdown("""
<div style="height:280px; display:flex; align-items:center; justify-content:center;
            background:#eef1f7; border-radius:8px; border:1px dashed #bbc4d8;
            color:#8a96a8; font-size:0.95rem; text-align:center; padding:20px;">
    <div>
        <div style="font-size:2.5rem; margin-bottom:10px;">📐</div>
        <b>1.</b> Paste folder name →
        <b>2.</b> Upload PDFs →
        <b>3.</b> Set floor →
        <b>4.</b> Build Report
    </div>
</div>
""", unsafe_allow_html=True)


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="footer">
    {ORG_NAME} · {ORG_EMAIL} · {ENGINEER} · Build Report v{APP_VER}
</div>
""", unsafe_allow_html=True)
