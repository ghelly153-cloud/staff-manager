"""Read-side logic: employee views, filtering, summaries, payroll rows, group cards.
Every summary is computed from the CURRENT snapshot for exactly the population passed in."""
from collections import Counter
from datetime import date, timedelta

from . import calc
from .config import config_rules
from .masking import mask_aadhaar, mask_mobile
from .workbook.schema import blank

NOT_RECORDED = "Not Recorded"


def att_status(snap, e, d):
    if not e["id"]:
        return NOT_RECORDED
    rec = snap.attendance.get(e["id"], {}).get(d)
    return rec["status"] if rec and rec["status"] else NOT_RECORDED


def pay_for(snap, e, period=None):
    rules = config_rules(snap.config)
    legacy = calc.legacy_pay(e)
    recs = [{"date": d, "status": r["status"]} for d, r in snap.attendance.get(e["id"], {}).items() if r["status"]] if e["id"] else []
    dw = calc.datewise_pay(recs, e["rate"], rules, period)
    return {"legacy": legacy, "datewise": dw, "overall": calc.combine(legacy, dw)}


def warnings_for(e, pay):
    w = []
    st = pay["overall"]["status"]
    if st in ("rate_required", "invalid_rate"):
        w.append("Rate required" if st == "rate_required" else "Invalid rate")
    if pay["legacy"]["status"] == "no_attendance" and e["rate"]["state"] == "number":
        w.append("No attendance recorded")
    if st == "rules_required":
        w.append("Pay rule needed")
    for f in e.get("missing_fields", []):
        w.append(f"{f.title()} missing")
    if e["status"] == "Not Verified":
        w.append("Status not verified")
    if e.get("id_state") == "duplicate":
        w.append("Duplicate ID")
    return w


def employee_row(snap, e, d, period=None, with_pay=True):
    pay = pay_for(snap, e, period) if with_pay else None
    return {
        "ref": e["ref"], "id": e["id"], "id_state": e["id_state"], "writable": e["writable"],
        "name": e["name_display"], "group": e["sheet"], "row": e["row"],
        "designation": e["designation"], "location": e["location"], "status": e["status"],
        "att": att_status(snap, e, d), "dep_date": e["dep_date"].isoformat() if e["dep_date"] else None,
        "legacy_days": pay["legacy"]["days"] if pay else None, "rate": e["rate"]["value"], "rate_state": e["rate"]["state"],
        "amount": pay["overall"]["amount"] if pay else None, "pay_status": pay["overall"]["status"] if pay else None,
        "pay_label": calc.LABELS[pay["overall"]["status"]] if pay else None,
        "datewise_days": pay["datewise"]["days"] if pay else None,
        "warnings": warnings_for(e, pay) if pay else [],
        "aadhaar": mask_aadhaar(e["aadhaar"]), "mobile": mask_mobile(e["mobile"]),
    }


def parse_date(v, default=None):
    if not v:
        return default
    try:
        return date.fromisoformat(v)
    except ValueError:
        return default


def filter_employees(snap, f):
    """f keys: group, q, location, designation, status(current|all|Active|Departed|Not Verified), att, date,
    dep_days, dep_from, dep_to"""
    d = f["date"]
    out = []
    q = (f.get("q") or "").strip().lower()
    st = f.get("status") or "current"
    for e in snap.employees:
        if f.get("group") and e["sheet"] != f["group"]:
            continue
        if st == "current" and e["status"] == "Departed":
            continue
        if st in ("Active", "Departed", "Not Verified") and e["status"] != st:
            continue
        if q and q not in e["name_display"].lower() and q not in (e["id"] or "").lower():
            continue
        if f.get("location") and (e["location"] or "") != f["location"]:
            continue
        if f.get("location") == "" and False:
            continue
        if f.get("designation") and (e["designation"] or "") != f["designation"]:
            continue
        if f.get("att") and att_status(snap, e, d) != f["att"]:
            continue
        if f.get("dep_from") and (not e["dep_date"] or e["dep_date"] < f["dep_from"]):
            continue
        if f.get("dep_to") and (not e["dep_date"] or e["dep_date"] > f["dep_to"]):
            continue
        out.append(e)
    return out


