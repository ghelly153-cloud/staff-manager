"""Turns raw worksheet grids into employee records + classified rows + issues.

PURE FUNCTIONS (no I/O). A grid is {"values": 2D, "formulas": 2D|None, "hidden": bool}
aligned so index [r][c] == sheet row r+1, column c+1.
Nothing here rewrites or "corrects" source data.
"""
import re
import difflib
from dataclasses import dataclass, field
from .schema import (ALIASES, APP_ALIASES, APP_COLUMNS, CORE_FOR_COMPAT, SUMMARY_LABELS, SUPPORT_PREFIX,
                     blank, col_letter, norm, ref, to_date, to_number)

HEADER_SCAN_ROWS = 15


def cell(grid, r, c):
    try:
        row = grid[r]
        return row[c] if c < len(row) else None
    except IndexError:
        return None


@dataclass
class SheetParse:
    name: str
    compatible: bool = False
    reason: str = ""
    hidden: bool = False
    used_rows: int = 0
    used_cols: int = 0
    header_row: int = -1                                   # 0-based
    cols: dict = field(default_factory=dict)               # key -> col0
    app_cols: dict = field(default_factory=dict)           # existing app helper columns
    app_col_plan: dict = field(default_factory=dict)       # where helper columns go on setup
    rate_label: str = ""
    title: str = ""
    employees: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    row_counts: dict = field(default_factory=dict)
    ignored_rows: list = field(default_factory=list)       # blank preformatted rows
    orphan_rows: list = field(default_factory=list)        # data but no name
    issues: list = field(default_factory=list)
    next_free_row: int = 0                                 # first blank formatted row above Total (0 = none)
    first_row_after_data: int = 0
    formula_count: int = 0


def issue(code, sev, sheet, msg, row=None, field_=None, key=None, detail=None):
    return {"code": code, "severity": sev, "sheet": sheet, "row": row, "field": field_,
            "emp_key": key, "message": msg, "detail": detail}


def find_header(values):
    for r in range(min(HEADER_SCAN_ROWS, len(values))):
        found = {}
        for c, v in enumerate(values[r]):
            n = norm(v)
            if not n:
                continue
            for key, al in ALIASES.items():
                if n in al and key not in found:
                    found[key] = c
            if "rate_year" not in found and re.fullmatch(r"\d{4}perday", n):
                found["rate_year"] = c
        if "name" in found and sum(k in found for k in CORE_FOR_COMPAT) >= 5:
            return r, found
    return None, {}


def _title_close(t, n):
    a, b = norm(t), norm(n)
    return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() > 0.85


def parse_sheet(name, grid):
    values = grid.get("values") or []
    formulas = grid.get("formulas") or values
    sp = SheetParse(name=name, hidden=bool(grid.get("hidden")))
    sp.used_rows = len(values)
    sp.used_cols = max((len(r) for r in values), default=0)
    sp.formula_count = sum(1 for row in formulas for v in row if isinstance(v, str) and v.startswith('='))
    if name.startswith(SUPPORT_PREFIX):
        sp.reason = "App support sheet"
        return sp
    if sp.hidden:
        sp.reason = "Hidden sheet (skipped)"
        sp.issues.append(issue("HIDDEN_SHEET", "info", name, "Sheet is hidden, so it is not shown as a group."))
        return sp
    h, cols = find_header(values)
    if h is None:
        sp.reason = "No recognisable employee header row (needs Staff Name plus the standard columns)"
        return sp
    sp.header_row, sp.cols, sp.compatible = h, cols, True
    if "rate_year" in cols:
        sp.rate_label = str(cell(values, h, cols["rate_year"])).strip()
    for c, v in enumerate(values[h]):
        n = norm(v)
        for key, al in APP_ALIASES.items():
            if n in al:
                sp.app_cols[key] = c
    base = max(max(cols.values()) + 1, sp.used_cols if sp.used_cols > 16 else 16, max(sp.app_cols.values(), default=-1) + 1)
    for i, (key, _) in enumerate(APP_COLUMNS):
        sp.app_col_plan[key] = sp.app_cols.get(key, base + i)
    for r in range(h):
        v = cell(values, r, cols["name"])
        if not blank(v):
            sp.title = str(v).strip()
            break
    if sp.title and norm(sp.title) != norm(name):
        sev = "info" if _title_close(sp.title, name) else "review"
        sp.issues.append(issue("TITLE_MISMATCH", sev, name,
                               f"Sheet tab is “{name}” but the title inside the sheet is “{sp.title}”.", row=1,
                               detail="Source left unchanged. Confirm which is correct."))
    _classify(sp, values, formulas)
    return sp


