"""All app-initiated changes to the workbook. Every write:
  validate (server-side) -> take the lock -> RE-READ the live cells -> conflict-check against what the user saw
  -> scoped write -> RE-READ and verify -> audit -> refresh snapshot -> only then report success.
Nothing is ever reported saved that is not in the workbook.
"""
import hashlib
import json
import re
from datetime import date, datetime

from .adapters.base import WorkbookError
from .config import ALL_ATTENDANCE_STATUSES, CONFIG_DEFAULTS
from .model import build_snapshot
from .queries import options
from .workbook.parser import parse_sheet
from .workbook.schema import (APP_COLUMNS, ATTENDANCE_HEADERS, AUDIT_HEADERS, CONFIG_HEADERS, SHEET_ATTENDANCE,
                              SHEET_AUDIT, SHEET_CONFIG, blank, col_letter, norm, to_date)


class ApiError(Exception):
    def __init__(self, status, code, message, extra=None):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


def safe_text(v, label="Text"):
    """Text that starts with = + - @ would become a FORMULA in Excel. Refuse it."""
    if isinstance(v, str) and v.strip()[:1] in ("=", "+", "-", "@"):
        raise ApiError(422, "validation", f"{label} cannot start with = + - or @.")
    return v


def _runs(rows):
    """[3,4,5,9,10] -> [(3,5),(9,10)] consecutive runs."""
    rows = sorted(set(rows))
    out = []
    for r in rows:
        if out and r == out[-1][1] + 1:
            out[-1][1] = r
        else:
            out.append([r, r])
    return [tuple(x) for x in out]


def make_emp_id(sheet, row, name, taken):
    base = hashlib.sha256(f"{sheet}|{row}|{' '.join(name.lower().split())}".encode()).hexdigest()[:8].upper()
    cand, n = f"EMP-{base}", 1
    while cand in taken:
        n += 1
        cand = f"EMP-{base}-{n}"
    return cand


FIELD_COL = {"name": "name", "designation": "designation", "location": "location", "rate": "rate", "sept": "sept",
             "octo": "octo", "aadhaar": "aadhaar", "mobile": "mobile", "from_date": "from_date", "to_date": "to_date"}
EDITOR_FIELDS = {"name", "designation", "location", "aadhaar", "mobile", "from_date", "to_date"}
ADMIN_FIELDS = {"rate", "sept", "octo"}          # pay-affecting inputs: admin only


