import requests
import time

base = "https://staff-manager-6oso.onrender.com"
s = requests.Session()
s.headers.update({"X-Requested-With": "emp-app", "Origin": base})

print("Pinging healthz...")
t0 = time.time()
r0 = s.get(f"{base}/healthz", timeout=30)
print(f"healthz: {r0.status_code} in {time.time()-t0:.2f}s: {r0.text}")

print("Logging in via dev-login...")
t0 = time.time()
r1 = s.post(f"{base}/auth/dev-login", json={"role": "admin"}, timeout=30)
print(f"dev-login: {r1.status_code} in {time.time()-t0:.2f}s: {r1.text}")

print("Fetching bootstrap...")
t0 = time.time()
r2 = s.get(f"{base}/api/bootstrap", timeout=30)
boot = r2.json()
print(f"bootstrap: {r2.status_code} in {time.time()-t0:.2f}s, today: {boot.get('today')}, emps: {boot.get('total_employees')}")

today_str = boot.get("today")
print(f"Fetching attendance for today ({today_str})...")
t0 = time.time()
r3 = s.get(f"{base}/api/attendance?date={today_str}", timeout=30)
data = r3.json()
print(f"attendance today: {r3.status_code} in {time.time()-t0:.2f}s, items count: {len(data.get('items', []))}, has_any_records: {data.get('has_any_records')}")
if data.get("items"):
    item0 = data["items"][0]
    print(f"Sample item 0: {item0.get('name')}, ref: {item0.get('ref')}, att: {item0.get('att')}, status: {item0.get('status')}")

print("Fetching attendance for past date (2026-10-15)...")
t0 = time.time()
r4 = s.get(f"{base}/api/attendance?date=2026-10-15", timeout=30)
data_past = r4.json()
print(f"attendance 2026-10-15: {r4.status_code} in {time.time()-t0:.2f}s, items count: {len(data_past.get('items', []))}, has_any_records: {data_past.get('has_any_records')}")

print("Fetching dashboard...")
t0 = time.time()
r5 = s.get(f"{base}/api/dashboard?date={today_str}", timeout=30)
dash = r5.json()
print(f"dashboard: {r5.status_code} in {time.time()-t0:.2f}s, total: {dash.get('summary', {}).get('total')}")

print("Fetching payroll...")
t0 = time.time()
r6 = s.get(f"{base}/api/payroll", timeout=30)
pay = r6.json()
print(f"payroll: {r6.status_code} in {time.time()-t0:.2f}s, total rows: {len(pay.get('rows', pay.get('employees', [])))}")
