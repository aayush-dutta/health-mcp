import os
import json
import threading
import asyncio
from datetime import date,timedelta
from requests_oauthlib import OAuth2Session
from mcp.server.fastmcp import FastMCP
from pathlib import Path
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
OURA_API_BASE = "https://api.ouraring.com/v2/usercollection"

OURA_CLIENT_ID = os.environ.get("OURA_CLIENT_ID")
OURA_CLIENT_SECRET = os.environ.get("OURA_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("OURA_REDIRECT_URI", "http://localhost:8080/callback")

SCOPES = ["daily", "heartrate", "workout","personal"]


BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "oura_token.json"
STATE_PATH = BASE_DIR / "oura_state.txt"

# -------------------
# OURA API URL Helpers
# -------------------

def invalid_date(dt: str)-> bool:
    """Validates whether the given string is an ISO8601 date
            Args:
                dt -> str - The date string we are trying to verify
    """
    try:
        date.fromisoformat(dt)
    except:
        return True
    return False

def prep_dates(start_date:str, end_date:str):
    """Performs validation on dates and returns default dates if validation fails
            Args:
                start_date -
                end_date   -
    """
    today = date.today()
    if invalid_date(end_date) or invalid_date(start_date) is None:
        end_date = today
        start_date=end_date-timedelta(days=6)
        end_date=end_date.isoformat()
        start_date=start_date.isoformat()
    return start_date,end_date

def date_url(extn: str ,start_date:str, end_date:str):
    """Gets any Oura API URL that requires a start date and an end date
            Args:
                [TODO: fill in]
       """
    start_date,end_date=prep_dates(start_date,end_date)
    return f"{OURA_API_BASE}/{extn}?start_date={start_date}&end_date={end_date}"

# -------------------
# TOKEN STORAGE
# -------------------

def save_token(token: dict):
    TOKEN_PATH.write_text(json.dumps(token))

def load_token() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    return json.loads(TOKEN_PATH.read_text())

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
async def make_oura_request(url: str) -> dict:
    """ Async wrapper for Oura request"""
    return await asyncio.to_thread(sync_oura_get, url) 


def sync_oura_get(url:str) -> dict:
    """ Helper API call to make authenticated calls to Oura"""
    token = load_token()
    if not token:
        return {"error": "User not authenticated. Run get_oura_login_url first."}

    oauth = get_oura_oauth_session(token=token)

    resp = oauth.get(url, timeout=30)

    if resp.status_code == 401:
        new_token = oauth.refresh_token(
            OURA_TOKEN_URL,
            client_id=OURA_CLIENT_ID,
            client_secret=OURA_CLIENT_SECRET,
        )
        save_token(new_token)
        resp = oauth.get(url, timeout=30)

    if resp.status_code == 429:
        return {"error": "rate_limited", "message": resp.text}

    resp.raise_for_status()
    return resp.json()

# -------------------
# TOOL: Today's date
# -------------------
@mcp.tool()
def get_today_date() -> str:
    """Retrieves today's date... Claude is a bit dumb here."""
    return date.today().isoformat()

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
# TOOL: DAILY READINESS
# -------------------
@mcp.tool()
async def get_oura_daily_readiness(start_date : str|None = None, end_date : str | None = None) -> dict:
    """Fetch Oura Daily Readiness Information. Defaults to the last week's information.

        Args:
            start_date : str - Start date of the query. Must be formatted as YYYY-MM-DD
            end_date   : str - End date of the query. Must be formatted as YYYY-MM-DD
        
        Constraints:
            end_date must be after the start_date
    """

    url = date_url("daily_readiness",start_date,end_date)
    data = await make_oura_request(url)

    if not data or "data" not in data:
        return f"Unable to fetch Oura daily readiness summary: {data}"

    return {
        "readiness" : [
            {
                "date" : day.get("day",None),
                "score": day.get("score",None)
            }
            for day in data["data"]
        ]
    }
# -------------------
# TOOL: DAILY SLEEP
# -------------------
@mcp.tool()
async def get_oura_daily_sleep(start_date : str|None = None, end_date : str | None = None) -> dict:
    """Fetch Oura Daily Sleep Information. Defaults to the last week's information.

        Args:
            start_date : str - Start date of the query. Must be formatted as YYYY-MM-DD
            end_date   : str - End date of the query. Must be formatted as YYYY-MM-DD
        
        Constraints:
            end_date must be after the start_date
    """

    url = date_url("daily_sleep",start_date,end_date)
    data = await make_oura_request(url)

    if not data or "data" not in data:
        return f"Unable to fetch Oura daily sleep summary: {data}"

    return {
        "sleep" : [
            {
                "date" : day.get("day",None),
                "score": day.get("score",None)
            }
            for day in data["data"]
        ]
    }

# -------------------
# TOOL: DAILY ACTIVITY
# -------------------
@mcp.tool()
async def get_oura_daily_activity(start_date : str|None = None, end_date : str | None = None) -> dict:
    """Fetch Oura Daily Activity Information. Defaults to the last week's information.

        Args:
            start_date : str - Start date of the query. Must be formatted as YYYY-MM-DD
            end_date   : str - End date of the query. Must be formatted as YYYY-MM-DD
        
        Constraints:
            end_date must be after the start_date
    """

    url = date_url("daily_activity",start_date,end_date)
    data = await make_oura_request(url)

    if not data or "data" not in data:
        return f"Unable to fetch Oura daily activity summary: {data}"

    return {
        "activity" : [
            {
                "date" : day.get("day",None),
                "score": day.get("score",None)
            }
            for day in data["data"]
        ]
    }

# -------------------
# CALLBACK SERVER
# -------------------
app = FastAPI()

@app.get("/callback")
async def callback(request: Request):
    """Defines callback server API"""
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    try:
        msg = process_oura_callback(code, state)
        return {"status": msg}
    except Exception as e:
        return {"error": str(e)}

def start_callback_server():
    """Spins up callback server"""
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