def _classify(sp, values, formulas):
    n, cols, h = sp.name, sp.cols, sp.header_row
    rc = {"employee": 0, "blank_formatted": 0, "summary": 0, "orphan_populated": 0}
    in_summary = False
    labels = {}
    input_keys = [k for k in ("designation", "location", "staff", "sept", "octo", "rate", "rate_year", "sweet",
                              "aadhaar", "mobile", "from_date", "to_date") if k in cols]
    for r in range(h + 1, len(values)):
        r1 = r + 1
        row = values[r]
        lab = [(c, norm(v)) for c, v in enumerate(row) if isinstance(v, str) and norm(v) in SUMMARY_LABELS]
        if lab:
            in_summary = True
            rc["summary"] += 1
            for c, l in lab:
                labels.setdefault(l, []).append((r1, c))
            continue
        if in_summary:
            if any(not blank(v) for v in row):
                rc["summary"] += 1
            continue
        nm = cell(values, r, cols["name"])
        has_inputs = any(not blank(cell(values, r, cols[k])) for k in input_keys)
        if blank(nm):
            if has_inputs:
                rc["orphan_populated"] += 1
                sp.orphan_rows.append(r1)
                sp.issues.append(issue("NAME_MISSING", "error", n,
                                       "Row has data but no staff name, so it is NOT counted as an employee.", row=r1))
            else:
                rc["blank_formatted"] += 1
                sp.ignored_rows.append(r1)
            continue
        rc["employee"] += 1
        sp.employees.append(_employee(sp, values, formulas, r, r1))
    sp.row_counts = rc
    _summary(sp, values, formulas, labels)


def _numfield(sp, r1, label, v, key, lo=None, hi=None):
    st, val = to_number(v)
    n = sp.name
    if st == "invalid":
        sp.issues.append(issue("VALUE_INVALID", "error", n, f"{label} is not a valid number: “{v}”.", row=r1, field_=label, key=key))
    elif st == "text_number":
        sp.issues.append(issue("NUMBER_AS_TEXT", "info", n, f"{label} is stored as text (“{v}”).", row=r1, field_=label, key=key))
        st = "number"
    if st == "number" and ((lo is not None and val < lo) or (hi is not None and val > hi)):
        sp.issues.append(issue("VALUE_INVALID", "error", n, f"{label} out of range ({val}).", row=r1, field_=label, key=key))
        st, val = "invalid", None
    return {"state": st, "value": val, "raw": v}


def _employee(sp, values, formulas, r, r1):
    n, cols = sp.name, sp.cols
    g = lambda k: cell(values, r, cols[k]) if k in cols else None
    ga = lambda k: cell(values, r, sp.app_cols[k]) if k in sp.app_cols else None
    key = f"{n}|{r1}"
    nm_raw = g("name")
    e = {"sheet": n, "row": r1, "key": key, "name": str(nm_raw), "name_display": " ".join(str(nm_raw).split()),
         "designation": None if blank(g("designation")) else str(g("designation")).strip(),
         "location": None if blank(g("location")) else str(g("location")).strip(),
         "staff_marker": g("staff"), "serial": g("no")}
    if str(nm_raw) != str(nm_raw).strip():
        sp.issues.append(issue("NAME_WHITESPACE", "info", n, "Name has extra spaces at the ends (shown trimmed; source unchanged).", row=r1, key=key))
    e["sept"] = _numfield(sp, r1, "Sept Present", g("sept"), key, 0, 31)
    e["octo"] = _numfield(sp, r1, "Octo Present", g("octo"), key, 0, 31)
    e["rate"] = _numfield(sp, r1, "Per Day Pay", g("rate"), key, 0, None)
    e["rate_year"] = dict(_numfield(sp, r1, sp.rate_label or "Yearly rate", g("rate_year"), key, 0), label=sp.rate_label) if "rate_year" in cols else None
    sw = to_number(g("sweet"))
    e["sweet"] = {"state": sw[0], "value": sw[1]}
    e["total_cached"] = g("total")
    e["net_cached"] = g("net")
    a = None if blank(g("aadhaar")) else (re.sub(r"\D", "", str(g("aadhaar"))) or str(g("aadhaar")).strip())
    m = None if blank(g("mobile")) else (re.sub(r"\D", "", str(g("mobile"))) or str(g("mobile")).strip())
    e["aadhaar"], e["mobile"] = a, m
    if a and not re.fullmatch(r"\d{12}", a):
        sp.issues.append(issue("AADHAAR_INVALID", "error", n, "Aadhaar is not 12 digits.", row=r1, field_="Aadhaar", key=key))
    if m and not re.fullmatch(r"(?:91)?[6-9]\d{9}", m):
        sp.issues.append(issue("MOBILE_INVALID", "error", n, "Mobile is not a valid 10-digit Indian number.", row=r1, field_="Mobile", key=key))
    for k, label in (("from_date", "From Date"), ("to_date", "To Date")):
        st, d = to_date(g(k)) if k in cols else ("blank", None)
        if st == "invalid":
            sp.issues.append(issue("DATE_INVALID", "error", n, f"{label} is not a valid date: “{g(k)}”.", row=r1, field_=label, key=key))
        e[k] = {"state": st, "value": d, "raw": g(k)}
    e["emp_id"] = None if blank(ga("emp_id")) else str(ga("emp_id")).strip()
    e["status_raw"] = None if blank(ga("status")) else str(ga("status")).strip()
    st_, dd = to_date(ga("dep_date")) if "dep_date" in sp.app_cols else ("blank", None)
    if st_ == "invalid":
        sp.issues.append(issue("DATE_INVALID", "error", n, "Departure Date is not a valid date.", row=r1, field_="Departure Date", key=key))
    e["dep_date"] = dd
    e["dep_reason"] = None if blank(ga("dep_reason")) else str(ga("dep_reason")).strip()
    e["verified_at"] = None if blank(ga("verified_at")) else str(ga("verified_at")).strip()
    # formula pattern checks (flag only)
    if "no" in cols:
        fa = cell(formulas, r, cols["no"])
        if not ((isinstance(fa, str) and fa.startswith("=")) or (isinstance(fa, (int, float)) and not isinstance(fa, bool))):
            sp.issues.append(issue("SERIAL_UNUSUAL", "review", n, f"No. column holds “{fa}” instead of a number or formula. Row kept as-is.", row=r1, field_="No.", key=key))
    if "total" in cols and "sept" in cols and "octo" in cols:
        fh = cell(formulas, r, cols["total"])
        want = f"=SUM({col_letter(cols['sept'])}{r1}:{col_letter(cols['octo'])}{r1})"
        if fh != want:
            sp.issues.append(issue("FORMULA_DEVIATION", "review", n, f"Total Present formula differs from the usual Sept+Oct sum (found {fh!r}).", row=r1, field_="Total Present", key=key))
    if "net" in cols and "total" in cols and "rate" in cols:
        fj = cell(formulas, r, cols["net"])
        want = f"=SUM({col_letter(cols['total'])}{r1}*{col_letter(cols['rate'])}{r1})"
        if fj != want:
            sp.issues.append(issue("FORMULA_DEVIATION", "review", n, f"Net Pay formula differs from Total × Per Day Pay (found {fj!r}).", row=r1, field_="Net Pay", key=key))
    return e


