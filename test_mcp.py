"""Smoke test for the MCP server: connects over stdio, lists the exposed
tools and calls two of them.

Run from the project root:  python test_mcp.py
"""

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,                 # this venv's python
        args=["-m", "src.app.mcp_server"],
        cwd=".",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            print(f"\n{len(tools)} tools exposed over MCP:")
            for t in tools:
                print(f"  - {t.name}: {(t.description or '').splitlines()[0][:70]}")

            print("\ncalling policy_search('devolucion por retracto')...")
            r = await session.call_tool("policy_search",
                                        {"query": "devolucion por retracto"})
            print(r.content[0].text[:300].replace("\n", " "))

            print("\ncalling orders_by_status('in_transit', limit=3)...")
            r = await session.call_tool("orders_by_status",
                                        {"status": "in_transit", "limit": 3})
            print(r.content[0].text[:300])

            print("\nMCP server OK")


if __name__ == "__main__":
    asyncio.run(main())
