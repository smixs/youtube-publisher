#!/usr/bin/env python3
"""
Google OAuth setup — run once to authorize Drive + YouTube access.

Usage:
  python3 scripts/setup_oauth.py [--client config/google-oauth-client.json]

Opens a browser for Google login. After authorization, saves tokens to config/google-oauth-tokens.json.
"""

import http.server
import json
import os
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

REDIRECT_PORT = 8914
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"


def main():
    client_path = CONFIG_DIR / "google-oauth-client.json"

    # Allow override via --client flag
    if "--client" in sys.argv:
        idx = sys.argv.index("--client")
        if idx + 1 < len(sys.argv):
            client_path = Path(sys.argv[idx + 1])

    if not client_path.exists():
        print(f"❌ Client credentials not found: {client_path}")
        print()
        print("To set up:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create/select a project")
        print("3. Enable Google Drive API and YouTube Data API v3")
        print("4. Create OAuth 2.0 credentials (Desktop app)")
        print("5. Download the JSON and save as:")
        print(f"   {CONFIG_DIR / 'google-oauth-client.json'}")
        sys.exit(1)

    with open(client_path) as f:
        creds = json.load(f)

    # Handle both "installed" and "web" credential types
    client = creds.get("installed") or creds.get("web")
    if not client:
        print("❌ Invalid client credentials file (expected 'installed' or 'web' key)")
        sys.exit(1)

    client_id = client["client_id"]
    client_secret = client["client_secret"]

    # Build authorization URL
    auth_params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{auth_params}"

    print(f"🔑 Opening browser for Google authorization...")
    print(f"   If browser doesn't open, visit:")
    print(f"   {auth_url}")
    print()

    # Capture the authorization code via local HTTP server
    auth_code = None

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            if "code" in params:
                auth_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>&#10004; Authorization successful!</h1>"
                                b"<p>You can close this tab.</p></body></html>")
            elif "error" in params:
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                error = params.get("error", ["unknown"])[0]
                self.wfile.write(f"<html><body><h1>Error: {error}</h1></body></html>".encode())
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, *args):
            pass  # Suppress server logs

    webbrowser.open(auth_url)

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
    print(f"⏳ Waiting for authorization on port {REDIRECT_PORT}...")
    server.handle_request()
    server.server_close()

    if not auth_code:
        print("❌ Authorization failed — no code received")
        sys.exit(1)

    print("✅ Authorization code received. Exchanging for tokens...")

    # Exchange code for tokens
    token_data = urllib.parse.urlencode({
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=token_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        resp = urllib.request.urlopen(req)
        tokens = json.loads(resp.read())
    except Exception as e:
        print(f"❌ Token exchange failed: {e}")
        sys.exit(1)

    # Save tokens
    tokens_path = CONFIG_DIR / "google-oauth-tokens.json"
    with open(tokens_path, "w") as f:
        json.dump(tokens, f, indent=2)

    print(f"✅ Tokens saved to {tokens_path}")
    print()
    print("You're all set! Try:")
    print('  python3 scripts/publish.py "https://drive.google.com/file/d/YOUR_FILE_ID/view"')


if __name__ == "__main__":
    main()
