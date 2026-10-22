#!/usr/bin/env python3
"""
Market Reader - Local Development Server with Finnhub Live API Integration
Zero external dependencies required (uses standard library http.server).
"""

import http.server
import socketserver
import socket
import os
import json
import csv
import io
import urllib.parse
from datetime import datetime

# Import Finnhub & Subscription Services
import finnhub_service
import subscription_service

PORT = 5050
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class DualStackServer(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6
    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except Exception:
            pass
        return super().server_bind()

class MarketReaderHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def enforce_guard(self, feature_key=None, limit_key=None, current_count=0, query=None):
        eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers, query)
        if feature_key:
            allowed, err = subscription_service.validate_feature_access(eff_tier, feature_key)
            if not allowed:
                self.send_json_response(err, status=403)
                return False, eff_tier, sub
        if limit_key:
            allowed, err = subscription_service.validate_limit_access(eff_tier, limit_key, current_count)
            if not allowed:
                self.send_json_response(err, status=403)
                return False, eff_tier, sub
        return True, eff_tier, sub

    def send_csv_response(self, csv_data, filename="export.csv"):
        body = csv_data.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 0. Entitlements Single Source of Truth Endpoint
        if path == "/api/entitlements":
            self.send_json_response(subscription_service.get_entitlements())
            return

        # 0.1. Current User Subscription Details & Effective Tier
        if path == "/api/subscription/me":
            eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers, query)
            t_cfg = subscription_service.get_tier_config(eff_tier)
            self.send_json_response({
                "userId": sub.get("user_id"),
                "email": sub.get("email"),
                "tier": eff_tier,
                "rawTier": sub.get("tier", "free"),
                "subscriptionStatus": sub.get("subscription_status", "active"),
                "currentPeriodEnd": sub.get("current_period_end"),
                "trialEnd": sub.get("trial_end"),
                "cancelAtPeriodEnd": sub.get("cancel_at_period_end", False),
                "limits": t_cfg.get("limits", {}),
                "features": t_cfg.get("features", {})
            })
            return

        # 0.2. Pro-Only Real-Time Quote Endpoint (Guarded)
        if path == "/api/realtime-quote":
            allowed, eff_tier, sub = self.enforce_guard(feature_key="realtimeQuotes", query=query)
            if not allowed:
                return
            symbol = query.get("symbol", ["BTC"])[0].upper()
            try:
                quote = finnhub_service.get_quote(symbol)
                quote["isRealTime"] = True
                quote["latencyMinutes"] = 0
                quote["tier"] = "pro"
                self.send_json_response(quote)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # 0.3. Pro-Only CSV Export Endpoint (Guarded)
        if path == "/api/export":
            allowed, eff_tier, sub = self.enforce_guard(feature_key="csvExport", query=query)
            if not allowed:
                return
            export_type = query.get("type", ["watchlist"])[0].lower()
            symbols_param = query.get("symbols", ["NVDA,AAPL,MSFT,TSLA,SPY"])[0]
            symbols = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]
            try:
                quotes_data = finnhub_service.get_batch_quotes(symbols)
                quotes_list = list(quotes_data.values()) if isinstance(quotes_data, dict) else quotes_data
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["Symbol", "Price", "Change", "ChangePct", "High", "Low", "Open", "PrevClose", "ExportedAt"])
                now_str = datetime.utcnow().isoformat()
                for q in quotes_list:
                    if isinstance(q, dict):
                        writer.writerow([
                            q.get("symbol", ""),
                            q.get("price", 0),
                            q.get("change", 0),
                            f"{q.get('pct', q.get('changePercent', 0))}%",
                            q.get("high", 0),
                            q.get("low", 0),
                            q.get("open", 0),
                            q.get("prev_close", q.get("previousClose", 0)),
                            now_str
                        ])
                self.send_csv_response(output.getvalue(), f"market_reader_{export_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv")
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # 0.4. Price Alerts Fetch Endpoint
        if path == "/api/alerts":
            eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers, query)
            user_id = sub.get("user_id") or "guest"
            alerts = subscription_service.get_user_alerts(user_id)
            max_alerts = subscription_service.get_limit(eff_tier, "maxPriceAlerts")
            self.send_json_response({
                "alerts": alerts,
                "count": len(alerts),
                "maxAlerts": max_alerts,
                "tier": eff_tier,
                "canAddMore": (max_alerts == -1) or (len(alerts) < max_alerts)
            })
            return

        # 1. API Status Endpoint
        if path == "/api/status":
            api_key = finnhub_service.get_api_key()
            self.send_json_response({
                "status": "healthy",
                "finnhub_connected": bool(api_key),
                "api_key_set": bool(api_key),
                "server_time": datetime.utcnow().isoformat()
            })
            return

        # 1.5. Live Market Ticker Band Endpoint (Bloomberg & TradingView Tape)
        if path == "/api/ticker-band":
            try:
                ticker_items = finnhub_service.get_ticker_band_data()
                self.send_json_response({"items": ticker_items, "count": len(ticker_items)})
            except Exception as e:
                self.send_json_response({"error": str(e), "items": []}, status=500)
            return

        # 2. Market Overview Cards Endpoint (S&P 500, NASDAQ, DXY INDEX, DOW JONES)
        if path == "/api/market-overview":
            try:
                overview = finnhub_service.get_market_overview()
                self.send_json_response(overview)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # 3. Market Catalog Endpoint (S&P 500, NYSE, NASDAQ, ETFs, Global, All, Watchlist)
        if path == "/api/catalog":
            category = query.get("category", ["sp500"])[0].lower()
            search = query.get("search", [""])[0]
            symbols_param = query.get("symbols", [""])[0]
            symbols_list = [s.strip().upper() for s in symbols_param.split(",") if s.strip()] if symbols_param else None
            try:
                page = int(query.get("page", ["1"])[0])
            except ValueError:
                page = 1
            try:
                limit = min(int(query.get("limit", ["50"])[0]), 100)
            except ValueError:
                limit = 50
            try:
                catalog_data = finnhub_service.get_catalog(category, search, page, limit, symbols=symbols_list)
                self.send_json_response(catalog_data)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # 4. Top Assets Endpoint with Category Filtering
        if path == "/api/top-assets":
            category = query.get("category", ["all"])[0]
            try:
                top_assets = finnhub_service.get_top_assets(category)
                self.send_json_response(top_assets)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # 4. Universal Symbol Search Endpoint (Google / Yahoo Finance style)
        if path == "/api/search":
            q = query.get("q", [""])[0]
            try:
                results = finnhub_service.search_symbols(q)
                self.send_json_response({"results": results, "count": len(results)})
            except Exception as e:
                self.send_json_response({"error": str(e), "results": []}, status=500)
            return

        # 5. Individual Symbol Quote Endpoint (Delayed 15m for Free, Real-Time for Pro)
        if path == "/api/quote":
            symbol = query.get("symbol", ["BTC"])[0].upper()
            eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers, query)
            latency = subscription_service.get_limit(eff_tier, "quoteLatencyMinutes")
            is_rt = subscription_service.can_access(eff_tier, "realtimeQuotes")
            try:
                quote_data = finnhub_service.get_quote(symbol)
                if isinstance(quote_data, dict):
                    quote_data["isRealTime"] = is_rt
                    quote_data["latencyMinutes"] = latency
                    quote_data["freshnessLabel"] = "Real-Time" if is_rt else "Delayed 15 min"
                    quote_data["tier"] = eff_tier
                self.send_json_response(quote_data)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # 5B. Company Profile, Financial Metrics, Ratios & Performance Assessment Endpoint
        if path == "/api/company-analysis":
            symbol = query.get("symbol", ["NVDA"])[0].upper()
            eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers, query)
            latency = subscription_service.get_limit(eff_tier, "quoteLatencyMinutes")
            is_rt = subscription_service.can_access(eff_tier, "realtimeQuotes")
            try:
                analysis_data = finnhub_service.get_company_analysis(symbol)
                if isinstance(analysis_data, dict):
                    analysis_data["isRealTime"] = is_rt
                    analysis_data["latencyMinutes"] = latency
                    analysis_data["freshnessLabel"] = "Real-Time" if is_rt else "Delayed 15 min"
                    analysis_data["tier"] = eff_tier
                self.send_json_response(analysis_data)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # 6. Batch Quotes Endpoint (Delayed 15m for Free, Real-Time for Pro)
        if path == "/api/batch-quotes":
            raw_syms = query.get("symbols", [""])[0]
            symbols = [s.strip().upper() for s in raw_syms.split(",") if s.strip()]
            eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers, query)
            latency = subscription_service.get_limit(eff_tier, "quoteLatencyMinutes")
            is_rt = subscription_service.can_access(eff_tier, "realtimeQuotes")
            try:
                quotes = finnhub_service.get_batch_quotes(symbols)
                if isinstance(quotes, dict):
                    for sym, q in quotes.items():
                        if isinstance(q, dict):
                            q["isRealTime"] = is_rt
                            q["latencyMinutes"] = latency
                            q["freshnessLabel"] = "Real-Time" if is_rt else "Delayed 15 min"
                            q["tier"] = eff_tier
                self.send_json_response(quotes)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # 5. Config Endpoint
        if path == "/api/config":
            self.send_json_response({
                "supabase_url": os.getenv("SUPABASE_URL", "https://pwjtpxctvxnynmsneudv.supabase.co"),
                "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB3anRweGN0dnhueW5tc25ldWR2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA2OTMzMDcsImV4cCI6MjEwNjI2OTMwN30.0DugtAPrOxt6dWLqE62C7_4FhEvaH4KEtrJJxPNzoJ4"),
                "finnhub_key_configured": bool(finnhub_service.get_api_key()),
            })
            return

        # 7. Market & Stock News Endpoint
        if path == "/api/news":
            category = query.get("category", ["general"])[0]
            symbol = query.get("symbol", [None])[0]
            try:
                news = finnhub_service.get_market_news(category=category, symbol=symbol)
                self.send_json_response({"news": news, "count": len(news)})
            except Exception as e:
                self.send_json_response({"error": str(e), "news": []}, status=500)
            return

        # 7B. Historical Candlestick Chart Endpoint
        if path == "/api/chart":
            symbol = query.get("symbol", ["SPY"])[0].upper()
            timeframe = query.get("timeframe", ["1D"])[0].upper()
            try:
                chart_data = finnhub_service.get_historical_candles(symbol, timeframe)
                if chart_data:
                    self.send_json_response(chart_data)
                else:
                    self.send_json_response({"symbol": symbol, "timeframe": timeframe, "candles": [], "meta": {}})
            except Exception as e:
                self.send_json_response({"error": str(e), "candles": []}, status=500)
            return

        # 8. Ask AI Financial Analyst Endpoint (GET support)
        if path == "/api/ai/ask":
            prompt = query.get("prompt", [""])[0]
            symbol = query.get("symbol", [None])[0]
            try:
                res = finnhub_service.ask_ai_financial_analyst(prompt, active_symbol=symbol)
                self.send_json_response(res)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # Route /pricing to pricing.html
        if path == "/pricing":
            self.path = "/pricing.html"

        # Default: Serve static files (index.html, styles.css, app.js, images)
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/ai/ask":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                req_data = json.loads(post_body) if post_body else {}
                prompt = req_data.get("prompt", "")
                portfolio = req_data.get("portfolio", None)
                active_symbol = req_data.get("activeSymbol", None)

                answer_data = finnhub_service.ask_ai_financial_analyst(prompt, portfolio, active_symbol)
                self.send_json_response(answer_data)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # Subscription update (e.g. upgrade, trial, billing webhook)
        if path == "/api/subscription/update":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                req_data = json.loads(post_body) if post_body else {}
                user_id = req_data.get("userId") or req_data.get("email") or "guest"
                tier = req_data.get("tier", "pro")
                status = req_data.get("status", "active")
                period_days = int(req_data.get("periodDays", 30))
                is_trial = bool(req_data.get("isTrial", False))
                cancel_at_period_end = bool(req_data.get("cancelAtPeriodEnd", False))
                email = req_data.get("email")

                updated = subscription_service.update_user_subscription(
                    user_id, tier=tier, status=status, period_days=period_days,
                    is_trial=is_trial, cancel_at_period_end=cancel_at_period_end, email=email
                )
                eff = subscription_service.get_effective_tier(updated)
                self.send_json_response({"success": True, "subscription": updated, "effectiveTier": eff})
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # Subscription cancel (graceful downgrade)
        if path == "/api/subscription/cancel":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                req_data = json.loads(post_body) if post_body else {}
                user_id = req_data.get("userId") or req_data.get("email") or "guest"
                immediate = bool(req_data.get("immediate", False))
                canceled = subscription_service.cancel_user_subscription(user_id, immediate=immediate)
                eff = subscription_service.get_effective_tier(canceled) if canceled else "free"
                self.send_json_response({"success": True, "subscription": canceled, "effectiveTier": eff})
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # Create Price Alert (Guarded by maxPriceAlerts limit)
        if path == "/api/alerts":
            try:
                eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers)
                user_id = sub.get("user_id") or "guest"
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                alert_data = json.loads(post_body) if post_body else {}

                created, err = subscription_service.add_user_alert(user_id, alert_data, user_tier=eff_tier)
                if err:
                    self.send_json_response(err, status=403)
                    return
                self.send_json_response({"success": True, "alert": created, "tier": eff_tier}, status=201)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # Delete Price Alert via POST
        if path == "/api/alerts/delete":
            try:
                eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers)
                user_id = sub.get("user_id") or "guest"
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                req_data = json.loads(post_body) if post_body else {}
                alert_id = req_data.get("id")
                deleted = subscription_service.delete_user_alert(user_id, alert_id)
                self.send_json_response({"success": deleted})
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # Stripe / Billing Checkout Session
        if path == "/api/billing/create-checkout-session":
            try:
                eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers)
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                req_data = json.loads(post_body) if post_body else {}

                user_id = req_data.get("userId") or sub.get("user_id") or "guest"
                email = req_data.get("email") or sub.get("email")
                plan = req_data.get("plan", "pro")
                interval = req_data.get("interval", "month")
                is_trial = bool(req_data.get("trial", False))
                success_url = req_data.get("successUrl")
                cancel_url = req_data.get("cancelUrl")

                session = subscription_service.create_checkout_session(
                    user_id=user_id,
                    plan=plan,
                    interval=interval,
                    is_trial=is_trial,
                    success_url=success_url,
                    cancel_url=cancel_url,
                    email=email
                )
                self.send_json_response({"success": True, "session": session})
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # Stripe / Billing Customer Portal
        if path == "/api/billing/portal":
            try:
                eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers)
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                req_data = json.loads(post_body) if post_body else {}

                user_id = req_data.get("userId") or sub.get("user_id") or "guest"
                return_url = req_data.get("returnUrl")
                portal = subscription_service.create_billing_portal_session(user_id=user_id, return_url=return_url)
                self.send_json_response({"success": True, "portal": portal})
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        # Stripe Webhook Listener
        if path == "/api/billing/webhook":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_len)
                sig_header = self.headers.get("Stripe-Signature")

                # Verify HMAC signature
                valid, err = subscription_service.verify_stripe_webhook_signature(raw_body, sig_header)
                if not valid:
                    self.send_json_response({"error": f"Webhook verification failed: {err}"}, status=400)
                    return

                event_data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                result = subscription_service.process_stripe_webhook_event(event_data)
                self.send_json_response({"received": True, "result": result})
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        self.send_json_response({"error": "Not Found"}, status=404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/alerts":
            try:
                eff_tier, sub = subscription_service.resolve_user_tier_from_request(self.headers, query)
                user_id = sub.get("user_id") or "guest"
                alert_id = query.get("id", [None])[0]
                deleted = subscription_service.delete_user_alert(user_id, alert_id)
                self.send_json_response({"success": deleted})
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        self.send_json_response({"error": "Not Found"}, status=404)

    def send_json_response(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

def run_server():
    os.chdir(DIRECTORY)
    for p in range(PORT, PORT + 20):
        try:
            httpd = DualStackServer(("::", p), MarketReaderHandler)
            print(f"============================================================")
            print(f"🚀 Market Reader Server live at: http://localhost:{p}")
            print(f"   (Also accessible at: http://127.0.0.1:{p})")
            print(f"🔑 Finnhub API Key Configured: {'YES' if finnhub_service.get_api_key() else 'NO (Awaiting .env entry)'}")
            print(f"📁 Serving directory: {DIRECTORY}")
            print(f"============================================================")
            httpd.serve_forever()
            break
        except Exception:
            try:
                with socketserver.TCPServer(("", p), MarketReaderHandler) as httpd:
                    print(f"============================================================")
                    print(f"🚀 Market Reader Server live at: http://localhost:{p}")
                    print(f"🔑 Finnhub API Key Configured: {'YES' if finnhub_service.get_api_key() else 'NO (Awaiting .env entry)'}")
                    print(f"📁 Serving directory: {DIRECTORY}")
                    print(f"============================================================")
                    httpd.serve_forever()
                    break
            except OSError:
                continue

if __name__ == "__main__":
    run_server()
