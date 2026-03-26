"""
pret_loads.py — slab load calculator for PRET (FEM)

Organization: ARME Engineers (ארמה מהנדסים)
Email: trom@arme.co.il
Engineer: Shimon Donen (שמעון דונן)

INPUT FORMAT:
─────────────────────────────────────────────
2309 -2          ← project number + level
100+250          ← load DL+LL (kg/m² if >=50, else t/m²)
20+5             ← section h+topping (cm)
L=720, 735, 575  ← lengths (cm if >=100, else m)
ST40,50,60       ← topping widths (cm), multiple variants

250+500          ← next load
20+5             ← same or different section
L=7.85
ST50

─────────────────────────────────────────────
USAGE:
  python pret_loads.py               ← interactive input
  python pret_loads.py input.txt     ← from file
  python pret_loads.py input.txt -o results/  ← save to folder
"""

import re
import sys
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from itertools import groupby

BAND = 1.20    # strip width, m
RHO  = 2.50    # concrete density, t/m³
KSPR = 0.96    # Kspr coefficient
LSPRD_MAX_CM = 150  # max Lsprd value, cm

# ─── Organization metadata (embedded in saved reports) ────────────────────────
ORG_NAME    = "ARME ENGINEERS"
ORG_EMAIL   = "trom@arme.co.il"
ORG_VERSION = "2.1"


# ─── Helper functions ─────────────────────────────────────────────────────────

def _fix_decimal(s: str) -> str:
    """Replace comma decimal separators with dots: 7,85 -> 7.85"""
    return re.sub(r'(\d),(\d)', r'\1.\2', s)

def _to_float(s: str) -> float:
    return float(_fix_decimal(s.strip()))

def _load_val(x: float) -> float:
    """Convert: if >=50 -> kg/m² -> t/m²"""
    return x / 1000.0 if x >= 50 else x

def _fmt(x: float) -> str:
    """Format: 3 decimal places, standard math rounding"""
    return f"{round(x, 3):.3f}"

def _fmt2(x: float) -> str:
    """Format: 2 decimal places"""
    return f"{round(x, 2):.2f}"

def _is_section(a: float, b: float) -> bool:
    """True if this is an h+top section (h=10-60cm, top=0-20cm, both integers)"""
    return (0 < a <= 60 and 0 <= b <= 20
            and a == int(a) and b == int(b))

def _parse_lengths(s: str) -> List[float]:
    """Parse length string: '720, 735, 575' or '7.20, 7.35' -> list in meters"""
    s = re.sub(r'(?i)^L\s*=\s*', '', s.strip())
    vals = []
    for tok in re.split(r'[\s;,]+', s):
        tok = tok.strip()
        if not tok:
            continue
        tok = _fix_decimal(tok)
        try:
            v = float(tok)
            vals.append(v / 100.0 if v >= 100 else v)
        except ValueError:
            continue
    return sorted(set(vals))

def _parse_st(s: str) -> List[int]:
    """Parse 'ST40,50,60' -> [40, 50, 60]"""
    m = re.search(r'(?i)ST\s*([0-9][0-9,\s]*)', s)
    if not m:
        return []
    vals = []
    for tok in re.split(r'[\s,]+', m.group(1).strip()):
        if tok:
            try:
                vals.append(int(float(tok)))
            except ValueError:
                pass
    return sorted(set(vals))


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class Slab:
    dl: float
    ll: float
    h_cm: int
    top_cm: int
    length_m: float
    st_list: List[int] = field(default_factory=list)
    load_idx: int = 0
    sec_idx: int = 0


# ─── Input validation ─────────────────────────────────────────────────────────

class InputError(Exception):
    """Raised when input data is malformed."""
    pass


