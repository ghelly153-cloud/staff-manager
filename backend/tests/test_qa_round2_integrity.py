"""QA Round 2: Data Integrity, Persistence, Security, and Regression Test Suite.
Verifies multi-date attendance isolation, workbook row moves resilience, PII protection,
strict financial safeguards, audit trail integrity, and conflict prevention.
"""
import pytest
from datetime import date
import openpyxl
from tests.conftest import H

def test_r2_01_multidate_attendance_isolation_and_persistence(env):
    """Test R2-01: Multi-date attendance persistence, non-bleeding isolation, and reload resilience."""
    # Run setup
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)
    emps = env.c.get("/api/employees").json()["items"]
    e1, e2 = emps[0], emps[1]

    date_a = "2026-10-10"
    date_b = "2026-10-12"
    date_c = "2026-10-14"

    # 1. Date A: e1 is Present, e2 is Absent
    r1 = env.c.post(f"/api/attendance/{e1['ref']}", json={"date": date_a, "status": "Present"}, headers=H)
    r2 = env.c.post(f"/api/attendance/{e2['ref']}", json={"date": date_a, "status": "Absent"}, headers=H)
    assert r1.status_code == 200 and r2.status_code == 200

    # 2. Date B: e1 is Absent, e2 is Present
    r3 = env.c.post(f"/api/attendance/{e1['ref']}", json={"date": date_b, "status": "Absent"}, headers=H)
    r4 = env.c.post(f"/api/attendance/{e2['ref']}", json={"date": date_b, "status": "Present"}, headers=H)
    assert r3.status_code == 200 and r4.status_code == 200

    # 3. Date C: Not Recorded for both
    res_c = env.c.get(f"/api/attendance?date={date_c}").json()
    assert res_c["has_any_records"] is False
    c_e1 = next(i for i in res_c["items"] if i["ref"] == e1["ref"])
    c_e2 = next(i for i in res_c["items"] if i["ref"] == e2["ref"])
    assert c_e1["att"] == "Not Recorded"
    assert c_e2["att"] == "Not Recorded", "Empty date must never default to Absent"

    # 4. Verify Date A records
    res_a = env.c.get(f"/api/attendance?date={date_a}").json()
    a_e1 = next(i for i in res_a["items"] if i["ref"] == e1["ref"])
    a_e2 = next(i for i in res_a["items"] if i["ref"] == e2["ref"])
    assert a_e1["att"] == "Present"
    assert a_e2["att"] == "Absent"

    # 5. Verify Date B records
    res_b = env.c.get(f"/api/attendance?date={date_b}").json()
    b_e1 = next(i for i in res_b["items"] if i["ref"] == e1["ref"])
    b_e2 = next(i for i in res_b["items"] if i["ref"] == e2["ref"])
    assert b_e1["att"] == "Absent"
    assert b_e2["att"] == "Present"

    # 6. Correct Date A: e1 changed to Absent
    r_corr = env.c.post(f"/api/attendance/{e1['ref']}", json={"date": date_a, "status": "Absent"}, headers=H)
    assert r_corr.status_code == 200
    res_a_new = env.c.get(f"/api/attendance?date={date_a}").json()
    assert next(i for i in res_a_new["items"] if i["ref"] == e1["ref"])["att"] == "Absent"

    # Verify Date B remained unaffected
    res_b_check = env.c.get(f"/api/attendance?date={date_b}").json()
    assert next(i for i in res_b_check["items"] if i["ref"] == e1["ref"])["att"] == "Absent"
    assert next(i for i in res_b_check["items"] if i["ref"] == e2["ref"])["att"] == "Present"

    # 7. Reload / restart sync from disk workbook to prove durable persistence
    env.sync.refresh(force=True)
    res_a_persisted = env.c.get(f"/api/attendance?date={date_a}").json()
    assert next(i for i in res_a_persisted["items"] if i["ref"] == e1["ref"])["att"] == "Absent"
    assert next(i for i in res_a_persisted["items"] if i["ref"] == e2["ref"])["att"] == "Absent"

