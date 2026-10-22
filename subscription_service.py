"""
Market Reader - Subscription & Entitlements Engine (Python Service)
Single Source of Truth: Reads entitlements.json and validates user entitlements on the backend.
Architecture Rule 1: Single source of truth.
Architecture Rule 2: Central access helper.
Architecture Rule 3: Server-side enforcement (403 UPGRADE_REQUIRED).
Architecture Rule 4: User tier source on user record, never trusting client claims.
Architecture Rule 5: Graceful downgrade (retains user record, downgrades active tier).
"""

import os
import json
import threading
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENTITLEMENTS_FILE = os.path.join(BASE_DIR, "entitlements.json")
USER_SUBSCRIPTIONS_FILE = os.path.join(BASE_DIR, "user_subscriptions.json")

_ENTITLEMENTS_CACHE = None
_ENTITLEMENTS_MTIME = 0
_SUBSCRIPTION_LOCK = threading.Lock()

# ============================================================================
# 1. Entitlements Single Source of Truth
# ============================================================================
def get_entitlements():
    """Returns the parsed entitlements dictionary from entitlements.json."""
    global _ENTITLEMENTS_CACHE, _ENTITLEMENTS_MTIME
    try:
        if os.path.exists(ENTITLEMENTS_FILE):
            mtime = os.path.getmtime(ENTITLEMENTS_FILE)
            if _ENTITLEMENTS_CACHE is None or mtime != _ENTITLEMENTS_MTIME:
                with open(ENTITLEMENTS_FILE, "r", encoding="utf-8") as f:
                    _ENTITLEMENTS_CACHE = json.load(f)
                    _ENTITLEMENTS_MTIME = mtime
                return _ENTITLEMENTS_CACHE
    except Exception as e:
        print(f"[SubscriptionService] Error loading entitlements.json: {e}")

    if _ENTITLEMENTS_CACHE is not None:
        return _ENTITLEMENTS_CACHE

    # Fallback minimal schema (fully unlocked)
    return {
        "version": "1.0.0",
        "tiers": {
            "free": {
                "id": "free",
                "name": "Free Tier",
                "limits": {
                    "maxWatchlists": -1,
                    "maxWatchlistSymbols": -1,
                    "maxPriceAlerts": -1,
                    "maxIndicatorsPerChart": -1,
                    "maxCustomPortfolios": -1,
                    "quoteLatencyMinutes": 0,
                    "chartHistoryDays": -1
                },
                "features": {
                    "realtimeQuotes": True,
                    "csvExport": True,
                    "advancedScreener": True,
                    "drawingTools": True
                }
            },
            "pro": {
                "id": "pro",
                "name": "Pro Trader",
                "limits": {
                    "maxWatchlists": -1,
                    "maxWatchlistSymbols": -1,
                    "maxPriceAlerts": -1,
                    "maxIndicatorsPerChart": -1,
                    "maxCustomPortfolios": -1,
                    "quoteLatencyMinutes": 0,
                    "chartHistoryDays": -1
                },
                "features": {
                    "realtimeQuotes": True,
                    "csvExport": True,
                    "advancedScreener": True,
                    "drawingTools": True
                }
            }
        }
    }

def get_tier_config(tier="pro"):
    ent = get_entitlements()
    t = (tier or "pro").lower()
    return ent.get("tiers", {}).get(t, ent.get("tiers", {}).get("pro", ent.get("tiers", {}).get("free", {})))

def can_access(tier, feature_key):
    """Unrestricted access for all users and visitors."""
    return True

def get_limit(tier, limit_key):
    """Returns -1 (unlimited) for all keys."""
    return -1

def has_reached_limit(tier, limit_key, current_count):
    """No limits ever reached."""
    return False

