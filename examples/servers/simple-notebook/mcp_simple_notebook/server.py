"""
Notebook MCP Resource Server with scope-based OAuth authentication.

This server demonstrates scope-based authorization with:
- 'read' scope: list_notes, read_note tools
- 'write' scope: add_note, edit_note tools
"""

import datetime
import logging
import secrets
from typing import Any, Literal

import click
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.requests import Request
from starlette.responses import Response

from mcp.server.auth.handlers.metadata import ProtectedResourceMetadataHandler
from mcp.server.auth.routes import cors_middleware
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp.server import FastMCP
from mcp.shared.auth import ProtectedResourceMetadata

from .token_verifier import IntrospectionTokenVerifier

logger = logging.getLogger(__name__)


class ResourceServerSettings(BaseSettings):
    """Settings for the Notebook MCP Resource Server."""

    model_config = SettingsConfigDict(env_prefix="MCP_NOTEBOOK_")

    # Server settings
    host: str = "localhost"
    port: int = 8001
    server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8001/mcp")

    # Authorization Server settings
    auth_server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    auth_server_introspection_endpoint: str = "http://localhost:9000/introspect"

    # RFC 8707 resource validation
    oauth_strict: bool = False


# In-memory storage for notes
# Format: {note_id: {"title": str, "content": str, "created_at": datetime, "updated_at": datetime}}
_notes: dict[str, dict[str, Any]] = {}


