#!/usr/bin/env python3
"""
Simple Notebook MCP Client with Aggregated Scope Handling.

This client demonstrates:
1. Connecting to the notebook server with OAuth
2. Calling list_tools() to discover available tools and their scope requirements
3. Aggregating scope requirements for 'list_notes' and 'add_note' tools
4. Requesting a token with all aggregated scopes upfront
5. Calling both tools using the same token
"""

import asyncio
import json
import os
import threading
import time
import webbrowser
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken


class InMemoryTokenStorage(TokenStorage):
    """Simple in-memory token storage implementation."""

    def __init__(self):
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info


class CallbackHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler to capture OAuth callback."""

    def __init__(self, request, client_address, server, callback_data):
        """Initialize with callback data storage."""
        self.callback_data = callback_data
        super().__init__(request, client_address, server)

    def do_GET(self):
        """Handle GET request from OAuth redirect."""
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        if "code" in query_params:
            self.callback_data["authorization_code"] = query_params["code"][0]
            self.callback_data["state"] = query_params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
            <html>
            <body>
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                <script>setTimeout(() => window.close(), 2000);</script>
            </body>
            </html>
            """)
        elif "error" in query_params:
            self.callback_data["error"] = query_params["error"][0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"""
            <html>
            <body>
                <h1>Authorization Failed</h1>
                <p>Error: {query_params["error"][0]}</p>
                <p>You can close this window and return to the terminal.</p>
            </body>
            </html>
            """.encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


class CallbackServer:
    """Simple server to handle OAuth callbacks."""

    def __init__(self, port: int = 3031):
        self.port = port
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.callback_data: dict[str, Any] = {"authorization_code": None, "state": None, "error": None}

    def _create_handler_with_data(self):
        """Create a handler class with access to callback data."""
        callback_data = self.callback_data

        class DataCallbackHandler(CallbackHandler):
            def __init__(self, request, client_address, server):
                super().__init__(request, client_address, server, callback_data)

        return DataCallbackHandler

    def start(self):
        """Start the callback server in a background thread."""
        handler_class = self._create_handler_with_data()
        self.server = HTTPServer(("localhost", self.port), handler_class)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the callback server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1)

    def wait_for_callback(self, timeout: int = 300) -> str:
        """Wait for OAuth callback with timeout."""
        # Clear previous callback data before waiting for a new callback
        self.callback_data["authorization_code"] = None
        self.callback_data["state"] = None
        self.callback_data["error"] = None

        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.callback_data["authorization_code"]:
                return self.callback_data["authorization_code"]
            elif self.callback_data["error"]:
                raise Exception(f"OAuth error: {self.callback_data['error']}")
            time.sleep(0.1)
        raise Exception("Timeout waiting for OAuth callback")

    def get_state(self) -> str | None:
        """Get the received state parameter."""
        return self.callback_data.get("state")


