"""Builds an immutable in-memory SNAPSHOT of the workbook after each successful sync.

The workbook stays the source of truth; the snapshot is a validated, derived read model.
"""
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from .config import CONFIG_DEFAULTS
from .workbook.parser import parse_sheet, issue
from .workbook.schema import (SHEET_ATTENDANCE, SHEET_AUDIT, SHEET_CONFIG, SUPPORT_PREFIX, blank, to_date)

STATUSES = ("Active", "Departed", "Not Verified")


@dataclass
class Snapshot:
    version: str = ""
    loaded_at: str = ""
    sheets: list = field(default_factory=list)          # SheetParse (all)
    groups: list = field(default_factory=list)          # compatible group names, workbook order
    skipped: list = field(default_factory=list)         # [{name, reason}]
    employees: list = field(default_factory=list)
    by_id: dict = field(default_factory=dict)
    by_key: dict = field(default_factory=dict)
    attendance: dict = field(default_factory=dict)      # emp_id -> {date: rec}
    attendance_by_date: dict = field(default_factory=dict)
    audit: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    support_present: dict = field(default_factory=dict)
    id_setup_needed: bool = True
    config_rows: dict = field(default_factory=dict)     # key -> row number (for updates)

    def sheet(self, name):
        return next((s for s in self.sheets if s.name == name), None)


def _parse_support(raw_sheets):
    att, audit, cfg, issues = {}, [], dict(CONFIG_DEFAULTS), []
    cfg_rows = {}
    g = raw_sheets.get(SHEET_ATTENDANCE)
    if g:
        for i, row in enumerate(g["values"][1:], start=2):
            if all(blank(v) for v in row):
                continue
            row = list(row) + [None] * (8 - len(row))
            st, d = to_date(row[1])
            eid = None if blank(row[2]) else str(row[2]).strip()
            if st != "date" or not eid:
                issues.append(issue("ATTENDANCE_ROW_INVALID", "error", SHEET_ATTENDANCE, "Attendance row has no valid date or Employee ID.", row=i))
                continue
            rec = {"date": d, "emp_id": eid, "group": row[3], "status": None if blank(row[4]) else str(row[4]).strip(),
                   "notes": row[5], "updated_at": row[6], "updated_by": row[7], "row": i}
            if eid in att and d in att[eid]:
                issues.append(issue("ATTENDANCE_DUPLICATE", "error", SHEET_ATTENDANCE,
                                    f"More than one attendance row for {eid} on {d.isoformat()} (last one is used).", row=i))
            att.setdefault(eid, {})[d] = rec
    g = raw_sheets.get(SHEET_AUDIT)
    if g:
        for i, row in enumerate(g["values"][1:], start=2):
            if all(blank(v) for v in row):
                continue
            row = list(row) + [None] * (9 - len(row))
            audit.append(dict(zip(("ts", "actor", "action", "emp_id", "group", "field", "before", "after", "note"), row[:9])))
    g = raw_sheets.get(SHEET_CONFIG)
    if g:
        for i, row in enumerate(g["values"][1:], start=2):
            if blank(row[0] if row else None):
                continue
            k = str(row[0]).strip()
            cfg_rows[k] = i
            try:
                cfg[k] = json.loads(row[1]) if len(row) > 1 and not blank(row[1]) else CONFIG_DEFAULTS.get(k)
            except (ValueError, TypeError):
                issues.append(issue("CONFIG_INVALID", "error", SHEET_CONFIG, f"Setting “{k}” is not valid JSON; default used.", row=i))
    return att, audit, cfg, cfg_rows, issues


def build_snapshot(raw, version, loaded_at, today):
    sheets_raw = raw["sheets"]
    s = Snapshot(version=version, loaded_at=loaded_at)
    att, audit, cfg, cfg_rows, support_issues = _parse_support(sheets_raw)
    s.attendance, s.audit, s.config, s.config_rows = att, audit, cfg, cfg_rows
    s.support_present = {n: (n in sheets_raw) for n in (SHEET_ATTENDANCE, SHEET_AUDIT, SHEET_CONFIG)}
    for name, grid in sheets_raw.items():
        sp = parse_sheet(name, grid)
        s.sheets.append(sp)
        if sp.compatible:
            s.groups.append(name)
        elif not name.startswith(SUPPORT_PREFIX):
            s.skipped.append({"name": name, "reason": sp.reason})
    issues = list(support_issues)
    for sp in s.sheets:
        issues += sp.issues
        if sp.compatible:
            for e in sp.employees:
                s.employees.append(e)
    _resolve(s, issues, today)
    for eid, days in att.items():
        for d, rec in days.items():
            s.attendance_by_date.setdefault(d, {})[eid] = rec
    s.issues = issues
    return s


