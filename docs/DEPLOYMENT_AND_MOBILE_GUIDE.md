# Staff Manager — Production Deployment & Mobile PWA Guide

This comprehensive, beginner-friendly guide walks you step-by-step through taking Staff Manager from your local computer into live, secure production connected to your organization's Microsoft 365 Excel workbook, and installing it on your phone as a Progressive Web App (PWA).

---

## Architecture Overview

```
                                      +------------------------------------+
                                      |   Microsoft 365 Cloud (Graph API)  |
                                      |   OneDrive / SharePoint Workbook   |
                                      +-----------------+------------------+
                                                        ^
                                                        | HTTPS / OAuth 2.0
                                                        v
+-------------------------------+             +------------------------------------+
|  Mobile Phone (Safari/Chrome) |             |     Production Backend Host        |
|  Installed PWA (Touch-ready)  | <=========> |     FastAPI Python Web Service     |
|  https://your-domain.com      |   HTTPS     |     Encrypted Token Disk Storage   |
+-------------------------------+             +------------------------------------+
```

- **Frontend**: Vanilla JavaScript Progressive Web App (PWA) with responsive mobile cards, touch-ergonomic attendance controls, and offline app-shell caching. Personal employee data and authentication flows are never cached offline to preserve privacy.
- **Backend**: FastAPI running on Python 3.11+, using MSAL (Microsoft Authentication Library) on the server. Client secrets and encryption tokens never reach browser code.
- **Two-way Sync**: Direct read/write to the Excel workbook using the Microsoft Graph REST API, verified with transaction auditing and conflict detection.

---

## 14-Step Production Go-Live Roadmap

### Step 1: Distinguish Local Development vs. Production
- **Local Development**:
  - `SOURCE=local`
  - `LOCAL_WORKBOOK_PATH=test_workbook.xlsx`
  - `DEV_AUTH=1`
  - Runs on `http://localhost:8000`. Features the role-testing controls ("Test as admin / editor / viewer").
- **Production Environment**:
  - `SOURCE=graph`
  - `DEV_AUTH=0` (Crucial: Disables role-selection controls; enforces Microsoft Entra ID authentication).
  - Runs on a public HTTPS URL (e.g. `https://staff.yourdomain.com`).

---

