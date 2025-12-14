# Health Data MCP Server
An MCP server that aggregates data across sources to provide health and wellness insights.

## Functionality and Use

Example queries include

**Summarize and trend sleep**
> "Can you summarize my sleep scores for the last month and trend it in a graph"

**Readiness and Tags**
> "Consider my tags for each day in the last month. Which tags seem to negatively impact my readiness scores the most"

**Contributors to Oura Scores**
> "On how many of the days in the last month did I walk more than 10000 steps?"

## Progress
As of 12/25, we support Oura ring data. See tools for more information.

## Setup

### 1. Get Oura Credentials

1. Go to [Oura's Dev Dashboard](https://developer.ouraring.com/applications)
2. Create a new application. Fill in the information in the form.
3. Ensure that the redirect URI is `http://localhost:8080/callback`
4. Note down the application token and secret

### 2. Retrieve Project and Install Dependencies

1. Clone this repository
2. Download UV for Python project management (Mac/Linus vs Windows)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
```shell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
3. Restart your terminal. The rest of the steps in this section are optional
4. Navigate to the project folder
5. Activate the virtual environment

```bash
source .venv/bin/activate
```
6. Install dependencies

```bash
uv sync
```


### 3. Configure Claude Desktop

1. Download [Claude Desktop](https://claude.com/download)
2. Naviagate to `~/Library/Application Support/Claude/claude_desktop_config.json` to access Claude Desktop's config (creating the file if required)
3. Add the following to the config file
```json
{
  "mcpServers": {
    "health_mcp": {
      "command": "/Absolute/Path/To/UV",
      "args": [
        "--directory",
        "/Absolute/Path/To/Cloned/health-mcp",
        "run",
        "server.py"
      ],
      "env": {
        "OURA_CLIENT_ID": "YOUR-CLIENT-ID",
        "OURA_CLIENT_SECRET": "YOUR-CIENT-SECRET",
        "OURA_REDIRECT_URI": "http://localhost:8080/callback"
      }
    }
  }
}
```
4. Restart Claude Desktop

### 4. Give it a shot!

1. Prompt Claude to retrieve Oura related data
2. Upon your first usage of the mcp-server, you will be redirected to authenticate Oura credentials


## Tools Available

- Note: most of these aren't endpoints- they are delegated to by a top-level resource
- `get_daily_x_score`: Retrives the daily x score and contributors. x can be sleep, readiness, or activity
- `get_oura_login_url`: Gets the Oura login URL for authentication
- `get_today_date`: Claude is really bad at dates...


## Notes
- If not given a date range, the tools default to using data from the previous week
- Requires an internet connection