def _validate_slabs(slabs: List[Slab]) -> List[str]:
    """Validate parsed slabs and return list of error messages (empty if ok)."""
    errors = []
    for s in slabs:
        if s.dl < 0:
            errors.append(f"DL must be >= 0 (got {s.dl})")
        if s.ll < 0:
            errors.append(f"LL must be >= 0 (got {s.ll})")
        if s.dl <= 0 and s.ll <= 0:
            errors.append(f"DL and LL cannot both be 0")
        if s.h_cm <= 0 or s.h_cm > 100:
            errors.append(f"Section height h={s.h_cm} cm is out of range (1-100)")
        if s.length_m <= 0 or s.length_m > 30:
            errors.append(f"Length L={s.length_m:.2f} m is out of range (0-30)")
        if not s.st_list:
            errors.append(
                f"No ST defined for h={s.h_cm} L={s.length_m:.2f}m "
                f"(DL={s.dl:.3f} LL={s.ll:.3f})"
            )
        for st in s.st_list:
            if st <= 0 or st > 200:
                errors.append(f"ST={st} cm is out of range (1-200)")
    return list(set(errors))  # deduplicate


# ─── Text parsing ─────────────────────────────────────────────────────────────

def _parse_block(lines: List[str]) -> Tuple[str, Optional[str], List[Slab]]:
    """Parse one block (one project). First line is the header."""
    if not lines:
        return '', None, []

    # Header: "2309 -2" -> id="2309", mark="-2"
    header = lines[0].strip()
    m = re.match(r'^(.+?)\s*([+-]\d+(?:[.,]\d+)?(?:\s*[A-Za-zА-Яа-я]*)?)?\s*$', header)
    proj_id = header
    mark = None
    if m:
        proj_id = m.group(1).strip()
        mark = m.group(2).strip() if m.group(2) else None

    slabs: List[Slab] = []
    cur_dl: Optional[float] = None
    cur_ll: Optional[float] = None
    cur_h: Optional[int] = None
    cur_top: Optional[int] = None
    cur_st: List[int] = []       # current effective ST for next L= line
    global_st: List[int] = []    # ST defined before first load — applies to all
    load_st: List[int] = []      # ST set at load level (after DL+LL, before sections)
    load_idx = -1
    sec_idx = -1
    pending_lengths: List[float] = []   # lengths waiting for ST
    has_section_in_load = False   # whether we've seen a section in current load

    for raw in lines[1:]:
        line = raw.strip()
        if not line:
            continue

        fixed = _fix_decimal(line)

        # ── ST-only line (no L=) ──────────────────────────────────────────
        if re.search(r'(?i)ST\d', line) and not re.search(r'(?i)\bL\s*=', line):
            st = _parse_st(line)
            if st:
                if load_idx == -1:
                    # Before first load — global ST
                    global_st = st
                    load_st = st
                    cur_st = st
                elif pending_lengths:
                    # ST came after L= — apply to pending lengths only (local)
                    for Lm in pending_lengths:
                        slabs.append(Slab(
                            dl=cur_dl, ll=cur_ll,
                            h_cm=cur_h, top_cm=cur_top,
                            length_m=Lm, st_list=st,
                            load_idx=load_idx, sec_idx=sec_idx
                        ))
                    pending_lengths = []
                    # Don't change load_st — this ST is local to this section
                    cur_st = st
                elif not has_section_in_load:
                    # ST after load line but before any section — load-level default
                    load_st = st
                    cur_st = st
                else:
                    # ST after a section header but before L= — section-level default
                    cur_st = st
            continue

        # ── L= line ───────────────────────────────────────────────────────
        if re.search(r'(?i)\bL\s*=', line) or (
            re.fullmatch(r'[\d.,\s;]+', fixed) and cur_h is not None and cur_dl is not None
        ):
            # Inline ST in L-line: "L=7.75+ST50,60"
            st_inline = _parse_st(line)
            clean = re.sub(r'(?i)\bST\s*[0-9][0-9,\s]*', '', line)
            lengths = _parse_lengths(clean)
            if not lengths:
                continue

            st_to_use = st_inline if st_inline else cur_st
            if st_to_use:
                for Lm in lengths:
                    slabs.append(Slab(
                        dl=cur_dl, ll=cur_ll,
                        h_cm=cur_h, top_cm=cur_top,
                        length_m=Lm, st_list=st_to_use,
                        load_idx=load_idx, sec_idx=sec_idx
                    ))
                pending_lengths = []
            else:
                # ST not known yet — put lengths on hold
                pending_lengths = lengths
            continue

        # ── DL+LL or h+top ────────────────────────────────────────────────
        m2 = re.match(r'^(-?\d+(?:[.,]\d+)?)\s*\+\s*(-?\d+(?:[.,]\d+)?)$', fixed)
        if m2:
            a = float(m2.group(1))
            b = float(m2.group(2))
            if _is_section(a, b):
                # Section h+top — reset cur_st to load-level default
                cur_h = int(a)
                cur_top = int(b)
                has_section_in_load = True
                # Reset to load-level ST (not previous section's local ST)
                cur_st = list(load_st)
                sec_idx += 1
                pending_lengths = []
            else:
                # Load DL+LL — reset everything, restore global
                cur_dl = _load_val(a)
                cur_ll = _load_val(b)
                cur_h = None
                cur_top = None
                load_st = list(global_st)  # reset load-level ST to global
                cur_st = list(global_st)
                has_section_in_load = False
                load_idx += 1
                sec_idx = -1
                pending_lengths = []
            continue

    # If pending_lengths remain without ST — add without ST (will be flagged as error)
    if pending_lengths and cur_dl is not None and cur_h is not None:
        for Lm in pending_lengths:
            slabs.append(Slab(
                dl=cur_dl, ll=cur_ll,
                h_cm=cur_h, top_cm=cur_top,
                length_m=Lm, st_list=[],
                load_idx=load_idx, sec_idx=sec_idx
            ))

    return proj_id, mark, slabs


