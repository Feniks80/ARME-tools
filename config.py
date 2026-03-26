# config.py — organization & factory settings
# ARME Engineers | trom@arme.co.il | Shimon Donen
# ═══════════════════════════════════════════════════════════════

# ── Organization ─────────────────────────────────────────────
ORG_NAME     = "ARME ENGINEERS"
ORG_NAME_HE  = "ארמה מהנדסים"
ORG_LOGO     = "Arme.jpg"

# ── Default engineer ─────────────────────────────────────────
DEFAULT_ENGINEER = "שמעון דונן"
DEFAULT_EMAIL    = "trom@arme.co.il"

# ── Accent color (RGB 0.0–1.0) ──────────────────────────────
ACCENT_COLOR = (0.10, 0.25, 0.50)

# ── Projects root folder ────────────────────────────────────
PROJECTS_ROOT = r"p:\Claude\projects\Build_report"

# ── Factories ────────────────────────────────────────────────
# Each factory has: name (Hebrew), subtitle, logo file, calc_type, email
# email is used on the title page of generated PDF reports
FACTORIES = {
    "sela": {
        "name":      "סלע בן ארי",
        "subtitle":  "לוחות דרוכים",
        "logo":      "SelaBenAri.png",
        "calc_type": 'לוח"דים',
        "email":     "s-ba@arme.co.il",
    },
    "haifa": {
        "name":      "שיכון ובינוי סולל בונה",
        "subtitle":  "מפעל חיפה",
        "logo":      "Haifa.jpg",
        "calc_type": 'לוח"דים',
        "email":     "trom@arme.co.il",
    },
    "ramet": {
        "name":      "רמת טרום",
        "subtitle":  "",
        "logo":      "Ramet.png",
        "calc_type": 'לוח"דים',
        "email":     "trom@arme.co.il",
    },
    "arad": {
        "name":      "ערד הארץ",
        "subtitle":  "",
        "logo":      "Arad.jpg",
        "calc_type": 'לוח"דים',
        "email":     "trom@arme.co.il",
    },
    "denia": {
        "name":      "סיבוס רימון",
        "subtitle":  "",
        "logo":      "Denia.png",
        "calc_type": 'לוח"דים',
        "email":     "trom@arme.co.il",
    },
}

# ── Auto-detect factory by project number ────────────────────
def detect_factory(project_num: str) -> str:
    """
    Detect factory key by project number pattern.

    Ranges:
        1000-1999       → sela (Sela Ben Ari)
        2200-2999       → ramet (Ramet Trom)
        6900+           → denia (Denia Sibus)
        YY-MM (25-08)   → haifa (2-digit year, 2-3 digit number)
        YYYY-NN (2025-17) → arad (4-digit year, then number)
    """
    import re

    # Arad: YYYY-NN format (4-digit year - number)
    if re.match(r"^\d{4}-\d{1,3}$", project_num):
        return "arad"

    # Haifa: YY-MM format (2-digit year - 2-3 digit number)
    if re.match(r"^\d{2}-\d{2,3}$", project_num):
        return "haifa"

    # Numeric ranges
    try:
        n = int(project_num)
    except ValueError:
        return ""

    if 1000 <= n <= 1999:
        return "sela"
    if 2200 <= n <= 2999:
        return "ramet"
    if n >= 6900:
        return "denia"

    return ""
