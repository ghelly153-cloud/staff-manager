from datetime import date
from app import calc
from app.workbook.parser import parse_sheet
from app.workbook.schema import to_number, to_date
from tests.conftest import H

# ---------- B. payroll calculations & financial safeguards ----------
def N(v): return {"state": "number", "value": v}
BL = {"state": "blank", "value": None}
def emp(s, o, r): return {"sept": s, "octo": o, "rate": r}

def test_5_days_x_100():
    # Under current policy, no payable amount is authorised
    r = calc.legacy_pay(emp(BL, N(5), N(100)))
    assert r["days"] == 5 and r["amount"] is None and r["status"] == "rates_unauthorised"
    assert calc.legacy_pay(emp(BL, N(5), N(100)), policy_approved=True)["amount"] == 500

def test_sept5_oct25_total30():
    r = calc.legacy_pay(emp(N(5), N(25), N(100)))
    assert r["days"] == 30 and r["amount"] is None

def test_30_days_x_100():
    r = calc.legacy_pay(emp(N(5), N(25), N(100)))
    assert r["days"] == 30 and r["amount"] is None
    assert calc.legacy_pay(emp(N(5), N(25), N(100)), policy_approved=True)["amount"] == 3000

def test_missing_rate_not_zero():
    r = calc.legacy_pay(emp(N(5), N(25), BL))
    assert r["status"] == "rate_required" and r["amount"] is None

def test_explicit_zero_rate_is_not_authorised():
    r = calc.legacy_pay(emp(N(5), N(25), N(0)))
    assert r["status"] == "rates_unauthorised" and r["amount"] is None
    assert calc.legacy_pay(emp(N(5), N(25), N(0)), policy_approved=True)["amount"] == 0

def test_blank_attendance_is_not_absent_or_zero():
    r = calc.legacy_pay(emp(BL, BL, N(100)))
    assert r["status"] == "no_attendance" and r["amount"] is None

def test_fractional_days():
    r = calc.legacy_pay(emp(BL, N(7.5), N(100)))
    assert r["days"] == 7.5 and r["amount"] is None
    assert calc.legacy_pay(emp(BL, N(7.5), N(100)), policy_approved=True)["amount"] == 750

def test_incomplete_excluded_from_confirmed_total():
    a = {"legacy": calc.legacy_pay(emp(N(5), N(25), N(100)))}
    b = {"legacy": calc.legacy_pay(emp(N(5), N(25), BL))}
    for x in (a, b):
        x["datewise"] = calc.datewise_pay([], x["legacy"] and {"state": "blank", "value": None}, {})
        x["overall"] = calc.combine(x["legacy"], x["datewise"])
    s = calc.summarize([a, b])
    assert s["confirmed_total"] is None and s["confirmed_count"] == 0 and s["rate_missing_count"] == 1 and s["total_legacy_days"] == 60

    # If policy were explicitly approved for record a:
    a_app = {"legacy": calc.legacy_pay(emp(N(5), N(25), N(100)), policy_approved=True)}
    a_app["datewise"] = calc.datewise_pay([], {"state": "blank", "value": None}, {}, policy_approved=True)
    a_app["overall"] = calc.combine(a_app["legacy"], a_app["datewise"], policy_approved=True)
    s_app = calc.summarize([a_app, b], policy_approved=True)
    assert s_app["confirmed_total"] == 3000 and s_app["confirmed_count"] == 1

def test_datewise_needs_rules_and_no_double_count():
    recs = [{"date": date(2026, 10, 10), "status": "Present"}, {"date": date(2026, 10, 20), "status": "Present"}]
    none = calc.datewise_pay(recs, N(100), {"paid_statuses": ["Present"]})
    assert none["status"] == "rules_required" and none["amount"] is None
    rules = {"paid_statuses": ["Present"], "legacy_cutoff_date": date(2026, 10, 17), "daily_rate_source": "per_day_pay"}
    ok = calc.datewise_pay(recs, N(100), rules)
    assert ok["days"] == 1 and ok["amount"] is None and ok["excluded_legacy_days"] == 1     # the Oct-10 day is covered by legacy totals
    ok_app = calc.datewise_pay(recs, N(100), rules, policy_approved=True)
    assert ok_app["days"] == 1 and ok_app["amount"] == 100