### Step 2: Register Application in Microsoft Entra ID (Azure Portal)
1. Sign in to the [Microsoft Entra Admin Center](https://entra.microsoft.com/) or Azure Portal.
2. Navigate to **Identity > Applications > App registrations** and click **New registration**.
3. Fill in:
   - **Name**: `Staff Manager Production`
   - **Supported account types**: `Accounts in this organizational directory only (Single tenant)`
   - **Redirect URI (Web)**: `https://your-domain.com/auth/callback`
4. Click **Register**. Note down the **Application (client) ID** and **Directory (tenant) ID**.

---

### Step 3: Generate Client Secret
1. In your registered app, go to **Certificates & secrets > Client secrets**.
2. Click **New client secret**, description `StaffManagerProd`, expiry 12-24 months.
3. Copy the **Value** immediately (it is only shown once).

---

### Step 4: Configure Least-Privilege Graph API Permissions
1. In the app registration, select **API permissions > Add a permission > Microsoft Graph**.
2. Choose **Delegated permissions**:
   - `User.Read` (Sign in and read user profile)
   - `Files.ReadWrite` (Read and write to user's OneDrive files)
   - *(Optional)*: If the workbook is stored in a SharePoint document library shared with the team, choose `Files.ReadWrite.All`.
3. Click **Grant admin consent** for your organization.

---

### Step 5: Locate your Workbook `GRAPH_DRIVE_ID` and `GRAPH_ITEM_ID`
To point the app at the exact master Excel file:
1. Open the [Microsoft Graph Explorer](https://developer.microsoft.com/graph/graph-explorer).
2. Sign in with your Microsoft 365 organizational admin account.
3. If stored in OneDrive:
   - Run query: `GET https://graph.microsoft.com/v1.0/me/drive/root/children`
   - Locate your master workbook in the JSON response.
   - Note down `parentReference.driveId` as your `GRAPH_DRIVE_ID`.
   - Note down `id` as your `GRAPH_ITEM_ID`.
4. If stored in a SharePoint Document Library:
   - Run query: `GET https://graph.microsoft.com/v1.0/sites/{site-id}/drives`
   - Browse into the drive's root children to find the exact file `id`.

---

### Step 6: Generate Encryption Keys and Session Secrets
Run this in PowerShell or Python to generate strong, unique random secrets:
```python
import secrets
from cryptography.fernet import Fernet

print("SESSION_SECRET:", secrets.token_urlsafe(48))
print("TOKEN_ENCRYPTION_KEY:", Fernet.generate_key().decode())
print("WEBHOOK_CLIENT_STATE:", secrets.token_hex(24))
```

---

### Step 7: Prepare Production Environment Variables (`.env`)
Create a secure `.env` file on your production server:
```ini
SOURCE=graph
DEV_AUTH=0
PUBLIC_BASE_URL=https://staff.yourdomain.com
AZURE_TENANT_ID=your-tenant-id-here
AZURE_CLIENT_ID=your-client-id-here
AZURE_CLIENT_SECRET=your-client-secret-here
GRAPH_DRIVE_ID=your-drive-id-here
GRAPH_ITEM_ID=your-item-id-here
SESSION_SECRET=your-generated-session-secret
TOKEN_ENCRYPTION_KEY=your-generated-fernet-key
WEBHOOK_CLIENT_STATE=your-generated-webhook-state
ROLE_ADMINS=admin@yourdomain.com,owner@yourdomain.com
ROLE_EDITORS=supervisor@yourdomain.com,manager@yourdomain.com
ROLE_VIEWERS=auditor@yourdomain.com
DATA_DIR=/var/data/staff-manager
APP_TIMEZONE=Asia/Kolkata
AUTO_ASSIGN_NEW_IDS=1
SYNC_INTERVAL_SECONDS=30
```

---

### Step 8: Choose and Configure Production Hosting
Pick the hosting option that suits your infrastructure:
- **Option A (Fully Managed Cloud — Render / Railway)**:
  - Connect your repository.
  - Set Build Command: `pip install -r requirements.txt`
  - Set Start Command: `cd backend && uvicorn app.main:build_default_app --factory --host 0.0.0.0 --port $PORT`
  - Attach a persistent volume to `/var/data/staff-manager` so encrypted token cache and audit logs survive restarts.
- **Option B (Ubuntu Linux VPS with Nginx + Systemd)**:
  - Run Uvicorn via a systemd service listening on `127.0.0.1:8000`.
  - Use Nginx as a reverse proxy with Let's Encrypt SSL (`certbot`).

---

### Step 9: Configure Nginx Reverse Proxy with HTTPS
```nginx
server {
    server_name staff.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_read_timeout 120s;
    }

    listen 443 ssl http2;
    ssl_certificate /etc/letsencrypt/live/staff.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/staff.yourdomain.com/privkey.pem;
}
```

---

### Step 10: Start Service, Verify Health & One-Time Connect
1. Start the service and inspect logs: `journalctl -u staff-manager -f`
2. Navigate to `https://staff.yourdomain.com`.
3. Sign in as an administrator via Microsoft Entra ID.
4. Navigate to **Sync & Health (`#/sync`)**.
5. Click **Connect Workbook** to perform the one-time OAuth consent granting file read/write permissions.
6. Verify the status updates to **Connected** with the live timestamp.

---

### Step 11: Execute Safe Workbook Setup
1. In the app, navigate to **Admin > Workbook Setup**.
2. Review the Migration Plan (checks for permanent IDs and helper columns).
3. Click **Run Safe Workbook Setup**:
   - Automatically takes a verified backup before modifying the workbook.
   - Assigns stable permanent IDs (`EMP-xxxxxxxx`) to all rows.
   - Installs helper columns and support sheets (`_App_Attendance`, `_App_Audit`, `_App_Config`).
4. Read-only lockout will clear automatically once verified.

---

### Step 12: Test Two-Way Sync Reliably
1. **Excel → App**: Open the master workbook in Excel Online or desktop. Update a test employee's location to "Test Location". Click **Refresh Source** in the app. Verify the change appears immediately.
2. **App → Excel**: In the app, mark an employee's attendance as "Present" for today. Open the Excel workbook and inspect the `_App_Attendance` sheet. Verify the attendance record is written with timestamp and operator ID. Revert test change.

---

### Step 13: Install on Mobile Phone (PWA)

#### On Apple iPhone (iOS Safari)
1. Open **Safari** and navigate to your production URL (`https://staff.yourdomain.com`).
2. Log in with your Microsoft 365 organization account.
3. Tap the **Share button** (square with upward arrow) at the bottom toolbar.
4. Scroll down and tap **Add to Home Screen**.
5. Confirm name "Staff Manager" and tap **Add**.
6. Open the app from your home screen. It will launch in full-screen standalone mode without Safari browser toolbars, with touch-optimized ergonomics and bottom navigation.

#### On Google Android (Google Chrome)
1. Open **Chrome** and navigate to `https://staff.yourdomain.com`.
2. Sign in with your organizational account.
3. Tap the **Three dots menu (⋮)** in the top right.
4. Tap **Install app** or **Add to Home screen**.
5. The Staff Manager app icon will appear on your phone home screen and app drawer.

---

### Step 14: Maintenance, Backups & Recovery
- **Automatic Backups**: The application creates timestamped backups in `DATA_DIR/backups/` prior to every schema migration or major mutation.
- **Session Expiry**: Sessions are configured with an 8-hour rolling lifetime and secure HTTP-only cookies.
- **Token Rotation**: The MSAL encrypted token cache automatically refreshes access tokens in the background before they expire.
- **Disaster Recovery**: If the workbook connection encounters network throttling or Microsoft API downtime, the system enters an honest `stale` state, preserving local edits safely until connectivity resumes.
