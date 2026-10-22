// Vercel Serverless Function: /api/chart
const https = require('https');

function fetchUrl(url) {
  return new Promise((resolve, reject) => {
    https.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Cache-Control', 's-maxage=30, stale-while-revalidate=60');

  if (req.method === 'OPTIONS') return res.status(200).end();

  const symbol = (req.query.symbol || 'SPY').toUpperCase().trim();
  const tf = (req.query.timeframe || '1D').toUpperCase().trim();

  const tfMap = {
    '1D': { interval: '5m', range: '1d' },
    '5D': { interval: '15m', range: '5d' },
    '1M': { interval: '1d', range: '1mo' },
    '6M': { interval: '1d', range: '6mo' },
    'YTD': { interval: '1d', range: 'ytd' },
    '1Y': { interval: '1wk', range: '1y' },
    '5Y': { interval: '1mo', range: '5y' },
    'ALL': { interval: '1mo', range: 'max' }
  };

  const { interval, range } = tfMap[tf] || tfMap['1D'];

  const cryptoMap = {
    'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'SOL': 'SOL-USD', 'ADA': 'ADA-USD',
    'DOGE': 'DOGE-USD', 'XRP': 'XRP-USD', 'BNB': 'BNB-USD', 'AVAX': 'AVAX-USD',
    'LINK': 'LINK-USD'
  };
  const yahooSym = cryptoMap[symbol] || symbol;

  try {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSym)}?interval=${interval}&range=${range}`;
    const data = await fetchUrl(url);
    const result = data?.chart?.result?.[0];

    if (result) {
      const meta = result.meta || {};
      const timestamps = result.timestamp || [];
      const quote = result.indicators?.quote?.[0] || {};
      const opens = quote.open || [];
      const highs = quote.high || [];
      const lows = quote.low || [];
      const closes = quote.close || [];
      const volumes = quote.volume || [];

      const candles = [];
      for (let i = 0; i < timestamps.length; i++) {
        const c = closes[i];
        if (c !== null && c !== undefined && !isNaN(c)) {
          const o = (opens[i] !== null && opens[i] !== undefined) ? opens[i] : c;
          const h = (highs[i] !== null && highs[i] !== undefined) ? highs[i] : Math.max(o, c);
          const l = (lows[i] !== null && lows[i] !== undefined) ? lows[i] : Math.min(o, c);
          const v = volumes[i] || 0;

          candles.push({
            time: timestamps[i],
            open: Number(Number(o).toFixed(2)),
            high: Number(Number(h).toFixed(2)),
            low: Number(Number(l).toFixed(2)),
            close: Number(Number(c).toFixed(2)),
            volume: Math.round(Number(v))
          });
        }
      }

      return res.status(200).json({
        symbol,
        timeframe: tf,
        candles,
        meta: {
          currency: meta.currency || 'USD',
          currentPrice: meta.regularMarketPrice,
          prevClose: meta.chartPreviousClose,
          fiftyTwoWeekHigh: meta.fiftyTwoWeekHigh,
          fiftyTwoWeekLow: meta.fiftyTwoWeekLow
        }
      });
    }
  } catch (err) {}

  return res.status(200).json({
    symbol,
    timeframe: tf,
    candles: [],
    meta: {}
  });
};