def _summary(sp, values, formulas, labels):
    n, cols = sp.name, sp.cols
    s = {"total_row": None, "advance": None, "sweets": None, "balance": None, "workbook_count": None,
         "total_range_end": None, "total_row_values": {}, "formula_verified": False}

    def grab(label):
        if label not in labels:
            return None
        r1, c = labels[label][0]
        r = r1 - 1
        for cc in range(c + 1, max(len(values[r]), c + 3)):
            v, f = cell(values, r, cc), cell(formulas, r, cc)
            if not blank(v) or not blank(f):
                return {"row": r1, "ref": ref(r1, cc), "value": v,
                        "formula": f if isinstance(f, str) and f.startswith("=") else None}
        return {"row": r1, "ref": None, "value": None, "formula": None}

    if "total" in labels:
        r1, _ = labels["total"][0]
        r = r1 - 1
        s["total_row"] = r1
        s["workbook_count"] = cell(values, r, cols["no"]) if "no" in cols else None
        s["total_row_values"] = {k: cell(values, r, cols[k]) for k in ("sept", "octo", "total", "net") if k in cols}
        fn = cell(formulas, r, cols["net"]) if "net" in cols else None
        m = re.search(r"\$?[A-Z]+\$?(\d+):\$?[A-Z]+\$?(\d+)", str(fn or ""))
        if m:
            s["total_range_end"] = int(m.group(2))
    for k in ("advance", "sweets", "balance"):
        s[k] = grab(k)
    if s["total_row"] and s["balance"] and s["balance"].get("formula") and s["advance"] and s["sweets"] and "net" in cols:
        nc = col_letter(cols["net"])
        t, a, w = s["total_row"], s["advance"]["row"], s["sweets"]["row"]
        want = {f"=SUM({nc}{t}-{nc}{a}-{nc}{w})", f"={nc}{t}-{nc}{a}-{nc}{w}"}
        s["formula_verified"] = s["balance"]["formula"].replace(" ", "") in want
    sp.summary = s
    wc = s["workbook_count"]
    if isinstance(wc, (int, float)) and not isinstance(wc, bool) and wc != len(sp.employees):
        sp.issues.append(issue("COUNT_MISMATCH", "info", n,
                               f"The sheet’s own staff count shows {int(wc)}, but {len(sp.employees)} named staff exist (the sheet counts blank formatted rows).",
                               row=s["total_row"]))
    if s["total_range_end"] and sp.employees and max(e["row"] for e in sp.employees) > s["total_range_end"]:
        sp.issues.append(issue("TOTAL_RANGE_SHORT", "error", n,
                               f"Staff exist below row {s['total_range_end']}, which the sheet’s Total row does not cover.", row=s["total_row"]))
    for k in ("advance", "sweets"):
        v = s[k]
        if v and isinstance(v["value"], (int, float)) and not isinstance(v["value"], bool) and 0 < v["value"] <= 1:
            sp.issues.append(issue("GROUP_AMOUNT_UNUSUAL", "info", n,
                                   f"{k.title()} is ₹{v['value']:g} — placeholder value in spreadsheet.",
                                   row=v["row"], field_=k.title()))
    free = [r for r in sp.ignored_rows if not s["total_row"] or r < s["total_row"]]
    sp.next_free_row = free[0] if free else 0
    last = max([e["row"] for e in sp.employees] + [sp.header_row + 1])
    sp.first_row_after_data = last + 1
