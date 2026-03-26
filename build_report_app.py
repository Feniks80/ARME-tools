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

# ── Force light color-scheme at browser level ────────────────────────────────
st.markdown('<meta name="color-scheme" content="light only">', unsafe_allow_html=True)

# ── Custom CSS (force light theme, override dark-mode defaults) ──────────────
st.markdown("""
<style>
    /* ═══ NUCLEAR: Override Streamlit's CSS variables at every level ═══════ */
    :root,
    [data-testid="stAppViewContainer"],
    [data-testid="stApp"],
    .stApp, html, body {
        --primary-color: #1a2a4a !important;
        --background-color: #f5f7fa !important;
        --secondary-background-color: #e8ecf4 !important;
        --text-color: #1a1a2e !important;
        --font: "Source Sans Pro", sans-serif !important;
        color-scheme: light only !important;
    }

    /* Force light on html/body */
    html, body {
        background-color: #f5f7fa !important;
        color: #1a1a2e !important;
        color-scheme: light only !important;
    }

    /* ═══ FORCE LIGHT THEME ═══════════════════════════════════════════════ */

    /* Main background */
    .stApp {
        background-color: #f5f7fa !important;
        color: #1a1a2e !important;
    }

    /* ── BLANKET: every single element in main area ──────────────────────── */
    .stApp .main *:not(.app-header *):not(.log-box *):not(.footer *) {
        color: #1a1a2e !important;
    }

    /* ── Headings ─────────────────────────────────────────────────────────── */
    .stApp .main h1, .stApp .main h2, .stApp .main h3,
    .stApp .main h4, .stApp .main h5, .stApp .main h6 {
        color: #1a1a2e !important;
    }

    /* ── Input fields — white bg, dark text ───────────────────────────────── */
    .stApp .main input,
    .stApp .main textarea {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
        border: 1px solid #c4ccd8 !important;
    }
    .stApp .main input::placeholder,
    .stApp .main textarea::placeholder {
        color: #8a96a8 !important;
        opacity: 1 !important;
    }

    /* ── Selectbox ─────────────────────────────────────────────────────────── */
    .stApp .main [data-baseweb="select"] > div,
    .stApp .main [data-testid="stSelectbox"] > div > div {
        background-color: #ffffff !important;
        color: #1a1a2e !important;
        border: 1px solid #c4ccd8 !important;
    }

    /* ── Checkbox — fix dark-on-dark ──────────────────────────────────────── */
    .stApp .main [data-testid="stCheckbox"] *,
    .stApp .main .stCheckbox * {
        color: #1a1a2e !important;
    }

    /* ── File uploader area ───────────────────────────────────────────────── */
    .stApp .main [data-testid="stFileUploader"] {
        background-color: #ffffff !important;
        border: 1px solid #c4ccd8 !important;
        border-radius: 8px !important;
    }
    .stApp .main [data-testid="stFileUploader"] *,
    .stApp .main [data-testid="stFileUploaderDropzone"] * {
        color: #1a1a2e !important;
    }
    .stApp .main [data-testid="stFileUploaderDropzone"] {
        background-color: #f8f9fb !important;
    }
    .stApp .main [data-testid="stFileUploader"] small {
        color: #6b7a90 !important;
    }
    /* Browse files button */
    .stApp .main [data-testid="stFileUploaderDropzone"] button,
    .stApp .main [data-testid="stFileUploader"] button[kind="secondary"],
    .stApp .main [data-testid="stFileUploader"] button {
        background-color: #f0f2f5 !important;
        color: #1a2a4a !important;
        border: 1px solid #1a2a4a !important;
    }
    /* Uploaded file name row */
    .stApp .main [data-testid="stFileUploaderFile"] *,
    .stApp .main .uploadedFile *,
    .stApp .main [data-testid="stFileUploaderFileName"] {
        color: #1a1a2e !important;
    }
    /* X delete button */
    .stApp .main [data-testid="stFileUploaderDeleteBtn"],
    .stApp .main [data-testid="stFileUploaderDeleteBtn"] * {
        color: #666 !important;
    }

    /* ── Tooltips & captions ──────────────────────────────────────────────── */
    .stApp .main [data-testid="stTooltipIcon"] { color: #6b7a90 !important; }
    .stApp .main [data-testid="stCaptionContainer"],
    .stApp .main [data-testid="stCaptionContainer"] * {
        color: #6b7a90 !important;
    }

    /* ── Horizontal rules ─────────────────────────────────────────────────── */
    .stApp .main hr { border-color: #dde3ec !important; }

    /* ── Sidebar — dark navy theme ────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background-color: #1a2a4a !important;
    }
    [data-testid="stSidebar"] * {
        color: #e8ecf4 !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] code {
        color: #f0c040 !important;
        background-color: rgba(255,255,255,0.1) !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.15) !important;
    }

    /* ── Header bar ───────────────────────────────────────────────────────── */
    .app-header {
        background: linear-gradient(135deg, #1a2a4a 0%, #2d4a8a 100%);
        padding: 18px 28px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .app-header h1 { color: white !important; font-size: 1.6rem; margin: 0; }
    .app-header .subtitle { color: #a8b8d8 !important; font-size: 0.85rem; margin-top: 4px; }
    .app-header * { color: white !important; }
    .app-header .subtitle, .app-header .subtitle * { color: #a8b8d8 !important; }

    /* ── Buttons ───────────────────────────────────────────────────────────── */
    .stButton > button {
        background-color: #1a2a4a !important;
        color: white !important;
        border: none !important;
        border-radius: 6px;
        padding: 10px 28px;
        font-size: 1rem;
        font-weight: 600;
    }
    .stButton > button:hover {
        background-color: #2d4a8a !important;
        color: white !important;
    }
    .stButton > button * { color: white !important; }

    /* Download button */
    [data-testid="stDownloadButton"] > button {
        background-color: #1e6b3a !important;
        color: white !important;
        border: none !important;
    }
    [data-testid="stDownloadButton"] > button:hover {
        background-color: #2a8f4e !important;
    }
    [data-testid="stDownloadButton"] > button * { color: white !important; }

    /* ── Cards ─────────────────────────────────────────────────────────────── */
    .info-card {
        background: #e8f0fe !important;
        border-left: 4px solid #1a2a4a;
        padding: 10px 16px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        font-size: 0.88rem;
    }
    .info-card, .info-card * { color: #1a1a2e !important; }

    .error-card {
        background: #fdecea !important;
        border-left: 4px solid #c0392b;
        padding: 10px 16px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        font-size: 0.88rem;
    }
    .error-card, .error-card * { color: #5a1a1a !important; }

    .success-card {
        background: #e6f4ea !important;
        border-left: 4px solid #1e6b3a;
        padding: 10px 16px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        font-size: 0.88rem;
    }
    .success-card, .success-card * { color: #1a3a1a !important; }

    /* ── Log box ───────────────────────────────────────────────────────────── */
    .log-box {
        background: #0d1117 !important;
        font-family: 'Courier New', monospace;
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
    .log-box, .log-box * { color: #c9d1d9 !important; }

    /* ── File list ─────────────────────────────────────────────────────────── */
    .file-list {
        background: #ffffff !important;
        border: 1px solid #dde3ec;
        border-radius: 8px;
        padding: 8px 12px;
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        max-height: 300px;
        overflow-y: auto;
        line-height: 1.6;
    }
    .file-list, .file-list * { color: #1a1a2e !important; }
    .file-list .file-item {
        padding: 2px 0;
        border-bottom: 1px solid #f0f2f5;
    }

    /* ── Empty state ───────────────────────────────────────────────────────── */
    .empty-state {
        height: 280px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #eef1f7 !important;
        border-radius: 8px;
        border: 1px dashed #bbc4d8;
        font-size: 0.95rem;
        text-align: center;
        padding: 20px;
    }
    .empty-state, .empty-state * { color: #6b7a90 !important; }

    /* ── Footer ────────────────────────────────────────────────────────────── */
    .footer {
        margin-top: 40px;
        padding-top: 16px;
        border-top: 1px solid #dde3ec;
        font-size: 0.78rem;
        text-align: center;
    }
    .footer, .footer * { color: #8a96a8 !important; }

    /* ── Spinner ───────────────────────────────────────────────────────────── */
    .stSpinner > div { color: #1a1a2e !important; }
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
*(e.g.* `1382 - אולם אירועים` *)*  
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
    else:
        st.markdown("*(config.py not found)*")

    st.markdown("---")
    st.markdown("## 📝 Filename Format")
    st.markdown("""
```
nn-h-L+STxx (DL+LL).pdf
```
- **nn** — serial number
- **h** — slab height (cm)
- **L** — span length (cm)
- **ST** — topping width (cm)
- **DL+LL** — dead + live load (kg/m²)

Example:
```
01-40-1385+ST25 (350+500).pdf
```
""")

    st.markdown("---")
    st.markdown("## 💡 Tips")
    st.markdown("""
- Upload all PDFs for **one floor** at a time
- Factory is auto-detected from project number:
  - `1000–1999` → Sela
  - `2200–2999` → Ramet
  - `YY-MM` format → Haifa
- The report includes title page, legend, TOC with clickable links, page numbers, and loading annotations
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
if "report_pdf" not in st.session_state:
    st.session_state.report_pdf = None
if "report_filename" not in st.session_state:
    st.session_state.report_filename = None
if "build_log" not in st.session_state:
    st.session_state.build_log = None
if "build_success" not in st.session_state:
    st.session_state.build_success = False


# ── Utility: detect factory from project number ──────────────────────────────
def detect_factory_key(proj_num: str) -> str:
    """Auto-detect factory from project number."""
    if not proj_num:
        return ""
    if hasattr(cfg, 'detect_factory'):
        return cfg.detect_factory(proj_num)
    return ""


# ── Main layout ───────────────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1.4], gap="large")


# ═══════════════════════════════════════════════════════════════════════════════
#  LEFT COLUMN — Input & Settings
# ═══════════════════════════════════════════════════════════════════════════════
with col_left:
    # ── Project Folder Name (auto-fill) ──────────────────────────────────────
    st.markdown("### 📁 Project Folder Name")
    st.markdown(
        '<div class="info-card">💡 Paste the <b>folder name</b> from your project '
        'directory to auto-fill project number, name &amp; factory.</div>',
        unsafe_allow_html=True,
    )

    folder_name = st.text_input(
        "Folder name",
        placeholder="e.g. 1382 - אולם אירועים  or  26-09 - קיסריה מרלוג",
        label_visibility="collapsed",
    )

    # Parse folder name → project number + name
    parsed_num = ""
    parsed_name = ""
    if folder_name.strip():
        m = re.match(r"([\d\-A-Za-z]+)\s*[-–—]\s*(.+)", folder_name.strip())
        if m:
            parsed_num = m.group(1).strip()
            parsed_name = m.group(2).strip()

    st.markdown("---")

    # ── Upload PDF Files ─────────────────────────────────────────────────────
    st.markdown("### 📂 Upload PDF Files")

    uploaded_files = st.file_uploader(
        "Upload calculation PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        help="Upload all PDF calculation files for one floor/level",
    )

    if uploaded_files:
        # Filter out any obvious report files
        valid_files = [f for f in uploaded_files
                       if "Static_Calculations_Report" not in f.name
                       and not f.name.replace(".pdf", "").endswith("_report")]

        st.markdown(f'<div class="info-card">📄 <b>{len(valid_files)} PDF file(s)</b> uploaded</div>',
                    unsafe_allow_html=True)

        # Show file list
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
        value=parsed_num,
        placeholder="e.g. 1382, 26-09, 2501",
    )

    # Auto-detect factory
    auto_factory = detect_factory_key(proj_num)

    proj_name = st.text_input(
        "Project Name",
        value=parsed_name,
        placeholder="e.g. אולם אירועים",
    )

    floor_name = st.text_input("Floor / Level", placeholder="e.g. +0.00, +14, גג")

    # Factory selector
    factory_options = {}
    if CONFIG_OK:
        factory_options = {k: f"{v['name']} ({k})" for k, v in cfg.FACTORIES.items()}

    factory_keys = list(factory_options.keys())
    factory_labels = list(factory_options.values())

    default_idx = 0
    if auto_factory and auto_factory in factory_keys:
        default_idx = factory_keys.index(auto_factory)

    factory_selection = st.selectbox(
        "Factory",
        options=factory_keys,
        format_func=lambda k: factory_options.get(k, k),
        index=default_idx,
        help="Auto-detected from project number when possible",
    )

    if auto_factory and auto_factory == factory_selection:
        st.markdown(f'<div class="info-card">🏭 Factory auto-detected: <b>{factory_options.get(auto_factory, auto_factory)}</b></div>',
                    unsafe_allow_html=True)

    engineer_name = st.text_input(
        "Engineer",
        value=getattr(cfg, 'DEFAULT_ENGINEER', 'שמעון דונן'),
        help="Engineer name for the report title page",
    )

    # Options
    st.markdown("---")
    annotate_loading = st.checkbox(
        "✏️ Annotate Loading pages",
        value=True,
        help="Add load annotations on Loading pages (requires annotate_loading.py)",
        disabled=not ANNOTATE_OK,
    )
    if not ANNOTATE_OK:
        st.caption("⚠️ annotate_loading.py not found — annotations disabled")

    # ── Build button ──────────────────────────────────────────────────────────
    st.markdown("---")
    build_clicked = st.button("▶  Build Report", use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  RIGHT COLUMN — Output & Download
# ═══════════════════════════════════════════════════════════════════════════════
with col_right:
    st.markdown("### 📊 Report Output")

    # ── Build action ──────────────────────────────────────────────────────────
    if build_clicked:
        # Validate inputs
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
            st.markdown(f'<div class="error-card">⚠️ <b>Cannot build report:</b><br>{err_html}</div>',
                        unsafe_allow_html=True)
        else:
            # ── Run the build ─────────────────────────────────────────────────
            with st.spinner("Building report... This may take a moment."):
                tmpdir = None
                try:
                    # Create temp directory structure
                    tmpdir = tempfile.mkdtemp(prefix="arme_report_")
                    project_dir = Path(tmpdir) / f"{proj_num.strip()} - {proj_name.strip()}"
                    floor_dir = project_dir / floor_name.strip()
                    floor_dir.mkdir(parents=True, exist_ok=True)

                    # Copy logos to temp dir if available
                    logos_src = SCRIPT_DIR / "logos"
                    logos_dst = Path(tmpdir) / "logos"
                    if logos_src.exists():
                        shutil.copytree(str(logos_src), str(logos_dst))
                    else:
                        # Try to find logo files in SCRIPT_DIR directly
                        logos_dst.mkdir(exist_ok=True)
                        for img_ext in ["*.jpg", "*.jpeg", "*.png", "*.gif"]:
                            for img in SCRIPT_DIR.glob(img_ext):
                                shutil.copy2(str(img), str(logos_dst / img.name))

                    # Point engine to temp logos
                    old_logos_dir = engine.LOGOS_DIR
                    if logos_dst.exists():
                        engine.LOGOS_DIR = logos_dst

                    # Save uploaded PDFs to floor directory
                    for uf in valid_files:
                        pdf_path = floor_dir / uf.name
                        pdf_path.write_bytes(uf.getbuffer())

                    # Capture stdout for log
                    old_stdout = sys.stdout
                    sys.stdout = log_capture = io.StringIO()

                    # Patch parse_project_folder for our temp structure
                    orig_parse = engine.parse_project_folder
                    p_num = proj_num.strip()
                    p_name = proj_name.strip()
                    def patched_parse(fp):
                        fp_name = Path(fp).name
                        m = re.match(r"([\d-]+)\s*-\s*(.+)", fp_name)
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
                            floor_name=floor_name.strip(),
                            no_annotate=not annotate_loading,
                        )
                    finally:
                        engine.parse_project_folder = orig_parse
                        engine.LOGOS_DIR = old_logos_dir

                    sys.stdout = old_stdout
                    log_output = log_capture.getvalue()

                    # Read the generated PDF
                    if output_path and Path(output_path).exists():
                        report_bytes = Path(output_path).read_bytes()
                        report_name = Path(output_path).name
                        st.session_state.report_pdf = report_bytes
                        st.session_state.report_filename = report_name
                        st.session_state.build_log = log_output
                        st.session_state.build_success = True
                    else:
                        st.session_state.report_pdf = None
                        st.session_state.build_log = log_output + "\n\nERROR: Output file not created."
                        st.session_state.build_success = False

                except Exception as e:
                    sys.stdout = old_stdout if 'old_stdout' in dir() else sys.__stdout__
                    log_text = log_capture.getvalue() if 'log_capture' in dir() else ""
                    st.session_state.report_pdf = None
                    st.session_state.build_log = f"{log_text}\n\nERROR: {type(e).__name__}: {e}"
                    st.session_state.build_success = False

                finally:
                    # Cleanup temp directory
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

        # Download button
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
<div class="empty-state">
    <div>
        <div style="font-size:2.5rem; margin-bottom:10px;">📐</div>
        Upload PDF files, fill in project details,<br>
        and click <b>&nbsp;▶ Build Report</b> to generate.
    </div>
</div>
""", unsafe_allow_html=True)


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="footer">
    {ORG_NAME} &nbsp;·&nbsp; {ORG_EMAIL} &nbsp;·&nbsp; {ENGINEER} &nbsp;·&nbsp; Build Report Generator v{APP_VER}
</div>
""", unsafe_allow_html=True)
