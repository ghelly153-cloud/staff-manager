@echo off
title Staff Manager
echo ===================================================
echo Starting Staff Manager (Backend + Mobile Tunnel)
echo ===================================================

cd /d "%~dp0backend"
echo [1/2] Starting backend on port 8000...
start "Staff Manager Backend" cmd /k "set SOURCE=local&& set LOCAL_WORKBOOK_PATH=test_workbook.xlsx&& set DEV_AUTH=1&& set DATA_DIR=./data&& python -m uvicorn app.main:build_default_app --factory --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak >nul

cd /d "%~dp0"
echo [2/2] Starting Cloudflare Tunnel for phone / mobile access...
start "Cloudflare Tunnel" cmd /k "npx -y cloudflared tunnel --url http://localhost:8000"

echo.
echo ===================================================
echo Server is running!
echo Look at the "Cloudflare Tunnel" window to see your
echo secure https://*.trycloudflare.com web address.
echo ===================================================
pause
