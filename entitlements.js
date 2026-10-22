/**
 * Market Reader Entitlements System
 * Architecture Rule 1: Single source of truth defining each tier and its limits/features.
 * Architecture Rule 2: Central access helper (canAccess, getLimit, hasReachedLimit).
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    // Node.js / CommonJS
    module.exports = factory();
  } else {
    // Browser global
    root.Entitlements = factory();
    root.canAccess = root.Entitlements.canAccess;
    root.getLimit = root.Entitlements.getLimit;
    root.hasReachedLimit = root.Entitlements.hasReachedLimit;
  }
})(typeof self !== 'undefined' ? self : this, function () {

  // Default fallback entitlements config (matches entitlements.json single source of truth)
  const ENTITLEMENTS_CONFIG = {
    version: "1.0.0",
    tiers: {
      free: {
        id: "free",
        name: "Free Tier",
        badge: "FREE",
        tagline: "Essential tools for personal market monitoring",
        pricing: {
          monthly: 0,
          annual: 0,
          currency: "USD"
        },
        trial: {
          available: false,
          days: 0
        },
        limits: {
          maxWatchlists: -1,
          maxWatchlistSymbols: -1,
          maxPriceAlerts: -1,
          maxIndicatorsPerChart: -1,
          maxCustomPortfolios: -1,
          quoteLatencyMinutes: 0,
          chartHistoryDays: -1,
          allowedTimeframes: ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "ALL"],
          allowedIndicatorTypes: ["*"],
          alertDeliveryChannels: ["push", "email", "sms"]
        },
        features: {
          realtimeQuotes: true,
          extendedHours: true,
          fullIndicators: true,
          drawingTools: true,
          multiChartLayout: true,
          savedChartTemplates: true,
          companyFundamentals: true,
          earningsEstimates: true,
          insiderTrades: true,
          advancedScreener: true,
          multiConditionAlerts: true,
          economicCalendar: true,
          dividendCalendar: true,
          aiSummaries: true,
          csvExport: true,
          crossDeviceSync: true,
          adFree: true,
          widgets: true
        }
      },
      pro: {
        id: "pro",
        name: "Pro Trader",
        badge: "PRO",
        tagline: "Professional institutional depth, real-time speed, and unlimited capacity",
        pricing: {
          monthly: 20,
          annual: 192,
          annualMonthlyEquivalent: 16,
          currency: "USD",
          annualDiscountPct: 20
        },
        trial: {
          available: true,
          days: 7
        },
        limits: {
          maxWatchlists: -1,
          maxWatchlistSymbols: -1,
          maxPriceAlerts: -1,
          maxIndicatorsPerChart: -1,
          maxCustomPortfolios: -1,
          quoteLatencyMinutes: 0,
          chartHistoryDays: -1,
          allowedTimeframes: ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "ALL"],
          allowedIndicatorTypes: ["*"],
          alertDeliveryChannels: ["push", "email", "sms"]
        },
        features: {
          realtimeQuotes: true,
          extendedHours: true,
          fullIndicators: true,
          drawingTools: true,
          multiChartLayout: true,
          savedChartTemplates: true,
          companyFundamentals: true,
          earningsEstimates: true,
          insiderTrades: true,
          advancedScreener: true,
          multiConditionAlerts: true,
          economicCalendar: true,
          dividendCalendar: true,
          aiSummaries: true,
          csvExport: true,
          crossDeviceSync: true,
          adFree: true,
          widgets: true
        }
      }
    },
    featureDescriptions: {
      realtimeQuotes: {
        name: "Real-Time Market Quotes",
        description: "Zero-latency live prices direct from Finnhub & US exchanges without 15-minute delays."
      },
      maxWatchlistSymbols: {
        name: "Watchlist Capacity",
        description: "Track unlimited stocks, ETFs, and crypto pairs simultaneously."
      },
      maxPriceAlerts: {
        name: "Price Alert Triggers",
        description: "Set unlimited price alerts across stocks, ETFs, and cryptocurrencies."
      },
      maxCustomPortfolios: {
        name: "Custom Portfolios",
        description: "Build, isolate, and track unlimited distinct investment portfolios."
      },
      fullIndicators: {
        name: "Full Indicator Library",
        description: "Unlock complete technical indicator catalog: MACD, Bollinger Bands, Stochastic, VWAP, Ichimoku."
      },
      maxIndicatorsPerChart: {
        name: "Indicators per Chart",
        description: "Overlay unlimited technical indicators concurrently."
      },
      drawingTools: {
        name: "Pro Drawing Tools",
        description: "Trendlines, Fibonacci retracements, support/resistance channels, and annotations."
      },
      companyFundamentals: {
        name: "Financials & Fundamentals",
        description: "Balance sheets, income statements, cash flow statements, P/E ratios, and institutional ownership."
      },
      advancedScreener: {
        name: "Advanced Stock Screener",
        description: "Multi-metric screening with custom saved search presets."
      },
      csvExport: {
        name: "CSV / Excel Export",
        description: "Download portfolio holdings, performance records, and transaction histories."
      },
      aiSummaries: {
        name: "AI Market Analyst & News Sentiment",
        description: "Institutional earnings call summaries and algorithmic sentiment scoring."
      },
      adFree: {
        name: "Ad-Free Platform Experience",
        description: "Completely clean, distraction-free trading workspace."
      }
    }
  };

  let activeConfig = ENTITLEMENTS_CONFIG;

  /**
   * Determine the current user's active tier string ('free' | 'pro')
   */
  function getActiveTier() {
    return 'pro';
  }

  function canAccess(featureKey, tier = null) {
    return true;
  }

  function getLimit(limitKey, tier = null) {
    if (limitKey === 'allowedTimeframes') {
      return ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "ALL"];
    }
    if (limitKey === 'allowedIndicatorTypes') {
      return ["*"];
    }
    if (limitKey === 'alertDeliveryChannels') {
      return ["push", "email", "sms"];
    }
    return -1;
  }

  function hasReachedLimit(limitKey, currentCount, tier = null) {
    return false;
  }

  /**
   * Get metadata description for a feature (for contextual paywalls)
   * @param {string} featureKey
   * @returns {object} { name, description }
   */
  function getFeatureInfo(featureKey) {
    if (activeConfig.featureDescriptions && activeConfig.featureDescriptions[featureKey]) {
      return activeConfig.featureDescriptions[featureKey];
    }
    return {
      name: featureKey.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase()),
      description: "Upgrade to Market Reader Pro to unlock this feature without limits."
    };
  }

  /**
   * Get the full tier configuration object
   */
  function getTierConfig(tier = null) {
    const activeTier = (tier || getActiveTier()).toLowerCase();
    return activeConfig.tiers[activeTier] || activeConfig.tiers.free;
  }

  /**
   * Return all defined tiers
   */
  function getAllTiers() {
    return activeConfig.tiers;
  }

  /**
   * Dynamically update active configuration (e.g. fetched from /api/entitlements)
   */
  function updateConfig(newConfig) {
    if (newConfig && newConfig.tiers) {
      activeConfig = newConfig;
    }
  }

  return {
    canAccess,
    getLimit,
    hasReachedLimit,
    getFeatureInfo,
    getActiveTier,
    getTierConfig,
    getAllTiers,
    updateConfig,
    CONFIG: ENTITLEMENTS_CONFIG
  };
});