def _is_header(s: str) -> bool:
    """
    Project header: starts with digits, but is NOT a pair X+Y (load/section),
    NOT a length line (L=...) and NOT an ST line.
    Examples: '6901', '6901 +2', '6901 -2', '2309 floor3'
    """
    fixed = _fix_decimal(s)
    if not re.match(r'^\d', s):
        return False
    if re.match(r'^\d+\+\d+\s*$', fixed):
        return False
    if re.search(r'(?i)\bL\s*=', s):
        return False
    if re.search(r'(?i)\bST\d', s):
        return False
    return True


def parse_text(text: str) -> List[Tuple[str, Optional[str], List[Slab]]]:
    """Split text into blocks by project headers and parse each."""
    lines = [l.rstrip() for l in text.splitlines()]
    blocks: List[List[str]] = []
    cur: Optional[List[str]] = None

    for line in lines:
        s = line.strip()
        if s and _is_header(s):
            cur = [line]
            blocks.append(cur)
        elif cur is not None:
            cur.append(line)

    results = []
    for block in blocks:
        pid, mark, slabs = _parse_block(block)
        if pid:
            results.append((pid, mark, slabs))
    return results


# ─── Compute result rows for PRET ─────────────────────────────────────────────

def _compute_lsprd_cm(st_cm: int) -> int:
    """Compute Lsprd in cm, capped at LSPRD_MAX_CM."""
    half_m = (st_cm / 100.0) / 2.0
    raw_cm = round((half_m + BAND) * 100)
    return min(raw_cm, LSPRD_MAX_CM)

def _compute_lspr_max(L_m: float) -> float:
    """Compute Lspr(max) = 0.4 * L"""
    return 0.4 * L_m

def _compute_kspr_max(lspr_max: float) -> float:
    """Compute Kspr(max) = 2 / Lspr(max). Returns 0 if Lspr(max) is 0."""
    if lspr_max <= 0:
        return 0.0
    return 2.0 / lspr_max


