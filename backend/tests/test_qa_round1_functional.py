"""QA Round 1: Developer and Functional Correctness Suite.
Executes comprehensive functional verification across all application routes and operations.
"""
import pytest
from datetime import date, timedelta
from tests.conftest import H

def test_r1_01_health_and_endpoints(env):
    """Test R1-01: Health check aliases respond with 200 and healthy status."""
    for path in ("/healthz", "/health", "/api/v1/health", "/api/health"):
        res = env.c.get(path)
        assert res.status_code == 200, f"{path} failed"
        assert res.json().get("ok") is True

def test_r1_02_auth_roles_and_session(env):
    """Test R1-02: Role login, session authorization, and logout."""
    # Viewer can read
    env.login("viewer")
    me = env.c.get("/api/me").json()
    assert me["role"] == "viewer"
    
    # Viewer cannot mutate attendance
    res = env.c.post("/api/attendance", json={"items": []}, headers=H)
    assert res.status_code == 403, "Viewer should be blocked from mutations"

    # Editor can mutate
    env.login("editor")
    me = env.c.get("/api/me").json()
    assert me["role"] == "editor"

    # Admin has highest rank
    env.login("admin")
    me = env.c.get("/api/me").json()
    assert me["role"] == "admin"

    # Logout
    env.c.post("/auth/logout", headers=H)
    res = env.c.get("/api/me")
    assert res.status_code == 401, "Should require sign in after logout"
    env.login("admin")

def test_r1_03_bootstrap_and_dashboard(env):
    """Test R1-03: Bootstrap and dashboard return accurate unified records."""
    boot = env.c.get("/api/bootstrap").json()
    assert boot["today"] is not None
    assert boot["role"] == "admin"
    assert len(boot["groups"]) == 2
    assert boot["total_employees"] == 6

    dash = env.c.get("/api/dashboard").json()
    sm = dash["summary"]
    assert sm["total"] == 6
    assert sm["pay"]["confirmed_total"] is None, "Financial policy safeguard must withhold payable total"
    assert "policy_notice" in sm["pay"]

def test_r1_04_employee_list_filtering_and_masking(env):
    """Test R1-04: Employee roster search, filter, pagination, and PII masking."""
    res = env.c.get("/api/employees?page=1&page_size=10").json()
    assert res["total"] == 6
    assert len(res["items"]) == 6
    
    # Masking
    for item in res["items"]:
        if item.get("aadhaar"):
            assert item["aadhaar"].startswith("XXXX"), f"Aadhaar was unmasked: {item['aadhaar']}"
        if item.get("mobile"):
            assert item["mobile"].startswith("XXXX"), f"Mobile was unmasked: {item['mobile']}"

    # Search by query
    res_q = env.c.get("/api/employees?q=Person 01").json()
    assert res_q["total"] == 1
    assert "Person 01" in res_q["items"][0]["name"]

    # Filter by group
    res_g = env.c.get("/api/employees?group=Group One").json()
    assert res_g["total"] == 4

def test_r1_05_employee_profile_and_edit_workflow(env):
    """Test R1-05: Employee profile view, setup enforcement, authorized edit, and admin reveal."""
    emps = env.c.get("/api/employees").json()["items"]
    e = emps[0]
    ref = e["ref"]

    # Profile view
    prof = env.c.get(f"/api/employees/{ref}").json()
    assert prof["name"] == e["name"]
    assert prof["amount"] is None, "Payable amount must be withheld"

    # Pre-setup edit attempt should return 409 id_setup_required
    res_blocked = env.c.put(f"/api/employees/{ref}", json={
        "data": {"name": e["name"], "designation": "Master Karigar"}
    }, headers=H)
    assert res_blocked.status_code == 409
    assert res_blocked.json().get("code") == "id_setup_required"

    # Run setup to assign permanent IDs and create attendance/audit sheets
    res_setup = env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)
    assert res_setup.status_code == 200
    assert res_setup.json()["ids_assigned"] == 6

    # Refresh employees list after setup
    emps = env.c.get("/api/employees").json()["items"]
    e = emps[0]
    ref = e["ref"]

    # Authorized edit now succeeds
    res_edit = env.c.put(f"/api/employees/{ref}", json={
        "data": {
            "name": e["name"],
            "designation": "Master Karigar",
            "location": "Hall A"
        }
    }, headers=H)
    assert res_edit.status_code == 200
    assert res_edit.json().get("ok") is True

    # Verify persisted in profile
    prof2 = env.c.get(f"/api/employees/{ref}").json()
    assert prof2["designation"] == "Master Karigar"

    # Admin reveal sensitive PII
    res_reveal = env.c.post(f"/api/employees/{ref}/reveal", headers=H)
    assert res_reveal.status_code == 200

