import os
import asyncio
import json
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("Missing OPENROUTER_API_KEY in .env file")

client_llm = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

MODEL = "meta-llama/llama-3.1-8b-instruct"
SYSTEM_PROMPT = "You are a helpful assistant with access to Google Calendar tools."

SCOPES = [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

def get_authenticated_session():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
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
            creds = flow.run_local_server(port=8080, open_browser=True)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds.token


def convert_mcp_tool_to_openai(tool):
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema,
        },
    }


async def execute_tool_call(tool_name, arguments, session):
    try:
        result = await session.call_tool(tool_name, arguments=arguments)
        if result.content and len(result.content) > 0:
            return result.content[0].text
        return "Tool executed but returned no content."
    except Exception as e:
        return f"Error calling tool: {e}"


async def main_loop():
    token = get_authenticated_session()
    server_url = "https://calendarmcp.googleapis.com/mcp/v1"

    print("Connecting to Google Calendar MCP server...")

    # Everything that needs the live MCP connection (listing tools AND
    # calling them during the chat loop) has to happen while these
    # context managers are open. Opening the connection in a separate
    # function and returning the session after the "async with" block
    # exits closes the connection immediately -- the session object
    # would look fine but every call on it would fail or hang.
    # AsyncExitStack lets us keep both context managers open for the
    # whole lifetime of the chat loop and clean them up together at
    # the end, no matter how the loop exits.
    async with AsyncExitStack() as stack:
        read_stream, write_stream, _get_session_id = await stack.enter_async_context(
            streamablehttp_client(
                url=server_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )
        )
        session = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        await session.initialize()
        tools_result = await session.list_tools()
        if not tools_result.tools:
            print("No tools available. Exiting.")
            return

        openai_tools = [convert_mcp_tool_to_openai(t) for t in tools_result.tools]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        print(f"Agent ready (using {MODEL}). Type 'exit' to quit.\n")
        while True:
            user_input = input("You: ")
            if user_input.lower() in ("exit", "quit"):
                break
            messages.append({"role": "user", "content": user_input})

            try:
                response = client_llm.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto",
                    temperature=0.7,
                    extra_headers={
                        "HTTP-Referer": "http://localhost:8080",
                        "X-Title": "Calendar Agent",
                    },
                )
                assistant_message = response.choices[0].message
                messages.append(assistant_message.to_dict())

                if assistant_message.tool_calls:
                    print("Agent is using tools...")
                    for tool_call in assistant_message.tool_calls:
                        tool_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                        result_text = await execute_tool_call(tool_name, arguments, session)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result_text,
                            }
                        )
                    second_response = client_llm.chat.completions.create(
                        model=MODEL,
                        messages=messages,
                        temperature=0.7,
                        extra_headers={
                            "HTTP-Referer": "http://localhost:8080",
                            "X-Title": "Calendar Agent",
                        },
                    )
                    final_reply = second_response.choices[0].message.content
                    messages.append({"role": "assistant", "content": final_reply})
                    print(f"Agent: {final_reply}\n")
                else:
                    reply = assistant_message.content
                    print(f"Agent: {reply}\n")

            except Exception as e:
                print(f"Error: {e}\n")

        # AsyncExitStack closes the ClientSession and the streamable HTTP
        # client automatically when this block exits, in the right order.


if __name__ == "__main__":
    asyncio.run(main_loop())