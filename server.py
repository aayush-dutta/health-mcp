import os
import json
import threading
from typing import Any
import httpx
from requests_oauthlib import OAuth2Session
from mcp.server.fastmcp import FastMCP
from requests.auth import HTTPBasicAuth
import requests
from fastapi import FastAPI, Request
import uvicorn


# -------------------
# MCP SERVER INIT
# -------------------
mcp = FastMCP("health")

# -------------------
# CONSTANTS
# -------------------
OURA_AUTH_URL = "https://cloud.ouraring.com/oauth/authorize"
OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"

OURA_CLIENT_ID = os.environ.get("OURA_CLIENT_ID")
OURA_CLIENT_SECRET = os.environ.get("OURA_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("OURA_REDIRECT_URI", "http://localhost:8080/callback")

SCOPES = ["daily", "heartrate", "workout","personal"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "oura_token.json")
STATE_PATH = os.path.join(BASE_DIR, "oura_state.txt")

# -------------------
# TOKEN STORAGE
# -------------------

def save_token(token: dict):
    with open(TOKEN_PATH, "w") as f:
        json.dump(token, f)

def load_token() -> dict | None:
    if not os.path.exists(TOKEN_PATH):
        return None
    with open(TOKEN_PATH, "r") as f:
        return json.load(f)

# -------------------
# OAUTH SESSION
# -------------------
def get_oura_oauth_session(token=None, auto_refresh=True):
    extra = {"client_id": OURA_CLIENT_ID, "client_secret": OURA_CLIENT_SECRET}

    return OAuth2Session(
        client_id=OURA_CLIENT_ID,
        token=token,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        auto_refresh_url=OURA_TOKEN_URL if auto_refresh else None,
        auto_refresh_kwargs=extra if auto_refresh else None,
        token_updater=save_token if auto_refresh else None,
    )

def process_oura_callback(code: str, state: str):
    saved_state = open(STATE_PATH).read().strip()
    if state != saved_state:
        raise Exception("Invalid OAuth state")

    # Build POST body using Oura-required format
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": OURA_CLIENT_ID,
        "client_secret": OURA_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(OURA_TOKEN_URL, data=data,timeout=10)

    token = response.json()

    if "access_token" not in token:
        raise Exception(f"Token exchange failed: {token}")

    save_token(token)
    return "Oura authentication successful!"

# -------------------
# OURA REQUEST HELPER
# -------------------
async def make_oura_request(url: str) -> dict[str, Any] | None:
    token = load_token()
    if not token:
        return {"error": "User not authenticated. Run get_oura_login_url first."}

    oauth = get_oura_oauth_session(token=token)

    signed_headers = {
        "Authorization": f"Bearer {oauth.token['access_token']}"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=signed_headers, timeout=30)

            # DEBUG (stderr only)
            import sys
            print("Oura API Response:", response.status_code, response.text, file=sys.stderr)


            # If unauthorized → refresh token automatically
            if response.status_code == 401:
                token = oauth.refresh_token(
                    OURA_TOKEN_URL,
                    client_id=OURA_CLIENT_ID,
                    client_secret=OURA_CLIENT_SECRET,
                )
                save_token(token)
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token['access_token']}"}
                )

            response.raise_for_status()
            try:
                return response.json()
            except Exception:
                return {"error": "Invalid JSON from Oura", "raw": response.text}

        except Exception as e:
            return {"error": str(e)}

# -------------------
# TOOL: LOGIN URL
# -------------------
@mcp.tool()
def get_oura_login_url() -> str:
    """Generate the OAuth login URL."""
    oauth = get_oura_oauth_session()
    authorization_url, state = oauth.authorization_url(OURA_AUTH_URL)

    with open(STATE_PATH, "w") as f:
        f.write(state)

    return authorization_url

# -------------------
# TOOL: DAILY READINES
# -------------------
@mcp.tool()
async def get_oura_daily_readiness() -> str:
    """Fetch Oura Daily Readiness Score."""

    url = "https://api.ouraring.com/v2/usercollection/daily_readiness?start_date=2025-12-01&end_date=2025-12-06"
    data = await make_oura_request(url)

    if not data or "data" not in data:
        return f"Unable to fetch Oura daily summary: {data}"

    summaries = []
    for day in data["data"]:
        summaries.append(
            f"Date: {day.get('day')}\n"
            f"Readiness Score: {day.get('score')}\n"
        )

    return "\n\n---\n\n".join(summaries)

app = FastAPI()

@app.get("/callback")
async def callback(request: Request):

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    try:
        msg = process_oura_callback(code, state)
        return {"status": msg}
    except Exception as e:
        return {"error": str(e)}

def start_callback_server():
    uvicorn.run(app, 
                host="127.0.0.1", 
                port=8080, 
                log_level="warning", 
                access_log=False)

# -------------------
# RUN EVERYTHING
# -------------------
def main():
    # Start callback HTTP server in background thread
    threading.Thread(target=start_callback_server, daemon=True).start()

    # Run MCP server (foreground)
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()