"""Comprehensive API test for the HotSpot Billing System."""
import requests

BASE = "http://localhost:8000/api/v1"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

def test(name, condition, info=""):
    status = PASS if condition else FAIL
    print(f"  {status} {name}" + (f" — {info}" if info else ""))
    return condition

print("\n=== HotSpot Billing System — API Tests ===\n")

# 1. Health
r = requests.get("http://localhost:8000/health")
test("Health check", r.status_code == 200 and r.json().get("status") == "healthy")

# 2. Admin login
r = requests.post(f"{BASE}/auth/admin/login", json={"email":"admin@hotspot.local","password":"Admin@1234"})
test("Admin login", r.status_code == 200 and "access_token" in r.json())
token = r.json().get("access_token", "")
headers = {"Authorization": f"Bearer {token}"}

# 3. Plans
r = requests.get(f"{BASE}/plans/")
test("List plans (public)", r.status_code == 200, f"{len(r.json())} plans")
plans = r.json()
plan_id = plans[0]["id"] if plans else None

# 4. Create plan
import time
unique_name = f"Test Plan {int(time.time())}"
r = requests.post(f"{BASE}/plans/", headers=headers, json={
    "name": unique_name, "price": 30.0, "duration_hours": 3,
    "bandwidth_profile": "2Mbps", "device_limit": 1, "is_active": True
})
test("Create plan (admin)", r.status_code in [200, 201], r.json().get("name",r.text[:80]) if r.status_code in [200,201] else r.text[:80])

# 5. Dashboard
r = requests.get(f"{BASE}/admin/dashboard", headers=headers)
test("Admin dashboard", r.status_code == 200, str(r.json()))

# 6. User registration
r = requests.post(f"{BASE}/auth/register", json={
    "full_name": "Jane Doe", "phone_number": "0799999999", "password": "Pass@1234"
})
test("User registration", r.status_code in [200, 201] or "already" in r.text.lower(), r.text[:80])

# 7. User login
r = requests.post(f"{BASE}/auth/login", json={"phone_number": "0799999999", "password": "Pass@1234"})
test("User login", r.status_code == 200 and "access_token" in r.json())
user_token = r.json().get("access_token", "")
user_headers = {"Authorization": f"Bearer {user_token}"}

# 8. Voucher generation
if plan_id:
    r = requests.post(f"{BASE}/vouchers/generate", headers=headers, json={
        "plan_id": plan_id, "quantity": 5, "prefix": "WIFI"
    })
    test("Generate vouchers", r.status_code in [200, 201], f"status={r.status_code}")
    if r.status_code in [200, 201]:
        vouchers = r.json()
        test("Voucher codes returned", isinstance(vouchers, list) and len(vouchers) == 5, f"{[v['code'] for v in vouchers]}")
        voucher_code = vouchers[0]["code"]
    else:
        print(f"    Error: {r.text[:200]}")
        voucher_code = None
else:
    voucher_code = None

# 9. List vouchers
r = requests.get(f"{BASE}/vouchers/", headers=headers)
test("List vouchers (admin)", r.status_code == 200, f"{len(r.json())} vouchers")

# 10. Redeem voucher
if voucher_code:
    r = requests.post(f"{BASE}/vouchers/redeem", json={
        "code": voucher_code, "phone_number": "0799999999"
    })
    test("Redeem voucher", r.status_code == 200, r.json().get("message",""))

# 11. Subscriptions
r = requests.get(f"{BASE}/subscriptions/my", headers=user_headers)
test("My subscriptions", r.status_code == 200, f"{len(r.json())} subscriptions")

# 12. Admin users
r = requests.get(f"{BASE}/admin/users", headers=headers)
test("Admin users list", r.status_code == 200, f"{len(r.json())} users")

# 13. Payments list
r = requests.get(f"{BASE}/payments/", headers=headers)
test("Payments list (admin)", r.status_code == 200, f"{len(r.json())} payments")

# 14. Settings
r = requests.get(f"{BASE}/admin/settings", headers=headers)
test("System settings", r.status_code == 200, f"{len(r.json())} settings")

# 15. Audit logs
r = requests.get(f"{BASE}/admin/audit-logs", headers=headers)
test("Audit logs", r.status_code == 200)

# 16. SMS logs
r = requests.get(f"{BASE}/admin/sms-logs", headers=headers)
test("SMS logs", r.status_code == 200)

# 17. API docs
r = requests.get("http://localhost:8000/docs")
test("API docs accessible", r.status_code == 200)

print("\n=== Tests Complete ===\n")