# ---------- A. workbook mapping ----------
def test_discovery_and_classification(env):
    sn = env.svc.snap
    assert sn.groups == ["Group One", "Group Two"] and [s["name"] for s in sn.skipped] == ["Notes"]
    g1 = sn.sheet("Group One")
    assert len(g1.employees) == 4 and g1.row_counts["blank_formatted"] == 8 and g1.row_counts["summary"] == 4
    assert g1.summary["formula_verified"] and g1.summary["total_row"]
    assert all(e["designation"] != "Total" for e in g1.employees)

def test_flags_not_fixes(env):
    codes = {i["code"] for i in env.svc.snap.issues}
    assert {"TITLE_MISMATCH", "NAME_WHITESPACE", "DUPLICATE_LOOKING", "RATE_REQUIRED", "INCOMPLETE_RECORD", "GROUP_AMOUNT_UNUSUAL", "STATUS_NOT_VERIFIED", "ID_SETUP_PENDING"} <= codes
    assert any(e["name"] == "Test Person 03 " for e in env.svc.snap.employees)       # source spelling preserved
    assert len(env.svc.snap.employees) == 6                                          # duplicate-looking kept as separate people

def test_status_default_not_verified_and_counts(env):
    d = env.c.get("/api/dashboard").json()["summary"]
    assert d["total"] == 6 and d["not_verified"] == 6 and d["active"] == 0 and d["departed"] == 0
    assert d["attendance"]["available"] is False and d["attendance"]["present"] is None   # no data != 0

# ---------- permissions / security ----------
def test_requires_signin(env):
    env.c.cookies.clear(); assert env.c.get("/api/dashboard").status_code == 401
def test_csrf_header_required(env):
    assert env.c.post("/api/sync/refresh").status_code == 403
def test_viewer_cannot_write(env):
    env.login("viewer"); r = env.c.post("/api/attendance", json={"items": []}, headers=H); assert r.status_code == 403
def test_masking_in_lists_and_exports(env):
    env.login("admin"); env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)
    ref = env.c.get("/api/employees").json()["items"][0]["ref"]
    assert env.c.patch(f"/api/employees/{ref}", json={"changes": {"aadhaar": "234123412346", "mobile": "9876543210"}, "expected": {}}, headers=H).status_code == 200
    items = env.c.get("/api/employees").json()["items"]
    assert items[0]["aadhaar"] == "XXXX XXXX 2346" and items[0]["mobile"] == "XXXXXX3210"
    for fmt in ("csv", "xlsx"):
        body = env.c.get(f"/api/reports/all_employees?format={fmt}").content
        assert b"234123412346" not in body and b"9876543210" not in body
    assert "234123412346" not in env.c.get(f"/api/employees/{ref}").text
    env.login("editor"); assert env.c.post(f"/api/employees/{ref}/reveal", headers=H).status_code == 403
    env.login("admin"); assert env.c.post(f"/api/employees/{ref}/reveal", headers=H).json()["aadhaar"] == "234123412346"

def test_auth_status_endpoint(env):
    res = env.c.get("/auth/status").json()
    assert res["dev_auth"] is True
    assert res["source"] == "local"
    assert res["authenticated"] is True
    assert res["role"] == "admin"

def test_financial_policy_safeguards_in_dashboard_and_reports(env):
    d = env.c.get("/api/dashboard").json()
    pay = d["summary"]["pay"]
    assert pay["confirmed_total"] is None
    assert pay["confirmed_count"] == 0
    assert pay["compensation_configured"] is False
    assert "not authorised" in pay["policy_status"].lower() or "not configured" in pay["policy_notice"].lower()

    # Employee list verification: no amounts calculated
    emps = env.c.get("/api/employees").json()
    for item in emps["items"]:
        assert item["amount"] is None
        assert item["pay_status"] in ("rates_unauthorised", "rate_required", "no_attendance")

    # Reports verification: no payable total
    rep = env.c.get("/api/reports/employee_pay").json()
    assert any("not approved" in n.lower() or "not authorised" in n.lower() for n in rep["meta"]["notes"])
    for r in rep["rows"]:
        assert "amount" not in r or r.get("amount") is None

    # Group amounts verification: balance app is None
    g = env.c.get("/api/groups/Group One").json()["amounts"]
    assert g["balance"]["app"] is None

