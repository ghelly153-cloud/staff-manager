# Staff Manager — Unified Workforce Operations

Professional Excel-connected employee operations, attendance tracking, and unified workforce management with zero invented financial liabilities and full mobile PWA readiness.

## Documentation
- **Production Deployment & Phone Installation Guide**: [`docs/DEPLOYMENT_AND_MOBILE_GUIDE.md`](docs/DEPLOYMENT_AND_MOBILE_GUIDE.md) (14-step go-live, Microsoft Entra ID setup, PWA installation on iOS Safari and Android Chrome)
- **Automated Verification & Test Results**: [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md) (41 passed unit/integration tests, bug fixes, and honest status)
- **Local Test Workbook**: Both `test_workbook.xlsx` and `text_workbook.xlsx` are preserved safely in the workspace.

## Core Directives & Guarantees
1. **Financial Policy Guard**: No employee has an authorized compensation rate or payable amount. All legacy workbook formulas and payable totals are locked and withheld (`rates_unauthorised`, ₹0.00 payable). Operational attendance days (Sept legacy, Oct legacy, date-wise) are tracked accurately.
2. **Unified Workforce Roster**: All staff members across all workbook sheets are presented together in a single consolidated roster. There is no artificial Group 1 / Group 2 segregation.
3. **Honest Source Status**: The application clearly reports `Local Test Copy (Not Live)` during development. Live Microsoft 365 status is reported only when genuinely verified via Microsoft Graph API.
4. **Mobile PWA First**: Full responsive design with mobile employee cards, ergonomic touch targets (≥ 44px), bottom navigation, and app-shell caching. Personal employee data is never cached offline.

## Quick Local Run
```powershell
pip install -r requirements.txt
cd backend
$env:SOURCE="local"; $env:LOCAL_WORKBOOK_PATH="test_workbook.xlsx"; $env:DEV_AUTH="1"; $env:DATA_DIR="./data"; python -m uvicorn app.main:build_default_app --factory --port 8000
```
Open [http://localhost:8000](http://localhost:8000) → Select a test role.
Automated tests: `cd backend && python -m pytest tests -q`
