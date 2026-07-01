import os
import asyncio
import json
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from openai import OpenAI

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("Missing OPENROUTER_API_KEY in .env file")

VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH")
if not VAULT_PATH:
    raise ValueError(
        "Missing OBSIDIAN_VAULT_PATH in .env file. "
        "Set it to the absolute path of your Obsidian vault, e.g. "
        "OBSIDIAN_VAULT_PATH=/home/username/Documents/MyVault"
    )

client_llm = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

MODEL = os.getenv("AGENT")                                           #"meta-llama/llama-3.1-8b-instruct"
SYSTEM_PROMPT = (
    "You are a helpful assistant with access to the user's Obsidian vault. "
    "Always read a note before updating it so you don't overwrite existing "
    "content by accident, unless the user clearly asks you to replace it."
)

server_params = StdioServerParameters(
    command="obsidian-mcp",
    args=[],
    env={
        **os.environ,
        "OBSIDIAN_VAULT_PATH": VAULT_PATH,
    },
)


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
    print(f"Starting Obsidian MCP server for vault: {VAULT_PATH}")

    # Keep the stdio subprocess and the MCP session open for the whole
    # chat loop via AsyncExitStack -- same lifetime issue as the Calendar
    # version: returning a session from inside an "async with" that opened
    # it closes the connection the moment the function returns.
    async with AsyncExitStack() as stack:
        read_stream, write_stream = await stack.enter_async_context(
            stdio_client(server_params)
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
                        "X-Title": "Obsidian Agent",
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
                            "X-Title": "Obsidian Agent",
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


if __name__ == "__main__":
    asyncio.run(main_loop())