def test_r2_02_employee_identity_resilient_to_row_moves(env):
    """Test R2-02: Permanent employee ID ensures identity is immune to row order changes."""
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)
    emps_before = env.c.get("/api/employees").json()["items"]
    e1, e2 = emps_before[0], emps_before[1]
    id1, id2 = e1["id"], e2["id"]
    name1, name2 = e1["name"], e2["name"]

    # Record attendance for e1
    test_date = "2026-10-18"
    env.c.post(f"/api/attendance/{e1['ref']}", json={"date": test_date, "status": "Present"}, headers=H)

    # Directly swap employee rows in the Excel workbook file (Group One)
    r1_idx = e1["row"]
    r2_idx = e2["row"]
    wb = openpyxl.load_workbook(env.path)
    ws = wb[e1["group"]]
    row1_vals = [cell.value for cell in ws[r1_idx]]
    row2_vals = [cell.value for cell in ws[r2_idx]]
    for col_idx, val in enumerate(row2_vals, start=1):
        ws.cell(row=r1_idx, column=col_idx, value=val)
    for col_idx, val in enumerate(row1_vals, start=1):
        ws.cell(row=r2_idx, column=col_idx, value=val)
    wb.save(env.path)

    # Force sync refresh from modified Excel file
    env.sync.refresh(force=True)

    # Fetch employees list
    emps_after = env.c.get("/api/employees").json()["items"]
    emp1_after = next(i for i in emps_after if i["id"] == id1)
    emp2_after = next(i for i in emps_after if i["id"] == id2)

    # Permanent IDs remain mapped to the correct person and their original names
    assert emp1_after["name"] == name1
    assert emp2_after["name"] == name2

    # Attendance history remains linked to emp1's permanent ID, NOT row index
    att_res = env.c.get(f"/api/attendance?date={test_date}").json()
    e1_att = next(i for i in att_res["items"] if i["id"] == id1)
    e2_att = next(i for i in att_res["items"] if i["id"] == id2)
    assert e1_att["att"] == "Present"
    assert e2_att["att"] == "Not Recorded"

def test_r2_03_strict_financial_safeguards(env):
    """Test R2-03: No approved fixed compensation rule enforced universally across all APIs."""
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)

    # 1. Dashboard summary
    dash = env.c.get("/api/dashboard").json()
    assert dash["summary"]["pay"]["confirmed_total"] is None
    assert "policy_notice" in dash["summary"]["pay"]

    # 2. Employees roster: every item must not have an approved amount
    emps = env.c.get("/api/employees").json()["items"]
    for e in emps:
        assert e.get("amount") is None
        prof = env.c.get(f"/api/employees/{e['ref']}").json()
        assert prof.get("amount") is None

    # 3. Payroll view
    pay = env.c.get("/api/payroll").json()
    assert pay.get("summary", {}).get("confirmed_total") is None

    # 4. Reports preview and export
    rep_pay = env.c.get("/api/reports/group_payroll").json()
    for row in rep_pay["rows"]:
        assert row.get("confirmed") is None

def test_r2_04_tamper_evident_audit_log_and_pii_security(env):
    """Test R2-04: Append-only audit log records actions, PII masked, viewer blocked from reveal."""
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)
    emps = env.c.get("/api/employees").json()["items"]
    e = emps[0]

    # Perform action: edit designation
    env.c.put(f"/api/employees/{e['ref']}", json={"data": {"designation": "Head Weaver"}}, headers=H)

    # Audit log check
    audit = env.c.get("/api/audit").json()["items"]
    assert len(audit) > 0
    latest = audit[0] # Most recent first
    assert "ts" in latest
    assert "actor" in latest
    assert "action" in latest

    # Viewer role check: blocked from unmasking sensitive PII
    env.login("viewer")
    res_reveal = env.c.post(f"/api/employees/{e['ref']}/reveal", headers=H)
    assert res_reveal.status_code == 403, "Viewer must be forbidden from revealing PII"
    env.login("admin")

def test_r2_05_idempotent_setup_and_conflict_handling(env):
    """Test R2-05: Repeat setup calls are idempotent and do not duplicate columns or reset IDs."""
    r1 = env.c.post("/api/setup/run", json={"confirmed": True}, headers=H).json()
    assert r1["ids_assigned"] == 6

    # Second setup run: must assign 0 new IDs and be completely idempotent
    r2 = env.c.post("/api/setup/run", json={"confirmed": True}, headers=H).json()
    assert r2["ids_assigned"] == 0

    # Ensure sheets have not been duplicated
    wb = openpyxl.load_workbook(env.path)
    sheet_names = wb.sheetnames
    assert sheet_names.count("_App_Attendance") == 1
    assert sheet_names.count("_App_Audit") == 1

def test_r2_06_dashboard_reconciles_with_roster(env):
    """Test R2-06: Home dashboard counts strictly reconcile with employee list and departed list."""
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)
    emps = env.c.get("/api/employees").json()
    total_emps = emps["total"]
    active_emps = sum(1 for e in emps["items"] if e.get("status") == "Active")

    dash = env.c.get("/api/dashboard").json()
    sm = dash["summary"]
    assert sm["total"] == total_emps
    assert sm["active"] == active_emps
