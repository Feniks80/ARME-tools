# config.py — настройки организации и заводов
# ═══════════════════════════════════════════════════════════════

# ── Организация ──────────────────────────────────────────────
ORG_NAME     = "ARME ENGINEERS"
ORG_NAME_HE  = "ארמה מהנדסים"
ORG_LOGO     = "Arme.jpg"

# ── Инженер по умолчанию ─────────────────────────────────────
DEFAULT_ENGINEER = "שמעון דונן"
DEFAULT_EMAIL    = "trom@arme.co.il"

# ── Цвет акцента (RGB 0.0–1.0) ──────────────────────────────
ACCENT_COLOR = (0.10, 0.25, 0.50)

# ── Корневая папка проектов ──────────────────────────────────
PROJECTS_ROOT = r"p:\Claude\projects\Build_report"

# ── Заводы ───────────────────────────────────────────────────
# email на уровне завода: если указан — используется вместо DEFAULT_EMAIL
FACTORIES = {
    "sela": {
        "name":      "סלע בן ארי",
        "subtitle":  "לוחות דרוכים",
        "logo":      "SelaBenAri.png",
        "calc_type": 'לוח"דים',
        "email":     "s-ba@arme.co.il",
    },
    "haifa": {
        "name":      "מפעל חיפה",
        "subtitle":  "",
        "logo":      "Haifa.jpg",
        "calc_type": 'לוח"דים',
    },
    "ramet": {
        "name":      "רמת טרום",
        "subtitle":  "",
        "logo":      "Ramet.png",
        "calc_type": 'לוח"דים',
    },
}

# ── Автодетект завода по номеру проекта ──────────────────────
def detect_factory(project_num: str) -> str:
    """Определяет завод по номеру проекта."""
    import re
    # Haifa: формат YY-MM (две цифры - две цифры)
    if re.match(r"^\d{2}-\d{2}$", project_num):
        return "haifa"
    # Числовой номер
    try:
        n = int(project_num)
    except ValueError:
        return ""
    if 1000 <= n <= 1999:
        return "sela"
    if 2200 <= n <= 2999:
        return "ramet"
    return ""

def get_email(factory_key: str = "") -> str:
    """Возвращает email для завода. Если у завода свой email — его, иначе DEFAULT_EMAIL."""
    if factory_key and factory_key in FACTORIES:
        factory_email = FACTORIES[factory_key].get("email", "")
        if factory_email:
            return factory_email
    return DEFAULT_EMAIL
