import os
import asyncio
import json
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH")
if not VAULT_PATH:
    raise ValueError(
        "Missing OBSIDIAN_VAULT_PATH in .env file. "
        "Set it to the absolute path of your Obsidian vault, e.g. "
        "OBSIDIAN_VAULT_PATH=/home/username/Documents/MyVault"
    )
server_params = StdioServerParameters(
    command="obsidian-mcp",
    args=[],
    env={
        **os.environ,
        "OBSIDIAN_VAULT_PATH": VAULT_PATH,
    },
)


async def test_mcp_connection():
    print(f"Starting Obsidian MCP server for vault: {VAULT_PATH}")

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            print("\nAvailable tools:")
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description.splitlines()[0]}")

            print("\nListing notes in vault root...")
            result = await session.call_tool("list_notes_tool", arguments={"recursive": True})
            content = result.content[0].text if result.content else "No data"
            try:
                data = json.loads(content)
                items = data.get("items", [])
                print(f"Found {data.get('total', len(items))} notes. First 10:")
                for note in items[:10]:
                    print(f"  - {note.get('path')}")
            except json.JSONDecodeError:
                print("Raw response:", content)

            print("\nListing all tags...")
            result = await session.call_tool(
                "list_tags_tool", arguments={"include_counts": True, "sort_by": "count"}
            )
            content = result.content[0].text if result.content else "No data"
            try:
                data = json.loads(content)
                items = data.get("items", [])
                print(f"Found {data.get('total', len(items))} tags. Top 10:")
                for tag in items[:10]:
                    print(f"  - #{tag.get('name')} ({tag.get('count', 0)})")
            except json.JSONDecodeError:
                print("Raw response:", content)


if __name__ == "__main__":
    asyncio.run(test_mcp_connection())
