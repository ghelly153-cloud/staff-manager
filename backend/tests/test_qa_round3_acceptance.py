"""QA Round 3: Independent Client Acceptance and End-to-End Regression Suite.
Executes realistic day-in-the-life user journeys across all pages, validates frontend assets,
PWA manifests, responsive CSS layout rules, and error recovery workflows.
"""
import pytest
import os
import json
import re
from tests.conftest import H

def test_r3_01_end_to_end_daily_user_journey(env):
    """Test R3-01: Realistic operator journey:
    1. Check connection status and source
    2. Search and locate employee
    3. Open profile and update designation
    4. Save, reopen profile, verify persisted
    5. Navigate to attendance on historical date
    6. Mark attendance and verify persistent feedback
    7. Switch to another date, verify isolation
    8. Review departed list and audit trail
    9. Preview and export report
    """
    # Initialize system with setup
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)

    # 1. Connection status
    sync = env.c.get("/api/sync/status").json()
    assert sync["state"] in ("ok", "idle", "connected")
    assert sync["live"] is False # Local copy is truthfully flagged

    # 2. Search employee
    roster = env.c.get("/api/employees?q=Person 01").json()
    assert roster["total"] >= 1
    emp = roster["items"][0]
    ref = emp["ref"]

    # 3 & 4. Profile view, edit, reopen
    prof = env.c.get(f"/api/employees/{ref}").json()
    assert prof["name"] == emp["name"]
    res_update = env.c.put(f"/api/employees/{ref}", json={
        "data": {
            "name": prof["name"],
            "designation": "Senior Artisan",
            "location": "Workshop 1"
        }
    }, headers=H)
    assert res_update.status_code == 200

    prof_reopened = env.c.get(f"/api/employees/{ref}").json()
    assert prof_reopened["designation"] == "Senior Artisan"
    assert prof_reopened["location"] == "Workshop 1"

    # 5 & 6. Historical date attendance
    hist_date = "2026-10-05"
    res_mark = env.c.post(f"/api/attendance/{ref}", json={"date": hist_date, "status": "Present"}, headers=H)
    assert res_mark.status_code == 200
    att_check = env.c.get(f"/api/attendance?date={hist_date}").json()
    e_att = next(i for i in att_check["items"] if i["ref"] == ref)
    assert e_att["att"] == "Present"

    # 7. Switch to next day - must be isolated
    next_date = "2026-10-06"
    att_next = env.c.get(f"/api/attendance?date={next_date}").json()
    e_next = next(i for i in att_next["items"] if i["ref"] == ref)
    assert e_next["att"] == "Not Recorded"

    # 8. Departed list and audit inspection
    dep = env.c.get("/api/departed").json()
    assert "items" in dep
    audit = env.c.get("/api/audit").json()
    assert len(audit["items"]) >= 2

    # 9. Report export
    rep = env.c.get("/api/reports/all_employees?format=csv")
    assert rep.status_code == 200
    assert "text/csv" in rep.headers["content-type"]

def test_r3_02_error_handling_and_recovery(env):
    """Test R3-02: Backend returns clean structured error responses and blocks invalid operations."""
    env.c.post("/api/setup/run", json={"confirmed": True}, headers=H)

    # 1. Non-existent employee edit returns 404
    res_404 = env.c.put("/api/employees/non_existent_ref", json={"data": {}}, headers=H)
    assert res_404.status_code == 404
    assert res_404.json().get("code") == "not_found"

    # 2. Invalid attendance status rejected
    emps = env.c.get("/api/employees").json()["items"]
    e = emps[0]
    res_inv = env.c.post(f"/api/attendance/{e['ref']}", json={"date": "2026-10-01", "status": "InvalidStatus"}, headers=H)
    assert res_inv.status_code == 422 # Validation error

    # 3. Missing CSRF header rejected on mutations
    res_csrf = env.c.post(f"/api/attendance/{e['ref']}", json={"date": "2026-10-01", "status": "Present"})
    assert res_csrf.status_code in (400, 403)
    assert res_csrf.json().get("code") in ("csrf", "bad_csrf")

def test_r3_03_frontend_pwa_and_asset_integrity():
    """Test R3-03: Verify PWA manifest, service worker, and HTML meta tags exist and are valid."""
    fe_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
    
    # 1. index.html checks
    index_html = os.path.join(fe_dir, "index.html")
    assert os.path.exists(index_html)
    with open(index_html, "r", encoding="utf-8") as f:
        html = f.read()
    assert '<meta name="viewport"' in html
    assert 'viewport-fit=cover' in html or 'width=device-width' in html
    assert 'rel="manifest"' in html
    assert '<meta name="theme-color"' in html

    # 2. manifest.webmanifest checks
    manifest_path = os.path.join(fe_dir, "manifest.webmanifest")
    assert os.path.exists(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["display"] == "standalone"
    assert "Staff Manager" in manifest["name"]
    assert len(manifest["icons"]) >= 2

    # 3. Service worker checks
    sw_path = os.path.join(fe_dir, "sw.js")
    assert os.path.exists(sw_path)
    with open(sw_path, "r", encoding="utf-8") as f:
        sw = f.read()
    assert "CACHE_NAME" in sw
    assert "staff-manager-shell" in sw

def test_r3_04_mobile_modal_responsive_css_rules():
    """Test R3-04: Verify CSS responsive layout rules prevent popup splitting and touch traps."""
    css_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "styles.css"))
    assert os.path.exists(css_path)
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    # Verify body.modal-open does NOT disable touch-action
    assert "touch-action: none;" not in css, "touch-action: none on body breaks mobile scrolling"

    # Verify modal-body scrolling and height limits
    assert ".modal-body" in css
    assert "overflow-y: auto" in css
    assert "touch-action: pan-y" in css

    # Verify modal footer responsive wrapping
    assert ".modal-footer" in css
    assert "flex-wrap: wrap" in css or "flex-direction: column" in css

    # Verify saving and feedback animations exist
    assert "@keyframes pulse-dot" in css
    assert "@keyframes saved-pop" in css
    assert "@keyframes shake-failed" in css

def test_r3_05_javascript_compensation_and_attendance_safeguards():
    """Test R3-05: Verify JS client code strictly blocks unapproved compensation and double-clicks."""
    p1_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "js", "pages1.js"))
    p2_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "js", "pages2.js"))
    with open(p1_path, "r", encoding="utf-8") as f:
        p1 = f.read()
    with open(p2_path, "r", encoding="utf-8") as f:
        p2 = f.read()

    # Check for unapproved compensation text
    assert "Amount not approved" in p1
    assert "Amount not approved" in p2
    assert "badge('₹0.00 (Unapproved)'" not in p1

    # Check attendance saving lock against double clicks
    assert "r._saving" in p2, "In-flight protection must be present for attendance clicks"
    assert ".saved" in p2, "Visual save verification feedback must be applied"
