"""
build_report_app.py — ARME Engineers | Build Report Generator (Streamlit web app)
trom@arme.co.il | Shimon Donen

Streamlit Cloud web interface for building PDF reports from prestressed slab calculations.
Combines build_report.py + annotate_loading.py into a single web workflow.

Run:
    streamlit run build_report_app.py

Requires:
    pip install streamlit pypdf reportlab python-bidi
    (build_report.py, annotate_loading.py, config.py must be in the same folder)

Font fix:
    Place FreeSans.ttf (or any Hebrew-capable TTF) in fonts/ directory.
    The app copies it into logos/ at startup so build_report.py finds it.
    On Streamlit Cloud, also add packages.txt with: fonts-freefont-ttf

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

# ── Resolve base dir (for imports) ───────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# ═══════════════════════════════════════════════════════════════════════════════
#  FONT FIX — ensure Hebrew fonts are discoverable by build_report.py
# ═══════════════════════════════════════════════════════════════════════════════
#
#  build_report.py._setup_fonts() searches for *.ttf in:
#    1. Hard-coded system paths (C:/Windows/Fonts/arial.ttf, DejaVuSans, etc.)
#    2. LOGOS_DIR/*.ttf
#    3. SCRIPT_DIR/*.ttf
#
#  On Streamlit Cloud:
#    - Windows fonts don't exist
#    - DejaVu/Liberation may or may not be installed
#    - Our repo has fonts/FreeSans.ttf — but that dir is NOT searched
#
#  Fix: copy fonts/*.ttf → logos/ so _setup_fonts() finds them.
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_hebrew_fonts():
    """
    Copy Hebrew-capable TTF from fonts/ into logos/ (where build_report.py looks).
    Also try system fonts as fallback.
    """
    logos_dir = SCRIPT_DIR / "logos"
    fonts_dir = SCRIPT_DIR / "fonts"

    # Ensure logos/ exists
    if not logos_dir.exists():
        logos_dir.mkdir(parents=True, exist_ok=True)

    # Already have .ttf in logos/?
    if list(logos_dir.glob("*.ttf")):
        return

    # Source 1: fonts/ directory in repo (FreeSans.ttf, etc.)
    if fonts_dir.exists():
        for ttf in fonts_dir.glob("*.ttf"):
            dst = logos_dir / ttf.name
            if not dst.exists():
                try:
                    shutil.copy2(str(ttf), str(dst))
                except Exception:
                    pass
        if list(logos_dir.glob("*.ttf")):
            return

    # Source 2: system fonts (Linux / Streamlit Cloud)
    system_fonts = [
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for src in system_fonts:
        if os.path.exists(src):
            dst = logos_dir / Path(src).name
            if not dst.exists():
                try:
                    shutil.copy2(src, str(dst))
                except Exception:
                    pass

_ensure_hebrew_fonts()


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
except ImportError:
    engine = None

try:
    from annotate_loading import annotate_pdf_loading
    ANNOTATE_OK = True
except ImportError:
    pass

# ── Metadata constants ────────────────────────────────────────────────────────
ORG_NAME   = "ARME Engineers"
ORG_EMAIL  = "trom@arme.co.il"
ENGINEER   = "Shimon Donen"
APP_VER    = "2.1 (web)"

# ── Custom CSS (matching pret_loads_app.py) ──────────────────────────────────
st.markdown("""
<style>
    /* Main background */
    .stApp { background-color: #f5f7fa; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #1a2a4a;
    }
    [data-testid="stSidebar"] * {
        color: #e8ecf4 !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #ffffff !important;
    }

    /* Header bar */
    .app-header {
        background: linear-gradient(135deg, #1a2a4a 0%, #2d4a8a 100%);
        padding: 18px 28px;
        border-radius: 10px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .app-header h1 {
        color: white !important;
        font-size: 1.6rem;
        margin: 0;
    }
    .app-header .subtitle {
        color: #a8b8d8;
        font-size: 0.85rem;
        margin-top: 4px;
    }

    /* Buttons */
    .stButton > button {
        background-color: #1a2a4a;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 10px 28px;
        font-size: 1rem;
        font-weight: 600;
        cursor: pointer;
        transition: background-color 0.2s;
    }
    .stButton > button:hover {
        background-color: #2d4a8a;
    }

    /* Download button */
    [data-testid="stDownloadButton"] > button {
        background-color: #1e6b3a;
        color: white;
        border: none;
        border-radius: 6px;
        width: 100%;
    }
    [data-testid="stDownloadButton"] > button:hover {
        background-color: #2a8f4e;
    }

    /* Info / error / success cards */
    .info-card {
        background: #e8f0fe;
        border-left: 4px solid #1a2a4a;
        padding: 10px 16px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        font-size: 0.88rem;
    }
    .error-card {
        background: #fdecea;
        border-left: 4px solid #c0392b;
        padding: 10px 16px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        font-size: 0.88rem;
    }
    .success-card {
        background: #e6f4ea;
        border-left: 4px solid #1e6b3a;
        padding: 10px 16px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        font-size: 0.88rem;
    }

    /* Monospace log */
    .log-box {
        background: #0d1117;
        color: #c9d1d9;
        font-family: 'Courier New', Courier, monospace;
        font-size: 11px;
        padding: 14px;
        border-radius: 8px;
        overflow-x: auto;
        white-space: pre-wrap;
        line-height: 1.5;
        border: 1px solid #30363d;
        max-height: 400px;
        overflow-y: auto;
    }

    /* File list */
    .file-list {
        background: #ffffff;
        border: 1px solid #dde3ec;
        border-radius: 8px;
        padding: 8px 12px;
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.82rem;
        max-height: 300px;
        overflow-y: auto;
        line-height: 1.6;
    }
    .file-list .file-item {
        padding: 2px 0;
        border-bottom: 1px solid #f0f2f5;
    }
    .file-list .file-item:last-child {
        border-bottom: none;
    }

    /* Folder name input highlight */
    .folder-hint {
        background: #fff8e1;
        border-left: 4px solid #f9a825;
        padding: 8px 14px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        font-size: 0.85rem;
        color: #5d4037;
    }

    /* Footer */
    .footer {
        margin-top: 40px;
        padding-top: 16px;
        border-top: 1px solid #dde3ec;
        color: #8a96a8;
        font-size: 0.78rem;
        text-align: center;
    }
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


# ── Sidebar — Help & Instructions ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📋 Instructions")
    st.markdown("""
**Step 1:** Enter the **folder name** of your project  
*(e.g. `1382 - אולם אירועים`)*  
→ project number, name & factory are auto-detected

**Step 2:** Upload PDF calculation files  
*(all PDFs for one floor/level)*

**Step 3:** Fill in floor/level & verify other details

**Step 4:** Click **Build Report**

**Step 5:** Download the generated PDF
""")

    st.markdown("---")
    st.markdown("## 🏭 Factories")
    if CONFIG_OK:
        for key, fdata in cfg.FACTORIES.items():
            st.markdown(f"- **{key}** — {fdata['name']}")
    else:
        st.markdown("*(config.py not found)*")

    st.markdown("---")
    st.markdown("## 🔍 Auto-detect rules")
    st.markdown("""
**From folder name:**
```
1382 - אולם אירועים
  └── proj_num: 1382
       proj_name: אולם אירועים
```
```
26-09 - קיסריה מרלוג
  └── proj_num: 26-09
       proj_name: קיסריה מרלוג
```

**Factory by project number:**
- `1000–1999` → סלע בן ארי (sela)
- `2200–2999` → רמת טרום (ramet)
- `YY-MM` → מפעל חיפה (haifa)
""")

    st.markdown("---")
    st.markdown("## 📝 Filename Format")
    st.markdown("""
```
nn-h-L+STxx (DL+LL).pdf
```
Example:
```
01-40-1385+ST25 (350+500).pdf
```
""")

    st.markdown("---")
    st.caption(f"© {datetime.now().year} {ORG_NAME}")


# ── Engine check ──────────────────────────────────────────────────────────────
missing = []
if not CONFIG_OK:
    missing.append("config.py")
if not ENGINE_OK:
    missing.append("build_report.py")
if missing:
    st.markdown(f"""
<div class="error-card">
⚠️ <b>Missing required files:</b> {', '.join(missing)}<br>
Place them in the same folder as this app and restart.
</div>
""", unsafe_allow_html=True)
    st.stop()


# ── Session state init ────────────────────────────────────────────────────────
for key, default in [
    ("report_pdf", None),
    ("report_filename", None),
    ("build_log", None),
    ("build_success", False),
    ("auto_proj_num", ""),
    ("auto_proj_name", ""),
    ("auto_factory", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def parse_folder_name(folder_name: str):
    """
    Parse project folder name → (project_num, project_name).
    Patterns:
        '1382 - אולם אירועים'  → ('1382', 'אולם אירועים')
        '26-09 - קיסריה מרלוג'  → ('26-09', 'קיסריה מרלוג')
        '2501'                   → ('2501', '')
    """
    name = folder_name.strip()
    m = re.match(r"([\d][\d\-]*\d?)\s+-\s+(.+)", name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m2 = re.match(r"^(\d[\d\-]*\d?)(?:\s|$)", name)
    if m2:
        return m2.group(1).strip(), ""
    return "", ""


def detect_factory_key(proj_num: str) -> str:
    """Auto-detect factory from project number via config."""
    if not proj_num or not CONFIG_OK:
        return ""
    if hasattr(cfg, 'detect_factory'):
        return cfg.detect_factory(proj_num)
    return ""


def copy_fonts_to_dir(target_dir: Path):
    """
    Copy Hebrew-capable TTF fonts into target_dir.
    Sources (in priority order):
      1. SCRIPT_DIR/fonts/*.ttf  (repo fonts — FreeSans.ttf)
      2. SCRIPT_DIR/logos/*.ttf  (already copied at startup)
      3. System fonts (Linux fallback)
    """
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    # Already have .ttf?
    if list(target_dir.glob("*.ttf")):
        return

    # Source 1: fonts/ in repo
    fonts_dir = SCRIPT_DIR / "fonts"
    if fonts_dir.exists():
        for ttf in fonts_dir.glob("*.ttf"):
            try:
                shutil.copy2(str(ttf), str(target_dir / ttf.name))
            except Exception:
                pass
        if list(target_dir.glob("*.ttf")):
            return

    # Source 2: logos/ (may have fonts from _ensure_hebrew_fonts)
    logos_dir = SCRIPT_DIR / "logos"
    if logos_dir.exists():
        for ttf in logos_dir.glob("*.ttf"):
            try:
                shutil.copy2(str(ttf), str(target_dir / ttf.name))
            except Exception:
                pass
        if list(target_dir.glob("*.ttf")):
            return

    # Source 3: system fonts
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
#  LEFT COLUMN — Input & Settings
# ═══════════════════════════════════════════════════════════════════════════════
with col_left:

    # ── Folder name input (auto-detect project) ──────────────────────────────
    st.markdown("### 📂 Project Folder Name")
    st.markdown(
        '<div class="folder-hint">'
        '💡 Paste the <b>folder name</b> from your project directory to auto-fill '
        'project number, name & factory.'
        '</div>',
        unsafe_allow_html=True
    )

    folder_name_input = st.text_input(
        "Folder name",
        placeholder="e.g.  1382 - אולם אירועים   or   26-09 - קיסריה מרלוג",
        label_visibility="collapsed",
    )

    # Auto-parse folder name
    if folder_name_input.strip():
        parsed_num, parsed_name = parse_folder_name(folder_name_input)
        if parsed_num:
            st.session_state.auto_proj_num = parsed_num
            st.session_state.auto_proj_name = parsed_name
            st.session_state.auto_factory = detect_factory_key(parsed_num)

            factory_display = ""
            if st.session_state.auto_factory and CONFIG_OK:
                fname = cfg.FACTORIES.get(st.session_state.auto_factory, {}).get("name", "")
                factory_display = f" &nbsp;·&nbsp; 🏭 {fname} ({st.session_state.auto_factory})"

            st.markdown(
                f'<div class="success-card">'
                f'✅ Detected: <b>{parsed_num}</b>'
                f'{" — " + parsed_name if parsed_name else ""}'
                f'{factory_display}'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="error-card">'
                '⚠️ Could not parse folder name. Expected format: '
                '<code>1382 - שם פרויקט</code> or <code>26-09 - שם פרויקט</code>'
                '</div>',
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
        "Upload calculation PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        help="Upload all PDF calculation files for one floor/level",
    )

    if uploaded_files:
        valid_files = [f for f in uploaded_files
                       if "Static_Calculations_Report" not in f.name
                       and not f.name.replace(".pdf", "").endswith("_report")]

        st.markdown(
            f'<div class="info-card">📄 <b>{len(valid_files)} PDF file(s)</b> uploaded</div>',
            unsafe_allow_html=True
        )

        file_names_html = "".join(
            f'<div class="file-item">{i+1:2d}. {f.name}</div>'
            for i, f in enumerate(valid_files)
        )
        st.markdown(f'<div class="file-list">{file_names_html}</div>', unsafe_allow_html=True)
    else:
        valid_files = []

    st.markdown("---")

    # ── Project Settings ──────────────────────────────────────────────────────
    st.markdown("### ⚙️ Project Settings")

    proj_num = st.text_input(
        "Project Number *",
        value=st.session_state.auto_proj_num,
        placeholder="e.g. 1382, 26-09, 2501",
    )

    proj_name = st.text_input(
        "Project Name",
        value=st.session_state.auto_proj_name,
        placeholder="e.g. אולם אירועים",
    )

    floor_name = st.text_input(
        "Floor / Level *",
        placeholder="e.g. +0.00, +14, גג, -1",
    )

    # Factory selector
    factory_options = {}
    if CONFIG_OK:
        factory_options = {k: f"{v['name']} ({k})" for k, v in cfg.FACTORIES.items()}

    factory_keys = list(factory_options.keys())

    default_idx = 0
    auto_fk = st.session_state.auto_factory or detect_factory_key(proj_num)
    if auto_fk and auto_fk in factory_keys:
        default_idx = factory_keys.index(auto_fk)

    factory_selection = st.selectbox(
        "Factory *",
        options=factory_keys,
        format_func=lambda k: factory_options.get(k, k),
        index=default_idx,
        help="Auto-detected from project number when possible",
    )

    if auto_fk and auto_fk == factory_selection:
        st.markdown(
            f'<div class="info-card">🏭 Auto-detected: '
            f'<b>{factory_options.get(auto_fk, auto_fk)}</b></div>',
            unsafe_allow_html=True
        )

    engineer_name = st.text_input(
        "Engineer",
        value=getattr(cfg, 'DEFAULT_ENGINEER', 'שמעון דונן') if CONFIG_OK else 'שמעון דונן',
        help="Engineer name for the report title page",
    )

    # Options
    st.markdown("---")
    annotate_loading = st.checkbox(
        "✏️ Annotate Loading pages",
        value=True,
        help="Add load annotations on Loading pages",
        disabled=not ANNOTATE_OK,
    )
    if not ANNOTATE_OK:
        st.caption("⚠️ annotate_loading.py not found — annotations disabled")

    # Build button
    st.markdown("---")
    build_clicked = st.button("▶  Build Report", use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  RIGHT COLUMN — Output & Download
# ═══════════════════════════════════════════════════════════════════════════════
with col_right:
    st.markdown("### 📊 Report Output")

    if build_clicked:
        # Validate
        errors = []
        if not valid_files:
            errors.append("No PDF files uploaded")
        if not proj_num.strip():
            errors.append("Project number is required")
        if not floor_name.strip():
            errors.append("Floor / level is required")
        if not factory_selection:
            errors.append("Factory selection is required")

        if errors:
            err_html = "<br>".join(f"• {e}" for e in errors)
            st.markdown(
                f'<div class="error-card">⚠️ <b>Cannot build report:</b><br>{err_html}</div>',
                unsafe_allow_html=True
            )
        else:
            with st.spinner("Building report... This may take a moment."):
                tmpdir = None
                old_stdout = sys.stdout
                log_capture = io.StringIO()

                try:
                    tmpdir = tempfile.mkdtemp(prefix="arme_report_")
                    p_num = proj_num.strip()
                    p_name = proj_name.strip()
                    fl_name = floor_name.strip()

                    if p_name:
                        project_dir = Path(tmpdir) / f"{p_num} - {p_name}"
                    else:
                        project_dir = Path(tmpdir) / p_num
                    floor_dir = project_dir / fl_name
                    floor_dir.mkdir(parents=True, exist_ok=True)

                    # ── Prepare logos dir with fonts ──────────────────────────
                    logos_dst = Path(tmpdir) / "logos"
                    logos_src = SCRIPT_DIR / "logos"
                    if logos_src.exists():
                        shutil.copytree(str(logos_src), str(logos_dst))
                    else:
                        logos_dst.mkdir(exist_ok=True)
                        for img_ext in ["*.jpg", "*.jpeg", "*.png", "*.gif"]:
                            for img in SCRIPT_DIR.glob(img_ext):
                                shutil.copy2(str(img), str(logos_dst / img.name))

                    # Copy Hebrew fonts into logos_dst
                    copy_fonts_to_dir(logos_dst)

                    # ── Point engine to temp logos ────────────────────────────
                    old_logos_dir = engine.LOGOS_DIR
                    engine.LOGOS_DIR = logos_dst

                    # Re-register fonts with new paths
                    try:
                        new_fn, new_fb = engine._setup_fonts()
                        engine.FN = new_fn
                        engine.FB = new_fb
                    except Exception:
                        pass

                    # ── Save uploaded PDFs ────────────────────────────────────
                    for uf in valid_files:
                        (floor_dir / uf.name).write_bytes(uf.getbuffer())

                    # ── Capture stdout ────────────────────────────────────────
                    sys.stdout = log_capture

                    # ── Patch parse_project_folder ────────────────────────────
                    orig_parse = engine.parse_project_folder
                    def patched_parse(fp):
                        fp_name = Path(fp).name
                        m = re.match(r"([\d][\d\-]*\d?)\s*-\s*(.+)", fp_name)
                        if m:
                            return m.group(1).strip(), m.group(2).strip()
                        return p_num, p_name
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
                        st.session_state.build_log = log_output + "\n\nERROR: Output file not created."
                        st.session_state.build_success = False

                except Exception as e:
                    sys.stdout = old_stdout
                    log_text = log_capture.getvalue()
                    st.session_state.report_pdf = None
                    st.session_state.build_log = f"{log_text}\n\nERROR: {type(e).__name__}: {e}"
                    st.session_state.build_success = False

                finally:
                    sys.stdout = old_stdout
                    if tmpdir and os.path.exists(tmpdir):
                        try:
                            shutil.rmtree(tmpdir)
                        except Exception:
                            pass

    # ── Display results ───────────────────────────────────────────────────────
    if st.session_state.build_success and st.session_state.report_pdf:
        size_kb = len(st.session_state.report_pdf) // 1024
        st.markdown(
            f'<div class="success-card">✅ <b>Report built successfully!</b> '
            f'({size_kb} KB)</div>',
            unsafe_allow_html=True
        )

        st.download_button(
            label=f"⬇️  Download {st.session_state.report_filename}",
            data=st.session_state.report_pdf,
            file_name=st.session_state.report_filename,
            mime="application/pdf",
            use_container_width=True,
        )
        st.caption(f"📄 File: `{st.session_state.report_filename}`")

    elif st.session_state.build_log and not st.session_state.build_success:
        st.markdown(
            '<div class="error-card">⚠️ <b>Build failed.</b> See log below for details.</div>',
            unsafe_allow_html=True
        )

    # ── Build log ─────────────────────────────────────────────────────────────
    if st.session_state.build_log:
        st.markdown("---")
        st.markdown("#### 📋 Build Log")
        log_html = (st.session_state.build_log
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))
        st.markdown(f'<div class="log-box">{log_html}</div>', unsafe_allow_html=True)

    # ── Empty state ───────────────────────────────────────────────────────────
    if not st.session_state.build_log:
        st.markdown("""
<div style="height:280px; display:flex; align-items:center; justify-content:center;
            background:#eef1f7; border-radius:8px; border:1px dashed #bbc4d8;
            color:#8a96a8; font-size:0.95rem; text-align:center; padding: 20px;">
    <div>
        <div style="font-size:2.5rem; margin-bottom:10px;">📐</div>
        <b>1.</b> Paste folder name &nbsp;→&nbsp;
        <b>2.</b> Upload PDFs &nbsp;→&nbsp;
        <b>3.</b> Set floor &nbsp;→&nbsp;
        <b>4.</b> Build Report
    </div>
</div>
""", unsafe_allow_html=True)


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="footer">
    {ORG_NAME} &nbsp;·&nbsp; {ORG_EMAIL} &nbsp;·&nbsp; {ENGINEER} &nbsp;·&nbsp; Build Report Generator v{APP_VER}
</div>
""", unsafe_allow_html=True)
