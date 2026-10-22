"""
Comprehensive End-to-End Test Suite for Market Reader Free & Pro Subscription Tiers
Tests:
1. Entitlements Single Source of Truth
2. Access & Limit Helpers
3. Server-Side Enforcement (403 UPGRADE_REQUIRED)
4. Anti-Tampering & User Tier Resolution
5. Price Alerts Storage & Quota Enforcement (Free 3 vs. Pro Unlimited)
6. Stripe Billing Checkout Session Creation
7. Stripe Webhook Signature Verification & Event Handlers
8. Graceful Downgrade Lifecycle
9. Live Quote Freshness & Latency Metadata
"""

import sys
import os
import json
import io
import time
import hmac
import hashlib
from datetime import datetime, timezone

# Ensure project directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import subscription_service
import server

class MockSocket:
    def __init__(self, request_bytes):
        self._rfile = io.BytesIO(request_bytes)
        self.output_buffer = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "r" in mode:
            return self._rfile
        return self.output_buffer

    def sendall(self, data):
        self.output_buffer.write(data)

    def send(self, data):
        self.output_buffer.write(data)
        return len(data)

    def get_response(self):
        return self.output_buffer.getvalue()

class MockServer:
    pass

def execute_request(method, path, headers=None, body=b""):
    headers = headers or {}
    req_lines = [f"{method} {path} HTTP/1.1", "Host: localhost:5050"]
    for k, v in headers.items():
        req_lines.append(f"{k}: {v}")
    if body and "Content-Length" not in headers:
        req_lines.append(f"Content-Length: {len(body)}")
    req_lines.append("")
    req_lines.append("")
    req_header_bytes = "\r\n".join(req_lines).encode("utf-8")
    full_req = req_header_bytes + body

    sock = MockSocket(full_req)
    try:
        handler = server.MarketReaderHandler(sock, ("127.0.0.1", 54321), MockServer())
    except Exception as e:
        # Some handlers close connection after writing
        pass

    raw_resp = sock.get_response()
    if not raw_resp:
        return 500, {}, b""

    head, _, body_resp = raw_resp.partition(b"\r\n\r\n")
    lines = head.decode("utf-8", errors="replace").split("\r\n")
    status_line = lines[0]
    status_code = int(status_line.split(" ")[1])
    resp_headers = {}
    for line in lines[1:]:
        if ":" in line:
            hk, hv = line.split(":", 1)
            resp_headers[hk.strip().lower()] = hv.strip()

    return status_code, resp_headers, body_resp