class Services:
    def __init__(self, settings, adapter, sync):
        self.s, self.adapter, self.sync = settings, adapter, sync
        sync.post_sync_hook = self._auto_assign_ids

    # ---------- helpers ----------
    @property
    def snap(self):
        sn = self.sync.snapshot
        if sn is None:
            raise ApiError(503, "not_ready", "The workbook has not been loaded yet. Check the connection on the Sync page.")
        return sn

    def _wrap(self, fn):
        try:
            return fn()
        except WorkbookError as ex:
            self.sync._fail(ex)
            raise ApiError(502, "write_failed", f"Not saved: {ex.message}", {"kind": ex.kind})

    def _live_sheet(self, name):
        g = self.adapter.read_sheet(name)
        if g is None:
            raise ApiError(409, "sheet_missing", f"Sheet “{name}” is no longer in the workbook. Refresh and try again.")
        return g

    def _live_emp(self, e_snap):
        """Find the employee by permanent ID in the LIVE sheet (rows may have moved)."""
        sp = parse_sheet(e_snap["sheet"], self._live_sheet(e_snap["sheet"]))
        for e in sp.employees:
            if e["emp_id"] == e_snap["id"]:
                return sp, e
        # moved to another sheet?
        for g in self.snap.groups:
            if g == e_snap["sheet"]:
                continue
            sp2 = parse_sheet(g, self._live_sheet(g))
            for e in sp2.employees:
                if e["emp_id"] == e_snap["id"]:
                    return sp2, e
        raise ApiError(409, "employee_gone", "This employee is no longer in the workbook (row deleted or ID changed). Refresh and review.")

    def _employee(self, ref):
        e = self.snap.by_id.get(ref)
        if not e:
            if ref and ref.startswith("row:"):
                raise ApiError(409, "id_setup_required", "This employee has no permanent ID yet. An admin must run ID setup first.")
            raise ApiError(404, "not_found", "Employee not found.")
        if e["id_state"] != "ok":
            raise ApiError(409, "id_problem", "This employee row has an ID problem (duplicate/missing). Fix it in Data Quality first.")
        return e

    def _require_setup(self):
        if self.snap.id_setup_needed:
            raise ApiError(409, "id_setup_required",
                           "Read-only until ID setup is run. An admin must open Admin ▸ Workbook setup (a backup is made first).")

    def _audit(self, actor, entries):
        """entries: list of dict(action, emp_id, group, field, before, after, note). Returns warning or None."""
        ts = self.s.now_iso()
        rows = [[ts, actor, x["action"], x.get("emp_id"), x.get("group"), x.get("field"),
                 _s(x.get("before")), _s(x.get("after")), x.get("note")] for x in entries]
        try:
            self.adapter.append_rows(SHEET_AUDIT, rows)
            return None
        except WorkbookError as ex:
            return f"Saved, but the audit log entry could not be written ({ex.kind})."

    def _finish(self):
        self.sync.refresh(force=True, reason="write")

    # ---------- one-time setup (structural change) ----------
    def plan_setup(self):
        sn = self.snap
        taken = {e["emp_id"] for e in sn.employees if e["emp_id"]}
        plan = {"already_done": not sn.id_setup_needed, "support_sheets_to_create": [n for n, ok in sn.support_present.items() if not ok],
                "groups": [], "ids_to_assign": 0}
        for sp in (s for s in sn.sheets if s.compatible):
            need = [e for e in sp.employees if not e["emp_id"]]
            missing_cols = [f"{col_letter(sp.app_col_plan[k])} “{h}”" for k, h in APP_COLUMNS if k not in sp.app_cols]
            plan["groups"].append({"sheet": sp.name, "new_columns": missing_cols, "ids_to_assign": len(need)})
            plan["ids_to_assign"] += len(need)
        plan["explanation"] = ("One-time, additive change: adds 5 helper columns to the right of each group sheet and 3 support sheets "
                               "(_App_Attendance, _App_Audit, _App_Config). No existing cell, formula or format is modified. "
                               "A backup copy of the workbook is created first.")
        return plan

    def run_setup(self, actor):
        with self.sync.lock:
            self.sync.refresh(force=True, reason="pre-setup")
            sn = self.snap
            def go():
                backup = self.adapter.backup("before-id-setup")
                for name, hdr in ((SHEET_ATTENDANCE, ATTENDANCE_HEADERS), (SHEET_AUDIT, AUDIT_HEADERS), (SHEET_CONFIG, CONFIG_HEADERS)):
                    self.adapter.ensure_sheet(name, hdr)
                taken = {e["emp_id"] for e in sn.employees if e["emp_id"]}
                assigned = 0
                for sp in (s for s in sn.sheets if s.compatible):
                    hdr_row = sp.header_row + 1
                    for key, label in APP_COLUMNS:
                        if key not in sp.app_cols:
                            self.adapter.write_cells(sp.name, {f"{col_letter(sp.app_col_plan[key])}{hdr_row}": label})
                    idcol = col_letter(sp.app_col_plan["emp_id"])
                    byrow = {}
                    for e in sp.employees:
                        if not e["emp_id"]:
                            nid = make_emp_id(sp.name, e["row"], e["name"], taken)
                            taken.add(nid)
                            byrow[e["row"]] = nid
                    for a, b in _runs(byrow):
                        self.adapter.write_block(sp.name, f"{idcol}{a}", [[byrow[r]] for r in range(a, b + 1)])
                    assigned += len(byrow)
                return backup, assigned
            backup, assigned = self._wrap(go)
            self._set_config_raw("id_migration_done_at", self.s.now_iso(), actor)
            warn = self._audit(actor, [{"action": "workbook_setup", "note": f"backup={backup}; ids_assigned={assigned}"}])
            self._finish()
            return {"ok": True, "backup": backup, "ids_assigned": assigned, "warning": warn}

    @staticmethod
    def _header_cells(sp):
        """Header cells for app helper columns missing on this sheet (e.g. a NEW group sheet added in Excel)."""
        hr = sp.header_row + 1
        return {f"{col_letter(sp.app_col_plan[k])}{hr}": label for k, label in APP_COLUMNS if k not in sp.app_cols}

    def _auto_assign_ids(self):
        sn = self.sync.snapshot
        if not sn or sn.id_setup_needed or not self.s.auto_assign_ids or getattr(self, "_assigning", False):
            return
        missing = [e for e in sn.employees if not e["emp_id"]]
        if not missing:
            return
        self._assigning = True
        try:
            self._auto_assign_inner(sn, missing)
        finally:
            self._assigning = False

    def _auto_assign_inner(self, sn, missing):
        with self.sync.lock:
            taken = {e["emp_id"] for e in sn.employees if e["emp_id"]}
            by_sheet = {}
            for e in missing:
                sp = sn.sheet(e["sheet"])
                nid = make_emp_id(e["sheet"], e["row"], e["name"], taken)
                taken.add(nid)
                by_sheet.setdefault(e["sheet"], {})[e["row"]] = (nid, e["name"])
            done = {}
            try:
                for sheet, rows in by_sheet.items():
                    sp = sn.sheet(sheet)
                    live = parse_sheet(sheet, self._live_sheet(sheet))
                    liverows = {e["row"]: e for e in live.employees}
                    idcol = col_letter(sp.app_col_plan["emp_id"])
                    ok = {r: v[0] for r, v in rows.items() if r in liverows and not liverows[r]["emp_id"] and liverows[r]["name"] == v[1]}
                    hdr = self._header_cells(sp)
                    if ok and hdr:
                        self.adapter.write_cells(sheet, hdr)
                    for a, b in _runs(ok):
                        self.adapter.write_block(sheet, f"{idcol}{a}", [[ok[r]] for r in range(a, b + 1)])
                    done[sheet] = len(ok)
                done = {k: v for k, v in done.items() if v}
                if done:
                    self._audit("system", [{"action": "auto_assign_id", "group": sh, "note": f"{n} new row(s)"} for sh, n in done.items()])
                    self.sync.refresh(force=True, reason="id-assign")
            except WorkbookError:
                pass

    # ---------- attendance ----------
    def mark_attendance(self, actor, role, items, correction=False):
        """items: [{ref, date, status, notes?, expected?}]. All-or-nothing validation. status 'Not Recorded' clears."""
        self._require_setup()
        if not items:
            raise ApiError(422, "empty", "Nothing to save.")
        cfg = self.snap.config
        enabled = set(cfg.get("attendance_statuses") or ["Present", "Absent"]) | {"Not Recorded"}
        today = self.s.today()
        errors, prepared = [], []
        seen = set()
        for i, it in enumerate(items):
            try:
                e = self._employee(it.get("ref"))
            except ApiError as ex:
                errors.append({"index": i, "error": ex.message})
                continue
            st, d = to_date(it.get("date"))
            if st != "date":
                errors.append({"index": i, "ref": e["id"], "error": "Invalid date."})
                continue
            status = it.get("status")
            if status not in enabled:
                errors.append({"index": i, "ref": e["id"], "error": f"Status “{status}” is not enabled."})
                continue
            if cfg.get("block_future_attendance", True) and d > today:
                errors.append({"index": i, "ref": e["id"], "error": "Attendance cannot be recorded for a future date."})
                continue
            if e["status"] == "Departed":
                if not (correction and role == "admin"):
                    errors.append({"index": i, "ref": e["id"], "error": "Departed employee: attendance cannot be recorded here. An admin can log a correction."})
                    continue
            key = f"{e['id']}|{d.isoformat()}"
            if key in seen:
                errors.append({"index": i, "ref": e["id"], "error": "Duplicate entry for the same employee and date in this request."})
                continue
            seen.add(key)
            try:
                safe_text(it.get("notes"), "Note")
            except ApiError as ex:
                errors.append({"index": i, "ref": e["id"], "error": ex.message})
                continue
            prepared.append((e, d, status, it.get("notes"), it.get("expected"), key, bool(e["status"] == "Departed")))
        if errors:
            raise ApiError(422, "validation", "Nothing was saved. Please fix the highlighted items.", {"items": errors})

        with self.sync.lock:
            def go():
                self.adapter.ensure_sheet(SHEET_ATTENDANCE, ATTENDANCE_HEADERS)   # no-op if it exists
                live = self._live_sheet(SHEET_ATTENDANCE)
                rows = live["values"]
                index = {}
                for r, row in enumerate(rows[1:], start=2):
                    if len(row) > 2 and not blank(row[2]) and not blank(row[1]):
                        s_, dd = to_date(row[1])
                        if s_ == "date":
                            index[f"{str(row[2]).strip()}|{dd.isoformat()}"] = (r, row)
                # conflicts: what the user saw vs what is saved now
                conflicts = []
                for (e, d, status, notes, expected, key, _) in prepared:
                    if expected is not None:
                        cur = (index.get(key, (None, [None] * 5))[1] + [None] * 8)[4]
                        cur = "Not Recorded" if blank(cur) else str(cur).strip()
                        if cur != expected:
                            conflicts.append({"ref": e["id"], "name": e["name_display"], "date": d.isoformat(), "yours": expected, "current": cur})
                if conflicts:
                    raise ApiError(409, "conflict", "Someone changed this attendance since you opened it. Nothing was saved.", {"conflicts": conflicts})
                ts = self.s.now_iso()
                new_rows, upd, audit = [], {}, []
                for (e, d, status, notes, expected, key, dep) in prepared:
                    val = "" if status == "Not Recorded" else status
                    if key in index:
                        r, old = index[key]
                        old = list(old) + [None] * 8
                        before = "Not Recorded" if blank(old[4]) else old[4]
                        if before == (status if status else "Not Recorded") and blank(notes) == blank(old[5]):
                            continue
                        upd[r] = [val, notes if notes is not None else old[5], ts, actor]
                    else:
                        if status == "Not Recorded":
                            continue
                        before = "Not Recorded"
                        new_rows.append([key, d.isoformat(), e["id"], e["sheet"], val, notes, ts, actor])
                    audit.append({"action": "attendance_correction" if dep else "attendance", "emp_id": e["id"], "group": e["sheet"],
                                  "field": d.isoformat(), "before": before, "after": status, "note": notes})
                for a, b in _runs(upd):
                    self.adapter.write_block(SHEET_ATTENDANCE, f"E{a}", [upd[r] for r in range(a, b + 1)])
                if new_rows:
                    self.adapter.append_rows(SHEET_ATTENDANCE, new_rows)
                # verify by re-reading
                chk = self._live_sheet(SHEET_ATTENDANCE)["values"]
                got = {}
                for row in chk[1:]:
                    if len(row) > 4 and not blank(row[2]):
                        s_, dd = to_date(row[1])
                        got[f"{str(row[2]).strip()}|{dd.isoformat() if s_ == 'date' else ''}"] = "Not Recorded" if blank(row[4]) else str(row[4]).strip()
                for (e, d, status, *_rest) in prepared:
                    k = f"{e['id']}|{d.isoformat()}"
                    if got.get(k, "Not Recorded") != status:
                        raise ApiError(502, "verify_failed", "The save could not be confirmed in the workbook. Please refresh and check.")
                return audit
            audit = self._wrap(go)
            warn = self._audit(actor, audit) if audit else None
            sn = self.sync.snapshot
            ts = self.s.now_iso()
            if sn and not any(dep for *_, dep in prepared):
                for (e, d, status, notes, _expected, key, _dep) in prepared:
                    val = None if status == "Not Recorded" else status
                    rec = {
                        "date": d,
                        "emp_id": e["id"],
                        "group": e["sheet"],
                        "status": val,
                        "notes": notes,
                        "updated_at": ts,
                        "updated_by": actor,
                        "row": None,
                    }
                    sn.attendance.setdefault(e["id"], {})[d] = rec
                    sn.attendance_by_date.setdefault(d, {})[e["id"]] = rec
                for entry in audit:
                    sn.audit.append({
                        "ts": ts,
                        "actor": actor,
                        "action": entry["action"],
                        "emp_id": entry.get("emp_id"),
                        "group": entry.get("group"),
                        "field": entry.get("field"),
                        "before": entry.get("before"),
                        "after": entry.get("after"),
                        "note": entry.get("note"),
                    })
                self.sync.last_success = datetime.now()
                self.sync.last_change_at = datetime.now()
                self.sync._ok(True, "write")
            else:
                self._finish()
            updated = [{"ref": e["id"], "name": e["name_display"], "date": d.isoformat(), "status": status} for (e, d, status, *_rest) in prepared]
            return {"ok": True, "saved": len(audit), "warning": warn, "updated": updated}

    # ---------- employment status ----------
    def set_status(self, actor, items):
        """items: [{ref, status: Active|Departed, dep_date?, reason?, expected_status?}] - Departed needs a real date."""
        self._require_setup()
        today = self.s.today()
        prepared, errors = [], []
        for i, it in enumerate(items):
            try:
                e = self._employee(it.get("ref"))
            except ApiError as ex:
                errors.append({"index": i, "error": ex.message})
                continue
            status = it.get("status")
            if status not in ("Active", "Departed"):
                errors.append({"index": i, "ref": e["id"], "error": "Status must be Active or Departed."})
                continue
            dd = None
            if status == "Departed":
                st, dd = to_date(it.get("dep_date"))
                if st != "date":
                    errors.append({"index": i, "ref": e["id"], "error": "A departure date is required (it is never guessed)."})
                    continue
                if dd > today:
                    errors.append({"index": i, "ref": e["id"], "error": "Departure date cannot be in the future."})
                    continue
            try:
                reason = safe_text((it.get("reason") or "").strip() or None, "Reason")
            except ApiError as ex:
                errors.append({"index": i, "ref": e["id"], "error": ex.message})
                continue
            prepared.append((e, status, dd, reason, it.get("expected_status")))
        if errors:
            raise ApiError(422, "validation", "Nothing was saved. Please fix the highlighted items.", {"items": errors})
        with self.sync.lock:
            def go():
                audit, by_sheet, spmap = [], {}, {}
                for (e, status, dd, reason, exp) in prepared:
                    sp, live = self._live_emp(e)
                    cur = live["status_raw"] or "Not Verified"
                    if exp is not None and cur != exp:
                        raise ApiError(409, "conflict", f"{e['name_display']}: status was changed in the workbook (now “{cur}”). Nothing was saved.",
                                       {"conflicts": [{"ref": e["id"], "yours": exp, "current": cur}]})
                    ts = f"{self.s.now_iso()} by {actor}"
                    spmap[sp.name] = sp
                    by_sheet.setdefault(sp.name, {})[live["row"]] = [status, dd, reason, ts]
                    audit.append({"action": "status", "emp_id": e["id"], "group": sp.name, "field": "Employment Status",
                                  "before": cur, "after": status + (f" ({dd.isoformat()})" if dd else ""), "note": reason})
                for spn, rows in by_sheet.items():
                    sp = spmap[spn]
                    c = col_letter(sp.app_col_plan["status"])
                    for a, b in _runs(rows):
                        self.adapter.write_block(sp.name, f"{c}{a}", [rows[r] for r in range(a, b + 1)])
                # verify
                for (e, status, dd, reason, exp) in prepared:
                    sp, live = self._live_emp(e)
                    if live["status_raw"] != status or live["dep_date"] != dd:
                        raise ApiError(502, "verify_failed", "The save could not be confirmed in the workbook. Please refresh and check.")
                return audit
            audit = self._wrap(go)
            warn = self._audit(actor, audit)
            self._finish()
            return {"ok": True, "saved": len(audit), "warning": warn}

    # ---------- employee details ----------
    def _validate_field(self, field, value, role):
        if field in ADMIN_FIELDS and role != "admin":
            raise ApiError(403, "forbidden", "Only an admin can change pay rates or present-day counts.")
        v = None if value is None or (isinstance(value, str) and not value.strip()) else value
        opts = options(self.snap)
        if field == "name":
            if v is None or len(str(v).strip()) < 2:
                raise ApiError(422, "validation", "Name is required (at least 2 characters).")
            return safe_text(str(v).strip(), "Name")
        if field in ("designation", "location"):
            if v is None:
                return None
            v = safe_text(str(v).strip(), field.title())
            allowed = opts["designations" if field == "designation" else "locations"]
            if v not in allowed and role != "admin":
                raise ApiError(422, "validation", f"“{v}” is not an approved {field}. Choose from the list (an admin can add new options).")
            return v
        if field in ("rate", "sept", "octo"):
            if v is None:
                return None
            try:
                n = float(str(v).replace(",", ""))
            except ValueError:
                raise ApiError(422, "validation", f"{field} must be a number.")
            if n < 0 or (field in ("sept", "octo") and n > 31):
                raise ApiError(422, "validation", f"{field} is out of range.")
            return int(n) if n == int(n) else n
        if field == "aadhaar":
            if v is None:
                return None
            d = re.sub(r"\D", "", str(v))
            if not re.fullmatch(r"[2-9]\d{11}", d):
                raise ApiError(422, "validation", "Aadhaar must be 12 digits (cannot start with 0 or 1).")
            return d
        if field == "mobile":
            if v is None:
                return None
            d = re.sub(r"\D", "", str(v))
            d = d[2:] if len(d) == 12 and d.startswith("91") else d
            if not re.fullmatch(r"[6-9]\d{9}", d):
                raise ApiError(422, "validation", "Mobile must be a valid 10-digit Indian number.")
            return d
        if field in ("from_date", "to_date"):
            if v is None:
                return None
            st, d = to_date(v)
            if st != "date":
                raise ApiError(422, "validation", f"{field.replace('_', ' ')} is not a valid date.")
            return d
        raise ApiError(422, "validation", f"Field “{field}” cannot be edited here.")

    def update_employee(self, actor, role, ref, changes, expected):
        self._require_setup()
        e0 = self._employee(ref)
        clean = {f: self._validate_field(f, v, role) for f, v in changes.items()}
        if not clean:
            raise ApiError(422, "empty", "No changes to save.")
        with self.sync.lock:
            def go():
                sp, live = self._live_emp(e0)
                conflicts, cells, audit = [], {}, []
                for f, newv in clean.items():
                    curv = live[f]["value"] if f in ("rate", "sept", "octo") else (live[f]["value"] if f in ("from_date", "to_date") else live[f])
                    if f in ("from_date", "to_date"):
                        curv = curv.isoformat() if curv else None
                    exp = (expected or {}).get(f)
                    if f in expected and _cmp(exp) != _cmp(curv):
                        conflicts.append({"field": f, "yours": exp, "current": curv})
                    if f not in sp.cols:
                        raise ApiError(409, "column_missing", f"This sheet has no column for {f}.")
                    cells[f"{col_letter(sp.cols[f])}{live['row']}"] = newv
                    audit.append({"action": "edit", "emp_id": e0["id"], "group": sp.name, "field": f,
                                  "before": "(masked)" if f in ("aadhaar", "mobile") else curv,
                                  "after": "(masked)" if f in ("aadhaar", "mobile") else (newv.isoformat() if isinstance(newv, date) else newv)})
                if conflicts:
                    raise ApiError(409, "conflict", "This record was changed in the workbook while you were editing. Nothing was saved.", {"conflicts": conflicts})
                self.adapter.write_cells(sp.name, {k: ("" if v is None else v) for k, v in cells.items()})
                sp2, live2 = self._live_emp(e0)
                for f, newv in clean.items():
                    got = live2[f]["value"] if f in ("rate", "sept", "octo", "from_date", "to_date") else live2[f]
                    if _cmp(got) != _cmp(newv):
                        raise ApiError(502, "verify_failed", "The save could not be confirmed in the workbook. Please refresh and check.")
                return audit
            audit = self._wrap(go)
            warn = self._audit(actor, audit)
            self._finish()
            return {"ok": True, "saved": len(audit), "warning": warn}

    def add_employee(self, actor, role, data, confirm_duplicate=False):
        self._require_setup()
        group = data.get("group")
        if group not in self.snap.groups:
            raise ApiError(422, "validation", "Choose an existing group.")
        name = self._validate_field("name", data.get("name"), role)
        fields = {"name": name}
        for f in ("designation", "location", "mobile", "aadhaar", "from_date"):
            if not blank(data.get(f)):
                fields[f] = self._validate_field(f, data.get(f), role)
        if role == "admin" and not blank(data.get("rate")):
            fields["rate"] = self._validate_field("rate", data.get("rate"), role)
        dup = [e for e in self.snap.employees if " ".join(e["name"].lower().split()) == " ".join(name.lower().split())]
        if dup and not confirm_duplicate:
            raise ApiError(409, "duplicate_candidate", "Someone with the same name already exists. Add anyway only if this is a different person.",
                           {"matches": [{"group": d["sheet"], "row": d["row"], "name": d["name_display"]} for d in dup]})
        with self.sync.lock:
            def go():
                live = self._live_sheet(group)
                sp = parse_sheet(group, live)
                row = sp.next_free_row
                if not row:
                    if sp.summary.get("total_row"):
                        raise ApiError(409, "no_free_row", "This sheet has no empty row above its Total row. In Excel, insert a row (copy an existing one) and try again.")
                    row = sp.first_row_after_data
                cells = {}
                prev = next((e for e in reversed(sp.employees) if e["row"] < row), None)
                lf = live["formulas"]
                for key in ("no", "total", "net"):
                    if key in sp.cols and prev:
                        cur = live["formulas"][row - 1][sp.cols[key]] if row - 1 < len(lf) and sp.cols[key] < len(lf[row - 1]) else None
                        pf = lf[prev["row"] - 1][sp.cols[key]]
                        if blank(cur) and isinstance(pf, str) and pf.startswith("="):
                            cells[f"{col_letter(sp.cols[key])}{row}"] = re.sub(rf"(?<![A-Z$])([A-Z]{{1,2}}){prev['row']}\b", rf"\g<1>{row}", pf)
                for f, v in fields.items():
                    cells[f"{col_letter(sp.cols[f])}{row}"] = v
                if "staff" in sp.cols and prev and prev["staff_marker"] is not None:
                    cells[f"{col_letter(sp.cols['staff'])}{row}"] = prev["staff_marker"]
                taken = {x["emp_id"] for x in self.snap.employees if x["emp_id"]}
                nid = make_emp_id(group, row, name, taken)
                cells[f"{col_letter(sp.app_col_plan['emp_id'])}{row}"] = nid
                cells.update(self._header_cells(sp))
                self.adapter.write_cells(group, cells)
                sp2 = parse_sheet(group, self._live_sheet(group))
                if not any(e["emp_id"] == nid and e["name"] == name for e in sp2.employees):
                    raise ApiError(502, "verify_failed", "The new row could not be confirmed in the workbook. Please refresh and check.")
                return nid, row
            nid, row = self._wrap(go)
            warn = self._audit(actor, [{"action": "add_employee", "emp_id": nid, "group": group, "note": f"row {row}"}])
            self._finish()
            return {"ok": True, "id": nid, "row": row, "warning": warn}

    def reveal(self, actor, ref):
        e = self.snap.by_id.get(ref) or self.snap.by_key.get(ref)
        if not e:
            raise ApiError(404, "not_found", "Employee not found.")
        w = self._audit(actor, [{"action": "reveal_sensitive", "emp_id": e["id"], "group": e["sheet"], "note": "Aadhaar/mobile shown to admin (values not logged)"}]) if not self.snap.id_setup_needed else None
        return {"aadhaar": e["aadhaar"], "mobile": e["mobile"]}

    # ---------- configuration ----------
    def _set_config_raw(self, key, value, actor):
        live = self._live_sheet(SHEET_CONFIG)
        row = None
        for r, rr in enumerate(live["values"][1:], start=2):
            if rr and not blank(rr[0]) and str(rr[0]).strip() == key:
                row = r
        payload = [key, json.dumps(value, default=str), self.s.now_iso(), actor]
        if row:
            self.adapter.write_block(SHEET_CONFIG, f"A{row}", [payload])
        else:
            self.adapter.append_rows(SHEET_CONFIG, [payload])

    def set_config(self, actor, key, value):
        self._require_setup()
        if key not in CONFIG_DEFAULTS or key in ("id_migration_done_at", "issue_resolutions"):
            raise ApiError(422, "validation", "Unknown or protected setting.")
        today = self.s.today()
        if key == "legacy_cutoff_date":
            if value in (None, ""):
                value = None
            else:
                st, d = to_date(value)
                if st != "date" or d > today:
                    raise ApiError(422, "validation", "Cut-off must be a valid date, not in the future.")
                value = d.isoformat()
        elif key == "daily_rate_source":
            if value not in (None, "", "per_day_pay"):
                raise ApiError(422, "validation", "Unsupported rate source.")
            value = value or None
        elif key == "attendance_statuses":
            if not isinstance(value, list) or not {"Present", "Absent"} <= set(value) or not set(value) <= set(ALL_ATTENDANCE_STATUSES):
                raise ApiError(422, "validation", "Must include Present and Absent; only known statuses allowed.")
        elif key == "paid_statuses":
            if not isinstance(value, list) or not value or not set(value) <= set(ALL_ATTENDANCE_STATUSES):
                raise ApiError(422, "validation", "Choose at least one known status.")
        elif key in ("locations", "designations"):
            if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
                raise ApiError(422, "validation", "Provide a list of names.")
            value = sorted({x.strip() for x in value})
        elif key == "required_fields":
            if not isinstance(value, list) or not set(value) <= {"designation", "location"}:
                raise ApiError(422, "validation", "Unsupported required field.")
        elif key == "block_future_attendance":
            value = bool(value)
        elif key == "recent_departure_days":
            if not isinstance(value, int) or not 1 <= value <= 365:
                raise ApiError(422, "validation", "Enter 1–365 days.")
        with self.sync.lock:
            before = self.snap.config.get(key)
            self._wrap(lambda: self._set_config_raw(key, value, actor))
            warn = self._audit(actor, [{"action": "config", "field": key, "before": before, "after": value}])
            self._finish()
            return {"ok": True, "warning": warn}

    def resolve_issue(self, actor, fingerprint, note, undo=False):
        self._require_setup()
        with self.sync.lock:
            res = dict(self.snap.config.get("issue_resolutions") or {})
            if undo:
                res.pop(fingerprint, None)
            else:
                res[fingerprint] = {"by": actor, "at": self.s.now_iso(), "note": (note or "")[:200]}
            self._wrap(lambda: self._set_config_raw("issue_resolutions", res, actor))
            warn = self._audit(actor, [{"action": "issue_unresolve" if undo else "issue_resolve", "field": fingerprint, "note": note}])
            self._finish()
            return {"ok": True, "warning": warn}

    def resolve_issues_bulk(self, actor, fingerprints, note):
        self._require_setup()
        with self.sync.lock:
            res = dict(self.snap.config.get("issue_resolutions") or {})
            now = self.s.now_iso()
            n = (note or "")[:200]
            for fp in fingerprints:
                res[fp] = {"by": actor, "at": now, "note": n}
            self._wrap(lambda: self._set_config_raw("issue_resolutions", res, actor))
            warn = self._audit(actor, [{"action": "issue_resolve_bulk", "count": len(fingerprints), "note": note}])
            self._finish()
            return {"ok": True, "warning": warn, "count": len(fingerprints)}


def _s(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    return str(v)


def _cmp(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        try:
            return float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v.strip()) else v.strip()
        except ValueError:
            return v.strip()
    return v
