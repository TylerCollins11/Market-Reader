#!/usr/bin/env python3
"""
Deploy updated Market Reader Pro to Vercel Production
"""
import os
import json
import urllib.request
import urllib.error

TOKEN = os.environ.get("VERCEL_TOKEN")
if not TOKEN:
    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".vercel_token")
    if os.path.exists(token_path):
        with open(token_path, "r", encoding="utf-8") as tf:
            TOKEN = tf.read().strip()

PROJECT_ID = os.environ.get("VERCEL_PROJECT_ID", "prj_slLK0isy6seLHZ8DXMeELgNgOI38")
TEAM_ID = os.environ.get("VERCEL_TEAM_ID", "team_xem540mYLfHDTPLMWyNKvnFv")

FILES_TO_DEPLOY = [
    "index.html",
    "styles.css",
    "app.js",
    "catalog_data.js",
    "static_catalog_data.json",
    "api_data.json",
    "entitlements.js",
    "entitlements.json",
    "pricing.html",
    "vercel.json",
    "api/index.js",
    "api/[...path].js",
    "api/api_data.json",
    "api/static_catalog_data.json",
    "api/entitlements.json"
]

base_dir = os.path.dirname(os.path.abspath(__file__))
payload_files = []

for fname in FILES_TO_DEPLOY:
    fpath = os.path.join(base_dir, fname)
    if not os.path.exists(fpath):
        print(f"Warning: {fname} does not exist!")
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    payload_files.append({
        "file": fname,
        "data": content,
        "encoding": "utf-8"
    })
    print(f"Loaded {fname} ({len(content)} bytes)")

deploy_payload = {
    "name": "market-reader-pro",
    "project": PROJECT_ID,
    "target": "production",
    "files": payload_files
}

url = f"https://api.vercel.com/v13/deployments?teamId={TEAM_ID}"
req = urllib.request.Request(
    url,
    data=json.dumps(deploy_payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    method="POST"
)

import ssl
context = ssl._create_unverified_context()

try:
    print("\nSending deployment to Vercel API...")
    with urllib.request.urlopen(req, context=context) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        deployment_id = res_data.get('id')
        print("\n✅ Deployment created successfully!")
        print(f"Deployment ID: {deployment_id}")
        print(f"URL: https://{res_data.get('url')}")
        print(f"Ready State: {res_data.get('readyState')}")

        if deployment_id:
            import time
            print(f"\nWaiting for deployment {deployment_id} to be READY...")
            is_ready = False
            for attempt in range(30):
                status_req = urllib.request.Request(
                    f"https://api.vercel.com/v13/deployments/{deployment_id}?teamId={TEAM_ID}",
                    headers={"Authorization": f"Bearer {TOKEN}"}
                )
                try:
                    with urllib.request.urlopen(status_req, context=context) as s_resp:
                        s_data = json.loads(s_resp.read().decode("utf-8"))
                        curr_state = s_data.get("readyState")
                        print(f"Attempt {attempt+1}: {curr_state}")
                        if curr_state == "READY":
                            print(f"✅ Deployment is READY on attempt {attempt+1}")
                            is_ready = True
                            break
                        if curr_state in ("ERROR", "CANCELED"):
                            print(f"❌ Deployment failed with state: {curr_state}")
                            print(f"Error: {s_data.get('errorMessage') or s_data.get('error')}")
                            break
                except Exception as ex:
                    print(f"Check attempt {attempt+1}: {ex}")
                time.sleep(3)

            if is_ready:
                print(f"\nAssigning alias 'market-reader-pro.vercel.app' to {deployment_id}...")
                alias_url = f"https://api.vercel.com/v2/deployments/{deployment_id}/aliases?teamId={TEAM_ID}"
                alias_payload = json.dumps({"alias": "market-reader-pro.vercel.app"}).encode("utf-8")
                alias_req = urllib.request.Request(
                    alias_url,
                    data=alias_payload,
                    headers={
                        "Authorization": f"Bearer {TOKEN}",
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(alias_req, context=context) as alias_resp:
                    alias_res = json.loads(alias_resp.read().decode("utf-8"))
                    print(f"✅ Production URL successfully mapped: https://market-reader-pro.vercel.app")

except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8")
    print(f"HTTP Error {e.code}: {err_body}")
except Exception as e:
    print(f"Error: {e}")

