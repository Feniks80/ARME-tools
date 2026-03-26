"""
pret_loads_app.py — ARME Engineers | PRET Loads Calculator (Streamlit web app)
trom@arme.co.il | Shimon Donen

Run:
    streamlit run pret_loads_app.py

Requires:
    pip install streamlit
    (pret_loads.py must be in the same folder)
"""

import streamlit as st
import re
import os
import io
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PRET Loads Calculator — ARME Engineers",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Import engine ─────────────────────────────────────────────────────────────
try:
    import pret_loads as engine
    ENGINE_OK = True
except ImportError:
    ENGINE_OK = False

# ── Metadata constants ────────────────────────────────────────────────────────
ORG_NAME   = "ARME Engineers"
ORG_EMAIL  = "trom@arme.co.il"
ENGINEER   = "Shimon Donen"
APP_VER    = "2.1 (web)"

# ── Custom CSS ────────────────────────────────────────────────────────────────
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

    /* Monospace output */
    .result-box {
        background: #0d1117;
        color: #c9d1d9;
        font-family: 'Courier New', Courier, monospace;
        font-size: 11px;
        padding: 16px;
        border-radius: 8px;
        overflow-x: scroll;
        white-space: pre;
        line-height: 1.45;
        border: 1px solid #30363d;
        min-width: 0;
        max-width: 100%;
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

    /* Info / error cards */
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
    <h1>🏗️ PRET Loads Calculator</h1>
    <div class="subtitle">{ORG_NAME} &nbsp;|&nbsp; {ORG_EMAIL} &nbsp;|&nbsp; {ENGINEER} &nbsp;|&nbsp; v{APP_VER}</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Sidebar — Help & Format ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📋 Input Format")
    st.markdown("""
**Line 1:** Project number + level
```
2309 -2
```
**Line 2:** Loads DL+LL  
*(kg/m² if ≥ 50, else t/m²)*
```
100+250
```
**Line 3:** Section h+topping (cm)
```
20+5
```
**Line 4:** Lengths (cm if ≥ 100, else m)
```
L=720, 735, 575
```
**Line 5:** Topping widths ST (cm)
```
ST40,50,60
```
""")

    st.markdown("---")
    st.markdown("## 📐 Constants")
    st.markdown(f"""
| Parameter | Value |
|---|---|
| Strip width B | 1.20 m |
| Concrete density | 2.50 t/m³ |
| Kspr factor | 0.96 |
| Lsprd max | 150 cm |
""")

    st.markdown("---")
    st.markdown("## 💡 Tips")
    st.markdown("""
- Multiple projects: separate with blank line
- `7,85` = `7.85` (comma decimal OK)
- ST can be on L= line: `L=7.75+ST50,60`
- Multiple lengths: `L=7.20, 7.35, 6.00`
""")

    st.markdown("---")
    st.caption(f"© {datetime.now().year} {ORG_NAME}")


# ── Engine check ──────────────────────────────────────────────────────────────
if not ENGINE_OK:
    st.markdown("""
<div class="error-card">
⚠️ <b>pret_loads.py not found.</b><br>
Place <code>pret_loads.py</code> in the same folder as this app and restart.
</div>
""", unsafe_allow_html=True)
    st.stop()


# ── Example data ──────────────────────────────────────────────────────────────
EXAMPLE = """2309 -2
100+250
20+5
L=720, 735, 575
ST40,50,60

250+500
20+5
L=7.85
ST50
"""

# ── State init ────────────────────────────────────────────────────────────────
if "result_text" not in st.session_state:
    st.session_state.result_text = None
if "report_text" not in st.session_state:
    st.session_state.report_text = None
if "n_projects" not in st.session_state:
    st.session_state.n_projects = 0
if "input_text" not in st.session_state:
    st.session_state.input_text = EXAMPLE


# ── Main layout ───────────────────────────────────────────────────────────────
col_in, col_out = st.columns([1, 1.6], gap="large")

# ─── LEFT: Input ──────────────────────────────────────────────────────────────
with col_in:
    st.markdown("### ✏️ Input Data")

    input_text = st.text_area(
        label="Enter project data:",
        value=st.session_state.input_text,
        height=340,
        placeholder="2309 -2\n100+250\n20+5\nL=720, 735\nST40,50",
        label_visibility="collapsed",
    )
    st.session_state.input_text = input_text

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        calc_clicked = st.button("▶  Calculate", use_container_width=True)
    with c2:
        clear_clicked = st.button("🗑 Clear", use_container_width=True)
    with c3:
        example_clicked = st.button("📄 Example", use_container_width=True)

    if clear_clicked:
        st.session_state.input_text = ""
        st.session_state.result_text = None
        st.session_state.report_text = None
        st.rerun()

    if example_clicked:
        st.session_state.input_text = EXAMPLE
        st.session_state.result_text = None
        st.session_state.report_text = None
        st.rerun()

    # ── Upload file ──
    st.markdown("---")
    st.markdown("**Or upload a .txt file:**")
    uploaded = st.file_uploader("Upload input file", type=["txt"], label_visibility="collapsed")
    if uploaded:
        content = uploaded.read().decode("utf-8", errors="replace")
        st.session_state.input_text = content
        st.session_state.result_text = None
        st.session_state.report_text = None
        st.rerun()


# ─── RIGHT: Output ────────────────────────────────────────────────────────────
with col_out:
    st.markdown("### 📊 Results")

    # ── Calculate ──
    if calc_clicked:
        text = input_text.strip()
        if not text:
            st.session_state.result_text = None
            st.warning("Please enter input data first.")
        else:
            with st.spinner("Calculating..."):
                try:
                    projects = engine.parse_text(text)
                    if not projects:
                        st.session_state.result_text = "INPUT ERROR: No projects found.\n\nFirst line must be a project number (e.g. '2309 -2')."
                        st.session_state.report_text = None
                        st.session_state.n_projects = 0
                    else:
                        # Validate
                        all_errors = []
                        for proj_id, mark, slabs in projects:
                            errs = engine._validate_slabs(slabs)
                            all_errors.extend(errs)

                        if all_errors:
                            err_msg = "INPUT ERROR — Please fix:\n\n"
                            for e in sorted(set(all_errors)):
                                err_msg += f"  • {e}\n"
                            st.session_state.result_text = err_msg
                            st.session_state.report_text = None
                            st.session_state.n_projects = 0
                        else:
                            # Build display results
                            lines = []
                            for proj_id, mark, slabs in projects:
                                lines.append(engine.format_output_gui(proj_id, mark, slabs))
                            st.session_state.result_text = "\n".join(lines)

                            # Build full report (for download)
                            report_lines = []
                            # Metadata header
                            report_lines.append(f"# {ORG_NAME} | {ORG_EMAIL} | {ENGINEER}")
                            report_lines.append(f"# Generated: {datetime.now():%Y-%m-%d %H:%M}  |  PRET Loads Calculator v{APP_VER}")
                            report_lines.append("")
                            for proj_id, mark, slabs in projects:
                                report_lines.append(engine.format_output_file(proj_id, mark, slabs, text))
                            st.session_state.report_text = "\n".join(report_lines)
                            st.session_state.n_projects = len(projects)

                except Exception as e:
                    st.session_state.result_text = f"ERROR: {e}"
                    st.session_state.report_text = None
                    st.session_state.n_projects = 0

    # ── Display result ──
    if st.session_state.result_text:
        result = st.session_state.result_text
        is_error = result.startswith("INPUT ERROR") or result.startswith("ERROR")

        if is_error:
            st.markdown(f'<div class="error-card">⚠️ {result.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="success-card">✅ <b>{st.session_state.n_projects} project(s) calculated</b></div>', unsafe_allow_html=True)

            # Result display — st.code gives native horizontal scroll
            st.code(result, language=None)

            # ── Download button ──
            if st.session_state.report_text:
                now_str = datetime.now().strftime("%Y%m%d_%H%M")
                filename = f"PRET_Loads_{now_str}.txt"
                st.markdown("---")
                st.download_button(
                    label="⬇️  Download Report (.txt)",
                    data=st.session_state.report_text.encode("utf-8"),
                    file_name=filename,
                    mime="text/plain",
                    use_container_width=True,
                )
                st.caption(f"File will be saved as: `{filename}`")
    else:
        st.markdown("""
<div style="height:220px; display:flex; align-items:center; justify-content:center;
            background:#eef1f7; border-radius:8px; border:1px dashed #bbc4d8;
            color:#8a96a8; font-size:0.95rem;">
    Enter input data and click <b>&nbsp;▶ Calculate</b>
</div>
""", unsafe_allow_html=True)


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="footer">
    {ORG_NAME} &nbsp;·&nbsp; {ORG_EMAIL} &nbsp;·&nbsp; {ENGINEER} &nbsp;·&nbsp; PRET Loads Calculator v{APP_VER}
</div>
""", unsafe_allow_html=True)
