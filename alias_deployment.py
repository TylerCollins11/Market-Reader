import os
import urllib.request
import json
import ssl

TOKEN = os.environ.get("VERCEL_TOKEN")
if not TOKEN:
    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".vercel_token")
    if os.path.exists(token_path):
        with open(token_path, "r", encoding="utf-8") as tf:
            TOKEN = tf.read().strip()

TEAM_ID = os.environ.get("VERCEL_TEAM_ID", "team_xem540mYLfHDTPLMWyNKvnFv")
DEPLOYMENT_ID = "dpl_58JEQmnyQJHadyc1bgraTqWED2vr"

url = f"https://api.vercel.com/v2/deployments/{DEPLOYMENT_ID}/aliases?teamId={TEAM_ID}"
payload = json.dumps({"alias": "market-reader-pro.vercel.app"}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    method="POST"
)

context = ssl._create_unverified_context()
try:
    with urllib.request.urlopen(req, context=context) as response:
        res = json.loads(response.read().decode("utf-8"))
        print("Alias assigned successfully:", res)
except Exception as e:
    print("Alias result / error:", e)
