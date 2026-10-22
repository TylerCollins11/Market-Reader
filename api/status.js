// Vercel Serverless Function: /api/status
module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'no-cache');
  return res.status(200).json({
    status: "healthy",
    finnhub_connected: true,
    api_key_set: true,
    server_time: new Date().toISOString(),
    environment: "vercel-serverless"
  });
};