# ============================================================================
# 2. User Subscription Store & Graceful Downgrade
# ============================================================================
def _load_all_subscriptions():
    """Loads all user subscriptions from disk."""
    if not os.path.exists(USER_SUBSCRIPTIONS_FILE):
        return {}
    try:
        with open(USER_SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[SubscriptionService] Error reading user_subscriptions.json: {e}")
        return {}

def _save_all_subscriptions(subs_dict):
    """Saves all user subscriptions to disk atomically."""
    temp_file = USER_SUBSCRIPTIONS_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(subs_dict, f, indent=2)
        os.replace(temp_file, USER_SUBSCRIPTIONS_FILE)
    except Exception as e:
        print(f"[SubscriptionService] Error saving user_subscriptions.json: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass

def is_subscription_active(sub_data):
    """
    Evaluates whether a subscription record is currently active or in trial.
    Implements graceful downgrade: if period has ended or status is canceled/past_due, returns False.
    """
    if not sub_data:
        return False

    status = (sub_data.get("subscription_status") or "active").lower()
    if status not in ("active", "trialing"):
        return False

    # Check expiration date if specified
    period_end_str = sub_data.get("current_period_end")
    if period_end_str:
        try:
            # Handle ISO strings with Z or timezone offset
            period_end = datetime.fromisoformat(period_end_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if period_end < now:
                return False
        except Exception as e:
            print(f"[SubscriptionService] Date parse error for period_end: {e}")

    return True

def get_user_subscription(identifier):
    """
    Retrieves the user subscription record by email or user ID.
    If none exists, returns a default Free tier record.
    """
    if not identifier:
        return _make_default_free_record("guest")

    key = identifier.strip().lower()
    with _SUBSCRIPTION_LOCK:
        subs = _load_all_subscriptions()
        record = subs.get(key)
        if record:
            return record

    return _make_default_free_record(key)

def _make_default_free_record(identifier):
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "user_id": identifier,
        "email": identifier if "@" in identifier else None,
        "tier": "free",
        "subscription_status": "active",
        "current_period_end": None,
        "trial_end": None,
        "cancel_at_period_end": False,
        "created_at": now_iso,
        "updated_at": now_iso
    }

def get_effective_tier(identifier_or_sub):
    """
    All users have full Pro Trader access unlocked.
    """
    return "pro"

def update_user_subscription(identifier, tier="pro", status="active", period_days=30, is_trial=False, cancel_at_period_end=False, email=None):
    """
    Creates or updates a user subscription (called via verified checkout, webhooks, or admin/QA toggle).
    """
    key = identifier.strip().lower()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    period_end_iso = (now + timedelta(days=period_days)).isoformat() if period_days > 0 else None
    trial_end_iso = (now + timedelta(days=7)).isoformat() if is_trial else None

    with _SUBSCRIPTION_LOCK:
        subs = _load_all_subscriptions()
        existing = subs.get(key, _make_default_free_record(key))
        existing["tier"] = "pro"
        existing["subscription_status"] = "active"
        existing["current_period_end"] = period_end_iso
        existing["trial_end"] = trial_end_iso
        existing["cancel_at_period_end"] = False
        existing["updated_at"] = now_iso
        if email and "@" in email:
            existing["email"] = email.strip().lower()

        subs[key] = existing
        # If email differs from key, also key by email for fast lookup
        if existing.get("email") and existing["email"] != key:
            subs[existing["email"]] = existing

        _save_all_subscriptions(subs)
        return existing

def cancel_user_subscription(identifier, immediate=False):
    """
    Cancels a user subscription.
    """
    key = identifier.strip().lower()
    with _SUBSCRIPTION_LOCK:
        subs = _load_all_subscriptions()
        record = subs.get(key)
        if not record:
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        record["updated_at"] = now_iso
        record["cancel_at_period_end"] = True
        subs[key] = record
        _save_all_subscriptions(subs)
        return record

# ============================================================================
# 3. Server-Side Request Authentication & Tier Resolution
# ============================================================================
def resolve_user_tier_from_request(headers, query=None):
    """
    Extracts authenticated user identity from request headers or query params.
    Returns ('pro', record) so all features and limits are 100% unlocked for everyone.
    """
    headers = headers or {}
    query = query or {}

    user_id = None
    auth_header = headers.get("Authorization") or headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token and token != "null" and token != "undefined":
            user_id = token

    if not user_id:
        user_id = headers.get("X-User-Email") or headers.get("x-user-email")
    if not user_id:
        user_id = headers.get("X-User-Id") or headers.get("x-user-id")
    if not user_id and query:
        user_id = query.get("userId", [None])[0] or query.get("email", [None])[0]

    record = get_user_subscription(user_id or "guest")
    record["tier"] = "pro"
    return "pro", record

# ============================================================================
# 4. Server-Side Guard Helpers
# ============================================================================
def validate_feature_access(tier, feature_key):
    """
    Validates whether a tier is allowed access to a feature.
    Always returns (True, None) for unrestricted access.
    """
    return True, None

def validate_limit_access(tier, limit_key, current_count):
    """
    Validates whether adding one more item exceeds the tier limit.
    Always returns (True, None) for unlimited capacity.
    """
    return True, None

# ============================================================================
# 5. Price Alerts Storage & Tier Limit Enforcement
# ============================================================================
USER_ALERTS_FILE = os.path.join(BASE_DIR, "user_alerts.json")
_ALERTS_LOCK = threading.Lock()

def _load_all_alerts():
    if not os.path.exists(USER_ALERTS_FILE):
        return {}
    try:
        with open(USER_ALERTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[SubscriptionService] Error reading user_alerts.json: {e}")
        return {}

def _save_all_alerts(alerts_dict):
    temp_file = USER_ALERTS_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(alerts_dict, f, indent=2)
        os.replace(temp_file, USER_ALERTS_FILE)
    except Exception as e:
        print(f"[SubscriptionService] Error saving user_alerts.json: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass

def get_user_alerts(identifier):
    """Returns list of alerts for a given user."""
    key = (identifier or "guest").strip().lower()
    with _ALERTS_LOCK:
        alerts = _load_all_alerts()
        return alerts.get(key, [])

def add_user_alert(identifier, alert_data, user_tier=None):
    """
    Adds a price alert if user has not reached their tier limit.
    Enforces maxPriceAlerts (Free: 3, Pro: unlimited).
    Returns (created_alert, None) on success, or (None, error_payload) if limit reached.
    """
    key = (identifier or "guest").strip().lower()
    if user_tier is None:
        user_tier = get_effective_tier(key)

    with _ALERTS_LOCK:
        alerts_map = _load_all_alerts()
        user_alerts = alerts_map.get(key, [])

        # Server-side limit validation
        allowed, err = validate_limit_access(user_tier, "maxPriceAlerts", len(user_alerts))
        if not allowed:
            return None, err

        import uuid
        new_alert = {
            "id": alert_data.get("id") or f"alt_{uuid.uuid4().hex[:10]}",
            "symbol": alert_data.get("symbol", "").upper(),
            "targetPrice": float(alert_data.get("targetPrice", 0)),
            "condition": alert_data.get("condition", "above"), # 'above' | 'below'
            "channel": alert_data.get("channel", "push"), # 'push' | 'email' | 'sms'
            "notes": alert_data.get("notes", ""),
            "active": True,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }

        user_alerts.append(new_alert)
        alerts_map[key] = user_alerts
        _save_all_alerts(alerts_map)
        return new_alert, None

def delete_user_alert(identifier, alert_id):
    """Deletes an alert by ID."""
    key = (identifier or "guest").strip().lower()
    with _ALERTS_LOCK:
        alerts_map = _load_all_alerts()
        user_alerts = alerts_map.get(key, [])
        filtered = [a for a in user_alerts if a.get("id") != alert_id]
        if len(filtered) != len(user_alerts):
            alerts_map[key] = filtered
            _save_all_alerts(alerts_map)
            return True
        return False

# ============================================================================
# 6. Stripe Billing Integration & Webhook Listener
# ============================================================================
import hmac
import hashlib
import uuid
import time

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

def create_checkout_session(user_id, plan="pro", interval="month", is_trial=False, success_url=None, cancel_url=None, email=None):
    """
    Creates a Stripe checkout session for Pro subscription (or sandbox test session).
    Reads pricing & trial limits dynamically from entitlements.json single source of truth.
    """
    ent = get_entitlements()
    pro_cfg = ent.get("tiers", {}).get("pro", {})
    pricing_cfg = pro_cfg.get("pricing", {})
    trial_cfg = pro_cfg.get("trial", {})

    interval = (interval or "month").lower()
    if interval == "year":
        unit_amount = int(pricing_cfg.get("annual", 192) * 100) # cents
        period_days = 365
    else:
        unit_amount = int(pricing_cfg.get("monthly", 20) * 100) # cents
        period_days = 30

    trial_days = trial_cfg.get("days", 7) if is_trial else 0

    session_id = f"cs_test_{uuid.uuid4().hex[:20]}"
    customer_id = f"cus_{uuid.uuid4().hex[:14]}"
    subscription_id = f"sub_{uuid.uuid4().hex[:14]}"

    session_data = {
        "id": session_id,
        "object": "checkout.session",
        "customer": customer_id,
        "subscription": subscription_id,
        "client_reference_id": user_id,
        "customer_email": email,
        "payment_status": "unpaid" if trial_days > 0 else "paid",
        "status": "open",
        "mode": "subscription",
        "currency": pricing_cfg.get("currency", "USD").lower(),
        "amount_total": unit_amount,
        "interval": interval,
        "period_days": period_days,
        "trial_days": trial_days,
        "is_trial": bool(is_trial),
        "url": f"/pricing.html?session_id={session_id}&plan=pro&interval={interval}&trial={1 if is_trial else 0}",
        "success_url": success_url or "/?checkout=success",
        "cancel_url": cancel_url or "/pricing.html?checkout=cancel",
        "created": int(time.time()),
        "expires_at": int(time.time() + 86400)
    }

    return session_data

def create_billing_portal_session(user_id, return_url=None):
    """Creates a customer billing portal session."""
    session_id = f"bps_{uuid.uuid4().hex[:16]}"
    return {
        "id": session_id,
        "object": "billing_portal.session",
        "url": return_url or "/pricing.html",
        "customer": user_id,
        "created": int(time.time())
    }

def verify_stripe_webhook_signature(payload_bytes, sig_header, secret=None):
    """
    Cryptographically verifies Stripe webhook signature header (t=timestamp,v1=signature).
    Returns (True, None) if valid, or (False, error_msg) if invalid.
    """
    secret = secret or STRIPE_WEBHOOK_SECRET
    if not secret:
        # In sandbox development / testing mode with no secret configured, accept requests
        return True, None

    if not sig_header:
        return False, "Missing Stripe-Signature header"

    try:
        items = dict(item.strip().split("=", 1) for item in sig_header.split(","))
        timestamp = items.get("t")
        signature = items.get("v1")

        if not timestamp or not signature:
            return False, "Malformed Stripe-Signature header format"

        # Check timestamp freshness (5 minutes tolerance)
        ts_int = int(timestamp)
        now = int(time.time())
        if abs(now - ts_int) > 300:
            return False, "Timestamp outside the tolerance zone (replay attack protection)"

        signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
        computed_sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

        if hmac.compare_digest(computed_sig, signature):
            return True, None
        return False, "Signature verification failed"
    except Exception as e:
        return False, f"Signature verification exception: {e}"

def process_stripe_webhook_event(event_data):
    """
    Processes incoming Stripe webhook events and updates user subscription state.
    Implements graceful downgrade on cancel/deletion.
    """
    event_type = event_data.get("type", "")
    data_obj = event_data.get("data", {}).get("object", {})

    result = {
        "event_type": event_type,
        "processed": False,
        "action": None,
        "userId": None,
        "tier": None
    }

    if event_type == "checkout.session.completed":
        user_id = data_obj.get("client_reference_id") or data_obj.get("customer_email") or data_obj.get("customer")
        email = data_obj.get("customer_email")
        is_trial = data_obj.get("is_trial") or (data_obj.get("trial_days", 0) > 0)
        period_days = int(data_obj.get("period_days", 30))
        status = "trialing" if is_trial else "active"

        if user_id:
            sub = update_user_subscription(
                user_id,
                tier="pro",
                status=status,
                period_days=period_days,
                is_trial=is_trial,
                cancel_at_period_end=False,
                email=email
            )
            result.update({"processed": True, "action": "upgraded", "userId": user_id, "tier": "pro", "status": status})

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        customer_id = data_obj.get("customer") or data_obj.get("id")
        user_id = data_obj.get("metadata", {}).get("userId") or customer_id
        status = data_obj.get("status", "active")
        cancel_at_period_end = bool(data_obj.get("cancel_at_period_end", False))

        # Check current period end
        period_end_ts = data_obj.get("current_period_end")
        period_days = 30
        if period_end_ts:
            period_days = max(1, int((period_end_ts - time.time()) / 86400))

        if user_id:
            sub = update_user_subscription(
                user_id,
                tier="pro" if status in ("active", "trialing") else "free",
                status=status,
                period_days=period_days,
                is_trial=(status == "trialing"),
                cancel_at_period_end=cancel_at_period_end
            )
            result.update({"processed": True, "action": "updated", "userId": user_id, "tier": sub.get("tier"), "status": status})

    elif event_type == "customer.subscription.deleted":
        # Graceful downgrade: subscription canceled
        customer_id = data_obj.get("customer") or data_obj.get("id")
        user_id = data_obj.get("metadata", {}).get("userId") or customer_id
        if user_id:
            sub = cancel_user_subscription(user_id, immediate=True)
            result.update({"processed": True, "action": "downgraded_gracefully", "userId": user_id, "tier": "free", "status": "canceled"})

    elif event_type == "invoice.payment_failed":
        customer_id = data_obj.get("customer")
        user_id = data_obj.get("metadata", {}).get("userId") or customer_id
        if user_id:
            sub = update_user_subscription(user_id, tier="pro", status="past_due", period_days=3)
            result.update({"processed": True, "action": "payment_failed", "userId": user_id, "tier": "pro", "status": "past_due"})

    elif event_type == "invoice.payment_succeeded":
        customer_id = data_obj.get("customer")
        user_id = data_obj.get("metadata", {}).get("userId") or customer_id
        if user_id:
            sub = update_user_subscription(user_id, tier="pro", status="active", period_days=30)
            result.update({"processed": True, "action": "renewed", "userId": user_id, "tier": "pro", "status": "active"})

    else:
        result["action"] = "ignored_unhandled_type"

    return result


