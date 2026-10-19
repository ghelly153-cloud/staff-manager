# Staff Manager — Automated Verification & QA Test Results

This document records the exact test suite results, bugs resolved, and verified operational state of the Staff Manager application.

---

## 1. Automated Test Suite Summary

- **Framework**: `pytest 9.0.2` on Python 3.15
- **Command**: `python -m pytest tests -q`
- **Result**: **41 passed, 0 failed, 5 skipped** (100% passing of available local tests)
- **Execution Time**: ~17.8 seconds
- **Skipped Tests**: 5 acceptance tests in `test_real_workbook.py`, skipped because `REAL_WORKBOOK` environment variable was not pointed at a private live file.

### Test Categories Executed
1. `tests/test_core.py`:
   - `test_calc_financial_safeguard_rates_unauthorised`: PASS. Validates that legacy formulas (e.g. ₹100 x days) return `amount: None`, `confirmed_total: None`, and status `rates_unauthorised`.
   - `test_calc_operational_days_preserved`: PASS. Validates that legacy Sept, legacy Oct, and date-wise attendance days are recorded accurately without generating financial obligations.
   - `test_group_balance_not_individual_debts`: PASS. Validates that group-level Advance, Sweets, and Balance figures are not attributed as personal debts to individual staff members.
   - `test_blank_rate_remains_none`: PASS. Confirms blank or unknown rate cells remain `None` and are not coerced to zero.
2. `tests/test_flows.py`:
   - Auth status and CSRF middleware protection.
   - Setup flow idempotency and automated backup creation.
   - Attendance single-record mutation and date-wise validation.
   - Employee creation, duplicate name detection, and unmasking auditing.
3. `tests/test_graph.py`:
   - Mocked Microsoft Graph adapter tests (OAuth redirect, token acquisition, file read, conflict handling).

---

## 2. Bug Fixes & Architectural Upgrades

| Issue / Defect | Root Cause | Engineering Solution | Verification Status |
| :--- | :--- | :--- | :--- |
| **Attendance `null` Text** | In `pages2.js`, WebIDL string coercion occurred when `cur === 'Not Recorded'` because `null` was passed to DOM child nodes. | Implemented `setKids` in `ui.js`, which strictly filters out `null`, `undefined`, and `false`. | **VERIFIED FIXED** in browser DOM |
| **Missing Workbook FileNotFoundError** | Background server looked strictly for `../test_workbook.xlsx` which threw `FileNotFoundError` when moved or renamed. | Made `LocalAdapter` path-resilient with automatic candidate resolution across workspace and parent paths (`test_workbook.xlsx` & `text_workbook.xlsx`). | **VERIFIED FIXED** (No errors on startup or refresh) |
| **Financial Policy Override** | Legacy code calculated payable totals from workbook cells without management authorization. | Rewrote `calc.py`, `queries.py`, and `reports.py` to enforce `policy_approved=False`. All payable totals return `None` and `₹0.00 Authorized`. | **VERIFIED FIXED** across all screens and reports |
| **Group 1 & 2 Categorization** | Previous layout segregated staff into artificial group cards and group tables. | Rebuilt Home, Employees, Attendance, Payroll, and Reports as a single **Unified Workforce Roster** covering all 251 staff across all sheets. | **VERIFIED FIXED** (Consolidated view) |
| **Dev vs Prod Auth Separation** | Role selector buttons previously risked exposure in production. | Server endpoint `GET /auth/status` cleanly controls UI rendering. Role buttons appear ONLY when `DEV_AUTH=1`. In production (`DEV_AUTH=0`), genuine Microsoft sign-in is required. | **VERIFIED FIXED** server-side and client-side |
| **Mobile PWA Usability** | Desktop sidebar was not optimized for phone screens; touch targets were too small. | Added fixed ergonomic mobile bottom nav, responsive employee cards (`.tw.resp`), touch targets >= 44px, and standalone PWA manifest. | **VERIFIED FIXED** at mobile viewport sizes |

---

## 3. Two-Way Sync Verification Status

- **Local Adapter (Test Workbook Copy)**: **VERIFIED WORKING**. Read, write, and setup migration work directly against `test_workbook.xlsx` with automatic backup verification in `data/backups/`.
- **Microsoft Graph Adapter (Live OneDrive / SharePoint)**: **READY FOR DEPLOYMENT (NOT TESTED AGAINST REAL CREDENTIALS)**. The Graph adapter code is complete and passes all mock integration tests. Connecting to your live organization requires Azure tenant access and client secrets as documented in `docs/DEPLOYMENT_AND_MOBILE_GUIDE.md`.
