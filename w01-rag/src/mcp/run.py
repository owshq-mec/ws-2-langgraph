"""Entry point for the MCP stdio server.

Run with `python -m src.mcp.run` or the `dataops-mcp` console script.

All logging is routed to stderr so the JSON-RPC framing on stdout stays clean.
"""
from __future__ import annotations

import asyncio
import logging
import sys


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stderr,
    )
    # Imported here (not at module top) so any import-time logging side effects
    # respect the stderr-only configuration above.
    from src.mcp.server import run_server

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