def _build_results_section(proj_id: str, mark, slabs: List[Slab]) -> str:
    """Build CALCULATION RESULTS section only (for GUI display)."""

    now = datetime.now().strftime("%Y-%m-%d  %H:%M")
    proj_name = f"{proj_id} {mark}".strip() if mark else proj_id

    sep2 = "=" * 60
    sorted_slabs = sorted(slabs, key=lambda s: (s.load_idx, s.sec_idx, s.length_m))

    lines = []
    lines += [f"Project: {proj_name}    Date: {now}", sep2]
    lines += ["CALCULATION RESULTS:", sep2, ""]

    load_groups = []
    for load_idx, group in groupby(sorted_slabs, key=lambda s: s.load_idx):
        load_groups.append((load_idx, list(group)))

    num_map: Dict[tuple, int] = {}
    counter = 0

    for load_idx, group in load_groups:
        dl = group[0].dl
        ll = group[0].ll
        dl_kgm2 = int(round(dl * 1000))
        ll_kgm2 = int(round(ll * 1000))
        dl12  = dl * BAND
        ll12  = ll * BAND

        # Load header
        lines.append(f"\u2500\u2500 Load {load_idx+1}: DL={dl:.3f} t/m\u00b2  LL={ll:.3f} t/m\u00b2 " + "\u2500" * 20)
        lines.append(f"  Strip loads: DL={dl12:.3f}  LL={ll12:.3f} t/m")

        # Group by section
        sec_groups = []
        for sec_key, sg in groupby(group, key=lambda s: (s.sec_idx, s.h_cm, s.top_cm)):
            sec_groups.append((sec_key, list(sg)))

        row_count = sum(max(len(s.st_list), 1) for _, sg in sec_groups for s in sg)
        sec_count = len(sec_groups)
        local_sts = set()
        for _, sg in sec_groups:
            for s in sg:
                for st in s.st_list:
                    local_sts.add(st)
        st_count = len(local_sts)
        lines.append(f"  {sec_count} sections x {st_count} toppings = {row_count} rows")
        lines.append("")

        for (sec_idx_val, h_cm, top_cm), sec_group in sec_groups:
            sdl12 = (top_cm / 100.0) * RHO * BAND
            lines.append(f"  Section h={h_cm} top={top_cm}:")
            lines.append("")

            _append_table(lines, sec_group, num_map, counter,
                          dl, ll, dl_kgm2, ll_kgm2, dl12, ll12, sdl12)
            # update counter from num_map
            counter = max(num_map.values()) if num_map else 0

            lines.append("")
        lines.append("")

    return "\n".join(lines)


def _append_table(lines, sec_group, num_map, counter_start,
                   dl, ll, dl_kgm2, ll_kgm2, dl12, ll12, sdl12):
    """Append table header + data rows for one section. Updates num_map in place."""

    # Column widths matching the corrected screenshot
    # NAME(35) | Lsprd(5) | DL(5) | LL(5) | SDL(5) | DL-ST(12) | LL-ST(12) | SDL-ST(12) | Lspr(max)(10) | Kspr(max)(9)
    hdr = (
        f"{'NAME':<35s}| {'Lsprd':>5s} | "
        f"{'DL':>5s} | {'LL':>5s} | {'SDL':>5s} | "
        f"{'DL-ST':>12s} | {'LL-ST':>12s} | {'SDL-ST':>12s} | "
        f"{'Lspr(max)':>10s} | {'Kspr(max)':>9s}"
    )
    lines.append(hdr)
    lines.append("-" * len(hdr))

    counter = counter_start
    sec_slabs = sorted(sec_group, key=lambda s: s.length_m)
    for s in sec_slabs:
        base_key = (round(s.dl, 6), round(s.ll, 6), s.h_cm, s.top_cm, int(round(s.length_m * 100)))
        if base_key not in num_map:
            counter += 1
            num_map[base_key] = counter
        nn = num_map[base_key]

        L_m  = s.length_m
        L_cm = int(round(L_m * 100))

        if s.st_list:
            for st_cm in sorted(s.st_list):
                half     = (st_cm / 100.0) / 2.0
                lsprd_cm = _compute_lsprd_cm(st_cm)
                lspr_max = _compute_lspr_max(L_m)
                kspr_max = _compute_kspr_max(lspr_max)
                dl_st    = s.dl * half
                ll_st    = s.ll * half
                conc_st  = half * ((s.h_cm + s.top_cm) / 100.0) * RHO
                name     = f"{nn:02d}-{s.h_cm}-{L_cm}+ST{st_cm} ({dl_kgm2}+{ll_kgm2})"

                dl_st_s   = f"{_fmt(dl_st)}({_fmt(dl_st*KSPR)})"
                ll_st_s   = f"{_fmt(ll_st)}({_fmt(ll_st*KSPR)})"
                conc_st_s = f"{_fmt(conc_st)}({_fmt(conc_st*KSPR)})"

                row = (
                    f"{name:<35s}| "
                    f"{lsprd_cm:>5d} | "
                    f"{_fmt(dl12):>5s} | {_fmt(ll12):>5s} | {_fmt(sdl12):>5s} | "
                    f"{dl_st_s:>12s} | {ll_st_s:>12s} | {conc_st_s:>12s} | "
                    f"{_fmt2(lspr_max):>10s} | {_fmt2(kspr_max):>9s}"
                )
                lines.append(row)
        else:
            name = f"{nn:02d}-{s.h_cm}-{L_cm} ({dl_kgm2}+{ll_kgm2})"
            row = (
                f"{name:<35s}| "
                f"{'--':>5s} | "
                f"{_fmt(dl12):>5s} | {_fmt(ll12):>5s} | {_fmt(sdl12):>5s} | "
                f"{'--':>12s} | {'--':>12s} | {'--':>12s} | "
                f"{'--':>10s} | {'--':>9s}"
            )
            lines.append(row)


