import urllib.request
import time

url = 'https://staff-manager-6oso.onrender.com/js/pages2.js'
print(f"Checking {url}...", flush=True)
for attempt in range(1, 15):
    try:
        req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode('utf-8')
            has_fix = 'updateRowAndCardDom' in text
            print(f"Attempt {attempt}: length={len(text)}, has_optimistic_ui={has_fix}", flush=True)
            if has_fix:
                print("SUCCESS: Render is now running the updated code!", flush=True)
                break
    except Exception as e:
        print(f"Attempt {attempt}: error={e}", flush=True)
    time.sleep(10)
