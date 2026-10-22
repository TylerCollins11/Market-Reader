# Market Reader - Pro Portfolio & Asset Platform

A modern, institutional-grade financial market tracking web application matching Bloomberg and Google Finance. Features real-time Finnhub market quotes, 18 technical chart styles, 503 S&P 500 stocks, live wire news updates, multi-portfolio paper trading, Ask AI financial diagnostics, and full company fundamentals with 6 calculated financial performance ratios.

---

## 🌐 Live Production Links
* **Live Production Site**: **[https://market-reader-pro.vercel.app](https://market-reader-pro.vercel.app)**
* **Alternative Deployment URL**: **[https://market-reader-pro-tyler-collins.vercel.app](https://market-reader-pro-tyler-collins.vercel.app)**
* **Local Development Server**: **`http://localhost:5050`**

---

## 📊 Core Financial Analysis Features
1. **Ticker Symbol Search**: Search any global equity (e.g. `NVDA`, `AAPL`, `MSFT`, `TSLA`, `PLTR`, `SPY`) directly from the top search bar or catalog modal.
2. **Latest Stock Price & Price Change**: Real-time quotes, dollar deltas, percentage changes (`▲ +%` / `▼ -%`), session high/low, open, and previous close.
3. **Company Profile & Financial Metrics**: Corporate overview, CEO, headquarters, employee count, website link, market cap, enterprise value, EPS, revenue, margins, beta, dividend yield, and 50-day SMA.
4. **Historical Price Visualizer**: 18 professional chart styles (Candlesticks, Heikin Ashi, OHLC, Area Cloud, Baseline, Mountain, etc.) across 8 timeframes (`1D`, `5D`, `1M`, `6M`, `YTD`, `1Y`, `5Y`, `ALL`) with interactive tooltips and crosshairs.
5. **Six Calculated Financial Performance Indicators**:
   - **Price-to-Earnings (P/E)**: Current Price / Diluted EPS
   - **Price-to-Sales (P/S)**: Market Cap / Annual Revenue
   - **Gross Margin**: (Gross Profit / Total Revenue) × 100%
   - **Net Profit Margin**: (Net Income / Total Revenue) × 100%
   - **Return on Equity (ROE)**: (Net Income / Total Stockholders' Equity) × 100%
   - **52-Week Range Position**: Position of current price within 52-week Low/High channel
6. **Data-Supported Company Assessment**: 4-Pillar institutional executive scorecard evaluating Valuation, Profitability, Financial Health, and Volatility with algorithmic Bullish/Moderate/Cautious synthesis.

---

## 🚀 Quick Start

Run the server with Python 3:

```bash
python3 server.py
```

Open your browser and navigate to:
```
http://localhost:5050
```

To visit the dedicated Pricing & Stripe Sandbox page:
```
http://localhost:5050/pricing.html
```

To run the automated 53-point test suite:
```bash
python3 test_subscription_e2e.py
```

---

## 💎 Free vs. Pro Tier Matrix

| Feature / Limit | Free Explorer Tier | Pro Trader Tier |
|---|---|---|
| **Pricing** | **$0 / month** | **$20 / month** or **$192 / year** ($16/mo · Save 20%) |
| **Free Trial** | — | **7-Day Full Access Free Trial** |
| **Watchlist Symbols** | Up to **15 symbols** (`maxWatchlistSymbols: 15`) | **Unlimited** (`-1`) |
| **Custom Portfolios** | **1 Portfolio** (`maxCustomPortfolios: 1`) | **Unlimited** (`-1`) |
| **Price Alerts** | Up to **3 active alerts** (`maxPriceAlerts: 3`) | **Unlimited** (`-1`) |
| **Alert Delivery Channels**| Push / In-App only | Push, Email, SMS (`["push", "email", "sms"]`) |
| **Indicators per Chart** | Max **3 indicators** (`maxIndicatorsPerChart: 3`) | **Unlimited** (`-1`) |
| **Allowed Indicator Types**| SMA 20, EMA 50, RSI 14 | **Full Suite** + MACD, Bollinger Bands, VWAP (`["*"]`) |
| **Live Quote Latency** | 🕒 **15-minute delayed** (`quoteLatencyMinutes: 15`) | ⚡ **Real-Time Finnhub US Feed** (0 latency) |
| **Chart Historical Depth** | 1D, 5D, 1M, 6M, YTD, 1Y (Max 365 days) | 1D, 5D, 1M, 6M, YTD, 1Y, **5Y, ALL Time** |
| **CSV / Excel Exports** | ✕ Locked (`UPGRADE_REQUIRED`) | ✓ **Instant Holdings & Trade CSV Download** |
| **Ask AI Financial Analyst**| Standard market trends | Priority sentiment scoring & diagnostics |
| **Downgrade Policy** | — | **Graceful Downgrade** (All past data safely preserved) |

---

## 🏛️ The 5 Architecture Rules

### 1. Single Source of Truth (`entitlements.json`)
All tier definitions, limits, feature flags, and pricing reside exclusively in [`entitlements.json`](./entitlements.json). There are zero hardcoded limits scattered in the code.
- To change a limit (e.g. increase Free watchlist symbols from 15 to 25): simply edit `entitlements.json`. The server and client pick up changes automatically without restarting or refactoring code.

### 2. Central Access Helper
All UI and business logic interact with tiers through central entitlement helpers:
- **Client (JS / UMD Module)**: [`entitlements.js`](./entitlements.js)
  - `canAccess(featureKey)`: Returns boolean whether the user has access.
  - `getLimit(limitKey)`: Returns the numeric limit (`-1` means unlimited).
  - `hasReachedLimit(limitKey, currentCount)`: Checks if adding another item reaches the limit.
- **Server (Python)**: [`subscription_service.py`](./subscription_service.py)
  - `can_access(tier, feature_key)`
  - `get_limit(tier, limit_key)`
  - `has_reached_limit(tier, limit_key, current_count)`

### 3. Server-Side Enforcement (403 `UPGRADE_REQUIRED`)
The backend never relies solely on UI hiding. Every gated action verifies entitlements on the server:
- `GET /api/realtime-quote` -> HTTP 403 `UPGRADE_REQUIRED` for Free tier.
- `GET /api/export` -> HTTP 403 `UPGRADE_REQUIRED` for Free tier.
- `POST /api/alerts` -> Enforces `maxPriceAlerts: 3`. Free user attempt to add a 4th alert returns HTTP 403:
  ```json
  {
    "error": "Upgrade required: You have reached the limit of 3 for your plan.",
    "code": "UPGRADE_REQUIRED",
    "limitKey": "maxPriceAlerts",
    "currentLimit": 3,
    "currentCount": 3,
    "tierRequired": "pro",
    "upgradeUrl": "/pricing.html"
  }
  ```

### 4. User Tier Source on User Record
A user's tier is stored securely on their backend user record ([`user_subscriptions.json`](./user_subscriptions.json)). Client-submitted claims (e.g. spoofed `X-User-Tier: pro` headers) are explicitly rejected unless verified against the server-side subscription store.

### 5. Graceful Downgrade Protection
When a Pro subscription lapses or is canceled:
- The user's account transitions to `free`.
- **Existing items are NEVER deleted**: Over-limit watchlists (>15 symbols) and multiple portfolios remain 100% visible, tradeable, and interactive.
- Creating **new** items beyond the Free limit triggers the contextual upgrade modal.

---

## 💳 Stripe Billing & Webhook Integration

### Available Endpoints
- **`POST /api/billing/create-checkout-session`**: Generates a Stripe checkout session with price, interval (`month` or `year`), 7-day trial parameters, and client metadata.
- **`POST /api/billing/portal`**: Generates a customer billing portal session URL.
- **`POST /api/billing/webhook`**: Standard Stripe webhook receiver supporting cryptographic HMAC-SHA256 signature verification (`t=timestamp,v1=signature`) and replay attack prevention.

### Handled Webhook Events
1. **`checkout.session.completed`**: Immediately activates Pro subscription, records trial or paid period, and persists to `user_subscriptions.json`.
2. **`customer.subscription.updated`**: Syncs renewal period, cancellation flags, and status.
3. **`customer.subscription.deleted`**: Executes graceful downgrade, setting `subscription_status: canceled` without deleting user data.
4. **`invoice.payment_failed`**: Flags account as `past_due` with grace period.
5. **`invoice.payment_succeeded`**: Renews active subscription period for another cycle.

---

## 🛠️ QA Debug Tier Simulator (1-Click Verification)

A floating widget is embedded in the bottom-right corner of the application (`🛠️ Tier: FREE / PRO`):
1. Click the floating badge to expand the **QA Tier Simulator**.
2. Tap **"Set PRO ⚡"** to instantly test real-time quotes, full indicators (MACD, BOLL, VWAP), unlimited portfolios, and exports.
3. Tap **"Set FREE"** to immediately test the 15-symbol watchlist capacity badge, 3-alert quota, 3-indicator limit, and contextual paywalls.
4. Changes sync automatically across backend APIs and frontend UI state.

---

## 🧪 Automated Test Suite

Run the full end-to-end test suite:
```bash
python3 test_subscription_e2e.py
```

Verifies all 53 assertions across:
- Entitlements schema & dynamic pricing
- Central access & limit helpers
- Server guards & 403 `UPGRADE_REQUIRED` payloads
- Anti-tampering client spoof rejection
- Price alert quota enforcement (Free 3 vs Pro unlimited)
- Stripe checkout session generation
- Stripe webhook HMAC-SHA256 signature verification & event lifecycle
- Graceful downgrade data preservation
- Real-time vs. 15-minute delayed quote metadata
