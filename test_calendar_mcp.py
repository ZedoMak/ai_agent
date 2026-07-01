import httpx
import os
import asyncio
import json
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from mcp import ClientSession
from mcp.client.sse import sse_client

load_dotenv()




SCOPES = [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

#local web server OAuth flow
def get_authenticated_session():
    """Obtains credentials via local web server flow and returns an access token."""
    creds = None
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost:8080/"],
                    }
                },
                scopes=SCOPES,
            )
            # opens a browser and runs the local server automatically
            creds = flow.run_local_server(port=8080, open_browser=True)
        
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    
    return creds.token  # returns the access token string


client = httpx.AsyncClient(verify=False, timeout=30.0)

async def test_mcp_connection():
    """Connects to the remote Google Calendar MCP server and lists tools."""
    token = get_authenticated_session()
    
    # The remote MCP server URL
    server_url = "https://calendar.mcp.googleapis.com/mcp/v1"
    
    print("🔌 Connecting to Google Calendar MCP server...")
    
    # Connect via SSE with the bearer token in headers
    async with sse_client(
        url=server_url,
        headers={"Authorization": f"Bearer {token}"},
        client=client 
    ) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the session
            await session.initialize()
            
            # List all available tools
            tools_result = await session.list_tools()
            print("\n📋 Available tools:")
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # try to list calendars as a simple test
            print("\n📅 Fetching your calendars...")

            result = await session.call_tool(
                "list_calendars",
                arguments={}  # no arguments needed for list_calendars
            )
            
            content = result.content[0].text if result.content else "No data"
            try:
                calendars = json.loads(content)
                print(f"Found {len(calendars)} calendars:")
                for cal in calendars[:5]:  # show first 5
                    print(f"  - {cal.get('summary', 'Unnamed')}")
            except json.JSONDecodeError:
                print("Raw response:", content)
            
            # try to list events for today (as a second test)
            print("\n📆 Fetching today's events...")
            from datetime import datetime, timedelta
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            # The list_events tool expects time_min and time_max in ISO format
            result = await session.call_tool(
                "list_events",
                arguments={
                    "time_min": today.isoformat() + "T00:00:00Z",
                    "time_max": tomorrow.isoformat() + "T00:00:00Z",
                    "max_results": 5
                }
            )
            content = result.content[0].text if result.content else "No events"
            try:
                events = json.loads(content)
                if events:
                    print(f"Today's events ({len(events)}):")
                    for evt in events:
                        start = evt.get('start', {}).get('dateTime', evt.get('start', {}).get('date', 'No time'))
                        summary = evt.get('summary', 'No title')
                        print(f"  - {start}: {summary}")
                else:
                    print("No events today!")
            except json.JSONDecodeError:
                print("Raw response:", content)

if __name__ == "__main__":
    asyncio.run(test_mcp_connection())