def sort_employees(emps, key, desc):
    keyf = {"name": lambda e: e["name_display"].lower(), "group": lambda e: (e["sheet"], e["row"]),
            "location": lambda e: (e["location"] or "~").lower(), "designation": lambda e: (e["designation"] or "~").lower(),
            "status": lambda e: e["status"], "row": lambda e: (e["sheet"], e["row"])}.get(key or "row", lambda e: (e["sheet"], e["row"]))
    return sorted(emps, key=keyf, reverse=bool(desc))


def summary(snap, emps, d, period=None, today=None):
    today = today or d
    n = len(emps)
    by_status = Counter(e["status"] for e in emps)
    rows = [pay_for(snap, e, period) for e in emps]
    pay = calc.summarize(rows)
    cur = [e for e in emps if e["status"] != "Departed"]
    avail = bool(snap.attendance_by_date.get(d))
    c = Counter(att_status(snap, e, d) for e in cur)
    att = {"date": d.isoformat(), "available": avail, "applicable": len(cur),
           "present": c.get("Present", 0) if avail else None, "absent": c.get("Absent", 0) if avail else None,
           "leave": c.get("Leave", 0) if avail else None, "off": c.get("Weekly Off/Holiday", 0) if avail else None,
           "not_recorded": c.get(NOT_RECORDED, 0)}
    loc = Counter((e["location"] or "(blank)") for e in emps)
    rec = {}
    for k in (7, 30, 90):
        lo = today - timedelta(days=k)
        rec[str(k)] = sum(1 for e in emps if e["status"] == "Departed" and e["dep_date"] and lo <= e["dep_date"] <= today)
    return {
        "total": n, "active": by_status.get("Active", 0), "departed": by_status.get("Departed", 0),
        "not_verified": by_status.get("Not Verified", 0), "attendance": att, "pay": pay,
        "legacy_present_days": calc.num(sum((calc.D(r["legacy"]["days"]) for r in rows if r["legacy"]["days"] is not None), calc.D(0))),
        "datewise_present_days": sum(r["datewise"]["days"] or 0 for r in rows if r["datewise"]["status"] != "none"),
        "locations": dict(loc.most_common()),
        "incomplete_records": sum(1 for e in emps if e["missing_fields"]),
        "recent_departures": rec,
    }


def group_amounts(snap, sp, summ):
    s = sp.summary or {}
    out = {"has_summary_rows": bool(s.get("total_row"))}
    for k in ("advance", "sweets"):
        v = s.get(k)
        val = v["value"] if v and isinstance(v["value"], (int, float)) and not isinstance(v["value"], bool) else None
        out[k] = {"value": val, "ref": v["ref"] if v else None, "state": "recorded" if val is not None else ("blank" if v else "not_in_sheet")}
    b = s.get("balance")
    wb_val = b["value"] if b and isinstance(b["value"], (int, float)) and not isinstance(b["value"], bool) else None
    out["balance"] = {
        "app": None,
        "workbook_cached": wb_val,
        "ref": b["ref"] if b else None,
        "formula_verified": s.get("formula_verified", False),
        "matches_workbook": bool(wb_val is not None),
        "is_unverified_source": True,
        "note": "Raw spreadsheet cell value. Under current compensation policy, no group balance is an approved financial obligation or individual liability."
    }
    return out


def group_cards(snap, d, period, today):
    cards = []
    for g in snap.groups:
        sp = snap.sheet(g)
        emps = [e for e in snap.employees if e["sheet"] == g]
        sm = summary(snap, emps, d, period, today)
        cards.append({"name": g, "title": sp.title, "summary": sm, "amounts": group_amounts(snap, sp, sm),
                      "rows": sp.row_counts, "issue_count": sum(1 for i in snap.issues if i["sheet"] == g and i["severity"] != "info" and not i["resolution"])})
    return cards


def options(snap):
    cfg = snap.config
    locs = sorted({e["location"] for e in snap.employees if e["location"]} | set(cfg.get("locations") or []))
    des = sorted({e["designation"] for e in snap.employees if e["designation"]} | set(cfg.get("designations") or []))
    return {"locations": locs, "designations": des, "groups": snap.groups,
            "attendance_statuses": cfg.get("attendance_statuses") or ["Present", "Absent"]}