def create_resource_server(settings: ResourceServerSettings) -> FastMCP:
    """
    Create Notebook MCP Resource Server with scope-based authorization.

    This server:
    1. Provides protected resource metadata (RFC 9728)
    2. Validates tokens via Authorization Server introspection
    3. Serves MCP tools with scope-based authorization
    """
    # Create token verifier for introspection with RFC 8707 resource validation
    token_verifier = IntrospectionTokenVerifier(
        introspection_endpoint=settings.auth_server_introspection_endpoint,
        server_url=str(settings.server_url),
        validate_resource=settings.oauth_strict,  # Only validate when --oauth-strict is set
    )

    # Create FastMCP server as a Resource Server
    app = FastMCP(
        name="Notebook MCP Server",
        instructions="Notebook server with scope-based OAuth authentication (read/write scopes)",
        host=settings.host,
        port=settings.port,
        debug=True,
        # Auth configuration for RS mode
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=settings.auth_server_url,
            required_scopes=None,  # No server-level required scopes (tools define their own)
            resource_server_url=settings.server_url,
        ),
    )

    # Add a custom route to expose protected resource metadata at base path
    # This is a workaround for client discovery that tries /.well-known/oauth-protected-resource
    # instead of /.well-known/oauth-protected-resource/mcp
    # The metadata serves the same content at both paths
    async def _protected_resource_metadata_handler(request: Request) -> Response:
        """Handler for protected resource metadata at base path."""
        metadata = ProtectedResourceMetadata(
            resource=settings.server_url,
            authorization_servers=[settings.auth_server_url],
            scopes_supported=None,  # None means tools define their own scopes
        )
        handler = ProtectedResourceMetadataHandler(metadata)
        return await handler.handle(request)

    @app.custom_route("/.well-known/oauth-protected-resource", methods=["GET", "OPTIONS"])
    async def protected_resource_metadata_fallback(request: Request) -> Response:
        """Fallback endpoint for protected resource metadata discovery."""
        return await _protected_resource_metadata_handler(request)

    @app.tool(required_scopes=["read"])
    async def list_notes() -> dict[str, Any]:
        """
        List all notes.

        Requires 'read' scope.
        Returns a list of all notes with their IDs, titles, and timestamps.
        """
        notes_list = [
            {
                "id": note_id,
                "title": note["title"],
                "created_at": note["created_at"].isoformat(),
                "updated_at": note["updated_at"].isoformat(),
            }
            for note_id, note in _notes.items()
        ]
        return {
            "notes": notes_list,
            "count": len(notes_list),
        }

    @app.tool(required_scopes=["read"])
    async def read_note(note_id: str) -> dict[str, Any]:
        """
        Read a specific note by ID.

        Requires 'read' scope.

        Args:
            note_id: The ID of the note to read.
        """
        if note_id not in _notes:
            return {
                "error": "Note not found",
                "note_id": note_id,
            }

        note = _notes[note_id]
        return {
            "id": note_id,
            "title": note["title"],
            "content": note["content"],
            "created_at": note["created_at"].isoformat(),
            "updated_at": note["updated_at"].isoformat(),
        }

    @app.tool(required_scopes=["write"])
    async def add_note(title: str, content: str) -> dict[str, Any]:
        """
        Add a new note.

        Requires 'write' scope.

        Args:
            title: The title of the note.
            content: The content of the note.
        """
        note_id = f"note_{secrets.token_hex(8)}"
        now = datetime.datetime.now(datetime.timezone.utc)

        _notes[note_id] = {
            "title": title,
            "content": content,
            "created_at": now,
            "updated_at": now,
        }

        return {
            "id": note_id,
            "title": title,
            "content": content,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    @app.tool(required_scopes=["write"])
    async def edit_note(note_id: str, title: str | None = None, content: str | None = None) -> dict[str, Any]:
        """
        Edit an existing note.

        Requires 'write' scope.

        Args:
            note_id: The ID of the note to edit.
            title: Optional new title for the note.
            content: Optional new content for the note.
        """
        if note_id not in _notes:
            return {
                "error": "Note not found",
                "note_id": note_id,
            }

        note = _notes[note_id]
        if title is not None:
            note["title"] = title
        if content is not None:
            note["content"] = content

        note["updated_at"] = datetime.datetime.now(datetime.timezone.utc)

        return {
            "id": note_id,
            "title": note["title"],
            "content": note["content"],
            "created_at": note["created_at"].isoformat(),
            "updated_at": note["updated_at"].isoformat(),
        }

    return app


@click.command()
@click.option("--port", default=8001, help="Port to listen on")
@click.option("--auth-server", default="http://localhost:9000", help="Authorization Server URL")
@click.option(
    "--transport",
    default="streamable-http",
    type=click.Choice(["sse", "streamable-http"]),
    help="Transport protocol to use ('sse' or 'streamable-http')",
)
@click.option(
    "--oauth-strict",
    is_flag=True,
    help="Enable RFC 8707 resource validation",
)
def main(port: int, auth_server: str, transport: Literal["sse", "streamable-http"], oauth_strict: bool) -> int:
    """
    Run the Notebook MCP Resource Server.

    This server:
    - Provides RFC 9728 Protected Resource Metadata
    - Validates tokens via Authorization Server introspection
    - Serves MCP tools requiring 'read' or 'write' scopes

    Must be used with a running Authorization Server.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        # Parse auth server URL
        auth_server_url = AnyHttpUrl(auth_server)

        # Create settings
        host = "localhost"
        server_url = f"http://{host}:{port}/mcp"
        settings = ResourceServerSettings(
            host=host,
            port=port,
            server_url=AnyHttpUrl(server_url),
            auth_server_url=auth_server_url,
            auth_server_introspection_endpoint=f"{auth_server}/introspect",
            oauth_strict=oauth_strict,
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Make sure to provide a valid Authorization Server URL")
        return 1

    try:
        mcp_server = create_resource_server(settings)

        logger.info(f"🚀 Notebook MCP Resource Server running on {settings.server_url}")
        logger.info(f"🔑 Using Authorization Server: {settings.auth_server_url}")
        logger.info(f"📝 Tools: list_notes, read_note (read scope) | add_note, edit_note (write scope)")

        # Run the server - this should block and keep running
        mcp_server.run(transport=transport)
        logger.info("Server stopped")
        return 0
    except Exception:
        logger.exception("Server error")
        return 1


if __name__ == "__main__":
    main()  # type: ignore[call-arg]