def test_r1_06_datewise_attendance_workflow(env):
    """Test R1-06: Daily attendance, past date isolation, and persistence."""
    # Ensure setup is confirmed so mutation is permitted
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)
    emps = env.c.get("/api/employees").json()["items"]
    e = emps[0]
    past_date = "2026-10-15"
    today_date = date.today().isoformat()

    # Initial check for past date: Not Recorded
    att_past_0 = env.c.get(f"/api/attendance?date={past_date}").json()
    assert att_past_0["has_any_records"] is False

    # Mark Present on past date
    res_mark = env.c.post(f"/api/attendance/{e['ref']}", json={
        "date": past_date,
        "status": "Present"
    }, headers=H)
    assert res_mark.status_code == 200
    assert res_mark.json().get("ok") is True

    # Retrieve past date: must show Present
    att_past_1 = env.c.get(f"/api/attendance?date={past_date}").json()
    assert att_past_1["has_any_records"] is True
    item_past = next(i for i in att_past_1["items"] if i["ref"] == e["ref"])
    assert item_past["att"] == "Present"

    # Check today's date: must remain isolated and Not Recorded
    att_today = env.c.get(f"/api/attendance?date={today_date}").json()
    item_today = next(i for i in att_today["items"] if i["ref"] == e["ref"])
    assert item_today["att"] == "Not Recorded", "Past attendance must not leak into today"

    # Bulk attendance mark on today
    res_bulk = env.c.post("/api/attendance/bulk", json={
        "date": today_date,
        "status": "Present",
        "refs": [emps[0]["ref"], emps[1]["ref"]]
    }, headers=H)
    assert res_bulk.status_code == 200

    att_today_2 = env.c.get(f"/api/attendance?date={today_date}").json()
    assert att_today_2["items"][0]["att"] == "Present"
    assert att_today_2["items"][1]["att"] == "Present"

def test_r1_07_status_departure_and_reactivation(env):
    """Test R1-07: Departure record, history retention, and reactivation."""
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)
    emps = env.c.get("/api/employees").json()["items"]
    e = emps[2]
    dep_date = "2026-10-10"

    # Mark Departed
    res_dep = env.c.post(f"/api/status/{e['ref']}", json={
        "status": "Departed",
        "dep_date": dep_date,
        "reason": "Relocated to hometown"
    }, headers=H)
    assert res_dep.status_code == 200

    # Verify Departed in roster
    prof_dep = env.c.get(f"/api/employees/{e['ref']}").json()
    assert prof_dep["status"] == "Departed"
    assert prof_dep["dep_date"] == dep_date

    # Departed staff appears in departed list
    dep_list = env.c.get("/api/departed").json()
    assert any(i["ref"] == e["ref"] for i in dep_list["items"])

    # Reactivate staff
    res_reactivate = env.c.post(f"/api/status/{e['ref']}", json={
        "status": "Active"
    }, headers=H)
    assert res_reactivate.status_code == 200

    prof_act = env.c.get(f"/api/employees/{e['ref']}").json()
    assert prof_act["status"] == "Active"

    # Check audit log retained departure and reactivation
    audit = env.c.get("/api/audit").json()["items"]
    emp_audits = [a for a in audit if a.get("emp_id") == e["id"]]
    assert len(emp_audits) >= 2, "Departure and reactivation must be audited"

def test_r1_08_reports_and_exports(env):
    """Test R1-08: Report generation, CSV/Excel export, and financial lockout."""
    # JSON report preview
    rep = env.c.get("/api/reports/all_employees").json()
    assert rep["title"] == "All employees"
    assert len(rep["columns"]) > 0
    assert len(rep["rows"]) == 6
    # Headers are structured dicts with key and label
    for col in rep["columns"]:
        assert "key" in col and "label" in col

    # CSV Export
    rep_csv = env.c.get("/api/reports/all_employees?format=csv")
    assert rep_csv.status_code == 200
    assert "text/csv" in rep_csv.headers.get("content-type", "")

    # Payroll report must enforce no payment totals
    rep_pay = env.c.get("/api/reports/group_payroll").json()
    for row in rep_pay["rows"]:
        assert row.get("confirmed") is None, "Confirmed payroll amount must be None"

def test_r1_09_admin_subtabs_and_governance(env):
    """Test R1-09: Admin quality issues, status review, options, and setup plan."""
    # Quality issues
    q = env.c.get("/api/quality").json()
    assert "items" in q and "counts" in q

    # Options
    opts = env.c.get("/api/options").json()
    assert "attendance_statuses" in opts
    assert "Asia/Kolkata" in opts.get("timezone", "")

    # Setup plan (already done in test fixture)
    plan = env.c.get("/api/setup/plan").json()
    assert "already_done" in plan

    # Sync status
    sync = env.c.get("/api/sync/status").json()
    assert sync["state"] in ("ok", "idle", "connected")
    assert sync["live"] is False, "Local test copy must be truthful"
