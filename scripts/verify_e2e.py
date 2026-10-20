import urllib.request
import urllib.parse
import json
import http.cookiejar

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def get(path):
    req = urllib.request.Request('http://127.0.0.1:8000' + path, headers={'X-Requested-With': 'emp-app'})
    with opener.open(req) as resp:
        return json.loads(resp.read().decode())

def post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request('http://127.0.0.1:8000' + path, data=body, headers={'Content-Type': 'application/json', 'X-Requested-With': 'emp-app'})
    with opener.open(req) as resp:
        return json.loads(resp.read().decode())

def put(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request('http://127.0.0.1:8000' + path, data=body, headers={'Content-Type': 'application/json', 'X-Requested-With': 'emp-app'}, method='PUT')
    with opener.open(req) as resp:
        return json.loads(resp.read().decode())

print("1. Checking auth status...")
st = get('/auth/status')
assert st['dev_auth'] == True
assert 'source_label' in st
print(f"   Auth status: authenticated={st['authenticated']}, label={st['source_label']}")

print("2. Logging in as admin...")
login = post('/auth/dev-login', {'role': 'admin'})
assert login['ok'] == True
print("   Admin login confirmed.")

print("3. Checking bootstrap...")
boot = get('/api/bootstrap')
assert boot['role'] == 'admin'
assert boot['total_employees'] == 251
print(f"   Bootstrap confirmed. Total staff: {boot['total_employees']}, groups: {boot['groups']}")

print("4. Checking dashboard...")
dash = get('/api/dashboard?date=2026-10-20')
assert dash['summary']['total'] == 251
assert 'quality' in dash
print(f"   Dashboard confirmed. Total: {dash['summary']['total']}, Active: {dash['summary']['active']}")

print("5. Checking employees pagination...")
emp1 = get('/api/employees?page=1&page_size=10')
assert emp1['total_pages'] == 26
assert len(emp1['items']) == 10
emp2 = get('/api/employees?page=2&page_size=10')
assert emp2['page'] == 2
print(f"   Employees pagination confirmed: Page 1 and 2, Total Pages = {emp1['total_pages']}")

print("6. Checking historical attendance for 2026-10-15...")
att_hist = get('/api/attendance?date=2026-10-15')
assert att_hist['date'] == '2026-10-15'
print(f"   Historical date retrieved: {att_hist['date']}, records: {len(att_hist['items'])}")

print("7. Testing targeted attendance marking...")
emp = emp1['items'][0]
ref_encoded = urllib.parse.quote(emp['ref'])
res_att = post(f'/api/attendance/{ref_encoded}', {'date': '2026-10-20', 'status': 'Present'})
assert res_att.get('ok') is True or 'saved' in res_att
print(f"   Targeted attendance marked: {res_att}")

print("8. Testing historical date attendance isolation...")
res_hist = post(f'/api/attendance/{ref_encoded}', {'date': '2026-10-15', 'status': 'Absent'})
assert res_hist.get('ok') is True or 'saved' in res_hist

# Verify 2026-10-15 shows Absent
check_15 = get('/api/attendance?date=2026-10-15')
rec_15 = next(x for x in check_15['items'] if x['ref'] == emp['ref'])
assert rec_15['att'] == 'Absent'

# Verify 2026-10-20 still shows Present (no cross-date contamination)
check_20 = get('/api/attendance?date=2026-10-20')
rec_20 = next(x for x in check_20['items'] if x['ref'] == emp['ref'])
assert rec_20['att'] == 'Present'
print("   Historical date isolation confirmed! 2026-10-15 = Absent, 2026-10-20 = Present.")

print("9. Checking options endpoint...")
opts = get('/api/options')
assert 'attendance_statuses' in opts
assert opts['timezone'] == 'Asia/Kolkata'
print(f"   Options endpoint confirmed: timezone={opts['timezone']}, statuses={opts['attendance_statuses']}")

print("10. Checking departed endpoint...")
dep = get('/api/departed')
assert 'active_count' in dep
assert 'total_staff' in dep
print(f"   Departed confirmed: active={dep['active_count']}, total_staff={dep['total_staff']}")

print("11. Checking audit log...")
aud = get('/api/audit')
assert 'items' in aud
assert len(aud['items']) > 0
latest_audit = aud['items'][0]
print(f"   Audit log confirmed: {len(aud['items'])} entries. Latest: {latest_audit.get('action')} on {latest_audit.get('emp_id')}")

print("12. Checking reports...")
reps = get('/api/reports')
assert len(reps) >= 4
print(f"   Reports confirmed: {[r['key'] for r in reps]}")

print("13. Checking financial policy safeguard...")
pay = get('/api/payroll')
p_summary = pay['summary']['pay']
assert p_summary['confirmed_total'] is None
assert p_summary['legacy_confirmed_total'] is None
assert p_summary['datewise_confirmed_total'] is None
assert p_summary['compensation_configured'] is False
assert p_summary['policy_status'] == "Rates not authorised"
print(f"   Financial safeguard confirmed: confirmed_total={p_summary['confirmed_total']}, policy_status='{p_summary['policy_status']}'.")
print("   Zero financial liabilities inferred.")

print("\n========================================================")
print("SUCCESS: ALL 13 END-TO-END VERIFICATION CHECKS PASSED!")
print("========================================================")