def _build_report(proj_id: str, mark, slabs: List[Slab], raw_input: str) -> str:
    """Build full EN report for file saving."""

    now = datetime.now().strftime("%Y-%m-%d  %H:%M")
    proj_name = f"{proj_id} {mark}".strip() if mark else proj_id

    sep  = "-" * 40
    sep2 = "=" * 60
    sorted_slabs = sorted(slabs, key=lambda s: (s.load_idx, s.sec_idx, s.length_m))

    lines = []

    # ── Organization header ──
    lines += [sep2]
    lines.append(f"  {ORG_NAME}  |  {ORG_EMAIL}  |  PRET Loads Calculator v{ORG_VERSION}")
    lines += [sep2, ""]

    # ── Header ──
    lines += [f"Project: {proj_name}    Date: {now}", sep2, ""]

    # ── Input data ──
    lines += ["INPUT DATA:", sep]
    lines += raw_input.strip().splitlines()
    lines += [""]

    # ── Parameters ──
    lines += ["CALCULATION PARAMETERS:", sep]
    lines.append(f"{'Strip width':<20}: {BAND:.2f} m")
    lines.append(f"{'Concrete density':<20}: {RHO:.2f} t/m\u00b3")
    lines.append(f"{'Kspr factor':<20}: {KSPR:.2f}")
    lines += [""]

    # ── Summary ──
    loads_seen: Dict[int, tuple] = {}
    secs_seen:  Dict[tuple, bool] = {}
    sts_seen:   Dict[int, bool] = {}
    lens_seen:  Dict[float, bool] = {}

    for s in sorted_slabs:
        loads_seen[s.load_idx] = (s.dl, s.ll)
        secs_seen[(s.h_cm, s.top_cm)] = True
        for st in s.st_list:
            sts_seen[st] = True
        lens_seen[round(s.length_m, 3)] = True

    loads_str = ", ".join(
        f"{int(round(dl*1000))}+{int(round(ll*1000))}"
        for dl, ll in loads_seen.values()
    )
    loads_tm  = ", ".join(
        f"{dl:.3f}+{ll:.3f}"
        for dl, ll in loads_seen.values()
    )
    secs_str  = ", ".join(f"{h}+{t}" for h, t in sorted(secs_seen))
    sts_str   = ", ".join(str(st) for st in sorted(sts_seen)) + " cm" if sts_seen else "--"
    lens_str  = ", ".join(f"{l:.2f}" for l in sorted(lens_seen)) + " m"

    total_rows = sum(max(len(s.st_list), 1) for s in sorted_slabs)

    lines += ["DATA SUMMARY:", sep]
    lines.append(f"{'Loads':<20}: {loads_str}  (t/m\u00b2: {loads_tm})")
    lines.append(f"{'Sections':<20}: {secs_str}")
    lines.append(f"{'Topping (ST)':<20}: {sts_str}")
    lines.append(f"{'Lengths':<20}: {lens_str}")
    lines.append(f"{'Total rows':<20}: {total_rows}")
    lines += [""]

    # ── Results (reuse same table builder) ──
    lines += ["CALCULATION RESULTS:", sep2, ""]

    load_groups = []
    for load_idx, group in groupby(sorted_slabs, key=lambda s: s.load_idx):
        load_groups.append((load_idx, list(group)))

    num_map: Dict[tuple, int] = {}
    counter = 0

    for load_idx, group in load_groups:
        dl = group[0].dl
        ll = group[0].ll
        dl_kgm2 = int(round(dl * 1000))
        ll_kgm2 = int(round(ll * 1000))
        dl12  = dl * BAND
        ll12  = ll * BAND

        lines.append(f"\u2500\u2500 Load {load_idx+1}: DL={dl:.3f} t/m\u00b2  LL={ll:.3f} t/m\u00b2 " + "\u2500" * 20)
        lines.append(f"  Strip loads: DL={dl12:.3f}  LL={ll12:.3f} t/m")

        sec_groups = []
        for sec_key, sg in groupby(group, key=lambda s: (s.sec_idx, s.h_cm, s.top_cm)):
            sec_groups.append((sec_key, list(sg)))

        row_count = sum(max(len(s.st_list), 1) for _, sg in sec_groups for s in sg)
        sec_count = len(sec_groups)
        local_sts = set()
        for _, sg in sec_groups:
            for s in sg:
                for st in s.st_list:
                    local_sts.add(st)
        st_count = len(local_sts)
        lines.append(f"  {sec_count} sections x {st_count} toppings = {row_count} rows")
        lines.append("")

        for (sec_idx_val, h_cm, top_cm), sec_group in sec_groups:
            sdl12 = (top_cm / 100.0) * RHO * BAND
            lines.append(f"  Section h={h_cm} top={top_cm}:")
            lines.append("")

            _append_table(lines, sec_group, num_map, counter,
                          dl, ll, dl_kgm2, ll_kgm2, dl12, ll12, sdl12)
            counter = max(num_map.values()) if num_map else 0

            lines.append("")
        lines.append("")

    # ── Footer ──
    lines.append(sep2)
    lines.append(f"  Generated by: {ORG_NAME} — PRET Loads Calculator v{ORG_VERSION}")
    lines.append(f"  Contact: {ORG_EMAIL}")
    lines.append(sep2)

    return "\n".join(lines)