def run_all_tests():
    passed = 0
    total = 0

    def assert_test(cond, title):
        nonlocal passed, total
        total += 1
        if cond:
            print(f"  ✓ [PASS] {title}")
            passed += 1
        else:
            print(f"  ✗ [FAIL] {title}")
            raise AssertionError(f"Test failed: {title}")

    print("\n============================================================")
    print("🧪 Running Market Reader Free & Pro Subscription Test Suite")
    print("============================================================\n")

    # TEST GROUP 1: Single Source of Truth & Entitlements
    print("▶ 1. Single Source of Truth & Entitlements Config")
    ent = subscription_service.get_entitlements()
    assert_test("tiers" in ent, "Entitlements contains 'tiers'")
    assert_test("free" in ent["tiers"] and "pro" in ent["tiers"], "Both 'free' and 'pro' tiers are defined")
    assert_test(ent["tiers"]["free"]["limits"]["maxWatchlistSymbols"] == 15, "Free tier maxWatchlistSymbols == 15")
    assert_test(ent["tiers"]["free"]["limits"]["maxCustomPortfolios"] == 1, "Free tier maxCustomPortfolios == 1")
    assert_test(ent["tiers"]["free"]["limits"]["maxPriceAlerts"] == 3, "Free tier maxPriceAlerts == 3")
    assert_test(ent["tiers"]["pro"]["limits"]["maxWatchlistSymbols"] == -1, "Pro tier maxWatchlistSymbols == -1 (unlimited)")
    assert_test(ent["tiers"]["pro"]["pricing"]["monthly"] == 20, "Pro monthly price is $20")
    assert_test(ent["tiers"]["pro"]["pricing"]["annual"] == 192, "Pro annual price is $192")

    # TEST GROUP 2: Central Access & Limit Helpers
    print("\n▶ 2. Central Access & Limit Helpers")
    assert_test(subscription_service.can_access("free", "realtimeQuotes") is False, "Free cannot access realtimeQuotes")
    assert_test(subscription_service.can_access("pro", "realtimeQuotes") is True, "Pro can access realtimeQuotes")
    assert_test(subscription_service.can_access("free", "csvExport") is False, "Free cannot access csvExport")
    assert_test(subscription_service.can_access("pro", "csvExport") is True, "Pro can access csvExport")
    assert_test(subscription_service.get_limit("free", "maxPriceAlerts") == 3, "get_limit(free, maxPriceAlerts) == 3")
    assert_test(subscription_service.get_limit("pro", "maxPriceAlerts") == -1, "get_limit(pro, maxPriceAlerts) == -1")
    assert_test(subscription_service.has_reached_limit("free", "maxPriceAlerts", 2) is False, "Count 2 not reached limit 3")
    assert_test(subscription_service.has_reached_limit("free", "maxPriceAlerts", 3) is True, "Count 3 reached limit 3")
    assert_test(subscription_service.has_reached_limit("pro", "maxPriceAlerts", 50) is False, "Pro never reaches limit")

    # TEST GROUP 3: Server-Side Enforcement (403 UPGRADE_REQUIRED)
    print("\n▶ 3. Server-Side Enforcement (403 UPGRADE_REQUIRED)")
    # Free request to /api/realtime-quote
    code, _, body = execute_request("GET", "/api/realtime-quote?symbol=NVDA", headers={"X-User-Email": "free_user_1@test.com"})
    assert_test(code == 403, "Free user receives HTTP 403 on /api/realtime-quote")
    data = json.loads(body.decode("utf-8"))
    assert_test(data.get("code") == "UPGRADE_REQUIRED", "Response code is UPGRADE_REQUIRED")

    # Free request to /api/export
    code, _, body = execute_request("GET", "/api/export?format=csv", headers={"X-User-Email": "free_user_1@test.com"})
    assert_test(code == 403, "Free user receives HTTP 403 on /api/export")

    # Pro request to /api/realtime-quote (provision Pro user)
    subscription_service.update_user_subscription("pro_user_1@test.com", tier="pro", status="active", period_days=30)
    code, _, body = execute_request("GET", "/api/realtime-quote?symbol=AAPL", headers={"X-User-Email": "pro_user_1@test.com"})
    assert_test(code == 200, "Pro user receives HTTP 200 on /api/realtime-quote")
    data = json.loads(body.decode("utf-8"))
    assert_test(data.get("tier") == "pro" and data.get("isRealTime") is True, "Pro real-time quote metadata valid")

    # Pro request to /api/export
    code, headers, body = execute_request("GET", "/api/export?format=csv", headers={"X-User-Email": "pro_user_1@test.com"})
    assert_test(code == 200, "Pro user receives HTTP 200 on /api/export")
    assert_test("text/csv" in headers.get("content-type", ""), "Pro export returns text/csv")

    # TEST GROUP 4: Anti-Tampering & Client Claim Ignored
    print("\n▶ 4. Anti-Tampering: Client Tier Claim Ignored")
    # A user claims X-User-Tier: pro, but their record in user_subscriptions.json is not pro
    code, _, body = execute_request(
        "GET",
        "/api/realtime-quote?symbol=NVDA",
        headers={"X-User-Email": "tampering_user@test.com", "X-User-Tier": "pro"}
    )
    assert_test(code == 403, "Client spoofed X-User-Tier: pro is rejected by backend verification")

    # TEST GROUP 5: Price Alerts Quota Enforcement (Free max 3, Pro unlimited)
    print("\n▶ 5. Price Alerts Storage & Quota Enforcement")
    test_user = "alert_tester@test.com"
    # Ensure fresh alerts
    subscription_service._save_all_alerts({test_user: []})

    # Alert 1
    alert1, err = subscription_service.add_user_alert(test_user, {"symbol": "AAPL", "targetPrice": 230}, user_tier="free")
    assert_test(alert1 is not None and err is None, "Free user can create 1st alert")
    # Alert 2
    alert2, err = subscription_service.add_user_alert(test_user, {"symbol": "NVDA", "targetPrice": 135}, user_tier="free")
    assert_test(alert2 is not None and err is None, "Free user can create 2nd alert")
    # Alert 3
    alert3, err = subscription_service.add_user_alert(test_user, {"symbol": "TSLA", "targetPrice": 250}, user_tier="free")
    assert_test(alert3 is not None and err is None, "Free user can create 3rd alert")
    # Alert 4 (Should be rejected with UPGRADE_REQUIRED)
    alert4, err = subscription_service.add_user_alert(test_user, {"symbol": "MSFT", "targetPrice": 420}, user_tier="free")
    assert_test(alert4 is None and err is not None, "Free user 4th alert is blocked")
    assert_test(err.get("code") == "UPGRADE_REQUIRED", "Error code is UPGRADE_REQUIRED for 4th alert")
    assert_test(err.get("currentLimit") == 3, "Error payload specifies currentLimit == 3")

    # Pro user adding 4th alert succeeds
    alert4_pro, err = subscription_service.add_user_alert(test_user, {"symbol": "MSFT", "targetPrice": 420}, user_tier="pro")
    assert_test(alert4_pro is not None and err is None, "Pro user can create 4th alert without limitation")

    # Delete alert
    deleted = subscription_service.delete_user_alert(test_user, alert1["id"])
    assert_test(deleted is True, "Alert can be deleted successfully")

    # TEST GROUP 6: Stripe Billing Checkout Session Creation
    print("\n▶ 6. Stripe Billing Checkout Session Creation")
    session = subscription_service.create_checkout_session(
        user_id="stripe_trader@test.com",
        plan="pro",
        interval="month",
        is_trial=True,
        email="stripe_trader@test.com"
    )
    assert_test(session["id"].startswith("cs_test_"), "Generated valid Stripe Checkout Session ID")
    assert_test(session["trial_days"] == 7, "Trial days set to 7 from entitlements")
    assert_test(session["payment_status"] == "unpaid", "Trial payment status is unpaid")
    assert_test(session["interval"] == "month", "Interval is month")

    annual_session = subscription_service.create_checkout_session(
        user_id="annual_trader@test.com",
        plan="pro",
        interval="year",
        is_trial=False
    )
    assert_test(annual_session["amount_total"] == 19200, "Annual amount is 19200 cents ($192.00)")
    assert_test(annual_session["period_days"] == 365, "Annual period days is 365")

    # HTTP Endpoint for Checkout Session
    code, _, body = execute_request(
        "POST",
        "/api/billing/create-checkout-session",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"userId": "api_trader@test.com", "plan": "pro", "interval": "month", "trial": True}).encode("utf-8")
    )
    assert_test(code == 200, "POST /api/billing/create-checkout-session returns HTTP 200")
    resp_data = json.loads(body.decode("utf-8"))
    assert_test(resp_data.get("success") is True and "session" in resp_data, "Returns valid session payload")

    # TEST GROUP 7: Stripe Webhook Signature Verification & Event Handlers
    print("\n▶ 7. Stripe Webhook Signature Verification & Events")
    secret = "whsec_test_secret_12345"
    payload = json.dumps({
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "webhook_customer@test.com",
                "customer_email": "webhook_customer@test.com",
                "is_trial": False,
                "period_days": 30
            }
        }
    }).encode("utf-8")

    ts = str(int(time.time()))
    signed_payload = f"{ts}.".encode("utf-8") + payload
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    sig_header = f"t={ts},v1={sig}"

    # Verify signature
    valid, err = subscription_service.verify_stripe_webhook_signature(payload, sig_header, secret=secret)
    assert_test(valid is True, "Valid Stripe HMAC-SHA256 signature accepted")

    # Invalid signature
    bad_sig_header = f"t={ts},v1=bad_signature_here"
    valid, err = subscription_service.verify_stripe_webhook_signature(payload, bad_sig_header, secret=secret)
    assert_test(valid is False, "Tampered signature rejected")

    # Stale timestamp (replay protection)
    old_ts = str(int(time.time()) - 400)
    old_signed = f"{old_ts}.".encode("utf-8") + payload
    old_sig = hmac.new(secret.encode("utf-8"), old_signed, hashlib.sha256).hexdigest()
    valid, err = subscription_service.verify_stripe_webhook_signature(payload, f"t={old_ts},v1={old_sig}", secret=secret)
    assert_test(valid is False, "Stale timestamp rejected (replay protection)")

    # Process checkout.session.completed event
    event_dict = json.loads(payload.decode("utf-8"))
    res = subscription_service.process_stripe_webhook_event(event_dict)
    assert_test(res["processed"] is True and res["action"] == "upgraded", "Webhook processed checkout.session.completed")
    eff = subscription_service.get_effective_tier("webhook_customer@test.com")
    assert_test(eff == "pro", "User upgraded to 'pro' tier via webhook")

    # TEST GROUP 8: Graceful Downgrade Lifecycle
    print("\n▶ 8. Graceful Downgrade Lifecycle")
    # User cancels subscription
    downgrade_user = "downgrade_user@test.com"
    subscription_service.update_user_subscription(downgrade_user, tier="pro", status="active", period_days=30)
    assert_test(subscription_service.get_effective_tier(downgrade_user) == "pro", "User initially Pro")

    # Cancel with immediate=True
    subscription_service.cancel_user_subscription(downgrade_user, immediate=True)
    eff_tier = subscription_service.get_effective_tier(downgrade_user)
    assert_test(eff_tier == "free", "Lapsed user gracefully transitions to 'free' effective tier")
    sub_record = subscription_service.get_user_subscription(downgrade_user)
    assert_test(sub_record is not None and sub_record.get("subscription_status") == "canceled", "User record retained safely without deletion")

    # TEST GROUP 9: Quote Freshness & Latency Metadata
    print("\n▶ 9. Quote Freshness & Latency Metadata")
    code, _, body = execute_request("GET", "/api/quote?symbol=NVDA", headers={"X-User-Email": "free_user_1@test.com"})
    assert_test(code == 200, "GET /api/quote returns HTTP 200")
    qdata = json.loads(body.decode("utf-8"))
    assert_test(qdata.get("latencyMinutes") == 15, "Free user quote shows latencyMinutes == 15")
    assert_test(qdata.get("isRealTime") is False, "Free user quote shows isRealTime == False")
    assert_test("15 min" in qdata.get("freshnessLabel", ""), "Freshness label indicates delayed quote")

    print("\n============================================================")
    print(f"🎉 ALL {passed}/{total} TESTS PASSED SUCCESSFULLY!")
    print("============================================================\n")
    return True

if __name__ == "__main__":
    success = run_all_tests()
    if not success:
        sys.exit(1)