def _resolve(s, issues, today):
    cfg = s.config
    ids = Counter(e["emp_id"] for e in s.employees if e["emp_id"])
    s.id_setup_needed = not cfg.get("id_migration_done_at")
    names = defaultdict(list)
    for e in s.employees:
        # identity
        if e["emp_id"] and ids[e["emp_id"]] > 1:
            e["id_state"] = "duplicate"
            issues.append(issue("DUPLICATE_ID", "error", e["sheet"], f"Employee ID {e['emp_id']} appears on more than one row. Writes for these rows are blocked.", row=e["row"], key=e["key"]))
        elif e["emp_id"]:
            e["id_state"] = "ok"
        else:
            e["id_state"] = "missing"
        e["id"] = e["emp_id"] if e["id_state"] == "ok" else None
        e["ref"] = e["id"] or f"row:{e['sheet']}|{e['row']}"          # provisional handle for read-only views
        e["writable"] = e["id_state"] == "ok" and not s.id_setup_needed
        # status (employment) - separate from attendance
        raw = (e["status_raw"] or "").lower()
        if raw == "active":
            e["status"] = "Active"
        elif raw == "departed":
            e["status"] = "Departed"
        else:
            e["status"] = "Not Verified"
            if raw:
                issues.append(issue("STATUS_INVALID", "review", e["sheet"], f"Employment Status “{e['status_raw']}” is not Active/Departed; treated as Not Verified.", row=e["row"], key=e["key"]))
        if e["status"] == "Departed" and not e["dep_date"]:
            issues.append(issue("DEPARTURE_DATE_MISSING", "review", e["sheet"], "Departed without a departure date (not invented).", row=e["row"], key=e["key"]))
        names[" ".join(e["name"].lower().split())].append(e)
        # per-employee gaps
        miss = [f for f in cfg.get("required_fields", []) if blank(e.get(f))]
        e["missing_fields"] = miss
        if e["rate"]["state"] == "invalid":
            issues.append(issue("RATE_REQUIRED", "error", e["sheet"], "Rate invalid — Per Day Pay is not a valid amount.", row=e["row"], key=e["key"], field_="Per Day Pay"))
        s.by_key[e["key"]] = e
        if e["id"]:
            s.by_id[e["id"]] = e
    for nm, lst in names.items():
        if len(lst) > 1:
            where = ", ".join(f"{x['sheet']} row {x['row']}" for x in lst)
            for x in lst:
                issues.append(issue("DUPLICATE_LOOKING", "review", x["sheet"], f"Same name also appears at: {where}. Kept as separate people until you confirm.", row=x["row"], key=x["key"]))
    # aggregated per-group notes (avoid hundreds of identical rows)
    for sp in s.sheets:
        if not sp.compatible or not sp.employees:
            continue
        n = len(sp.employees)
        nv = sum(1 for e in sp.employees if e["status"] == "Not Verified")
        if nv:
            issues.append(issue("STATUS_NOT_VERIFIED", "review", sp.name, f"{nv} of {n} employees have a status that is not verified yet.", detail="Use Admin ▸ Status review."))
        n_blank_rate = sum(1 for e in sp.employees if e["rate"]["state"] == "blank")
        if n_blank_rate:
            issues.append(issue("RATE_REQUIRED", "info", sp.name, f"{n_blank_rate} of {n} employees have no approved rate configured under company policy.", field_="Per Day Pay"))
        n_missing_req = sum(1 for e in sp.employees if e.get("missing_fields"))
        if n_missing_req:
            issues.append(issue("INCOMPLETE_RECORD", "info", sp.name, f"{n_missing_req} of {n} employees have missing designation or location in workbook.", field_="Record Details"))
        for k, label in (("aadhaar", "Aadhaar"), ("mobile", "Mobile"), ("from_date", "From Date")):
            empty = sum(1 for e in sp.employees if (e[k] is None if k in ("aadhaar", "mobile") else e[k]["state"] == "blank"))
            if empty:
                issues.append(issue("OPTIONAL_EMPTY", "info", sp.name, f"{label} is empty for {empty} of {n} employees."))
    rl = {sp.rate_label for sp in s.sheets if sp.compatible and sp.rate_label}
    if len(rl) > 1:
        issues.append(issue("HEADER_INCONSISTENT", "info", "(workbook)", f"The yearly-rate column heading differs between sheets: {', '.join(sorted(rl))}. That column is blank everywhere and is NOT used for pay."))
    # attendance integrity
    for eid, days in s.attendance.items():
        e = s.by_id.get(eid)
        if e is None:
            issues.append(issue("ATTENDANCE_ORPHAN", "review", SHEET_ATTENDANCE, f"Attendance exists for {eid}, who is no longer in any group sheet. History kept."))
            continue
        for d, rec in days.items():
            if e["status"] == "Departed" and e["dep_date"] and d > e["dep_date"]:
                issues.append(issue("ATTENDANCE_AFTER_DEPARTURE", "review", e["sheet"], f"Attendance on {d.isoformat()} is after the departure date.", key=e["key"], row=e["row"]))
            if rec["status"] and rec["status"] not in ("Present", "Absent", "Leave", "Weekly Off/Holiday"):
                issues.append(issue("ATTENDANCE_ROW_INVALID", "error", SHEET_ATTENDANCE, f"Unknown attendance status “{rec['status']}”.", row=rec["row"]))
    if s.id_setup_needed:
        issues.append(issue("ID_SETUP_PENDING", "review", "(workbook)",
                            "Permanent employee IDs have not been set up yet. The app is READ-ONLY until an admin runs ID setup (a backup is made first)."))
    elif any(e["id_state"] == "missing" for e in s.employees):
        c = sum(1 for e in s.employees if e["id_state"] == "missing")
        issues.append(issue("ID_MISSING", "review", "(workbook)", f"{c} employee row(s) have no App ID yet (new rows). They will be assigned automatically or by an admin."))
    # fingerprints + resolutions
    res = cfg.get("issue_resolutions") or {}
    for i in issues:
        e = s.by_key.get(i["emp_key"]) if i.get("emp_key") else None
        i["emp_id"] = e["id"] if e else None
        i["emp_name"] = e["name_display"] if e else None
        i["fingerprint"] = "|".join(str(x) for x in (i["code"], (e or {}).get("id") or i["sheet"], i["row"] if not e or not e["id"] else "", i["field"] or ""))
        i["resolution"] = res.get(i["fingerprint"])
