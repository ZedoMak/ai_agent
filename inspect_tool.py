import os
import asyncio
import json
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH")

server_params = StdioServerParameters(
    command="obsidian-mcp",
    args=[],
    env={**os.environ, "OBSIDIAN_VAULT_PATH": VAULT_PATH},
)


async def main():
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            print("=== raw list_notes_tool response ===")
            result = await session.call_tool(
                "list_notes_tool", arguments={"recursive": True}
            )
            content = result.content[0].text if result.content else "No data"
            try:
                data = json.loads(content)
                print(json.dumps(data, indent=2)[:3000])
            except json.JSONDecodeError:
                print("Raw (non-JSON):", content)


if __name__ == "__main__":
    asyncio.run(main())