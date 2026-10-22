// Vercel Serverless Function: /api/config
module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  return res.status(200).json({
    supabase_url: process.env.SUPABASE_URL || "https://pwjtpxctvxnynmsneudv.supabase.co",
    supabase_anon_key: process.env.SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB3anRweGN0dnhueW5tc25ldWR2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA2OTMzMDcsImV4cCI6MjEwNjI2OTMwN30.0DugtAPrOxt6dWLqE62C7_4FhEvaH4KEtrJJxPNzoJ4",
    finnhub_key_configured: true
  });
};