def format_output_gui(proj_id: str, mark, slabs: List[Slab]) -> str:
    """Results-only output for GUI display."""
    return _build_results_section(proj_id, mark, slabs)


def format_output_file(proj_id: str, mark, slabs: List[Slab], raw_input: str) -> str:
    """Full report for file saving."""
    return _build_report(proj_id, mark, slabs, raw_input)


# ─── File saving ──────────────────────────────────────────────────────────────

DEFAULT_SAVE_DIR = os.path.join("P:\\", "Claude", "projects", "PRET_loads")

def _save_project(proj_id: str, mark, slabs: List[Slab], raw_input: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    name = f"{proj_id} {mark}".strip() if mark else proj_id
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', name)
    content = format_output_file(proj_id, mark, slabs, raw_input)
    path = os.path.join(output_dir, f"{safe_name}_EN.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Saved: {path}")


# ─── Entry point ──────────────────────────────────────────────────────────────

def process_text(text: str, output_dir=None) -> str:
    projects = parse_text(text)
    if not projects:
        return "INPUT ERROR: No projects found. Please enter data correctly."

    save_dir = output_dir if output_dir else DEFAULT_SAVE_DIR
    all_output = []
    for proj_id, mark, slabs in projects:
        # Validate
        errors = _validate_slabs(slabs)
        if errors:
            err_msg = "INPUT ERROR: Please enter data correctly.\n"
            for e in errors:
                err_msg += f"  - {e}\n"
            return err_msg

        out = format_output_gui(proj_id, mark, slabs)
        all_output.append(out)
        _save_project(proj_id, mark, slabs, text, save_dir)

    return "\n".join(all_output)


def main():
    output_dir = None
    input_file = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ('-o', '--output') and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 2
        else:
            input_file = args[i]
            i += 1

    if input_file:
        with open(input_file, encoding='utf-8') as f:
            text = f.read()
    else:
        print("Enter data (empty line to finish block, Ctrl+D to calculate):")
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        text = "\n".join(lines)

    result = process_text(text, output_dir)
    print(result)


if __name__ == '__main__':
    main()