async def main():
    """Main entry point - demonstrates aggregated scope handling."""
    # Default server URL - can be overridden with environment variable
    server_port = os.getenv("MCP_SERVER_PORT", "8001")
    server_url = f"http://localhost:{server_port}/mcp"

    print("📓 Simple Notebook MCP Client (Aggregated Scopes)")
    print(f"Connecting to: {server_url}")
    print()

    try:
        callback_server = CallbackServer(port=3031)
        callback_server.start()

        async def callback_handler() -> tuple[str, str | None]:
            """Wait for OAuth callback and return auth code and state."""
            print("⏳ Waiting for authorization callback...")
            auth_code = callback_server.wait_for_callback(timeout=300)
            return auth_code, callback_server.get_state()

        client_metadata_dict = {
            "client_name": "Simple Notebook Client (Aggregated)",
            "redirect_uris": ["http://localhost:3031/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        }

        async def _default_redirect_handler(authorization_url: str) -> None:
            """Default redirect handler that opens the URL in a browser."""
            print(f"🌐 Opening browser for authorization: {authorization_url}")
            webbrowser.open(authorization_url)

        # Create OAuth authentication handler
        oauth_auth = OAuthClientProvider(
            server_url=server_url.replace("/mcp", ""),
            client_metadata=OAuthClientMetadata.model_validate(client_metadata_dict),
            storage=InMemoryTokenStorage(),
            redirect_handler=_default_redirect_handler,
            callback_handler=callback_handler,
        )

        print("📡 Opening StreamableHTTP transport connection with auth...")
        async with streamablehttp_client(
            url=server_url,
            auth=oauth_auth,
            timeout=timedelta(seconds=60),
        ) as (read_stream, write_stream, get_session_id):
            print("🤝 Initializing MCP session...")
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("✨ Session initialization complete!")
                print()

                # Step 1: List available tools and extract scope requirements
                print("🔧 Step 1: Listing available tools and extracting scope requirements...")
                try:
                    tools_result = await session.list_tools()
                    print("✅ list_tools succeeded!")
                    print()

                    # Display tools and extract scopes for list_notes and add_note
                    target_tools = {"list_notes", "add_note"}
                    aggregated_scopes: set[str] = set()

                    if tools_result.tools:
                        print(f"📋 Found {len(tools_result.tools)} tool(s):")
                        for tool in tools_result.tools:
                            scopes = tool.meta.get("required_scopes", []) if tool.meta else []
                            scope_str = ", ".join(scopes) if scopes else "none"
                            print(f"  - {tool.name}")
                            print(f"    Description: {tool.description or 'N/A'}")
                            print(f"    Required scopes: {scope_str}")
                            print()

                            # Collect scopes for target tools
                            if tool.name in target_tools and scopes:
                                aggregated_scopes.update(scopes)
                    else:
                        print("📋 No tools found.")
                        print()
                        return

                    # Step 2: Aggregate scopes and set in OAuth context
                    if aggregated_scopes:
                        aggregated_scopes_list = sorted(list(aggregated_scopes))
                        scope_string = " ".join(aggregated_scopes_list)
                        print(f"🔐 Step 2: Aggregating scopes for target tools: {', '.join(target_tools)}")
                        print(f"   Aggregated scopes: {scope_string}")
                        print()

                        # Explicitly set the requested scope using the framework method
                        # This ensures the OAuth flow requests all needed scopes upfront,
                        # overriding any scope suggested by the server
                        oauth_auth.set_requested_scope(scope_string)
                        print(f"✅ Set OAuth client metadata scope to: {scope_string}")
                        print()
                    else:
                        print("⚠️  No scopes found for target tools (list_notes, add_note)")
                        print()

                except Exception as e:
                    print(f"❌ Failed to call list_tools: {e}")
                    import traceback

                    traceback.print_exc()
                    return

                # Step 3: Call list_notes (will trigger OAuth with aggregated scopes)
                print("📋 Step 3: Calling list_notes tool...")
                try:
                    list_result = await session.call_tool("list_notes", {})
                    print("✅ list_notes succeeded!")
                    print()

                    # Extract notes from the result
                    notes = []
                    if hasattr(list_result, "content"):
                        for content in list_result.content:
                            if content.type == "text":
                                try:
                                    result_data = json.loads(content.text)
                                    notes = result_data.get("notes", [])
                                except json.JSONDecodeError:
                                    print(f"⚠️  Could not parse list_notes result: {content.text}")
                    else:
                        print(f"⚠️  Unexpected result format: {list_result}")
                        return

                    # Display notes
                    if notes:
                        print(f"📝 Found {len(notes)} note(s):")
                        for note in notes:
                            print(f"  - ID: {note.get('id', 'unknown')}")
                            print(f"    Title: {note.get('title', 'N/A')}")
                            print(f"    Created: {note.get('created_at', 'N/A')}")
                            print()
                    else:
                        print("📝 No notes found.")
                        print()

                    # Step 4: Call add_note (should use same token with aggregated scopes)
                    print("✏️  Step 4: Calling add_note tool (requires 'write' scope from aggregated scopes)...")
                    try:
                        add_result = await session.call_tool(
                            "add_note",
                            {
                                "title": "My New Note (Aggregated)",
                                "content": "This note was added using the aggregated scope client!",
                            },
                        )
                        print("✅ add_note succeeded!")
                        print()

                        # Display the new note
                        if hasattr(add_result, "content"):
                            for content in add_result.content:
                                if content.type == "text":
                                    try:
                                        note_data = json.loads(content.text)
                                        print("📄 New note created:")
                                        print(f"  ID: {note_data.get('id', 'unknown')}")
                                        print(f"  Title: {note_data.get('title', 'N/A')}")
                                        print(f"  Content: {note_data.get('content', 'N/A')}")
                                        print(f"  Created: {note_data.get('created_at', 'N/A')}")
                                        print(f"  Updated: {note_data.get('updated_at', 'N/A')}")
                                    except json.JSONDecodeError:
                                        print(f"📄 New note (raw): {content.text}")
                        else:
                            print(f"📄 New note: {add_result}")
                    except Exception as e:
                        print(f"❌ Failed to call add_note: {e}")
                        import traceback

                        traceback.print_exc()

                except Exception as e:
                    print(f"❌ Failed to call list_notes: {e}")
                    import traceback

                    traceback.print_exc()

    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Stop the callback server when done
        if "callback_server" in locals():
            callback_server.stop()


def cli():
    """CLI entry point for uv script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
