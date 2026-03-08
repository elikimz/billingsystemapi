"""
Comprehensive backend route test — covers every endpoint.
Run: python3 test_all_routes.py
"""
import requests
import time
import sys

BASE = "http://localhost:8000"
API = f"{BASE}/api/v1"

GREEN = "\033[92m✓\033[0m"
RED   = "\033[91m✗\033[0m"
WARN  = "\033[93m!\033[0m"

passed = 0
failed = 0
warnings = 0

def ok(name, info=""):
    global passed
    passed += 1
    print(f"  {GREEN} {name}" + (f"  [{info}]" if info else ""))

def fail(name, info=""):
    global failed
    failed += 1
    print(f"  {RED} {name}" + (f"  [{info}]" if info else ""))

def warn(name, info=""):
    global warnings
    warnings += 1
    print(f"  {WARN} {name}" + (f"  [{info}]" if info else ""))

def test(name, condition, info="", expected_fail=False):
    if condition:
        ok(name, info)
    elif expected_fail:
        warn(name, f"EXPECTED FAIL — {info}")
    else:
        fail(name, info)
    return condition

# ─────────────────────────────────────────────
print("\n══════════════════════════════════════════")
print("  HotSpot Billing System — Full Route Test")
print("══════════════════════════════════════════\n")

# ── HEALTH ──────────────────────────────────
print("[ Health & Docs ]")
r = requests.get(f"{BASE}/health")
test("GET /health", r.status_code == 200 and r.json().get("status") == "healthy")

r = requests.get(f"{BASE}/")
test("GET / (root)", r.status_code == 200)

r = requests.get(f"{BASE}/docs")
test("GET /docs (Swagger UI)", r.status_code == 200)

r = requests.get(f"{BASE}/openapi.json")
test("GET /openapi.json", r.status_code == 200)

# ── AUTH ─────────────────────────────────────
print("\n[ Auth ]")

# Admin login
r = requests.post(f"{API}/auth/admin/login",
    json={"email": "admin@hotspot.local", "password": "Admin@1234"})
test("POST /auth/admin/login (valid)", r.status_code == 200 and "access_token" in r.json(),
     r.json().get("role",""))
ADMIN_TOKEN = r.json().get("access_token", "")
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

r = requests.post(f"{API}/auth/admin/login",
    json={"email": "admin@hotspot.local", "password": "wrongpass"})
test("POST /auth/admin/login (wrong password)", r.status_code == 401)

r = requests.post(f"{API}/auth/admin/login",
    json={"email": "nobody@x.com", "password": "Admin@1234"})
test("POST /auth/admin/login (unknown email)", r.status_code == 401)

# User register
ts = int(time.time())
phone = f"07{ts % 100000000:08d}"
r = requests.post(f"{API}/auth/register",
    json={"full_name": "Test User", "phone_number": phone, "password": "Pass@1234"})
test("POST /auth/register (new user)", r.status_code in [200, 201], phone)
USER_TOKEN = r.json().get("access_token", "")
USER_HEADERS = {"Authorization": f"Bearer {USER_TOKEN}"}

r = requests.post(f"{API}/auth/register",
    json={"full_name": "Test User", "phone_number": phone, "password": "Pass@1234"})
test("POST /auth/register (duplicate)", r.status_code == 400)

# User login
r = requests.post(f"{API}/auth/login",
    json={"phone_number": phone, "password": "Pass@1234"})
test("POST /auth/login (valid)", r.status_code == 200 and "access_token" in r.json())
USER_TOKEN = r.json().get("access_token", USER_TOKEN)
USER_HEADERS = {"Authorization": f"Bearer {USER_TOKEN}"}

r = requests.post(f"{API}/auth/login",
    json={"phone_number": phone, "password": "wrongpass"})
test("POST /auth/login (wrong password)", r.status_code == 401)

# ── PLANS ────────────────────────────────────
print("\n[ Plans ]")

r = requests.get(f"{API}/plans/")
test("GET /plans/ (public)", r.status_code == 200, f"{len(r.json())} plans")
plans = r.json()
PLAN_ID = plans[0]["id"] if plans else None

r = requests.post(f"{API}/plans/",
    headers=ADMIN_HEADERS,
    json={"name": f"AutoPlan-{ts}", "price": 25.0, "duration_hours": 2,
          "bandwidth_profile": "1Mbps", "device_limit": 1, "is_active": True})
test("POST /plans/ (admin create)", r.status_code in [200, 201], r.json().get("name",""))
NEW_PLAN_ID = r.json().get("id", PLAN_ID)

r = requests.get(f"{API}/plans/{NEW_PLAN_ID}")
test("GET /plans/{id}", r.status_code == 200, r.json().get("name",""))

r = requests.put(f"{API}/plans/{NEW_PLAN_ID}",
    headers=ADMIN_HEADERS,
    json={"description": "Updated description"})
test("PUT /plans/{id} (admin update)", r.status_code == 200)

r = requests.post(f"{API}/plans/", json={"name": "NoPlan", "price": 10.0, "duration_hours": 1})
test("POST /plans/ (unauthenticated)", r.status_code in [401, 403])

# ── VOUCHERS ─────────────────────────────────
print("\n[ Vouchers ]")

r = requests.post(f"{API}/vouchers/generate",
    headers=ADMIN_HEADERS,
    json={"plan_id": PLAN_ID, "quantity": 3, "prefix": "TST"})
test("POST /vouchers/generate (admin)", r.status_code in [200, 201],
     str([v['code'] for v in r.json()]) if r.status_code in [200,201] else r.text[:80])
