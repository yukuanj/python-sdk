"""
Tests for tool-level authorization with required_scopes.
"""

import time
from typing import Any

import httpx
import pytest
from pydantic import AnyHttpUrl

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.auth.provider import (
    AccessToken,
    ProviderTokenVerifier,
)
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

from .test_auth_integration import MockOAuthProvider


@pytest.fixture
def mock_oauth_provider() -> MockOAuthProvider:
    """Create a mock OAuth provider for testing."""
    return MockOAuthProvider()


def create_server_with_tool_scopes(mock_oauth_provider: MockOAuthProvider) -> FastMCP:
    """Create a FastMCP server with tools that have required_scopes."""
    # Create token verifier
    token_verifier = ProviderTokenVerifier(mock_oauth_provider)

    # Create auth settings
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl("https://auth.example.com"),
        resource_server_url=AnyHttpUrl("http://127.0.0.1:8000/mcp"),
    )

    # Create FastMCP server
    mcp = FastMCP(
        name="ToolScopeTestServer",
        token_verifier=token_verifier,
        auth=auth_settings,
    )

    # Add a tool without required_scopes (should be accessible without auth)
    @mcp.tool()
    def public_tool(message: str) -> str:
        """A public tool that doesn't require authentication."""
        return f"Public: {message}"

    # Add a tool with required_scopes
    @mcp.tool(required_scopes=["read"])
    def read_tool(message: str) -> str:
        """A tool that requires 'read' scope."""
        return f"Read: {message}"

    # Add a tool with multiple required_scopes
    @mcp.tool(required_scopes=["read", "write"])
    def write_tool(message: str) -> str:
        """A tool that requires both 'read' and 'write' scopes."""
        return f"Write: {message}"

    # Add a tool with different scope
    @mcp.tool(required_scopes=["admin"])
    def admin_tool(message: str) -> str:
        """A tool that requires 'admin' scope."""
        return f"Admin: {message}"

    return mcp


@pytest.fixture
def streamable_http_app(mock_oauth_provider: MockOAuthProvider):
    """Create a FastMCP streamable HTTP app for testing."""
    mcp = create_server_with_tool_scopes(mock_oauth_provider)
    return mcp.streamable_http_app()


@pytest.fixture
async def streamable_http_client(streamable_http_app):
    """Create an httpx client using ASGITransport for testing streamable HTTP."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=streamable_http_app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.mark.anyio
async def test_public_tool_no_auth_required_streamable_http(
    streamable_http_client: httpx.AsyncClient,
) -> None:
    """Test that tools without required_scopes can be called without authentication (streamable HTTP)."""
    # Make a POST request to the tool endpoint without auth
    response = await streamable_http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "public_tool", "arguments": {"message": "test"}},
        },
        headers={"Content-Type": "application/json"},
    )

    # Should succeed (200 OK)
    assert response.status_code == 200
    result = response.json()
    assert result.get("result") is not None
    assert result["result"]["content"][0]["text"] == "Public: test"


@pytest.mark.anyio
async def test_tool_call_without_token_returns_401_streamable_http(
    streamable_http_client: httpx.AsyncClient,
) -> None:
    """Test that calling a tool with required_scopes without token returns 401."""
    # Make a POST request to the tool endpoint without auth
    response = await streamable_http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "read_tool", "arguments": {"message": "test"}},
        },
        headers={"Content-Type": "application/json"},
    )

    # Should get 401
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    www_auth = response.headers["WWW-Authenticate"]
    assert 'error="invalid_token"' in www_auth
    assert 'scope="read"' in www_auth


@pytest.mark.anyio
async def test_tool_call_with_insufficient_scope_returns_403_streamable_http(
    streamable_http_client: httpx.AsyncClient,
    mock_oauth_provider: MockOAuthProvider,
) -> None:
    """Test that calling a tool with insufficient scopes returns 403."""
    # Create a token with only "read" scope (not enough for write_tool which needs "read" and "write")
    token_with_read_only = f"token_read_{int(time.time())}"
    access_token = AccessToken(
        token=token_with_read_only,
        client_id="test_client",
        scopes=["read"],
        expires_at=int(time.time()) + 3600,
    )
    mock_oauth_provider.tokens[token_with_read_only] = access_token

    # Make a POST request with token that has insufficient scope
    response = await streamable_http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "write_tool", "arguments": {"message": "test"}},
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_with_read_only}",
        },
    )

    # Should get 403 for insufficient scope
    assert response.status_code == 403
    assert "WWW-Authenticate" in response.headers
    www_auth = response.headers["WWW-Authenticate"]
    assert 'error="insufficient_scope"' in www_auth
    assert 'scope="read write"' in www_auth


@pytest.mark.anyio
async def test_tool_call_with_valid_scopes_succeeds_streamable_http(
    streamable_http_client: httpx.AsyncClient,
    mock_oauth_provider: MockOAuthProvider,
) -> None:
    """Test that calling a tool with valid token and required scopes succeeds."""
    # Create a token with "read" scope
    token_with_read = f"token_read_{int(time.time())}"
    access_token = AccessToken(
        token=token_with_read,
        client_id="test_client",
        scopes=["read"],
        expires_at=int(time.time()) + 3600,
    )
    mock_oauth_provider.tokens[token_with_read] = access_token

    # Make a POST request with valid token
    response = await streamable_http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "read_tool", "arguments": {"message": "test"}},
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_with_read}",
        },
    )

    # Should succeed
    assert response.status_code == 200
    result = response.json()
    assert result.get("result") is not None
    assert result["result"]["content"][0]["text"] == "Read: test"


@pytest.mark.anyio
async def test_tool_call_with_multiple_scopes_succeeds_streamable_http(
    streamable_http_client: httpx.AsyncClient,
    mock_oauth_provider: MockOAuthProvider,
) -> None:
    """Test that calling a tool requiring multiple scopes succeeds with token having all scopes."""
    # Create a token with both "read" and "write" scopes
    token_with_read_write = f"token_read_write_{int(time.time())}"
    access_token = AccessToken(
        token=token_with_read_write,
        client_id="test_client",
        scopes=["read", "write"],
        expires_at=int(time.time()) + 3600,
    )
    mock_oauth_provider.tokens[token_with_read_write] = access_token

    # Make a POST request with token that has all required scopes
    response = await streamable_http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "write_tool", "arguments": {"message": "test"}},
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_with_read_write}",
        },
    )

    # Should succeed
    assert response.status_code == 200
    result = response.json()
    assert result.get("result") is not None
    assert result["result"]["content"][0]["text"] == "Write: test"


@pytest.mark.anyio
async def test_tool_call_with_wrong_scope_returns_403_streamable_http(
    streamable_http_client: httpx.AsyncClient,
    mock_oauth_provider: MockOAuthProvider,
) -> None:
    """Test that calling a tool with wrong scope (e.g., 'read' scope for 'admin' tool) returns 403."""
    # Create a token with only "read" scope (not "admin")
    token_with_read = f"token_read_{int(time.time())}"
    access_token = AccessToken(
        token=token_with_read,
        client_id="test_client",
        scopes=["read"],
        expires_at=int(time.time()) + 3600,
    )
    mock_oauth_provider.tokens[token_with_read] = access_token

    # Make a POST request with token that has wrong scope
    response = await streamable_http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "admin_tool", "arguments": {"message": "test"}},
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_with_read}",
        },
    )

    # Should get 403 for insufficient scope
    assert response.status_code == 403
    assert "WWW-Authenticate" in response.headers
    www_auth = response.headers["WWW-Authenticate"]
    assert 'error="insufficient_scope"' in www_auth
    assert 'scope="admin"' in www_auth
