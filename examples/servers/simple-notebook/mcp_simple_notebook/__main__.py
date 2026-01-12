"""Main entry point for notebook MCP server."""

import sys

from mcp_simple_notebook.server import main

sys.exit(main())  # type: ignore[call-arg]