VOUCHER_CODE = r.json()[0]["code"] if r.status_code in [200, 201] else None

r = requests.get(f"{API}/vouchers/", headers=ADMIN_HEADERS)
test("GET /vouchers/ (admin list)", r.status_code == 200, f"{len(r.json())} vouchers")

r = requests.get(f"{API}/vouchers/", )
test("GET /vouchers/ (unauthenticated)", r.status_code in [401, 403])

if VOUCHER_CODE:
    r = requests.post(f"{API}/vouchers/redeem",
        json={"code": VOUCHER_CODE, "phone_number": phone})
    test("POST /vouchers/redeem (valid code)", r.status_code == 200,
         r.json().get("message","") if r.status_code == 200 else r.text[:80])

    r = requests.post(f"{API}/vouchers/redeem",
        json={"code": VOUCHER_CODE, "phone_number": phone})
    test("POST /vouchers/redeem (already redeemed)", r.status_code == 400)

r = requests.post(f"{API}/vouchers/redeem",
    json={"code": "INVALID-CODE", "phone_number": phone})
test("POST /vouchers/redeem (invalid code)", r.status_code == 404)

# ── SUBSCRIPTIONS ────────────────────────────
print("\n[ Subscriptions ]")

r = requests.get(f"{API}/subscriptions/my", headers=USER_HEADERS)
test("GET /subscriptions/my (user)", r.status_code == 200, f"{len(r.json())} subs")

r = requests.get(f"{API}/subscriptions/", headers=ADMIN_HEADERS)
test("GET /subscriptions/ (admin list)", r.status_code == 200, f"{len(r.json())} subs")

r = requests.get(f"{API}/subscriptions/my")
test("GET /subscriptions/my (unauthenticated)", r.status_code in [401, 403])

# ── PAYMENTS ─────────────────────────────────
print("\n[ Payments ]")

r = requests.get(f"{API}/payments/", headers=ADMIN_HEADERS)
test("GET /payments/ (admin list)", r.status_code == 200, f"{len(r.json())} payments")

r = requests.get(f"{API}/payments/my", headers=USER_HEADERS)
test("GET /payments/my (user)", r.status_code == 200)

r = requests.post(f"{API}/payments/mpesa/initiate",
    headers=USER_HEADERS,
    json={"phone_number": "0799999999", "plan_id": PLAN_ID})
# M-Pesa may fail in sandbox — just check it's not a 500
test("POST /payments/mpesa/initiate", r.status_code != 500,
     f"status={r.status_code} (M-Pesa sandbox may reject)")

# ── USERS ─────────────────────────────────────
print("\n[ Users ]")

r = requests.get(f"{API}/users/me", headers=USER_HEADERS)
test("GET /users/me (user profile)", r.status_code == 200,
     r.json().get("phone_number",""))

r = requests.put(f"{API}/users/me", headers=USER_HEADERS,
    json={"full_name": "Updated Name"})
test("PUT /users/me (update profile)", r.status_code == 200)

r = requests.get(f"{API}/users/me")
test("GET /users/me (unauthenticated)", r.status_code in [401, 403])

# ── ADMIN ENDPOINTS ───────────────────────────
print("\n[ Admin ]")

r = requests.get(f"{API}/admin/dashboard", headers=ADMIN_HEADERS)
test("GET /admin/dashboard", r.status_code == 200, str(r.json()))

r = requests.get(f"{API}/admin/users", headers=ADMIN_HEADERS)
test("GET /admin/users", r.status_code == 200, f"{len(r.json())} users")

r = requests.get(f"{API}/admin/settings", headers=ADMIN_HEADERS)
test("GET /admin/settings", r.status_code == 200, f"{len(r.json())} settings")

r = requests.get(f"{API}/admin/audit-logs", headers=ADMIN_HEADERS)
test("GET /admin/audit-logs", r.status_code == 200)

r = requests.get(f"{API}/admin/sms-logs", headers=ADMIN_HEADERS)
test("GET /admin/sms-logs", r.status_code == 200)

r = requests.get(f"{API}/admin/admins", headers=ADMIN_HEADERS)
test("GET /admin/admins", r.status_code == 200, f"{len(r.json())} admins")

r = requests.post(f"{API}/admin/admins", headers=ADMIN_HEADERS,
    json={"full_name": f"New Admin {ts}", "email": f"admin{ts}@test.com",
          "password": "Admin@1234", "role": "admin"})
test("POST /admin/admins (create admin)", r.status_code in [200, 201],
     r.json().get("email","") if r.status_code in [200,201] else r.text[:80])

r = requests.get(f"{API}/admin/dashboard")
test("GET /admin/dashboard (unauthenticated)", r.status_code in [401, 403])

# ── ROUTERS ───────────────────────────────────
print("\n[ Routers/Access Points ]")

r = requests.get(f"{API}/admin/routers", headers=ADMIN_HEADERS)
test("GET /admin/routers", r.status_code == 200, f"{len(r.json())} routers")

r = requests.post(f"{API}/admin/routers", headers=ADMIN_HEADERS,
    json={"name": f"Router-{ts}", "ip_address": "192.168.1.1",
          "location": "Main Office"})
test("POST /admin/routers (create)", r.status_code in [200, 201],
     r.json().get("name","") if r.status_code in [200,201] else r.text[:80])

# ── SUMMARY ───────────────────────────────────
total = passed + failed + warnings
print(f"\n══════════════════════════════════════════")
print(f"  Results: {passed}/{total} passed  |  {failed} failed  |  {warnings} warnings")
print(f"══════════════════════════════════════════\n")

if failed > 0:
    sys.exit(1)
